import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import { fakeEngine, PICKED, READY, RECIPE, SAMPLES, SETTINGS, SIZES, takes } from "@/test/engine";
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
        leftOut: [{ name: "Green sky.CR3", why: "Mado can't read camera RAW yet." }],
      },
    });

    expect(await screen.findByRole("note")).toHaveTextContent(
      "Left out, as they are: Green sky.CR3 (Mado can't read camera RAW yet).",
    );
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
