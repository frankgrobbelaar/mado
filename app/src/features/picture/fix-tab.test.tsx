import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type Fixes, type PictureDetails, type Tool } from "@/lib/engine";
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

/** Nothing Mado can measure to fix: a JPEG saved at 92, well exposed. */
const FINE: Fixes = {
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

function model(id: string, name: string, size: number, state: Tool["state"] = "ready"): Tool {
  return {
    id,
    name,
    version: "models-1",
    purpose: "",
    licence: "Apache-2.0",
    size,
    when: "asked",
    state,
    done: 0,
    problem: null,
  };
}

const READY_MODELS = [
  model("scunet", "SCUNet", 72_932_271),
  model("fbcnn", "FBCNN", 287_709_421),
  model("nafnet", "NAFNet", 68_940_956),
];

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

type Fetch = ReturnType<typeof fakeEngine>;

/** Harbour at dusk opened from Phone, its fixes' answers. */
function engine(answers: Record<string, unknown> = {}): Fetch {
  return fakeEngine({
    "/folders": FOLDERS,
    "/settings": SETTINGS,
    "/pictures/11": details,
    "/pictures/11/neighbours": { before: [], after: [] },
    "/pictures/11/view": blob,
    "/pictures/11/full": blob,
    "/pictures/11/fixes": FINE,
    "/sizes": SIZES,
    "POST /screens": [],
    "POST /pictures/11/plan": plan({
      width: 4032,
      height: 3024,
      label: "",
      method: "keep",
      model: null,
      fix: "took out noise",
      fixSeconds: 21,
      seconds: 22,
    }),
    "POST /pictures/11/preview": () =>
      new Response(new Blob(["preview"], { type: "image/webp" }), {
        headers: { "X-Made-In": "1.4" },
      }),
    "POST /pictures/11/saving": {
      name: "Harbour at dusk (Cleaned).jpg",
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

function renderPicture(picture = "/library/pictures/11?folder=1") {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "screens") return [{ width: 3440, height: 1440, main: true }];
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[picture]}>
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

async function openFix() {
  const tab = await screen.findByRole("tab", { name: "Fix" });
  fireEvent.click(tab);
  return screen.findByRole("region", { name: "Fixes" });
}

describe("The Fix tab", () => {
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
            [{ target, contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          );
        }
        unobserve() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists the four fixes, each off till turned on, and says when nothing measured needs fixing", async () => {
    engine();
    renderPicture();

    const fixes = await openFix();
    for (const name of ["Noise", "Blur", "JPEG blocks", "Dark photo"]) {
      expect(within(fixes).getByRole("switch", { name })).not.toBeChecked();
    }
    expect(
      await screen.findByText(
        /Nothing Mado can measure needs fixing: it's well exposed and saved at JPEG quality 92/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/A picture out of focus only comes a little crisper/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
    expect(screen.getByText("Turn a fix on to compare before and after")).toBeInTheDocument();
  });

  it("turns a fix on with its strength, plans it and compares before and after", async () => {
    const fetch = engine();
    renderPicture();
    const fixes = await openFix();

    fireEvent.click(within(fixes).getByRole("switch", { name: "Noise" }));

    expect(within(fixes).getByRole("slider", { name: "How much noise comes out" })).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toEqual({
        edit: null,
        size: null,
        paint: null,
        look: null,
        fix: { noise: { strength: 1 }, blur: null, jpeg: null, dark: null },
      }),
    );
    expect(
      await screen.findByText("Noise, blur and blocks show at 100%: zoom in to compare them"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/About 20 s on your graphics card, as Save makes it/),
    ).toBeVisible();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save…" })).toBeEnabled());
    // All of it shows only a dark photo's brightening, which needs no model.
    expect(
      sent(fetch, "POST", "/pictures/11/preview").filter(
        (each) => (each as { recipe: { fix?: unknown } }).recipe.fix,
      ),
    ).toEqual([]);

    fireEvent.click(within(fixes).getByRole("switch", { name: "Dark photo" }));

    expect(await screen.findByText("After · Dark photo")).toBeInTheDocument();
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview")).toContainEqual(
        expect.objectContaining({
          recipe: {
            edit: null,
            fix: { noise: null, blur: null, jpeg: null, dark: { contrast: 0 } },
            size: null,
            look: null,
          },
          side: "after",
        }),
      ),
    );
  });

  it("says it's looking at the picture, and what each fix mends as its switch is read", async () => {
    engine({ "/pictures/11/fixes": () => new Promise(() => {}) });
    renderPicture();
    const fixes = await openFix();

    expect(screen.getByText("Looking at what it needs…")).toBeVisible();
    expect(within(fixes).getByRole("switch", { name: "Noise" })).toHaveAccessibleDescription(
      "Grain and speckles from a small camera or a dark room.",
    );
  });

  it("says there's nothing to save when the fixes on change nothing in it", async () => {
    engine({
      "POST /pictures/11/plan": plan({ method: "keep", model: null, label: "", fix: null }),
    });
    renderPicture();
    const fixes = await openFix();

    fireEvent.click(within(fixes).getByRole("switch", { name: "Dark photo" }));

    expect(
      await screen.findByText("Nothing to save: it isn't dark, so Dark photo leaves it as it is."),
    ).toBeInTheDocument();
    expect(
      within(fixes).getByText("It isn't dark, so Dark photo leaves it as it is."),
    ).toBeVisible();
    expect(within(fixes).queryByRole("slider", { name: "Local contrast" })).toBeNull();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
    expect(
      screen.getByText("Nothing changes: the fixes on find nothing to do in it"),
    ).toBeInTheDocument();
  });

  it("says when the graphics card is too full for the fixes, so they run on the processor", async () => {
    engine({
      "POST /pictures/11/plan": plan({
        method: "keep",
        model: null,
        label: "",
        fix: "took out noise",
        fixSeconds: 600,
        place: "card",
        fixPlace: "processor",
      }),
    });
    renderPicture();
    const fixes = await openFix();

    fireEvent.click(within(fixes).getByRole("switch", { name: "Noise" }));

    expect(
      await screen.findByText(/Your graphics card is full of the models Mado has used/),
    ).toBeInTheDocument();
    expect(screen.getByText(/About 10 min on the processor/)).toBeVisible();
  });

  it("compares a part at full detail at 100%, the picture unfixed before", async () => {
    const fetch = engine();
    renderPicture();
    const fixes = await openFix();
    fireEvent.click(within(fixes).getByRole("switch", { name: "Blur" }));

    fireEvent.click(screen.getByRole("radio", { name: "100%" }));

    await waitFor(() => {
      const asked = sent(fetch, "POST", "/pictures/11/preview") as {
        side: string;
        region?: unknown;
        recipe: { fix?: unknown };
      }[];
      expect(asked.some((each) => each.side === "before" && each.region && !each.recipe.fix)).toBe(
        true,
      );
      expect(asked.some((each) => each.side === "after" && each.region && each.recipe.fix)).toBe(
        true,
      );
    });
    expect(screen.getByRole("slider", { name: "Drag to compare before and after" })).toBeVisible();
  });

  it("suggests what Mado measured, and starts JPEG blocks as hard as the picture was squeezed", async () => {
    const fetch = engine({
      "/pictures/11/fixes": { ...FINE, jpegQuality: 18, blocks: true, stops: 3.1, dark: true },
    });
    renderPicture();
    const fixes = await openFix();

    expect(
      await screen.findByText(
        /Mado suggests JPEG blocks: it was saved at quality 18; dark: about 3\.1 stops under/,
      ),
    ).toBeInTheDocument();
    expect(within(fixes).getAllByText("Suggested")).toHaveLength(2);
    fireEvent.click(within(fixes).getByRole("switch", { name: "JPEG blocks" }));
    expect(
      within(fixes).getByRole("slider", { name: "How hard JPEG blocks come out" }),
    ).toHaveAttribute("aria-valuenow", "82");
    fireEvent.click(within(fixes).getByRole("switch", { name: "Dark photo" }));
    expect(within(fixes).getByText(/Mado brightens it by about 3\.1 stops/)).toBeVisible();
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        fix: { jpeg: { quality: null, strength: 0.82 }, dark: { contrast: 0 } },
      }),
    );
  });

  it("offers a model to download first, the stage waiting for it", async () => {
    const fetch = engine({
      "/tools": [model("scunet", "SCUNet", 72_932_271, "missing")],
      "POST /tools/scunet/download": model("scunet", "SCUNet", 72_932_271, "downloading"),
      "POST /pictures/11/plan": plan({
        method: "keep",
        model: null,
        label: "",
        fix: "took out noise",
        needs: [{ id: "scunet", name: "SCUNet", size: 72_932_271 }],
      }),
    });
    renderPicture();
    const fixes = await openFix();

    fireEvent.click(within(fixes).getByRole("switch", { name: "Noise" }));

    expect(
      await screen.findByText(/Noise comes out with SCUNet, an AI model Mado downloads/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "100%" }));
    expect(await screen.findByText("After shows once SCUNet is downloaded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Download SCUNet" }));
    await waitFor(() => expect(sent(fetch, "POST", "/tools/scunet/download")).toHaveLength(1));
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
  });

  it("says the graphics card is busy with the queue when a preview waits for it", async () => {
    engine({
      "/queue/now": {
        working: true,
        paused: false,
        batch: "Holiday prints",
        over: 18,
        total: 48,
        progress: 0.37,
        waiting: 30,
      },
      "POST /pictures/11/preview": () => new Promise(() => {}), // waits for the card
    });
    renderPicture();
    const fixes = await openFix();
    fireEvent.click(within(fixes).getByRole("switch", { name: "Noise" }));
    fireEvent.click(screen.getByRole("radio", { name: "100%" }));

    expect(
      await screen.findByText(
        "Waiting for the graphics card: Holiday prints lets it go after the tile it's on",
        {},
        { timeout: 4000 },
      ),
    ).toBeInTheDocument();
  });

  it("keeps a camera RAW's JPEG blocks off, as a RAW has none", async () => {
    engine({
      "/pictures/11": { ...details, raw: true, format: "DNG", name: "Harbour at dusk.dng" },
      "/pictures/11/fixes": { ...FINE, jpegQuality: null, colour: "Display P3" },
    });
    renderPicture();
    const fixes = await openFix();

    expect(within(fixes).getByRole("switch", { name: "JPEG blocks" })).toBeDisabled();
    expect(within(fixes).getByText(/A camera RAW has no JPEG blocks/)).toBeVisible();
    expect(await screen.findByText(/Its Display P3 colours are kept/)).toBeInTheDocument();
  });

  it("says a grey picture stays grey, see-through parts stay, and a huge one takes a while", async () => {
    engine({
      "/pictures/11/fixes": { ...FINE, grey: true, seeThrough: true, megapixels: 96 },
      "POST /pictures/11/plan": plan({
        method: "keep",
        model: null,
        label: "",
        fix: "took out noise",
        fixSeconds: 190,
      }),
    });
    renderPicture();
    const fixes = await openFix();
    fireEvent.click(within(fixes).getByRole("switch", { name: "Noise" }));

    expect(
      await screen.findByText("It stays black and white. Its see-through parts stay as they are."),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/A big picture: 96 megapixels, fixed a tile at a time/),
    ).toBeInTheDocument();
  });

  it("saves the fixes as one recipe with the rest", async () => {
    let made = false;
    const fetch = engine({
      "POST /pictures/11/make": () => {
        made = true;
        return job({ state: "queued", progress: 0, madeFor: null, fix: "took out noise" });
      },
      "/jobs": () => (made ? [job({ stage: "fixing", madeFor: null, fix: "took out noise" })] : []),
    });
    renderPicture();
    const fixes = await openFix();
    fireEvent.click(within(fixes).getByRole("switch", { name: "Noise" }));
    const save = screen.getByRole("button", { name: "Save…" });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);

    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    expect(await within(dialog).findByText("Harbour at dusk (Cleaned).jpg")).toBeInTheDocument();
    expect(within(dialog).getByText("Took out noise").parentElement).toHaveTextContent(
      "Took out noise, 4032 × 3024",
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/make")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/11/make")[0]).toMatchObject({
      recipe: { fix: { noise: { strength: 1 } }, size: null, look: null },
    });
    expect(await screen.findByText("Fixing it")).toBeInTheDocument();
  });

  it("shows a dark photo brightened in the Looks tab's small copies too", async () => {
    const fetch = engine({
      "/looks": LOOKS,
      ...Object.fromEntries(
        LOOKS.looks.map((look) => [`POST /pictures/11/looks/${look.id}`, blob]),
      ),
    });
    renderPicture();
    const fixes = await openFix();
    fireEvent.click(within(fixes).getByRole("switch", { name: "Dark photo" }));
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/plan").length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("tab", { name: "Looks" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/looks/warm-film")).toContainEqual({
        edit: { version: details.version, edits: [] },
        fix: { noise: null, blur: null, jpeg: null, dark: { contrast: 0 } },
      }),
    );
  });

  it("starts the next picture with no fixes, the last one's never reaching it", async () => {
    const SAIL = PICTURES[1] as (typeof PICTURES)[number];
    const fetch = engine({
      "/pictures/11/neighbours": { before: [], after: [SAIL] },
      "/pictures/12": { ...details, ...SAIL },
      "/pictures/12/neighbours": { before: [DUSK], after: [] },
      "/pictures/12/view": blob,
      "/pictures/12/fixes": FINE,
      "POST /pictures/12/plan": plan({ method: "keep", model: null, label: "" }),
    });
    renderPicture();
    const fixes = await openFix();
    fireEvent.click(within(fixes).getByRole("switch", { name: "Noise" }));
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/plan").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("tab", { name: "Size" }));

    const next = await screen.findByRole("button", { name: "Next picture" });
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);

    expect(
      await screen.findByRole("heading", { name: "Little sail", level: 1 }),
    ).toBeInTheDocument();
    await new Promise((settle) => setTimeout(settle, 450));
    expect(sent(fetch, "POST", "/pictures/12/plan")).toEqual([]);
  });

  it("tells the Size tab the fixes clean first, so the model doesn't clean again", async () => {
    engine({
      "POST /pictures/11/plan": plan({ cleanedFirst: true, cleanMatters: false }),
    });
    renderPicture();
    const fixes = await openFix();
    fireEvent.click(within(fixes).getByRole("switch", { name: "Noise" }));
    fireEvent.click(screen.getByRole("tab", { name: "Size" }));
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));

    expect(
      await screen.findByText(
        "The Fix tab takes noise and blocks out first, so Fast doesn't clean them again.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Clean noise and blocks first" })).toBeNull();
  });
});
