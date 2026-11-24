import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type Job, type PictureDetails, type Plan } from "@/lib/engine";
import { FOLDERS, fakeEngine, job, PICTURES, plan, READY, SETTINGS, SIZES } from "@/test/engine";
import { PicturePage } from "./picture-page";
import { regionAt } from "./size-stage";

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
  gainMap: null,
};

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

type Fetch = ReturnType<typeof fakeEngine>;

/** Harbour at dusk opened from Phone, with the Size tab's answers. */
function engine(answers: Record<string, unknown> = {}): Fetch {
  return fakeEngine({
    "/folders": FOLDERS,
    "/settings": SETTINGS,
    "/pictures/11": details,
    "/pictures/11/neighbours": { before: [], after: [] },
    "/pictures/11/view": blob,
    "/pictures/11/full": blob,
    "/sizes": SIZES,
    "POST /screens": [],
    "POST /pictures/11/plan": plan(),
    "POST /pictures/11/preview": () =>
      new Response(new Blob(["preview"], { type: "image/webp" }), {
        headers: { "X-Made-In": "1.2" },
      }),
    "POST /pictures/11/saving": {
      name: "Harbour at dusk (TV 8K) (2).jpg",
      folder: "D:\\Pictures\\Phone",
      taken: "Harbour at dusk (TV 8K).jpg",
      takenAt: new Date().toISOString(),
      bytes: 18_000_000,
      colour: "Display P3",
    },
    "/jobs": [],
    "/tools": [],
    ...answers,
  });
}

function renderPicture() {
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
}

function sent(fetch: Fetch, method: string, path: string): unknown[] {
  return fetch.mock.calls
    .filter(
      ([input, init]) =>
        (init?.method ?? "GET") === method && new URL(String(input)).pathname === path,
    )
    .map(([, init]) => JSON.parse(String(init?.body ?? "null")));
}

async function openSave() {
  const save = await screen.findByRole("button", { name: "Save…" });
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.click(save);
}

async function chooseTv() {
  const tv = await screen.findByRole("button", { name: /TV 8K/ });
  fireEvent.click(tv);
  return tv;
}

describe("The Size tab", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("offers the devices, the owner's screens and prints, and remembers this PC's screens", async () => {
    const fetch = engine();
    renderPicture();

    const tools = await screen.findByRole("complementary", { name: "Tools" });
    expect(
      await within(tools).findByRole("button", { name: /Phone\s*1290 × 2796/ }),
    ).toHaveAttribute("aria-pressed", "false");
    for (const name of ["Tablet", "Laptop", "Monitor 4K", "Ultrawide", "TV 8K"]) {
      expect(within(tools).getByRole("button", { name: new RegExp(name) })).toBeInTheDocument();
    }
    expect(
      within(tools).getByRole("button", { name: /Main screen\s*3440 × 1440/ }),
    ).toBeInTheDocument();
    expect(within(tools).getByRole("button", { name: "A4" })).toBeInTheDocument();
    expect(within(tools).getByRole("button", { name: "Other size" })).toBeInTheDocument();
    // Nothing picked: Save saves the picture as it is, quietly.
    await waitFor(() => expect(within(tools).getByRole("button", { name: "Save…" })).toBeEnabled());
    await waitFor(() =>
      expect(sent(fetch, "POST", "/screens")).toEqual([
        { seen: [{ width: 3440, height: 1440, main: true }] },
      ]),
    );
  });

  it("plans a size: the shape over the picture, the note, the quality line and the time", async () => {
    const fetch = engine();
    renderPicture();

    const tv = await chooseTv();

    expect(tv).toHaveAttribute("aria-pressed", "true");
    expect(
      await screen.findByText(
        "A TV is 16:9 and this picture is 4:3, so a little of the top and bottom goes.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("JPEG 95 · sRGB · about 18 MB")).toBeInTheDocument();
    expect(screen.getByText(/What every TV shows\. Made with the photo model/)).toBeInTheDocument();
    expect(screen.getByText(/About 40 s on your graphics card/)).toBeInTheDocument();
    expect(screen.getByText(/^After/)).toHaveTextContent("After 7680 × 4320"); // under the picture
    expect(
      screen.getByRole("button", { name: "The point the crop is around: drag it to move it" }),
    ).toBeInTheDocument();
    expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toEqual({
      edit: null,
      size: { size: "tv-8k", shape: "crop", focus: null, kind: null, quality: null, clean: true },
      paint: null,
      look: null,
    });
    expect(screen.getByRole("button", { name: "Save…" })).toBeEnabled();
  });

  it("moves the crop's point with the keyboard, and changes what it is and the model", async () => {
    const fetch = engine();
    renderPicture();
    await chooseTv();

    const point = await screen.findByRole("button", {
      name: "The point the crop is around: drag it to move it",
    });
    fireEvent.keyDown(point, { key: "ArrowUp" });
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        size: { focus: [0.5, 0.43] },
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("radio", { name: "Drawing" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        size: { kind: "drawing" },
      }),
    );
    fireEvent.click(screen.getByRole("radio", { name: "Best" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        size: { quality: "best" },
      }),
    );
  });

  it("offers a model that's a download in its place, with the lighter way beside it", async () => {
    engine({
      "POST /pictures/11/plan": plan({
        quality: "best",
        model: "RealESRGAN x4plus",
        cleanMatters: false,
        needs: [{ id: "realesrgan-x4plus", name: "RealESRGAN x4plus", size: 67_087_820 }],
      }),
      "/tools": [],
      "POST /tools/realesrgan-x4plus/download": {},
    });
    renderPicture();
    await chooseTv();

    expect(
      await screen.findByText(/Best for photos is RealESRGAN x4plus, a 67\.1 MB download/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download RealESRGAN x4plus" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use Fast" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
    expect(screen.getByText("Best cleans as it makes the picture bigger.")).toBeInTheDocument();
  });

  it("saves as a new picture, saying the name's taken, and makes it as a job", async () => {
    let made = false;
    const fetch = engine({
      "POST /pictures/11/make": () => {
        made = true;
        return job({ state: "queued", progress: 0 });
      },
      "/jobs": () => (made ? [job()] : []),
    });
    renderPicture();
    await chooseTv();
    await openSave();

    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    expect(await within(dialog).findByText("Harbour at dusk (TV 8K) (2).jpg")).toBeInTheDocument();
    expect(within(dialog).getByText(/is already there/)).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /As a new picture/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(
      within(dialog).getByText(/Its colours \(the colour profile: Display P3\)/),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: /Where it was taken/ })).not.toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/make")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/11/make")[0]).toMatchObject({
      recipe: { size: { size: "tv-8k", shape: "crop" }, look: null },
      saving: {
        how: "new",
        format: "JPEG",
        quality: 95,
        folder: null,
        keepCamera: true,
        keepColours: true,
        keepLocation: false,
        always: false,
      },
    });
    const progress = await screen.findByRole("progressbar", {
      name: "Making Harbour at dusk for TV 8K",
    });
    expect(progress).toHaveAttribute("aria-valuenow", "37");
    expect(screen.getByText("Making it bigger")).toBeInTheDocument();
    expect(screen.getByText("about 25 s left")).toBeInTheDocument();
  });

  it("saves a camera RAW only as a new picture, saying why Replace isn't offered", async () => {
    const fetch = engine({
      "/settings": { ...SETTINGS, saveFirst: "replace" },
      "/pictures/11": { ...details, name: "Harbour at dusk.CR3", format: "CR3", raw: true },
      "POST /pictures/11/make": job({ state: "queued" }),
    });
    renderPicture();
    await chooseTv();
    expect(
      await screen.findByText("As a new picture beside the original, the RAW staying as it is."),
    ).toBeInTheDocument();
    await openSave();

    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    expect(
      await within(dialog).findByText(/Replacing the original isn't offered/),
    ).toHaveTextContent("Mado can't write camera RAW");
    expect(within(dialog).queryByRole("radio", { name: /Replace the original/ })).toBeNull();
    expect(within(dialog).queryByRole("checkbox", { name: "Always save this way" })).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/make")).toHaveLength(1));
    const [made] = sent(fetch, "POST", "/pictures/11/make") as [{ saving: { how: string } }];
    expect(made.saving.how).toBe("new");
  });

  it("replaces the original when chosen, saying the original waits in quarantine", async () => {
    const fetch = engine({ "POST /pictures/11/make": job({ how: "replace", state: "queued" }) });
    renderPicture();
    await chooseTv();
    await openSave();

    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    fireEvent.click(await within(dialog).findByRole("radio", { name: /Replace the original/ }));
    expect(
      within(dialog).getByText(
        "The original waits in quarantine for 30 days, and History puts it back.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("radio", { name: "PNG" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Always save this way" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/make")[0]).toMatchObject({
        saving: { how: "replace", format: "PNG", quality: null, always: true },
      }),
    );
  });

  it("offers next time the way saved with Always", async () => {
    let always = false;
    engine({
      "/settings": () => ({ ...SETTINGS, saveFirst: always ? "replace" : "new" }),
      "POST /pictures/11/make": () => {
        always = true; // the engine keeps the way chosen
        return job({ how: "replace", state: "queued" });
      },
    });
    renderPicture();
    await chooseTv();
    await openSave();
    const first = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    fireEvent.click(await within(first).findByRole("radio", { name: /Replace the original/ }));
    fireEvent.click(within(first).getByRole("checkbox", { name: "Always save this way" }));
    fireEvent.click(within(first).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await openSave();

    const again = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    expect(
      await within(again).findByRole("radio", { name: /Replace the original/ }),
    ).toHaveAttribute("aria-checked", "true");
  });

  it("cancels a job under way, and says what a finished one saved", async () => {
    let state: Job = job();
    const fetch = engine({
      "/jobs": () => [state],
      "POST /jobs/7/cancel": () => {
        state = job({ state: "cancelled", finishedAt: new Date().toISOString() });
        return state;
      },
    });
    renderPicture();

    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(sent(fetch, "POST", "/jobs/7/cancel")).toHaveLength(1));
    expect(
      await screen.findByText("Cancelled. Nothing was saved, and the original is as it was."),
    ).toBeInTheDocument();
  });

  it("offers no Cancel once a job is saving, as it's past cancelling", async () => {
    engine({ "/jobs": [job({ stage: "saving", progress: 0.95, secondsLeft: 1 })] });
    renderPicture();

    expect(await screen.findByText("Saving it")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("reaches Choose a folder from the keyboard, inside its choice", async () => {
    engine();
    renderPicture();
    await chooseTv();
    await openSave();
    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    fireEvent.click(await within(dialog).findByRole("radio", { name: /Replace the original/ }));

    const choose = within(dialog).getByRole("button", { name: "Choose a folder…" });
    const pressed = fireEvent.keyDown(choose, { key: "Enter" });

    expect(pressed).toBe(true); // not held back, so Enter presses the button
    expect(within(dialog).getByRole("radio", { name: /Replace the original/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("says a picture's see-through parts go white as JPEG", async () => {
    engine({ "POST /pictures/11/plan": plan({ seeThrough: true, format: "PNG" }) });
    renderPicture();
    await chooseTv();
    await openSave();
    const dialog = await screen.findByRole("dialog", { name: "Save Harbour at dusk" });
    await within(dialog).findByRole("radio", { name: /As a new picture/ });
    expect(within(dialog).queryByText(/see-through/)).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("radio", { name: "JPEG" }));

    expect(
      within(dialog).getByText("JPEG has no see-through parts, so they'll be white."),
    ).toBeInTheDocument();
  });

  it("says what a finished job saved, and why one didn't work", async () => {
    engine({
      "/jobs": [
        job({
          state: "done",
          progress: 1,
          finishedAt: new Date().toISOString(),
          result: "D:\\Pictures\\Phone\\Harbour at dusk (TV 8K).jpg",
          resultName: "Harbour at dusk (TV 8K).jpg",
          resultPicture: { id: 41, version: "v41" },
        }),
      ],
    });
    renderPicture();

    expect(await screen.findByText("Harbour at dusk (TV 8K).jpg")).toBeInTheDocument();
    expect(
      screen.getByText(/As a new picture in Phone\. History can take it away\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open it" })).toHaveAttribute(
      "href",
      "/library/pictures/41",
    );
    const tools = screen.getByRole("complementary", { name: "Tools" });
    expect(within(tools).getByRole("button", { name: "Show in folder" })).toBeInTheDocument();
  });

  it("compares before and after at full detail when zoomed in", async () => {
    const fetch = engine();
    renderPicture();
    await chooseTv();
    await screen.findByText(/A TV is 16:9/);

    fireEvent.click(screen.getByRole("radio", { name: "100%" }));

    expect(await screen.findByRole("img", { name: "After · TV 8K" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Before" })).toBeInTheDocument();
    const slider = screen.getByRole("slider", { name: "Drag to compare before and after" });
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(slider).toHaveAttribute("aria-valuenow", "45");
    const asked = sent(fetch, "POST", "/pictures/11/preview") as { side: string; region: object }[];
    expect(asked.map((each) => each.side).sort()).toEqual(["after", "before"]);
    // Centred on the point the crop is around, in the picture made.
    expect(asked[0]?.region).toEqual({ x: 3340, y: 1592, width: 1000, height: 560 });
    expect(await screen.findByText("Preview made in 1.2 s")).toBeInTheDocument();
  });

  it("asks for previews as the plan decided, so they follow it when it changes", async () => {
    const fetch = engine();
    renderPicture();
    await chooseTv();
    await screen.findByText(/A TV is 16:9/);

    fireEvent.click(screen.getByRole("radio", { name: "100%" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/preview")).toHaveLength(2));
    expect(sent(fetch, "POST", "/pictures/11/preview")[0]).toMatchObject({
      recipe: { size: { size: "tv-8k", kind: "photo", quality: "fast", focus: [0.5, 0.45] } },
    });
  });

  it("waits for the model's download before showing after, but shows before", async () => {
    let downloaded = false;
    const best = plan({
      quality: "best",
      model: "RealESRGAN x4plus",
      needs: [{ id: "realesrgan-x4plus", name: "RealESRGAN x4plus", size: 67_087_820 }],
    });
    const fetch = engine({
      "POST /pictures/11/plan": () => (downloaded ? plan({ quality: "best" }) : best),
    });
    renderPicture();
    await chooseTv();
    await screen.findByText(/A TV is 16:9/);
    fireEvent.click(screen.getByRole("radio", { name: "100%" }));

    expect(await screen.findByRole("img", { name: "Before" })).toBeInTheDocument();
    const sides = () =>
      (sent(fetch, "POST", "/pictures/11/preview") as { side: string }[]).map((each) => each.side);
    expect(sides()).toEqual(["before"]);
    expect(
      screen.getByText("After shows once RealESRGAN x4plus is downloaded"),
    ).toBeInTheDocument();

    downloaded = true;
    fireEvent.click(screen.getByRole("button", { name: "Use Fast" })); // a new plan, as after any change
    await waitFor(() => expect(sides()).toContain("after"));
  });

  it("keeps a part previewed at 100% within what one preview may be on a big screen", async () => {
    const fetch = engine();
    vi.stubGlobal("devicePixelRatio", 2);
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private readonly told: ResizeObserverCallback) {}
        observe() {
          const entry = { contentRect: { width: 2400, height: 1300 } } as ResizeObserverEntry;
          this.told([entry], this as unknown as ResizeObserver);
        }
        disconnect() {}
        unobserve() {}
      },
    );
    renderPicture();
    await chooseTv();
    await screen.findByText(/A TV is 16:9/);

    fireEvent.click(screen.getByRole("radio", { name: "100%" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/preview")).toHaveLength(2));
    const asked = sent(fetch, "POST", "/pictures/11/preview") as {
      region: { width: number; height: number };
    }[];
    for (const each of asked) {
      expect(each.region.width * each.region.height).toBeLessThanOrEqual(4_000_000);
      expect(each.region.width / each.region.height).toBeCloseTo(2400 / 1300, 1);
    }
    const after = await screen.findByRole("img", { name: "After · TV 8K" });
    expect(Number.parseFloat(after.style.width)).toBeCloseTo(2400, -1); // it fills the stage
  });

  it("moves round the part compared with the arrow keys", async () => {
    const fetch = engine();
    renderPicture();
    await chooseTv();
    await screen.findByText(/A TV is 16:9/);
    fireEvent.click(screen.getByRole("radio", { name: "100%" }));
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/11/preview")).toHaveLength(2));

    const stage = screen.getByRole("group", { name: /Move round the picture/ });
    fireEvent.keyDown(stage, { key: "ArrowRight" });

    await waitFor(() => {
      const asked = sent(fetch, "POST", "/pictures/11/preview") as { region: { x: number } }[];
      expect(asked.at(-1)?.region.x).toBeGreaterThan(3340);
    });
  });

  it("steps the crop's point from where it was last put, not the plan before", async () => {
    const fetch = engine({ "POST /pictures/11/plan": plan() }); // the plan never catches up
    renderPicture();
    await chooseTv();

    const point = await screen.findByRole("button", {
      name: "The point the crop is around: drag it to move it",
    });
    fireEvent.keyDown(point, { key: "ArrowUp" });
    fireEvent.keyDown(point, { key: "ArrowUp" });

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        size: { focus: [0.5, 0.41] },
      }),
    );
  });

  it("starts the next picture with what Mado sees in it, keeping the size", async () => {
    const sail = PICTURES[1] as (typeof PICTURES)[number];
    const fetch = engine({
      "/pictures/11/neighbours": { before: [], after: [sail] },
      "/pictures/12": { ...details, ...sail },
      "/pictures/12/neighbours": { before: [DUSK], after: [] },
      "/pictures/12/view": blob,
      "POST /pictures/12/plan": () => new Response("{}", { status: 500 }),
    });
    renderPicture();
    await chooseTv();
    fireEvent.click(await screen.findByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("radio", { name: "Drawing" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        size: { kind: "drawing" },
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Next picture" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/12/plan").at(-1)).toMatchObject({
        size: { size: "tv-8k", kind: null, focus: null },
      }),
    );
    // Its plan failed: the last picture's isn't shown in its place, nor asked for again.
    await waitFor(() =>
      expect(screen.queryByText(/A TV is 16:9 and this picture is 4:3/)).not.toBeInTheDocument(),
    );
    expect(sent(fetch, "POST", "/pictures/12/plan")).toHaveLength(1);
  });
});

describe("A picture replaced in another format", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  const replaced = job({
    how: "replace",
    state: "done",
    progress: 1,
    finishedAt: new Date().toISOString(),
    result: "D:\\Pictures\\Phone\\Harbour at dusk.jpg",
    resultName: "Harbour at dusk.jpg",
    resultPicture: { id: 42, version: "v42" },
  });

  it("offers the picture that took its place", async () => {
    engine({ "/jobs": [replaced] });
    renderPicture();

    expect(await screen.findByRole("link", { name: "Open it" })).toHaveAttribute(
      "href",
      "/library/pictures/42",
    );
  });

  it("says Mado replaced it once the original's gone from the library", async () => {
    engine({
      "/jobs": [replaced],
      "/pictures/11": () =>
        Response.json({ detail: "That picture isn't in your library any more." }, { status: 404 }),
    });
    renderPicture();

    expect(
      await screen.findByText(/Mado replaced it with Harbour at dusk\.jpg/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Mado didn't change it/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Harbour at dusk.jpg" })).toHaveAttribute(
      "href",
      "/library/pictures/42",
    );
  });
});

describe("A picture just made", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("offers Open it once the library has read it", async () => {
    let read = false;
    const done = {
      state: "done" as const,
      progress: 1,
      finishedAt: new Date().toISOString(),
      result: "D:\\Pictures\\Phone\\Harbour at dusk (TV 8K).jpg",
      resultName: "Harbour at dusk (TV 8K).jpg",
    };
    engine({
      "/jobs": () => [job({ ...done, resultPicture: read ? { id: 41, version: "v41" } : null })],
    });
    renderPicture();

    expect(await screen.findByText("Harbour at dusk (TV 8K).jpg")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open it" })).not.toBeInTheDocument();
    read = true; // the library reads it a moment later
    expect(await screen.findByRole("link", { name: "Open it" }, { timeout: 4000 })).toHaveAttribute(
      "href",
      "/library/pictures/41",
    );
  });
});

describe("A part of the picture made", () => {
  it("is centred where asked, as far as the picture's edges let it", () => {
    const made: Pick<Plan, "width" | "height"> = { width: 7680, height: 4320 };

    expect(regionAt([0.5, 0.5], 1000, 560, made)).toEqual({
      x: 3340,
      y: 1880,
      width: 1000,
      height: 560,
    });
    expect(regionAt([0, 1], 1000, 560, made)).toEqual({ x: 0, y: 3760, width: 1000, height: 560 });
  });
});
