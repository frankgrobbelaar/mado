import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import { fakeEngine, PICKED, READY, RECIPE, SETTINGS, SIZES, WATCH_FOLDERS } from "@/test/engine";
import { RecipesPage } from "./recipes-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function Where() {
  const location = useLocation();
  return <p>The batch from {JSON.stringify(location.state)}</p>;
}

function renderRecipes(picked: string[] = []) {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "pick_pictures") return picked;
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/recipes"]}>
          <Routes>
            <Route path="/recipes" element={<RecipesPage />} />
            <Route path="/batch" element={<Where />} />
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
  "/recipes": [RECIPE],
  "/watch-folders": WATCH_FOLDERS,
  "/settings": SETTINGS,
  "/sizes": SIZES,
};

describe("RecipesPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists each recipe's steps as a line, and how often and when it was used", async () => {
    fakeEngine(ENGINE);
    renderRecipes();

    const recipes = await screen.findByRole("region", { name: "Recipes" });
    expect(recipes).toHaveTextContent("Holiday prints");
    expect(recipes).toHaveTextContent("Used 3 times · tonight");
    expect(recipes).toHaveTextContent("TV 8K→Warm film 60→JPEG 95 into Edited");
  });

  it("says what each watch folder does and did, and turns one off", async () => {
    const fetch = fakeEngine({ ...ENGINE, "PUT /watch-folders/1": WATCH_FOLDERS[0] });
    renderRecipes();

    const watch = await screen.findByRole("region", { name: "Watch folders" });
    expect(watch).toHaveTextContent("D:\\Pictures\\To TV → Holiday prints → To TV\\Done");
    expect(watch).toHaveTextContent("Ran today 14:02 on 6 pictures");
    expect(watch).toHaveTextContent("F: isn't connected; it waits for it");
    expect(watch).toHaveTextContent("Off");
    fireEvent.click(within(watch).getByRole("switch", { name: "Watch D:\\Pictures\\To TV" }));

    await waitFor(() =>
      expect(sent(fetch, "PUT", "/watch-folders/1")).toEqual([
        {
          path: "D:\\Pictures\\To TV",
          recipe: 1,
          results: "D:\\Pictures\\To TV\\Done",
          watching: false,
        },
      ]),
    );
  });

  it("says why a watch folder's new pictures couldn't go in the queue", async () => {
    const why = "It needs a model Mado downloads the first time it's asked for: download it first.";
    fakeEngine({ ...ENGINE, "/watch-folders": [{ ...WATCH_FOLDERS[0], problem: why }] });
    renderRecipes();

    const watch = await screen.findByRole("region", { name: "Watch folders" });
    expect(await within(watch).findByText(why)).toBeInTheDocument();
    expect(watch).not.toHaveTextContent("Ran today");
  });

  it("uses a recipe on pictures picked from the PC, in Many at once", async () => {
    fakeEngine({ ...ENGINE, "POST /batches/pictures": PICKED });
    renderRecipes(["D:\\Pictures\\Holiday\\Warm dunes.jpg"]);

    fireEvent.pointerDown(await screen.findByRole("button", { name: "Use on pictures…" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Pick pictures…" })).click();

    expect(await screen.findByText(/The batch from/)).toHaveTextContent('"recipe":1');
  });

  it("keeps a new recipe with its steps", async () => {
    const fetch = fakeEngine({ ...ENGINE, "POST /recipes": RECIPE });
    renderRecipes();

    fireEvent.click(await screen.findByRole("button", { name: "New recipe" }));
    const card = await screen.findByRole("dialog", { name: "New recipe" });
    fireEvent.change(within(card).getByLabelText("Its name"), {
      target: { value: "Phone wallpapers" },
    });
    fireEvent.pointerDown(within(card).getByRole("button", { name: "Add a step" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Make it for a screen" })).click();
    const sizes = await screen.findByRole("dialog", { name: "Make them for a screen" });
    fireEvent.click(await within(sizes).findByRole("button", { name: /^Phone/ }));
    fireEvent.click(within(sizes).getByRole("button", { name: "Done" }));
    fireEvent.click(within(card).getByRole("button", { name: "Keep it" }));

    await waitFor(() => expect(sent(fetch, "POST", "/recipes")).toHaveLength(1));
    const [body] = sent(fetch, "POST", "/recipes");
    expect(body.name).toBe("Phone wallpapers");
    expect(body.steps).toEqual([
      { step: "size", size: "phone", shape: "crop", kind: null, quality: null, clean: true },
    ]);
    expect(body.saving.folder).toBe("Edited");
  });
});
