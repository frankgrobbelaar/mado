import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type EngineStatus, type Settings, type Tool } from "@/lib/engine";
import { fakeEngine, READY, SETTINGS } from "@/test/engine";
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
    ...overrides,
  });
}

function renderSetup(engine: EngineStatus = READY) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? engine : undefined,
  );
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
    expect(screen.getByRole("button", { name: "Finish" })).toBeDisabled();
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

  it("finishes once the tools are ready, and remembers setup is done", async () => {
    const fetch = firstRun({
      "/tools": [{ ...FFMPEG, state: "ready", done: FFMPEG.size }, LATER],
    });
    renderSetup();

    expect(await screen.findByText("ffmpeg")).toBeInTheDocument();
    expect(screen.queryByText("A model")).not.toBeInTheDocument(); // fetched when asked for

    const finish = await screen.findByRole("button", { name: "Finish" });
    await waitFor(() => expect(finish).toBeEnabled());
    finish.click();

    expect(await screen.findByText("Home")).toBeInTheDocument();
    const [[, put]] = sent(fetch, "PUT", "/settings") as [[unknown, RequestInit]];
    expect(JSON.parse(String(put.body))).toEqual({ setUp: true });
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
