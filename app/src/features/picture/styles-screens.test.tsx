/**
 * The painting styles' screens, as Mado draws them, written out to be shot in dark and light:
 *
 *   node scripts/readme-pictures.mjs --screens app/src/features/picture/styles-screens.test.tsx --out <folder>
 *
 * The styles on the Looks tab with one picked; a look, a style and touches at once; a style on a
 * part; a classic one's setting; a network to download first; the card busy with the queue; a huge
 * picture; a grey picture; see-through parts; a picture as the style, too plain to give one, its
 * reader to download, chosen and kept; one of the owner's styles; the step for many at once; and
 * History naming a style. Skipped unless MADO_SHOTS names a folder. Every picture is a scene the
 * shoot draws by code, never a painting, and every name is made up.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, it, vi } from "vitest";
import { AppShell } from "@/components/shell/app-shell";
import { BatchPage } from "@/features/batch/batch-page";
import { HistoryPage } from "@/features/history/history-page";
import {
  EngineProvider,
  type Fixes,
  type LookStep,
  type PaintStep,
  type PictureItem,
  type Recipe,
} from "@/lib/engine";
import {
  batchPicture,
  entry,
  FOLDERS,
  fakeEngine,
  LIBRARY,
  LOOKS,
  PC,
  PICKED,
  picture,
  pictureDetails,
  plan,
  READY,
  SETTINGS,
  SIZES,
  STYLES,
  scanDone,
  styleTool,
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

/** Each picture and the scene it's drawn as. */
const PICTURES: [PictureItem, string][] = [
  [picture(11, "Harbour at dusk.jpg", "2026-11-14T18:42:07"), "harbour"],
  [picture(12, "Little sail.jpg", "2026-11-14T16:05:00"), "little-sail"],
  [
    picture(13, "Garden rose.png", "2026-11-13T15:47:00", { format: "PNG" }),
    "garden-rose/cutout=flower",
  ],
  [
    picture(14, "Old pier.png", "2026-11-13T09:12:00", {
      format: "PNG",
      width: 12000,
      height: 8000,
      size: 168_000_000,
    }),
    "misty-pines",
  ],
  [picture(15, "Still lake.jpg", "2026-11-14T07:58:00"), "still-lake/look=silver"],
];
const SCENES = new Map(PICTURES.map(([item, drawn]) => [item.id, drawn]));
const item = (id: number) => PICTURES.find(([each]) => each.id === id)?.[0] as PictureItem;

const COLOUR: Fixes = {
  jpegQuality: 92,
  blocks: false,
  stops: 0,
  dark: false,
  grey: false,
  seeThrough: false,
  colour: "sRGB",
  megapixels: 12.2,
  colours: "colour",
  tone: null,
};

/** Every style's network downloaded, and MicroAST. */
const NETWORKS = [
  ...STYLES.painters.map((style) => styleTool(style.download ?? "", style.name)),
  { ...styleTool("microast", "MicroAST"), size: 1_996_025, done: 1_996_025 },
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

/** What every screen's engine answers: the made-up library, every network downloaded. */
const EVERYWHERE: Record<string, unknown> = {
  "/health": { status: "ok", version: "0.10.0", dataDir: "", schemaVersion: 12 },
  "/settings": SETTINGS,
  "/library": LIBRARY,
  "/folders": FOLDERS,
  "/scan": scanDone(),
  "/records": null,
  "/pc": PC,
  "/jobs": [],
  "/jobs/held": [],
  "/tools": NETWORKS,
  "/sizes": SIZES,
  "/looks": LOOKS,
  "/styles": STYLES,
  "POST /screens": [],
  "/queue/now": QUIET,
};

/** A painting style and a look as a scene's words: "style=monet/paint=.8/look=warm-film". */
function wordsOf(paint: PaintStep | null | undefined, look: LookStep | null | undefined): string {
  const words = [
    paint ? `style=${paint.style}` : "",
    paint && paint.strength < 1 ? `paint=${paint.strength}` : "",
    look && look.look !== "original" ? `look=${look.look}` : "",
    look && look.look !== "original" && look.strength < 1 ? `strength=${look.strength}` : "",
    look?.touches.grain ? `grain=${look.touches.grain}` : "",
    look?.touches.vignette ? `vignette=${look.touches.vignette}` : "",
    paint?.parts?.length || look?.parts?.length ? "part=sky" : "",
  ];
  return words.filter(Boolean).join("/");
}

function pictureFor(url: URL, init: RequestInit | undefined): Response | undefined {
  const path = url.pathname;
  const copy = path.match(/^\/pictures\/(\d+)\/(thumbnail|view|full)$/);
  if (copy) return scene(SCENES.get(Number(copy[1])) ?? "harbour");
  const look = path.match(/^\/pictures\/(\d+)\/looks\/([\w-]+)$/);
  if (look) {
    const drawn = SCENES.get(Number(look[1])) ?? "harbour";
    return scene(look[2] === "original" ? drawn : `${drawn}/look=${look[2]}`);
  }
  const style = path.match(/^\/pictures\/(\d+)\/styles\/([\w-]+)$/);
  if (style) return scene(`${SCENES.get(Number(style[1])) ?? "harbour"}/style=${style[2]}`);
  if (/^\/styles\/yours-\d+\/thumbnail$/.test(path)) return scene("night-market");
  const preview = path.match(/^\/pictures\/(\d+)\/preview$/);
  if (preview) {
    const asked = JSON.parse(String(init?.body)) as { recipe: Recipe; side: string };
    const drawn = SCENES.get(Number(preview[1])) ?? "harbour";
    const words = asked.side === "after" ? wordsOf(asked.recipe.paint, asked.recipe.look) : "";
    return scene(words ? `${drawn}/${words}` : drawn, { "X-Made-In": "0.4" });
  }
  if (/^\/history\/\d+\/thumbnail$/.test(path)) return scene("harbour/style=hokusai");
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
  return fetch;
}

/** The plan for what's asked, at the picture's own pixels: its style and look in words, painted
 * on the card. */
function planFor(id: number, more: Record<string, unknown> = {}) {
  const shown = item(id);
  return (init: RequestInit | undefined) => {
    const recipe = JSON.parse(String(init?.body)) as Recipe;
    const named = recipe.paint
      ? (STYLES.painters.find((each) => each.id === recipe.paint?.style)?.name ?? "A style")
      : null;
    return plan({
      width: shown.width ?? 4032,
      height: shown.height ?? 3024,
      label: "",
      shape: "crop",
      sides: "none",
      kept: { x: 0, y: 0, width: 1, height: 1 },
      canvas: { x: 0, y: 0, width: 1, height: 1 },
      method: "keep",
      model: null,
      how: "",
      note: "",
      look: named,
      paintPlace: recipe.paint ? "card" : null,
      seconds: 1.2,
      ...more,
    });
  };
}

/** A picture in Phone opened, a colour photo unless said, with the plan for its style. */
function opened(id: number, fixes: Partial<Fixes> = {}, more: Record<string, unknown> = {}) {
  return {
    [`/pictures/${id}`]: pictureDetails(item(id), { camera: null }),
    [`/pictures/${id}/neighbours`]: { before: [], after: [] },
    [`/pictures/${id}/fixes`]: { ...COLOUR, ...fixes },
    [`POST /pictures/${id}/plan`]: planFor(id),
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

/** jsdom's pointer events carry no button; Mado's stages look for the left one. */
class PointerEventLike extends MouseEvent {
  pointerId: number;
  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 1;
  }
}

/** The sky over the harbour, as SAM picks it with one click, outlined in a frame 1000 square. */
const SKY = {
  parts: [{ name: "Part 1", clicks: [{ x: 0.3, y: 0.25, keep: true }], choice: 1, choices: 3 }],
  outline: "M0 0L1000 0L1000 613L805 573L625 620L455 567L295 633L130 600L0 647Z",
  read: 0.9,
  place: "card",
  seconds: 0.05,
  waited: 0,
  missed: false,
};

/** The picture's page on the Looks tab, the styles' grid at the top of the tools column. */
async function stylesOf(id: number) {
  draw("/library/pictures/:id", `/library/pictures/${id}?folder=1`, <PicturePage />);
  fireEvent.click(await screen.findByRole("tab", { name: "Looks" }));
  return screen.findByRole("radiogroup", { name: "Painting styles" });
}

/** The styles' heading at the top of the tools column, as the shoot scrolls it. */
function showStyles() {
  screen.getByRole("heading", { name: "Painting styles" }).setAttribute("data-shot-top", "");
}

describe.runIf(SHOTS)("The painting styles' screens", () => {
  beforeEach(() => {
    drawScenes();
    vi.stubGlobal("PointerEvent", PointerEventLike);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("styles", async () => {
    engine(opened(11));
    await measuredBoxes("styles");
    const grid = await stylesOf(11);
    fireEvent.click(within(grid).getByRole("radio", { name: "After Monet" }));
    const strength = screen.getByRole("slider", { name: "Style strength" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    await settle(2000);
    showStyles();
    await dump("styles");
  });

  it("style-own-colours", async () => {
    engine(opened(11));
    await measuredBoxes("style-own-colours");
    const grid = await stylesOf(11);
    fireEvent.click(within(grid).getByRole("radio", { name: "After Van Gogh" }));
    fireEvent.click(screen.getByRole("switch", { name: "Keep the picture's colours" }));
    await settle(2000);
    showStyles();
    await dump("style-own-colours");
  });

  it("style-look-touches", async () => {
    engine(opened(11));
    await measuredBoxes("style-look-touches");
    const grid = await stylesOf(11);
    fireEvent.click(within(grid).getByRole("radio", { name: "After Hokusai" }));
    const looks = screen.getByRole("radiogroup", { name: "Looks" });
    fireEvent.click(within(looks).getByRole("radio", { name: "Warm film" }));
    const strength = screen.getByRole("slider", { name: "Strength" });
    for (let step = 0; step < 4; step++) fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.click(screen.getByRole("button", { name: /^Grain/ }));
    await settle(2000);
    await dump("style-look-touches");
  });

  it("style-part", async () => {
    engine(opened(11, {}, { "POST /pictures/11/select": SKY }));
    await measuredBoxes("style-part");
    const grid = await stylesOf(11);
    fireEvent.click(within(grid).getByRole("radio", { name: "After Seurat" }));
    await settle(500);
    const stage = document.querySelector(".checks.cursor-crosshair") as HTMLElement;
    fireEvent.click(stage, { clientX: 300, clientY: 120 });
    await screen.findByText(/only on a part/);
    await settle(2000);
    await dump("style-part");
  });

  it("style-classic", async () => {
    engine(opened(12));
    await measuredBoxes("style-classic");
    const grid = await stylesOf(12);
    fireEvent.click(within(grid).getByRole("radio", { name: "Oil paint" }));
    const brush = screen.getByRole("slider", { name: "Brush" });
    fireEvent.keyDown(brush, { key: "PageUp" });
    fireEvent.keyDown(brush, { key: "PageUp" });
    await settle(2000);
    showStyles();
    await dump("style-classic");
  });

  it("style-download", async () => {
    engine({
      ...opened(11),
      "/tools": [
        styleTool("style-van-gogh-starry-night", "After Van Gogh", "missing"),
        {
          ...styleTool("style-hokusai-great-wave", "After Hokusai", "downloading"),
          done: 2_893_000,
        },
        styleTool("style-monet-water-lilies-1915", "After Monet"),
        styleTool("style-seurat-gravelines", "After Seurat", "missing"),
        { ...styleTool("microast", "MicroAST", "missing"), size: 1_996_025 },
      ],
      // Save waits for the network, as the engine's plan says.
      "POST /pictures/11/plan": planFor(11, {
        needs: [{ id: "style-van-gogh-starry-night", name: "After Van Gogh", size: 6_888_971 }],
      }),
    });
    await measuredBoxes("style-download");
    const grid = await stylesOf(11);
    fireEvent.click(
      await within(grid).findByRole("radio", { name: "After Van Gogh, 6.9 MB to download" }),
    );
    await settle(2000);
    showStyles();
    await dump("style-download");
  });

  it("style-busy", async () => {
    engine({
      ...opened(11),
      "/queue/now": {
        working: true,
        paused: false,
        batch: "Holiday prints",
        over: 3,
        total: 40,
        progress: 0.3,
        waiting: 37,
      },
      "POST /pictures/11/preview": () => new Response(new ReadableStream({ start() {} })),
    });
    await measuredBoxes("style-busy");
    const grid = await stylesOf(11);
    fireEvent.click(within(grid).getByRole("radio", { name: "After Monet" }));
    await screen.findByText(/Waiting for the graphics card/, {}, { timeout: 3000 });
    await settle(500);
    showStyles();
    await dump("style-busy");
  });

  it("style-huge", async () => {
    engine({
      ...opened(14),
      "POST /pictures/14/plan": planFor(14, {
        paintNote:
          "Painted at 1392 × 928, then made 12000 × 8000: about 9 times bigger, so seen close its strokes are soft. A smaller size on the Size tab keeps them crisp.",
        seconds: 4.1,
      }),
    });
    await measuredBoxes("style-huge");
    const grid = await stylesOf(14);
    fireEvent.click(within(grid).getByRole("radio", { name: "After Hokusai" }));
    await screen.findByText(/about 9 times bigger/);
    await settle(1500);
    showStyles();
    await dump("style-huge");
  });

  it("style-grey", async () => {
    engine(opened(15, { grey: true }));
    await measuredBoxes("style-grey");
    const grid = await stylesOf(15);
    fireEvent.click(within(grid).getByRole("radio", { name: "After Monet" }));
    await screen.findByText(/This picture is black and white/);
    await settle(1500);
    showStyles();
    await dump("style-grey");
  });

  it("style-see-through", async () => {
    engine(opened(13, { seeThrough: true }));
    await measuredBoxes("style-see-through");
    const grid = await stylesOf(13);
    fireEvent.click(within(grid).getByRole("radio", { name: "Cartoon" }));
    await settle(2000);
    await dump("style-see-through");
  });

  it("picture-style", async () => {
    engine(opened(11));
    await measuredBoxes("picture-style");
    await stylesOf(11);
    fireEvent.click(screen.getByRole("button", { name: "A picture of yours…" }));
    await screen.findByRole("dialog", { name: "A picture as the style" });
    await settle(1000);
    await dump("picture-style");
  });

  it("picture-style-plain", async () => {
    engine({
      ...opened(11),
      "POST /pictures/11/style": () =>
        Response.json(
          {
            detail:
              "Harbour at dusk.jpg is nearly one colour, so there's little style in it to take. Pick a picture with more colour and texture.",
          },
          { status: 422 },
        ),
    });
    await measuredBoxes("picture-style-plain");
    await stylesOf(11);
    fireEvent.click(screen.getByRole("button", { name: "A picture of yours…" }));
    const card = await screen.findByRole("dialog", { name: "A picture as the style" });
    fireEvent.click(within(card).getByRole("button", { name: "Use this picture" }));
    await within(card).findByRole("alert");
    await settle(1000);
    await dump("picture-style-plain");
  });

  it("picture-style-reader", async () => {
    engine({
      ...opened(11),
      "/tools": [
        ...NETWORKS.slice(0, 4),
        { ...styleTool("microast", "MicroAST", "missing"), size: 1_996_025 },
      ],
    });
    await measuredBoxes("picture-style-reader");
    await stylesOf(11);
    fireEvent.click(screen.getByRole("button", { name: "A picture of yours…" }));
    const card = await screen.findByRole("dialog", { name: "A picture as the style" });
    await within(card).findByText(/Reading a picture's style takes MicroAST/);
    await settle(1000);
    await dump("picture-style-reader");
  });

  it("picture-style-keep", async () => {
    engine({
      ...opened(11),
      "POST /pictures/11/style": { code: "c3R5bGU=", named: "Night market", version: "v10" },
    });
    await measuredBoxes("picture-style-keep");
    await stylesOf(11);
    fireEvent.click(screen.getByRole("button", { name: "A picture of yours…" }));
    const card = await screen.findByRole("dialog", { name: "A picture as the style" });
    fireEvent.click(within(card).getByRole("button", { name: "Use this picture" }));
    await screen.findByRole("radio", { name: "Night market style" });
    fireEvent.click(screen.getByRole("button", { name: "Keep as a style" }));
    await settle(2000);
    showStyles();
    await dump("picture-style-keep");
  });

  it("style-yours", async () => {
    engine(opened(12));
    await measuredBoxes("style-yours");
    const grid = await stylesOf(12);
    fireEvent.click(within(grid).getByRole("radio", { name: "Lantern glow" }));
    await screen.findByText("From Night market.jpg");
    await settle(2000);
    showStyles();
    await dump("style-yours");
  });

  it("batch-paint", async () => {
    await measuredBoxes("batch-paint");
    engine({
      "/recipes": [],
      "POST /batches/takes": takes({
        words: [
          {
            kind: "paint",
            title: "A painting style",
            detail: "After Hokusai at 80%, in each picture's own colours",
            chip: "After Hokusai",
            amount: "80%",
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
      pick: { how: "ticked", ids: [11, 12, 15] },
      picked: {
        ...PICKED,
        pictures: [
          batchPicture(11, "Harbour at dusk.jpg"),
          batchPicture(12, "Little sail.jpg"),
          batchPicture(15, "Still lake.jpg"),
        ],
      },
    });
    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "A painting style" })).click();
    const card = await screen.findByRole("dialog", { name: "Paint them in a style" });
    fireEvent.click(await within(card).findByRole("button", { name: "After Hokusai" }));
    fireEvent.click(within(card).getByRole("switch", { name: "Keep each picture's own colours" }));
    const strength = within(card).getByRole("slider", { name: "Style strength" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    await settle(1500);
    await dump("batch-paint");
  });

  it("history-painted", async () => {
    engine({
      "/history": {
        entries: [
          entry({
            id: 3,
            madeFor: null,
            look: "After Hokusai at 80% and Warm film at 60%",
            name: "Harbour at dusk.jpg",
            result: "D:\\Pictures\\Phone\\Harbour at dusk (After Hokusai, Warm film).jpg",
            resultName: "Harbour at dusk (After Hokusai, Warm film).jpg",
          }),
          entry({
            id: 2,
            madeFor: "TV 8K",
            look: "Oil paint at 90%",
            name: "Little sail.jpg",
            result: "D:\\Pictures\\Phone\\Little sail (TV 8K, Oil paint).jpg",
            resultName: "Little sail (TV 8K, Oil paint).jpg",
          }),
        ],
        older: null,
        batches: [],
        reviews: [],
      },
    });
    draw("/history", "/history", <HistoryPage />);
    await screen.findByText(/After Hokusai at 80% and Warm film at 60%/);
    await settle(1500);
    await dump("history-painted");
  });
});
