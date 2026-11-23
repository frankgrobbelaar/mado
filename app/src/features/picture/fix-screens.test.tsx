/**
 * The Fix tab's screens, as Mado draws them, written out to be shot in dark and light:
 *
 *   node scripts/readme-pictures.mjs --screens app/src/features/picture/fix-screens.test.tsx --out <folder>
 *
 * A dark photo brightened, before and after; noise at 100%; JPEG blocks Mado suggests; a model to
 * download first; the card busy with the queue, or too full for the fixes; nothing to fix, or a
 * dark photo's fix on a picture that isn't dark; a camera RAW; a grey, see-through
 * and huge picture; a screenshot's blocks round letters; the Size tab once the fixes cleaned; the
 * Fix step for many at once; Save and History naming the fixes. Skipped unless MADO_SHOTS names a
 * folder. Every picture is a scene the shoot draws by code, every name made up.
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
  EngineProvider,
  type Fixes,
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

/** Each picture, the scene it's drawn as, and what's wrong with it ("dark=2.5/grain=40"). */
const PICTURES: [PictureItem, string, string][] = [
  [picture(11, "Harbour at dusk.jpg", "2026-11-14T18:42:07"), "harbour", "dark=2.6/grain=45"],
  [picture(12, "Little sail.jpg", "2026-11-14T16:05:00"), "little-sail", "grain=130"],
  [picture(13, "Still lake.jpg", "2026-11-14T07:58:00"), "still-lake", "blocks=6"],
  [
    picture(14, "Low tide.NEF", "2026-11-14T14:20:00", {
      format: "NEF",
      raw: true,
      width: 6000,
      height: 4000,
    }),
    "low-tide",
    "grain=90",
  ],
  [
    picture(15, "Old pier.png", "2026-11-13T09:12:00", {
      format: "PNG",
      width: 12000,
      height: 8000,
      size: 168_000_000,
    }),
    "misty-pines",
    "grain=90",
  ],
  [
    picture(16, "Screenshot 2026-11-12 091402.jpg", "2026-11-12T09:14:02", {
      width: 1920,
      height: 1080,
    }),
    "snowfield",
    "blocks=5",
  ],
];
const SCENES = new Map(PICTURES.map(([item, drawn, wrong]) => [item.id, [drawn, wrong]] as const));
const item = (id: number) => PICTURES.find(([each]) => each.id === id)?.[0] as PictureItem;

const NOTHING: Fixes = {
  jpegQuality: 92,
  blocks: false,
  stops: 0,
  dark: false,
  grey: false,
  seeThrough: false,
  colour: "sRGB",
  megapixels: 12.2,
};

function model(id: string, name: string, size: number, state: Tool["state"] = "ready"): Tool {
  return {
    id,
    name,
    version: id === "nafnet" ? "models-3" : "models-1",
    purpose: "",
    licence: "Apache-2.0 AND MIT",
    size,
    when: "asked",
    state,
    done: state === "downloading" ? Math.round(size * 0.42) : 0,
    problem: null,
  };
}

const MODELS = [
  model("scunet", "SCUNet", 72_932_271),
  model("fbcnn", "FBCNN", 287_709_421),
  model("nafnet", "NAFNet", 68_940_956),
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

/** What every screen's engine answers: the made-up library, the fixes' models downloaded. */
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
  "/tools": MODELS,
  "/sizes": SIZES,
  "/looks": { looks: [], yours: [] },
  "POST /screens": [],
  "/queue/now": QUIET,
};

/** A preview as the engine makes it: before, the picture as it is; after, fixed. A part comes
 * stretched to its place, as at 100%. */
function previewOf(id: number, init: RequestInit | undefined): Response {
  const [drawn = "harbour", wrong = ""] = SCENES.get(id) ?? [];
  const asked = JSON.parse(String(init?.body)) as {
    recipe: Recipe;
    side: string;
    region?: Region;
  };
  const shown = item(id);
  const part = asked.region
    ? `/region=${[
        asked.region.x / (shown.width ?? 1),
        asked.region.y / (shown.height ?? 1),
        asked.region.width / (shown.width ?? 1),
        asked.region.height / (shown.height ?? 1),
      ]
        .map((each) => each.toFixed(4))
        .join(",")}`
    : "";
  const fix = asked.side === "after" ? asked.recipe.fix : null;
  // What the fixes asked for take out: all of it fitted is sent only the brightening.
  const out: Record<string, boolean> = {
    dark: Boolean(fix?.dark),
    grain: Boolean(fix?.noise),
    blocks: Boolean(fix?.jpeg),
    blur: Boolean(fix?.blur),
  };
  const left = wrong
    .split("/")
    .filter((word) => word && !out[word.split("=")[0] ?? ""])
    .join("/");
  return scene(left ? `${drawn}/${left}${part}` : `${drawn}${part}`, { "X-Made-In": "1.4" });
}

function pictureFor(url: URL, init: RequestInit | undefined): Response | undefined {
  const copy = url.pathname.match(/^\/pictures\/(\d+)\/(thumbnail|view|full)$/);
  if (copy) {
    const [drawn = "harbour", wrong = ""] = SCENES.get(Number(copy[1])) ?? [];
    return scene(`${drawn}/${wrong}`);
  }
  const preview = url.pathname.match(/^\/pictures\/(\d+)\/preview$/);
  if (preview) return previewOf(Number(preview[1]), init);
  if (url.pathname.match(/^\/history\/\d+\/thumbnail$/)) return scene("harbour");
  return undefined;
}

function engine(answers: Record<string, unknown>) {
  const fetch = fakeEngine({ ...EVERYWHERE, ...answers });
  const answer = fetch.getMockImplementation();
  fetch.mockImplementation(async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    // A screen's own answer comes first: a preview that waits for the card, say.
    if (answer && `${init?.method ?? "GET"} ${url.pathname}` in answers) return answer(input, init);
    return (
      pictureFor(url, init) ??
      (answer ? answer(input, init) : Response.json({ detail: "Not found" }, { status: 404 }))
    );
  });
}

/** A picture in Phone opened, with what Mado measured of it and the plan for its fixes. */
function opened(id: number, fixes: Partial<Fixes> = {}, more: Record<string, unknown> = {}) {
  const shown = item(id);
  return {
    [`/pictures/${id}`]: pictureDetails(shown, { camera: null }),
    [`/pictures/${id}/neighbours`]: { before: [], after: [] },
    [`/pictures/${id}/fixes`]: {
      ...NOTHING,
      megapixels: ((shown.width ?? 0) * (shown.height ?? 0)) / 1e6,
      ...fixes,
    },
    [`POST /pictures/${id}/plan`]: plan({
      width: shown.width ?? 4032,
      height: shown.height ?? 3024,
      label: "",
      method: "keep",
      model: null,
      fix: "brightened it",
      fixSeconds: 24,
      seconds: 25,
    }),
    ...more,
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

/** The picture's page on the Fix tab, with these fixes turned on. */
async function fixTab(id: number, on: string[]) {
  draw("/library/pictures/:id", `/library/pictures/${id}?folder=1`, <PicturePage />);
  fireEvent.click(await screen.findByRole("tab", { name: "Fix" }));
  // What Mado measured first, as the owner sees it before turning a fix on.
  await screen.findByText(/Mado suggests|Nothing Mado can measure/);
  for (const name of on) fireEvent.click(await screen.findByRole("switch", { name }));
}

describe.runIf(SHOTS)("The Fix tab's screens", () => {
  beforeEach(() => drawScenes());
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("fix-dark", async () => {
    engine(opened(11, { jpegQuality: 94, stops: 2.6, dark: true }));
    await measuredBoxes("fix-dark");
    await fixTab(11, ["Dark photo"]);
    await screen.findByText(/Mado brightens it by about 2\.6 stops/);
    await settle(2500);
    await dump("fix-dark");
  });

  it("fix-noise", async () => {
    engine(
      opened(
        12,
        { jpegQuality: 95 },
        {
          "POST /pictures/12/plan": plan({
            width: 4032,
            height: 3024,
            label: "",
            method: "keep",
            model: null,
            fix: "took out noise",
            fixSeconds: 31,
          }),
        },
      ),
    );
    await measuredBoxes("fix-noise");
    await fixTab(12, ["Noise"]);
    fireEvent.click(screen.getByRole("radio", { name: "100%" }));
    await settle(2500);
    await dump("fix-noise");
  });

  it("fix-jpeg", async () => {
    engine(
      opened(
        13,
        { jpegQuality: 18, blocks: true },
        {
          "POST /pictures/13/plan": plan({
            width: 4032,
            height: 3024,
            label: "",
            method: "keep",
            model: null,
            fix: "took out JPEG blocks",
            fixQuality: "best",
            fixSeconds: 19,
          }),
        },
      ),
    );
    await measuredBoxes("fix-jpeg");
    await fixTab(13, ["JPEG blocks"]);
    fireEvent.click(screen.getByRole("radio", { name: "100%" }));
    await settle(2500);
    await dump("fix-jpeg");
  });

  it("fix-download", async () => {
    engine({
      ...opened(12, { jpegQuality: 95 }),
      "/tools": [model("scunet", "SCUNet", 72_932_271, "downloading"), ...MODELS.slice(1)],
    });
    await measuredBoxes("fix-download");
    await fixTab(12, ["Noise"]);
    await screen.findByRole("progressbar", { name: "Downloading SCUNet" });
    await settle(1500);
    await dump("fix-download");
  });

  it("fix-busy", async () => {
    engine({
      ...opened(11, { stops: 2.6, dark: true }),
      "/queue/now": {
        working: true,
        paused: false,
        batch: "Phone wallpapers",
        over: 12,
        total: 30,
        progress: 0.4,
        waiting: 18,
      },
      "POST /pictures/11/preview": () => new Promise<never>(() => {}), // waits for the card
    });
    await measuredBoxes("fix-busy");
    await fixTab(11, ["Dark photo"]);
    await screen.findByText(/Waiting for the graphics card/, {}, { timeout: 4000 });
    await settle(500);
    await dump("fix-busy");
  });

  it("fix-nothing", async () => {
    engine(opened(12, { jpegQuality: 95 }));
    await measuredBoxes("fix-nothing");
    await fixTab(12, []);
    await screen.findByText(/Nothing Mado can measure needs fixing/);
    await settle(1500);
    await dump("fix-nothing");
  });

  it("fix-raw", async () => {
    engine(opened(14, { jpegQuality: null, colour: "Display P3" }));
    await measuredBoxes("fix-raw");
    await fixTab(14, ["Noise"]);
    await screen.findByText(/Its Display P3 colours are kept/);
    await settle(2000);
    await dump("fix-raw");
  });

  it("fix-big", async () => {
    engine(
      opened(
        15,
        { jpegQuality: null, grey: true, seeThrough: true },
        {
          "POST /pictures/15/plan": plan({
            width: 12000,
            height: 8000,
            label: "",
            method: "keep",
            model: null,
            fix: "took out noise",
            fixSeconds: 240,
          }),
        },
      ),
    );
    await measuredBoxes("fix-big");
    await fixTab(15, ["Noise"]);
    await screen.findByText(/A big picture: 96 megapixels/);
    await settle(2000);
    await dump("fix-big");
  });

  it("fix-crowded", async () => {
    engine(
      opened(
        12,
        { jpegQuality: 95 },
        {
          "POST /pictures/12/plan": plan({
            width: 4032,
            height: 3024,
            label: "",
            method: "keep",
            model: null,
            fix: "took out noise",
            fixSeconds: 520,
            place: "card",
            fixPlace: "processor",
          }),
        },
      ),
    );
    await measuredBoxes("fix-crowded");
    await fixTab(12, ["Noise"]);
    await screen.findByText(/Your graphics card is full of the models Mado has used/);
    await settle(2000);
    await dump("fix-crowded");
  });

  it("fix-not-dark", async () => {
    engine(
      opened(
        12,
        { jpegQuality: 95 },
        {
          "POST /pictures/12/plan": plan({
            width: 4032,
            height: 3024,
            label: "",
            method: "keep",
            model: null,
            fix: null,
          }),
        },
      ),
    );
    await measuredBoxes("fix-not-dark");
    await fixTab(12, ["Dark photo"]);
    await screen.findByText(/Nothing to save: it isn't dark/);
    await settle(2000);
    await dump("fix-not-dark");
  });

  it("fix-screenshot", async () => {
    engine(
      opened(
        16,
        { jpegQuality: 25, blocks: true },
        {
          "POST /pictures/16/plan": plan({
            width: 1920,
            height: 1080,
            label: "",
            kind: "screenshot",
            method: "keep",
            model: null,
            fix: "took out JPEG blocks",
            fixQuality: "best",
            fixSeconds: 3,
          }),
        },
      ),
    );
    await measuredBoxes("fix-screenshot");
    await fixTab(16, ["JPEG blocks"]);
    fireEvent.click(screen.getByRole("radio", { name: "100%" }));
    await settle(2500);
    await dump("fix-screenshot");
  });

  it("size-cleaned", async () => {
    engine({
      ...opened(11, { stops: 2.6, dark: true }),
      "POST /pictures/11/plan": plan({
        cleanedFirst: true,
        cleanMatters: false,
        fix: "brightened it",
        fixSeconds: 24,
        model: "Real-ESRGAN general, keeping grain",
      }),
    });
    await measuredBoxes("size-cleaned");
    await fixTab(11, ["Dark photo"]);
    fireEvent.click(screen.getByRole("tab", { name: "Size" }));
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));
    await screen.findByText(/The Fix tab takes noise and blocks out first/);
    await settle(2000);
    await dump("size-cleaned");
  });

  it("save-fixed", async () => {
    engine({
      ...opened(11, { stops: 2.6, dark: true }),
      "POST /pictures/11/saving": {
        name: "Harbour at dusk (Brightened).jpg",
        folder: "D:\\Pictures\\Phone",
        taken: null,
        takenAt: null,
        bytes: 4_100_000,
        colour: "sRGB",
      },
    });
    await measuredBoxes("save-fixed");
    await fixTab(11, ["Dark photo"]);
    await settle(1000);
    fireEvent.click(screen.getByRole("button", { name: "Save…" }));
    await screen.findByText("Harbour at dusk (Brightened).jpg");
    await settle(1000);
    await dump("save-fixed");
  });

  it("batch-fix", async () => {
    await measuredBoxes("batch-fix");
    engine({
      "/recipes": [],
      "POST /batches/takes": takes({
        words: [
          {
            kind: "fix",
            title: "Fix",
            detail: "Noise at 100%, brightened",
            chip: "Noise and dark photo",
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
          batchPicture(11, "Harbour at dusk.jpg"),
          batchPicture(12, "Little sail.jpg"),
          batchPicture(13, "Still lake.jpg"),
        ],
      },
    });
    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Fix: noise, blur, JPEG blocks, dark" })).click();
    fireEvent.click(await screen.findByRole("switch", { name: "Dark photo" }));
    await settle(1500);
    await dump("batch-fix");
  });

  it("history-fixed", async () => {
    engine({
      "/history": {
        entries: [
          entry({
            id: 3,
            madeFor: null,
            fix: "took out noise and brightened it",
            name: "Harbour at dusk.jpg",
            result: "D:\\Pictures\\Phone\\Harbour at dusk (Fixed).jpg",
            resultName: "Harbour at dusk (Fixed).jpg",
          }),
          entry({
            id: 2,
            madeFor: "TV 8K",
            fix: "took out JPEG blocks",
            name: "Still lake.jpg",
            result: "D:\\Pictures\\Phone\\Still lake (Cleaned, TV 8K).jpg",
            resultName: "Still lake (Cleaned, TV 8K).jpg",
          }),
        ],
        older: null,
        batches: [],
        reviews: [],
      },
    });
    draw("/history", "/history", <HistoryPage />);
    await screen.findByText(/took out noise and brightened it/);
    await settle(1500);
    await dump("history-fixed");
  });
});
