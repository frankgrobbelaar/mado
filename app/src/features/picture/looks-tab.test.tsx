import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type PictureDetails, type Recipe, type YourLook } from "@/lib/engine";
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
  camera: "Pixelworks PW-7 Pro",
  orientation: 1,
  located: true,
  problem: null,
  damaged: false,
};

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));
const copies = Object.fromEntries(
  [...LOOKS.looks, ...LOOKS.yours].map((look) => [`/pictures/11/looks/${look.id}`, blob]),
);

type Fetch = ReturnType<typeof fakeEngine>;

/** The plan for what's asked: for TV 8K when a size is, else the picture's own pixels; with
 * the look's words when a look is. */
function planned(init: RequestInit | undefined) {
  const recipe = JSON.parse(String(init?.body)) as Recipe;
  const look = recipe.look
    ? `${recipe.look.look === "warm-film" ? "Warm film" : recipe.look.look}${recipe.look.strength < 1 ? ` at ${Math.round(recipe.look.strength * 100)}%` : ""}`
    : null;
  if (recipe.size) return plan({ look });
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
    look,
    seconds: 1.4,
  });
}

/** Harbour at dusk opened from Phone, with the Looks tab's answers. */
function engine(answers: Record<string, unknown> = {}): Fetch {
  return fakeEngine({
    "/folders": FOLDERS,
    "/settings": SETTINGS,
    "/pictures/11": details,
    "/pictures/11/neighbours": { before: [], after: [] },
    "/pictures/11/view": blob,
    "/sizes": SIZES,
    "POST /screens": [],
    "/looks": LOOKS,
    ...copies,
    "POST /pictures/11/plan": planned,
    "POST /pictures/11/preview": () =>
      new Response(new Blob(["preview"], { type: "image/webp" }), {
        headers: { "X-Made-In": "0.1" },
      }),
    "POST /pictures/11/saving": {
      name: "Harbour at dusk (Warm film).jpg",
      folder: "D:\\Pictures\\Phone",
      taken: null,
      takenAt: null,
      bytes: 3_000_000,
      colour: "Display P3",
    },
    "/jobs": [],
    "/tools": [],
    ...answers,
  });
}

function renderLooks() {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "screens") return [];
    if (command === "pick_cube") return "D:\\Looks\\Teal pop.cube";
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

async function openLooks() {
  fireEvent.click(await screen.findByRole("tab", { name: "Looks" }));
  return screen.findByRole("radiogroup", { name: "Looks" });
}

/** What the words over the picture say: the look shown on it. */
async function onStage(words: string) {
  const tools = screen.getByRole("complementary", { name: "Tools" });
  await waitFor(() =>
    expect(screen.getAllByText(words).filter((each) => !tools.contains(each))).toHaveLength(1),
  );
}

/** An answer that never comes: what's asked for stays on its way. */
const never = () => new Response(new ReadableStream({ start() {} }));

describe("The Looks tab", () => {
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

  it("lists every look as a small copy of this picture, the original picked", async () => {
    const fetch = engine();
    renderLooks();

    const grid = await openLooks();

    const tiles = within(grid).getAllByRole("radio");
    expect(tiles.map((tile) => tile.textContent)).toEqual(LOOKS.looks.map((look) => look.name));
    expect(within(grid).getByRole("radio", { name: "Original" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await waitFor(() => expect(sent(fetch, "GET", "/pictures/11/looks/warm-film")).toHaveLength(1));
    const asked = fetch.mock.calls.map(([input]) => String(input));
    expect(asked).toContain("http://127.0.0.1:5000/pictures/11/looks/warm-film?v=v11-1a2b3c4d");
    for (const heading of ["Looks", "Finishing touches", "Your looks"])
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Strength" })).toHaveAttribute("data-disabled", "");
    // The board's header: hold to see the original, where the Size tab has its zoom.
    expect(screen.getByRole("button", { name: "Hold to see the original" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Zoom" })).not.toBeInTheDocument();
    expect(
      screen.getByText("Every look is shown on this picture as you go through them"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
  });

  it("shows skeletons while the looks are on their way, and says so", async () => {
    engine({ "/looks": never });
    renderLooks();

    fireEvent.click(await screen.findByRole("tab", { name: "Looks" }));

    expect(await screen.findByRole("status", { name: "Loading the looks" })).toBeInTheDocument();
  });

  it("says why when the looks can't be listed", async () => {
    engine({
      "/looks": () => Response.json({ detail: "Mado's records are damaged." }, { status: 503 }),
    });
    renderLooks();

    fireEvent.click(await screen.findByRole("tab", { name: "Looks" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mado couldn't list the looks: Mado's records are damaged.",
    );
  });

  it("shows a look picked on the picture, and goes through them with the arrow keys", async () => {
    const fetch = engine();
    renderLooks();
    const grid = await openLooks();

    fireEvent.click(within(grid).getByRole("radio", { name: "Warm film" }));

    expect(within(grid).getByRole("radio", { name: "Warm film" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview").at(-1)).toMatchObject({
        recipe: { size: null, look: { look: "warm-film", strength: 1 } },
        side: "after",
      }),
    );
    await onStage("Warm film · 100%");
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        size: null,
        look: { look: "warm-film" },
      }),
    );

    fireEvent.keyDown(within(grid).getByRole("radio", { name: "Warm film" }), {
      key: "ArrowRight",
    });

    expect(within(grid).getByRole("radio", { name: "Cool film" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(within(grid).getByRole("radio", { name: "Cool film" })).toHaveFocus();
    fireEvent.keyDown(within(grid).getByRole("radio", { name: "Cool film" }), { key: "ArrowDown" });
    expect(within(grid).getByRole("radio", { name: "Silver" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview").at(-1)).toMatchObject({
        recipe: { look: { look: "silver" } },
      }),
    );
  });

  it("shows a look on the picture while the pointer rests on it, and the one picked after", async () => {
    const fetch = engine();
    renderLooks();
    const grid = await openLooks();

    fireEvent.pointerEnter(within(grid).getByRole("radio", { name: "Night neon" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview").at(-1)).toMatchObject({
        recipe: { look: { look: "night-neon" } },
      }),
    );
    await onStage("Night neon · 100%");
    expect(within(grid).getByRole("radio", { name: "Original" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    fireEvent.pointerLeave(grid);
    await onStage("Original");
  });

  it("sets the strength, and finishing touches each with its own amount", async () => {
    const fetch = engine();
    renderLooks();
    const grid = await openLooks();
    fireEvent.click(within(grid).getByRole("radio", { name: "Warm film" }));

    const strength = screen.getByRole("slider", { name: "Strength" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    fireEvent.keyDown(strength, { key: "PageDown" });
    expect(screen.getByText("60%")).toBeInTheDocument();
    const grain = screen.getByRole("button", { name: "Grain" });
    fireEvent.click(grain);

    expect(screen.getByRole("button", { name: "Grain 20" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const amount = screen.getByRole("slider", { name: "Grain" });
    fireEvent.keyDown(amount, { key: "ArrowLeft" });
    expect(screen.getByRole("button", { name: "Grain 19" })).toBeInTheDocument();
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview").at(-1)).toMatchObject({
        recipe: { look: { look: "warm-film", strength: 0.6, touches: { grain: 19, dust: 0 } } },
      }),
    );
    await onStage("Warm film · 60% · grain");
    // As low as it goes, a touch is still on, its slider still under the pointer or the keys.
    fireEvent.keyDown(amount, { key: "Home" });
    expect(screen.getByRole("button", { name: "Grain 1" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Grain" })).toBe(amount);

    fireEvent.click(screen.getByRole("button", { name: "Grain 1" }));

    expect(screen.getByRole("button", { name: "Grain" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("slider", { name: "Grain" })).not.toBeInTheDocument();
  });

  it("goes through the tools by the arrow keys, and not to the next picture from the looks", async () => {
    const fetch = engine({
      "/pictures/11/neighbours": { before: [], after: [PICTURES[1]] },
    });
    renderLooks();
    const size = await screen.findByRole("tab", { name: "Size" });

    fireEvent.keyDown(size, { key: "ArrowRight" });

    const looks = screen.getByRole("tab", { name: "Looks" });
    expect(looks).toHaveAttribute("aria-selected", "true");
    expect(looks).toHaveFocus();
    expect(screen.getByRole("tabpanel", { name: "Looks" })).toBeInTheDocument();
    await screen.findByRole("radiogroup", { name: "Looks" });
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    await new Promise((settle) => setTimeout(settle, 50));
    expect(screen.getByRole("heading", { name: "Harbour at dusk" })).toBeInTheDocument();
    expect(sent(fetch, "GET", "/pictures/12")).toHaveLength(0); // the next picture never opened
  });

  it("shows the original while the button is held, or the \\ key", async () => {
    engine();
    renderLooks();
    const grid = await openLooks();
    fireEvent.click(within(grid).getByRole("radio", { name: "Faded" }));
    const looked = await screen.findByRole("img", { name: "Harbour at dusk in Faded · 100%" });
    const hold = screen.getByRole("button", { name: "Hold to see the original" });

    fireEvent.pointerDown(hold, { pointerId: 1 });

    expect(hold).toHaveAttribute("aria-pressed", "true");
    expect(looked).toHaveClass("opacity-0");
    await onStage("Original");
    fireEvent.pointerUp(hold, { pointerId: 1 });
    expect(looked).toHaveClass("opacity-100");

    fireEvent.keyDown(window, { key: "\\" });
    expect(looked).toHaveClass("opacity-0");
    fireEvent.keyUp(window, { key: "\\" });
    expect(looked).toHaveClass("opacity-100");
  });

  it("imports a .cube file and picks it, and says plainly why one won't do", async () => {
    let imported = false;
    const teal = {
      id: "yours-2",
      name: "Teal pop",
      version: "a3b4c5d6",
      kind: "cube",
      points: 33,
      touches: { grain: 0, vignette: 0, glow: 0, fade: 0, leak: 0, dust: 0 },
      source: "Teal pop.cube",
      addedAt: "2026-11-22T21:00:00+02:00",
    };
    const fetch = engine({
      "/looks": () => (imported ? { ...LOOKS, yours: [...LOOKS.yours, teal] } : LOOKS),
      "POST /looks/import": () => {
        imported = true;
        return teal;
      },
      "/pictures/11/looks/yours-2": blob,
    });
    renderLooks();
    await openLooks();

    fireEvent.click(screen.getByRole("button", { name: "Import a .cube file" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/looks/import")).toEqual([{ path: "D:\\Looks\\Teal pop.cube" }]),
    );
    expect(await screen.findByRole("button", { name: "Teal pop" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText("From Teal pop.cube")).toBeInTheDocument();
  });

  it("says why a .cube file can't be imported", async () => {
    engine({
      "POST /looks/import": () =>
        Response.json(
          {
            detail:
              "Teal pop.cube: It's damaged or cut short: a 33-point table has 35,937 rows, and it has 12,000.",
          },
          { status: 422 },
        ),
    });
    renderLooks();
    await openLooks();

    fireEvent.click(screen.getByRole("button", { name: "Import a .cube file" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Teal pop.cube: It's damaged or cut short: a 33-point table has 35,937 rows, and it has 12,000.",
    );
  });

  it("keeps the mix as a look, saying when its name is taken", async () => {
    const fetch = engine({
      "POST /looks": () =>
        Response.json(
          { detail: "You have a look called Holiday warm already. Pick another name." },
          { status: 422 },
        ),
    });
    renderLooks();
    const grid = await openLooks();
    const keep = screen.getByRole("button", { name: "Keep this mix as a look" });
    expect(keep).toBeDisabled(); // the original, untouched: nothing to keep

    fireEvent.click(within(grid).getByRole("radio", { name: "Warm film" }));
    fireEvent.click(keep);
    fireEvent.change(screen.getByLabelText("Its name"), { target: { value: "holiday warm" } });
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You have a look called Holiday warm already. Pick another name.",
    );
    expect(sent(fetch, "POST", "/looks")[0]).toMatchObject({
      name: "holiday warm",
      look: { look: "warm-film", strength: 1 },
    });
  });

  it("picks one of yours with its touches, renames it, and deletes it after asking", async () => {
    let deleted = false;
    const fetch = engine({
      "/looks": () => (deleted ? { ...LOOKS, yours: [] } : LOOKS),
      "PUT /looks/yours-1": { ...LOOKS.yours[0], name: "Summer warm" },
      "DELETE /looks/yours-1": () => {
        deleted = true;
        return null;
      },
    });
    renderLooks();
    await openLooks();

    fireEvent.click(await screen.findByRole("button", { name: "Holiday warm" }));

    expect(screen.getByRole("button", { name: "Grain 20" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Vignette 35" })).toBeInTheDocument();
    expect(screen.getByText("Warm film at 60%, grain 20, vignette 35")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    fireEvent.change(screen.getByLabelText("A new name for Holiday warm"), {
      target: { value: "Summer warm" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    await waitFor(() =>
      expect(sent(fetch, "PUT", "/looks/yours-1")).toEqual([{ name: "Summer warm" }]),
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete…" }));
    const asking = await screen.findByRole("dialog", { name: "Delete Holiday warm?" });
    expect(sent(fetch, "DELETE", "/looks/yours-1")).toHaveLength(0); // asked first
    fireEvent.click(within(asking).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(sent(fetch, "DELETE", "/looks/yours-1")).toHaveLength(1));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Holiday warm" })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("radio", { name: "Original" })).toHaveAttribute("aria-checked", "true");
  });

  it("renames only the look picked: picking another closes what was open for the first", async () => {
    const night = { ...(LOOKS.yours[0] as YourLook), id: "yours-2", name: "Night city" };
    const fetch = engine({ "/looks": { ...LOOKS, yours: [...LOOKS.yours, night] } });
    renderLooks();
    await openLooks();
    fireEvent.click(await screen.findByRole("button", { name: "Holiday warm" }));
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    expect(screen.getByLabelText("A new name for Holiday warm")).toHaveValue("Holiday warm");

    fireEvent.click(screen.getByRole("button", { name: "Night city" }));

    expect(screen.queryByLabelText("A new name for Holiday warm")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    expect(screen.getByLabelText("A new name for Night city")).toHaveValue("Night city");
    expect(sent(fetch, "PUT", "/looks/yours-1")).toHaveLength(0);
  });

  it("waits for the plan of the look picked last before Save opens, never an older one", async () => {
    engine({
      "POST /pictures/11/plan": (init: RequestInit | undefined) =>
        String(init?.body).includes("cool-film") ? never() : planned(init),
    });
    renderLooks();
    const grid = await openLooks();
    fireEvent.click(within(grid).getByRole("radio", { name: "Warm film" }));
    const save = screen.getByRole("button", { name: "Save…" });
    await waitFor(() => expect(save).toBeEnabled());

    fireEvent.click(within(grid).getByRole("radio", { name: "Cool film" }));

    await new Promise((settle) => setTimeout(settle, 450)); // past the look settling
    expect(save).toBeDisabled();
  });

  it("says what Save waits for when the size needs a model downloaded", async () => {
    engine({
      "POST /pictures/11/plan": plan({
        quality: "best",
        look: "Warm film",
        needs: [{ id: "realesrgan-x4plus", name: "RealESRGAN x4plus", size: 67_087_820 }],
      }),
    });
    renderLooks();
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));
    const grid = await openLooks();
    fireEvent.click(within(grid).getByRole("radio", { name: "Warm film" }));

    expect(
      await screen.findByText("Save waits for RealESRGAN x4plus, which the Size tab downloads."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
  });

  it("opens the picture it made as it is, without the look it was given again", async () => {
    const result = { ...details, id: 41, name: "Harbour at dusk (Warm film).jpg", version: "v41" };
    const copiesOf41 = Object.fromEntries(
      [...LOOKS.looks, ...LOOKS.yours].map((look) => [`/pictures/41/looks/${look.id}`, blob]),
    );
    engine({
      ...copiesOf41,
      "/pictures/41": result,
      "/pictures/41/neighbours": { before: [], after: [] },
      "/pictures/41/view": blob,
      "POST /pictures/41/plan": planned,
      "POST /pictures/41/preview": blob,
      "/jobs": (_init: RequestInit | undefined, url: URL) =>
        url.searchParams.get("picture") === "11"
          ? [
              job({
                madeFor: null,
                look: "Warm film",
                state: "done",
                progress: 1,
                finishedAt: new Date().toISOString(),
                result: "D:\\Pictures\\Phone\\Harbour at dusk (Warm film).jpg",
                resultName: "Harbour at dusk (Warm film).jpg",
                resultPicture: { id: 41, version: "v41" },
              }),
            ]
          : [],
    });
    renderLooks();
    const grid = await openLooks();
    fireEvent.click(within(grid).getByRole("radio", { name: "Warm film" }));

    fireEvent.click(await screen.findByRole("link", { name: "Open it" }));

    expect(
      await screen.findByRole("heading", { name: "Harbour at dusk (Warm film)" }),
    ).toBeInTheDocument();
    const next = await screen.findByRole("radiogroup", { name: "Looks" });
    expect(within(next).getByRole("radio", { name: "Original" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("saves a look alone as a new picture, with one Save for the whole recipe", async () => {
    const fetch = engine({ "POST /pictures/11/make": job({ madeFor: null, look: "Warm film" }) });
    renderLooks();
    const grid = await openLooks();
    fireEvent.click(within(grid).getByRole("radio", { name: "Warm film" }));

    const save = screen.getByRole("button", { name: "Save…" });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);

    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    expect(dialog).toHaveTextContent("With Warm film, 4032 × 3024");
    expect(await within(dialog).findByText("Harbour at dusk (Warm film).jpg")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/make")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/11/make")[0]).toMatchObject({
      recipe: { size: null, look: { look: "warm-film", strength: 1 } },
      saving: { how: "new" },
    });
  });

  it("follows the job giving the picture its look, as the Size tab does", async () => {
    engine({
      "/jobs": [job({ madeFor: null, look: "Warm film at 60%", stage: "looking", progress: 0.88 })],
    });
    renderLooks();
    await openLooks();

    expect(await screen.findByText("Giving it its look")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", { name: "Making Harbour at dusk with Warm film at 60%" }),
    ).toHaveAttribute("aria-valuenow", "88");
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled(); // one at a time
  });

  it("saves the size chosen on the Size tab and the look together", async () => {
    const fetch = engine({ "POST /pictures/11/make": job({ look: "Warm film" }) });
    renderLooks();
    fireEvent.click(await screen.findByRole("button", { name: /TV 8K/ }));
    const grid = await openLooks();
    fireEvent.click(within(grid).getByRole("radio", { name: "Warm film" }));

    const save = screen.getByRole("button", { name: "Save…" });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);

    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    expect(dialog).toHaveTextContent("Made for TV 8K (7680 × 4320), with Warm film");
    fireEvent.click(await within(dialog).findByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/make")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/11/make")[0]).toMatchObject({
      recipe: { size: { size: "tv-8k" }, look: { look: "warm-film" } },
    });
    // The stage shows the picture as both make it: the size's shape, with the look.
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/preview")).toContainEqual(
        expect.objectContaining({
          recipe: expect.objectContaining({ size: expect.objectContaining({ size: "tv-8k" }) }),
        }),
      ),
    );
  });
});
