import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  EngineProvider,
  type Fixes,
  type PictureDetails,
  type Recipe,
  type YourStyle,
} from "@/lib/engine";
import {
  FOLDERS,
  fakeEngine,
  LOOKS,
  PICTURES,
  plan,
  READY,
  SETTINGS,
  SIZES,
  STYLES,
  styleTool,
} from "@/test/engine";
import { PicturePage } from "./picture-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const DUSK = PICTURES[0] as (typeof PICTURES)[number];

const details: PictureDetails = {
  ...DUSK,
  folderId: 1,
  folder: "D:\\Pictures\\Phone",
  dir: "",
  modifiedAt: DUSK.takenAt,
  takenFrom: "camera",
  camera: "Testcam T7 Pro",
  orientation: 1,
  located: true,
  problem: null,
  damaged: false,
  outside: false,
  pasted: false,
  aside: false,
  savesTo: null,
};

/** A colour photo, nothing to fix. */
const FINE: Fixes = {
  jpegQuality: 92,
  blocks: false,
  stops: 0,
  dark: false,
  grey: false,
  seeThrough: false,
  colour: "sRGB",
  megapixels: 12.2,
};

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));
const STYLE_IDS = [...STYLES.painters, ...STYLES.classics, ...STYLES.yours].map((each) => each.id);
const copies = Object.fromEntries([
  ...LOOKS.looks.map((look) => [`/pictures/11/looks/${look.id}`, blob]),
  ...STYLE_IDS.map((id) => [`/pictures/11/styles/${id}`, blob]),
  ["/pictures/11/thumbnail", blob],
  ["/styles/yours-1/thumbnail", blob],
]);
/** Every style's network downloaded, and MicroAST. */
const NETWORKS = [
  ...STYLES.painters.map((style) => styleTool(style.download ?? "", style.name)),
  styleTool("microast", "MicroAST"),
];
const IDLE = { working: false, batch: null, over: 0, total: 0, waiting: 0, paused: false };

type Fetch = ReturnType<typeof fakeEngine>;

/** The plan for what's asked: the picture's own pixels, its style painted on the card. */
function planned(init: RequestInit | undefined) {
  const recipe = JSON.parse(String(init?.body)) as Recipe;
  return plan({
    width: 4032,
    height: 3024,
    label: "",
    shape: "crop",
    sides: "none",
    kept: { x: 0, y: 0, width: 1, height: 1 },
    canvas: { x: 0, y: 0, width: 1, height: 1 },
    method: "keep",
    model: null,
    how: "",
    note: "",
    look: recipe.paint ? recipe.paint.style : null,
    paintPlace: recipe.paint ? "card" : null,
    seconds: 1.4,
  });
}

/** Harbour at dusk opened from Phone, with the Looks tab's answers and its styles'. */
function engine(answers: Record<string, unknown> = {}): Fetch {
  return fakeEngine({
    "/folders": FOLDERS,
    "/settings": SETTINGS,
    "/pictures/11": details,
    "/pictures/11/neighbours": { before: [], after: [] },
    "/pictures/11/view": blob,
    "/pictures/11/fixes": FINE,
    "/sizes": SIZES,
    "POST /screens": [],
    "/looks": LOOKS,
    "/styles": STYLES,
    ...copies,
    "POST /pictures/11/plan": planned,
    "POST /pictures/11/preview": () =>
      new Response(new Blob(["preview"], { type: "image/webp" }), {
        headers: { "X-Made-In": "0.1" },
      }),
    "/jobs": [],
    "/tools": NETWORKS,
    "/queue/now": IDLE,
    ...answers,
  });
}

function renderLooks() {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "screens") return [];
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/library/pictures/11?folder=1"]}>
          <Routes>
            <Route path="/library/pictures/:id" element={<PicturePage />} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function sent(fetch: Fetch, method: string, path: string): unknown[] {
  return fetch.mock.calls
    .filter(
      ([input, init]) =>
        (init?.method ?? "GET") === method && new URL(String(input)).pathname === path,
    )
    .map(([, init]) => JSON.parse(String(init?.body ?? "null")));
}

async function openStyles() {
  fireEvent.click(await screen.findByRole("tab", { name: "Looks" }));
  return screen.findByRole("radiogroup", { name: "Painting styles" });
}

/** What the words over the picture say: the look and style shown on it. */
async function onStage(words: string) {
  const tools = screen.getByRole("complementary", { name: "Tools" });
  await waitFor(() =>
    expect(screen.getAllByText(words).filter((each) => !tools.contains(each))).toHaveLength(1),
  );
}

/** An answer that never comes: what's asked for stays on its way. */
const never = () => new Response(new ReadableStream({ start() {} }));

describe("Painting styles", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
    // jsdom has neither: the slider measures its thumb, the stage its space (it says it once).
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private told: ResizeObserverCallback) {}
        observe(target: Element) {
          this.told(
            [{ target, contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          );
        }
        unobserve() {}
        disconnect() {}
      },
    );
    Element.prototype.setPointerCapture = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists the styles as small copies of this picture, a group of their own beside the looks", async () => {
    const fetch = engine();
    renderLooks();

    const grid = await openStyles();

    expect(
      within(grid)
        .getAllByRole("radio")
        .map((tile) => tile.textContent),
    ).toEqual([
      "None",
      "After Van Gogh",
      "After Hokusai",
      "After Monet",
      "After Seurat",
      "Pencil sketch",
      "Coloured pencil",
      "Oil paint",
      "Cartoon",
      "Lantern glow",
    ]);
    expect(within(grid).getByRole("radio", { name: "None" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    // Each small copy's address carries the picture's version, so a changed picture is asked again.
    await waitFor(() =>
      expect(fetch.mock.calls.map(([input]) => String(input))).toContain(
        "http://127.0.0.1:5000/pictures/11/styles/monet?v=v11",
      ),
    );
    expect(screen.getByRole("heading", { name: "Painting styles" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "A picture of yours…" })).toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: "Style strength" })).toBeNull();
    expect(
      screen.getByText("Every look and style is shown on this picture as you go through them"),
    ).toBeInTheDocument();
  });

  it("paints the picture in the style picked, at its strength, in its own colours when asked, and saves it so", async () => {
    const fetch = engine();
    renderLooks();
    const grid = await openStyles();

    fireEvent.click(within(grid).getByRole("radio", { name: "After Monet" }));

    expect(within(grid).getByRole("radio", { name: "After Monet" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview").at(-1)).toMatchObject({
        recipe: {
          paint: { style: "monet", strength: 1, colours: false, setting: null },
          look: null,
        },
        side: "after",
      }),
    );
    await onStage("After Monet · 100%");
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        paint: { style: "monet", strength: 1, colours: false, setting: null },
      }),
    );
    expect(await screen.findByRole("button", { name: "Save…" })).toBeEnabled();

    const strength = screen.getByRole("slider", { name: "Style strength" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.click(screen.getByRole("switch", { name: "Keep the picture's colours" }));

    await onStage("After Monet · 80%");
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        paint: { style: "monet", strength: 0.8, colours: true },
      }),
    );
  });

  it("puts a look and touches on top of a style: the style first, then the look", async () => {
    const fetch = engine();
    renderLooks();
    const grid = await openStyles();

    fireEvent.click(within(grid).getByRole("radio", { name: "After Hokusai" }));
    const looks = screen.getByRole("radiogroup", { name: "Looks" });
    fireEvent.click(within(looks).getByRole("radio", { name: "Warm film" }));
    fireEvent.click(screen.getByRole("button", { name: "Grain" }));

    await onStage("After Hokusai · 100% · Warm film · 100% · grain");
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        paint: { style: "hokusai", strength: 1 },
        look: { look: "warm-film", touches: { grain: 20 } },
      }),
    );
  });

  it("gives a classic one its one setting, and no colours to keep: they're its own", async () => {
    const fetch = engine();
    renderLooks();
    const grid = await openStyles();

    fireEvent.click(within(grid).getByRole("radio", { name: "Oil paint" }));

    const brush = screen.getByRole("slider", { name: "Brush" });
    expect(brush).toHaveAttribute("aria-valuenow", "50");
    expect(screen.queryByRole("switch", { name: "Keep the picture's colours" })).toBeNull();
    fireEvent.keyDown(brush, { key: "PageUp" });
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        paint: { style: "oil", setting: 60 },
      }),
    );
    await onStage("Oil paint · 100%");
  });

  it("shows a style on the picture while the pointer rests on it, without planning it", async () => {
    const fetch = engine();
    renderLooks();
    const grid = await openStyles();

    fireEvent.pointerEnter(within(grid).getByRole("radio", { name: "After Seurat" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview").at(-1)).toMatchObject({
        recipe: { paint: { style: "seurat" } },
      }),
    );
    await onStage("After Seurat · 100%");
    expect(sent(fetch, "POST", "/pictures/11/plan")).toHaveLength(0);
    fireEvent.pointerLeave(grid);
    await onStage("Original");
  });

  it("downloads a style's network the first time it's asked for, saying its size and how far it's got", async () => {
    let state: "missing" | "downloading" = "missing";
    const fetch = engine({
      "/tools": () => [
        styleTool("style-van-gogh-starry-night", "After Van Gogh", state),
        ...NETWORKS.slice(1),
      ],
      "POST /tools/style-van-gogh-starry-night/download": () => {
        state = "downloading";
        return styleTool("style-van-gogh-starry-night", "After Van Gogh", "downloading");
      },
    });
    renderLooks();
    const grid = await openStyles();
    const tile = await within(grid).findByRole("radio", {
      name: "After Van Gogh, 6.9 MB to download",
    });
    // Its small copy waits for it too: the picture as it is, meanwhile.
    expect(sent(fetch, "GET", "/pictures/11/styles/van-gogh")).toHaveLength(0);
    fireEvent.pointerEnter(tile);
    expect(sent(fetch, "POST", "/pictures/11/preview")).toHaveLength(0);

    fireEvent.click(tile);

    const card = await screen.findByRole("region", { name: "After Van Gogh to download" });
    expect(card).toHaveTextContent(
      "After Van Gogh paints with a small AI model Mado downloads the first time it's asked for (6.9 MB). It stays on this PC.",
    );
    expect(
      screen.getByText("The style shows once After Van Gogh is downloaded, under Painting styles"),
    ).toBeInTheDocument();
    expect(sent(fetch, "POST", "/pictures/11/preview")).toHaveLength(0);
    fireEvent.click(within(card).getByRole("button", { name: "Download After Van Gogh" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/tools/style-van-gogh-starry-night/download")).toHaveLength(1),
    );
    expect(
      await within(card).findByRole("progressbar", { name: "Downloading After Van Gogh" }),
    ).toBeInTheDocument();
    // Its tile says how far it's got too.
    expect(
      within(grid).getByRole("radio", { name: "After Van Gogh, downloading, 0%" }),
    ).toBeInTheDocument();
  });

  it("takes a picture's style from its colours and textures, and keeps it as a style, never the picture", async () => {
    const kept: YourStyle[] = [];
    const lantern = STYLES.yours[0] as YourStyle;
    const fetch = engine({
      "/styles": () => ({ ...STYLES, yours: [lantern, ...kept] }),
      "POST /pictures/11/style": { code: "c3R5bGU=", named: "Harbour at dusk", version: "v11" },
      "POST /pictures/11/styles/picture": blob,
      "POST /pictures/11/styles/yours-2": blob,
      "/pictures/11/styles/yours-2": blob,
      "/styles/yours-2/thumbnail": blob,
      "POST /styles": () => {
        const mine: YourStyle = {
          id: "yours-2",
          name: "Dusk harbour",
          source: "Harbour at dusk.jpg",
          addedAt: "2026-11-24T10:00:00+02:00",
        };
        kept.push(mine);
        return Response.json(mine, { status: 201 });
      },
    });
    renderLooks();
    await openStyles();

    fireEvent.click(screen.getByRole("button", { name: "A picture of yours…" }));
    const card = await screen.findByRole("dialog", { name: "A picture as the style" });
    expect(card).toHaveTextContent(
      "Mado takes a picture's colours and textures, never what it shows",
    );
    fireEvent.click(within(card).getByRole("button", { name: "Use this picture" }));

    const grid = await screen.findByRole("radiogroup", { name: "Painting styles" });
    expect(
      await within(grid).findByRole("radio", { name: "Harbour at dusk style" }),
    ).toHaveAttribute("aria-checked", "true");
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        paint: { style: "picture", code: "c3R5bGU=", named: "Harbour at dusk" },
      }),
    );
    await onStage("Harbour at dusk style · 100%");
    expect(
      screen.getByText("From Harbour at dusk's colours and textures, never what it shows."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Keep as a style" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Its name" }), {
      target: { value: "Dusk harbour" },
    });
    expect(
      screen.getByText(
        "Mado keeps its style and a small copy to know it by, never the picture itself.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/styles")).toEqual([
        { name: "Dusk harbour", code: "c3R5bGU=", picture: 11 },
      ]),
    );
    expect(await within(grid).findByRole("radio", { name: "Dusk harbour" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        paint: { style: "yours-2", strength: 1 },
      }),
    );
  });

  it("offers the name of the picture read last to keep, not the one before", async () => {
    const names = ["Harbour at dusk", "Night market"];
    engine({
      "POST /pictures/11/style": () => ({
        code: "c3R5bGU=",
        named: names.shift() ?? "Night market",
        version: "v11",
      }),
      "POST /pictures/11/styles/picture": blob,
    });
    renderLooks();
    await openStyles();
    for (const named of ["Harbour at dusk", "Night market"]) {
      fireEvent.click(screen.getByRole("button", { name: "A picture of yours…" }));
      const card = await screen.findByRole("dialog", { name: "A picture as the style" });
      fireEvent.click(within(card).getByRole("button", { name: "Use this picture" }));
      await screen.findByRole("radio", { name: `${named} style` });
      if (named === "Harbour at dusk")
        fireEvent.click(screen.getByRole("button", { name: "Keep as a style" }));
    }

    fireEvent.click(await screen.findByRole("button", { name: "Keep as a style" }));

    expect(screen.getByRole("textbox", { name: "Its name" })).toHaveValue("Night market");
  });

  it("says plainly why a picture won't do as a style", async () => {
    engine({
      "POST /pictures/11/style": () =>
        Response.json(
          {
            detail:
              "Harbour at dusk.jpg is nearly one colour, so there's little style in it to take. Pick a picture with more colour and texture.",
          },
          { status: 422 },
        ),
    });
    renderLooks();
    await openStyles();
    fireEvent.click(screen.getByRole("button", { name: "A picture of yours…" }));
    const card = await screen.findByRole("dialog", { name: "A picture as the style" });

    fireEvent.click(within(card).getByRole("button", { name: "Use this picture" }));

    expect(await within(card).findByRole("alert")).toHaveTextContent(
      "Harbour at dusk.jpg is nearly one colour, so there's little style in it to take.",
    );
  });

  it("waits for MicroAST, downloaded the first time, to read a picture's style or paint with yours", async () => {
    const fetch = engine({
      "/tools": [...NETWORKS.slice(0, 4), styleTool("microast", "MicroAST", "missing")],
    });
    renderLooks();
    const grid = await openStyles();
    expect(
      await within(grid).findByRole("radio", { name: "Lantern glow, 6.9 MB to download" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "A picture of yours…" }));

    const card = await screen.findByRole("dialog", { name: "A picture as the style" });
    expect(within(card).getByText(/Reading a picture's style takes MicroAST/)).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Use this picture" })).toBeNull();
    fireEvent.click(within(card).getByRole("button", { name: "Download MicroAST" }));
    await waitFor(() => expect(sent(fetch, "POST", "/tools/microast/download")).toHaveLength(1));
  });

  it("says where one of yours came from, renames it, and deletes it after asking", async () => {
    const fetch = engine({
      "PUT /styles/yours-1": { ...STYLES.yours[0], name: "Lanterns" },
      "DELETE /styles/yours-1": null,
    });
    renderLooks();
    const grid = await openStyles();
    fireEvent.click(within(grid).getByRole("radio", { name: "Lantern glow" }));
    expect(screen.getByText("From Night market.jpg")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    fireEvent.change(screen.getByRole("textbox", { name: "A new name for Lantern glow" }), {
      target: { value: "Lanterns" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    await waitFor(() =>
      expect(sent(fetch, "PUT", "/styles/yours-1")).toEqual([{ name: "Lanterns" }]),
    );

    fireEvent.click(await screen.findByRole("button", { name: "Delete…" }));
    const asking = await screen.findByRole("dialog", { name: "Delete Lantern glow?" });
    expect(asking).toHaveTextContent("Pictures you painted with it stay as they are.");
    fireEvent.click(within(asking).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(sent(fetch, "DELETE", "/styles/yours-1")).toHaveLength(1));
    await waitFor(() =>
      expect(within(grid).getByRole("radio", { name: "None" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
  });

  it("says a black and white picture is painted in the style's colours unless its own are kept", async () => {
    const fetch = engine({ "/pictures/11/fixes": { ...FINE, grey: true } });
    renderLooks();
    const grid = await openStyles();
    // Mado measures the picture only once a style is chosen: the Looks tab alone reads no more
    // than its thumbnail and view.
    expect(sent(fetch, "GET", "/pictures/11/fixes")).toHaveLength(0);

    fireEvent.click(within(grid).getByRole("radio", { name: "After Hokusai" }));

    expect(await screen.findByText(/This picture is black and white/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "Keep the picture's colours" }));
    expect(screen.queryByText(/This picture is black and white/)).toBeNull();
  });

  it("says when a style is painted far smaller than the picture it makes, and on the processor", async () => {
    const note =
      "Painted at 1392 × 783, then made 7680 × 4320: about 6 times bigger, so seen close its strokes are soft. A smaller size on the Size tab keeps them crisp.";
    engine({
      "POST /pictures/11/plan": (init: RequestInit | undefined) => ({
        ...planned(init),
        paintNote: note,
        paintPlace: "processor",
      }),
    });
    renderLooks();
    const grid = await openStyles();

    fireEvent.click(within(grid).getByRole("radio", { name: "After Seurat" }));

    expect(await screen.findByText(note)).toBeInTheDocument();
    expect(
      screen.getByText(
        "Painted on the processor on this PC: each style takes a few seconds to show.",
      ),
    ).toBeInTheDocument();
  });

  it("says when the style waits for the graphics card while the queue has it", async () => {
    engine({
      "/queue/now": {
        working: true,
        batch: "Holiday prints",
        over: 3,
        total: 40,
        waiting: 37,
        paused: false,
      },
      "POST /pictures/11/preview": never,
    });
    renderLooks();
    const grid = await openStyles();

    fireEvent.click(within(grid).getByRole("radio", { name: "After Monet" }));

    expect(
      await screen.findByText(
        "Waiting for the graphics card: Holiday prints lets it go after the tile it's on",
        {},
        { timeout: 3000 },
      ),
    ).toBeInTheDocument();
  });
});
