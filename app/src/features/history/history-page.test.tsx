import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type BatchLine, EngineProvider, type HistoryEntry, type ReviewLine } from "@/lib/engine";
import { entry, fakeEngine, READY } from "@/test/engine";
import { HistoryPage } from "./history-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function renderHistory() {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter>
          <HistoryPage />
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

/** Yesterday at 18:05, as History keeps it. */
function yesterday(): string {
  const day = new Date();
  day.setDate(day.getDate() - 1);
  day.setHours(18, 5, 0, 0);
  return day.toISOString();
}

const REPLACED: HistoryEntry = entry({
  id: 2,
  kind: "replaced",
  name: "Old harbour.jpg",
  madeFor: "TV 8K",
  original: "D:\\Pictures\\Phone\\Old harbour.jpg",
  result: "D:\\Pictures\\Phone\\Old harbour.jpg",
  resultName: "Old harbour.jpg",
  aside: "D:\\Mado quarantine\\2026-11-22\\Old harbour.jpg",
  asideUntil: "2026-12-22",
});

const EMPTIED: HistoryEntry = entry({
  id: 3,
  at: yesterday(),
  kind: "emptied",
  name: "D:",
  madeFor: null,
  original: null,
  result: null,
  resultName: null,
  bytes: 1_400_000_000,
  canUndo: false,
});

describe("History", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows a review as one line, puts all of it back, and each picture's own line under it", async () => {
    const lines = ["IMG_2043.jpg", "IMG_2041.jpg"].map((name, at) =>
      entry({
        id: 20 + at,
        kind: "aside",
        name,
        madeFor: null,
        original: `D:\\Pictures\\Phone\\${name}`,
        result: null,
        resultName: null,
        aside: `D:\\Mado quarantine\\2026-11-22\\${name}`,
        asideUntil: "2026-12-22",
        keptName: "IMG_2042.jpg",
        review: 3,
        bytes: 3_200_000,
      }),
    );
    const review: ReviewLine = {
      id: 3,
      at: lines[0]?.at ?? "",
      duplicates: 1,
      bursts: 1,
      pictures: 2,
      bytes: 1_400_000_000,
      back: 0,
      cleared: 0,
      canUndo: true,
      drives: ["D:"],
      asideUntil: "2026-12-22",
      picture: null,
    };
    const fetch = fakeEngine({
      "/history": { entries: lines, older: null, batches: [], reviews: [review] },
      "POST /history/reviews/3/undo": { done: 2, problems: [] },
      "POST /history/20/undo": lines[0],
    });
    renderHistory();

    const line = await screen.findByText("Set aside 2 duplicates and bursts, freeing 1.4 GB");
    const row = line.closest("li") as HTMLElement;
    expect(row).toHaveTextContent(
      "Kept the sharpest of each; the rest are in quarantine until 22 Dec.",
    );
    fireEvent.click(within(row).getByRole("button", { name: "Show the 2 pictures" }));
    expect(screen.getByText("Set aside IMG_2043.jpg")).toBeInTheDocument();
    expect(
      screen.getAllByText("IMG_2042.jpg was kept; this one is in quarantine on D: until 22 Dec."),
    ).toHaveLength(2);

    fireEvent.click(within(row).getByRole("button", { name: "Put back all 2" }));
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter(([input]) => String(input).endsWith("/history/reviews/3/undo")),
      ).toHaveLength(1),
    );
  });

  it("says when a review was put back whole", async () => {
    const back = entry({
      id: 20,
      kind: "aside",
      name: "IMG_2043.jpg",
      madeFor: null,
      result: null,
      resultName: null,
      keptName: "IMG_2042.jpg",
      review: 3,
      undoneAt: new Date().toISOString(),
      canUndo: false,
    });
    fakeEngine({
      "/history": {
        entries: [back],
        older: null,
        batches: [],
        reviews: [
          {
            id: 3,
            at: back.at,
            duplicates: 1,
            bursts: 0,
            pictures: 1,
            bytes: 3_200_000,
            back: 1,
            cleared: 0,
            canUndo: false,
            drives: [],
            asideUntil: null,
            picture: null,
          },
        ],
      },
    });
    renderHistory();

    const line = await screen.findByText("Put back the 1 duplicate");
    const row = line.closest("li") as HTMLElement;
    expect(row).toHaveTextContent("Everything set aside is back where it was");
    expect(within(row).queryByRole("button", { name: /Put/ })).not.toBeInTheDocument();
  });

  it("lists what Mado did by day, newest first, with each line's undo", async () => {
    fakeEngine({ "/history": { entries: [entry(), REPLACED, EMPTIED], older: null } });
    renderHistory();

    const today = await screen.findByRole("region", { name: /^Today/ });
    expect(within(today).getByText("Made Harbour at dusk for TV 8K")).toBeInTheDocument();
    expect(
      within(today).getByText("As a new picture: Harbour at dusk (TV 8K).jpg in Phone"),
    ).toBeInTheDocument();
    expect(within(today).getByRole("button", { name: "Take it away" })).toBeInTheDocument();
    expect(
      within(today).getByText("Replaced Old harbour.jpg with its TV 8K version"),
    ).toBeInTheDocument();
    expect(
      within(today).getByText("The original is in quarantine on D: until 22 Dec."),
    ).toBeInTheDocument();
    expect(within(today).getByRole("button", { name: "Put back" })).toBeInTheDocument();
    const before = screen.getByRole("region", { name: /^Yesterday/ });
    expect(within(before).getByText("Emptied D:'s quarantine, 1.4 GB")).toBeInTheDocument();
    expect(within(before).queryByRole("button")).not.toBeInTheDocument();
  });

  it("says what a picture was made with: its look, alone or with a size", async () => {
    fakeEngine({
      "/history": {
        entries: [
          entry({
            madeFor: null,
            look: "Warm film at 60%",
            result: "D:\\Pictures\\Phone\\Harbour at dusk (Warm film).jpg",
            resultName: "Harbour at dusk (Warm film).jpg",
          }),
          { ...REPLACED, look: "Silver" },
        ],
        older: null,
      },
    });
    renderHistory();

    const today = await screen.findByRole("region", { name: /^Today/ });
    expect(
      within(today).getByText("Made Harbour at dusk with Warm film at 60%"),
    ).toBeInTheDocument();
    expect(
      within(today).getByText("Replaced Old harbour.jpg with its TV 8K, Silver version"),
    ).toBeInTheDocument();
  });

  it("says whether a picture went after its days or when the quarantine was emptied", async () => {
    const gone = { clearedAt: "2026-11-23T10:00:00+02:00", aside: null, canUndo: false };
    fakeEngine({
      "/history": {
        entries: [
          { ...REPLACED, ...gone, clearedBy: "owner" },
          entry({ id: 5, undoneAt: "x", ...gone, clearedBy: "days" }),
        ],
        older: null,
      },
    });
    renderHistory();

    expect(
      await screen.findByText("The original went when you emptied the quarantine."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("It was cleared out of quarantine after its 30 days."),
    ).toBeInTheDocument();
  });

  it("takes a new picture away, puts it back, and puts a replaced original back", async () => {
    const fetch = fakeEngine({
      "/history": {
        entries: [
          entry(),
          entry({
            id: 4,
            undoneAt: "x",
            canUndo: false,
            canRedo: true,
            aside: "D:\\Mado quarantine\\2026-11-22\\Harbour at dusk (TV 8K).jpg",
            asideUntil: "2026-12-22",
          }),
          REPLACED,
        ],
        older: null,
      },
      "POST /history/1/undo": entry({ canUndo: false, canRedo: true }),
      "POST /history/4/redo": entry({ id: 4 }),
      "POST /history/2/undo": REPLACED,
    });
    renderHistory();

    fireEvent.click(await screen.findByRole("button", { name: "Take it away" }));
    fireEvent.click(screen.getByRole("button", { name: "Put it back" }));
    fireEvent.click(screen.getByRole("button", { name: "Put back" }));

    await waitFor(() => {
      const posted = fetch.mock.calls
        .filter(([, init]) => init?.method === "POST")
        .map(([input]) => new URL(String(input)).pathname);
      expect(posted).toEqual(["/history/1/undo", "/history/4/redo", "/history/2/undo"]);
    });
    expect(screen.getByText("Took away Harbour at dusk (TV 8K).jpg")).toBeInTheDocument();
  });

  it("replaces an original put back again, and says why an older change waits", async () => {
    const putBack = {
      ...REPLACED,
      undoneAt: "x",
      canUndo: false,
      canRedo: true,
      aside: "D:\\Mado quarantine\\2026-11-22\\Old harbour.jpg",
    };
    const fetch = fakeEngine({
      "/history": { entries: [putBack], older: null },
      "POST /history/2/redo": () =>
        new Response(
          JSON.stringify({
            detail:
              "Old harbour.jpg was replaced again since. Put that back first: History undoes a picture's changes newest first.",
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
    });
    renderHistory();

    expect(await screen.findByText("Put Old harbour.jpg back")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Put it back" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Replace it again" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/newest first/);
    const posted = fetch.mock.calls
      .filter(([, init]) => init?.method === "POST")
      .map(([input]) => new URL(String(input)).pathname);
    expect(posted).toEqual(["/history/2/redo"]);
  });

  it("shows the week before, and filters by picture or folder", async () => {
    const fetch = fakeEngine({
      "/history": (_init: RequestInit | undefined, url: URL) =>
        url.searchParams.get("before")
          ? { entries: [EMPTIED], older: null }
          : { entries: [entry()], older: "2026-11-15" },
    });
    renderHistory();

    fireEvent.click(await screen.findByRole("button", { name: "Show the week before" }));
    expect(await screen.findByText("Emptied D:'s quarantine, 1.4 GB")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox", { name: "Filter by picture or folder" }), {
      target: { value: "harbour" },
    });
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([input]) => new URL(String(input)).searchParams.get("q") === "harbour",
        ),
      ).toBe(true),
    );
  });

  it("says when there's nothing yet, and clears History after asking", async () => {
    let entries = [entry()];
    const fetch = fakeEngine({
      "/history": () => ({ entries, older: null }),
      "POST /history/clear": () => {
        entries = [];
        return { cleared: 1 };
      },
    });
    renderHistory();

    fireEvent.click(await screen.findByRole("button", { name: "Clear History…" }));
    const dialog = await screen.findByRole("dialog", { name: "Clear History?" });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Nothing" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Clear History" }));

    expect(await screen.findByText(/1 line cleared from History/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Nothing yet" })).toBeInTheDocument();
    const cleared = fetch.mock.calls.find(([input]) => String(input).endsWith("/history/clear"));
    expect(JSON.parse(String(cleared?.[1]?.body))).toEqual({ keep: "nothing" });
  });

  it("shows a batch as one line, with what undoes all of it, and each picture's own lines", async () => {
    const lines = [
      entry({ id: 11, batch: 7, name: "Warm dunes.jpg", resultName: "Warm dunes (TV 8K).jpg" }),
      entry({ id: 12, batch: 7, name: "Still lake.heic", resultName: "Still lake (TV 8K).jpg" }),
    ];
    const fetch = fakeEngine({
      "/history": {
        entries: lines,
        older: null,
        batches: [
          {
            id: 7,
            name: "Holiday prints",
            source: "Holiday",
            watch: null,
            how: "new",
            madeFor: "TV 8K",
            look: null,
            purpose: "tv",
            into: "Holiday › Edited",
            made: 47,
            undone: 0,
            failed: ["Old pier.tif"],
            overnight: true,
            canUndo: true,
            canRedo: false,
            working: false,
            drive: null,
            asideUntil: null,
            picture: null,
          },
        ],
      },
      "POST /history/batches/7/undo": { done: 47, problems: [] },
    });
    renderHistory();

    expect(await screen.findByText("Made 47 pictures for the TV overnight")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Holiday prints, as new pictures in Holiday › Edited · Old pier.tif didn't work/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Warm dunes (TV 8K).jpg", { exact: false })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show the 2 pictures" }));
    expect(await screen.findAllByRole("button", { name: "Take it away" })).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Take them away" }));
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([input, init]) =>
            init?.method === "POST" && String(input).endsWith("/history/batches/7/undo"),
        ),
      ).toBe(true),
    );
  });

  it("keeps a batch made across midnight as one line, on the day of its newest picture", async () => {
    const late = new Date();
    late.setDate(late.getDate() - 1);
    late.setHours(23, 40, 0, 0);
    const early = new Date();
    early.setHours(0, 20, 0, 0);
    fakeEngine({
      "/history": {
        entries: [
          entry({ id: 21, batch: 9, at: early.toISOString(), name: "Pier.jpg" }),
          entry({ id: 20, batch: 9, at: late.toISOString(), name: "Sail.jpg" }),
          entry({ id: 19, batch: 8, at: late.toISOString(), name: "Dunes.jpg" }),
        ],
        older: null,
        batches: [batchLine({ id: 9, made: 2 }), batchLine({ id: 8, name: "Dunes", made: 1 })],
      },
    });
    renderHistory();

    expect(await screen.findByText("Made 2 pictures for the TV overnight")).toBeInTheDocument();
    const today = screen.getByRole("region", { name: /^Today/ });
    expect(within(today).getByRole("button", { name: "Show the 2 pictures" })).toBeInTheDocument();
    const before = screen.getByRole("region", { name: /^Yesterday/ });
    expect(within(before).queryByText("Made 2 pictures for the TV overnight")).toBeNull();
    expect(within(before).getByRole("button", { name: "Show the picture" })).toBeInTheDocument();
  });

  it("says a batch is still being made rather than undoing what's made so far", async () => {
    fakeEngine({
      "/history": {
        entries: [entry({ id: 31, batch: 4, name: "Pier.jpg" })],
        older: null,
        batches: [batchLine({ id: 4, made: 1, working: true })],
      },
    });
    renderHistory();

    expect(await screen.findByText("Still being made")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Take them away" })).toBeNull();
  });
});

function batchLine(overrides: Partial<BatchLine>): BatchLine {
  return {
    id: 7,
    name: "Holiday prints",
    source: "Holiday",
    watch: null,
    how: "new",
    madeFor: "TV 8K",
    look: null,
    edit: null,
    restore: null,
    fix: null,
    depth: null,
    purpose: "tv",
    into: "Holiday › Edited",
    made: 47,
    undone: 0,
    failed: [],
    overnight: true,
    canUndo: true,
    canRedo: false,
    working: false,
    drive: null,
    asideUntil: null,
    picture: null,
    ...overrides,
  };
}
