import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import {
  batchPicture,
  fakeEngine,
  PICKED,
  READY,
  RECIPE,
  rawReader,
  SAMPLES,
  SETTINGS,
  SIZES,
  STYLES,
  takes,
} from "@/test/engine";
import { BatchPage } from "./batch-page";
import type { BatchStart } from "./open";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function renderBatch(start: BatchStart | null) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[{ pathname: "/batch", state: start }]}>
          <Routes>
            <Route path="/batch" element={<BatchPage />} />
            <Route path="/queue" element={<p>The queue</p>} />
            <Route path="/library" element={<p>The library</p>} />
            <Route path="/" element={<p>Home</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls
    .filter(([input, init]) => (init?.method ?? "GET") === method && String(input).endsWith(path))
    .map(([, init]) => JSON.parse(String(init?.body ?? "null")));
}

const ENGINE = {
  "/settings": SETTINGS,
  "/recipes": [RECIPE],
  "/sizes": SIZES,
  "POST /batches/takes": takes(),
  "POST /batches/samples": SAMPLES,
  "/batches/samples/abc123": SAMPLES,
  "DELETE /batches/samples/abc123": null,
  "POST /batches": { id: 7 },
};

describe("BatchPage", () => {
  beforeEach(() => {
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

  it("goes back Home to change which, for pictures pasted or opened from File Explorer", async () => {
    fakeEngine(ENGINE);
    renderBatch({ pick: { how: "opened", paths: ["D:\\Pictures\\Holiday"] }, picked: PICKED });

    fireEvent.click(await screen.findByRole("button", { name: "Change which" }));

    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("starts from a recipe and says its steps, what it takes and where they go, as the board does", async () => {
    fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED, recipe: 1 });

    expect(
      await screen.findByText(
        (_, element) =>
          element?.tagName === "P" &&
          element.textContent === "3 pictures ticked in Holiday · 8.1 MB",
      ),
    ).toBeInTheDocument();
    const steps = screen.getByRole("region", { name: "Steps, in order" });
    expect(await within(steps).findByText("From the recipe")).toBeInTheDocument();
    expect(
      within(steps)
        .getAllByRole("listitem")
        .map((step) => step.textContent),
    ).toEqual([
      expect.stringContaining("Make it for a screen"),
      expect.stringContaining("A look"),
      expect.stringContaining("Save"),
    ]);
    expect(within(steps).getByRole("button", { name: "Holiday prints" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const cost = screen.getByRole("region", { name: "What it takes" });
    expect(await within(cost).findByText("about 32 min")).toBeInTheDocument();
    expect(within(cost).getByText("about 480 MB")).toBeInTheDocument();
    expect(within(cost).getByText("412 GB")).toBeInTheDocument();
    expect(
      within(cost).getByText("Timed on this PC's graphics card, one picture at a time."),
    ).toBeInTheDocument();
    expect(screen.getByText("Holiday › Edited")).toBeInTheDocument();
  });

  it("sees three first, made in full, with their sizes before and after", async () => {
    const fetch = fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED, recipe: 1 });

    const first = screen.getByRole("region", { name: "See it first" });
    expect(await within(first).findByText("1 min 50 s", {}, { timeout: 3000 })).toBeInTheDocument();
    // The arrow is drawn, not typed (IBM Plex as Mado bundles it has none), and read as "to".
    expect(first).toHaveTextContent("2.7 MB to 9.8 MB");
    expect(first).not.toHaveTextContent("→");
    const [asked] = sent(fetch, "POST", "/batches/samples");
    expect(asked.round).toBe(0);
    expect(asked.steps.map((step: { step: string }) => step.step)).toEqual(["size", "look"]);
  });

  it("puts them in the queue for tonight, keeping what See it first made", async () => {
    const fetch = fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED, recipe: 1 });

    fireEvent.click(await screen.findByRole("radio", { name: "Tonight, from 23:00" }));
    await screen.findByText("1 min 50 s", {}, { timeout: 3000 });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Put 3 in the queue" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Put 3 in the queue" }));

    expect(await screen.findByText("The queue")).toBeInTheDocument();
    const [body] = sent(fetch, "POST", "/batches");
    expect(body).toMatchObject({
      name: "Holiday prints",
      source: "Holiday",
      starts: "tonight",
      recipe: 1,
      sample: "abc123",
    });
    expect(body.pictures).toHaveLength(3);
  });

  it("changes a step with the Size tab's choices", async () => {
    const fetch = fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });

    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Make it for a screen" })).click();
    const card = await screen.findByRole("dialog", { name: "Make them for a screen" });
    fireEvent.click(await within(card).findByRole("button", { name: /^Phone/ }));
    fireEvent.click(within(card).getByRole("button", { name: "Done" }));

    await waitFor(() => {
      const asked = sent(fetch, "POST", "/batches/takes").at(-1);
      expect(asked?.steps).toEqual([
        { step: "size", size: "phone", shape: "crop", kind: null, quality: null, clean: true },
      ]);
    });
    expect(screen.queryByText("From the recipe")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep as a recipe…" })).toBeInTheDocument();
  });

  it("cuts out each picture's subject as a step made first, saving as PNG to keep its nothing", async () => {
    const fetch = fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });

    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Cut out the subject" })).click();
    const card = await screen.findByRole("dialog", { name: "Cut out the subject" });
    fireEvent.click(within(card).getByRole("radio", { name: "Best" }));
    fireEvent.click(within(card).getByRole("button", { name: "Done" }));

    await waitFor(() => {
      const asked = sent(fetch, "POST", "/batches/takes").at(-1);
      expect(asked?.steps).toEqual([
        { step: "cutout", quality: "best", behind: "nothing", colour: null },
      ]);
      expect(asked?.saving.format).toBe("PNG");
    });
    fireEvent.click(screen.getByRole("button", { name: "Change save" }));
    const saving = await screen.findByRole("dialog", { name: "How they're saved" });
    expect(within(saving).queryByRole("radio", { name: "JPEG" })).toBeNull();
    expect(within(saving).getByRole("radio", { name: "WebP" })).toBeInTheDocument();
  });

  it("fixes each picture as a step made before the size, as the Fix tab chooses", async () => {
    const fetch = fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });

    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Fix: noise, blur, JPEG blocks, dark" })).click();
    const card = await screen.findByRole("dialog", { name: "Fix them" });
    expect(within(card).getByRole("switch", { name: "Noise" })).toBeChecked();
    fireEvent.click(within(card).getByRole("switch", { name: "Dark photo" }));
    fireEvent.click(within(card).getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/batches/takes").at(-1)?.steps).toEqual([
        {
          step: "fix",
          noise: { strength: 1 },
          blur: null,
          jpeg: null,
          dark: { contrast: 0 },
        },
      ]),
    );
  });

  it("paints each picture in a style as a step made after the size, before the look", async () => {
    const fetch = fakeEngine({ ...ENGINE, "/styles": STYLES });
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED, recipe: 1 });
    const steps = screen.getByRole("region", { name: "Steps, in order" });
    expect(await within(steps).findByText("From the recipe")).toBeInTheDocument();

    fireEvent.pointerDown(within(steps).getByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "A painting style" })).click();
    const card = await screen.findByRole("dialog", { name: "Paint them in a style" });
    fireEvent.click(await within(card).findByRole("button", { name: "After Hokusai" }));
    fireEvent.click(within(card).getByRole("switch", { name: "Keep each picture's own colours" }));
    fireEvent.keyDown(within(card).getByRole("slider", { name: "Style strength" }), {
      key: "PageDown",
    });
    expect(within(card).getByRole("button", { name: "Lantern glow" })).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/batches/takes").at(-1)?.steps).toEqual([
        RECIPE.steps[0],
        { step: "paint", style: "hokusai", strength: 0.9, colours: true, setting: null },
        RECIPE.steps[1],
      ]),
    );
  });

  it("gives a classic style its one setting in a batch, without colours to keep", async () => {
    const fetch = fakeEngine({ ...ENGINE, "/styles": STYLES });
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });

    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "A painting style" })).click();
    const card = await screen.findByRole("dialog", { name: "Paint them in a style" });
    fireEvent.click(await within(card).findByRole("button", { name: "Pencil sketch" }));
    expect(within(card).queryByRole("switch")).toBeNull();
    fireEvent.keyDown(within(card).getByRole("slider", { name: "Darkness" }), { key: "PageUp" });
    fireEvent.click(within(card).getByRole("button", { name: "Done" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/batches/takes").at(-1)?.steps).toEqual([
        { step: "paint", style: "pencil", strength: 1, colours: false, setting: 60 },
      ]),
    );
  });

  it("takes each JPEG's blocks out as hard as it was squeezed, with no strength to set", async () => {
    const fetch = fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });
    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Fix: noise, blur, JPEG blocks, dark" })).click();
    const card = await screen.findByRole("dialog", { name: "Fix them" });

    fireEvent.click(within(card).getByRole("switch", { name: "JPEG blocks" }));

    expect(
      within(card).queryByRole("slider", { name: "How hard JPEG blocks come out" }),
    ).toBeNull();
    expect(within(card).getByText(/as hard as it was squeezed, read from the file/)).toBeVisible();
    fireEvent.click(within(card).getByRole("button", { name: "Done" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/batches/takes").at(-1)?.steps).toEqual([
        {
          step: "fix",
          noise: { strength: 1 },
          blur: null,
          jpeg: { quality: null, strength: null },
          dark: null,
        },
      ]),
    );
  });

  it("says on the Size card when the Fix step cleans first, so Fast doesn't again", async () => {
    fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });
    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Fix: noise, blur, JPEG blocks, dark" })).click();
    fireEvent.click(
      within(await screen.findByRole("dialog", { name: "Fix them" })).getByRole("button", {
        name: "Done",
      }),
    );
    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Make it for a screen" })).click();
    const card = await screen.findByRole("dialog", { name: "Make them for a screen" });

    fireEvent.click(await within(card).findByRole("button", { name: /^Phone/ }));

    expect(
      within(card).getByText(
        "The Fix step takes noise and blocks out first, so Fast doesn't clean them again.",
      ),
    ).toBeVisible();
    expect(within(card).queryByRole("switch", { name: "Clean noise and blocks first" })).toBeNull();
  });

  it("says what each download it waits for is for, offering Fast only for the photo model", async () => {
    fakeEngine({
      ...ENGINE,
      "/tools": [],
      "POST /batches/takes": takes({
        needs: [
          { id: "scunet", name: "SCUNet", size: 72_932_271 },
          { id: "birefnet-lite", name: "BiRefNet lite", size: 224_006_154 },
        ],
      }),
    });
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED, recipe: 1 });

    expect(await screen.findByText(/Noise comes out with SCUNet, an AI model/)).toBeInTheDocument();
    expect(
      screen.getByText(/Cutting out at Best is BiRefNet lite, an AI model/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Best for photos is/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Use Fast" })).toBeNull();
  });

  it("takes the fixes out once every fix in them is off", async () => {
    const fetch = fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });
    fireEvent.pointerDown(await screen.findByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Fix: noise, blur, JPEG blocks, dark" })).click();
    const card = await screen.findByRole("dialog", { name: "Fix them" });

    fireEvent.click(within(card).getByRole("switch", { name: "Noise" }));
    fireEvent.click(within(card).getByRole("button", { name: "Done" }));

    expect(
      await screen.findByText(/Pick what to do: cut out their subject, fix them/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetch).toHaveBeenCalled();
  });

  it("asks once for the folder new pictures go into", async () => {
    fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });

    fireEvent.click(await screen.findByRole("button", { name: "Change save" }));
    const card = await screen.findByRole("dialog", { name: "How they're saved" });
    fireEvent.click(within(card).getByRole("button", { name: "Choose…" }));

    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("pick_folder", expect.anything()),
    );
    const asked = shell.invoke.mock.calls.filter(([command]) => command === "pick_folder");
    expect(asked).toHaveLength(1);
  });

  it("says which were left out, and why", async () => {
    fakeEngine(ENGINE);
    renderBatch({
      pick: { how: "ticked", ids: [1, 2, 3, 4] },
      picked: {
        ...PICKED,
        leftOut: [{ name: "Old pier.tif", why: "It won't open.", waiting: false }],
      },
    });

    expect(await screen.findByRole("note")).toHaveTextContent(
      "Left out, as they are: Old pier.tif (It won't open).",
    );
    expect(screen.queryByRole("region", { name: "Mado's RAW reader" })).not.toBeInTheDocument();
  });

  it("leaves camera RAW out while Mado's RAW reader comes, showing it come, then asks again", async () => {
    const waiting =
      "It's a camera RAW, and Mado is getting its RAW reader: it joins once that's here.";
    let reader = rawReader("downloading", 1_611_429);
    let leftOut = [{ name: "Green sky.CR3", why: waiting, waiting: true }];
    const fetch = fakeEngine({
      ...ENGINE,
      "/tools": () => [reader],
      "POST /batches/pictures": () => ({ ...PICKED, leftOut }),
    });
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3, 4] } });

    const note = await screen.findByRole("region", { name: "Mado's RAW reader" });
    expect(within(note).getByText("Downloading · 46%")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Green sky.CR3 (It's a camera RAW");

    reader = rawReader("ready");
    leftOut = [];
    await waitFor(
      () =>
        expect(
          fetch.mock.calls.filter(([url]) => String(url).endsWith("/batches/pictures")),
        ).toHaveLength(2),
      { timeout: 3000 },
    );
    await waitFor(() => expect(screen.queryByRole("note")).not.toBeInTheDocument());
  });

  it("asks again for camera RAW Mado is still reading once its reader is here", async () => {
    let leftOut = [
      {
        name: "Green sky.CR3",
        why: "It's a camera RAW Mado is reading now: it joins once it's read.",
        waiting: true,
      },
    ];
    const fetch = fakeEngine({
      ...ENGINE,
      "/tools": [rawReader("ready")],
      "POST /batches/pictures": () => ({ ...PICKED, leftOut }),
    });
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3, 9] } });
    const askedFor = () =>
      fetch.mock.calls.filter(([url]) => String(url).endsWith("/batches/pictures")).length;

    expect(await screen.findByRole("note")).toHaveTextContent("Mado is reading now");
    expect(screen.queryByRole("region", { name: "Mado's RAW reader" })).not.toBeInTheDocument();
    leftOut = []; // the scan read it
    await waitFor(() => expect(askedFor()).toBeGreaterThan(1), { timeout: 5000 });
    await waitFor(() => expect(screen.queryByRole("note")).not.toBeInTheDocument());
    const settled = askedFor();
    await act(async () => {
      await new Promise((done) => setTimeout(done, 3500));
    });
    expect(askedFor()).toBe(settled); // none wait: it stops asking
  });

  it("saves a batch with camera RAW as new pictures, saying why Replace isn't offered", async () => {
    fakeEngine({ ...ENGINE, "/settings": { ...SETTINGS, saveFirst: "replace" } });
    renderBatch({
      pick: { how: "ticked", ids: [1, 2, 3] },
      picked: { ...PICKED, pictures: [...PICKED.pictures, batchPicture(9, "Green sky.CR3")] },
    });

    const saving = await screen.findByRole("region", { name: "Saving" });
    expect(within(saving).queryByText("Replace the originals")).toBeNull();
    expect(within(saving).getByText(/Replacing the originals isn't offered/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Change save" }));
    const card = await screen.findByRole("dialog", { name: "How they're saved" });
    expect(within(card).queryByText("Replace the originals")).toBeNull();
    expect(within(card).getByText(/Replacing the originals isn't offered/)).toBeInTheDocument();
    expect(within(card).getByText("Where they go")).toBeInTheDocument();
  });

  it("says only that the originals stay, till it knows where new pictures go", async () => {
    fakeEngine(ENGINE);
    renderBatch({ pick: { how: "ticked", ids: [1, 2, 3] }, picked: PICKED });

    const saving = await screen.findByRole("region", { name: "Saving" });
    expect(within(saving).getByText("The originals stay as they are.")).toBeInTheDocument();
    expect(saving).not.toHaveTextContent("Into .");
  });

  it("asks for the pictures first when it has none", async () => {
    fakeEngine(ENGINE);
    renderBatch(null);

    expect(
      await screen.findByRole("heading", { name: "Pick the pictures first" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pick pictures" })).toBeInTheDocument();
  });
});
