/**
 * The Depth tab's screens, as Mado draws them, written out to be shot in dark and light:
 *
 *   node scripts/readme-pictures.mjs --screens app/src/features/picture/depth-screens.test.tsx --out <folder>
 *
 * Portrait blur in focus at its subject; fog; tilt-shift's band; the depth model to download
 * first; the card busy with the queue; a flat picture and a huge one; a 3D photo's choices, being
 * made, made and playing, as an animated WebP where the PC has no H.264 encoder, with ffmpeg to
 * download first, and for an HDR photo (an ordinary video); the Depth step for many at once;
 * History naming them. Skipped unless MADO_SHOTS
 * names a folder. Every picture is a scene the shoot draws by code, every name made up.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, it, vi } from "vitest";
import { AppShell } from "@/components/shell/app-shell";
import { BatchPage } from "@/features/batch/batch-page";
import { HistoryPage } from "@/features/history/history-page";
import {
  type DepthRead,
  EngineProvider,
  type Motion,
  type MotionFacts,
  type PictureItem,
  type Recipe,
  type Region,
  type Tool,
} from "@/lib/engine";
import {
  batchPicture,
  entry,
  FOLDERS,
  fakeEngine,
  LIBRARY,
  PC,
  PICKED,
  picture,
  pictureDetails,
  plan,
  READY,
  SETTINGS,
  SIZES,
  scanDone,
  takes,
} from "@/test/engine";
import { drawScenes, dump, measuredBoxes, SHOTS, scene } from "@/test/shots";
import { PicturePage } from "./picture-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({ minimize() {}, toggleMaximize() {}, close() {} }),
}));

/** Each picture, the scene it's drawn as, and the part of it that's its subject. */
const PICTURES: [PictureItem, string, string | null][] = [
  [picture(11, "Little sail.jpg", "2026-11-14T16:05:00"), "little-sail", "boat"],
  [picture(12, "Canyon road.jpg", "2026-11-14T10:20:00"), "red-canyon", null],
  [picture(13, "Night market.jpg", "2026-11-13T21:40:00"), "night-market", null],
  [
    picture(14, "Screenshot 2026-11-12 091402.png", "2026-11-12T09:14:02", {
      format: "PNG",
      width: 1920,
      height: 1080,
    }),
    "snowfield",
    null,
  ],
  [
    picture(15, "Old pier.png", "2026-11-13T09:12:00", {
      format: "PNG",
      width: 12000,
      height: 8000,
      size: 168_000_000,
    }),
    "misty-pines",
    null,
  ],
];
const SCENES = new Map(
  PICTURES.map(([item, drawn, subject]) => [item.id, [drawn, subject]] as const),
);
const item = (id: number) => PICTURES.find(([each]) => each.id === id)?.[0] as PictureItem;

function model(id: string, name: string, size: number, state: Tool["state"] = "ready"): Tool {
  return {
    id,
    name,
    version: id === "ffmpeg" ? "8.0" : "models-2",
    purpose: "",
    licence: id === "ffmpeg" ? "LGPL-2.1-or-later" : "Apache-2.0",
    size,
    when: "asked",
    state,
    done: state === "downloading" ? Math.round(size * 0.42) : 0,
    problem: null,
  };
}

const MODELS = [
  model("depth-anything-v2-small", "Depth Anything V2 Small", 99_072_196),
  model("lama", "LaMa", 209_176_178),
  model("ffmpeg", "ffmpeg", 76_972_461),
];

const QUIET = {
  working: false,
  paused: false,
  batch: null,
  over: 0,
  total: 0,
  progress: 0,
  waiting: 0,
};

/** What every screen's engine answers: the made-up library, the models downloaded. */
const EVERYWHERE: Record<string, unknown> = {
  "/health": { status: "ok", version: "0.12.0", dataDir: "", schemaVersion: 13 },
  "/settings": SETTINGS,
  "/library": LIBRARY,
  "/folders": FOLDERS,
  "/scan": scanDone(),
  "/records": null,
  "/pc": PC,
  "/jobs": [],
  "/jobs/held": [],
  "/tools": MODELS,
  "/sizes": SIZES,
  "/looks": { looks: [], yours: [] },
  "POST /screens": [],
  "/queue/now": QUIET,
};

/** Read on the card in a fifth of a second, its subject found. */
function read(id: number, more: Partial<DepthRead> = {}): DepthRead {
  const [, subject] = SCENES.get(id) ?? [];
  const shown = item(id);
  return {
    needs: [],
    read: true,
    flat: false,
    place: "card",
    seconds: 0.2,
    waited: 0,
    subject: subject !== null,
    focus: subject ? [0.65, 0.5] : null,
    seeThrough: false,
    grey: false,
    megapixels: ((shown.width ?? 0) * (shown.height ?? 0)) / 1e6,
    tooBig: false,
    ...more,
  };
}

/** A preview as the engine makes it: before, the picture as it is; after, as its depth tools
 * leave it. A part comes stretched to its place, as at 100%. */
function previewOf(id: number, init: RequestInit | undefined): Response {
  const [drawn = "harbour", subject = null] = SCENES.get(id) ?? [];
  const asked = JSON.parse(String(init?.body)) as {
    recipe: Recipe;
    side: string;
    region?: Region;
  };
  const shown = item(id);
  const asks: string[] = [];
  const depth = asked.side === "after" ? asked.recipe.depth : null;
  if (depth?.portrait) {
    asks.push(`bokeh=${(8.4 / depth.portrait.aperture).toFixed(1)}`);
    if (subject) asks.push(`focus=${subject}`);
  }
  if (depth?.tilt) {
    const { centre, height } = depth.tilt;
    asks.push(`tilt=${(centre - height / 2).toFixed(3)},${(centre + height / 2).toFixed(3)}`);
  }
  if (depth?.fog) asks.push(`fog=${Math.round(depth.fog.density * 100)}`);
  if (asked.region) {
    const part = [
      asked.region.x / (shown.width ?? 1),
      asked.region.y / (shown.height ?? 1),
      asked.region.width / (shown.width ?? 1),
      asked.region.height / (shown.height ?? 1),
    ];
    asks.push(`region=${part.map((each) => each.toFixed(4)).join(",")}`);
  }
  return scene([drawn, ...asks].join("/"), { "X-Made-In": "0.9" });
}

function pictureFor(url: URL, init: RequestInit | undefined): Response | undefined {
  const copy = url.pathname.match(/^\/pictures\/(\d+)\/(thumbnail|view|full)$/);
  if (copy) return scene(SCENES.get(Number(copy[1]))?.[0] ?? "harbour");
  const preview = url.pathname.match(/^\/pictures\/(\d+)\/preview$/);
  if (preview) return previewOf(Number(preview[1]), init);
  if (url.pathname.match(/^\/history\/\d+\/thumbnail$/)) return scene("little-sail");
  // The video plays in Mado; in a picture of the page, its poster (the picture) stands in.
  if (url.pathname.match(/^\/motion\/\w+\/video$/)) return scene("little-sail");
  return undefined;
}

function engine(answers: Record<string, unknown>) {
  const fetch = fakeEngine({ ...EVERYWHERE, ...answers });
  const answer = fetch.getMockImplementation();
  fetch.mockImplementation(async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (answer && `${init?.method ?? "GET"} ${url.pathname}` in answers) return answer(input, init);
    return (
      pictureFor(url, init) ??
      (answer ? answer(input, init) : Response.json({ detail: "Not found" }, { status: 404 }))
    );
  });
}

/** What a 3D photo of a 4032 × 3024 picture can be here: 1080p or 4K, Windows' own encoder. */
const FACTS: MotionFacts = {
  ffmpeg: true,
  encoder: "h264_mf",
  encoderName: "Windows' own video encoder",
  sizes: [
    { size: "1080p", width: 1920, height: 1440, bytes: 10_000_000 },
    { size: "4k", width: 3840, height: 2880, bytes: 25_000_000 },
  ],
  webp: { size: "1080p", width: 1280, height: 960, bytes: 29_491_200 },
  seconds: [3, 5, 8],
  needs: [],
};

const MADE: Motion = {
  id: "ab12",
  state: "done",
  progress: 1,
  seconds: 52,
  width: 1920,
  height: 1440,
  bytes: 9_400_000,
  format: "mp4",
  encoderName: "Windows' own video encoder",
  problem: null,
};

/** A picture in Phone opened, with its depth read and the plan for its depth tools. */
function opened(id: number, more: Partial<DepthRead> = {}, answers: Record<string, unknown> = {}) {
  const shown = item(id);
  return {
    [`/pictures/${id}`]: pictureDetails(shown, { camera: null }),
    [`/pictures/${id}/neighbours`]: { before: [], after: [] },
    [`POST /pictures/${id}/depth`]: read(id, more),
    [`/pictures/${id}/motion`]: FACTS,
    [`POST /pictures/${id}/plan`]: plan({
      width: shown.width ?? 4032,
      height: shown.height ?? 3024,
      label: "",
      method: "keep",
      model: null,
      depth: "portrait blur at f/2.8",
      depthSeconds: 4,
      depthPlace: "card",
      seconds: 4,
    }),
    ...answers,
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

/** The picture's page on the Depth tab, with these tools turned on. */
async function depthTab(id: number, on: string[]) {
  draw("/library/pictures/:id", `/library/pictures/${id}?folder=1`, <PicturePage />);
  fireEvent.click(await screen.findByRole("tab", { name: "Depth" }));
  await screen.findByRole("region", { name: "Depth tools" });
  for (const name of on) fireEvent.click(await screen.findByRole("switch", { name }));
}

/** The picture's page on the Depth tab, as "3D photo". */
async function motionTab(id: number) {
  draw("/library/pictures/:id", `/library/pictures/${id}?folder=1`, <PicturePage />);
  fireEvent.click(await screen.findByRole("tab", { name: "Depth" }));
  fireEvent.click(await screen.findByRole("radio", { name: "3D photo" }));
  return screen.findByRole("region", { name: "3D photo" });
}

describe.runIf(SHOTS)("The Depth tab's screens", () => {
  beforeEach(() => drawScenes());
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("depth-portrait", async () => {
    engine(opened(11));
    await measuredBoxes("depth-portrait");
    await depthTab(11, ["Portrait blur"]);
    await screen.findByText(/In focus at its subject, found as Cut out finds it/);
    await settle(2500);
    await dump("depth-portrait");
  });

  it("depth-fog", async () => {
    engine(
      opened(
        12,
        {},
        {
          "POST /pictures/12/plan": plan({
            width: 4032,
            height: 3024,
            label: "",
            method: "keep",
            model: null,
            depth: "fog",
            depthSeconds: 2,
            depthPlace: "card",
            seconds: 2,
          }),
        },
      ),
    );
    await measuredBoxes("depth-fog");
    await depthTab(12, ["Fog"]);
    await settle(2500);
    await dump("depth-fog");
  });

  it("depth-tilt", async () => {
    engine(
      opened(
        13,
        {},
        {
          "POST /pictures/13/plan": plan({
            width: 4032,
            height: 3024,
            label: "",
            method: "keep",
            model: null,
            depth: "tilt-shift",
            depthSeconds: 4,
            depthPlace: "card",
            seconds: 4,
          }),
        },
      ),
    );
    await measuredBoxes("depth-tilt");
    await depthTab(13, ["Tilt-shift"]);
    await settle(2500);
    await dump("depth-tilt");
  });

  it("depth-compared", async () => {
    engine(opened(11));
    await measuredBoxes("depth-compared");
    await depthTab(11, ["Portrait blur"]);
    fireEvent.click(screen.getByRole("radio", { name: "100%" }));
    await settle(2500);
    await dump("depth-compared");
  });

  it("depth-download", async () => {
    engine({
      ...opened(12, {
        read: false,
        needs: [
          { id: "depth-anything-v2-small", name: "Depth Anything V2 Small", size: 99_072_196 },
        ],
        seconds: null,
        subject: false,
        focus: null,
      }),
      "/tools": [
        model("depth-anything-v2-small", "Depth Anything V2 Small", 99_072_196, "downloading"),
        ...MODELS.slice(1),
      ],
    });
    await measuredBoxes("depth-download");
    await depthTab(12, ["Fog"]);
    await screen.findByRole("region", { name: "Depth Anything V2 Small to download" });
    await settle(1500);
    await dump("depth-download");
  });

  it("depth-busy", async () => {
    engine({
      ...opened(11),
      "/queue/now": {
        working: true,
        paused: false,
        batch: "Holiday prints",
        over: 18,
        total: 48,
        progress: 0.4,
        waiting: 30,
      },
      "POST /pictures/11/preview": () => new Promise<never>(() => {}), // waits for the card
    });
    await measuredBoxes("depth-busy");
    await depthTab(11, ["Portrait blur"]);
    await screen.findByText(/Waiting for the graphics card/, {}, { timeout: 4000 });
    await settle(500);
    await dump("depth-busy");
  });

  it("depth-flat", async () => {
    engine(
      opened(
        14,
        { flat: true, subject: false, focus: null, seeThrough: true },
        {
          "POST /pictures/14/plan": plan({
            width: 1920,
            height: 1080,
            label: "",
            kind: "screenshot",
            method: "keep",
            model: null,
            depth: "tilt-shift",
            depthSeconds: 1,
            depthPlace: "card",
            seconds: 1,
          }),
        },
      ),
    );
    await measuredBoxes("depth-flat");
    await depthTab(14, ["Tilt-shift"]);
    await screen.findByText(/Mado finds little depth in it: it reads as flat/);
    await settle(2000);
    await dump("depth-flat");
  });

  it("depth-big", async () => {
    engine(
      opened(
        15,
        {},
        {
          "POST /pictures/15/plan": plan({
            width: 12000,
            height: 8000,
            label: "",
            method: "keep",
            model: null,
            depth: "portrait blur at f/2.8",
            depthSeconds: 31,
            depthPlace: "card",
            seconds: 31,
          }),
        },
      ),
    );
    await measuredBoxes("depth-big");
    await depthTab(15, ["Portrait blur"]);
    await screen.findByText(/A big picture: 96 megapixels/);
    await settle(2000);
    await dump("depth-big");
  });

  it("motion-choices", async () => {
    engine(opened(11));
    await measuredBoxes("motion-choices");
    await motionTab(11);
    await screen.findByText(/1920 × 1440 · 5 s · about/);
    await settle(1500);
    await dump("motion-choices");
  });

  it("motion-hdr", async () => {
    engine(
      opened(
        11,
        {},
        {
          "/pictures/11": pictureDetails(item(11), {
            camera: null,
            hdr: true,
            gainMap: {
              readable: true,
              stops: 3,
              baseIsHdr: false,
              colour: false,
              width: 1008,
              height: 756,
              why: null,
            },
          }),
        },
      ),
    );
    await measuredBoxes("motion-hdr");
    await motionTab(11);
    await screen.findByText(/A 3D photo is an ordinary video, in sRGB/);
    await settle(1500);
    await dump("motion-hdr");
  });

  it("motion-making", async () => {
    engine({
      ...opened(11),
      "POST /pictures/11/motion": { ...MADE, state: "making", progress: 0, seconds: null },
      "/motion/ab12": { ...MADE, state: "making", progress: 0.42, seconds: null },
    });
    await measuredBoxes("motion-making");
    await motionTab(11);
    fireEvent.click(await screen.findByRole("button", { name: "Make the 3D photo" }));
    await screen.findByRole("progressbar", { name: "Making the 3D photo" });
    await settle(1500);
    await dump("motion-making");
  });

  it("motion-made", async () => {
    engine({
      ...opened(11),
      "POST /pictures/11/motion": { ...MADE, state: "waiting", progress: 0, seconds: null },
      "/motion/ab12": MADE,
    });
    await measuredBoxes("motion-made");
    await motionTab(11);
    fireEvent.click(screen.getByRole("radio", { name: "Sway" }));
    fireEvent.click(await screen.findByRole("button", { name: "Make the 3D photo" }));
    await screen.findByRole("button", { name: "Save beside the picture" });
    await settle(2000);
    await dump("motion-made");
  });

  it("motion-webp", async () => {
    engine(
      opened(11, {}, { "/pictures/11/motion": { ...FACTS, encoder: null, encoderName: null } }),
    );
    await measuredBoxes("motion-webp");
    await motionTab(11);
    await screen.findByText(/This PC has no H.264 encoder Mado may use/);
    await settle(1500);
    await dump("motion-webp");
  });

  it("motion-ffmpeg", async () => {
    engine({
      ...opened(11, {}, { "/pictures/11/motion": { ...FACTS, ffmpeg: false, encoder: null } }),
      "/tools": [...MODELS.slice(0, 2), model("ffmpeg", "ffmpeg", 76_972_461, "missing")],
    });
    await measuredBoxes("motion-ffmpeg");
    await motionTab(11);
    await screen.findByRole("region", { name: "ffmpeg to download" });
    await settle(1500);
    await dump("motion-ffmpeg");
  });

  it("batch-depth", async () => {
    await measuredBoxes("batch-depth");
    engine({
      "/recipes": [],
      "POST /batches/takes": takes({
        words: [
          {
            kind: "depth",
            title: "Depth",
            detail: "Portrait blur at f/2.8, each in focus at its subject",
            chip: "Portrait blur",
            amount: null,
          },
          {
            kind: "save",
            title: "Save",
            detail: "As new pictures, JPEG 92, beside the originals",
            chip: "JPEG 92 beside the originals",
            amount: null,
          },
        ],
      }),
    });
    draw("/batch", "/batch", <BatchPage />, {
      pick: { how: "ticked", ids: [11, 12, 13] },
      picked: {
        ...PICKED,
        pictures: [
          batchPicture(11, "Little sail.jpg"),
          batchPicture(12, "Canyon road.jpg"),
          batchPicture(13, "Night market.jpg"),
        ],
      },
    });
    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (
      await screen.findByRole("menuitem", { name: "Depth: portrait blur, fog, tilt-shift" })
    ).click();
    await settle(1500);
    await dump("batch-depth");
  });

  it("history-depth", async () => {
    engine({
      "/history": {
        entries: [
          entry({
            id: 3,
            madeFor: null,
            depth: "into a 3D photo, swaying for 5 s",
            name: "Little sail.jpg",
            original: "D:\\Pictures\\Phone\\Little sail.jpg",
            result: "D:\\Pictures\\Phone\\Little sail (3D photo).mp4",
            resultName: "Little sail (3D photo).mp4",
          }),
          entry({
            id: 2,
            madeFor: null,
            depth: "portrait blur at f/2.8 and fog",
            name: "Little sail.jpg",
            original: "D:\\Pictures\\Phone\\Little sail.jpg",
            result: "D:\\Pictures\\Phone\\Little sail (Depth).jpg",
            resultName: "Little sail (Depth).jpg",
          }),
        ],
        older: null,
        batches: [],
        reviews: [],
      },
    });
    draw("/history", "/history", <HistoryPage />);
    await screen.findByText(/into a 3D photo, swaying for 5 s/);
    await settle(1500);
    await dump("history-depth");
  });
});
