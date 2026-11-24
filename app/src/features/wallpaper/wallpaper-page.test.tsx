import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ClaimProvider, useClaims } from "@/components/shell/claim";
import { EngineProvider, type StudioState } from "@/lib/engine";
import {
  choice,
  FOLDERS,
  fakeEngine,
  LIBRARY,
  monitor,
  page,
  part,
  picture,
  READY,
  SIDE,
  studio,
} from "@/test/engine";
import { WallpaperPage } from "./wallpaper-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn(), startWithWindows: false }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function Address() {
  const location = useLocation();
  return <p data-testid="address">{`${location.pathname}${location.search}`}</p>;
}

/** Takes a picture as a drop or a paste would hand it over. */
function Dropper() {
  const claims = useClaims();
  return (
    <button
      type="button"
      onClick={() => claims.current?.take({ id: 42, name: "Pier at dawn.jpg", outside: true })}
    >
      Drop Pier at dawn
    </button>
  );
}

/** The studio, drawn once the engine's answered: its monitors, or why there are none. */
async function renderStudio(at = "/wallpaper") {
  shell.invoke.mockImplementation(async (command: string, args?: { on?: boolean }) => {
    if (command === "engine_status") return READY;
    if (command === "pick_folder") return "D:\\Wallpapers";
    if (command === "start_with_windows") return shell.startWithWindows;
    if (command === "set_start_with_windows") {
      shell.startWithWindows = Boolean(args?.on);
      return shell.startWithWindows;
    }
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <ClaimProvider>
          <MemoryRouter initialEntries={[at]}>
            <Routes>
              <Route path="/wallpaper" element={<WallpaperPage />} />
              <Route path="/library" element={<p>The library</p>} />
            </Routes>
            <Address />
            <Dropper />
          </MemoryRouter>
        </ClaimProvider>
      </EngineProvider>
    </QueryClientProvider>,
  );
  await act(async () => {});
  await screen.findByText(/An app that draws its own desktop hides it/);
}

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

/** The engine with the studio as `now` (`state.now`, which an answer may change), and what the
 * studio's changes asked for, in order. */
function engine(now: StudioState, answers: Record<string, unknown> = {}) {
  const state = { now };
  const asked: { method: string; path: string; body: unknown }[] = [];
  const note = (method: string) => (init: RequestInit | undefined, url: URL) => {
    asked.push({
      method,
      path: `${url.pathname}${url.search}`,
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    return state.now;
  };
  const fetch = fakeEngine({
    "/wallpaper": () => state.now,
    "PUT /wallpaper": note("PUT"),
    "PUT /wallpaper/pictures": note("PUT"),
    "DELETE /wallpaper/pictures": note("DELETE"),
    "POST /wallpaper/set": note("POST"),
    "POST /wallpaper/save": note("POST"),
    "POST /wallpaper/cancel": note("POST"),
    "PUT /wallpaper/daily": note("PUT"),
    "/wallpaper/monitors/studio27/wallpaper": blob,
    "/wallpaper/monitors/side24/wallpaper": blob,
    "/pictures/11/view": blob,
    "/pictures/11/thumbnail": blob,
    "/pictures/12/thumbnail": blob,
    "/folders": FOLDERS,
    "/library": { ...LIBRARY, favourites: 2 },
    "/tools": [],
    ...answers,
  });
  return { fetch, asked, state };
}

describe("WallpaperPage", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
    shell.startWithWindows = false;
    // jsdom has neither: the sliders measure their thumbs, and a drag holds its pointer.
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private told: ResizeObserverCallback) {}
        observe(target: Element) {
          this.told(
            [{ target, contentRect: { width: 300, height: 20 } } as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          );
        }
        unobserve() {}
        disconnect() {}
      },
    );
    Element.prototype.setPointerCapture = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("draws the monitors as Windows arranges them, each with its name, size and wallpaper", async () => {
    engine(studio());
    await renderStudio();

    expect(screen.getByRole("heading", { level: 1, name: "Wallpaper" })).toBeVisible();
    const monitors = screen.getByRole("group", { name: "Your monitors" });
    const main = within(monitors).getByRole("button", { name: /^Studio 27, 2560 × 1440/ });
    expect(main).toHaveAttribute("aria-pressed", "true");
    expect(within(monitors).getByText("2560 × 1440")).toHaveClass("font-mono");
    expect(within(monitors).getByText("1920 × 1080")).toBeVisible();
    expect(within(monitors).getByText("Main")).toBeVisible();
    // Each shows the wallpaper Windows has on it, till a picture's chosen.
    await waitFor(() =>
      expect(within(main).getByRole("img", { name: "Its wallpaper now" })).toHaveAttribute(
        "src",
        "blob:made-up",
      ),
    );
    expect(screen.getByText(/An app that draws its own desktop hides it/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Set as wallpaper" })).toBeDisabled();
  });

  it("picks a picture for the monitor chosen from the favourites", async () => {
    const { fetch, asked } = engine(studio(), {
      "/pictures": page([
        picture(11, "Harbour at dusk.jpg", "2026-11-14T18:42:07", { favourite: true }),
        picture(12, "Little sail.jpg", "2026-11-14T16:05:00", { favourite: true }),
      ]),
    });
    await renderStudio();

    fireEvent.click(await screen.findByRole("button", { name: /^Side 24/ }));
    fireEvent.click(screen.getByRole("button", { name: "Pick a picture…" }));
    const card = await screen.findByRole("dialog", { name: "Pick a picture" });
    expect(within(card).getByText("For Side 24 · 1920 × 1080")).toBeVisible();
    fireEvent.click(await within(card).findByRole("button", { name: "Little sail" }));

    await waitFor(() =>
      expect(asked).toEqual([
        {
          method: "PUT",
          path: "/wallpaper/pictures",
          body: { monitor: "side24", pictureId: 12, shape: "crop" },
        },
      ]),
    );
    const listed = fetch.mock.calls
      .map(([input]) => new URL(String(input)))
      .find((url) => url.pathname === "/pictures");
    expect(listed?.searchParams.get("favourites")).toBe("1");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says when there are no favourites yet, and picks from all pictures instead", async () => {
    engine(studio(), {
      "/pictures": (_init: unknown, url: URL) =>
        url.searchParams.get("favourites") === "1"
          ? page([])
          : page([picture(12, "Little sail.jpg", "2026-11-14T16:05:00")]),
    });
    await renderStudio();

    fireEvent.click(await screen.findByRole("button", { name: "Pick a picture…" }));
    const card = await screen.findByRole("dialog", { name: "Pick a picture" });
    expect(await within(card).findByText("No favourites yet")).toBeVisible();
    fireEvent.click(within(card).getByRole("radio", { name: "All pictures" }));

    expect(await within(card).findByRole("button", { name: "Little sail" })).toBeVisible();
  });

  it("takes a picture dropped or pasted for the monitor chosen", async () => {
    const { asked } = engine(studio());
    await renderStudio();

    await screen.findByRole("group", { name: "Your monitors" });
    fireEvent.click(screen.getByRole("button", { name: "Drop Pier at dawn" }));

    await waitFor(() =>
      expect(asked).toEqual([
        {
          method: "PUT",
          path: "/wallpaper/pictures",
          body: { monitor: "studio27", pictureId: 42, shape: "crop" },
        },
      ]),
    );
  });

  it("chooses the picture a picture's page sent for the main monitor, and forgets it", async () => {
    const { asked } = engine(studio());
    await renderStudio("/wallpaper?picture=42");

    await waitFor(() =>
      expect(asked).toEqual([
        {
          method: "PUT",
          path: "/wallpaper/pictures",
          body: { monitor: "studio27", pictureId: 42, shape: "crop" },
        },
      ]),
    );
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/wallpaper$/));
  });

  it("lays one picture across all of them, with a gap for the bezels", async () => {
    const { asked } = engine(
      studio({
        layout: "across",
        choices: [choice({ monitor: null })],
        parts: [
          part({ area: { x: 0, y: 0.1, width: 0.571, height: 0.75 } }),
          part({ monitor: "side24", width: 1920, height: 1080 }),
        ],
      }),
    );
    await renderStudio();

    expect(await screen.findByText("All monitors · 4480 × 1440")).toBeVisible();
    const gap = screen.getByRole("slider", { name: "Gap for the bezels" });
    fireEvent.keyDown(gap, { key: "ArrowRight" });
    await waitFor(() => expect(asked).toHaveLength(1)); // once it settles
    fireEvent.click(screen.getByRole("radio", { name: "One for each" }));

    await waitFor(() =>
      expect(asked.map((each) => each.body)).toEqual([
        { layout: "across", gap: 1 },
        { layout: "each", gap: 1 },
      ]),
    );
  });

  it("never sends a gap still settling with the layout it had before a switch", async () => {
    const { asked } = engine(
      studio({ layout: "across", choices: [choice({ monitor: null })], parts: [part()] }),
    );
    await renderStudio();

    fireEvent.keyDown(screen.getByRole("slider", { name: "Gap for the bezels" }), {
      key: "ArrowRight",
    });
    fireEvent.click(screen.getByRole("radio", { name: "One for each" }));
    await new Promise((resolve) => setTimeout(resolve, 400)); // past the gap's settling

    expect(asked.map((each) => each.body)).toEqual([{ layout: "each", gap: 1 }]);
  });

  it("says Windows shows an HDR photo's wallpaper as an ordinary picture", async () => {
    const hdr = choice();
    engine(
      studio({ choices: [{ ...hdr, picture: { ...hdr.picture, hdr: true } }], parts: [part()] }),
    );
    await renderStudio();

    expect(
      await screen.findByText(/Windows shows a wallpaper as an ordinary picture/),
    ).toBeInTheDocument();
  });

  it("moves where a part is cut by dragging it, and zooms with the keyboard", async () => {
    const { asked } = engine(studio({ choices: [choice({ zoom: 2 })], parts: [part()] }));
    await renderStudio();

    const main = await screen.findByRole("button", { name: /^Studio 27/ });
    fireEvent.pointerDown(main, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
    fireEvent.pointerMove(main, { clientX: 60, clientY: 100, pointerId: 1 });
    fireEvent.pointerUp(main, { clientX: 60, clientY: 100, pointerId: 1 });

    await waitFor(() => expect(asked).toHaveLength(1));
    const moved = asked[0]?.body as { x: number; y: number; zoom: number };
    expect(moved.x).toBeGreaterThan(0.5); // the picture moved left: the part's middle moved right
    expect(moved.zoom).toBe(2);

    fireEvent.keyDown(main, { key: "+" });
    await waitFor(() => expect(asked).toHaveLength(2));
    const zoomed = asked[1]?.body as { zoom: number } | undefined;
    expect(zoomed?.zoom).toBeGreaterThan(2);
  });

  it("starts a key's move from the picture chosen now, not one moved before it", async () => {
    const { asked, state } = engine(studio({ choices: [choice({ zoom: 2 })], parts: [part()] }));
    await renderStudio();

    const main = await screen.findByRole("button", { name: /^Studio 27/ });
    fireEvent.pointerDown(main, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
    fireEvent.pointerMove(main, { clientX: 20, clientY: 100, pointerId: 1 });
    fireEvent.pointerUp(main, { clientX: 20, clientY: 100, pointerId: 1 });
    await waitFor(() => expect(asked).toHaveLength(1));
    // Another picture comes, cut around its subject (a drop, say), and the studio catches up.
    state.now = studio({
      choices: [
        choice({
          zoom: 2,
          picture: { ...choice().picture, id: 12, name: "Little sail.jpg", version: "v12" },
        }),
      ],
      parts: [part({ picture: 12 })],
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Drop Pier at dawn" }));
    });
    await waitFor(() => expect(asked).toHaveLength(2));
    await waitFor(() => expect(screen.getByText("Little sail")).toBeVisible());

    fireEvent.keyDown(main, { key: "ArrowRight" });

    await waitFor(() => expect(asked).toHaveLength(3));
    const moved = asked[2]?.body as { pictureId: number; x: number } | undefined;
    expect(moved?.pictureId).toBe(12);
    expect(moved?.x).toBeCloseTo(0.5 + 0.05 * 0.5); // from its subject, a step of the part seen
  });

  it("says when a picture is far too small, what it'll look like, and offers Fast and Best", async () => {
    const { asked } = engine(
      studio({
        choices: [choice()],
        parts: [
          part({
            method: "ai",
            scale: 8,
            warning:
              "That's 8 times bigger than the picture's 320 × 180: beyond 4 times, detail can't be found, so it looks painted rather than real.",
          }),
        ],
      }),
    );
    await renderStudio();

    expect(await screen.findByText(/looks painted rather than real/)).toBeVisible();
    expect(screen.getByText(/made 8 times bigger/)).toBeVisible();
    fireEvent.click(screen.getByRole("radio", { name: "Best" }));

    await waitFor(() =>
      expect(asked.at(-1)?.body).toEqual(expect.objectContaining({ quality: "best" })),
    );
  });

  it("says before the first set that Windows' slideshow and spotlight go off", async () => {
    engine(studio({ slideshow: true, spotlight: true, choices: [choice()], parts: [part()] }));
    await renderStudio();

    expect(await screen.findByText(/Windows' slideshow is on/)).toBeVisible();
    expect(screen.getByText(/Windows spotlight is on/)).toBeVisible();
  });

  it("sets the wallpaper, saying how far it's got, then that it's set", async () => {
    const making = studio({
      choices: [choice()],
      parts: [part()],
      making: {
        id: 3,
        purpose: "set",
        state: "making",
        progress: 0.4,
        secondsLeft: null,
        problem: null,
        setAt: null,
        saved: [],
      },
    });
    const answer: { state?: { now: StudioState } } = {};
    const { asked, state } = engine(studio({ choices: [choice()], parts: [part()] }), {
      "POST /wallpaper/set": () => {
        if (answer.state) answer.state.now = making;
        return making;
      },
    });
    answer.state = state;
    await renderStudio();

    fireEvent.click(await screen.findByRole("button", { name: "Set as wallpaper" }));

    expect(
      await screen.findByRole("progressbar", { name: "Making the wallpaper" }),
    ).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getByText("Working out the time…")).toBeVisible();
    expect(asked).toEqual([]);
  });

  it("says how long a wallpaper being made has left, and stops it", async () => {
    const { asked } = engine(
      studio({
        choices: [choice()],
        parts: [part()],
        making: {
          id: 3,
          purpose: "set",
          state: "making",
          progress: 0.5,
          secondsLeft: 42,
          problem: null,
          setAt: null,
          saved: [],
        },
      }),
    );
    await renderStudio();

    expect(await screen.findByText("about 40 s left")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));

    await waitFor(() =>
      expect(asked).toEqual([{ method: "POST", path: "/wallpaper/cancel", body: null }]),
    );
  });

  it("says a wallpaper that couldn't be set, in Windows' words", async () => {
    engine(
      studio({
        choices: [choice()],
        parts: [part()],
        making: {
          id: 3,
          purpose: "set",
          state: "failed",
          progress: 0,
          secondsLeft: null,
          problem:
            "Windows wouldn't set the wallpaper. Your wallpaper is as it was: try again in a moment.",
          setAt: null,
          saved: [],
        },
      }),
    );
    await renderStudio();

    expect(await screen.findByRole("alert")).toHaveTextContent("Your wallpaper is as it was");
  });

  it("says why a picture Mado can't read can't be a wallpaper, rather than waiting", async () => {
    engine(
      studio({
        choices: [choice({ problem: "Broken.jpg won't open: it isn't a picture Mado reads." })],
        parts: [],
      }),
    );
    await renderStudio();

    expect(await screen.findByText(/Broken.jpg won't open/)).toBeVisible();
    expect(screen.queryByText("Mado is looking at the picture…")).toBeNull();
    expect(screen.getByRole("button", { name: "Set as wallpaper" })).toBeDisabled();
  });

  it("leaves an extended part's zoom alone, as it has none", async () => {
    const { asked } = engine(studio({ choices: [choice({ shape: "extend" })], parts: [part()] }));
    await renderStudio();

    const main = await screen.findByRole("button", { name: /^Studio 27/ });
    fireEvent.keyDown(main, { key: "+" });
    fireEvent.keyDown(main, { key: "-" });
    await act(async () => {});

    expect(asked).toEqual([]);
  });

  it("keeps a picture sent from its page till there are monitors to make it for", async () => {
    const { asked, state } = engine(studio({ monitors: [] }));
    await renderStudio("/wallpaper?picture=42");
    expect(await screen.findByText("Windows didn't say what monitors there are")).toBeVisible();
    expect(asked).toEqual([]);

    state.now = studio();
    fireEvent.click(screen.getByRole("button", { name: "Look again" }));

    await waitFor(() =>
      expect(asked).toEqual([
        {
          method: "PUT",
          path: "/wallpaper/pictures",
          body: { monitor: "studio27", pictureId: 42, shape: "crop" },
        },
      ]),
    );
  });

  it("sends the daily change's time once it's typed, not each step on the way", async () => {
    const { asked } = engine(studio({ daily: { ...studio().daily, on: true, candidates: 3 } }));
    await renderStudio();
    fireEvent.click(await screen.findByRole("tab", { name: "Every day" }));

    const time = screen.getByLabelText("At");
    fireEvent.change(time, { target: { value: "00:00" } }); // typing 08:00: its hours pass 00
    fireEvent.change(time, { target: { value: "08:00" } });

    await waitFor(() => expect(asked).toHaveLength(1), { timeout: 2000 });
    expect(asked[0]?.body).toEqual({ on: true, at: "08:00", layout: "each", folder: null });
  });

  it("saves the parts as pictures into a folder picked", async () => {
    const { asked } = engine(studio({ choices: [choice()], parts: [part()] }));
    await renderStudio();

    fireEvent.click(await screen.findByRole("button", { name: "Save as pictures…" }));
    const card = await screen.findByRole("dialog", { name: "Save as pictures" });
    fireEvent.click(within(card).getByRole("button", { name: "Pick a folder…" }));
    expect(await within(card).findByText("D:\\Wallpapers")).toBeVisible();
    fireEvent.click(within(card).getByRole("radio", { name: "One picture of them all" }));
    fireEvent.click(within(card).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(asked).toEqual([
        {
          method: "POST",
          path: "/wallpaper/save",
          body: { what: "whole", folder: "D:\\Wallpapers", format: "PNG" },
        },
      ]),
    );
  });

  it("puts back the owner's own wallpaper, and says what Windows can't", async () => {
    const back = {
      studio: studio(),
      told: [
        "Windows spotlight was on, and only Windows turns it on again: choose Windows spotlight in Settings › Personalisation › Background.",
      ],
    };
    engine(
      studio({
        monitors: [monitor({ mine: true }), { ...SIDE, mine: true }],
        yours: {
          kept: [{ monitor: "studio27", name: "Studio 27", path: "C:\\Beach.jpg", there: true }],
          slideshow: false,
          spotlight: true,
          showingMine: true,
        },
      }),
      { "POST /wallpaper/put-back": back },
    );
    await renderStudio();

    fireEvent.click(await screen.findByRole("button", { name: "Put back your own wallpaper" }));

    expect(await screen.findByText(/only Windows turns it on again/)).toBeVisible();
  });

  it("keeps a monitor's picture while it's unplugged, and asks for one for a new monitor", async () => {
    engine(
      studio({
        monitors: [
          monitor(),
          monitor({
            key: "new",
            name: "Screen 3",
            number: 3,
            main: false,
            x: -1920,
            width: 1920,
            height: 1080,
            wallpaper: null,
            shown: false,
            version: null,
          }),
        ],
        choices: [choice(), choice({ monitor: "side24", connected: false })],
        parts: [part()],
      }),
    );
    await renderStudio();

    expect(
      await screen.findByText(/A monitor isn't connected: its picture waits for it/),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /^Screen 3/ }));
    expect(screen.getByRole("button", { name: "Pick a picture…" })).toBeVisible();
  });

  it("changes every day once turned on, and says Mado must be running, Start with Windows beside it", async () => {
    const { asked } = engine(studio({ daily: { ...studio().daily, candidates: 12, skipped: 2 } }));
    await renderStudio();

    fireEvent.click(await screen.findByRole("tab", { name: "Every day" }));
    fireEvent.click(screen.getByRole("switch", { name: "Change it every day" }));

    await waitFor(() =>
      expect(asked).toEqual([
        {
          method: "PUT",
          path: "/wallpaper/daily",
          body: { on: true, at: "07:00", layout: "each", folder: null },
        },
      ]),
    );
    expect(screen.getByText(/needs Mado open, or waiting in the tray/)).toBeVisible();
    expect(screen.getByText(/2 aren't there now/)).toBeVisible();
    const start = screen.getByRole("switch", { name: "Start with Windows" });
    fireEvent.click(start);
    await waitFor(() => expect(shell.startWithWindows).toBe(true));
  });

  it("says there are no favourites yet for the daily change", async () => {
    engine(studio());
    await renderStudio();

    fireEvent.click(await screen.findByRole("tab", { name: "Every day" }));

    expect(screen.getByText(/No favourites yet/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Show your favourites" })).toHaveAttribute(
      "href",
      "/library?favourites=1",
    );
  });

  it("says why it can't, when Windows doesn't say what monitors there are", async () => {
    engine(
      studio({
        monitors: [],
        problem: "Windows' desktop wallpaper didn't answer.",
      }),
    );
    await renderStudio();

    expect(await screen.findByText(/didn't answer/)).toBeVisible();
  });
});
