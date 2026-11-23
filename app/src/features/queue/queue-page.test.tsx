import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import { batch, fakeEngine, localTime, PC, queue, READY } from "@/test/engine";
import { QueuePage } from "./queue-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function renderQueue() {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/queue"]}>
          <Routes>
            <Route path="/queue" element={<QueuePage />} />
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

const NOW = {
  working: true,
  paused: false,
  batch: "Holiday prints",
  over: 18,
  total: 48,
  progress: 0.37,
  waiting: 30,
};

describe("QueuePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows the batch being made as the board draws it", async () => {
    fakeEngine({ "/queue": queue(), "/pc": PC });
    renderQueue();

    expect(
      await screen.findByText(
        (_, element) =>
          element?.tagName === "P" &&
          element.textContent ===
            "Holiday prints: 48 pictures from Holiday, one at a time on the graphics card",
      ),
    ).toBeInTheDocument();
    const progress = screen.getByRole("region", { name: "Progress" });
    expect(progress).toHaveTextContent("18/48");
    expect(progress).toHaveTextContent("about 6 min left");
    expect(progress).toHaveTextContent("Started 23:00 · nights only, till 07:00");
    expect(within(progress).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "37");
    const recipe = screen.getByRole("region", { name: "Recipe · Holiday prints" });
    expect(recipe).toHaveTextContent("TV 8K then Warm film 60 then JPEG 95 into Edited");
    expect(recipe).not.toHaveTextContent("→"); // drawn, as the fonts have no arrow
    expect(recipe).toHaveTextContent("Seen first on 3 pictures; you said they look right.");
    expect(screen.getByRole("region", { name: "Saving" })).toHaveTextContent(
      "Into Holiday › Edited. The originals stay as they are.",
    );

    const rows = within(screen.getByRole("region", { name: "Pictures in the queue" })).getAllByRole(
      "row",
    );
    expect(rows[1]).toHaveTextContent("Red canyon.jpgA look 2/33.8 MBnow");
    expect(rows[2]).toHaveTextContent("Misty pines.jpgWaiting4.2 MBnext");
    expect(rows[3]).toHaveTextContent("Still lake.heicWaiting2.9 MB+28 more");
    expect(rows[4]).toHaveTextContent("The file is damaged, so it was left as it is.");
    expect(rows[4]).toHaveTextContent("didn't work");
    expect(rows[5]).toHaveTextContent("Warm dunes (TV 8K).jpgDone2.7 MB9.8 MB");
    expect(screen.getByRole("button", { name: "Show the 14 others done" })).toBeInTheDocument();
  });

  it("moves ticked pictures next, to the end, or out of the queue", async () => {
    const fetch = fakeEngine({
      "/queue": queue(),
      "/pc": PC,
      "POST /queue/next": { moved: 2 },
      "POST /queue/remove": { moved: 1 },
    });
    renderQueue();

    fireEvent.click(await screen.findByRole("checkbox", { name: "Tick Misty pines.jpg" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Tick Still lake.heic" }));
    const bar = screen.getByRole("toolbar", { name: "Ticked pictures" });
    expect(bar).toHaveTextContent("2 ticked");
    fireEvent.click(within(bar).getByRole("button", { name: "Do these next" }));

    await waitFor(() => expect(sent(fetch, "POST", "/queue/next")).toEqual([{ jobs: [2, 3] }]));
  });

  it("pauses, and cancels all only once asked", async () => {
    const fetch = fakeEngine({
      "/queue": queue(),
      "/pc": PC,
      "POST /queue/pause": { ...NOW, paused: true },
      "POST /queue/cancel": { moved: 31 },
    });
    renderQueue();

    fireEvent.click(await screen.findByRole("button", { name: "Pause" }));
    await waitFor(() => expect(sent(fetch, "POST", "/queue/pause")).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "Cancel all…" }));
    const card = await screen.findByRole("dialog", { name: "Cancel the queue?" });
    expect(card).toHaveTextContent("Pictures made already stay where they are");
    expect(sent(fetch, "POST", "/queue/cancel")).toHaveLength(0);
    fireEvent.click(within(card).getByRole("button", { name: "Cancel all" }));

    await waitFor(() => expect(sent(fetch, "POST", "/queue/cancel")).toHaveLength(1));
  });

  it("tries a picture that didn't work again", async () => {
    const fetch = fakeEngine({ "/queue": queue(), "/pc": PC, "POST /queue/4/retry": NOW });
    renderQueue();

    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

    await waitFor(() => expect(sent(fetch, "POST", "/queue/4/retry")).toHaveLength(1));
  });

  it("says what a drive without room needs, makes what fits, or empties its quarantine once asked again", async () => {
    const fetch = fakeEngine({
      "/queue": queue({
        paused: true,
        working: false,
        room: {
          drive: "D:",
          fit: false,
          free: 800_000_000,
          needed: 2_000_000_000,
          more: 1_456_000_000,
          fitting: 11,
          aside: 1_900_000_000,
          batch: "Holiday prints",
        },
      }),
      "/pc": PC,
      "POST /queue/fit": NOW,
      "POST /quarantine/empty": { bytes: 1_900_000_000 },
      "POST /queue/resume": NOW,
    });
    renderQueue();

    const room = await screen.findByRole("region", { name: "D: needs 1.5 GB more" });
    expect(room).toHaveTextContent(
      "The queue paused itself. D: has 800 MB free and the rest of Holiday prints needs 2 GB.",
    );
    fireEvent.click(within(room).getByRole("button", { name: "Make the 11 that fit now" }));
    await waitFor(() => expect(sent(fetch, "POST", "/queue/fit")).toEqual([{ drive: "D:" }]));

    fireEvent.click(within(room).getByRole("button", { name: "Empty D:'s quarantine first…" }));
    const card = await screen.findByRole("dialog", { name: "Empty D:'s quarantine?" });
    fireEvent.click(within(card).getByRole("button", { name: "Empty it" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/quarantine/empty")).toEqual([{ drive: "D:" }]),
    );
  });

  it("says when nothing waits, and where batches come from", async () => {
    fakeEngine({ "/queue": queue({ batch: null, rows: [], working: false }), "/pc": PC });
    renderQueue();

    expect(
      await screen.findByRole("heading", { name: "Nothing in the queue" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Recipes and watch folders" })).toHaveAttribute(
      "href",
      "/recipes",
    );
  });

  it("ticks every picture waiting, those not listed yet too", async () => {
    const listed = queue();
    const [first] = listed.rows.filter((row) => row.state === "queued");
    if (!first) throw new Error("The queue's fixture has pictures waiting.");
    const more = ["Sail.jpg", "Pier.jpg"].map((name, at) => ({ ...first, job: 10 + at, name }));
    fakeEngine({
      "/queue": (_init: RequestInit | undefined, url: URL) =>
        url.searchParams.get("all")
          ? queue({ rows: [...listed.rows, ...more], waitingMore: 0, doneMore: 0 })
          : listed,
      "/pc": PC,
    });
    renderQueue();

    fireEvent.click(await screen.findByRole("checkbox", { name: "Tick every picture waiting" }));

    const bar = await screen.findByRole("toolbar", { name: "Ticked pictures" });
    await waitFor(() => expect(bar).toHaveTextContent("4 ticked"));
  });

  it("keeps a finished batch whose pictures didn't all work, with Try again, till it's cleared", async () => {
    const fetch = fakeEngine({
      "/queue": queue({
        working: false,
        finished: true,
        batch: batch({
          done: 47,
          failed: 1,
          waiting: 0,
          progress: 1,
          secondsLeft: null,
          finishedAt: localTime(2026, 11, 23, 5, 12),
        }),
        rows: queue().rows.filter((row) => row.state === "failed" || row.state === "done"),
        waitingMore: 0,
        doneMore: 46,
        secondsLeft: null,
      }),
      "/pc": PC,
      "POST /queue/clear": { ...NOW, working: false, batch: null, waiting: 0 },
    });
    renderQueue();

    expect(
      await screen.findByText(
        "Holiday prints is done. 1 picture didn't work: try it again, or clear it.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Progress" })).toHaveTextContent("Finished 05:12");
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel all…" })).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(sent(fetch, "POST", "/queue/clear")).toHaveLength(1));
  });
});
