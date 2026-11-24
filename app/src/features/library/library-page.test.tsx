import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type LibraryFolder, type PictureItem } from "@/lib/engine";
import {
  FOLDERS,
  fakeEngine,
  hit,
  LIBRARY,
  PICTURES,
  page,
  picture,
  READY,
  rawReader,
  scanDone,
  searchModel,
  searchResults,
  searchState,
} from "@/test/engine";
import { LibraryPage } from "./library-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

/** Where the page is now: its address and query, to see where a click led. */
function Address() {
  const location = useLocation();
  return (
    <>
      <p data-testid="address">{`${location.pathname}${location.search}`}</p>
      <p data-testid="state">{JSON.stringify(location.state)}</p>
    </>
  );
}

function renderLibrary(at = "/library", picked: string | null = null) {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "pick_folder") return picked;
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    // As the app has it: StrictMode runs state changes twice, to show any that aren't pure.
    <StrictMode>
      <QueryClientProvider client={queries}>
        <EngineProvider>
          <MemoryRouter initialEntries={[at]}>
            <Routes>
              <Route path="/library" element={<LibraryPage />} />
              <Route path="/library/pictures/:id" element={<p>A picture</p>} />
              <Route path="/batch" element={<p>Many at once</p>} />
              <Route path="/settings/general" element={<p>Settings</p>} />
            </Routes>
            <Address />
          </MemoryRouter>
        </EngineProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}

/** An IntersectionObserver that sees everything as in view at once. */
class SeesEverything {
  constructor(
    private readonly report: (seen: { isIntersecting: boolean; target: Element }[]) => void,
  ) {}
  observe(target: Element) {
    this.report([{ isIntersecting: true, target }]);
  }
  unobserve() {}
  disconnect() {}
}

/** Every picture's thumbnail, as a few bytes standing in for a picture. */
function thumbnails(pictures: PictureItem[]) {
  return Object.fromEntries(
    pictures.map((each) => [
      `/pictures/${each.id}/thumbnail`,
      () => new Response(new Blob(["made-up picture"], { type: "image/webp" })),
    ]),
  );
}

/** A library of three folders whose grid shows `pictures` (one page unless told). */
function library(answers: Record<string, unknown> = {}, folders: LibraryFolder[] = FOLDERS) {
  return fakeEngine({
    "/folders": folders,
    "/scan": scanDone(),
    "/pictures": page(PICTURES),
    ...thumbnails(PICTURES),
    ...answers,
  });
}

function asked(fetch: ReturnType<typeof fakeEngine>, path: string) {
  return fetch.mock.calls
    .map(([input]) => new URL(String(input)))
    .filter((url) => url.pathname === path);
}

describe("LibraryPage", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows an empty library with the one thing to do, and adds a folder", async () => {
    const fetch = library({ "/folders": [], "POST /folders": FOLDERS[0] }, []);
    renderLibrary("/library", "D:\\Pictures\\Phone");

    expect(
      await screen.findByRole("heading", { name: "Your library is empty" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No folders yet. The ones you add show here as a tree."),
    ).toBeInTheDocument();
    screen.getByRole("button", { name: "Add a folder" }).click();

    await waitFor(() =>
      expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
    );
  });

  it("lists the folders as a tree, with the one showing lit and open", async () => {
    library();
    renderLibrary("/library?folder=1");

    await screen.findByRole("link", { name: /All pictures/ });
    const tree = screen.getByRole("navigation", { name: "Folders" });
    const lit = await within(tree).findByRole("link", { current: "page" });
    expect(lit).toHaveTextContent("Phone3,104");
    expect(within(tree).getByRole("link", { name: /All pictures/ })).toHaveTextContent("4,812");
    expect(within(tree).getByRole("link", { name: /2026/ })).toHaveTextContent("1,840");
    expect(within(tree).queryByRole("link", { name: /Trip/ })).not.toBeInTheDocument();

    within(tree).getByRole("button", { name: "Show the folders in Camera" }).click();

    expect(await within(tree).findByRole("link", { name: /Trip/ })).toHaveAttribute(
      "href",
      "/library?folder=2&dir=Trip",
    );
  });

  it("tags a picture kept from a burst or from copies, opening its review there", async () => {
    const tagged = PICTURES.map((each) =>
      each.id === 21
        ? { ...each, group: { key: 21, kind: "burst" as const, pictures: 5 } }
        : each.id === 12
          ? { ...each, group: { key: 9, kind: "duplicates" as const, pictures: 2 } }
          : each,
    );
    library({ "/pictures": page(tagged) });
    renderLibrary("/library?folder=1");

    const burst = await screen.findByRole("link", { name: "Review the burst of 5" });
    expect(burst).toHaveTextContent("burst of 5");
    expect(burst).toHaveAttribute("href", "/duplicates?group=21");
    expect(screen.getByRole("link", { name: "Review the 2 copies" })).toHaveAttribute(
      "href",
      "/duplicates?group=9",
    );
    expect(screen.getAllByRole("link", { name: /^Review the/ })).toHaveLength(2);
  });

  it("shows a folder's pictures by the day they were taken, as the board draws them", async () => {
    const fetch = library();
    renderLibrary("/library?folder=1");

    expect(await screen.findByRole("heading", { name: "Phone", level: 1 })).toBeInTheDocument();
    const line = await screen.findByText(/pictures by the day they were taken/);
    expect(line).toHaveTextContent("7 pictures by the day they were taken · D:\\Pictures\\Phone");
    // A long path stays on one line, whole on hovering.
    expect(line).toHaveClass("truncate");
    expect(line).toHaveAttribute("title", "D:\\Pictures\\Phone");
    const day = screen.getByRole("region", { name: "Saturday 14 November 3 pictures" });
    const names = within(day)
      .getAllByRole("link", { name: /./ })
      .map((link) => link.getAttribute("aria-label"));
    expect(names.filter(Boolean)).toEqual(["Harbour at dusk", "Little sail", "Spring meadow"]);
    expect(within(day).getByText("18:42")).toBeInTheDocument();
    expect(within(day).getAllByText("HEIC")).toHaveLength(2);
    const older = screen.getByRole("region", { name: "Wednesday 11 November 2 pictures" });
    expect(within(older).getByText("RAW")).toBeInTheDocument(); // read, wearing its tag
    expect(within(older).getByText("Won't open")).toBeInTheDocument();
    expect(asked(fetch, "/pictures")[0]?.searchParams.get("folder")).toBe("1");
    await waitFor(() => expect(asked(fetch, "/pictures/11/thumbnail").length).toBeGreaterThan(0));
    await waitFor(() => expect(asked(fetch, "/pictures/31/thumbnail").length).toBeGreaterThan(0));
  });

  it("tags an HDR photo's tile HDR, a HEIC's first", async () => {
    const hdr = PICTURES.map((each) =>
      each.id === 11 || each.id === 12 ? { ...each, hdr: true } : each,
    );
    library({ "/pictures": page(hdr) });
    renderLibrary("/library?folder=1");

    const day = await screen.findByRole("region", { name: "Saturday 14 November 3 pictures" });
    expect(within(day).getAllByText("HDR")).toHaveLength(2); // Harbour at dusk.heic, Little sail
    expect(within(day).getAllByText("HEIC")).toHaveLength(1); // Spring meadow, an ordinary HEIC
  });

  it("shows a camera RAW waiting for Mado's RAW reader as the reader comes", async () => {
    const waiting = PICTURES.map((each) =>
      each.raw ? { ...each, state: "waiting" as const, width: null, height: null } : each,
    );
    let reader = rawReader("downloading", 1_611_429);
    library({ "/pictures": page(waiting), "/tools": () => [reader] });
    renderLibrary("/library?folder=1");

    const older = await screen.findByRole("region", { name: "Wednesday 11 November 2 pictures" });
    expect(await within(older).findByText("Getting the RAW reader · 46%")).toBeInTheDocument();
    expect(within(older).getByText("RAW")).toBeInTheDocument();

    reader = rawReader("failed", 0, "Mado couldn't download LibRaw: you're offline.");
    expect(
      await within(older).findByText("Needs the RAW reader", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
  });

  it("opens a picture with the list it came from in its address", async () => {
    library();
    renderLibrary("/library?folder=1&order=oldest");

    (await screen.findByRole("link", { name: "Little sail" })).click();

    expect(await screen.findByText("A picture")).toBeInTheDocument();
    expect(screen.getByTestId("address")).toHaveTextContent(
      "/library/pictures/12?folder=1&order=oldest",
    );
  });

  it("ticks pictures, a run of them with Shift, and offers what works with them now", async () => {
    library();
    const clipboard = { writeText: vi.fn(async () => {}) };
    Object.defineProperty(navigator, "clipboard", { value: clipboard, configurable: true });
    renderLibrary("/library?folder=1");

    fireEvent.click(await screen.findByRole("checkbox", { name: "Tick Harbour at dusk" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Tick Snowfield" }), { shiftKey: true });

    const bar = screen.getByRole("toolbar", { name: "Ticked pictures" });
    expect(bar).toHaveTextContent("4 ticked");
    expect(bar).toHaveTextContent("from 2 days");
    within(bar).getByRole("button", { name: "Copy paths" }).click();
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalled());
    expect(clipboard.writeText.mock.calls[0]).toEqual([
      [
        "D:\\Pictures\\Phone\\Harbour at dusk.heic",
        "D:\\Pictures\\Phone\\Little sail.jpg",
        "D:\\Pictures\\Phone\\Spring meadow.heic",
        "D:\\Pictures\\Phone\\Snowfield.jpg",
      ].join("\n"),
    ]);
    expect(await within(bar).findByRole("status")).toHaveTextContent("Copied 4 paths.");

    within(bar).getByRole("button", { name: "Show in folder" }).click();
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("show_files", {
        paths: expect.arrayContaining(["D:\\Pictures\\Phone\\Snowfield.jpg"]),
      }),
    );

    within(bar).getByRole("button", { name: "Clear" }).click();
    await waitFor(() =>
      expect(screen.queryByRole("toolbar", { name: "Ticked pictures" })).not.toBeInTheDocument(),
    );
  });

  it("moves along the ticked pictures' toolbar with the arrow keys", async () => {
    library();
    renderLibrary("/library?folder=1");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Tick Snowfield" }));
    const bar = await screen.findByRole("toolbar", { name: "Ticked pictures" });
    const show = within(bar).getByRole("button", { name: "Show in folder" });

    show.focus();
    fireEvent.keyDown(show, { key: "ArrowRight" });

    await waitFor(() =>
      expect(within(bar).getByRole("button", { name: "Copy path" })).toHaveFocus(),
    );
  });

  it("offers to show ticked pictures in their folders while they're in a few", async () => {
    library();
    renderLibrary("/library");

    fireEvent.click(await screen.findByRole("checkbox", { name: "Tick Snowfield" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Tick Red canyon" }));

    const bar = screen.getByRole("toolbar", { name: "Ticked pictures" });
    expect(within(bar).getByRole("button", { name: "Show in 2 folders" })).toBeInTheDocument();
  });

  it("searches as it's typed, and says when nothing matches", async () => {
    const fetch = library({
      "/search": searchResults("zebra", []),
    });
    renderLibrary("/library?folder=1");

    const search = await screen.findByRole("searchbox", { name: "Search Phone" });
    fireEvent.change(search, { target: { value: "zebra" } });

    expect(
      await screen.findByRole("heading", { name: "Nothing in Phone matches “zebra”" }),
    ).toBeInTheDocument();
    const asking = asked(fetch, "/search").at(-1);
    expect(asking?.searchParams.get("q")).toBe("zebra");
    expect(asking?.searchParams.get("folder")).toBe("1");
    expect(screen.queryByRole("button", { name: /^Date taken/ })).toBeNull();
    screen.getByRole("button", { name: "Clear the search" }).click();

    expect(await screen.findByRole("link", { name: "Harbour at dusk" })).toBeInTheDocument();
    expect(search).toHaveValue("");
  });

  it("clears the search when the folder is opened afresh from the tree", async () => {
    library({
      "/search": searchResults("harbour", [
        { kind: "name", pictures: [hit(PICTURES[0] as PictureItem)], total: 1 },
      ]),
    });
    renderLibrary("/library?folder=1");
    const search = await screen.findByRole("searchbox", { name: "Search Phone" });
    fireEvent.change(search, { target: { value: "harbour" } });
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("q=harbour"));

    screen.getByRole("link", { name: /^Phone/ }).click();

    await waitFor(() => expect(search).toHaveValue(""));
    await new Promise((done) => setTimeout(done, 400)); // longer than the search waits for keys
    expect(screen.getByTestId("address")).toHaveTextContent(/^\/library\?folder=1$/);
  });

  it("turns the order round, oldest first", async () => {
    const fetch = library();
    renderLibrary("/library");

    (await screen.findByRole("button", { name: "Date taken, newest first" })).click();

    expect(
      await screen.findByRole("button", { name: "Date taken, oldest first" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(asked(fetch, "/pictures").at(-1)?.searchParams.get("order")).toBe("oldest"),
    );
  });

  it("brings the next page as it's asked for", async () => {
    const later = [picture(41, "Late tram.jpg", "2026-11-10T22:14:00")];
    const fetch = library({
      "/pictures": (_: RequestInit | undefined, url: URL) =>
        url.searchParams.get("after") ? page(later) : page(PICTURES, "2026-11-11T13:22:00|32", 8),
      ...thumbnails(later),
    });
    renderLibrary("/library");

    (await screen.findByRole("button", { name: "Show more pictures" })).click();

    expect(await screen.findByRole("link", { name: "Late tram" })).toBeInTheDocument();
    expect(asked(fetch, "/pictures").at(-1)?.searchParams.get("after")).toBe(
      "2026-11-11T13:22:00|32",
    );
    expect(screen.queryByRole("button", { name: "Show more pictures" })).not.toBeInTheDocument();
  });

  it("doesn't keep asking for a page that won't come, and offers to try again", async () => {
    vi.stubGlobal("IntersectionObserver", SeesEverything); // the grid's end is in view
    const fetch = library({
      "/pictures": (_: RequestInit | undefined, url: URL) =>
        url.searchParams.get("after")
          ? new Response("Internal Server Error", { status: 500 })
          : page(PICTURES, "2026-11-11T13:22:00|32", 8),
    });
    renderLibrary("/library");

    expect(
      await screen.findByRole("button", { name: "Couldn't bring more pictures. Try again" }),
    ).toBeInTheDocument();
    await new Promise((done) => setTimeout(done, 500));

    const asking = asked(fetch, "/pictures").filter((url) => url.searchParams.get("after"));
    expect(asking).toHaveLength(1);
  });

  it("says how far a scan has read while it reads", async () => {
    library({
      "/scan": scanDone({
        state: "running",
        stage: "reading",
        read: 212,
        toRead: 4812,
        secondsLeft: 185,
      }),
    });
    renderLibrary("/library");

    expect(await screen.findByText(/Reading new pictures/)).toHaveTextContent(
      "Reading new pictures: 212 of 4,812 · about 3 min left",
    );
  });

  it("says when a folder's drive isn't connected", async () => {
    library({}, [{ ...(FOLDERS[0] as LibraryFolder), available: false }, ...FOLDERS.slice(1)]);
    renderLibrary("/library?folder=1");

    expect(await screen.findByText(/isn't connected/)).toHaveTextContent(
      "D:\\Pictures\\Phone isn't connected. Its pictures show as Mado last saw them",
    );
  });

  it("goes to all the pictures when the folder asked for isn't in the library any more", async () => {
    library();
    renderLibrary("/library?folder=99&order=oldest");

    await waitFor(() =>
      expect(screen.getByTestId("address")).toHaveTextContent(/^\/library\?order=oldest$/),
    );
    expect(await screen.findByRole("heading", { name: "Library", level: 1 })).toBeInTheDocument();
  });

  it("takes a folder out of the library, after asking", async () => {
    const fetch = library({ "DELETE /folders/1": null });
    renderLibrary("/library?folder=1");

    fireEvent.pointerDown(await screen.findByRole("button", { name: "More for Phone" }), {
      button: 0,
      ctrlKey: false,
    });
    (await screen.findByRole("menuitem", { name: "Take out of your library…" })).click();
    const card = await screen.findByRole("dialog", { name: "Take Phone out of your library?" });
    expect(card).toHaveTextContent("The pictures stay exactly where they are");
    within(card).getByRole("button", { name: "Take it out" }).click();

    await waitFor(() =>
      expect(fetch.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true),
    );
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/library$/));
  });

  it("says when the engine couldn't give the pictures, and asks again", async () => {
    let tries = 0;
    library({
      "/pictures": () => {
        tries += 1;
        return tries === 1
          ? new Response("Internal Server Error", { status: 500 })
          : page(PICTURES);
      },
    });
    renderLibrary("/library");

    expect(await screen.findByRole("alert")).toHaveTextContent("Mado couldn't load this screen.");
    screen.getByRole("button", { name: "Try again" }).click();

    expect(await screen.findByRole("link", { name: "Harbour at dusk" })).toBeInTheDocument();
  });

  it("makes ticked pictures many at once", async () => {
    library();
    renderLibrary("/library?folder=1");

    fireEvent.click(await screen.findByRole("checkbox", { name: "Tick Harbour at dusk" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Tick Little sail" }));
    const bar = screen.getByRole("toolbar", { name: "Ticked pictures" });
    fireEvent.click(within(bar).getByRole("button", { name: "Many at once…" }));

    expect(await screen.findByText("Many at once")).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("state").textContent ?? "null")).toEqual({
      pick: { how: "ticked", ids: [11, 12] },
    });
  });

  it("makes a whole folder many at once from its menu", async () => {
    library();
    renderLibrary("/library?folder=1&dir=2026");

    fireEvent.pointerDown(await screen.findByRole("button", { name: "More for 2026" }), {
      button: 0,
      ctrlKey: false,
    });
    expect(screen.queryByRole("menuitem", { name: "Take out of your library…" })).toBeNull();
    (await screen.findByRole("menuitem", { name: "Many at once…" })).click();

    expect(await screen.findByText("Many at once")).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("state").textContent ?? "null")).toEqual({
      pick: { how: "folder", folder: 1, dir: "2026" },
    });
  });
});

describe("Searching the Library", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  const sign = picture(41, "Corner shop.jpg", "2026-11-12T10:15:00");
  const boat = picture(42, "Little sail.jpg", "2026-11-14T16:05:00");
  const harbour = picture(43, "Zumi harbour.jpg", "2026-11-10T09:00:00");
  const found = searchResults("zumi", [
    {
      kind: "words",
      pictures: [
        hit(sign, {
          words: [
            { text: "Open daily · ", marked: false },
            { text: "ZUMI", marked: true },
            { text: " 73", marked: false },
          ],
        }),
      ],
      total: 1,
    },
    { kind: "described", pictures: [hit(boat, { score: 0.82 })], total: 1 },
    { kind: "name", pictures: [hit(harbour, { away: true })], total: 1 },
  ]);

  it("shows what it found in groups: the words marked, the closest first, names last", async () => {
    library({ "/search": found, ...thumbnails([sign, boat, harbour]) });
    renderLibrary("/library?folder=1&q=zumi");

    expect(await screen.findByRole("heading", { name: /^With the words “zumi”/ })).toBeVisible();
    expect(screen.getByRole("heading", { name: /^Looks like “zumi”/ })).toHaveTextContent(
      "1 picture · the closest first",
    );
    expect(screen.getByRole("heading", { name: /^“zumi” in the name/ })).toBeVisible();
    expect(screen.getByText("ZUMI", { selector: "strong" })).toBeVisible();
    expect(screen.getByText(/pictures found for “zumi”/)).toHaveTextContent(
      "3 pictures found for “zumi”",
    );
    // Each opens with the search in its address, so its neighbours are the results'.
    expect(screen.getByRole("link", { name: "Little sail" })).toHaveAttribute(
      "href",
      "/library/pictures/42?folder=1&q=zumi",
    );
    // A picture on a drive that isn't connected is found, and says so.
    expect(screen.getByText("Away")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Zumi harbour, its drive isn't connected" }),
    ).toBeVisible();
  });

  it("starts many at once from what it found", async () => {
    library({ "/search": found, ...thumbnails([sign, boat, harbour]) });
    renderLibrary("/library?folder=1&q=zumi");

    (await screen.findByRole("button", { name: "Many at once…" })).click();

    expect(await screen.findByText("Many at once")).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("state").textContent ?? "null")).toEqual({
      pick: { how: "search", folder: 1, dir: "", q: "zumi" },
    });
  });

  it("says its model is on its way, and that names still find meanwhile", async () => {
    const coming = searchState({
      describer: searchModel("siglip-base-patch16-224", { state: "downloading", done: 52_000_000 }),
      words: { ...searchState().words, model: searchModel("pp-ocrv6-small") },
      read: 0,
    });
    library({ "/search": searchResults("harbour", [], { state: coming }) });
    renderLibrary("/library?q=harbour");

    expect(await screen.findByText(/Getting Mado's reader of pictures/)).toHaveTextContent(
      "Getting Mado's reader of pictures for search: 52 MB of 207 MB.",
    );
    expect(screen.getByText(/a search finds pictures by their names/)).toBeVisible();
  });

  it("offers to try again when its model didn't come", async () => {
    const failed = searchState({
      describer: searchModel("siglip-base-patch16-224", {
        state: "failed",
        done: 0,
        problem: "Mado couldn't download SigLIP base: offline.",
      }),
    });
    const fetch = library({
      "/search": searchResults("harbour", [], { state: failed }),
      "POST /tools/siglip-base-patch16-224/download": searchModel("siglip-base-patch16-224"),
    });
    renderLibrary("/library?q=harbour");

    (await screen.findByRole("button", { name: "Try again" })).click();

    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([input]) =>
          String(input).endsWith("/tools/siglip-base-patch16-224/download"),
        ),
      ).toBe(true),
    );
  });

  it("says how far the library has been read, and pauses it", async () => {
    const reading = searchState({ read: 2340, of: 18200, reading: true });
    const fetch = library({
      "/search": searchResults("boat", found.groups.slice(1, 2), { state: reading }),
      "POST /search/pause": { ...reading, paused: true },
      ...thumbnails([boat]),
    });
    renderLibrary("/library?q=boat");

    expect(await screen.findByText(/so far: search covers those/)).toHaveTextContent(
      "Read 2,340 of 18,200 so far: search covers those.",
    );
    screen.getByRole("button", { name: "Pause" }).click();

    await waitFor(() =>
      expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/search/pause"))).toBe(
        true,
      ),
    );
  });

  it("says which pictures couldn't be read, once the rest are", async () => {
    const left = searchState({ read: 4810, of: 4812, failed: 2 });
    library({ "/search": searchResults("boat", found.groups.slice(1, 2), { state: left }) });
    renderLibrary("/library?q=boat");

    expect(await screen.findByText(/couldn't be read for search/)).toHaveTextContent(
      "Read 4,810 of 4,812: search covers those. 2 pictures couldn't be read for search. Mado tries them again the next time it looks through your library.",
    );
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
  });

  it("says when a reader couldn't run, and tries again", async () => {
    const stuck = searchState({
      read: 3,
      of: 5000,
      problem: { reader: "words", said: "The graphics card couldn't run the AI model (made up)." },
    });
    const fetch = library({
      "/search": searchResults("boat", found.groups.slice(1, 2), { state: stuck }),
      "POST /search/resume": { ...stuck, problem: null, reading: true },
      ...thumbnails([boat]),
    });
    renderLibrary("/library?q=boat");

    const said = await screen.findByRole("alert");
    expect(said).toHaveTextContent(
      "Mado's reader of words couldn't run: The graphics card couldn't run the AI model (made up). Search still finds pictures by what they show and by their names.",
    );
    within(said).getByRole("button", { name: "Try again" }).click();
    await waitFor(() =>
      expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/search/resume"))).toBe(
        true,
      ),
    );
  });

  it("says when reading takes turns with the queue on the graphics card", async () => {
    const busy = searchState({ read: 10, of: 40, reading: true, busy: true });
    library({ "/search": searchResults("boat", [], { state: busy }) });
    renderLibrary("/library?q=boat");

    expect(
      await screen.findByText(/It takes turns with the queue on the graphics card/),
    ).toBeVisible();
  });

  it("says a search in another language looked at names and words only", async () => {
    library({ "/search": searchResults("der Hund", [], { english: false }) });
    renderLibrary("/library?q=der%20Hund");

    expect(
      await screen.findByText(/works in English, so this search looked at names/),
    ).toBeVisible();
  });

  it("says when Windows can't read the writing a search is in, and where Best is", async () => {
    const windows = searchState({
      words: { ...searchState().words, chosen: "fast", reader: "fast", model: null },
    });
    library({
      "/search": searchResults("Βάρκα", [], { unreadable: "Greek", state: windows }),
    });
    renderLibrary("/library?q=%CE%92%CE%AC%CF%81%CE%BA%CE%B1");

    expect(
      await screen.findByText(
        /Windows reads words only in English here, so this search doesn't find Greek ones/,
      ),
    ).toBeVisible();
    screen.getByRole("link", { name: "Settings › General" }).click();
    expect(await screen.findByText("Settings")).toBeInTheDocument();
  });

  it("says when Windows has no language to read words in at all", async () => {
    const none = searchState({
      words: { ...searchState().words, chosen: "fast", reader: "fast", languages: [], model: null },
    });
    library({ "/search": searchResults("shop", [], { state: none }) });
    renderLibrary("/library?q=shop");

    expect(await screen.findByText(/Windows has no language to read words in here/)).toBeVisible();
  });

  it("shows the pictures most like one, and makes them many at once", async () => {
    const fetch = library({
      "/search/like/11": searchResults("Harbour at dusk.heic", [
        { kind: "like", pictures: [hit(boat, { score: 0.91 })], total: 1 },
      ]),
      ...thumbnails([boat]),
    });
    renderLibrary("/library?like=11");

    expect(
      await screen.findByRole("heading", { name: /^Most like Harbour at dusk/ }),
    ).toHaveTextContent("the most alike first");
    expect(screen.getByText(/picture most like Harbour at dusk/)).toHaveTextContent(
      "1 picture most like Harbour at dusk",
    );
    expect(asked(fetch, "/search")).toEqual([]);
    expect(screen.getByRole("link", { name: "Little sail" })).toHaveAttribute(
      "href",
      "/library/pictures/42?like=11",
    );

    screen.getByRole("button", { name: "Many at once…" }).click();
    expect(await screen.findByText("Many at once")).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("state").textContent ?? "null")).toEqual({
      pick: { how: "search", like: 11 },
    });
  });

  it("leaves the pictures most like one from the folder tree", async () => {
    library({
      "/search/like/11": searchResults("Harbour at dusk.heic", [
        { kind: "like", pictures: [hit(boat, { score: 0.91 })], total: 1 },
      ]),
      ...thumbnails([boat]),
    });
    renderLibrary("/library?like=11");
    await screen.findByRole("heading", { name: /^Most like Harbour at dusk/ });

    screen.getByRole("link", { name: /^Phone/ }).click();
    await waitFor(() =>
      expect(screen.getByTestId("address")).toHaveTextContent(/^\/library\?folder=1$/),
    );
    screen.getByRole("link", { name: /^Favourites/ }).click();
    await waitFor(() =>
      expect(screen.getByTestId("address")).toHaveTextContent(/^\/library\?favourites=1$/),
    );
  });

  it("says when nothing is like a picture, with the way back to all of them", async () => {
    library({ "/search/like/11": searchResults("Harbour at dusk.heic", []) });
    renderLibrary("/library?like=11");

    expect(
      await screen.findByRole("heading", {
        name: "Nothing in your library looks like Harbour at dusk",
      }),
    ).toBeVisible();
    screen.getByRole("button", { name: "Show all your pictures" }).click();
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/library$/));
  });
});

describe("Favourites in the Library", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  const loved = [
    picture(11, "Harbour at dusk.jpg", "2026-11-14T18:42:07", { favourite: true }),
    picture(31, "Pier at dawn.jpg", "2026-11-12T07:10:00", {
      favourite: true,
      outside: true,
      path: "E:\\Elsewhere\\Pier at dawn.jpg",
    }),
  ];

  it("are a view of their own, kept in the address, a picture opened from it keeping it", async () => {
    const fetch = library({
      "/library": { ...LIBRARY, favourites: 2 },
      "/pictures": page(loved),
      ...thumbnails(loved),
    });
    renderLibrary("/library?favourites=1");

    expect(await screen.findByRole("heading", { level: 1, name: "Favourites" })).toBeVisible();
    const row = await screen.findByRole("link", { name: /^Favourites/ });
    const tree = screen.getByRole("navigation", { name: "Folders" });
    expect(row).toHaveAttribute("aria-current", "page");
    expect(row).toHaveTextContent("2");
    expect(within(tree).getByRole("link", { name: /All pictures/ })).not.toHaveAttribute(
      "aria-current",
    );
    expect(asked(fetch, "/pictures")[0]?.searchParams.get("favourites")).toBe("1");
    expect(screen.getByRole("link", { name: "Harbour at dusk" })).toHaveAttribute(
      "href",
      "/library/pictures/11?favourites=1",
    );
    // One from outside the library opens on a page of its own.
    expect(screen.getByRole("link", { name: "Pier at dawn" })).toHaveAttribute(
      "href",
      "/pictures/31",
    );
    // A folder in the tree is the library again, not its favourites.
    expect(within(tree).getByRole("link", { name: /Phone/ })).toHaveAttribute(
      "href",
      "/library?folder=1",
    );
  });

  it("say so when there are none yet, with the way to give a picture a heart", async () => {
    library({ "/library": { ...LIBRARY, favourites: 0 }, "/pictures": page([]) });
    renderLibrary("/library?favourites=1");

    expect(await screen.findByRole("heading", { name: "No favourites yet" })).toBeVisible();
    expect(screen.getByText(/Give a picture a heart/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Show all your pictures" })).toHaveAttribute(
      "href",
      "/library",
    );
  });

  it("start many at once from every favourite", async () => {
    library({
      "/library": { ...LIBRARY, favourites: 2 },
      "/pictures": page(loved),
      ...thumbnails(loved),
    });
    renderLibrary("/library?favourites=1");

    fireEvent.click(await screen.findByRole("button", { name: "Many at once…" }));

    expect(await screen.findByText("Many at once")).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("state").textContent ?? "null")).toEqual({
      pick: { how: "favourites", q: "" },
    });
  });

  it("give a picture a heart from its tile", async () => {
    const hearts: unknown[] = [];
    library({
      "/library": LIBRARY,
      "PUT /pictures/12/favourite": (init: RequestInit | undefined) => {
        hearts.push(JSON.parse(String(init?.body)));
        return {};
      },
    });
    renderLibrary("/library");

    const heart = await screen.findByRole("button", { name: "Favourite Little sail" });
    expect(heart).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(heart);

    await waitFor(() => expect(hearts).toEqual([{ favourite: true }]));
    expect(screen.getByTestId("address")).toHaveTextContent("/library");
  });
});
