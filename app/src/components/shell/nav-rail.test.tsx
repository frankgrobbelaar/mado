import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type QueueNow } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { badgeOf, NavRail } from "./nav-rail";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const IDLE: QueueNow = {
  working: false,
  paused: false,
  batch: null,
  over: 0,
  total: 0,
  progress: 0,
  waiting: 0,
};

function renderRail(page = "/", queue: QueueNow = IDLE) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  fakeEngine({ "/queue/now": queue });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[page]}>
          <NavRail />
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

/** The tiles lit while `page` is open. */
function litOn(page: string): string[] {
  renderRail(page);
  return screen
    .getAllByRole("link")
    .filter((tile) => tile.getAttribute("aria-current") === "page")
    .map((tile) => tile.textContent ?? "");
}

describe("NavRail", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists Mado's places in order, the Queue between the Library and History", () => {
    renderRail();

    expect(screen.getAllByRole("link").map((tile) => tile.textContent)).toEqual([
      "Home",
      "Library",
      "Queue",
      "History",
      "Settings",
    ]);
  });

  it.each([
    ["/", "Home"],
    ["/library", "Library"],
    ["/library/pictures/7", "Library"],
    ["/batch", "Library"],
    ["/queue", "Queue"],
    ["/recipes", "Queue"],
    ["/history", "History"],
    ["/settings", "Settings"],
    ["/settings/about", "Settings"],
  ])("keeps the place of %s lit: %s", (page, tile) => {
    expect(litOn(page)).toEqual([tile]);
  });

  it("badges the Queue with how far the batch being made has got", async () => {
    renderRail("/", { ...IDLE, working: true, batch: "Holiday prints", progress: 0.37 });

    const queue = await screen.findByRole("link", { name: "Queue, Holiday prints is 37% made" });
    await waitFor(() => expect(queue).toHaveTextContent("Queue37%"));
  });

  it("says how many pictures wait when nothing is being made, and nothing when none do", () => {
    expect(badgeOf({ ...IDLE, waiting: 48 })).toEqual({ text: "48", label: "48 pictures wait" });
    expect(badgeOf(IDLE)).toBeNull();
    expect(badgeOf(undefined)).toBeNull();
  });
});
