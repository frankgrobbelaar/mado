import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type EngineStatus } from "@/lib/engine";
import { FOLDERS, fakeEngine, LIBRARY, READY, SETTINGS, scanDone } from "@/test/engine";
import { HomePage } from "./home-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function renderHome(engine: EngineStatus = READY, picked: string | null = null) {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return engine;
    if (command === "pick_folder") return picked;
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route index element={<HomePage />} />
            <Route path="/setup" element={<p>Setup</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) => (init?.method ?? "GET") === method && String(input).endsWith(path),
  );
}

/** A paragraph reading exactly `text`, however it's split into parts. */
function paragraph(text: string) {
  return (_: string, element: Element | null) =>
    element?.tagName === "P" && element.textContent === text;
}

describe("HomePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows the library in numbers, as the board draws it", async () => {
    fakeEngine({ "/settings": SETTINGS, "/library": LIBRARY, "/scan": scanDone() });
    renderHome();

    const panel = await screen.findByRole("region", { name: "Your library" });
    expect(within(panel).getByText("4,812")).toBeInTheDocument();
    expect(within(panel).getByRole("img")).toHaveAccessibleName(
      "Phone 3,104, Camera 1,422, Scans 286",
    );
    expect(within(panel).getByText("Camera RAW, not readable yet")).toBeInTheDocument();
    expect(within(panel).getByText("Won't open")).toBeInTheDocument();
    expect(
      screen.getByText(paragraph("4,812 pictures · 3 folders · 38.2 GB · read today 09:14, 6 new")),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "The tools come next" })).toBeInTheDocument();
  });

  it("says how far a scan has read while it reads", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone({ state: "running", stage: "reading", read: 212, toRead: 4812 }),
    });
    renderHome();

    expect(
      await screen.findByText(
        paragraph("4,812 pictures · 3 folders · 38.2 GB · reading 212 of 4,812"),
      ),
    ).toBeInTheDocument();
  });

  it("adds a folder picked in Windows' folder picker", async () => {
    const fetch = fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "POST /folders": FOLDERS[0],
    });
    renderHome(READY, "D:\\Pictures\\Phone");

    (await screen.findByRole("button", { name: "Add a folder" })).click();

    await waitFor(() => expect(sent(fetch, "POST", "/folders")).toHaveLength(1));
    const [[, init]] = sent(fetch, "POST", "/folders") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({ path: "D:\\Pictures\\Phone" });
  });

  it("says why a folder couldn't be added", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "POST /folders": () =>
        Response.json(
          { detail: "D:\\Pictures\\Phone is already in your library." },
          { status: 400 },
        ),
    });
    renderHome(READY, "D:\\Pictures\\Phone");

    (await screen.findByRole("button", { name: "Add a folder" })).click();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "D:\\Pictures\\Phone is already in your library.",
    );
  });

  it("shows an empty library with its one next step", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": { ...LIBRARY, folders: 0, pictures: 0, size: 0, raw: 0, broken: 0, parts: [] },
      "/scan": scanDone({ state: "idle", startedAt: null, finishedAt: null }),
    });
    renderHome();

    expect(
      await screen.findByRole("heading", { name: "Your library is empty" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add a folder" })).toHaveLength(1);
  });

  it("leads to setup until it's done", async () => {
    fakeEngine({ "/settings": { ...SETTINGS, setUp: false } });
    renderHome();

    expect(await screen.findByText("Setup")).toBeInTheDocument();
  });

  it("shows its layout while the engine answers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    renderHome();

    expect(await screen.findByRole("status", { name: "Loading Home" })).toBeInTheDocument();
  });

  it("says when the engine isn't running, instead of the page", async () => {
    fakeEngine({});
    renderHome({ state: "failed", message: "It stopped unexpectedly.", details: "" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Mado's engine isn't running.");
    expect(screen.queryByRole("status", { name: "Loading Home" })).not.toBeInTheDocument();
  });
});
