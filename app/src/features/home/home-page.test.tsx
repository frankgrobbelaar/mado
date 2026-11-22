import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type EngineStatus } from "@/lib/engine";
import { fakeEngine, READY, SETTINGS } from "@/test/engine";
import { HomePage } from "./home-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function renderHome(engine: EngineStatus = READY) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? engine : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route index element={<HomePage />} />
            <Route path="/setup" element={<p>Setup</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

describe("HomePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("says honestly that Mado is being built", async () => {
    fakeEngine({ "/settings": SETTINGS });
    renderHome();

    expect(await screen.findByRole("heading", { name: "Mado is being built" })).toBeInTheDocument();
    expect(screen.getByText(/it changes nothing on this PC/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument(); // nothing to pretend with
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
});
