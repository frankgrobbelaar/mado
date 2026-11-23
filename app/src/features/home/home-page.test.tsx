import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type EngineStatus, type PictureItem } from "@/lib/engine";
import {
  batch,
  duplicates,
  FOLDERS,
  fakeEngine,
  LIBRARY,
  localTime,
  outsidePicture,
  PICKED,
  PICTURES,
  pictureDetails,
  READY,
  SETTINGS,
  scanDone,
} from "@/test/engine";
import { HomePage } from "./home-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function renderHome(
  engine: EngineStatus = READY,
  picked: string | null = null,
  pictures: string[] = [],
) {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return engine;
    if (command === "pick_folder") return picked;
    if (command === "pick_pictures") return pictures;
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route index element={<HomePage />} />
            <Route path="/setup" element={<p>Setup</p>} />
            <Route path="/library/pictures/:id" element={<Where what="A picture's page" />} />
            <Route path="/pictures/:id" element={<Where what="A picture's own page" />} />
            <Route path="/batch" element={<Where what="Many at once" />} />
            <Route path="/duplicates" element={<Where what="The review" />} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function Where({ what }: { what: string }) {
  const location = useLocation();
  return (
    <p>
      {what} at {location.pathname}
      {location.state ? ` with ${JSON.stringify(location.state)}` : ""}
    </p>
  );
}

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) => (init?.method ?? "GET") === method && String(input).endsWith(path),
  );
}

/** A paragraph reading exactly `text`, however it's split into parts. */
function paragraph(text: string) {
  return (_: string, element: Element | null) =>
    element?.tagName === "P" && element.textContent === text;
}

describe("HomePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows the library in numbers, as the board draws it", async () => {
    fakeEngine({ "/settings": SETTINGS, "/library": LIBRARY, "/scan": scanDone() });
    renderHome();

    const panel = await screen.findByRole("region", { name: "Your library" });
    expect(within(panel).getByText("4,812")).toBeInTheDocument();
    expect(within(panel).getByRole("img")).toHaveAccessibleName(
      "Phone 3,104, Camera 1,422, Scans 286",
    );
    expect(within(panel).getByText("Camera RAW, not readable yet")).toBeInTheDocument();
    expect(within(panel).getByText("Won't open")).toBeInTheDocument();
    expect(
      screen.getByText(paragraph("4,812 pictures · 3 folders · 38.2 GB · read today 09:14, 6 new")),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Drop pictures here" })).toBeInTheDocument();
  });

  it("says how far a scan has read while it reads", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone({ state: "running", stage: "reading", read: 212, toRead: 4812 }),
    });
    renderHome();

    expect(
      await screen.findByText(
        paragraph("4,812 pictures · 3 folders · 38.2 GB · reading 212 of 4,812"),
      ),
    ).toBeInTheDocument();
  });

  it("adds a folder picked in Windows' folder picker", async () => {
    const fetch = fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "POST /folders": FOLDERS[0],
    });
    renderHome(READY, "D:\\Pictures\\Phone");

    (await screen.findByRole("button", { name: "Add a folder" })).click();

    await waitFor(() => expect(sent(fetch, "POST", "/folders")).toHaveLength(1));
    const [[, init]] = sent(fetch, "POST", "/folders") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({ path: "D:\\Pictures\\Phone" });
  });

  it("says why a folder couldn't be added", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "POST /folders": () =>
        Response.json(
          { detail: "D:\\Pictures\\Phone is already in your library." },
          { status: 400 },
        ),
    });
    renderHome(READY, "D:\\Pictures\\Phone");

    (await screen.findByRole("button", { name: "Add a folder" })).click();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "D:\\Pictures\\Phone is already in your library.",
    );
  });

  it("shows an empty library with its one next step", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": { ...LIBRARY, folders: 0, pictures: 0, size: 0, raw: 0, broken: 0, parts: [] },
      "/scan": scanDone({ state: "idle", startedAt: null, finishedAt: null }),
    });
    renderHome();

    expect(
      await screen.findByRole("heading", { name: "Your library is empty" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add a folder" })).toHaveLength(1);
  });

  it("leads to setup until it's done", async () => {
    fakeEngine({ "/settings": { ...SETTINGS, setUp: false } });
    renderHome();

    expect(await screen.findByText("Setup")).toBeInTheDocument();
  });

  it("shows its layout while the engine answers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    renderHome();

    expect(await screen.findByRole("status", { name: "Loading Home" })).toBeInTheDocument();
  });

  it("says when the engine isn't running, instead of the page", async () => {
    fakeEngine({});
    renderHome({ state: "failed", message: "It stopped unexpectedly.", details: "" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Mado's engine isn't running.");
    expect(screen.queryByRole("status", { name: "Loading Home" })).not.toBeInTheDocument();
  });

  it("opens one picture picked from the library on its page", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "POST /open": {
        picture: pictureDetails(PICTURES[0] as PictureItem),
        picked: null,
        leftOut: [],
      },
    });
    renderHome(READY, null, ["D:\\Pictures\\Phone\\Harbour at dusk.heic"]);

    fireEvent.click(await screen.findByRole("button", { name: "Pick pictures" }));

    expect(
      await screen.findByText(/A picture's page at \/library\/pictures\/11/),
    ).toBeInTheDocument();
  });

  it("opens one picture from outside the library on its own page", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "POST /open": { picture: outsidePicture(), picked: null, leftOut: [] },
    });
    renderHome(READY, null, ["E:\\Elsewhere\\Pier at dawn.jpg"]);

    fireEvent.click(await screen.findByRole("button", { name: "Pick pictures" }));

    expect(await screen.findByText(/A picture's own page at \/pictures\/42/)).toBeInTheDocument();
  });

  it("opens many pictures in Many at once", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "POST /open": { picture: null, picked: PICKED, leftOut: [] },
    });
    renderHome(READY, null, [
      "C:\\Users\\owner\\Desktop\\Rose.jpg",
      "C:\\Users\\owner\\Desktop\\Lily.jpg",
    ]);

    fireEvent.click(await screen.findByRole("button", { name: "Pick pictures" }));

    expect(await screen.findByText(/Many at once at \/batch/)).toHaveTextContent('"how":"picked"');
  });

  it("says when nothing picked is a picture Mado reads", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "POST /open": () =>
        Response.json(
          { detail: "notes.txt isn't a picture Mado reads. It reads JPEG, PNG, HEIC…" },
          { status: 422 },
        ),
    });
    renderHome(READY, null, ["C:\\notes.txt"]);

    fireEvent.click(await screen.findByRole("button", { name: "Pick pictures" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "notes.txt isn't a picture Mado reads.",
    );
  });

  it("asks to paste one too, as the Home board says", async () => {
    fakeEngine({ "/settings": SETTINGS, "/library": LIBRARY, "/scan": scanDone() });
    renderHome();

    expect(
      await screen.findByText(
        "Or paste one, or pick them from your PC. Make them right for a phone, a TV or a print, give them a look, or cut something out. They don't need to be in your library.",
      ),
    ).toBeInTheDocument();
  });

  it("tells of a batch done, and its folder opens, which lets it go", async () => {
    const fetch = fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "/batches/done": [
        batch({ done: 48, failed: 0, waiting: 0, finishedAt: localTime(2026, 11, 23, 6, 40) }),
      ],
      "POST /batches/7/seen": null,
    });
    renderHome();

    await screen.findByText("Holiday is ready for the TV");
    const needs = screen.getByRole("region", { name: "Needs you" });
    expect(needs).toHaveTextContent("48Holiday is ready for the TV");
    expect(needs).toHaveTextContent(
      "Made for TV 8K, with Warm film at 60% overnight, as new pictures in Holiday › Edited.",
    );
    fireEvent.click(within(needs).getByRole("button", { name: "Open folder" }));

    await waitFor(() => expect(sent(fetch, "POST", "/batches/7/seen")).toHaveLength(1));
    expect(shell.invoke).toHaveBeenCalledWith("open_folder", {
      path: "D:\\Pictures\\Holiday\\Edited",
    });
  });

  it("asks for a review of duplicates and bursts, and says how far looking has got", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": { ...LIBRARY, broken: 0 },
      "/scan": scanDone(),
      "/duplicates": duplicates({ pictures: 212 }),
    });
    renderHome();

    await screen.findByText("Duplicates and bursts");
    const needs = screen.getByRole("region", { name: "Needs you" });
    expect(needs).toHaveTextContent(
      "212Duplicates and burstsKeep the sharpest of each; the rest wait in quarantine for 30 days.",
    );
    fireEvent.click(within(needs).getByRole("button", { name: "Review" }));

    expect(await screen.findByText("The review at /duplicates")).toBeInTheDocument();
  });

  it("says looking for duplicates is under way", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": { ...LIBRARY, broken: 0 },
      "/scan": scanDone(),
      "/duplicates": duplicates({ looking: { looked: 3200, of: 4812 }, pictures: 40 }),
    });
    renderHome();

    expect(await screen.findByText(/Still looking: 3,200 of 4,812 looked at/)).toBeInTheDocument();
  });

  it("lists the pictures that won't open, each to show, try again or mark as damaged", async () => {
    const fetch = fakeEngine({
      "/settings": SETTINGS,
      "/library": { ...LIBRARY, broken: 3, damaged: 1 },
      "/scan": scanDone(),
      "/library/wont-open": {
        pictures: [
          {
            id: 32,
            name: "Old pier.tif",
            path: "E:\\Scans\\1990\\Old pier.tif",
            folder: "E:\\Scans\\1990",
            format: "TIF",
            size: 61_000_000,
            problem: "The file is damaged or was only half copied: image file is truncated.",
            version: "v32",
          },
          {
            id: 33,
            name: "Torn map.jpg",
            path: "E:\\Scans\\Torn map.jpg",
            folder: "E:\\Scans",
            format: "JPEG",
            size: 900_000,
            problem: "Mado can't tell what kind of picture it is.",
            version: "v33",
          },
        ],
        damaged: 1,
      },
      "POST /pictures/32/read": { ...LIBRARY, id: 32, state: "broken" },
      "POST /pictures/33/damaged": { id: 33, state: "broken", damaged: true },
    });
    renderHome();

    await screen.findByRole("button", { name: "See which" });
    const needs = screen.getByRole("region", { name: "Needs you" });
    expect(needs).toHaveTextContent(
      "2Won't openTheir files are damaged or were only half copied. They're left as they are.",
    );
    fireEvent.click(within(needs).getByRole("button", { name: "See which" }));

    const card = await screen.findByRole("dialog");
    await within(card).findByText("Old pier.tif");
    const items = within(card).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Old pier.tif won't open");
    expect(items[0]).toHaveTextContent("image file is truncated.");
    expect(items[0]).toHaveTextContent("In Scans › 1990");
    expect(card).toHaveTextContent("1 marked as damaged isn't listed.");

    fireEvent.click(
      within(items[0] as HTMLElement).getByRole("button", { name: "Show in folder" }),
    );
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("show_in_folder", {
        path: "E:\\Scans\\1990\\Old pier.tif",
      }),
    );
    fireEvent.click(within(items[0] as HTMLElement).getByRole("button", { name: "Try again" }));
    expect(
      await within(card).findByText("It still won't open, so Mado left it as it is."),
    ).toBeInTheDocument();
    fireEvent.click(
      within(items[1] as HTMLElement).getByRole("button", { name: "Mark as damaged" }),
    );
    await waitFor(() => expect(sent(fetch, "POST", "/pictures/33/damaged")).toHaveLength(1));
    expect(sent(fetch, "POST", "/pictures/32/read")).toHaveLength(1);
  });

  it("keeps the card of pictures that won't open while the last is marked, to say so", async () => {
    let marked = false;
    const PIER = {
      id: 32,
      name: "Old pier.tif",
      path: "E:\\Scans\\Old pier.tif",
      folder: "E:\\Scans",
      format: "TIF",
      size: 61_000_000,
      problem: "The file is damaged or was only half copied: image file is truncated.",
      version: "v32",
    };
    fakeEngine({
      "/settings": SETTINGS,
      "/library": () => ({ ...LIBRARY, broken: 1, damaged: marked ? 1 : 0 }),
      "/scan": scanDone(),
      "/library/wont-open": () => ({ pictures: marked ? [] : [PIER], damaged: marked ? 1 : 0 }),
      "POST /pictures/32/damaged": () => {
        marked = true;
        return { id: 32, state: "broken", damaged: true };
      },
    });
    renderHome();

    fireEvent.click(await screen.findByRole("button", { name: "See which" }));
    const card = await screen.findByRole("dialog");
    fireEvent.click(await within(card).findByRole("button", { name: "Mark as damaged" }));

    expect(
      await within(card).findByText("Every picture opens now, or you've marked it as damaged."),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBe(card);
    expect(screen.queryByRole("button", { name: "See which" })).not.toBeInTheDocument();
  });

  it("shows the space on the drive most of the library is on, then the others", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "/space": [
        {
          drive: "D:",
          connected: true,
          free: 412_000_000_000,
          total: 1_000_000_000_000,
          pictures: 38_200_000_000,
          quarantine: 1_400_000_000,
          queue: 1_200_000_000,
        },
        {
          drive: "E:",
          connected: true,
          free: 120_000_000_000,
          total: 500_000_000_000,
          pictures: 4_100_000_000,
          quarantine: 0,
          queue: 0,
        },
        {
          drive: "F:",
          connected: false,
          free: null,
          total: null,
          pictures: 900_000_000,
          quarantine: 0,
          queue: 0,
        },
      ],
    });
    renderHome();

    const space = await screen.findByRole("region", { name: "Space on D:" });
    expect(space).toHaveTextContent("412 GBfree");
    expect(space).toHaveTextContent(
      "Your pictures use 38.2 GB; quarantine holds 1.4 GB. The queue needs 1.2 GB more.",
    );
    expect(within(space).getByRole("img")).toHaveAccessibleName("38.2 GB of pictures, 412 GB free");
    expect(space).toHaveTextContent("E:120 GB free · 4.1 GB of pictures");
    expect(space).toHaveTextContent("F:not connected");
  });

  it("says when the drive most of the library is on isn't connected", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "/space": [
        {
          drive: "D:",
          connected: false,
          free: null,
          total: null,
          pictures: 38_200_000_000,
          quarantine: 0,
          queue: 0,
        },
      ],
    });
    renderHome();

    const space = await screen.findByRole("region", { name: "Space on D:" });
    expect(space).toHaveTextContent("D: isn't connected. Its pictures stay in your library");
  });

  it("shows what was made today, each with what it was made for", async () => {
    fakeEngine({
      "/settings": SETTINGS,
      "/library": LIBRARY,
      "/scan": scanDone(),
      "/history/today": [
        { id: 3, name: "Night market", madeFor: "TV 8K", look: null, edit: null },
        { id: 2, name: "Misty pines", madeFor: null, look: "Warm film at 60%", edit: null },
        { id: 4, name: "Garden rose", madeFor: null, look: null, edit: "cut out the subject" },
        { id: 5, name: "Little sail", madeFor: null, look: null, edit: "erased 2 parts" },
        {
          id: 6,
          name: "Old pier",
          madeFor: null,
          look: null,
          edit: "erased a part, blurred what's behind a part",
        },
        { id: 7, name: "Red canyon", madeFor: "Phone", look: null, edit: "cut out a part" },
      ],
    });
    renderHome();

    const today = await screen.findByRole("region", { name: "Made today" });
    expect(today).toHaveTextContent("Night marketTV 8K");
    expect(today).toHaveTextContent("Misty pinesWarm film");
    // An edit alone says what it did, in the words a new picture's name has for it.
    expect(today).toHaveTextContent("Garden roseCut out");
    expect(today).toHaveTextContent("Little sailErased");
    expect(today).toHaveTextContent("Old pierEdited");
    expect(today).toHaveTextContent("Red canyonPhone");
    expect(within(today).getByRole("link", { name: "History" })).toHaveAttribute(
      "href",
      "/history",
    );
  });
});
