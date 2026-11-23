/**
 * Camera RAW's screens, as Mado draws them, written out to be shot in dark and light:
 *
 *   node scripts/readme-pictures.mjs --screens app/src/test/raw-screens.test.tsx --out <folder>
 *
 * The Library with RAWs read (a camera's RAW and its JPEG side by side) and while Mado's RAW
 * reader comes; a RAW's page waiting for the reader, the reader not come, a RAW from a camera the
 * reader doesn't know, a huge RAW developed at full size; Save for a RAW; Many at once with RAWs
 * waiting, and with RAWs in it; Home's numbers; Settings › About's downloads. Skipped unless
 * MADO_SHOTS names a folder. Every picture is a scene the shoot draws by code, every name made up.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, it, vi } from "vitest";
import { AppShell } from "@/components/shell/app-shell";
import { BatchPage } from "@/features/batch/batch-page";
import { HomePage } from "@/features/home/home-page";
import { LibraryPage } from "@/features/library/library-page";
import { PicturePage } from "@/features/picture/picture-page";
import { SettingsPage } from "@/features/settings/settings-page";
import { EngineProvider, type PictureItem, type Tool } from "@/lib/engine";
import {
  batchPicture,
  FOLDERS,
  fakeEngine,
  LIBRARY,
  PC,
  page,
  picture,
  pictureDetails,
  plan,
  READY,
  RECIPE,
  rawReader,
  SAMPLES,
  SETTINGS,
  SIZES,
  scanDone,
  takes,
} from "./engine";
import { drawScenes, dump, measuredBoxes, SHOTS, scene } from "./shots";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({ minimize() {}, toggleMaximize() {}, close() {} }),
}));

const CAMERA = "D:\\Pictures\\Camera";

/** A picture in Camera: a RAW when its name says so. */
function shot(id: number, name: string, takenAt: string, more: Partial<PictureItem> = {}) {
  const raw = /\.(cr3|nef|dng|arw)$/i.test(name);
  return picture(id, name, takenAt, {
    path: `${CAMERA}\\${name}`,
    format: name.split(".").pop()?.toUpperCase() ?? "JPEG",
    raw,
    width: raw ? 6000 : 4032,
    height: raw ? 4000 : 3024,
    size: raw ? 31_000_000 : 6_200_000,
    ...more,
  });
}

/** Camera's pictures, newest first, each with the scene drawn for it: RAW and JPEG of one moment
 * sit side by side. */
const CAMERA_PICTURES: [PictureItem, string][] = [
  [shot(40, "Harbour at dusk.CR3", "2026-11-14T18:42:07"), "harbour"],
  [shot(41, "Harbour at dusk.JPG", "2026-11-14T18:42:07"), "harbour"],
  [shot(42, "Little sail.CR3", "2026-11-14T16:05:00"), "little-sail"],
  [shot(43, "Little sail.JPG", "2026-11-14T16:05:00"), "little-sail"],
  [shot(44, "Low tide.NEF", "2026-11-14T14:20:00"), "low-tide"],
  [shot(45, "Spring meadow.DNG", "2026-11-14T11:31:00"), "spring-meadow"],
  [shot(46, "Red canyon.NEF", "2026-11-13T12:30:00"), "red-canyon"],
  [shot(47, "Snowfield.DNG", "2026-11-13T10:02:00"), "snowfield"],
  [shot(48, "Misty pines.JPG", "2026-11-13T09:12:00"), "misty-pines"],
  [shot(49, "Green sky.CR3", "2026-11-11T23:51:00"), "green-sky"],
];
const SCENES = new Map(CAMERA_PICTURES.map(([item, drawn]) => [item.id, drawn]));
const ITEMS = CAMERA_PICTURES.map(([item]) => item);
const item = (id: number) => ITEMS.find((each) => each.id === id) as PictureItem;
/** The same pictures while Mado's RAW reader comes: the RAWs listed as they are. */
const WAITING = ITEMS.map((each) =>
  each.raw ? { ...each, state: "waiting" as const, width: null, height: null } : each,
);

const DOWNLOADS: Tool[] = [
  {
    id: "ffmpeg",
    name: "ffmpeg",
    version: "9.0.2",
    purpose: "Reads and writes picture formats.",
    licence: "LGPL-2.1-or-later",
    size: 76_972_461,
    when: "setup",
    state: "ready",
    done: 76_972_461,
    problem: null,
  },
  rawReader("ready"),
  {
    id: "realesrgan-x4plus",
    name: "RealESRGAN x4plus",
    version: "0.1.0",
    purpose: "Best for photos.",
    licence: "BSD-3-Clause AND Apache-2.0",
    size: 67_087_820,
    when: "asked",
    state: "missing",
    done: 0,
    problem: null,
  },
];

const OFFLINE =
  "Mado couldn't download LibRaw: [Errno 11001] getaddrinfo failed. Check the internet connection, then try again.";
const UNKNOWN =
  "Mado's RAW reader doesn't know this kind of RAW file yet (a camera newer than it, say), or it isn't one. Mado left it exactly as it is.";

/** What every screen's engine answers: the made-up library, LibRaw there unless a screen says. */
const EVERYWHERE: Record<string, unknown> = {
  "/health": { status: "ok", version: "0.7.0", dataDir: "", schemaVersion: 9 },
  "/settings": SETTINGS,
  "/library": LIBRARY,
  "/folders": FOLDERS,
  "/scan": scanDone(),
  "/records": null,
  "/pc": PC,
  "/jobs": [],
  "/jobs/held": [],
  "/tools": DOWNLOADS,
  "/sizes": SIZES,
  "/looks": { mine: [], mado: [] },
  "POST /screens": [],
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

/** The made-up pictures the engine sends: each picture's scene, as the screen asks for it. */
function pictureFor(url: URL): Response | undefined {
  const copy = url.pathname.match(/^\/pictures\/(\d+)\/(thumbnail|view|preview)$/);
  if (copy) return scene(SCENES.get(Number(copy[1])) ?? "harbour", { "X-Made-In": "0.9" });
  const sample = url.pathname.match(/^\/batches\/samples\/\w+\/(\d)\/(before|after|full)$/);
  if (sample) {
    const drawn = SCENES.get(SEEN[Number(sample[1])] ?? 40) ?? "harbour";
    return scene(sample[2] === "before" ? drawn : `${drawn}/look=warm-film/strength=.6`);
  }
  return undefined;
}

/** See it first's three in the batch of RAWs: two RAWs and the JPEG. */
const SEEN = [40, 44, 48];
const SEEN_FIRST = {
  ...SAMPLES,
  id: "raws1",
  samples: SAMPLES.samples.map((each, index) => ({
    ...each,
    picture: SEEN[index] ?? 40,
    name: item(SEEN[index] ?? 40).name,
    bytes: item(SEEN[index] ?? 40).size,
  })),
};

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

/** A RAW in Camera opened as its page asks for it. No camera's name: a made-up one could be
 * someone's. */
function opened(each: PictureItem, more: Record<string, unknown> = {}) {
  return {
    [`/pictures/${each.id}`]: pictureDetails(each, {
      camera: null,
      folderId: 2,
      folder: CAMERA,
      ...more,
    }),
    [`/pictures/${each.id}/neighbours`]: { before: [], after: [] },
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

describe.runIf(SHOTS)("Camera RAW's screens", () => {
  beforeEach(() => drawScenes());
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("raw-library", async () => {
    engine({ "/pictures": page(ITEMS) });
    draw("/library", "/library?folder=2", <LibraryPage />);
    await screen.findAllByText("Harbour at dusk");
    await settle();
    await dump("raw-library");
  });

  it("raw-library-waiting", async () => {
    engine({ "/pictures": page(WAITING), "/tools": [rawReader("downloading", 1_611_429)] });
    draw("/library", "/library?folder=2", <LibraryPage />);
    await screen.findAllByText("Getting the RAW reader · 46%");
    await settle();
    await dump("raw-library-waiting");
  });

  it("raw-page-waiting", async () => {
    const waiting = WAITING.find((each) => each.id === 44) as PictureItem;
    engine({ ...opened(waiting), "/tools": [rawReader("downloading", 1_611_429)] });
    draw("/library/pictures/:id", "/library/pictures/44?folder=2", <PicturePage />);
    await screen.findByRole("progressbar", { name: "Downloading Mado's RAW reader" });
    await settle(800);
    await dump("raw-page-waiting");
  });

  it("raw-page-offline", async () => {
    const waiting = WAITING.find((each) => each.id === 44) as PictureItem;
    engine({ ...opened(waiting), "/tools": [rawReader("failed", 0, OFFLINE)] });
    draw("/library/pictures/:id", "/library/pictures/44?folder=2", <PicturePage />);
    await screen.findByRole("button", { name: "Try again" });
    await settle(800);
    await dump("raw-page-offline");
  });

  it("raw-page-unknown", async () => {
    engine(opened(item(49), { state: "broken", problem: UNKNOWN, width: null, height: null }));
    draw("/library/pictures/:id", "/library/pictures/49?folder=2", <PicturePage />);
    await screen.findByText(UNKNOWN);
    await settle(800);
    await dump("raw-page-unknown");
  });

  it("raw-page-huge", async () => {
    const huge = { ...item(47), width: 12288, height: 8192, size: 216_000_000 };
    engine({
      ...opened(huge),
      "/pictures/47/full": () => new Promise<never>(() => {}), // still being developed
    });
    draw("/library/pictures/:id", "/library/pictures/47?folder=2", <PicturePage />);
    fireEvent.click(await screen.findByRole("radio", { name: "100%" }));
    await screen.findByText(/Developing the RAW at full size/);
    await settle(800);
    await dump("raw-page-huge");
  });

  it("raw-save", async () => {
    await measuredBoxes("raw-save");
    const harbour = item(40);
    engine({
      ...opened(harbour),
      "POST /pictures/40/plan": plan({ colour: "Display P3" }),
      "POST /pictures/40/saving": {
        name: "Harbour at dusk (TV 8K).jpg",
        folder: CAMERA,
        taken: null,
        takenAt: null,
        bytes: 18_000_000,
        colour: "Display P3",
      },
    });
    draw("/library/pictures/:id", "/library/pictures/40?folder=2", <PicturePage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Size" }));
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));
    await settle(1000);
    fireEvent.click(screen.getByRole("button", { name: "Save…" }));
    await screen.findByText(/Replacing the original isn't offered/);
    await settle();
    await dump("raw-save");
  });

  it("raw-batch-waiting", async () => {
    const waiting =
      "It's a camera RAW, and Mado is getting its RAW reader: it joins once that's here.";
    engine({
      "/tools": [rawReader("downloading", 2_418_000)],
      "POST /batches/takes": takes(),
      "/recipes": [],
    });
    draw("/batch", "/batch", <BatchPage />, {
      pick: { how: "ticked", ids: [41, 43, 48, 40, 42] },
      picked: {
        pictures: [
          batchPicture(41, "Harbour at dusk.JPG"),
          batchPicture(43, "Little sail.JPG"),
          batchPicture(48, "Misty pines.JPG"),
        ],
        bytes: 18_600_000,
        source: "Camera",
        shared: CAMERA,
        words: "ticked in Camera",
        leftOut: [
          { name: "Harbour at dusk.CR3", why: waiting, waiting: true },
          { name: "Little sail.CR3", why: waiting, waiting: true },
        ],
      },
    });
    await screen.findByRole("progressbar", { name: "Downloading Mado's RAW reader" });
    await settle();
    await dump("raw-batch-waiting");
  });

  it("raw-batch", async () => {
    engine({
      "/recipes": [RECIPE],
      "POST /batches/takes": takes({
        into: "Camera › Edited",
        example: "Name (TV 8K, Warm film).jpg",
        seconds: 300,
        bytes: 46_000_000,
      }),
      "POST /batches/samples": SEEN_FIRST,
      "/batches/samples/raws1": SEEN_FIRST,
    });
    draw("/batch", "/batch", <BatchPage />, {
      recipe: 1,
      pick: { how: "ticked", ids: [40, 42, 44, 48] },
      picked: {
        pictures: [
          batchPicture(40, "Harbour at dusk.CR3"),
          batchPicture(42, "Little sail.CR3"),
          batchPicture(44, "Low tide.NEF"),
          batchPicture(48, "Misty pines.JPG"),
        ],
        bytes: 99_200_000,
        source: "Camera",
        shared: CAMERA,
        words: "ticked in Camera",
        leftOut: [],
      },
    });
    await screen.findByText(/Replacing the originals isn't offered/);
    await settle(3500);
    await dump("raw-batch");
  });

  it("raw-home", async () => {
    engine({
      "/library": { ...LIBRARY, rawWaiting: 318 },
      "/tools": [rawReader("downloading", 1_611_429)],
      "/history/today": [],
      "/batches/done": [],
      "/space": [],
      "/duplicates": null,
      "/library/wont-open": { pictures: [], damaged: 0 },
    });
    draw("/", "/", <HomePage />);
    await screen.findByText("Waiting for the RAW reader");
    await settle();
    await dump("raw-home");
  });

  it("raw-about", async () => {
    engine({
      "/tools": DOWNLOADS.map((each) => (each.id === "libraw" ? rawReader("missing") : each)),
    });
    draw("/settings/:section", "/settings/about", <SettingsPage />);
    await screen.findByText(/fetched the first time Mado reads a camera RAW/);
    await settle();
    // The downloads sit below About and This PC: shown as the page scrolled to them.
    for (const above of ["About Mado", "This PC"])
      screen.getByRole("heading", { name: above }).closest("section")?.remove();
    await dump("raw-about");
  });
});
