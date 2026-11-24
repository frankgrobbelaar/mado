import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  type DepthRead,
  EngineProvider,
  type Motion,
  type MotionFacts,
  type PictureDetails,
  type Tool,
} from "@/lib/engine";
import { FOLDERS, fakeEngine, PICTURES, plan, READY, SETTINGS, SIZES } from "@/test/engine";
import { PicturePage } from "./picture-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const DUSK = PICTURES[0] as (typeof PICTURES)[number];

const details: PictureDetails = {
  ...DUSK,
  folderId: 1,
  folder: "D:\\Pictures\\Phone",
  dir: "",
  modifiedAt: DUSK.takenAt,
  takenFrom: "camera",
  camera: "Testcam T7 Pro",
  orientation: 1,
  located: true,
  problem: null,
  damaged: false,
  outside: false,
  pasted: false,
  aside: false,
  savesTo: null,
};

/** Read: a subject found, not flat, on the card in a fifth of a second. */
const READ: DepthRead = {
  needs: [],
  read: true,
  flat: false,
  place: "card",
  seconds: 0.2,
  waited: 0,
  subject: true,
  focus: [0.62, 0.7],
  seeThrough: false,
  grey: false,
  megapixels: 12.2,
  tooBig: false,
};

const FACTS: MotionFacts = {
  ffmpeg: true,
  encoder: "h264_mf",
  encoderName: "Windows' own video encoder",
  sizes: [{ size: "1080p", width: 1920, height: 1440, bytes: 7_500_000 }],
  webp: { size: "1080p", width: 1280, height: 960, bytes: 24_000_000 },
  seconds: [3, 5, 8],
  needs: [],
};

function tool(id: string, name: string, size: number, state: Tool["state"] = "ready"): Tool {
  return {
    id,
    name,
    version: "models-2",
    purpose: "",
    licence: "Apache-2.0",
    size,
    when: "asked",
    state,
    done: 0,
    problem: null,
  };
}

const TOOLS = [
  tool("depth-anything-v2-small", "Depth Anything V2 Small", 99_072_196),
  tool("lama", "LaMa", 209_176_178),
  tool("ffmpeg", "ffmpeg", 76_972_461),
];

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

type Fetch = ReturnType<typeof fakeEngine>;

function engine(answers: Record<string, unknown> = {}): Fetch {
  return fakeEngine({
    "/folders": FOLDERS,
    "/settings": SETTINGS,
    "/pictures/11": details,
    "/pictures/11/neighbours": { before: [], after: [] },
    "/pictures/11/view": blob,
    "/pictures/11/full": blob,
    "/sizes": SIZES,
    "POST /screens": [],
    "POST /pictures/11/depth": READ,
    "/pictures/11/motion": FACTS,
    "POST /pictures/11/plan": plan({
      width: 4032,
      height: 3024,
      label: "",
      method: "keep",
      model: null,
      depth: "portrait blur at f/2.8",
      depthSeconds: 4,
      depthPlace: "card",
      seconds: 4,
    }),
    "POST /pictures/11/preview": () =>
      new Response(new Blob(["preview"], { type: "image/jpeg" }), {
        headers: { "X-Made-In": "0.4" },
      }),
    "/jobs": [],
    "/tools": TOOLS,
    "/queue/now": {
      working: false,
      paused: false,
      batch: null,
      over: 0,
      total: 0,
      progress: 0,
      waiting: 0,
    },
    ...answers,
  });
}

function renderPicture() {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command === "screens") return [{ width: 3440, height: 1440, main: true }];
    if (command === "pick_folder") return "D:\\Videos";
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/library/pictures/11?folder=1"]}>
          <Routes>
            <Route path="/library/pictures/:id" element={<PicturePage />} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function sent(fetch: Fetch, method: string, path: string): unknown[] {
  return fetch.mock.calls
    .filter(
      ([input, init]) =>
        (init?.method ?? "GET") === method && new URL(String(input)).pathname === path,
    )
    .map(([, init]) => JSON.parse(String(init?.body ?? "null")));
}

async function openDepth() {
  fireEvent.click(await screen.findByRole("tab", { name: "Depth" }));
  return screen.findByRole("region", { name: "Depth tools" });
}

describe("The Depth tab", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private told: ResizeObserverCallback) {}
        observe(target: Element) {
          this.told(
            [{ target, contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          );
        }
        unobserve() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists portrait blur, fog and tilt-shift, each off, and says it read the picture's depth", async () => {
    const fetch = engine();
    renderPicture();

    const tools = await openDepth();

    for (const name of ["Portrait blur", "Fog", "Tilt-shift"]) {
      expect(within(tools).getByRole("switch", { name })).not.toBeChecked();
    }
    expect(
      await screen.findByText(/Mado read how far away each part of it is in/),
    ).toBeInTheDocument();
    expect(screen.getByText("0.2 s")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save…" })).toBeDisabled();
    expect(sent(fetch, "POST", "/pictures/11/depth")[0]).toEqual({
      version: details.version,
      edits: [],
    });
    // How it differs from Edit's blur behind, as the switch is read.
    expect(
      within(tools).getByRole("switch", { name: "Portrait blur" }),
    ).toHaveAccessibleDescription(
      /Blur what's behind it, on the Edit tab, blurs everything behind a part evenly/,
    );
  });

  it("turns portrait blur on at f/2.8, in focus at its subject, and plans it", async () => {
    const fetch = engine();
    renderPicture();
    const tools = await openDepth();

    fireEvent.click(within(tools).getByRole("switch", { name: "Portrait blur" }));

    expect(within(tools).getByRole("slider", { name: /Aperture/ })).toHaveAttribute(
      "aria-valuetext",
      "f/2.8",
    );
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toEqual({
        edit: null,
        size: null,
        paint: null,
        look: null,
        depth: {
          portrait: { focus: null, aperture: 2.8, quality: null },
          fog: null,
          tilt: null,
        },
      }),
    );
    expect(
      await screen.findByText(/About 5 s on your graphics card, as Save makes it/),
    ).toBeVisible();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save…" })).toBeEnabled());
    expect(screen.getByText(/In focus at its subject, found as Cut out finds it/)).toBeVisible();
  });

  it("puts the focus where the picture is clicked", async () => {
    const fetch = engine();
    renderPicture();
    const tools = await openDepth();
    fireEvent.click(within(tools).getByRole("switch", { name: "Portrait blur" }));
    const shown = await screen.findByRole("img", { name: /After · Portrait blur at f\/2.8/ });
    const stage = shown.parentElement as HTMLElement;
    stage.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 1000, height: 750, right: 1000, bottom: 750 }) as DOMRect;

    fireEvent.pointerDown(stage, { clientX: 250, clientY: 375, pointerId: 1 });

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        depth: { portrait: { focus: [0.25, 0.5], aperture: 2.8, quality: null } },
      }),
    );
    expect(
      screen.getByText("In focus where you clicked. Click the picture to choose again."),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "In focus at its subject" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        depth: { portrait: { focus: null } },
      }),
    );
  });

  it("drags tilt-shift's band into place and makes it taller by its edge", async () => {
    const fetch = engine();
    renderPicture();
    const tools = await openDepth();
    fireEvent.click(within(tools).getByRole("switch", { name: "Tilt-shift" }));
    const shown = await screen.findByRole("img", { name: /After · Tilt-shift/ });
    const stage = shown.parentElement as HTMLElement;
    stage.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 1000, height: 600, right: 1000, bottom: 600 }) as DOMRect;
    stage.setPointerCapture = vi.fn();

    fireEvent.pointerDown(stage, { clientX: 500, clientY: 330, pointerId: 1 }); // inside the band
    fireEvent.pointerMove(stage, { clientX: 500, clientY: 240, pointerId: 1 });
    fireEvent.pointerUp(stage, { pointerId: 1 });

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        depth: { tilt: { centre: 0.4, height: 0.2, strength: 0.6 } },
      }),
    );
    // The band's lower edge, now at 0.5 down, dragged to 0.6: twice as far from its middle.
    fireEvent.pointerDown(stage, { clientX: 500, clientY: 300, pointerId: 2 });
    fireEvent.pointerMove(stage, { clientX: 500, clientY: 360, pointerId: 2 });
    fireEvent.pointerUp(stage, { pointerId: 2 });
    await waitFor(() => {
      const last = sent(fetch, "POST", "/pictures/11/plan").at(-1) as {
        depth: { tilt: { height: number } };
      };
      expect(last.depth.tilt.height).toBeCloseTo(0.4, 5);
    });
  });

  it("moves the focus and the band from the keyboard", async () => {
    const fetch = engine();
    renderPicture();
    const tools = await openDepth();
    fireEvent.click(within(tools).getByRole("switch", { name: "Portrait blur" }));
    fireEvent.click(within(tools).getByRole("switch", { name: "Tilt-shift" }));

    fireEvent.keyDown(await screen.findByRole("button", { name: /What's in focus/ }), {
      key: "ArrowRight",
    });
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        depth: { portrait: { focus: [0.64, 0.7] } },
      }),
    );
    const grip = screen.getByRole("button", { name: /Tilt-shift's band/ });
    fireEvent.keyDown(grip, { key: "ArrowUp" });
    fireEvent.keyDown(grip, { key: "ArrowRight" });
    await waitFor(() => {
      const last = sent(fetch, "POST", "/pictures/11/plan").at(-1) as {
        depth: { tilt: { centre: number; height: number } };
      };
      expect(last.depth.tilt.centre).toBeCloseTo(0.53, 5);
      expect(last.depth.tilt.height).toBeCloseTo(0.22, 5);
    });
  });

  it("puts the focus inside the band when both are on, the band moved by its edges or grip", async () => {
    const fetch = engine();
    renderPicture();
    const tools = await openDepth();
    fireEvent.click(within(tools).getByRole("switch", { name: "Portrait blur" }));
    fireEvent.click(within(tools).getByRole("switch", { name: "Tilt-shift" }));
    const shown = await screen.findByRole("img", { name: /After · Portrait blur/ });
    const stage = shown.parentElement as HTMLElement;
    stage.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 1000, height: 600, right: 1000, bottom: 600 }) as DOMRect;
    stage.setPointerCapture = vi.fn();

    fireEvent.pointerDown(stage, { clientX: 300, clientY: 372, pointerId: 1 }); // inside the band
    fireEvent.pointerUp(stage, { pointerId: 1 });

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/plan").at(-1)).toMatchObject({
        depth: {
          portrait: { focus: [0.3, 0.62] },
          tilt: { centre: 0.55, height: 0.2 },
        },
      }),
    );
  });

  it("asks for the depth model first, with its size, while tilt-shift works without it", async () => {
    engine({
      "/tools": [tool("depth-anything-v2-small", "Depth Anything V2 Small", 99_072_196, "missing")],
      "POST /pictures/11/depth": {
        ...READ,
        read: false,
        needs: [
          { id: "depth-anything-v2-small", name: "Depth Anything V2 Small", size: 99_072_196 },
        ],
        seconds: null,
        subject: false,
        focus: null,
      },
    });
    renderPicture();
    const tools = await openDepth();

    const card = await screen.findByRole("region", { name: "Depth Anything V2 Small to download" });
    expect(card).toHaveTextContent("99.1 MB");
    expect(
      within(card).getByRole("button", { name: "Download Depth Anything V2 Small" }),
    ).toBeVisible();
    fireEvent.click(within(tools).getByRole("switch", { name: "Fog" }));
    expect(
      await screen.findByText("After shows once Depth Anything V2 Small is downloaded"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Save waits for Depth Anything V2 Small, still to download/),
    ).toBeVisible();
  });

  it("says when a picture is flat, when it has no subject, and keeps its see-through parts", async () => {
    engine({
      "POST /pictures/11/depth": {
        ...READ,
        flat: true,
        subject: false,
        focus: null,
        seeThrough: true,
      },
    });
    renderPicture();
    const tools = await openDepth();

    expect(
      await screen.findByText(/Mado finds little depth in it: it reads as flat/),
    ).toBeInTheDocument();
    expect(screen.getByText("Its see-through parts stay as they are.")).toBeInTheDocument();
    fireEvent.click(within(tools).getByRole("switch", { name: "Portrait blur" }));
    expect(
      screen.getByText(/Mado found no subject in it, so it's in focus where it found/),
    ).toBeVisible();
  });

  it("says when the graphics card is busy with the queue", async () => {
    engine({
      "/queue/now": {
        working: true,
        paused: false,
        batch: "Holiday prints",
        over: 18,
        total: 48,
        progress: 0.4,
        waiting: 30,
      },
      "POST /pictures/11/preview": () => new Promise(() => {}),
    });
    renderPicture();
    const tools = await openDepth();
    fireEvent.click(within(tools).getByRole("switch", { name: "Portrait blur" }));

    expect(
      await screen.findByText(
        "Waiting for the graphics card: Holiday prints lets it go after the tile it's on",
        {},
        { timeout: 3000 },
      ),
    ).toBeInTheDocument();
  });
});

describe("A 3D photo", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private told: ResizeObserverCallback) {}
        observe(target: Element) {
          this.told(
            [{ target, contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          );
        }
        unobserve() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  async function openMotion() {
    fireEvent.click(await screen.findByRole("tab", { name: "Depth" }));
    fireEvent.click(await screen.findByRole("radio", { name: "3D photo" }));
    return screen.findByRole("region", { name: "3D photo" });
  }

  const done: Motion = {
    id: "ab12",
    state: "done",
    progress: 1,
    seconds: 14,
    width: 1920,
    height: 1440,
    bytes: 6_800_000,
    format: "mp4",
    encoderName: "Windows' own video encoder",
    problem: null,
  };

  it("is made as chosen, plays on the stage and is saved beside the picture", async () => {
    const fetch = engine({
      "POST /pictures/11/motion": { ...done, state: "waiting", progress: 0 },
      "/motion/ab12": done,
      "/motion/ab12/video": () => new Response(new Blob(["video"], { type: "video/mp4" })),
      "POST /motion/ab12/save": {
        path: "D:\\Pictures\\Phone\\Harbour at dusk (3D photo).mp4",
        name: "Harbour at dusk (3D photo).mp4",
        historyId: 9,
      },
    });
    renderPicture();
    const panel = await openMotion();

    fireEvent.click(within(panel).getByRole("radio", { name: "Sway" }));
    fireEvent.click(within(panel).getByRole("radio", { name: "3 s" }));
    expect(await screen.findByText("1920 × 1440 · 3 s · about 4.5 MB")).toBeInTheDocument();
    expect(screen.getByText("Made with Windows' own video encoder.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Make the 3D photo" }));

    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/motion").at(-1)).toEqual({
        version: details.version,
        edits: [],
        motion: "sway",
        seconds: 3,
        amount: 0.5,
        fill: "fast",
        size: "1080p",
        format: "mp4",
      }),
    );
    expect(
      await screen.findByLabelText("Harbour at dusk, moving through its depth"),
    ).toHaveAttribute("src", "blob:made-up");
    fireEvent.click(screen.getByRole("button", { name: "Save beside the picture" }));
    expect(await screen.findByText("Harbour at dusk (3D photo).mp4")).toBeInTheDocument();
    expect(sent(fetch, "POST", "/motion/ab12/save").at(-1)).toEqual({ folder: null });
  });

  it("stays made while another tab is looked at", async () => {
    const fetch = engine({
      "POST /pictures/11/motion": { ...done, state: "waiting", progress: 0 },
      "/motion/ab12": done,
      "/motion/ab12/video": () => new Response(new Blob(["video"], { type: "video/mp4" })),
    });
    renderPicture();
    await openMotion();
    await screen.findByText(/1920 × 1440 · 5 s · about/);
    fireEvent.click(screen.getByRole("button", { name: "Make the 3D photo" }));
    expect(
      await screen.findByLabelText("Harbour at dusk, moving through its depth"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Size" }));
    fireEvent.click(await screen.findByRole("tab", { name: "Depth" }));

    expect(await screen.findByRole("button", { name: "Save beside the picture" })).toBeVisible();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "DELETE")).toHaveLength(0);
  });

  it("is made as an animated WebP where the PC has no H.264 encoder", async () => {
    const fetch = engine({
      "/pictures/11/motion": { ...FACTS, encoder: null, encoderName: null },
      "POST /pictures/11/motion": { ...done, format: "webp", state: "waiting" },
      "/motion/ab12": { ...done, format: "webp" },
      "/motion/ab12/video": blob,
    });
    renderPicture();
    const panel = await openMotion();

    expect(
      await within(panel).findByText(/This PC has no H.264 encoder Mado may use/),
    ).toBeVisible();
    expect(within(panel).queryByRole("radio", { name: "MP4 video" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Make the 3D photo" }));
    await waitFor(() =>
      expect(sent(fetch, "POST", "/pictures/11/motion").at(-1)).toMatchObject({ format: "webp" }),
    );
    expect(
      await screen.findByRole("img", { name: "Harbour at dusk, moving through its depth" }),
    ).toBeInTheDocument();
  });

  it("asks for ffmpeg before an MP4, and says why one couldn't be made", async () => {
    engine({
      "/pictures/11/motion": { ...FACTS, ffmpeg: false, encoder: null, encoderName: null },
      "/tools": [...TOOLS.slice(0, 2), tool("ffmpeg", "ffmpeg", 76_972_461, "missing")],
    });
    renderPicture();
    await openMotion();

    expect(await screen.findByRole("region", { name: "ffmpeg to download" })).toHaveTextContent(
      "An animated WebP needs nothing more.",
    );
    expect(screen.getByRole("button", { name: "Make the 3D photo" })).toBeDisabled();
  });
});
