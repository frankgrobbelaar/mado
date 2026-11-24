/**
 * HDR photos' and saving as it is's screens, as Mado draws them, written out to be shot in dark
 * and light:
 *
 *   node scripts/readme-pictures.mjs --screens app/src/features/picture/hdr-screens.test.tsx --out <folder>
 *
 * An HDR photo's page (its facts saying HDR, Save there with nothing chosen); Save keeping its HDR,
 * and saying a format that can't before Save; a HEIC saved as it is, as a JPEG; a gain map Mado
 * can't read; the Library's HDR tags; Many at once as just Save, and its HDR choice; History saying
 * what a picture saved as it is was saved as; the wallpaper studio saying Windows' wallpaper is an
 * ordinary picture. Skipped unless MADO_SHOTS names a folder. Every picture is a scene the shoot
 * draws by code, every name made up.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, it, vi } from "vitest";
import { AppShell } from "@/components/shell/app-shell";
import { BatchPage } from "@/features/batch/batch-page";
import { HistoryPage } from "@/features/history/history-page";
import { HomePage } from "@/features/home/home-page";
import { LibraryPage } from "@/features/library/library-page";
import { WallpaperPage } from "@/features/wallpaper/wallpaper-page";
import { EngineProvider, type GainMap, type PictureItem } from "@/lib/engine";
import {
  batch,
  choice,
  duplicates,
  entry,
  FOLDERS,
  fakeEngine,
  LIBRARY,
  monitor,
  PC,
  PICKED,
  page,
  part,
  picture,
  pictureDetails,
  plan,
  READY,
  SETTINGS,
  SIZES,
  scanDone,
  studio,
  takes,
  WORDS,
} from "@/test/engine";
import { drawScenes, dump, measuredBoxes, SHOTS, scene } from "@/test/shots";
import { PicturePage } from "./picture-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({ minimize() {}, toggleMaximize() {}, close() {} }),
}));

/** A phone's HDR photo's gain map: three stops, a quarter of its size. */
const GAIN: GainMap = {
  readable: true,
  stops: 3,
  baseIsHdr: false,
  colour: false,
  width: 1008,
  height: 756,
  why: null,
};

/** The pictures in Phone, newest first, each with the scene drawn for it. */
const PHONE: [PictureItem, string][] = [
  [picture(10, "Night market.jpg", "2026-11-14T21:10:00", { hdr: true }), "night-market"],
  [picture(11, "Harbour at dusk.heic", "2026-11-14T18:42:07", { hdr: true }), "harbour"],
  [picture(12, "Little sail.jpg", "2026-11-14T16:05:00", { hdr: true }), "little-sail"],
  [picture(13, "Low tide.jpg", "2026-11-14T14:20:00"), "low-tide"],
  [picture(14, "Spring meadow.heic", "2026-11-14T11:31:00"), "spring-meadow"],
  [picture(15, "Still lake.jpg", "2026-11-14T07:58:00", { hdr: true }), "still-lake"],
  [picture(20, "Warm dunes.jpg", "2026-11-13T17:20:00"), "warm-dunes"],
  [picture(21, "Garden rose.jpg", "2026-11-13T15:47:00", { hdr: true }), "garden-rose"],
  [picture(22, "Red canyon.jpg", "2026-11-13T12:30:00"), "red-canyon"],
  [picture(24, "Snowfield.jpg", "2026-11-13T10:02:00"), "snowfield"],
  [picture(25, "Misty pines.jpg", "2026-11-13T09:12:00"), "misty-pines"],
  [picture(30, "Green sky.jpg", "2026-11-11T23:51:00", { hdr: true }), "green-sky"],
];
const SCENES = new Map(PHONE.map(([item, drawn]) => [item.id, drawn]));
const ITEMS = PHONE.map(([item]) => item);
const item = (id: number) => ITEMS.find((each) => each.id === id) as PictureItem;

const QUIET = {
  working: false,
  paused: false,
  batch: null,
  over: 0,
  total: 0,
  progress: 0,
  waiting: 0,
};

/** What every screen's engine answers: the made-up library, a quiet queue. */
const EVERYWHERE: Record<string, unknown> = {
  "/health": { status: "ok", version: "0.13.0", dataDir: "", schemaVersion: 15 },
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
  "/recipes": [],
  "POST /screens": [],
  "/queue/now": QUIET,
};

function pictureFor(url: URL): Response | undefined {
  const copy = url.pathname.match(/^\/pictures\/(\d+)\/(thumbnail|view|full|preview)$/);
  if (copy) return scene(SCENES.get(Number(copy[1])) ?? "harbour");
  if (url.pathname.match(/^\/history\/\d+\/thumbnail$/)) return scene("harbour");
  return undefined;
}

function engine(answers: Record<string, unknown>) {
  const fetch = fakeEngine({ ...EVERYWHERE, ...answers });
  const answer = fetch.getMockImplementation();
  fetch.mockImplementation(async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (answer && `${init?.method ?? "GET"} ${url.pathname}` in answers) return answer(input, init);
    return (
      pictureFor(url) ??
      (answer ? answer(input, init) : Response.json({ detail: "Not found" }, { status: 404 }))
    );
  });
}

/** A picture in Phone opened: its details, gain map and plan, and the name Save would give. */
function opened(id: number, gainMap: GainMap | null, made: Parameters<typeof plan>[0] = {}) {
  const shown = item(id);
  const stem = shown.name.replace(/\.[^.]+$/, "");
  return {
    [`/pictures/${id}`]: pictureDetails(shown, { gainMap }),
    [`/pictures/${id}/neighbours`]: { before: [], after: [] },
    [`POST /pictures/${id}/plan`]: plan({
      width: 4032,
      height: 3024,
      hdr: gainMap?.readable ? "kept" : "none",
      format: "JPEG",
      formatQuality: 92,
      ...made,
    }),
    [`POST /pictures/${id}/saving`]: {
      name: made.label ? `${stem} (${made.label}).jpg` : `${stem}.jpg`,
      folder: "D:\\Pictures\\Phone",
      taken: null,
      takenAt: null,
      bytes: made.label ? 18_000_000 : 3_400_000,
      colour: "Display P3",
    },
  };
}

function draw(route: string, at: string, shown: ReactNode, state?: unknown) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : command === "screens" ? [] : undefined,
  );
  const [pathname = at, search] = at.split("?");
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[{ pathname, search: search ? `?${search}` : "", state }]}>
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

/** The picture's page, its Save dialog opened once Save is ready. */
async function saveOpened(id: number) {
  draw("/library/pictures/:id", `/library/pictures/${id}?folder=1`, <PicturePage />);
  await settle(800);
  fireEvent.click(await screen.findByRole("button", { name: "Save…" }));
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByText("Keep from the original");
  return dialog;
}

describe.runIf(SHOTS)("HDR photos' and saving as it is's screens", () => {
  beforeEach(() => drawScenes());
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("hdr-page", async () => {
    engine(opened(12, GAIN));
    await measuredBoxes("hdr-page");
    draw("/library/pictures/:id", "/library/pictures/12?folder=1", <PicturePage />);
    await screen.findByText(/JPEG · HDR/);
    await screen.findByText(/Save keeps it as it is/);
    await settle();
    await dump("hdr-page");
  });

  it("hdr-save", async () => {
    engine(opened(12, GAIN, { label: "TV 8K", width: 7680, height: 4320, formatQuality: 95 }));
    await measuredBoxes("hdr-save");
    draw("/library/pictures/:id", "/library/pictures/12?folder=1", <PicturePage />);
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));
    await settle(800);
    fireEvent.click(await screen.findByRole("button", { name: "Save…" }));
    await screen.findByRole("checkbox", { name: "Its HDR (the gain map)" });
    await settle();
    await dump("hdr-save");
  });

  it("hdr-save-png", async () => {
    engine(opened(12, GAIN, { label: "TV 8K", width: 7680, height: 4320, formatQuality: 95 }));
    await measuredBoxes("hdr-save-png");
    draw("/library/pictures/:id", "/library/pictures/12?folder=1", <PicturePage />);
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));
    await settle(800);
    fireEvent.click(await screen.findByRole("button", { name: "Save…" }));
    fireEvent.click(await screen.findByRole("radio", { name: "PNG" }));
    await screen.findByText(/PNG has no room for a gain map/);
    await settle();
    await dump("hdr-save-png");
  });

  it("as-is-save", async () => {
    engine(opened(11, { ...GAIN, stops: 2 }, { format: "JPEG", formatQuality: 92 }));
    await measuredBoxes("as-is-save");
    await saveOpened(11);
    await screen.findByText(/Replacing the original isn't offered: saved as it is/);
    await settle();
    await dump("as-is-save");
  });

  it("as-is-same-format", async () => {
    engine(opened(13, null, { format: "JPEG", formatQuality: 88 }));
    await measuredBoxes("as-is-same-format");
    await saveOpened(13);
    await screen.findByText(/It's a JPEG already/);
    await settle();
    await dump("as-is-same-format");
  });

  it("hdr-unread", async () => {
    engine(
      opened(15, {
        ...GAIN,
        readable: false,
        stops: null,
        why: "Its gain map is version 2.0, which Mado doesn't know yet.",
      }),
    );
    await measuredBoxes("hdr-unread");
    draw("/library/pictures/:id", "/library/pictures/15?folder=1", <PicturePage />);
    await screen.findByText(/Mado shows and saves it as an ordinary picture/);
    await settle();
    await dump("hdr-unread");
  });

  it("hdr-library", async () => {
    engine({ "/pictures": page(ITEMS, null, ITEMS.length) });
    await measuredBoxes("hdr-library");
    draw("/library", "/library?folder=1", <LibraryPage />);
    await screen.findAllByText("HDR");
    await settle();
    await dump("hdr-library");
  });

  it("batch-just-save", async () => {
    engine({
      "POST /batches/takes": takes({ words: WORDS.filter((each) => each.kind === "save") }),
    });
    await measuredBoxes("batch-just-save");
    draw("/batch", "/batch", <BatchPage />, {
      pick: { how: "ticked", ids: [1, 2, 3] },
      picked: PICKED,
    });
    await screen.findByText(/With none, each is saved as it is/);
    await settle();
    await dump("batch-just-save");
  });

  it("batch-save-hdr", async () => {
    engine({});
    await measuredBoxes("batch-save-hdr");
    draw("/batch", "/batch", <BatchPage />, {
      pick: { how: "ticked", ids: [1, 2, 3] },
      picked: PICKED,
    });
    fireEvent.click(await screen.findByRole("button", { name: "Change save" }));
    fireEvent.click(await screen.findByRole("radio", { name: "WebP" }));
    await screen.findByText(/WebP has no room for a gain map/);
    await settle();
    await dump("batch-save-hdr");
  });

  it("history-saved-as", async () => {
    engine({
      "/history": {
        entries: [
          entry({
            name: "Harbour at dusk.heic",
            madeFor: null,
            result: "D:\\Pictures\\Phone\\Harbour at dusk.jpg",
            resultName: "Harbour at dusk.jpg",
          }),
          entry({
            id: 2,
            name: "Little sail.jpg",
            madeFor: null,
            result: "D:\\Pictures\\Phone\\Little sail (2).avif",
            resultName: "Little sail (2).avif",
          }),
        ],
        older: null,
        batches: [],
      },
    });
    await measuredBoxes("history-saved-as");
    draw("/history", "/history", <HistoryPage />);
    await screen.findByText("Saved Harbour at dusk as JPEG");
    await settle();
    await dump("history-saved-as");
  });

  it("wallpaper-hdr", async () => {
    const shown = item(12);
    engine({
      "/wallpaper": studio({
        monitors: [monitor({ key: "desk27", name: "Desk 27", number: 1 })],
        width: 2560,
        height: 1440,
        choices: [
          choice({
            monitor: "desk27",
            picture: {
              id: 12,
              name: shown.name,
              path: shown.path,
              width: 4032,
              height: 3024,
              version: shown.version,
              outside: false,
              hdr: true,
              focus: { x: 0.5, y: 0.5 },
            },
          }),
        ],
        parts: [part({ monitor: "desk27", picture: 12 })],
      }),
    });
    await measuredBoxes("wallpaper-hdr");
    draw("/wallpaper", "/wallpaper", <WallpaperPage />);
    await screen.findByText(/Windows shows a wallpaper as an ordinary picture/);
    await settle();
    await dump("wallpaper-hdr");
  });

  it("home-just-save", async () => {
    engine({
      "/duplicates": duplicates({ duplicates: 0, bursts: 0, pictures: 0 }),
      "/batches/done": [
        batch({
          source: "Phone",
          done: 240,
          failed: 0,
          waiting: 0,
          progress: 1,
          startedAt: "2026-11-24T15:00:00",
          madeFor: null,
          look: null,
          purpose: null,
          savedAs: "JPEG",
          into: "beside the originals",
          folder: "D:\\Pictures\\Phone",
        }),
      ],
      "/space": [
        {
          drive: "D:",
          connected: true,
          free: 412_000_000_000,
          total: 1_000_000_000_000,
          pictures: 38_200_000_000,
          quarantine: 1_400_000_000,
          queue: 0,
        },
      ],
      "/history/today": [],
    });
    await measuredBoxes("home-just-save");
    draw("/", "/", <HomePage />);
    await screen.findByText(/Saved as JPEG, as new pictures beside the originals/);
    await settle();
    await dump("home-just-save");
  });
});
