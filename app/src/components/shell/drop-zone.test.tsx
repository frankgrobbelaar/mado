import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import { batchPicture, fakeEngine, PICKED, READY } from "@/test/engine";
import { DropZone } from "./drop-zone";

type Dropped = { payload: { type: string; paths?: string[] } };

const shell = vi.hoisted(() => ({
  invoke: vi.fn(),
  dropped: null as ((event: Dropped) => void) | null,
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("@tauri-apps/api/webview", () => ({
  getCurrentWebview: () => ({
    onDragDropEvent: async (handler: (event: Dropped) => void) => {
      shell.dropped = handler;
      return () => {
        shell.dropped = null;
      };
    },
  }),
}));

function Where() {
  const location = useLocation();
  return <p data-testid="where">{`${location.pathname} ${JSON.stringify(location.state)}`}</p>;
}

function renderDrop() {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/history"]}>
          <Routes>
            <Route path="*" element={<Where />} />
          </Routes>
          <DropZone />
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

async function drop(event: Dropped["payload"]) {
  await vi.waitFor(() => expect(shell.dropped).not.toBeNull());
  await vi.waitFor(() => expect(shell.invoke).toHaveBeenCalledWith("engine_status"));
  await act(async () => {}); // the engine's status, ready, reaches the page first
  act(() => shell.dropped?.({ payload: event }));
}

describe("DropZone", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("says what dropping does while pictures are over the window", async () => {
    fakeEngine({});
    renderDrop();

    await drop({ type: "enter", paths: ["D:\\Pictures\\Holiday"] });

    expect(await screen.findByText("Drop them here")).toBeInTheDocument();
    await drop({ type: "leave" });
    expect(screen.queryByText("Drop them here")).toBeNull();
  });

  it("opens pictures dropped from anywhere in Many at once, from any page", async () => {
    fakeEngine({ "POST /batches/pictures": PICKED });
    renderDrop();

    await drop({ type: "drop", paths: ["D:\\Pictures\\Holiday"] });

    await vi.waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent('/batch {"pick":{"how":"dropped"'),
    );
  });

  it("opens one picture from the library on its page", async () => {
    fakeEngine({
      "POST /batches/pictures": { ...PICKED, pictures: [batchPicture(11, "Harbour at dusk.heic")] },
    });
    renderDrop();

    await drop({ type: "drop", paths: ["D:\\Pictures\\Phone\\Harbour at dusk.heic"] });

    await vi.waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent("/library/pictures/11"),
    );
  });
});
