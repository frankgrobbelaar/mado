import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { InUse } from "./in-use";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function renderNote() {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <InUse />
      </EngineProvider>
    </QueryClientProvider>,
  );
}

const HARBOUR = {
  job: 7,
  name: "Harbour at dusk.jpg",
  path: "D:\\Pictures\\Phone\\Harbour at dusk.jpg",
  verb: "replace",
  since: "2026-11-23T14:02:00+02:00",
  until: "2026-11-23T14:02:30+02:00",
  batch: "Holiday prints",
};

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) => (init?.method ?? "GET") === method && String(input).endsWith(path),
  );
}

describe("InUse", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("says a picture is open in another app, and tries it again now or skips it", async () => {
    const fetch = fakeEngine({
      "/jobs/held": [HARBOUR, { ...HARBOUR, job: 8, name: "Still lake.jpg", verb: "read" }],
      "POST /jobs/7/try-now": null,
      "POST /jobs/7/skip": null,
    });
    renderNote();

    const note = await screen.findByRole("status");
    expect(note).toHaveTextContent(
      "Harbour at dusk.jpg is open in another appMado can't replace it while it's open. Close it there and Mado tries again by itself.",
    );
    expect(note).toHaveTextContent("1 more waits the same way");

    fireEvent.click(screen.getByRole("button", { name: "Try again now" }));
    await waitFor(() => expect(sent(fetch, "POST", "/jobs/7/try-now")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Skip it" }));
    await waitFor(() => expect(sent(fetch, "POST", "/jobs/7/skip")).toHaveLength(1));
  });

  it("isn't there while no picture waits so", async () => {
    const fetch = fakeEngine({ "/jobs/held": [] });
    renderNote();

    await waitFor(() => expect(sent(fetch, "GET", "/jobs/held")).toHaveLength(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
