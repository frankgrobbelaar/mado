import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  callEngine,
  EngineError,
  EngineProvider,
  type EngineStatus,
  useEngine,
  usePictureImage,
} from "./engine";

const shell = vi.hoisted(() => ({
  invoke: vi.fn(),
  listeners: [] as ((event: { payload: unknown }) => void)[],
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: async (_event: string, handler: (event: { payload: unknown }) => void) => {
    shell.listeners.push(handler);
    return () => {};
  },
}));

const ready = {
  state: "ready",
  url: "http://127.0.0.1:5000",
  token: "secret",
} as const satisfies EngineStatus;

function emit(status: EngineStatus) {
  for (const listener of shell.listeners) listener({ payload: status });
}

function ShowState() {
  return <p>{useEngine().state}</p>;
}

describe("EngineProvider", () => {
  beforeEach(() => {
    shell.listeners.length = 0;
    shell.invoke.mockReset();
  });

  it("starts from what the shell reports now", async () => {
    shell.invoke.mockResolvedValue(ready);

    render(
      <EngineProvider>
        <ShowState />
      </EngineProvider>,
    );

    expect(await screen.findByText("ready")).toBeInTheDocument();
  });

  it("follows the shell's status events", async () => {
    shell.invoke.mockResolvedValue({ state: "starting" });
    render(
      <EngineProvider>
        <ShowState />
      </EngineProvider>,
    );
    await screen.findByText("starting");

    act(() => emit({ state: "failed", message: "It crashed.", details: "" }));

    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("never lets a late answer overwrite a newer event", async () => {
    let answer: (status: EngineStatus) => void = () => {};
    shell.invoke.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    render(
      <EngineProvider>
        <ShowState />
      </EngineProvider>,
    );
    await waitFor(() => expect(shell.listeners).toHaveLength(1));

    act(() => emit(ready));
    await act(async () => answer({ state: "starting" }));

    expect(screen.getByText("ready")).toBeInTheDocument();
  });
});

describe("callEngine", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends this launch's token", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await callEngine(ready, "/health");

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("http://127.0.0.1:5000/health");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret");
  });

  it("turns an error answer into an EngineError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(async () => new Response("no", { status: 401 })),
    );

    await expect(callEngine(ready, "/health")).rejects.toThrow(EngineError);
  });

  it("says so in plain words when the engine doesn't answer at all", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await expect(callEngine(ready, "/health")).rejects.toThrow("Mado's engine didn't answer.");
  });
});

function Picture({ path }: { path: string | null }) {
  const { address, problem } = usePictureImage(path);
  return <p>{address ?? problem ?? "nothing yet"}</p>;
}

describe("usePictureImage", () => {
  beforeEach(() => {
    shell.listeners.length = 0;
    shell.invoke.mockReset();
    shell.invoke.mockResolvedValue(ready);
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("fetches a picture with the token and shows it as an address of its own", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => new Response(new Blob(["picture"])));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <EngineProvider>
        <Picture path="/pictures/7/thumbnail?v=1" />
      </EngineProvider>,
    );

    expect(await screen.findByText("blob:made-up")).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret");
  });

  it("lets a picture's request go once it isn't wanted any more", async () => {
    const signals: AbortSignal[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((_url, init) => {
        if (init?.signal) signals.push(init.signal);
        return new Promise<Response>(() => {}); // still on its way
      }),
    );
    const { rerender } = render(
      <EngineProvider>
        <Picture path="/pictures/7/view?v=1" />
      </EngineProvider>,
    );
    await waitFor(() => expect(signals).toHaveLength(1));

    rerender(
      <EngineProvider>
        <Picture path={null} />
      </EngineProvider>,
    );

    await waitFor(() => expect(signals[0]?.aborted).toBe(true));
  });
});
