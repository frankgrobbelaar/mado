/**
 * Search's screens, as Mado draws them, written out to be shot in dark and light:
 *
 *   node scripts/readme-pictures.mjs --screens app/src/test/search-screens.test.tsx --out <folder>
 *
 * No board draws them, so they're drawn in Graphite's own patterns: the Library's results in
 * groups (the words marked, the closest first, a picture on a drive away), with the library still
 * being read; search's reader of pictures on its way; nothing found, and a search in another
 * language; a writing Windows can't read here; a reader that couldn't run, and pictures that
 * couldn't be read; More like this; a picture's page with More like this; Home while the library
 * is read; Settings › General › Search. Skipped unless MADO_SHOTS
 * names a folder. Every picture is a scene the shoot draws by code, every name made up.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, it, vi } from "vitest";
import { AppShell } from "@/components/shell/app-shell";
import { HomePage } from "@/features/home/home-page";
import { LibraryPage } from "@/features/library/library-page";
import { PicturePage } from "@/features/picture/picture-page";
import { SettingsPage } from "@/features/settings/settings-page";
import { EngineProvider, type PictureItem } from "@/lib/engine";
import {
  duplicates,
  FOLDERS,
  fakeEngine,
  hit,
  LIBRARY,
  PC,
  picture,
  pictureDetails,
  plan,
  READY,
  SETTINGS,
  SIZES,
  scanDone,
  searchModel,
  searchResults,
  searchState,
} from "./engine";
import { drawScenes, dump, measuredBoxes, SHOTS, scene } from "./shots";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({ minimize() {}, toggleMaximize() {}, close() {} }),
}));

/** Phone's pictures a search finds, each with the scene drawn for it. */
const FOUND: [PictureItem, string][] = [
  [picture(70, "Corner market.jpg", "2026-11-12T19:10:00"), "night-market"],
  [picture(71, "Late stall.jpg", "2026-11-09T21:40:00"), "night-market/flip"],
  [picture(72, "Little sail.jpg", "2026-11-14T16:05:00"), "little-sail"],
  [picture(73, "Low tide.jpg", "2026-11-14T14:20:00"), "low-tide"],
  [picture(74, "Open water.jpg", "2026-11-13T11:03:00"), "little-sail/flip"],
  [picture(75, "Harbour at dusk.heic", "2026-11-14T18:42:07"), "harbour"],
  [picture(76, "Still lake.jpg", "2026-11-14T07:58:00"), "still-lake"],
  [picture(77, "Shoreline.jpg", "2026-11-11T13:22:00"), "low-tide/flip"],
  [picture(78, "Sailing club 2026.jpg", "2026-10-02T10:00:00"), "warm-dunes"],
  [picture(79, "Boat race.jpg", "2026-09-20T15:30:00"), "spring-meadow"],
];
const SCENES = new Map(FOUND.map(([item, drawn]) => [item.id, drawn]));
const item = (id: number) => FOUND.find(([each]) => each.id === id)?.[0] as PictureItem;

/** What a search for "sail" finds: the words on two stalls, five that look like it, two names. */
const SAIL = searchResults("sail", [
  {
    kind: "words",
    pictures: [
      hit(item(70), {
        words: [
          { text: "Fresh fish · ", marked: false },
          { text: "SAIL", marked: true },
          { text: " & ROPE 24", marked: false },
        ],
      }),
      hit(item(71), {
        words: [
          { text: "Last ", marked: false },
          { text: "sailing", marked: true },
          { text: " 21:30", marked: false },
        ],
      }),
    ],
    total: 2,
  },
  {
    kind: "described",
    pictures: [72, 74, 75, 73, 77].map((id, at) =>
      hit(item(id), { score: 0.9 - at * 0.12, away: id === 77 }),
    ),
    total: 5,
  },
  { kind: "name", pictures: [hit(item(78))], total: 1 },
]);

const READING = searchState({ read: 2340, of: 18200, reading: true });

const EVERYWHERE: Record<string, unknown> = {
  "/health": { status: "ok", version: "0.8.0", dataDir: "", schemaVersion: 10 },
  "/settings": SETTINGS,
  "/library": LIBRARY,
  "/folders": FOLDERS,
  "/scan": scanDone(),
  "/records": null,
  "/pc": PC,
  "/jobs": [],
  "/jobs/held": [],
  "/tools": [],
  "/sizes": SIZES,
  "/looks": { looks: [], yours: [] },
  "POST /screens": [],
  "/search/state": searchState(),
  "/queue/now": {
    working: false,
    paused: false,
    batch: null,
    over: 0,
    total: 0,
    progress: 0,
    waiting: 0,
  },
};

function pictureFor(url: URL): Response | undefined {
  const copy = url.pathname.match(/^\/pictures\/(\d+)\/(thumbnail|view|full)$/);
  if (copy) return scene(SCENES.get(Number(copy[1])) ?? "harbour");
  return undefined;
}

function engine(answers: Record<string, unknown>) {
  const fetch = fakeEngine({ ...EVERYWHERE, ...answers });
  const answer = fetch.getMockImplementation();
  fetch.mockImplementation(async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    return (
      pictureFor(url) ??
      (answer ? answer(input, init) : Response.json({ detail: "Not found" }, { status: 404 }))
    );
  });
}

function draw(route: string, at: string, shown: ReactNode) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : command === "screens" ? [] : undefined,
  );
  const [pathname = at, search] = at.split("?");
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[{ pathname, search: search ? `?${search}` : "" }]}>
          <Routes>
            <Route element={<AppShell />}>
              <Route path={route} element={shown} />
            </Route>
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

async function settle(ms = 1500) {
  for (let waited = 0; waited < ms; waited += 100) {
    await act(async () => {
      await new Promise((done) => setTimeout(done, 100));
    });
  }
}

describe.runIf(SHOTS)("Search's screens", () => {
  beforeEach(() => drawScenes());
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("search-results", async () => {
    engine({ "/search": { ...SAIL, state: READING } });
    await measuredBoxes("search-results");
    draw("/library", "/library?folder=1&q=sail", <LibraryPage />);
    await screen.findByText(/With the words/);
    await settle();
    await dump("search-results");
  });

  it("search-model-coming", async () => {
    const coming = searchState({
      read: 0,
      describer: searchModel("siglip-base-patch16-224", { state: "downloading", done: 86_000_000 }),
      words: { ...searchState().words, model: searchModel("pp-ocrv6-small") },
    });
    engine({
      "/search": searchResults("sail", [{ kind: "name", pictures: [hit(item(78))], total: 1 }], {
        state: coming,
      }),
    });
    await measuredBoxes("search-model-coming");
    draw("/library", "/library?folder=1&q=sail", <LibraryPage />);
    await screen.findByText(/Getting Mado's reader of pictures/);
    await settle();
    await dump("search-model-coming");
  });

  it("search-nothing-other-language", async () => {
    engine({ "/search": searchResults("le bateau", [], { english: false }) });
    await measuredBoxes("search-nothing-other-language");
    draw("/library", "/library?folder=1&q=le%20bateau", <LibraryPage />);
    await screen.findByText(/Nothing in Phone matches/);
    await settle();
    await dump("search-nothing-other-language");
  });

  it("search-windows-cant-read", async () => {
    const windows = searchState({
      words: { ...searchState().words, chosen: "fast", reader: "fast", model: null },
      busy: true,
      reading: true,
      read: 16100,
      of: 18200,
    });
    engine({
      "/search": searchResults("Βάρκα", [], { unreadable: "Greek", state: windows }),
    });
    await measuredBoxes("search-windows-cant-read");
    draw("/library", "/library?q=%CE%92%CE%AC%CF%81%CE%BA%CE%B1", <LibraryPage />);
    await screen.findByText(/Windows reads words only in English/);
    await settle();
    await dump("search-windows-cant-read");
  });

  it("search-reader-stuck", async () => {
    const stuck = searchState({
      read: 2,
      of: 4812,
      problem: { reader: "words", said: "The graphics card couldn't run the AI model (made up)." },
    });
    engine({ "/search": { ...SAIL, state: stuck } });
    await measuredBoxes("search-reader-stuck");
    draw("/library", "/library?folder=1&q=sail", <LibraryPage />);
    await screen.findByText(/couldn't run/);
    await settle();
    await dump("search-reader-stuck");
  });

  it("search-some-unread", async () => {
    engine({ "/search": { ...SAIL, state: searchState({ read: 4810, of: 4812, failed: 2 }) } });
    await measuredBoxes("search-some-unread");
    draw("/library", "/library?folder=1&q=sail", <LibraryPage />);
    await screen.findByText(/couldn't be read for search/);
    await settle();
    await dump("search-some-unread");
  });

  it("more-like-this", async () => {
    engine({
      "/search/like/75": searchResults("Harbour at dusk.heic", [
        {
          kind: "like",
          pictures: [72, 74, 73, 77, 76, 79].map((id, at) =>
            hit(item(id), { score: 0.92 - at * 0.04 }),
          ),
          total: 6,
        },
      ]),
    });
    await measuredBoxes("more-like-this");
    draw("/library", "/library?like=75", <LibraryPage />);
    await screen.findByText(/Most like Harbour at dusk/);
    await settle();
    await dump("more-like-this");
  });

  it("picture-more-like-this", async () => {
    engine({
      "/pictures/75": pictureDetails(item(75), { camera: null }),
      "/pictures/75/neighbours": { before: [item(72)], after: [item(73), item(76)] },
      "POST /pictures/75/plan": plan({ width: 4032, height: 3024, label: "", sides: "none" }),
    });
    await measuredBoxes("picture-more-like-this");
    draw("/library/pictures/:id", "/library/pictures/75?folder=1", <PicturePage />);
    await screen.findByRole("button", { name: "More like this" });
    await settle();
    await dump("picture-more-like-this");
  });

  it("home-reading", async () => {
    engine({
      "/search/state": READING,
      "/duplicates": duplicates({ groups: [], duplicates: 0, bursts: 0, pictures: 0 }),
      "/batches/done": [],
      "/space": [],
      "/history/today": [],
    });
    await measuredBoxes("home-reading");
    draw("/", "/", <HomePage />);
    await screen.findByText("Read for search");
    await settle();
    await dump("home-reading");
  });

  it("settings-search", async () => {
    engine({ "/search/state": READING });
    await measuredBoxes("settings-search");
    draw("/settings/:section", "/settings/general", <SettingsPage />);
    const panel = await screen.findByRole("region", { name: "Search" });
    await settle();
    // Only the page scrolls: the panels above it are left out, so it shows in the shot.
    for (const above of ["General", "Saving", "Many at once"])
      screen.getByRole("region", { name: above }).remove();
    panel.scrollIntoView?.();
    await dump("settings-search");
  });
});
