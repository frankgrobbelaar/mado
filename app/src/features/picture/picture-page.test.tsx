import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type PictureDetails, type PictureItem } from "@/lib/engine";
import { FOLDERS, fakeEngine, PICTURES, READY } from "@/test/engine";
import { PicturePage } from "./picture-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function Address() {
  const location = useLocation();
  return <p data-testid="address">{`${location.pathname}${location.search}`}</p>;
}

function renderPicture(at: string) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[at]}>
          <Routes>
            <Route path="/library/pictures/:id" element={<PicturePage />} />
            <Route path="/library" element={<p>The library</p>} />
          </Routes>
          <Address />
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

/** A picture's details, from one in the grid. */
function details(item: PictureItem, overrides: Partial<PictureDetails> = {}): PictureDetails {
  return {
    ...item,
    folderId: 1,
    folder: "D:\\Pictures\\Phone",
    dir: "",
    modifiedAt: item.takenAt,
    takenFrom: "camera",
    camera: "Pixelworks PW-7 Pro",
    orientation: 1,
    located: true,
    damaged: false,
    problem: null,
    ...overrides,
  };
}

const [DUSK, SAIL, MEADOW, SNOWFIELD] = PICTURES as [
  PictureItem,
  PictureItem,
  PictureItem,
  PictureItem,
];
const RAW = PICTURES[5] as PictureItem;
const BROKEN = PICTURES[6] as PictureItem;

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

/** Little sail opened from Phone: Harbour at dusk before it, Spring meadow and Snowfield after. */
function engine(answers: Record<string, unknown> = {}) {
  return fakeEngine({
    "/folders": FOLDERS,
    "/pictures/12": details(SAIL),
    "/pictures/12/neighbours": { before: [DUSK], after: [MEADOW, SNOWFIELD] },
    "/pictures/11": details(DUSK),
    "/pictures/11/neighbours": { before: [], after: [SAIL, MEADOW] },
    "/pictures/13": details(MEADOW),
    "/pictures/13/neighbours": { before: [DUSK, SAIL], after: [SNOWFIELD] },
    "/pictures/12/view": blob,
    "/pictures/12/full": blob,
    "/pictures/11/view": blob,
    "/pictures/13/view": blob,
    ...Object.fromEntries(PICTURES.map((each) => [`/pictures/${each.id}/thumbnail`, blob])),
    ...answers,
  });
}

function asked(fetch: ReturnType<typeof fakeEngine>, path: string) {
  return fetch.mock.calls.filter(([input]) => new URL(String(input)).pathname === path);
}

describe("PicturePage", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows the picture large, its facts, its neighbours and its tools", async () => {
    const fetch = engine();
    renderPicture("/library/pictures/12?folder=1");

    expect(
      await screen.findByRole("heading", { name: "Little sail", level: 1 }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("JPEG · 4032 × 3024 · 3.1 MB · 14 Nov 2026, 16:05"),
    ).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Little sail" })).toHaveAttribute(
      "src",
      "blob:made-up",
    );
    expect(await screen.findByRole("link", { name: "Phone" })).toHaveAttribute(
      "href",
      "/library?folder=1",
    );
    const strip = await screen.findByRole("navigation", { name: "Pictures in Phone" });
    expect(
      within(strip)
        .getAllByRole("link")
        .map((link) => link.getAttribute("aria-label")),
    ).toEqual(["Harbour at dusk", "Little sail", "Spring meadow", "Snowfield"]);
    expect(within(strip).getByRole("link", { name: "Little sail" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    const tools = screen.getByRole("complementary", { name: "Tools" });
    expect(
      within(tools).getByRole("heading", { name: "Make it for a screen" }),
    ).toBeInTheDocument();
    expect(within(tools).getByRole("tab", { name: "Size" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(tools).getByRole("tab", { name: "Looks" })).toBeEnabled();
    expect(within(tools).getByRole("tab", { name: "Edit" })).toBeEnabled();
    expect(screen.getByText("Pixelworks PW-7 Pro")).toBeInTheDocument();
    expect(screen.getByText("Carries where it was taken")).toBeInTheDocument();
    expect(asked(fetch, "/pictures/12/full")).toHaveLength(0); // only once it's zoomed
  });

  it("goes to the picture before and after, by its buttons and the arrow keys", async () => {
    engine();
    renderPicture("/library/pictures/12?folder=1");
    await screen.findByRole("heading", { name: "Little sail", level: 1 });

    await waitFor(() => expect(screen.getByRole("button", { name: "Next picture" })).toBeEnabled());
    screen.getByRole("button", { name: "Next picture" }).click();
    expect(
      await screen.findByRole("heading", { name: "Spring meadow", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("address")).toHaveTextContent("/library/pictures/13?folder=1");

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Previous picture" })).toBeEnabled(),
    );
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(
      await screen.findByRole("heading", { name: "Little sail", level: 1 }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Previous picture" })).toBeEnabled(),
    );
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(
      await screen.findByRole("heading", { name: "Harbour at dusk", level: 1 }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Previous picture" })).toBeDisabled(),
    );
  });

  it("leaves the arrow keys to the zoom while it has them", async () => {
    engine();
    renderPicture("/library/pictures/12?folder=1");
    const fit = await screen.findByRole("radio", { name: "Fit" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Next picture" })).toBeEnabled());

    fireEvent.keyDown(fit, { key: "ArrowRight" });

    expect(screen.getByTestId("address")).toHaveTextContent("/library/pictures/12?folder=1");
  });

  it("shows the picture itself at 100%", async () => {
    const fetch = engine();
    renderPicture("/library/pictures/12");

    (await screen.findByRole("radio", { name: "100%" })).click();

    await waitFor(() => expect(asked(fetch, "/pictures/12/full")).toHaveLength(1));
    expect(await screen.findByRole("img", { name: "Little sail" })).toHaveStyle({
      width: "4032px",
    });
  });

  it("shows the picture in its folder", async () => {
    engine();
    renderPicture("/library/pictures/12");

    (await screen.findByRole("button", { name: "Show in folder" })).click();

    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("show_in_folder", {
        path: "D:\\Pictures\\Phone\\Little sail.jpg",
      }),
    );
  });

  it("copies the picture's path, and says so", async () => {
    engine();
    const clipboard = { writeText: vi.fn(async () => {}) };
    Object.defineProperty(navigator, "clipboard", { value: clipboard, configurable: true });
    renderPicture("/library/pictures/12");

    (await screen.findByRole("button", { name: "Copy path" })).click();

    expect(await screen.findByText("Copied its path.")).toHaveAttribute("role", "status");
    expect(clipboard.writeText).toHaveBeenCalledWith("D:\\Pictures\\Phone\\Little sail.jpg");
  });

  it("says camera RAW isn't readable yet, in the picture's place", async () => {
    engine({
      "/pictures/31": details(RAW, { camera: null, located: false }),
      "/pictures/31/neighbours": { before: [], after: [] },
    });
    renderPicture("/library/pictures/31");

    expect(
      await screen.findByRole("heading", { name: "Camera RAW isn't readable yet" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/leaves it exactly as it is/)).toBeInTheDocument();
  });

  it("says a picture won't open, and tries again on asking", async () => {
    const fetch = engine({
      "/pictures/32": details(BROKEN, {
        problem: "The file is damaged or was only half copied: image file is truncated.",
      }),
      "/pictures/32/neighbours": { before: [], after: [] },
      "POST /pictures/32/read": details(BROKEN),
    });
    renderPicture("/library/pictures/32");

    expect(
      await screen.findByRole("heading", { name: "Old pier.tif won't open" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/image file is truncated/)).toBeInTheDocument();
    screen.getByRole("button", { name: "Try again" }).click();

    await waitFor(() =>
      expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
    );
  });

  it("says why a picture couldn't be shown, in the engine's words", async () => {
    engine({
      "/pictures/12/view": () =>
        Response.json(
          { detail: "Mado needs ffmpeg to show HEIC pictures, and it isn't there." },
          { status: 503 },
        ),
    });
    renderPicture("/library/pictures/12");

    expect(await screen.findByText(/Mado needs ffmpeg to show HEIC pictures/)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Little sail.jpg can't be shown" }),
    ).toBeInTheDocument();
  });

  it("says when the picture isn't in the library any more", async () => {
    engine({
      "/pictures/99": () =>
        Response.json({ detail: "That picture isn't in your library any more." }, { status: 404 }),
      "/pictures/99/neighbours": () =>
        Response.json({ detail: "That picture isn't in your library any more." }, { status: 404 }),
    });
    renderPicture("/library/pictures/99?folder=1");

    expect(
      await screen.findByRole("heading", { name: "This picture isn't in your library any more" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the library" })).toHaveAttribute(
      "href",
      "/library?folder=1",
    );
  });
});
