import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import { job } from "@/test/engine";
import { JobCard } from "./job-card";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => undefined) }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function renderCard(made: ReturnType<typeof job>) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <EngineProvider>
        <MemoryRouter>
          <JobCard job={made} />
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

describe("JobCard", () => {
  it("says a Save waits while its picture is open in another app, and tries again by itself", () => {
    renderCard(
      job({
        state: "queued",
        stage: null,
        progress: 0,
        secondsLeft: null,
        heldUntil: "2026-11-23T14:02:30+02:00",
        problem:
          "Harbour at dusk.heic is open in another app. Mado can't replace it while it's open.",
      }),
    );

    expect(screen.getByText("Waiting: it's open in another app")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Close it there and Mado tries again by itself, every 30 seconds for 10 minutes.",
      ),
    ).toBeInTheDocument();
  });

  it("says plainly that a Save waits to start otherwise", () => {
    renderCard(job({ state: "queued", stage: null, progress: 0, secondsLeft: null }));

    expect(screen.getByText("Waiting to start")).toBeInTheDocument();
  });
});
