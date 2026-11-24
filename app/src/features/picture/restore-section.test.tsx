import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type Fixes, type Job, type PictureDetails, type Tool } from "@/lib/engine";
import {
  FOLDERS,
  fakeEngine,
  job,
  LOOKS,
  PICTURES,
  plan,
  READY,
  SETTINGS,
  SIZES,
} from "@/test/engine";
import { PicturePage } from "./picture-page";
import { SCRATCH_STROKES } from "./restore";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const DUSK = PICTURES[0] as (typeof PICTURES)[number];

/** A made-up scan of an old print, opened from Phone. */
const details: PictureDetails = {
  ...DUSK,
  gainMap: null,
  folderId: 1,
  folder: "D:\\Pictures\\Phone",
  dir: "",
  modifiedAt: DUSK.takenAt,
  takenFrom: "camera",
  camera: null,
  orientation: 1,
  located: false,
  problem: null,
  damaged: false,
  outside: false,
  pasted: false,
  aside: false,
  savesTo: null,
};

/** What Mado measured of a black-and-white print: well exposed, saved at 92. */
const GREY: Fixes = {
  jpegQuality: 92,
  blocks: false,
  stops: 0,
  dark: false,
  grey: true,
  seeThrough: false,
  colour: "sRGB",
  megapixels: 12.2,
  colours: "grey",
  tone: null,
};

const COLOUR: Fixes = { ...GREY, grey: false, colours: "colour" };
const SEPIA: Fixes = { ...GREY, grey: false, colours: "toned", tone: "sepia" };

function model(id: string, name: string, size: number, state: Tool["state"] = "ready"): Tool {
  return {
    id,
    name,
    version: "models-3",
    purpose: "",
    licence: "MIT",
    size,
    when: "asked",
    state,
    done: 0,
    problem: null,
  };
}

const DETECTOR = model("oldphoto-scratch-detector", "Old-photo scratch detector", 75_391_673);
const LAMA = model("lama", "LaMa", 208_000_000);
const DDCOLOR = model("ddcolor-tiny", "DDColor tiny", 270_266_480);
const READY_MODELS = [DETECTOR, LAMA, DDCOLOR, model("scunet", "SCUNet", 72_932_271)];

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

/** The detector's answer: its mask, and how much of the picture it found. */
function mask(found: number) {
  return () =>
    new Response(new Blob(["mask"], { type: "image/png" }), {
      headers: { "X-Found": String(found), "X-Made-In": "0.4", "X-Place": "card" },
    });
}

type Fetch = ReturnType<typeof fakeEngine>;

function engine(answers: Record<string, unknown> = {}): Fetch {
  return fakeEngine({
    "/folders": FOLDERS,
    "/settings": SETTINGS,
    "/pictures/11": details,
    "/pictures/11/neighbours": { before: [], after: [] },
    "/pictures/11/view": blob,
    "/pictures/11/full": blob,
    "/pictures/11/thumbnail": blob,
    "/pictures/11/fixes": GREY,
    "/sizes": SIZES,
    "/looks": LOOKS,
    "POST /screens": [],
    "POST /pictures/11/plan": plan({
      width: 4032,
      height: 3024,
      label: "",
      method: "keep",
      model: null,
      restore: "coloured it",
      restoreSeconds: 2,
      restorePlace: "card",
      seconds: 3,
    }),
    "POST /pictures/11/preview": () =>
      new Response(new Blob(["preview"], { type: "image/webp" }), {
        headers: { "X-Made-In": "0.8" },
      }),
    "POST /pictures/11/scratches": mask(0.012),
    "POST /pictures/11/saving": {
      name: "Harbour at dusk (Coloured).jpg",
      folder: "D:\\Pictures\\Phone",
      taken: null,
      takenAt: null,
      bytes: 3_000_000,
      colour: "sRGB",
    },
    "/jobs": [],
    "/tools": READY_MODELS,
    "/queue/now": {
      working: false,
      paused: false,
      batch: null,
      over: 0,
      total: 0,
      progress: 0,
      waiting: 0,
    },
    ...answers,
  });
}

function renderPicture(): QueryClient {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "screens") return [{ width: 3440, height: 1440, main: true }];
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
  return queries;
}

/** A stroke of the scratches' brush across the picture's top (the stage stands 800 x 600 here). */
async function paintAStroke() {
  const picture = (await screen.findByRole("img", { name: "Harbour at dusk" }))
    .parentElement as HTMLElement;
  fireEvent.pointerDown(picture, { clientX: 80, clientY: 60, button: 0, pointerId: 1 });
  fireEvent.pointerMove(picture, { clientX: 400, clientY: 60, pointerId: 1 });
  fireEvent.pointerUp(picture, { pointerId: 1 });
}

function sent(fetch: Fetch, method: string, path: string): unknown[] {
  return fetch.mock.calls
    .filter(
      ([input, init]) =>
        (init?.method ?? "GET") === method && new URL(String(input)).pathname === path,
    )
    .map(([, init]) => JSON.parse(String(init?.body ?? "null")));
}

/** Every body sent to an address that starts so: the Looks tab's small copies. */
function sentUnder(fetch: Fetch, start: string): unknown[] {
  return fetch.mock.calls
    .filter(
      ([input, init]) =>
        init?.method === "POST" && new URL(String(input)).pathname.startsWith(start),
    )
    .map(([, init]) => JSON.parse(String(init?.body ?? "null")));
}

async function openFix() {
  fireEvent.click(await screen.findByRole("tab", { name: "Fix" }));
  return screen.findByRole("region", { name: "Restoring" });
}

class PointerEventLike extends MouseEvent {
  pointerId: number;
  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 1;
  }
}

describe("Restoring an old photo", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
    // jsdom has none: the slider measures its thumb, the stage its space (it says it once).
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private told: ResizeObserverCallback) {}
        observe(target: Element) {
          this.told(
            [{ target, contentRect: { width: 800, height: 600 } } as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          );
        }
        unobserve() {}
        disconnect() {}
      },
    );
    vi.stubGlobal("PointerEvent", PointerEventLike);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      right: 800,
      bottom: 600,
      width: 800,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    Element.prototype.setPointerCapture = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    shell.invoke.mockReset();
  });

  it("offers to colour a black-and-white photo, says the colours are a guess, and plans it first", async () => {
    const fetch = engine();
    renderPicture();
    const restoring = await openFix();

    expect(await screen.findByText("It's black and white: Mado can colour it.")).toBeVisible();
    expect(within(restoring).getByText("Suggested")).toBeVisible();
    expect(screen.getByText("It stays black and white.")).toBeVisible();

    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));

    expect(within(restoring).getByRole("radio", { name: "Colour it" })).toBeChecked();
    expect(within(restoring).getByRole("slider", { name: "How much colour" })).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
    expect(
      within(restoring).getByText(
        "The colours are guessed from what photos usually look like: a coat's colour is a guess.",
      ),
    ).toBeVisible();
    expect(screen.queryByText("It stays black and white.")).toBeNull();
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        restore: {
          version: details.version,
          scratches: null,
          colour: { strength: 1 },
          faded: null,
        },
      }),
    );
    expect(await screen.findByText(/About 5 s on your graphics card/)).toBeVisible();
    // All of it shows colouring: it's plain to see at any size.
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview")).toContainEqual(
        expect.objectContaining({
          recipe: expect.objectContaining({
            restore: expect.objectContaining({ colour: { strength: 1 } }),
          }),
        }),
      ),
    );
    expect(await screen.findByText("After · Colour")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save…" })).toBeEnabled());
  });

  it("names restoring in Save's header, made before the fixes", async () => {
    engine();
    renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save…" })).toBeEnabled());

    fireEvent.click(screen.getByRole("button", { name: "Save…" }));

    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    expect(within(dialog).getByText("Coloured it")).toBeVisible();
  });

  it("leaves the Size tab no longer saying Save keeps it as it is once restoring is on", async () => {
    engine();
    renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));
    fireEvent.click(screen.getByRole("tab", { name: "Size" }));

    expect(
      await screen.findByText("Pick a screen or a print to see the picture made for it."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Save keeps it as it is/)).toBeNull();
  });

  it("starts a colour photo on its faded colours, and says a colour photo coloured gets new ones", async () => {
    const fetch = engine({ "/pictures/11/fixes": COLOUR });
    renderPicture();
    const restoring = await openFix();

    expect(
      await screen.findByText(
        "A colour photo's faded colours brought back from the picture itself.",
      ),
    ).toBeVisible();
    expect(within(restoring).queryByText("Suggested")).toBeNull();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));

    expect(within(restoring).getByRole("radio", { name: "Bring its colours back" })).toBeChecked();
    expect(
      within(restoring).getByRole("slider", { name: "How far its colours come back" }),
    ).toBeInTheDocument();
    expect(
      within(restoring).getByText(
        "Whether its colours faded Mado can't measure: compare before and after.",
      ),
    ).toBeVisible();
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        restore: { scratches: null, colour: null, faded: { strength: 1 } },
      }),
    );

    fireEvent.click(within(restoring).getByRole("radio", { name: "Colour it" }));
    expect(
      within(restoring).getByText(
        "It's in colour already: colouring guesses new colours from its light and puts them in place of its own.",
      ),
    ).toBeVisible();
  });

  it("says a sepia print's brown is mixed in, and a print has no faded colours to bring back", async () => {
    engine({ "/pictures/11/fixes": SEPIA });
    renderPicture();
    const restoring = await openFix();

    expect(await screen.findByText("It's a sepia print: Mado can colour it.")).toBeVisible();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));
    expect(
      within(restoring).getByText(
        "A sepia print: the strength mixes the colours guessed with its brown.",
      ),
    ).toBeVisible();

    fireEvent.click(within(restoring).getByRole("radio", { name: "Bring its colours back" }));
    expect(
      within(restoring).getByText("It's a sepia print, so there are no colours to bring back."),
    ).toBeVisible();
  });

  it("shows what it found as a mask to check first, then fills it with what's painted", async () => {
    const fetch = engine();
    renderPicture();
    const restoring = await openFix();

    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/scratches")).toEqual([
        { version: details.version, edits: [] },
      ]),
    );
    expect(await screen.findByText("The mask")).toBeInTheDocument();
    expect(
      screen.getByText("Paint over what Mado missed · Alt to take away what isn't a scratch"),
    ).toBeVisible();
    expect(await within(restoring).findByText("1.2%")).toBeInTheDocument();
    expect(within(restoring).getByText(/dark scratches are the ones it misses most/)).toBeVisible();
    // Nothing is filled while the mask is checked: the previews wait.
    expect(
      sent(fetch, "POST", "/pictures/11/preview").filter(
        (each) => (each as { recipe: { restore?: unknown } }).recipe.restore,
      ),
    ).toEqual([]);

    const picture = (await screen.findByRole("img", { name: "Harbour at dusk" }))
      .parentElement as HTMLElement;
    fireEvent.pointerDown(picture, { clientX: 80, clientY: 60, button: 0, pointerId: 1 });
    fireEvent.pointerMove(picture, { clientX: 400, clientY: 60, pointerId: 1 });
    fireEvent.pointerUp(picture, { pointerId: 1 });
    fireEvent.click(within(restoring).getByRole("button", { name: "Fill them in" }));

    const stroke = {
      points: [
        [0.1, 0.1],
        [0.5, 0.1],
      ],
      size: 0.01,
      take: false,
    };
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        restore: { scratches: { strokes: [stroke] }, colour: null, faded: null },
      }),
    );
    expect(await screen.findByText("After · Scratches")).toBeInTheDocument();
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview")).toContainEqual(
        expect.objectContaining({
          recipe: expect.objectContaining({
            restore: expect.objectContaining({ scratches: { strokes: [stroke] } }),
          }),
        }),
      ),
    );
    expect(within(restoring).getByRole("button", { name: "Check the mask" })).toBeVisible();
  });

  it("says finding them waits for the graphics card while the queue has it", async () => {
    engine({
      "POST /pictures/11/scratches": () => new Promise<never>(() => {}), // waits for the card
      "/queue/now": {
        working: true,
        paused: false,
        batch: "Phone wallpapers",
        over: 12,
        total: 30,
        progress: 0.4,
        waiting: 18,
      },
    });
    renderPicture();
    const restoring = await openFix();

    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));

    expect(within(restoring).getByText("Looking for scratches and dust…")).toBeVisible();
    expect(
      await screen.findByText(
        "Waiting for the graphics card: Phone wallpapers lets it go after the tile it's on",
        {},
        { timeout: 3000 },
      ),
    ).toBeVisible();
  });

  it("keeps as many strokes as the engine takes, and says so past them", async () => {
    const fetch = engine();
    renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));
    const picture = (await screen.findByRole("img", { name: "Harbour at dusk" }))
      .parentElement as HTMLElement;

    for (let dab = 0; dab <= SCRATCH_STROKES; dab++) {
      fireEvent.pointerDown(picture, { clientX: 80, clientY: 60, button: 0, pointerId: 1 });
      fireEvent.pointerUp(picture, { pointerId: 1 });
    }

    expect(
      await screen.findByText(/That's as many strokes as Mado keeps: fill them in/),
    ).toBeVisible();
    await waitFor(() => {
      const asked = sent(fetch, "POST", "/pictures/11/plan").at(-1) as {
        restore: { scratches: { strokes: unknown[] } };
      };
      expect(asked.restore.scratches.strokes).toHaveLength(SCRATCH_STROKES);
    });
    // 513 strokes each draw the page again: about 6 s alone, 19 s beside a busy processor.
  }, 60_000);

  it("holds Save on every tab till the mask has been checked", async () => {
    engine();
    renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));

    expect(
      await screen.findByText("Save waits till you've checked the scratches' mask on the Fix tab."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();

    fireEvent.click(await within(restoring).findByRole("button", { name: "Fill them in" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Save…" })).toBeEnabled());
    expect(screen.queryByText(/Save waits till you've checked/)).toBeNull();
  });

  it("says when it found nothing, that painting fills it, and clears what was painted", async () => {
    engine({ "POST /pictures/11/scratches": mask(0) });
    renderPicture();
    const restoring = await openFix();

    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));

    expect(
      await within(restoring).findByText(
        "Mado found no scratches or dust. If you see some, paint over them on the picture: Mado fills what you paint.",
      ),
    ).toBeVisible();
    const clear = within(restoring).getByRole("button", { name: "Clear what you painted" });
    expect(clear).toBeDisabled();
    const picture = (await screen.findByRole("img", { name: "Harbour at dusk" }))
      .parentElement as HTMLElement;
    fireEvent.pointerDown(picture, { clientX: 80, clientY: 60, button: 0, pointerId: 1 });
    fireEvent.pointerUp(picture, { pointerId: 1 });
    expect(clear).toBeEnabled();
    fireEvent.click(clear);
    expect(clear).toBeDisabled();
  });

  it("says there's nothing to save when nothing was found and nothing painted", async () => {
    engine({
      "POST /pictures/11/scratches": mask(0),
      "POST /pictures/11/plan": plan({
        method: "keep",
        label: "",
        restore: null,
        restoreCovers: 0,
      }),
    });
    renderPicture();
    const restoring = await openFix();

    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));
    fireEvent.click(await within(restoring).findByRole("button", { name: "Fill them in" }));

    expect(
      await screen.findByText(
        "Nothing to save: Mado found no scratches or dust, and none was painted.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
    expect(
      await screen.findByText("Nothing changes: there are no scratches or dust to fill"),
    ).toBeInTheDocument();
  });

  it("won't fill a mask over most of the picture, and says a big one is a lot to invent", async () => {
    engine({
      "POST /pictures/11/plan": plan({
        method: "keep",
        restore: "filled its scratches and dust",
        restoreCovers: 0.6,
      }),
    });
    renderPicture();
    const restoring = await openFix();

    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));

    expect(
      await within(restoring).findByText(
        /That's most of the picture: Mado fills scratches and dust/,
      ),
    ).toBeVisible();
    expect(within(restoring).getByRole("button", { name: "Fill them in" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
    // Seen and left, the mask still covers too much: Save says so.
    fireEvent.click(screen.getByRole("tab", { name: "Looks" }));
    fireEvent.click(screen.getByRole("tab", { name: "Fix" }));
    expect(
      await screen.findByText("Save waits till the mask covers less of the picture."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
  });

  it("offers its models to download first, the rest working meanwhile", async () => {
    engine({
      "/tools": [
        { ...DETECTOR, state: "missing" },
        { ...LAMA, state: "missing" },
        { ...DDCOLOR, state: "missing" },
      ],
    });
    renderPicture();
    const restoring = await openFix();

    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));
    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));

    expect(
      within(restoring).getByText("Mado looks for them once its scratch detector is here."),
    ).toBeVisible();
    const detector = await screen.findByRole("region", {
      name: "Old-photo scratch detector to download",
    });
    expect(detector).toHaveTextContent("Scratches and dust are found");
    expect(detector).toHaveTextContent("75.4 MB");
    expect(screen.getByRole("region", { name: "LaMa to download" })).toHaveTextContent(
      "Scratches are filled",
    );
    expect(screen.getByRole("region", { name: "DDColor tiny to download" })).toHaveTextContent(
      "Black-and-white photos are coloured",
    );
    expect(
      await screen.findByText(
        "Save waits for Old-photo scratch detector and LaMa and DDColor tiny, still to download.",
      ),
    ).toBeVisible();
  });

  it("lets the strokes go when the picture changed while its mask waited, and shows it again", async () => {
    let shown = details;
    const fetch = engine({ "/pictures/11": () => shown });
    const queries = renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));
    await paintAStroke();
    fireEvent.click(within(restoring).getByRole("button", { name: "Fill them in" }));
    await within(restoring).findByRole("button", { name: "Check the mask" });

    shown = { ...details, version: "v11-changed-elsewhere" };
    await act(() => queries.invalidateQueries());

    expect(
      await screen.findByText(/changed since Mado found its scratches, so they were found again/),
    ).toBeVisible();
    expect(screen.getByText("The mask")).toBeInTheDocument();
    expect(
      within(restoring).getByRole("button", { name: "Clear what you painted" }),
    ).toBeDisabled();
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/scratches").at(-1)).toEqual({
        version: "v11-changed-elsewhere",
        edits: [],
      }),
    );
  });

  it("holds Save on another tab when the picture changed there, till its mask is checked again", async () => {
    let shown = details;
    engine({ "/pictures/11": () => shown });
    const queries = renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));
    fireEvent.click(await within(restoring).findByRole("button", { name: "Fill them in" }));
    fireEvent.click(screen.getByRole("tab", { name: "Looks" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save…" })).toBeEnabled());

    shown = { ...details, version: "v11-changed-elsewhere" };
    await act(() => queries.invalidateQueries());

    expect(
      await screen.findByText("Save waits till you've checked the scratches' mask on the Fix tab."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
    fireEvent.click(screen.getByRole("tab", { name: "Size" })); // still not checked
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
    fireEvent.click(screen.getByRole("tab", { name: "Fix" }));
    expect(await screen.findByText(/changed since Mado found its scratches/)).toBeVisible();
    expect(screen.getByText("The mask")).toBeInTheDocument();
  });

  it("lets restoring go quietly once Mado's own Save has put it in the original's place", async () => {
    let shown = details;
    let jobs: Job[] = [];
    engine({ "/pictures/11": () => shown, "/jobs": () => jobs });
    const queries = renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));
    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));
    await paintAStroke();
    fireEvent.click(within(restoring).getByRole("button", { name: "Fill them in" }));

    jobs = [
      job({
        how: "replace",
        state: "done",
        stage: null,
        progress: 1,
        madeFor: null,
        restore: "filled its scratches and dust and coloured it",
        resultName: details.name,
        finishedAt: new Date().toISOString(),
      }),
    ];
    shown = { ...details, version: "v11-saved-in-place" };
    await act(() => queries.invalidateQueries());

    await waitFor(() =>
      expect(
        within(restoring).getByRole("switch", { name: "Scratches and dust" }),
      ).not.toBeChecked(),
    );
    expect(within(restoring).getByRole("switch", { name: "Colour" })).not.toBeChecked();
    expect(screen.queryByText(/changed since Mado found its scratches/)).toBeNull();
  });

  it("lets colour go once Mado's Save put it in place, and keeps it when the file changed elsewhere", async () => {
    let shown = details;
    let jobs: Job[] = [];
    engine({ "/pictures/11": () => shown, "/jobs": () => jobs });
    const queries = renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));

    // Changed elsewhere: colour goes by the picture as it is, so it stays, and nothing is said.
    shown = { ...details, version: "v11-changed-elsewhere" };
    await act(() => queries.invalidateQueries());
    await screen.findByText("After · Colour");
    expect(within(restoring).getByRole("switch", { name: "Colour" })).toBeChecked();
    expect(screen.queryByText(/changed since/)).toBeNull();

    // Saved in its place: the colour is in it now, so colouring it again would guess anew.
    jobs = [
      job({
        how: "replace",
        state: "done",
        stage: null,
        progress: 1,
        madeFor: null,
        restore: "coloured it",
        resultName: details.name,
        finishedAt: new Date().toISOString(),
      }),
    ];
    shown = { ...details, version: "v11-saved-in-place" };
    await act(() => queries.invalidateQueries());
    await waitFor(() =>
      expect(within(restoring).getByRole("switch", { name: "Colour" })).not.toBeChecked(),
    );
  });

  it("asks for a smaller copy of a scan too big to restore", async () => {
    engine({ "/pictures/11": { ...details, width: 12_000, height: 9_000 } });
    renderPicture();
    fireEvent.click(await screen.findByRole("tab", { name: "Fix" }));

    expect(
      await screen.findByText(
        "It's 108 megapixels, and Mado restores pictures up to 100. Make a smaller copy of it on the Size tab, then restore that.",
      ),
    ).toBeVisible();
    expect(screen.queryByRole("region", { name: "Restoring" })).toBeNull();
    const card = screen.getByRole("region", { name: "Too big to restore" });

    fireEvent.click(within(card).getByRole("button", { name: "Go to the Size tab" }));

    expect(await screen.findByRole("tab", { name: "Size", selected: true })).toBeInTheDocument();
  });

  it("shows the picture restored on the other tabs and in the small copies, leaving the mask's check", async () => {
    const fetch = engine();
    renderPicture();
    const restoring = await openFix();
    fireEvent.click(within(restoring).getByRole("switch", { name: "Colour" }));
    fireEvent.click(within(restoring).getByRole("switch", { name: "Scratches and dust" }));
    expect(await screen.findByText("The mask")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Looks" }));

    await waitFor(() =>
      expect(sentUnder(fetch, "/pictures/11/looks/")).toContainEqual(
        expect.objectContaining({
          restore: expect.objectContaining({
            scratches: { strokes: [] },
            colour: { strength: 1 },
          }),
        }),
      ),
    );
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview")).toContainEqual(
        expect.objectContaining({
          recipe: expect.objectContaining({
            restore: expect.objectContaining({ scratches: { strokes: [] } }),
          }),
        }),
      ),
    );

    // Back on the Fix tab, the picture is shown filled, the mask a click away.
    fireEvent.click(screen.getByRole("tab", { name: "Fix" }));
    expect(
      await within(await screen.findByRole("region", { name: "Restoring" })).findByRole("button", {
        name: "Check the mask",
      }),
    ).toBeVisible();
    expect(screen.queryByText("The mask")).toBeNull();
  });
});
