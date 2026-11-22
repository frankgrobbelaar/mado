import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { EngineProvider, useBackups } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { Notices } from "./notices";

type Handler = (event: { payload: unknown }) => void;
const shell = vi.hoisted(() => ({ handlers: new Map<string, Handler>(), invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: async (name: string, handler: Handler) => {
    shell.handlers.set(name, handler);
    return () => shell.handlers.delete(name);
  },
}));

function asked(fetch: ReturnType<typeof fakeEngine>, path: string): number {
  return fetch.mock.calls.filter(([input]) => new URL(String(input)).pathname === path).length;
}

function Listed() {
  useBackups(); // a screen showing what the engine did
  return <Notices />;
}

describe("Notices", () => {
  it("shows what the engine tells while the window is open, leading where it says", async () => {
    shell.invoke.mockResolvedValue(READY);
    const fetch = fakeEngine({ "/backups": { backups: [], restored: null } });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EngineProvider>
          <MemoryRouter>
            <Routes>
              <Route index element={<Listed />} />
              <Route path="/settings/:section" element={<p>Your data</p>} />
            </Routes>
          </MemoryRouter>
        </EngineProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(shell.handlers.has("notice")).toBe(true));
    await waitFor(() => expect(asked(fetch, "/backups")).toBe(1));

    act(() =>
      shell.handlers.get("notice")?.({
        payload: {
          title: "Backed up",
          body: "Mado's records · checked · 4 MB",
          link: "/settings/data",
        },
      }),
    );

    const note = await screen.findByRole("status");
    await waitFor(() => expect(asked(fetch, "/backups")).toBe(2)); // what changed, asked again
    expect(note).toHaveTextContent("Backed up");
    expect(note).toHaveTextContent("Mado's records · checked · 4 MB");
    screen.getByRole("button", { name: "View" }).click();
    expect(await screen.findByText("Your data")).toBeInTheDocument();
  });

  it("stays while it's pointed at or focused, and goes when dismissed", async () => {
    shell.invoke.mockResolvedValue(READY);
    fakeEngine({});
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EngineProvider>
          <MemoryRouter>
            <Notices />
          </MemoryRouter>
        </EngineProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(shell.handlers.has("notice")).toBe(true));
    vi.useFakeTimers();
    try {
      act(() =>
        shell.handlers.get("notice")?.({
          payload: {
            title: "The backup didn't finish",
            body: "There isn't room on C:",
            link: null,
          },
        }),
      );
      const note = screen.getByRole("status");

      fireEvent.mouseEnter(note);
      act(() => vi.advanceTimersByTime(60_000));
      expect(screen.getByRole("status")).toBeInTheDocument(); // read at leisure

      fireEvent.mouseLeave(note);
      act(() => vi.advanceTimersByTime(60_000));
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }

    act(() =>
      shell.handlers.get("notice")?.({
        payload: { title: "Backed up", body: "Mado's records", link: null },
      }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
