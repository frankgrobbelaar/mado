import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type PictureDetails, type PictureItem } from "@/lib/engine";
import { FOLDERS, fakeEngine, PICTURES, READY, rawReader } from "@/test/engine";
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
            <Route path="/wallpaper" element={<p>The studio</p>} />
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
    camera: "Testcam T7 Pro",
    orientation: 1,
    located: true,
    damaged: false,
    problem: null,
    outside: false,
    pasted: false,
    aside: false,
    savesTo: null,
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
    expect(screen.getByText("Testcam T7 Pro")).toBeInTheDocument();
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

  it("shows a camera RAW developed, as any picture, wearing what its camera said", async () => {
    engine({
      "/pictures/31": details(RAW, { camera: "Lumen X100" }),
      "/pictures/31/neighbours": { before: [], after: [] },
      "/pictures/31/view": blob,
    });
    renderPicture("/library/pictures/31");

    expect(await screen.findByRole("img", { name: "Green sky" })).toBeInTheDocument();
    expect(screen.getByText("Lumen X100")).toBeInTheDocument();
  });

  it("shows Mado's RAW reader coming in a waiting RAW's place, and reads it once it's here", async () => {
    const waiting = details(RAW, { state: "waiting", width: null, height: null, camera: null });
    let reader = rawReader("downloading", 1_611_429);
    const fetch = engine({
      "/pictures/31": waiting,
      "/pictures/31/neighbours": { before: [], after: [] },
      "/tools": () => [reader],
      "POST /pictures/31/read": details(RAW),
      "/pictures/31/view": blob,
    });
    renderPicture("/library/pictures/31");

    expect(
      await screen.findByRole("heading", { name: "Green sky.CR3 waits for Mado's RAW reader" }),
    ).toBeInTheDocument();
    const note = await screen.findByRole("region", { name: "Mado's RAW reader" });
    expect(within(note).getByText(/Camera RAW is read by LibRaw \(3\.5 MB\)/)).toBeInTheDocument();
    expect(within(note).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "46");

    reader = rawReader("ready");
    await waitFor(() => expect(asked(fetch, "/pictures/31/read")).toHaveLength(1), {
      timeout: 3000,
    });
  });

  it("says why Mado's RAW reader didn't come, and tries again on asking", async () => {
    const fetch = engine({
      "/pictures/31": details(RAW, { state: "waiting", width: null, height: null }),
      "/pictures/31/neighbours": { before: [], after: [] },
      "/tools": [
        rawReader(
          "failed",
          0,
          "The LibRaw download didn't match what Mado expects, so Mado didn't use it. Try again; if it happens again, the file online has changed.",
        ),
      ],
      "POST /tools/libraw/download": rawReader("downloading"),
    });
    renderPicture("/library/pictures/31");

    const note = await screen.findByRole("region", { name: "Mado's RAW reader" });
    expect(await within(note).findByRole("alert")).toHaveTextContent(
      "didn't match what Mado expects",
    );
    expect(
      screen.getByText(
        "This camera RAW waits for Mado's RAW reader: once it's here, it can be made for a screen, given a look, edited or fixed.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(note).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(asked(fetch, "/tools/libraw/download")).toHaveLength(1));
  });

  it("keeps a waiting RAW's tile in the strip to a few words", async () => {
    const waiting = { ...RAW, state: "waiting" as const, width: null, height: null };
    engine({
      "/pictures/12/neighbours": { before: [DUSK], after: [waiting] },
      "/tools": [rawReader("downloading", 1_611_429)],
    });
    renderPicture("/library/pictures/12?folder=1");

    const strip = await screen.findByRole("navigation", { name: /pictures in/i });
    const tile = within(strip).getByRole("link", { name: "Green sky" });
    expect(await within(tile).findByText("RAW · 46%")).toHaveAttribute(
      "title",
      "Getting the RAW reader · 46%",
    );
  });

  it("says a RAW from a camera its reader doesn't know yet won't open, in the reader's words", async () => {
    const unknown =
      "Mado's RAW reader doesn't know this kind of RAW file yet (a camera newer than it, say), or it isn't one. Mado left it exactly as it is.";
    engine({
      "/pictures/31": details(RAW, { state: "broken", problem: unknown }),
      "/pictures/31/neighbours": { before: [], after: [] },
    });
    renderPicture("/library/pictures/31");

    expect(
      await screen.findByRole("heading", { name: "Green sky.CR3 won't open" }),
    ).toBeInTheDocument();
    expect(screen.getByText(unknown)).toBeInTheDocument();
    expect(screen.queryByText(/only half copied/)).not.toBeInTheDocument();
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

  it("gives the picture a heart beside its name", async () => {
    const hearts: unknown[] = [];
    engine({
      "PUT /pictures/12/favourite": (init: RequestInit | undefined) => {
        hearts.push(JSON.parse(String(init?.body)));
        return details(SAIL, { favourite: true });
      },
    });
    renderPicture("/library/pictures/12?folder=1");

    await screen.findByRole("heading", { name: "Little sail", level: 1 });
    const heart = screen.getByRole("button", { name: "Favourite Little sail" });
    expect(heart).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(heart);

    await waitFor(() => expect(hearts).toEqual([{ favourite: true }]));
  });

  it("finds the library's pictures most like it", async () => {
    engine();
    renderPicture("/library/pictures/12?folder=1");

    fireEvent.click(await screen.findByRole("button", { name: "More like this" }));

    expect(screen.getByTestId("address")).toHaveTextContent(/^\/library\?like=12$/);
  });

  it("makes it a wallpaper in the studio", async () => {
    engine();
    renderPicture("/library/pictures/12?folder=1");

    await screen.findByRole("heading", { name: "Little sail", level: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Make it a wallpaper" }));

    expect(await screen.findByText("The studio")).toBeInTheDocument();
    expect(screen.getByTestId("address")).toHaveTextContent("/wallpaper?picture=12");
  });
});
