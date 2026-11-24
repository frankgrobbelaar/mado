/**
 * The README's screens, drawn with Mado's own components and made-up data chosen for them, and
 * written out for scripts/readme-pictures.mjs to shoot (docs/development.md, "Taking the README's
 * pictures again"). Skipped unless MADO_SHOTS names a folder, so CI and `pnpm check` never run it.
 *
 * One story runs through them: Mado 0.7.0 with the made-up library (Phone, Camera and Scans,
 * 4,812 pictures), the queue making Phone wallpapers, 12 of 30, in every screen's status bar and
 * on the rail. Every picture is a scene the shoot draws by code (scripts/readme-scenes.mjs).
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
import { WallpaperPage } from "@/features/wallpaper/wallpaper-page";
import {
  type BatchPicture,
  EngineProvider,
  type KeptRecipe,
  type LookStep,
  type PaintStep,
  type PictureItem,
  type Recipe,
  type StepWords,
} from "@/lib/engine";
import {
  batch,
  choice,
  duplicates,
  FOLDERS,
  fakeEngine,
  LIBRARY,
  LOOKS,
  monitor,
  PC,
  page,
  part,
  picture,
  pictureDetails,
  plan,
  READY,
  SETTINGS,
  SIZES,
  STYLES,
  scanDone,
  studio,
  takes,
} from "./engine";
import { drawScenes, dump, measuredBoxes, SHOTS, scene } from "./shots";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({ minimize() {}, toggleMaximize() {}, close() {} }),
}));

/** The pictures in Phone, newest first, each with the scene drawn for it. */
const PHONE: [PictureItem, string][] = [
  [picture(10, "Night market.jpg", "2026-11-14T21:10:00"), "night-market"],
  [picture(11, "Harbour at dusk.heic", "2026-11-14T18:42:07", { favourite: true }), "harbour"],
  [picture(12, "Little sail.jpg", "2026-11-14T16:05:00", { size: 4_400_000 }), "little-sail"],
  [picture(13, "Low tide.jpg", "2026-11-14T14:20:00"), "low-tide"],
  [picture(14, "Spring meadow.heic", "2026-11-14T11:31:00"), "spring-meadow"],
  [picture(15, "Still lake.jpg", "2026-11-14T07:58:00"), "still-lake"],
  [
    picture(20, "Warm dunes.jpg", "2026-11-13T17:20:00", {
      group: { key: 20, kind: "duplicates", pictures: 2 },
    }),
    "warm-dunes",
  ],
  [picture(21, "Garden rose.jpg", "2026-11-13T15:47:00", { favourite: true }), "garden-rose"],
  [picture(22, "Red canyon.jpg", "2026-11-13T12:30:00"), "red-canyon"],
  [picture(23, "Open water.jpg", "2026-11-13T11:03:00"), "little-sail/flip"],
  [
    picture(24, "Snowfield.jpg", "2026-11-13T10:02:00", {
      group: { key: 24, kind: "burst", pictures: 5 },
    }),
    "snowfield",
  ],
  [picture(25, "Misty pines.jpg", "2026-11-13T09:12:00"), "misty-pines"],
  [picture(30, "Green sky.jpg", "2026-11-11T23:51:00"), "green-sky"],
  [picture(31, "Late tram.jpg", "2026-11-11T22:14:00"), "night-market/flip"],
  [picture(32, "Shoreline.jpg", "2026-11-11T13:22:00"), "low-tide/flip"],
  [picture(33, "Morning lake.jpg", "2026-11-11T06:40:00"), "still-lake/flip"],
];
const SCENES = new Map(PHONE.map(([item, drawn]) => [item.id, drawn]));
const ITEMS = PHONE.map(([item]) => item);
const item = (id: number) => ITEMS.find((each) => each.id === id) as PictureItem;

/** Pictures made today, newest first, for Home, and the scene each is drawn as. */
const MADE = [
  { id: 61, name: "Garden rose", madeFor: null, look: null, edit: "cut out the subject" },
  { id: 62, name: "Harbour at dusk", madeFor: "Ultrawide", look: null, edit: null },
  { id: 63, name: "Snowfield", madeFor: "A3 print", look: null, edit: null },
  { id: 64, name: "Misty pines", madeFor: null, look: "Warm film at 60%", edit: null },
  { id: 65, name: "Red canyon", madeFor: "Phone", look: null, edit: null },
  { id: 66, name: "Night market", madeFor: "TV 8K", look: null, edit: null },
];
const MADE_SCENES: Record<number, string> = {
  61: "garden-rose/cutout=flower",
  62: "harbour",
  63: "snowfield",
  64: "misty-pines/look=warm-film/strength=.6",
  65: "red-canyon",
  66: "night-market",
};

/** Mado's fourteen looks: the board's nine and Mado's own five. */
const ALL_LOOKS = {
  ...LOOKS,
  looks: [
    ...LOOKS.looks,
    { id: "bold-colour", name: "Bold colour", version: "9a" },
    { id: "sepia-print", name: "Sepia print", version: "9b" },
    { id: "moody-blue", name: "Moody blue", version: "9c" },
    { id: "cross-processed", name: "Cross-processed", version: "9d" },
    { id: "soft-pastel", name: "Soft pastel", version: "9e" },
  ],
};

/** A fix's model, downloaded, as the engine lists it. */
const FIX_MODEL = {
  id: "",
  name: "",
  version: "models-1",
  purpose: "",
  licence: "Apache-2.0 AND MIT",
  size: 0,
  when: "asked",
  state: "ready",
  done: 0,
  problem: null,
} as const;

/** See it first's three, in a batch of Trip's pictures, each made with Warm film. */
const SAMPLE_SCENES = ["warm-dunes", "still-lake", "snowfield"];

/** The owner's monitors, as Windows tells the shell of them and the wallpaper studio draws them:
 * the main one, one beside it and one turned on its side. */
const MONITORS = [
  { width: 2560, height: 1440, main: true },
  { width: 1920, height: 1080, main: false },
  { width: 1080, height: 1920, main: false },
];

/** The sizes the Size tab offers, the owner's screens among them as the engine names them. */
const SIZES_HERE = {
  ...SIZES,
  yours: MONITORS.map(({ width, height }, at) => ({
    id: `yours-${width}x${height}`,
    name: at === 0 ? "Main screen" : `Screen ${at + 1}`,
    width,
    height,
    group: "yours",
    purpose: "screen",
    label: `${width} × ${height}`,
  })),
};

/** What every screen's engine answers: Mado 0.7.0 with the made-up library, the queue making
 * Phone wallpapers. */
const EVERYWHERE: Record<string, unknown> = {
  "/health": { status: "ok", version: "0.7.0", dataDir: "", schemaVersion: 9 },
  "/settings": SETTINGS,
  "/library": { ...LIBRARY, favourites: 24 },
  "/folders": FOLDERS,
  "/scan": scanDone(),
  "/records": null,
  "/pc": PC,
  "/jobs": [],
  "/jobs/held": [],
  "/tools": [],
  "/sizes": SIZES_HERE,
  "/looks": ALL_LOOKS,
  "/styles": STYLES,
  "POST /screens": [],
  "/queue/now": {
    working: true,
    paused: false,
    batch: "Phone wallpapers",
    over: 12,
    total: 30,
    progress: 0.4,
    waiting: 18,
  },
};

/** A look step as a scene's words: "look=warm-film/strength=.6/grain=20/part=sky". */
function looked(step: LookStep | null, part: string | null): string {
  if (!step) return "";
  const words = [
    step.look !== "original" ? `look=${step.look}` : "",
    step.look !== "original" && step.strength < 1 ? `strength=${step.strength}` : "",
    step.touches.grain ? `grain=${step.touches.grain}` : "",
    step.touches.vignette ? `vignette=${step.touches.vignette}` : "",
    step.parts?.length && part ? `part=${part}` : "",
  ];
  return words.filter(Boolean).join("/");
}

/** A painting style as a scene's words: "style=monet/paint=.8". */
function painted(step: PaintStep | null | undefined): string {
  if (!step) return "";
  return [`style=${step.style}`, step.strength < 1 ? `paint=${step.strength}` : ""]
    .filter(Boolean)
    .join("/");
}

/** Pictures shown with something wrong with them while a screen fixes it, by their number: the
 * scene as the picture is, before its fixes ("low-tide/dark=2.6/grain=45"). */
const DAMAGED = new Map<number, string>();

/** What's still wrong with a damaged picture after the fixes asked for ("low-tide/dark=2.6/grain=45"
 * brightened is "low-tide/grain=45"), as the engine makes them: all of a picture fitted is sent
 * only the brightening; a part at full detail every fix. */
function unfixed(damaged: string, fix: Recipe["fix"]): string {
  const [drawn = "", ...wrong] = damaged.split("/");
  const out: Record<string, boolean> = {
    dark: Boolean(fix?.dark),
    grain: Boolean(fix?.noise),
    blocks: Boolean(fix?.jpeg),
  };
  return [drawn, ...wrong.filter((word) => !out[word.split("=")[0] ?? ""])].join("/");
}

/** The made-up pictures the engine sends: each picture's scene, as the screen asks for it. */
function pictureFor(url: URL, init: RequestInit | undefined): Response | undefined {
  const path = url.pathname;
  const copy = path.match(/^\/pictures\/(\d+)\/(thumbnail|view|full)$/);
  if (copy) {
    const id = Number(copy[1]);
    return scene(DAMAGED.get(id) ?? SCENES.get(id) ?? "harbour");
  }
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
    const onPart = !asked.recipe.look?.parts?.length && asked.recipe.paint?.parts?.length;
    const words = [
      painted(asked.recipe.paint),
      looked(asked.recipe.look, "sky"),
      onPart ? "part=sky" : "",
    ]
      .filter(Boolean)
      .join("/");
    const id = Number(preview[1]);
    const fix = asked.side === "after" ? asked.recipe.fix : null;
    const damaged = DAMAGED.get(id);
    const drawn = (damaged ? unfixed(damaged, fix) : null) ?? SCENES.get(id) ?? "harbour";
    return scene(words ? `${drawn}/${words}` : drawn, { "X-Made-In": "0.9" });
  }
  const made = path.match(/^\/history\/(\d+)\/thumbnail$/);
  if (made) return scene(MADE_SCENES[Number(made[1])] ?? "harbour");
  const sample = path.match(/^\/batches\/samples\/\w+\/(\d)\/(before|after|full)$/);
  if (sample) {
    const drawn = SAMPLE_SCENES[Number(sample[1])] ?? "warm-dunes";
    return scene(sample[2] === "before" ? drawn : `${drawn}/look=warm-film/strength=.6`);
  }
  return undefined;
}

/** The engine for a screen: what every screen has, `answers`, and the pictures. */
function engine(answers: Record<string, unknown>) {
  const fetch = fakeEngine({ ...EVERYWHERE, ...answers });
  const answer = fetch.getMockImplementation();
  fetch.mockImplementation(async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    return (
      pictureFor(url, init) ??
      (answer ? answer(input, init) : Response.json({ detail: "Not found" }, { status: 404 }))
    );
  });
}

/** A page in the window as Mado draws it, the rail, title bar and status bar round it: `route`
 * as app.tsx routes it, opened at `at`. */
function draw(route: string, at: string, page: ReactNode, state?: unknown) {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "screens") return MONITORS;
    return undefined;
  });
  const [pathname = at, search] = at.split("?");
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[{ pathname, search: search ? `?${search}` : "", state }]}>
          <Routes>
            <Route element={<AppShell />}>
              <Route path={route} element={page} />
            </Route>
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

/** Lets the page settle: the engine's answers in, the pictures asked for and shown. */
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

/** A picture in Phone, opened as its page asks for it: its details and its neighbours. No camera's
 * name: a made-up one could be someone's. */
function opened(id: number) {
  const at = ITEMS.findIndex((each) => each.id === id);
  return {
    [`/pictures/${id}`]: pictureDetails(item(id), { camera: null }),
    [`/pictures/${id}/neighbours`]: {
      before: ITEMS.slice(Math.max(at - 1, 0), at),
      after: ITEMS.slice(at + 1, at + 9),
    },
  };
}

/** Harbour at dusk's plan: TV 8K cropped around the harbour, and the look when there's one. A
 * phone's HEIC, its colours are Display P3, and stay so. */
function harbourPlan(init: RequestInit | undefined) {
  const recipe = JSON.parse(String(init?.body)) as Recipe;
  const look = recipe.look
    ? `Warm film at ${Math.round(recipe.look.strength * 100)}%${recipe.look.parts?.length ? ", grain 20, vignette 35 on a part" : ""}`
    : null;
  if (!recipe.size)
    return plan({
      width: 4032,
      height: 3024,
      label: "",
      sides: "none",
      kept: { x: 0, y: 0, width: 1, height: 1 },
      canvas: { x: 0, y: 0, width: 1, height: 1 },
      method: "keep",
      model: null,
      how: "",
      note: "",
      look,
      colour: "Display P3",
      seconds: 1,
    });
  return plan({
    kept: { x: 0, y: 0.22, width: 1, height: 0.75 },
    canvas: { x: 0, y: 0.22, width: 1, height: 0.75 },
    focus: [0.55, 0.6],
    look,
    colour: "Display P3",
  });
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

/** The little boat, sails and hull, picked with one click on its sail. */
const BOAT = {
  parts: [{ name: "Part 1", clicks: [{ x: 0.655, y: 0.5, keep: true }], choice: 1, choices: 3 }],
  outline: "M655 393L665 420L725 540L743 543L723 583L593 583L568 543L578 540Z",
  read: 0.9,
  place: "card",
  seconds: 0.05,
  waited: 0,
  missed: false,
};

describe.runIf(SHOTS)("The README's screens", () => {
  beforeEach(() => {
    drawScenes();
    vi.stubGlobal("PointerEvent", PointerEventLike);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("home", async () => {
    engine({
      "/duplicates": duplicates({ duplicates: 120, bursts: 92, pictures: 212 }),
      "/batches/done": [
        batch({ done: 48, failed: 0, waiting: 0, progress: 1, look: null, finishedAt: null }),
      ],
      "/space": [
        {
          drive: "D:",
          connected: true,
          free: 412_000_000_000,
          total: 1_000_000_000_000,
          pictures: 38_200_000_000,
          quarantine: 1_400_000_000,
          queue: 1_200_000_000,
        },
      ],
      "/history/today": MADE,
    });
    await measuredBoxes("home");
    draw("/", "/", <HomePage />);
    await screen.findByText("Made today");
    await settle();
    await dump("home");
  });

  it("library", async () => {
    engine({ "/pictures": page(ITEMS, "page-2", 3104) });
    await measuredBoxes("library");
    draw("/library", "/library?folder=1", <LibraryPage />);
    for (const name of [
      "Night market",
      "Harbour at dusk",
      "Little sail",
      "Red canyon",
      "Misty pines",
      "Green sky",
    ])
      fireEvent.click(await screen.findByRole("checkbox", { name: `Tick ${name}` }));
    await settle();
    await dump("library");
  });

  it("size", async () => {
    engine({ ...opened(11), "POST /pictures/11/plan": harbourPlan });
    await measuredBoxes("size");
    draw("/library/pictures/:id", "/library/pictures/11?folder=1", <PicturePage />);
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));
    await screen.findByText(/A TV is 16:9/);
    await settle();
    await dump("size");
  });

  it("looks", async () => {
    engine({
      ...opened(11),
      "POST /pictures/11/plan": harbourPlan,
      "POST /pictures/11/select": SKY,
    });
    await measuredBoxes("looks");
    draw("/library/pictures/:id", "/library/pictures/11?folder=1", <PicturePage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Looks" }));
    fireEvent.click(await screen.findByRole("radio", { name: "Warm film" }));
    const strength = screen.getByRole("slider", { name: "Strength" });
    for (let step = 0; step < 4; step++) fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.click(screen.getByRole("button", { name: /^Grain/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Vignette/ }));
    await settle(500);
    const stage = document.querySelector(".checks.cursor-crosshair") as HTMLElement;
    fireEvent.click(stage, { clientX: 300, clientY: 120 });
    await screen.findByText(/only on a part/);
    await settle(2000);
    await dump("looks");
  });

  it("edit", async () => {
    engine({
      ...opened(12),
      "POST /pictures/12/plan": plan({ width: 4032, height: 3024, label: "", sides: "none" }),
      "POST /pictures/12/select": BOAT,
    });
    await measuredBoxes("edit");
    draw("/library/pictures/:id", "/library/pictures/12?folder=1", <PicturePage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Edit" }));
    await settle(500);
    const stage = (await screen.findByRole("img", { name: "Little sail" }))
      .parentElement as HTMLElement;
    fireEvent.pointerDown(stage, { clientX: 500, clientY: 300, button: 0, pointerId: 1 });
    await screen.findByText(/picked with one click/);
    await settle();
    await dump("edit");
  });

  it("fix", async () => {
    DAMAGED.set(13, "low-tide/dark=2.6/grain=45");
    try {
      engine({
        ...opened(13),
        "/pictures/13/fixes": {
          jpegQuality: 94,
          blocks: false,
          stops: 2.6,
          dark: true,
          grey: false,
          seeThrough: false,
          colour: "sRGB",
          megapixels: 12.2,
        },
        "/tools": [
          { ...FIX_MODEL, id: "scunet", name: "SCUNet", size: 72_932_271 },
          { ...FIX_MODEL, id: "nafnet", name: "NAFNet", size: 68_940_956 },
        ],
        "POST /pictures/13/plan": plan({
          width: 4032,
          height: 3024,
          label: "",
          method: "keep",
          model: null,
          sides: "none",
          fix: "took out noise and brightened it",
          fixSeconds: 26,
          seconds: 27,
        }),
      });
      await measuredBoxes("fix");
      draw("/library/pictures/:id", "/library/pictures/13?folder=1", <PicturePage />);
      fireEvent.click(await screen.findByRole("tab", { name: "Fix" }));
      fireEvent.click(await screen.findByRole("switch", { name: "Dark photo" }));
      fireEvent.click(await screen.findByRole("switch", { name: "Noise" }));
      await screen.findByText(/Mado brightens it by about 2\.6 stops/);
      await settle(2500);
      await dump("fix");
    } finally {
      DAMAGED.clear();
    }
  });

  it("save", async () => {
    engine({
      ...opened(11),
      "POST /pictures/11/plan": harbourPlan,
      "POST /pictures/11/saving": {
        name: "Harbour at dusk (TV 8K, Warm film).jpg",
        folder: "D:\\Pictures\\Phone",
        taken: null,
        takenAt: null,
        bytes: 18_000_000,
        colour: "Display P3",
      },
    });
    await measuredBoxes("save");
    draw("/library/pictures/:id", "/library/pictures/11?folder=1", <PicturePage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Looks" }));
    fireEvent.click(await screen.findByRole("radio", { name: "Warm film" }));
    const strength = screen.getByRole("slider", { name: "Strength" });
    for (let step = 0; step < 4; step++) fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.click(screen.getByRole("tab", { name: "Size" }));
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));
    await screen.findByText(/A TV is 16:9/);
    await settle(1000);
    fireEvent.click(screen.getByRole("button", { name: "Save…" }));
    await screen.findByText("Harbour at dusk (TV 8K, Warm film).jpg");
    await settle();
    await dump("save");
  });

  it("batch", async () => {
    const trip: BatchPicture[] = Array.from({ length: 36 }, (_, at) => ({
      id: 100 + at,
      path: `D:\\Pictures\\Camera\\Trip\\${["Dune ridge", "Lake at dawn", "High pass"][at % 3]} ${at + 1}.jpg`,
      name: `${["Dune ridge", "Lake at dawn", "High pass"][at % 3]} ${at + 1}.jpg`,
      size: 2_700_000,
      width: 4032,
      height: 3024,
      version: `v${100 + at}`,
      raw: false,
    }));
    const words: StepWords[] = [
      {
        kind: "size",
        title: "Make it for a screen",
        detail:
          "Monitor 4K, 3840 × 2160, cropped around the subject; the right model for each picture",
        chip: "Monitor 4K",
        amount: null,
      },
      {
        kind: "look",
        title: "A look",
        detail: "Warm film at 60%",
        chip: "Warm film",
        amount: "60",
      },
      {
        kind: "save",
        title: "Save",
        detail: "As new pictures, JPEG 92, into a folder called Edited beside each",
        chip: "JPEG 92 into Edited",
        amount: null,
      },
    ];
    const recipe: KeptRecipe = {
      id: 1,
      name: "Trip to 4K",
      steps: [
        { step: "size", size: "monitor-4k", shape: "crop", kind: null, quality: null, clean: true },
        {
          step: "look",
          look: "warm-film",
          strength: 0.6,
          touches: { grain: 0, vignette: 0, glow: 0, fade: 0, leak: 0, dust: 0 },
        },
      ],
      saving: {
        how: "new",
        format: "JPEG",
        quality: 92,
        folder: "Edited",
        keepCamera: true,
        keepColours: true,
        keepLocation: false,
      },
      words,
      used: 4,
      usedAt: null,
      tonight: false,
    };
    const samples = {
      id: "trip123",
      round: 0,
      seconds: 72,
      // Three spread across the batch, as See it first picks them: its 4th, 17th and 30th.
      samples: [
        [103, 7_900_000],
        [116, 8_400_000],
        [129, 9_100_000],
      ].map(([picture = 0, madeBytes], index) => ({
        index,
        name: trip.find((each) => each.id === picture)?.name ?? "",
        bytes: 2_700_000,
        madeBytes,
        picture,
        state: "done",
        progress: 1,
        seconds: 24,
        width: 3840,
        height: 2160,
        problem: null,
      })),
    };
    engine({
      "/recipes": [
        recipe,
        { ...recipe, id: 2, name: "Phone wallpapers", used: 9 },
        { ...recipe, id: 3, name: "Holiday prints", used: 3 },
      ],
      "POST /batches/takes": takes({
        words,
        seconds: 840,
        bytes: 300_000_000, // as the three seen first come out, about 8.5 MB each
        example: "Name (Monitor 4K, Warm film).jpg",
        into: "Trip › Edited",
        madeFor: "Monitor 4K",
      }),
      "POST /batches/samples": samples,
      "/batches/samples/trip123": samples,
    });
    await measuredBoxes("batch");
    draw("/batch", "/batch", <BatchPage />, {
      pick: { how: "ticked", ids: trip.map((each) => each.id) },
      picked: {
        pictures: trip,
        bytes: trip.reduce((sum, each) => sum + each.size, 0),
        source: "Trip",
        shared: "D:\\Pictures\\Camera\\Trip",
        words: "ticked in Trip",
        leftOut: [],
      },
      recipe: 1,
      starts: "tonight",
    });
    await screen.findByText("Many at once");
    await settle(3500);
    await dump("batch");
  });

  it("wallpaper", async () => {
    const main = monitor({ key: "desk27", name: "Desk 27", number: 1 });
    const side = monitor({
      key: "side24",
      name: "Side 24",
      number: 2,
      x: -1920,
      y: 180,
      width: 1920,
      height: 1080,
      scale: 1,
      main: false,
    });
    const panel = monitor({
      key: "panel24",
      name: "Panel 24",
      number: 3,
      x: 2560,
      y: -240,
      width: 1080,
      height: 1920,
      scale: 1,
      rotation: 90,
      main: false,
    });
    const chosen = (key: string, id: number, focus: { x: number; y: number }) =>
      choice({
        monitor: key,
        picture: {
          id,
          name: item(id).name,
          path: item(id).path,
          width: 4032,
          height: 3024,
          version: item(id).version,
          outside: false,
          focus,
        },
      });
    engine({
      "/wallpaper": studio({
        monitors: [main, side, panel],
        width: 5560,
        height: 1920,
        choices: [
          chosen("desk27", 11, { x: 0.55, y: 0.6 }),
          chosen("side24", 24, { x: 0.5, y: 0.45 }),
          chosen("panel24", 21, { x: 0.5, y: 0.48 }),
        ],
        parts: [
          part({ monitor: "desk27", picture: 11 }),
          part({ monitor: "side24", picture: 24, width: 1920, height: 1080, scale: 0.476 }),
          part({ monitor: "panel24", picture: 21, width: 1080, height: 1920, scale: 0.635 }),
        ],
      }),
    });
    await measuredBoxes("wallpaper");
    draw("/wallpaper", "/wallpaper", <WallpaperPage />);
    await screen.findByText(/as Windows arranges them/);
    await settle();
    await dump("wallpaper");
  });
});
