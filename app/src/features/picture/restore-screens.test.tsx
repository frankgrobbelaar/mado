/**
 * Restoring's screens, as Mado draws them, written out to be shot in dark and light:
 *
 *   node scripts/readme-pictures.mjs --screens app/src/features/picture/restore-screens.test.tsx --out <folder>
 *
 * An old sepia print's scratches and dust found and shown as a mask, the one it missed painted
 * over; filled and coloured, before and after; a black-and-white print coloured; a colour photo's
 * faded colours brought back; and the small things: the models to download first, nothing found, a
 * mask over most of the picture, a colour photo asked to be coloured, a sepia print's faded colours,
 * a scan too big; the Restore step for many at once; Save and History naming it. Skipped unless
 * MADO_SHOTS names a folder. Every picture is a scene the shoot draws by code, every name made up.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, it, vi } from "vitest";
import { AppShell } from "@/components/shell/app-shell";
import { BatchPage } from "@/features/batch/batch-page";
import { HistoryPage } from "@/features/history/history-page";
import { EngineProvider, type Fixes, type PictureItem, type Recipe, type Tool } from "@/lib/engine";
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

/** Each picture, the scene it's drawn as, and how it's old ("look=sepia-print/scratches=1"). */
const PICTURES: [PictureItem, string, string][] = [
  [
    picture(21, "Old harbour.jpg", "2026-11-20T10:02:00", { width: 4032, height: 3024 }),
    "harbour",
    "look=sepia-print/scratches=1/grain=30",
  ],
  [picture(22, "Old meadow.jpg", "2026-11-20T10:05:00"), "spring-meadow", "look=silver/grain=25"],
  [picture(23, "Summer lake.jpg", "2026-11-20T10:07:00"), "still-lake", "look=faded"],
  [
    picture(24, "Album page.tif", "2026-11-20T10:09:00", {
      format: "TIFF",
      width: 14000,
      height: 9000,
      size: 378_000_000,
    }),
    "misty-pines",
    "look=sepia-print",
  ],
];
const SCENES = new Map(PICTURES.map(([item, drawn, old]) => [item.id, [drawn, old]] as const));
const item = (id: number) => PICTURES.find(([each]) => each.id === id)?.[0] as PictureItem;

const SEPIA: Fixes = {
  jpegQuality: 90,
  blocks: false,
  stops: 0,
  dark: false,
  grey: false,
  seeThrough: false,
  colour: "sRGB",
  megapixels: 12.2,
  colours: "toned",
  tone: "sepia",
};
const GREY: Fixes = { ...SEPIA, grey: true, colours: "grey", tone: null };
const COLOUR: Fixes = { ...SEPIA, colours: "colour", tone: null };

function model(id: string, name: string, size: number, state: Tool["state"] = "ready"): Tool {
  return {
    id,
    name,
    version: id === "ddcolor-tiny" ? "models-1" : "models-3",
    purpose: "",
    licence: id === "oldphoto-scratch-detector" ? "MIT" : "Apache-2.0",
    size,
    when: "asked",
    state,
    done: state === "downloading" ? Math.round(size * 0.36) : 0,
    problem: null,
  };
}

const MODELS = [
  model("oldphoto-scratch-detector", "Old-photo scratch detector", 75_391_673),
  model("lama", "LaMa", 209_175_026),
  model("ddcolor-tiny", "DDColor tiny", 270_266_480),
  model("scunet", "SCUNet", 72_932_271),
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

/** What every screen's engine answers: the made-up library, restoring's models downloaded. */
const EVERYWHERE: Record<string, unknown> = {
  "/health": { status: "ok", version: "0.13.0", dataDir: "", schemaVersion: 14 },
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

/** A picture as restoring leaves it: its scratches filled, coloured (its own colours, the old
 * print's tone gone) or its faded colours back. */
function restoredScene(id: number, recipe: Recipe | null): string {
  const [drawn = "harbour", old = ""] = SCENES.get(id) ?? [];
  const restore = recipe?.restore;
  const out = (word: string) => {
    const [key] = word.split("=");
    if (key === "scratches") return Boolean(restore?.scratches);
    if (key === "look") return Boolean(restore?.colour || restore?.faded);
    return false;
  };
  const left = old
    .split("/")
    .filter((word) => word && !out(word))
    .join("/");
  return left ? `${drawn}/${left}` : drawn;
}

function pictureFor(url: URL, init: RequestInit | undefined): Response | undefined {
  const copy = url.pathname.match(/^\/pictures\/(\d+)\/(thumbnail|view|full)$/);
  if (copy) return scene(restoredScene(Number(copy[1]), null));
  const preview = url.pathname.match(/^\/pictures\/(\d+)\/preview$/);
  if (preview) {
    const asked = JSON.parse(String(init?.body)) as { recipe: Recipe; side: string };
    const id = Number(preview[1]);
    return scene(restoredScene(id, asked.side === "after" ? asked.recipe : null), {
      "X-Made-In": "0.8",
    });
  }
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
      pictureFor(url, init) ??
      (answer ? answer(input, init) : Response.json({ detail: "Not found" }, { status: 404 }))
    );
  });
}

/** What the detector found on a picture: the mask the shoot draws, and how much it covers. */
function found(id: number, covers: number) {
  const [drawn = "harbour"] = SCENES.get(id) ?? [];
  const mask = covers > 0 ? `${drawn}/mask` : `${drawn}/mask=none`;
  return () => scene(mask, { "X-Found": String(covers), "X-Made-In": "0.6", "X-Place": "card" });
}

/** A picture in Phone opened, with what Mado measured of it and the plan for restoring it. */
function opened(id: number, fixes: Fixes, more: Record<string, unknown> = {}) {
  const shown = item(id);
  return {
    [`/pictures/${id}`]: pictureDetails(shown, { camera: null, located: false }),
    [`/pictures/${id}/neighbours`]: { before: [], after: [] },
    [`/pictures/${id}/fixes`]: {
      ...fixes,
      megapixels: ((shown.width ?? 0) * (shown.height ?? 0)) / 1e6,
    },
    [`POST /pictures/${id}/scratches`]: found(id, 0.014),
    [`POST /pictures/${id}/plan`]: plan({
      width: shown.width ?? 4032,
      height: shown.height ?? 3024,
      label: "",
      method: "keep",
      model: null,
      restore: "filled its scratches and dust and coloured it",
      restoreSeconds: 10,
      restorePlace: "card",
      restoreCovers: 0.016,
      seconds: 11,
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

/** The picture's page on the Fix tab, with these of restoring's rows turned on. */
async function restoring(id: number, on: string[]) {
  draw("/library/pictures/:id", `/library/pictures/${id}?folder=1`, <PicturePage />);
  fireEvent.click(await screen.findByRole("tab", { name: "Fix" }));
  const rows = await screen.findByRole("region", { name: "Restoring" });
  // What Mado measured of its colours first, which way the Colour row starts.
  await within(rows).findByText(/Mado can colour it|faded colours brought back from the picture/);
  for (const name of on) fireEvent.click(within(rows).getByRole("switch", { name }));
  return rows;
}

/** A stroke of the brush along the dark scratch the detector missed (fractions of the picture). */
function paintTheMissedScratch(stage: HTMLElement) {
  // jsdom lays nothing out: the picture stands where the shoot's stage puts it, about this big.
  const frame = { left: 0, top: 0, width: 1000, height: 750 };
  stage.getBoundingClientRect = () => ({
    ...frame,
    right: 1000,
    bottom: 750,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  const at = ([x, y]: [number, number]) => ({
    clientX: frame.left + x * frame.width,
    clientY: frame.top + y * frame.height,
    pointerId: 1,
  });
  const points: [number, number][] = [
    [0.38, 0],
    [0.395, 0.2],
    [0.385, 0.45],
    [0.37, 0.7],
    [0.42, 1],
  ];
  fireEvent.pointerDown(stage, { ...at(points[0] ?? [0, 0]), button: 0 });
  for (const point of points.slice(1)) fireEvent.pointerMove(stage, at(point));
  fireEvent.pointerUp(stage, at(points.at(-1) ?? [0, 0]));
}

describe.runIf(SHOTS)("Restoring's screens", () => {
  beforeEach(() => {
    drawScenes();
    Element.prototype.setPointerCapture = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("restore-mask", async () => {
    engine(opened(21, SEPIA));
    await measuredBoxes("restore-mask");
    await restoring(21, ["Scratches and dust"]);
    await screen.findByText("The mask");
    await settle(1200);
    const stage = (await screen.findByRole("img", { name: "Old harbour" }))
      .parentElement as HTMLElement;
    paintTheMissedScratch(stage);
    await settle(1500);
    await dump("restore-mask");
  });

  it("restore-filled", async () => {
    engine(opened(21, SEPIA));
    await measuredBoxes("restore-filled");
    const rows = await restoring(21, ["Scratches and dust", "Colour"]);
    await screen.findByText("The mask");
    await settle(800);
    fireEvent.click(within(rows).getByRole("button", { name: "Fill them in" }));
    await screen.findByText(/After · Scratches, Colour/);
    await settle(2500);
    await dump("restore-filled");
  });

  it("restore-colour", async () => {
    engine(
      opened(22, GREY, {
        "POST /pictures/22/plan": plan({
          width: 4032,
          height: 3024,
          label: "",
          method: "keep",
          model: null,
          restore: "coloured it",
          restoreSeconds: 4.6,
          restorePlace: "card",
          seconds: 5,
        }),
      }),
    );
    await measuredBoxes("restore-colour");
    await restoring(22, ["Colour"]);
    await screen.findByText(/a coat's colour is a guess/);
    await settle(2500);
    await dump("restore-colour");
  });

  it("restore-faded", async () => {
    engine(
      opened(23, COLOUR, {
        "POST /pictures/23/plan": plan({
          width: 4032,
          height: 3024,
          label: "",
          method: "keep",
          model: null,
          restore: "brought its faded colours back",
          restoreSeconds: 1.2,
          restorePlace: "card",
          seconds: 2,
        }),
      }),
    );
    await measuredBoxes("restore-faded");
    await restoring(23, ["Colour"]);
    await screen.findByText(/Whether its colours faded Mado can't measure/);
    await settle(2500);
    await dump("restore-faded");
  });

  it("restore-download", async () => {
    engine({
      ...opened(21, SEPIA),
      "/tools": [
        model("oldphoto-scratch-detector", "Old-photo scratch detector", 75_391_673, "downloading"),
        model("lama", "LaMa", 209_175_026),
        model("ddcolor-tiny", "DDColor tiny", 270_266_480, "missing"),
      ],
    });
    await measuredBoxes("restore-download");
    await restoring(21, ["Scratches and dust", "Colour"]);
    await screen.findByRole("progressbar", { name: "Downloading Old-photo scratch detector" });
    await settle(1500);
    await dump("restore-download");
  });

  it("restore-nothing", async () => {
    engine(
      opened(21, SEPIA, {
        "POST /pictures/21/scratches": found(21, 0),
        "POST /pictures/21/plan": plan({
          width: 4032,
          height: 3024,
          label: "",
          method: "keep",
          model: null,
          restore: null,
          restoreCovers: 0,
          seconds: 0,
        }),
      }),
    );
    await measuredBoxes("restore-nothing");
    await restoring(21, ["Scratches and dust"]);
    await screen.findByText(/Mado found no scratches or dust/);
    await settle(1500);
    await dump("restore-nothing");
  });

  it("restore-most", async () => {
    engine(
      opened(21, SEPIA, {
        "POST /pictures/21/scratches": found(21, 0.31),
        "POST /pictures/21/plan": plan({
          width: 4032,
          height: 3024,
          label: "",
          method: "keep",
          model: null,
          restore: "filled its scratches and dust",
          restoreSeconds: 4,
          restorePlace: "card",
          restoreCovers: 0.62,
          seconds: 5,
        }),
      }),
    );
    await measuredBoxes("restore-most");
    await restoring(21, ["Scratches and dust"]);
    await screen.findByText(/That's most of the picture/);
    await settle(1500);
    await dump("restore-most");
  });

  it("restore-in-colour", async () => {
    engine(opened(23, COLOUR));
    await measuredBoxes("restore-in-colour");
    const rows = await restoring(23, ["Colour"]);
    fireEvent.click(within(rows).getByRole("radio", { name: "Colour it" }));
    await screen.findByText(/It's in colour already/);
    await settle(2000);
    await dump("restore-in-colour");
  });

  it("restore-sepia", async () => {
    engine(opened(21, SEPIA));
    await measuredBoxes("restore-sepia");
    const rows = await restoring(21, ["Colour"]);
    fireEvent.click(within(rows).getByRole("radio", { name: "Bring its colours back" }));
    await screen.findByText(/so there are no colours to bring back/);
    await settle(2000);
    await dump("restore-sepia");
  });

  it("restore-big", async () => {
    engine(opened(24, SEPIA));
    await measuredBoxes("restore-big");
    draw("/library/pictures/:id", "/library/pictures/24?folder=1", <PicturePage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Fix" }));
    await screen.findByText(/Mado restores pictures up to 100/);
    await settle(1500);
    await dump("restore-big");
  });

  it("save-restored", async () => {
    engine({
      ...opened(21, SEPIA),
      "POST /pictures/21/saving": {
        name: "Old harbour (Restored).jpg",
        folder: "D:\\Pictures\\Phone",
        taken: null,
        takenAt: null,
        bytes: 5_200_000,
        colour: "sRGB",
      },
    });
    await measuredBoxes("save-restored");
    const rows = await restoring(21, ["Scratches and dust", "Colour"]);
    await screen.findByText("The mask");
    await settle(800);
    fireEvent.click(within(rows).getByRole("button", { name: "Fill them in" }));
    await settle(1200);
    fireEvent.click(screen.getByRole("button", { name: "Save…" }));
    await screen.findByText("Old harbour (Restored).jpg");
    await settle(1000);
    await dump("save-restored");
  });

  it("batch-restore", async () => {
    await measuredBoxes("batch-restore");
    engine({
      "/recipes": [],
      "POST /batches/samples": () => new Promise<never>(() => {}), // three being made first
      "POST /batches/takes": takes({
        words: [
          {
            kind: "restore",
            title: "Restore",
            detail: "Black and white and sepia coloured, faded colours brought back",
            chip: "Coloured or colours back",
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
      pick: { how: "ticked", ids: [21, 22, 23] },
      picked: {
        ...PICKED,
        pictures: [
          batchPicture(21, "Old harbour.jpg"),
          batchPicture(22, "Old meadow.jpg"),
          batchPicture(23, "Summer lake.jpg"),
        ],
      },
    });
    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Restore: colour, faded colours" })).click();
    await screen.findByRole("dialog", { name: "Restore old photos" });
    await settle(1500);
    await dump("batch-restore");
  });

  it("history-restored", async () => {
    engine({
      "/history": {
        entries: [
          entry({
            id: 3,
            madeFor: null,
            restore: "filled its scratches and dust and coloured it",
            name: "Old harbour.jpg",
            result: "D:\\Pictures\\Phone\\Old harbour (Restored).jpg",
            resultName: "Old harbour (Restored).jpg",
          }),
          entry({
            id: 2,
            madeFor: "TV 4K",
            restore: "coloured it",
            fix: "took out noise",
            name: "Old meadow.jpg",
            result: "D:\\Pictures\\Phone\\Old meadow (Coloured, Cleaned, TV 4K).jpg",
            resultName: "Old meadow (Coloured, Cleaned, TV 4K).jpg",
          }),
        ],
        older: null,
        batches: [],
        reviews: [],
      },
    });
    draw("/history", "/history", <HistoryPage />);
    await screen.findByText(/filled its scratches and dust and coloured it/);
    await settle(1500);
    await dump("history-restored");
  });
});
