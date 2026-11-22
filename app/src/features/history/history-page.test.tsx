import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type HistoryEntry } from "@/lib/engine";
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
});
