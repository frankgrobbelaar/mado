import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  EngineProvider,
  type Job,
  type PictureDetails,
  type Recipe,
  type Selection,
  type Tool,
} from "@/lib/engine";
import {
  FOLDERS,
  fakeEngine,
  job,
  LOOKS,
  PC,
  PICTURES,
  plan,
  READY,
  SETTINGS,
  SIZES,
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
  camera: "Pixelworks PW-7 Pro",
  orientation: 1,
  located: true,
  problem: null,
  damaged: false,
};

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

/** A model Mado downloads, as /tools lists it. */
function model(id: string, name: string, size: number, state: Tool["state"] = "ready"): Tool {
  return {
    id,
    name,
    version: "models-2",
    purpose: "",
    licence: "Apache-2.0",
    size,
    when: "asked",
    state,
    done: state === "downloading" ? size / 4 : 0,
    problem: null,
  };
}

const MODELS: Tool[] = [
  model("lama", "LaMa", 209_176_178),
  model("sam2.1-hiera-tiny", "SAM 2.1", 155_621_781),
  model("mi-gan", "MI-GAN", 28_081_346),
  model("birefnet-lite", "BiRefNet lite", 224_006_154),
];

/** SAM's answer, as the stand-in engine gives it: a part for each click that keeps, read in
 * 0.9 s the first time. */
function picked(init: RequestInit | undefined): Selection {
  const body = JSON.parse(String(init?.body)) as {
    parts: { clicks: { x: number; y: number; keep: boolean }[]; choice: number | null }[];
    click: { x: number; y: number; keep: boolean } | null;
  };
  const parts = body.parts.map((part) => ({ ...part }));
  if (body.click?.keep) parts.push({ clicks: [body.click], choice: null });
  else if (body.click && parts.length) parts.at(-1)?.clicks.push(body.click);
  return {
    parts: parts.map((part, at) => ({
      name: `Part ${at + 1}`,
      clicks: part.clicks,
      choice: part.choice ?? 1,
      choices: 3,
    })),
    outline: parts.length ? "M600 400L700 400L700 500L600 500Z" : "",
    read: body.parts.length === 0 && body.click?.keep ? 0.9 : null,
    place: "card",
    seconds: 0.05,
    waited: 0,
    missed: false,
  };
}

/** The plan for what's asked: the edits said, a cut-out with nothing behind it as PNG. */
function planned(init: RequestInit | undefined) {
  const recipe = JSON.parse(String(init?.body)) as Recipe;
  const edits = recipe.edit?.edits ?? [];
  const subject = edits.some((edit) => edit.kind === "subject" && edit.behind === "nothing");
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
    look: recipe.look ? "Warm film on a part" : null,
    edit: edits.length ? (subject ? "cut out the subject" : "erased a part") : null,
    format: subject ? "PNG" : "JPEG",
    formatQuality: subject ? null : 92,
    seeThrough: subject,
    nothingBehind: subject,
    seconds: 0.4,
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
    "/pictures/11/thumbnail": blob,
    "/sizes": SIZES,
    "POST /screens": [],
    "/looks": LOOKS,
    ...Object.fromEntries(LOOKS.looks.map((look) => [`/pictures/11/looks/${look.id}`, blob])),
    ...Object.fromEntries(LOOKS.looks.map((look) => [`POST /pictures/11/looks/${look.id}`, blob])),
    "POST /pictures/11/plan": planned,
    "POST /pictures/11/preview": () =>
      new Response(new Blob(["preview"], { type: "image/webp" }), {
        headers: { "X-Made-In": "0.1" },
      }),
    "POST /pictures/11/select": picked,
    "POST /pictures/11/edit": { seconds: 0.2, place: "card", waited: 0, smeared: false },
    "POST /pictures/11/saving": {
      name: "Harbour at dusk (Cut out).png",
      folder: "D:\\Pictures\\Phone",
      taken: null,
      takenAt: null,
      bytes: 9_000_000,
      colour: "Display P3",
    },
    "/jobs": [],
    "/tools": MODELS,
    "/pc": PC,
    "/queue/now": { working: false, batch: null, over: 0, total: 0, waiting: 0, paused: false },
    ...answers,
  });
}

/** An erase of the part picked at the middle of the picture, as the tab sends it. */
const ERASE = {
  kind: "erase",
  parts: [{ clicks: [{ x: 0.5, y: 0.5, keep: true }], choice: 1 }],
  strokes: [],
  quality: "fast",
};

function renderPage(): QueryClient {
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
  return queries;
}

function sent(fetch: Fetch, method: string, path: string): unknown[] {
  return fetch.mock.calls
    .filter(
      ([input, init]) =>
        (init?.method ?? "GET") === method && new URL(String(input)).pathname === path,
    )
    .map(([, init]) => JSON.parse(String(init?.body ?? "null")));
}

async function openEdit() {
  fireEvent.click(await screen.findByRole("tab", { name: "Edit" }));
  return screen.findByRole("radiogroup", { name: "Edit tool" });
}

/** The picture on the stage, where clicks and the brush go. */
async function thePicture(): Promise<HTMLElement> {
  const shown = await screen.findByRole("img", { name: "Harbour at dusk" });
  return shown.parentElement as HTMLElement;
}

/** A click on the picture at fractions of it (the stage stands 800 × 600 here). */
function clickAt(picture: HTMLElement, x: number, y: number, alt = false) {
  fireEvent.pointerDown(picture, {
    clientX: x * 800,
    clientY: y * 600,
    button: 0,
    altKey: alt,
    pointerId: 1,
  });
}

class PointerEventLike extends MouseEvent {
  pointerId: number;
  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 1;
  }
}

describe("The Edit tab", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
    vi.stubGlobal("PointerEvent", PointerEventLike);
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

  it("offers SAM 2.1 to download first, saying its size, before a part can be picked", async () => {
    const fetch = engine({
      "/tools": [model("sam2.1-hiera-tiny", "SAM 2.1", 155_621_781, "missing")],
      "POST /tools/sam2.1-hiera-tiny/download": model(
        "sam2.1-hiera-tiny",
        "SAM 2.1",
        155_621_781,
        "downloading",
      ),
    });
    renderPage();
    await openEdit();

    const card = await screen.findByRole("region", { name: "SAM 2.1 to download" });
    expect(card).toHaveTextContent("Select picks a part with a click with SAM 2.1");
    expect(card).toHaveTextContent("156 MB");
    fireEvent.click(within(card).getByRole("button", { name: "Download SAM 2.1" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/tools/sam2.1-hiera-tiny/download")).toHaveLength(1),
    );
  });

  it("picks a part with a click, names it plainly and says how long the picture took to read", async () => {
    const fetch = engine();
    renderPage();
    await openEdit();
    expect(screen.getByText("Nothing picked yet: click the picture to pick a part.")).toBeVisible();

    clickAt(await thePicture(), 0.5, 0.5);

    expect(await screen.findByText("Part 1 · picked with one click")).toBeInTheDocument();
    expect(sent(fetch, "POST", "/pictures/11/select")[0]).toEqual({
      version: details.version,
      edits: [],
      parts: [],
      click: { x: 0.5, y: 0.5, keep: true },
    });
    const tools = screen.getByRole("complementary", { name: "Tools" });
    expect(within(tools).getByText("Part 1")).toBeInTheDocument();
    expect(within(tools).queryByText(/boat|sky|person/i)).toBeNull(); // never a guessed name
    expect(screen.getByText(/Mado read the picture in/)).toHaveTextContent(
      "Mado read the picture in 0.9 s; every click after that is instant",
    );
    expect(
      screen.getByText("Click to add · Alt-click to take away · Esc to start again"),
    ).toBeVisible();
  });

  it("an Alt-click takes away, Bigger steps the last part's answer, and Esc lets go", async () => {
    const fetch = engine();
    renderPage();
    await openEdit();
    const picture = await thePicture();
    clickAt(picture, 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");

    clickAt(picture, 0.52, 0.5, true);
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/select")).toHaveLength(2));
    expect(sent(fetch, "POST", "/pictures/11/select")[1]).toMatchObject({
      click: { x: 0.52, y: 0.5, keep: false },
    });
    await screen.findByText("Part 1 · picked with 2 clicks");
    fireEvent.click(screen.getByRole("button", { name: "Bigger" }));
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/select")).toHaveLength(3));
    expect(sent(fetch, "POST", "/pictures/11/select")[2]).toMatchObject({
      parts: [{ choice: 2 }],
      click: null,
    });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(
      await screen.findByText("Nothing picked yet: click the picture to pick a part."),
    ).toBeVisible();
  });

  it("erases what's picked as a step of the recipe Save makes, and undo takes it back", async () => {
    const fetch = engine();
    renderPage();
    await openEdit();
    clickAt(await thePicture(), 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Erase" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/edit")).toHaveLength(1));
    const erase = {
      kind: "erase",
      parts: [{ clicks: [{ x: 0.5, y: 0.5, keep: true }], choice: 1 }],
      strokes: [],
      quality: "fast",
    };
    expect(sent(fetch, "POST", "/pictures/11/edit")[0]).toEqual({
      version: details.version,
      edits: [erase],
    });
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toEqual({
        edit: { version: details.version, edits: [erase] },
        size: null,
        look: null,
      }),
    );
    expect(await screen.findByRole("button", { name: "Save…" })).toBeEnabled();
    expect(screen.queryByText("Part 1")).toBeNull(); // what was picked went into the erase
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled());
  });

  it("offers Best when an erase came out smooth where the picture round it has detail", async () => {
    const fetch = engine({
      "POST /pictures/11/edit": { seconds: 0.2, place: "card", waited: 0, smeared: true },
    });
    renderPage();
    await openEdit();
    clickAt(await thePicture(), 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    fireEvent.click(screen.getByRole("button", { name: "Erase" }));

    fireEvent.click(await screen.findByRole("button", { name: "Try Best" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/edit")).toHaveLength(2));
    const again = sent(fetch, "POST", "/pictures/11/edit")[1] as { edits: { quality: string }[] };
    expect(again.edits).toHaveLength(1); // the erase made again at Best, not a second one
    expect(again.edits[0]?.quality).toBe("best");
  });

  it("the brush paints what clicking can't pick, Alt takes away, and Erase erases it", async () => {
    const fetch = engine();
    renderPage();
    const tools = await openEdit();
    fireEvent.click(within(tools).getByRole("radio", { name: "Erase" }));
    const picture = await thePicture();

    fireEvent.pointerDown(picture, { clientX: 80, clientY: 60, button: 0, pointerId: 1 });
    fireEvent.pointerMove(picture, { clientX: 400, clientY: 60, pointerId: 1 });
    fireEvent.pointerUp(picture, { pointerId: 1 });
    fireEvent.pointerDown(picture, {
      clientX: 240,
      clientY: 60,
      button: 0,
      altKey: true,
      pointerId: 1,
    });
    fireEvent.pointerUp(picture, { pointerId: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Erase" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/edit")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/11/edit")[0]).toMatchObject({
      edits: [
        {
          kind: "erase",
          parts: [],
          strokes: [
            {
              points: [
                [0.1, 0.1],
                [0.5, 0.1],
              ],
              size: 0.04,
              take: false,
            },
            { points: [[0.3, 0.1]], size: 0.04, take: true },
          ],
        },
      ],
    });
  });

  it("cuts out the subject without a click, and a cut-out with nothing behind saves as PNG or WebP", async () => {
    const fetch = engine();
    renderPage();
    const tools = await openEdit();
    fireEvent.click(within(tools).getByRole("radio", { name: "Cut out" }));

    fireEvent.click(screen.getByRole("button", { name: "Cut out the subject" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/edit")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/11/edit")[0]).toMatchObject({
      edits: [{ kind: "subject", quality: "fast", behind: "nothing", colour: null }],
    });
    fireEvent.click(await screen.findByRole("button", { name: "Save…" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("radio", { name: "PNG" })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: "WebP" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("radio", { name: "JPEG" })).toBeNull();
    expect(within(dialog).queryByRole("radio", { name: "AVIF" })).toBeNull();
    expect(dialog).toHaveTextContent("Cut out the subject");
  });

  it("gives what's picked a look: the Looks tab opens with Only on a part set to it", async () => {
    const fetch = engine();
    renderPage();
    await openEdit();
    clickAt(await thePicture(), 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");

    fireEvent.click(screen.getByRole("button", { name: "Looks" }));

    expect(await screen.findByRole("tab", { name: "Looks", selected: true })).toBeInTheDocument();
    const part = await screen.findByRole("region", { name: "Only on a part" });
    expect(within(part).getByText("Part 1")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("radio", { name: "Warm film" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        // The parts are tied to the picture as it is, as edits are.
        edit: { version: details.version, edits: [] },
        look: {
          look: "warm-film",
          parts: [{ clicks: [{ x: 0.5, y: 0.5, keep: true }], choice: 1 }],
        },
      }),
    );
    fireEvent.click(within(part).getByRole("button", { name: "Whole picture" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        look: { look: "warm-film" },
      }),
    );
    const whole = sent(fetch, "POST", "/pictures/11/plan").at(-1) as {
      edit: unknown;
      look: object;
    };
    expect(whole.look).not.toHaveProperty("parts");
    expect(whole.edit).toBeNull();
  });

  it("says when the picture changed since Mado read it, letting the picks go", async () => {
    engine({
      "POST /pictures/11/select": () =>
        new Response(
          JSON.stringify({
            detail:
              "Harbour at dusk.heic changed since Mado read it, so the parts you picked may not be where they were. Your edits were let go; start again with it as it is now.",
          }),
          { status: 409 },
        ),
    });
    renderPage();
    await openEdit();

    clickAt(await thePicture(), 0.5, 0.5);

    expect(await screen.findAllByText(/changed since Mado read it/)).not.toHaveLength(0);
  });

  it("lets the edits go quietly once Mado's own Save has put them in the original's place", async () => {
    let shown = details;
    let jobs: Job[] = [];
    engine({ "/pictures/11": () => shown, "/jobs": () => jobs });
    const queries = renderPage();
    await openEdit();
    clickAt(await thePicture(), 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    fireEvent.click(screen.getByRole("button", { name: "Erase" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());

    jobs = [
      job({
        how: "replace",
        state: "done",
        stage: null,
        progress: 1,
        madeFor: null,
        edit: "erased a part",
        resultName: details.name,
        finishedAt: new Date().toISOString(),
      }),
    ];
    shown = { ...details, version: "v11-saved-in-place" };
    await act(() => queries.invalidateQueries());

    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled());
    expect(screen.queryByText(/changed since Mado read it/)).toBeNull();
  });

  it("still says so when the picture changed outside Mado after an older Save in its place", async () => {
    let shown = details;
    const hourAgo = new Date(Date.now() - 3_600_000).toISOString();
    const older = job({
      how: "replace",
      state: "done",
      stage: null,
      progress: 1,
      madeFor: null,
      resultName: details.name,
      queuedAt: hourAgo,
      startedAt: hourAgo,
      finishedAt: hourAgo,
    });
    engine({ "/pictures/11": () => shown, "/jobs": [older] });
    const queries = renderPage();
    await openEdit();
    clickAt(await thePicture(), 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    fireEvent.click(screen.getByRole("button", { name: "Erase" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());

    shown = { ...details, version: "v11-changed-elsewhere" };
    await act(() => queries.invalidateQueries());

    expect(await screen.findAllByText(/changed since Mado read it/)).not.toHaveLength(0);
  });

  it("makes a click asked for once an edit came back while a pick was on its way", async () => {
    let open: () => void = () => undefined;
    const slow = new Promise<void>((resolve) => {
      open = resolve;
    });
    const fetch = engine({
      "POST /pictures/11/select": async (init: RequestInit | undefined) => {
        const body = JSON.parse(String(init?.body)) as { click: { x: number } | null };
        if (body.click?.x === 0.3) await slow;
        return picked(init);
      },
    });
    renderPage();
    await openEdit();
    const picture = await thePicture();
    clickAt(picture, 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    clickAt(picture, 0.3, 0.3); // on its way...
    fireEvent.click(screen.getByRole("button", { name: "Erase" })); // ...as the erase comes back
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());

    clickAt(picture, 0.7, 0.7); // a click on the picture as erased, while that pick is still out
    open();

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/select").at(-1)).toMatchObject({
        edits: [ERASE],
        parts: [],
        click: { x: 0.7, y: 0.7, keep: true },
      }),
    );
    expect(await screen.findByText("Part 1 · picked with one click")).toBeInTheDocument();
  });

  it("puts the label by the last part still picked once one is let go", async () => {
    engine();
    renderPage();
    await openEdit();
    const picture = await thePicture();
    clickAt(picture, 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    clickAt(picture, 0.2, 0.3);
    await screen.findByText("Part 2 · picked with one click");

    fireEvent.click(screen.getByRole("button", { name: "Let go of Part 2" }));

    const label = await screen.findByText("Part 1 · picked with one click");
    expect(label.style.left).toBe("50%");
    expect(label.style.top).toBe("50%");
  });

  it("makes clicks in turn while the picture is still being read, never dropping one", async () => {
    let open: () => void = () => undefined;
    const reading = new Promise<void>((resolve) => {
      open = resolve;
    });
    const fetch = engine({
      "POST /pictures/11/select": async (init: RequestInit | undefined) => {
        const body = JSON.parse(String(init?.body)) as { parts: unknown[] };
        if (body.parts.length === 0) await reading; // the first click: SAM reads the picture
        return picked(init);
      },
    });
    renderPage();
    await openEdit();
    const picture = await thePicture();

    clickAt(picture, 0.5, 0.5);
    clickAt(picture, 0.2, 0.3); // while the first is on its way
    open();

    expect(await screen.findByText("Part 2 · picked with one click")).toBeInTheDocument();
    const asked = sent(fetch, "POST", "/pictures/11/select");
    expect(asked).toHaveLength(2);
    expect(asked[1]).toMatchObject({
      parts: [{ clicks: [{ x: 0.5, y: 0.5, keep: true }] }],
      click: { x: 0.2, y: 0.3, keep: true },
    });
  });

  it("says the queue has the graphics card only for work that runs on it", async () => {
    let finish: () => void = () => undefined;
    const making = new Promise<void>((resolve) => {
      finish = resolve;
    });
    engine({
      "/queue/now": {
        working: true,
        batch: "Holiday prints",
        over: 3,
        total: 40,
        waiting: 37,
        paused: false,
      },
      "POST /pictures/11/edit": async () => {
        await making;
        return { seconds: 1, place: "processor", waited: 0, smeared: false };
      },
    });
    renderPage();
    const tools = await openEdit();
    fireEvent.click(within(tools).getByRole("radio", { name: "Cut out" }));

    fireEvent.click(screen.getByRole("button", { name: "Cut out the subject" })); // on the processor

    expect(await screen.findByText("Making the edit…", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.queryByText(/Waiting for the graphics card/)).toBeNull();
    finish();
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());
    fireEvent.click(within(tools).getByRole("radio", { name: "Select" }));
    clickAt(await thePicture(), 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    let erased: () => void = () => undefined;
    const erasing = new Promise<void>((resolve) => {
      erased = resolve;
    });
    engine({
      "/queue/now": {
        working: true,
        batch: "Holiday prints",
        over: 3,
        total: 40,
        waiting: 37,
        paused: false,
      },
      "POST /pictures/11/edit": async () => {
        await erasing;
        return { seconds: 1, place: "card", waited: 0.4, smeared: false };
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Erase" })); // Fast, on the card here

    expect(
      await screen.findByText(
        "Waiting for the graphics card: Holiday prints lets it go after the tile it's on",
        {},
        { timeout: 3000 },
      ),
    ).toBeInTheDocument();
    erased();
  });

  it("says when the picture was read on the processor", async () => {
    engine({
      "POST /pictures/11/select": (init: RequestInit | undefined) => ({
        ...picked(init),
        place: "processor",
      }),
    });
    renderPage();
    await openEdit();

    clickAt(await thePicture(), 0.5, 0.5);

    expect(await screen.findByText(/Mado read the picture in/)).toHaveTextContent(
      "Mado read the picture in 0.9 s on the processor; every click after that is instant",
    );
  });

  it("shows what's picked on the picture as its edits leave it, cropped to fill, not squashed", async () => {
    const fetch = engine();
    renderPage();
    await openEdit();
    const picture = await thePicture();
    clickAt(picture, 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    fireEvent.click(screen.getByRole("button", { name: "Erase" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());

    clickAt(picture, 0.3, 0.3);
    await screen.findByText("Part 1 · picked with one click");

    await waitFor(() =>
      expect(
        sent(fetch, "POST", "/pictures/11/preview").some(
          (body) =>
            JSON.stringify((body as { fit?: unknown }).fit) ===
              JSON.stringify({ width: 128, height: 128 }) &&
            JSON.stringify((body as { recipe: Recipe }).recipe.edit?.edits) ===
              JSON.stringify([ERASE]),
        ),
      ).toBe(true),
    );
    const small = document.querySelectorAll('svg[preserveAspectRatio="xMidYMid slice"]');
    expect(small.length).toBeGreaterThan(0);
  });

  it("hides the pointer under the brush only over the picture", async () => {
    engine();
    renderPage();
    const tools = await openEdit();

    fireEvent.click(within(tools).getByRole("radio", { name: "Erase" }));

    const picture = await thePicture();
    expect(picture).toHaveClass("cursor-none");
    expect(picture.parentElement).not.toHaveClass("cursor-none");
  });

  it("shows the looks on the picture as its edits leave it", async () => {
    const fetch = engine();
    renderPage();
    await openEdit();
    clickAt(await thePicture(), 0.5, 0.5);
    await screen.findByText("Part 1 · picked with one click");
    fireEvent.click(screen.getByRole("button", { name: "Erase" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled());

    fireEvent.click(screen.getByRole("tab", { name: "Looks" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/looks/warm-film")).toContainEqual({
        edit: { version: details.version, edits: [ERASE] },
      }),
    );
  });

  it("says a picture too big to edit is, and offers the Size tab to make a smaller copy", async () => {
    const fetch = engine({ "/pictures/11": { ...details, width: 12000, height: 9000 } });
    renderPage();
    await openEdit();

    expect(
      await screen.findByText(
        "It's 108 megapixels, and Mado edits pictures up to 100. Make a smaller copy of it on the Size tab, then edit that.",
      ),
    ).toBeInTheDocument();
    clickAt(await thePicture(), 0.5, 0.5);
    expect(sent(fetch, "POST", "/pictures/11/select")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Go to the Size tab" }));
    expect(await screen.findByRole("tab", { name: "Size", selected: true })).toBeInTheDocument();
  });
});
