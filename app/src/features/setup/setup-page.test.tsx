import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  EngineProvider,
  type EngineStatus,
  type LibraryFolder,
  type Settings,
  type Tool,
} from "@/lib/engine";
import { FOLDERS, fakeEngine, READY, SETTINGS, scanDone } from "@/test/engine";
import { SetupPage } from "./setup-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const FFMPEG: Tool = {
  id: "ffmpeg",
  name: "ffmpeg",
  version: "9.0.2",
  purpose: "Reads and writes every kind of picture and video.",
  licence: "LGPL-2.1-or-later",
  size: 76_972_461,
  when: "setup",
  state: "missing",
  done: 0,
  problem: null,
};
/** A tool fetched the first time it's asked for: not on the Tools step. */
const LATER: Tool = {
  id: "model",
  name: "A model",
  version: "1",
  purpose: "Fetched when it's asked for.",
  licence: "MIT",
  size: 50_000_000,
  when: "asked",
  state: "missing",
  done: 0,
  problem: null,
};

/** A first run: setup not done, ffmpeg still to fetch. */
function firstRun(overrides: Record<string, unknown> = {}) {
  const saved = { settings: { ...SETTINGS, setUp: false } as Settings };
  return fakeEngine({
    "/health": {
      status: "ok",
      version: "0.1.0",
      dataDir: "C:\\Users\\you\\AppData\\Local\\Mado",
      schemaVersion: 1,
    },
    "/settings": () => saved.settings,
    "PUT /settings": (init?: RequestInit) => {
      saved.settings = JSON.parse(String(init?.body)) as Settings;
      return saved.settings;
    },
    "/tools": [FFMPEG],
    "POST /tools/ffmpeg/download": { ...FFMPEG, state: "downloading" },
    "/folders": [],
    "/scan": scanDone({ state: "idle", startedAt: null, finishedAt: null }),
    ...overrides,
  });
}

function renderSetup(engine: EngineStatus = READY, picked: string | null = null) {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return engine;
    if (command === "pick_folder") return picked;
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/setup"]}>
          <Routes>
            <Route path="/setup" element={<SetupPage />} />
            <Route path="/" element={<p>Home</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

/** An element reading exactly `text`, however it's split into parts. */
function reading(text: string) {
  return (_: string, element: Element | null) => element?.textContent === text;
}

/** On from the tools, once they're ready, to the folders. */
async function toTheFolders() {
  const next = await screen.findByRole("button", { name: "Next: your folders" });
  await waitFor(() => expect(next).toBeEnabled());
  next.click();
}

function sent(fetch: ReturnType<typeof firstRun>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) => (init?.method ?? "GET") === method && String(input).endsWith(path),
  );
}

describe("SetupPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("welcomes the owner and downloads ffmpeg", async () => {
    const fetch = firstRun();
    renderSetup();

    expect(screen.getByRole("heading", { name: "Welcome to Mado" })).toBeInTheDocument();
    expect(await screen.findByText("ffmpeg")).toBeInTheDocument();
    expect(screen.getByText("77 MB · LGPL-2.1-or-later")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next: your folders" })).toBeDisabled();
    const steps = screen.getByRole("list", { name: "Setup" });
    expect(within(steps).getByText("1 · Tools")).toHaveAttribute("aria-current", "step");
    screen.getByRole("button", { name: "Download" }).click();

    await waitFor(() => expect(sent(fetch, "POST", "/tools/ffmpeg/download")).toHaveLength(1));
  });

  it("shows how far a download has got", async () => {
    firstRun({ "/tools": [{ ...FFMPEG, state: "downloading", done: 38_486_230 }] });
    renderSetup();

    expect(await screen.findByRole("progressbar", { name: "Downloading ffmpeg" })).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
  });

  it("says why a download failed, and offers to try again", async () => {
    firstRun({
      "/tools": [
        { ...FFMPEG, state: "failed", problem: "The download didn't match its checksum." },
      ],
    });
    renderSetup();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The download didn't match its checksum.",
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("goes on to the folders once the tools are ready, and remembers setup is done", async () => {
    const fetch = firstRun({
      "/tools": [{ ...FFMPEG, state: "ready", done: FFMPEG.size }, LATER],
    });
    renderSetup();

    expect(await screen.findByText("ffmpeg")).toBeInTheDocument();
    expect(screen.queryByText("A model")).not.toBeInTheDocument(); // fetched when asked for

    const next = await screen.findByRole("button", { name: "Next: your folders" });
    await waitFor(() => expect(next).toBeEnabled());
    next.click();

    expect(
      await screen.findByRole("heading", { name: "Where do your pictures live?" }),
    ).toBeInTheDocument();
    expect(screen.getByText("2 · Your folders")).toHaveAttribute("aria-current", "step");
    const start = screen.getByRole("button", { name: "Start using Mado" });
    await waitFor(() => expect(start).toBeEnabled());
    start.click();

    expect(await screen.findByText("Home")).toBeInTheDocument();
    const [[, put]] = sent(fetch, "PUT", "/settings") as [[unknown, RequestInit]];
    expect(JSON.parse(String(put.body))).toEqual({ setUp: true });
  });

  it("adds the folders pictures live in and says what it found in each", async () => {
    const looking: LibraryFolder = {
      ...FOLDERS[2],
      id: 4,
      path: "E:\\Scans",
      looked: false,
      pictures: 200,
      reading: 12,
    } as LibraryFolder;
    const fetch = firstRun({
      "/tools": [{ ...FFMPEG, state: "ready", done: FFMPEG.size }],
      "/folders": [FOLDERS[0], FOLDERS[1], looking],
      "POST /folders": FOLDERS[0],
      "DELETE /folders/1": null,
      "/scan": scanDone({ state: "running", stage: "reading", secondsLeft: 185 }),
    });
    renderSetup(READY, "D:\\Pictures\\Phone");
    await toTheFolders();

    const added = await screen.findByRole("region", { name: "Folders added" });
    expect(await within(added).findByText("D:\\Pictures\\Phone")).toBeInTheDocument();
    expect(within(added).getByText(reading("Found 3,104 pictures"))).toBeInTheDocument();
    expect(
      within(added).getByText(reading("Found 1,422 pictures, 318 of them camera RAW")),
    ).toBeInTheDocument();
    expect(within(added).getByText(reading("Looking… 212 so far"))).toBeInTheDocument();
    expect(
      screen.getByText(
        reading(
          "It reads the rest in the background, about 3 min for 4,738 pictures, and keeps watching these folders for new ones.",
        ),
      ),
    ).toBeInTheDocument();

    within(added).getByRole("button", { name: "Add a folder" }).click();
    within(added).getByRole("button", { name: "Take D:\\Pictures\\Phone out" }).click();

    await waitFor(() => expect(sent(fetch, "POST", "/folders")).toHaveLength(1));
    await waitFor(() => expect(sent(fetch, "DELETE", "/folders/1")).toHaveLength(1));
  });

  it("starts without folders, which can come later", async () => {
    const fetch = firstRun({ "/tools": [{ ...FFMPEG, state: "ready", done: FFMPEG.size }] });
    renderSetup();
    await toTheFolders();

    expect(await screen.findByText(/No folders yet\? Skip this/)).toBeInTheDocument();
    const start = screen.getByRole("button", { name: "Start using Mado" });
    await waitFor(() => expect(start).toBeEnabled());
    start.click();

    expect(await screen.findByText("Home")).toBeInTheDocument();
    expect(sent(fetch, "PUT", "/settings")).toHaveLength(1);
  });

  it("goes back to the tools from the folders", async () => {
    firstRun({ "/tools": [{ ...FFMPEG, state: "ready", done: FFMPEG.size }] });
    renderSetup();
    await toTheFolders();

    (await screen.findByRole("button", { name: "Back" })).click();

    expect(await screen.findByRole("heading", { name: "Welcome to Mado" })).toBeInTheDocument();
  });

  it("says when the engine isn't running, and offers to try again", async () => {
    firstRun();
    renderSetup({ state: "failed", message: "It stopped unexpectedly.", details: "" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mado's engine isn't running. It stopped unexpectedly. Nothing in your folders was touched.",
    );
    screen.getByRole("button", { name: "Try again" }).click();

    expect(shell.invoke).toHaveBeenCalledWith("restart_engine");
  });

  it("says when the engine couldn't answer, and asks again", async () => {
    let asked = 0;
    firstRun({
      "/tools": () => {
        asked += 1;
        return asked === 1 ? new Response("Internal Server Error", { status: 500 }) : [FFMPEG];
      },
    });
    renderSetup();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mado couldn't load this screen. The engine answered 500 to GET /tools.",
    );
    screen.getByRole("button", { name: "Try again" }).click();

    expect(await screen.findByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
