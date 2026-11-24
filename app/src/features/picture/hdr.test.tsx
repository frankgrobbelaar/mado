import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type GainMap, type PictureDetails, type Plan } from "@/lib/engine";
import {
  FOLDERS,
  fakeEngine,
  job,
  PICTURES,
  pictureDetails,
  plan,
  READY,
  SETTINGS,
  SIZES,
} from "@/test/engine";
import { PicturePage } from "./picture-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

/** Little sail, a phone's HDR photo: a JPEG with a gain map a quarter of its size. */
const SAIL = PICTURES[1] as (typeof PICTURES)[number];
const GAIN: GainMap = {
  readable: true,
  stops: 3,
  baseIsHdr: false,
  colour: false,
  width: 1008,
  height: 756,
  why: null,
};

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

type Fetch = ReturnType<typeof fakeEngine>;

function engine(
  details: PictureDetails,
  made: Partial<Plan>,
  answers: Record<string, unknown> = {},
) {
  return fakeEngine({
    "/folders": FOLDERS,
    "/settings": SETTINGS,
    "/pictures/12": details,
    "/pictures/12/neighbours": { before: [], after: [] },
    "/pictures/12/view": blob,
    "/pictures/12/full": blob,
    "/sizes": SIZES,
    "POST /screens": [],
    "POST /pictures/12/plan": plan({ format: "JPEG", formatQuality: 92, ...made }),
    "POST /pictures/12/saving": {
      name: "Little sail (2).jpg",
      folder: "D:\\Pictures\\Phone",
      taken: null,
      takenAt: null,
      bytes: 3_000_000,
      colour: "Display P3",
    },
    "POST /pictures/12/make": job({ state: "queued", progress: 0 }),
    "/jobs": [],
    "/tools": [],
    ...answers,
  });
}

function renderPicture() {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "screens") return [];
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/library/pictures/12?folder=1"]}>
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
  return screen.findByRole("dialog", { name: "Save Little sail" });
}

describe("An HDR photo and saving as it is", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    shell.invoke.mockReset();
  });

  it("says it's HDR where it says what kind it is", async () => {
    engine(pictureDetails({ ...SAIL, hdr: true }, { gainMap: GAIN }), {});
    renderPicture();

    const facts = await screen.findByText(/^JPEG · HDR · 4032 × 3024/);
    expect(facts).toHaveAttribute(
      "title",
      expect.stringContaining("on an HDR screen it goes up to 3 stops (8 times) brighter"),
    );
  });

  it("says when its gain map is one Mado can't read, and shows it as an ordinary picture", async () => {
    const unread: GainMap = {
      ...GAIN,
      readable: false,
      stops: null,
      why: "Its gain map is version 2.0, which Mado doesn't know yet.",
    };
    engine(pictureDetails(SAIL, { gainMap: unread }), {});
    renderPicture();

    expect(
      await screen.findByText(
        "Its gain map is version 2.0, which Mado doesn't know yet. Mado shows and saves it as an ordinary picture.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/^JPEG · 4032 × 3024/)).toBeInTheDocument(); // no HDR in its facts
  });

  it("keeps its HDR at Save, and says a format that can't hold it before Save", async () => {
    const fetch = engine(pictureDetails({ ...SAIL, hdr: true }, { gainMap: GAIN }), {
      hdr: "kept",
      asIs: true,
    });
    renderPicture();

    const dialog = await openSave();
    const kept = await within(dialog).findByRole("checkbox", { name: "Its HDR (the gain map)" });
    expect(kept).toBeChecked();
    fireEvent.click(within(dialog).getByRole("radio", { name: "PNG" }));
    expect(kept).toBeDisabled();
    expect(kept).not.toBeChecked();
    expect(
      within(dialog).getByText(
        "PNG has no room for a gain map, so saved as PNG it's an ordinary picture. JPEG and AVIF keep it.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("radio", { name: /JPEG/ }));
    expect(kept).toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/12/make")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/12/make")[0]).toMatchObject({
      saving: { how: "new", format: "JPEG", keepHdr: true },
    });
  });

  it("says why a recipe leaves no HDR", async () => {
    engine(pictureDetails({ ...SAIL, hdr: true }, { gainMap: GAIN }), {
      hdr: "lost",
      hdrWhy:
        "A pencil sketch is paper and lines, with no light in it to brighten, so it's an ordinary picture.",
      asIs: true,
    });
    renderPicture();

    const dialog = await openSave();
    expect(
      await within(dialog).findByRole("checkbox", { name: "Its HDR (the gain map)" }),
    ).toBeDisabled();
    expect(within(dialog).getByText(/A pencil sketch is paper and lines/)).toBeInTheDocument();
  });

  it("saves any picture as it is with nothing chosen: a new picture, never in its place", async () => {
    const fetch = engine(pictureDetails(SAIL), {
      asIs: true,
      label: "",
      width: 4032,
      height: 3024,
    });
    renderPicture();

    expect(
      await screen.findByText(
        "Save keeps it as it is, in the format you pick; pick a screen or a print to make it for one.",
      ),
    ).toBeInTheDocument();
    const dialog = await openSave();
    expect(
      await within(dialog).findByText(/Replacing the original isn't offered/),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/As it is,/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("radio", { name: /Replace the original/ })).toBeNull();
    expect(
      within(dialog).getByText(/Replacing the original isn't offered: saved as it is, it's a copy/),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "It's a JPEG already: this saves a fresh copy beside it, at the quality you pick.",
      ),
    ).toBeInTheDocument();
    expect(within(dialog).queryByRole("checkbox", { name: /Its HDR/ })).toBeNull(); // not an HDR photo
    // It can only be a new picture: no way of the owner's for Save to keep.
    expect(within(dialog).queryByRole("checkbox", { name: "Always save this way" })).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetch, "POST", "/pictures/12/make")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/12/make")[0]).toMatchObject({
      recipe: { edit: null, size: null, look: null },
      saving: { how: "new", format: "JPEG" },
    });
  });
});
