import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import {
  burstGroup,
  copiesGroup,
  duplicates,
  fakeEngine,
  groupPicture,
  LIBRARY,
  READY,
} from "@/test/engine";
import { DuplicatesPage } from "./duplicates-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const picture = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

function renderPage(at = "/duplicates") {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[at]}>
          <Routes>
            <Route path="/duplicates" element={<DuplicatesPage />} />
            <Route path="/history" element={<p>History</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) => (init?.method ?? "GET") === method && String(input).includes(path),
  );
}

function body(fetch: ReturnType<typeof fakeEngine>, method: string, path: string): unknown {
  const [call] = sent(fetch, method, path).slice(-1);
  return call ? JSON.parse(String(call[1]?.body)) : undefined;
}

function engine(answers: Record<string, unknown> = {}) {
  return fakeEngine({
    "/duplicates": duplicates(),
    "/library": LIBRARY,
    "/pictures/41/thumbnail": picture,
    "/pictures/42/thumbnail": picture,
    "/pictures/43/thumbnail": picture,
    "/pictures/11/thumbnail": picture,
    "/pictures/12/thumbnail": picture,
    ...answers,
  });
}

describe("DuplicatesPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists the groups with the one kept marked, and sets aside the rest of every one", async () => {
    const fetch = engine({
      "POST /duplicates/aside": {
        review: 3,
        pictures: 2,
        bytes: 6_400_000,
        left: [
          {
            name: "Harbour at dusk small.jpg",
            why: "Harbour at dusk small.jpg is open in another app, so Mado left it as it is. Close it there, then set it aside again.",
          },
        ],
      },
    });
    renderPage();

    const burst = await screen.findByRole("region", { name: "Burst · 3 shots" });
    expect(burst).toHaveTextContent("Keeping IMG_2042.jpg, the sharpest.");
    expect(within(burst).getByRole("button", { name: "IMG_2042.jpg, kept" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(burst).getByText("10:02:15")).toBeInTheDocument();
    expect(burst).toHaveTextContent("4032 × 3024 · 3.2 MB");
    expect(burst).toHaveTextContent("Phone › 2026");
    const copies = screen.getByRole("region", { name: "Duplicates · 2 copies" });
    expect(copies).toHaveTextContent("Keeping Harbour at dusk.jpg, the most pixels.");
    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === "P" && element.textContent === "2 groups · 3 to set aside · 7.3 MB",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Set aside 3, freeing 7.3 MB" }));

    await waitFor(() =>
      expect(body(fetch, "POST", "/duplicates/aside")).toEqual({
        groups: null,
        kind: "all",
        version: "found-1",
      }),
    );
    expect(await screen.findByText(/Set aside 2 pictures, freeing 6.4 MB/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "One was left as it is:Harbour at dusk small.jpg is open in another app",
    );
  });

  it("keeps another with a click, or more than one with their ticks", async () => {
    const fetch = engine({ "PUT /duplicates/41/keep": burstGroup({ chosen: true }) });
    renderPage();

    const burst = await screen.findByRole("region", { name: "Burst · 3 shots" });
    expect(within(burst).getByRole("checkbox", { name: "Keep IMG_2042.jpg" })).toBeDisabled();

    fireEvent.click(within(burst).getByRole("button", { name: "Keep IMG_2043.jpg instead" }));
    await waitFor(() =>
      expect(body(fetch, "PUT", "/duplicates/41/keep")).toEqual({
        keep: [43],
        members: [41, 42, 43],
      }),
    );

    fireEvent.click(within(burst).getByRole("checkbox", { name: "Keep IMG_2041.jpg too" }));
    await waitFor(() =>
      expect(body(fetch, "PUT", "/duplicates/41/keep")).toEqual({
        keep: [42, 41],
        members: [41, 42, 43],
      }),
    );
  });

  it("lets a group go as not the same, and sets one group aside on its own", async () => {
    const fetch = engine({
      "POST /duplicates/11/not-same": null,
      "POST /duplicates/aside": { review: 4, pictures: 2, bytes: 6_400_000, left: [] },
    });
    renderPage();

    const copies = await screen.findByRole("region", { name: "Duplicates · 2 copies" });
    fireEvent.click(within(copies).getByRole("button", { name: "Not the same" }));
    expect(
      await screen.findByText("Mado won't ask about those again, unless one of them changes."),
    ).toBeInTheDocument();

    const burst = screen.getByRole("region", { name: "Burst · 3 shots" });
    fireEvent.click(within(burst).getByRole("button", { name: "Set aside 2" }));
    await waitFor(() =>
      expect(body(fetch, "POST", "/duplicates/aside")).toEqual({
        groups: [{ key: 41, members: [41, 42, 43], keep: [42] }],
      }),
    );
    expect(sent(fetch, "POST", "/duplicates/11/not-same")).toHaveLength(1);
  });

  it("opens at the group a tag in the Library names, marked, its page long enough to hold it", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    const fetch = engine();
    renderPage("/duplicates?group=11");

    const copies = await screen.findByRole("region", { name: "Duplicates · 2 copies" });
    expect(copies).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("region", { name: "Burst · 3 shots" })).not.toHaveAttribute(
      "aria-current",
    );
    const asked = sent(fetch, "GET", "/duplicates?kind=all")[0]?.[0];
    expect(new URL(String(asked)).searchParams.get("reach")).toBe("11");
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
  });

  it("tells bursts from duplicates", async () => {
    const fetch = engine();
    renderPage();

    fireEvent.click(await screen.findByRole("radio", { name: "Bursts 1" }));

    await waitFor(() => expect(sent(fetch, "GET", "kind=bursts")).not.toHaveLength(0));
  });

  it("says how far it has got while still looking", async () => {
    engine({
      "/duplicates": duplicates({
        looking: { looked: 3200, of: 4812 },
        groups: [],
        duplicates: 0,
        bursts: 0,
        pictures: 0,
        bytes: 0,
      }),
    });
    renderPage();

    const looking = await screen.findByRole("status", { name: "Still looking" });
    expect(looking).toHaveTextContent("Looked at 3,200 of 4,812.");
    expect(within(looking).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "67");
    expect(screen.getByText(/Nothing found yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Set aside/ })).not.toBeInTheDocument();
  });

  it("says when there are none", async () => {
    engine({
      "/duplicates": duplicates({ groups: [], duplicates: 0, bursts: 0, pictures: 0, bytes: 0 }),
    });
    renderPage();

    expect(await screen.findByText("No duplicates or bursts")).toBeInTheDocument();
    expect(
      screen.getByText(/Mado looked at all 4,812 pictures and found none/),
    ).toBeInTheDocument();
  });

  it("says when a drive isn't connected or a picture went since, and holds that group back", async () => {
    engine({
      "/duplicates": duplicates({
        groups: [
          copiesGroup({
            ready: false,
            problem: "F: isn't connected. Connect it to set these aside.",
            pictures: [
              groupPicture(11, "Harbour at dusk.jpg", { keep: true, suggested: true }),
              groupPicture(12, "Harbour at dusk small.jpg", { there: "away" }),
            ],
          }),
          burstGroup({
            ready: true,
            pictures: [
              groupPicture(41, "IMG_2041.jpg", { there: "gone" }),
              groupPicture(42, "IMG_2042.jpg", { keep: true, suggested: true }),
            ],
          }),
        ],
        pictures: 1,
        away: 1,
      }),
    });
    renderPage();

    const copies = await screen.findByRole("region", { name: "Duplicates · 2 copies" });
    expect(copies).toHaveTextContent("F: isn't connected. Connect it to set these aside.");
    expect(within(copies).getByText("Not connected")).toBeInTheDocument();
    expect(within(copies).getByRole("button", { name: "Set aside 1" })).toBeDisabled();
    const burst = screen.getByRole("region", { name: "Burst · 2 shots" });
    expect(within(burst).getByText("Gone since")).toBeInTheDocument();
    expect(burst).toHaveTextContent("IMG_2041.jpg isn't there any more");
    expect(screen.getByText(/1 more is on a drive that isn't connected/)).toBeInTheDocument();
  });

  it("says nothing's left to review once everything is set aside, not that none were found", async () => {
    let left = duplicates();
    engine({
      "/duplicates": () => left,
      "POST /duplicates/aside": () => {
        left = duplicates({ groups: [], duplicates: 0, bursts: 0, pictures: 0, bytes: 0 });
        return { review: 5, pictures: 3, bytes: 7_300_000, left: [] };
      },
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Set aside 3, freeing 7.3 MB" }));

    expect(await screen.findByText("Nothing left to review")).toBeInTheDocument();
    expect(screen.queryByText("No duplicates or bursts")).not.toBeInTheDocument();
    expect(screen.getByText(/Set aside 3 pictures, freeing 7.3 MB/)).toBeInTheDocument();
  });

  it("says when everything set aside was put back", async () => {
    engine({
      "/duplicates": duplicates({ putBack: { at: "2026-11-22T18:05:00+02:00", pictures: 2 } }),
    });
    renderPage();

    expect(
      await screen.findByText(/Everything you set aside on 22 Nov is back where it was/),
    ).toBeInTheDocument();
  });

  it("opens one big beside the one kept, at Fit and at 100%, and keeps it instead", async () => {
    const fetch = engine({
      "/pictures/43/view": picture,
      "/pictures/42/view": picture,
      "/pictures/43/full": picture,
      "/pictures/42/full": picture,
      "PUT /duplicates/41/keep": burstGroup(),
    });
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "See IMG_2043.jpg big beside the one kept" }),
    );

    const card = await screen.findByRole("dialog");
    expect(card).toHaveTextContent("IMG_2043.jpg beside IMG_2042.jpg");
    expect(within(card).getByText("Kept")).toBeInTheDocument();
    await waitFor(() => expect(sent(fetch, "GET", "/pictures/43/view")).not.toHaveLength(0));
    fireEvent.click(within(card).getByRole("radio", { name: "100%" }));
    await waitFor(() => expect(sent(fetch, "GET", "/pictures/42/full")).not.toHaveLength(0));

    fireEvent.click(within(card).getByRole("button", { name: "Keep this one instead" }));
    await waitFor(() =>
      expect(body(fetch, "PUT", "/duplicates/41/keep")).toEqual({
        keep: [43],
        members: [41, 42, 43],
      }),
    );
  });
});
