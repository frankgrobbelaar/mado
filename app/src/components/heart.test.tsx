import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { HeartButton } from "./heart";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

async function renderHeart(favourite: boolean, on: "tile" | "page" = "page") {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <HeartButton picture={{ id: 7, name: "Little sail.jpg", favourite }} on={on} />
      </EngineProvider>
    </QueryClientProvider>,
  );
  await act(async () => {}); // the engine is ready, as the shell says
}

describe("HeartButton", () => {
  beforeEach(() => {
    shell.invoke.mockImplementation(async (command: string) =>
      command === "engine_status" ? READY : undefined,
    );
  });

  it("gives a picture its heart at once, and the engine keeps it", async () => {
    const asked: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      fakeEngine({
        "PUT /pictures/7/favourite": (init: RequestInit | undefined) => {
          asked.push(JSON.parse(String(init?.body)));
          return {};
        },
      }),
    );
    await renderHeart(false);

    const heart = screen.getByRole("button", { name: "Favourite Little sail" });
    expect(heart).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(heart);

    expect(heart).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(asked).toEqual([{ favourite: true }]));
  });

  it("takes a heart back, and on a tile it's always shown once given", async () => {
    vi.stubGlobal("fetch", fakeEngine({ "PUT /pictures/7/favourite": {} }));
    await renderHeart(true, "tile");

    const heart = screen.getByRole("button", { name: "Favourite Little sail" });
    expect(heart).toHaveAttribute("aria-pressed", "true");
    expect(heart.className).toContain("opacity-100");
    fireEvent.click(heart);

    expect(heart).toHaveAttribute("aria-pressed", "false");
  });

  it("says when the engine couldn't keep it, and shows it as it was", async () => {
    vi.stubGlobal("fetch", fakeEngine({}));
    await renderHeart(false);

    fireEvent.click(screen.getByRole("button", { name: "Favourite Little sail" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Favourite Little sail" })).toHaveAttribute(
        "aria-pressed",
        "false",
      ),
    );
    expect(screen.getByRole("button", { name: "Favourite Little sail" })).toHaveAttribute(
      "title",
      expect.stringContaining("couldn't"),
    );
  });
});
