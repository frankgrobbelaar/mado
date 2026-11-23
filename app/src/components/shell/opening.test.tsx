import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { OpeningNote } from "@/features/batch/open";
import { EngineProvider } from "@/lib/engine";
import { fakeEngine, outsidePicture, PICKED, PICTURES, pictureDetails, READY } from "@/test/engine";
import { Opening, OpeningNotice, pathsIn } from "./opening";

type Dropped = { payload: { type: string; paths?: string[] } };

const shell = vi.hoisted(() => ({
  invoke: vi.fn(),
  dropped: null as ((event: Dropped) => void) | null,
  heard: new Map<string, () => void>(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: async (name: string, heard: () => void) => {
    shell.heard.set(name, heard);
    return () => shell.heard.delete(name);
  },
}));
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

const OUTSIDE = outsidePicture();
const DUSK = pictureDetails(PICTURES[0] as (typeof PICTURES)[number]); // the library's, number 11

function Where() {
  const location = useLocation();
  return <p data-testid="where">{`${location.pathname} ${JSON.stringify(location.state)}`}</p>;
}

function Shell() {
  const [note, setNote] = useState<OpeningNote | null>(null);
  return (
    <>
      <Opening onNote={setNote} />
      {note && <OpeningNotice note={note} onClose={() => setNote(null)} />}
      <input aria-label="Search the library" />
      <div role="dialog" aria-label="Save" data-testid="card">
        <input type="range" aria-label="Quality" />
      </div>
    </>
  );
}

function renderOpening(answers: Record<string, unknown> = {}, at = "/history") {
  shell.invoke.mockImplementation(async (command: string) => {
    if (command === "engine_status") return READY;
    if (command in answers) {
      const answer = answers[command];
      return typeof answer === "function" ? answer() : answer;
    }
    return [];
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[at]}>
          <Routes>
            <Route path="*" element={<Where />} />
          </Routes>
          <Shell />
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

async function ready() {
  await vi.waitFor(() => expect(shell.dropped).not.toBeNull());
  await vi.waitFor(() => expect(shell.invoke).toHaveBeenCalledWith("engine_status"));
  await act(async () => {}); // the engine's status, ready, reaches the page first
}

async function drop(event: Dropped["payload"]) {
  await ready();
  act(() => shell.dropped?.({ payload: event }));
}

/** Ctrl+V on `target`, with what the clipboard gives a page: a picture file, words, or both. */
async function paste(target: EventTarget, given: { picture?: File; words?: string }) {
  await ready();
  const event = new Event("paste", { bubbles: true, cancelable: true });
  const items = given.picture
    ? [{ kind: "file", type: given.picture.type, getAsFile: () => given.picture }]
    : [];
  Object.defineProperty(event, "clipboardData", {
    value: { items, getData: () => given.words ?? "" },
  });
  act(() => {
    target.dispatchEvent(event);
  });
  return event;
}

/** What the window sent the engine at `path`, each time. */
function sent(fetch: ReturnType<typeof fakeEngine>, path: string) {
  return fetch.mock.calls
    .filter(([input]) => new URL(String(input)).pathname === path)
    .map(([, init]) => init);
}

describe("Opening", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
    shell.heard.clear();
  });

  it("says what dropping does while pictures are over the window", async () => {
    fakeEngine({});
    renderOpening();

    await drop({ type: "enter", paths: ["D:\\Pictures\\Holiday"] });

    expect(await screen.findByText("Drop them here")).toBeInTheDocument();
    expect(
      screen.getByText("One picture opens its page; several, or a folder, open Many at once."),
    ).toBeInTheDocument();
    await drop({ type: "leave" });
    expect(screen.queryByText("Drop them here")).toBeNull();
  });

  it("opens several pictures, or a folder, in Many at once with them chosen", async () => {
    const fetch = fakeEngine({ "POST /open": { picture: null, picked: PICKED, leftOut: [] } });
    renderOpening();

    await drop({ type: "drop", paths: ["D:\\Pictures\\Holiday"] });

    await vi.waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent('/batch {"pick":{"how":"dropped"'),
    );
    expect(JSON.parse(String(sent(fetch, "/open")[0]?.body))).toEqual({
      paths: ["D:\\Pictures\\Holiday"],
      how: "dropped",
    });
  });

  it("opens one picture from the library on its page, and one from outside on its own", async () => {
    fakeEngine({
      "POST /open": (init: RequestInit) =>
        String(init.body).includes("Phone")
          ? { picture: DUSK, picked: null, leftOut: [] }
          : { picture: OUTSIDE, picked: null, leftOut: [] },
    });
    renderOpening();

    await drop({ type: "drop", paths: ["D:\\Pictures\\Phone\\Harbour at dusk.heic"] });
    await vi.waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(`/library/pictures/${DUSK.id}`),
    );
    await drop({ type: "drop", paths: ["E:\\Elsewhere\\Pier at dawn.jpg"] });
    await vi.waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/pictures/42"));
  });

  it("says what was left out beside the one picture that opened", async () => {
    fakeEngine({
      "POST /open": {
        picture: OUTSIDE,
        picked: null,
        leftOut: [{ name: "notes.txt", why: "notes.txt isn't a picture Mado reads." }],
      },
    });
    renderOpening();

    await drop({ type: "drop", paths: ["E:\\Elsewhere\\Pier at dawn.jpg", "E:\\notes.txt"] });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Left out notes.txtnotes.txt isn't a picture Mado reads.",
    );
  });

  it("says why nothing opened, in the engine's words", async () => {
    fakeEngine({
      "POST /open": () =>
        Response.json(
          { detail: "Brochure.pdf isn't a picture Mado reads. It reads JPEG, PNG…" },
          { status: 422 },
        ),
    });
    renderOpening();

    await drop({ type: "drop", paths: ["E:\\Brochure.pdf"] });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nothing openedBrochure.pdf isn't a picture Mado reads.",
    );
  });

  it("says why a folder with no picture in it opened nothing, and stays put", async () => {
    fakeEngine({
      "POST /open": {
        picture: null,
        picked: {
          ...PICKED,
          pictures: [],
          leftOut: [{ name: "notes.txt", why: "It isn't a picture Mado reads." }],
        },
        leftOut: [],
      },
    });
    renderOpening();

    await drop({ type: "drop", paths: ["D:\\Notes"] });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nothing openednotes.txt: It isn't a picture Mado reads.",
    );
    expect(screen.getByTestId("where")).toHaveTextContent("/history");
  });

  it("pastes files copied in File Explorer as if they were dropped", async () => {
    const fetch = fakeEngine({ "POST /open": { picture: OUTSIDE, picked: null, leftOut: [] } });
    renderOpening({ clipboard_files: ["E:\\Elsewhere\\Pier at dawn.jpg"] });

    // A page sees a copied file as a picture too: the shell's list of paths goes first.
    const copied = new File(["made up"], "Pier at dawn.jpg", { type: "image/jpeg" });
    const event = await paste(document.body, { picture: copied });

    await vi.waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/pictures/42"));
    expect(event.defaultPrevented).toBe(true);
    expect(JSON.parse(String(sent(fetch, "/open")[0]?.body))).toEqual({
      paths: ["E:\\Elsewhere\\Pier at dawn.jpg"],
      how: "pasted",
    });
    expect(sent(fetch, "/pasted")).toEqual([]);
  });

  it("keeps a picture on the clipboard in Mado's folder and opens it", async () => {
    const pasted = outsidePicture({ id: 7, name: "Pasted 2026-11-23 14.05.png", pasted: true });
    const fetch = fakeEngine({ "POST /pasted": pasted });
    renderOpening();

    const shot = new File([new Uint8Array([137, 80, 78, 71])], "image.png", { type: "image/png" });
    await paste(document.body, { picture: shot });

    await vi.waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/pictures/7"));
    const asked = sent(fetch, "/pasted")[0];
    expect(asked?.body).toBe(shot);
    expect(new Headers(asked?.headers).get("Content-Type")).toBe("image/png");
  });

  it("says when a picture on the clipboard is too big to paste", async () => {
    fakeEngine({
      "POST /pasted": () =>
        Response.json(
          { detail: "That picture is too big to paste (40,000 × 20,000)." },
          { status: 413 },
        ),
    });
    renderOpening();

    const shot = new File([new Uint8Array([137, 80, 78, 71])], "image.png", { type: "image/png" });
    await paste(document.body, { picture: shot });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nothing pastedThat picture is too big to paste (40,000 × 20,000).",
    );
  });

  it("says a picture is too big to paste when the window was given it empty", async () => {
    // Past 2^26 pixels (256 MiB of them), the window's own clipboard gives a page an empty PNG.
    const fetch = fakeEngine({});
    renderOpening();

    const empty = new File([], "image.png", { type: "image/png" });
    await paste(document.body, { picture: empty });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nothing pastedThat picture is too big to paste: Mado takes pictures up to 67 megapixels from the clipboard.",
    );
    expect(sent(fetch, "/pasted")).toEqual([]);
  });

  it("opens a path copied as words", async () => {
    const fetch = fakeEngine({ "POST /open": { picture: OUTSIDE, picked: null, leftOut: [] } });
    renderOpening();

    await paste(document.body, { words: '"E:\\Elsewhere\\Pier at dawn.jpg"\r\n' });

    await vi.waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/pictures/42"));
    expect(JSON.parse(String(sent(fetch, "/open")[0]?.body)).how).toBe("pasted");
  });

  it("says there's no picture on the clipboard when there isn't", async () => {
    const fetch = fakeEngine({});
    renderOpening();

    await paste(document.body, { words: "A shopping list" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nothing to pasteThere's no picture on the clipboard.",
    );
    expect(sent(fetch, "/open")).toEqual([]);
  });

  it("leaves a paste in a text field to paste words as usual", async () => {
    const fetch = fakeEngine({});
    renderOpening();

    const field = screen.getByRole("textbox", { name: "Search the library" });
    const event = await paste(field, { words: "E:\\Elsewhere\\Pier at dawn.jpg" });

    expect(event.defaultPrevented).toBe(false);
    await act(async () => {});
    expect(shell.invoke).not.toHaveBeenCalledWith("clipboard_files");
    expect(sent(fetch, "/open")).toEqual([]);
  });

  it("leaves a paste in a card alone, as the card is what's in front", async () => {
    const fetch = fakeEngine({});
    renderOpening({ clipboard_files: ["E:ElsewherePier at dawn.jpg"] });

    const quality = screen.getByRole("slider", { name: "Quality" });
    const event = await paste(quality, { words: "" });

    expect(event.defaultPrevented).toBe(false);
    await act(async () => {});
    expect(shell.invoke).not.toHaveBeenCalledWith("clipboard_files");
    expect(sent(fetch, "/open")).toEqual([]);
  });

  it("opens what Windows handed over once the engine is ready, and more as it comes", async () => {
    const choices = [[["E:\\Elsewhere\\Pier at dawn.jpg"]], [["D:\\Pictures\\Holiday"]]];
    const fetch = fakeEngine({
      "POST /open": (init: RequestInit) =>
        String(init.body).includes("Holiday")
          ? { picture: null, picked: PICKED, leftOut: [] }
          : { picture: OUTSIDE, picked: null, leftOut: [] },
    });
    renderOpening({ take_opened: () => choices.shift() ?? [] }, "/");

    await vi.waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/pictures/42"));
    expect(JSON.parse(String(sent(fetch, "/open")[0]?.body)).how).toBe("opened");
    act(() => shell.heard.get("opened")?.());
    await vi.waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent('/batch {"pick":{"how":"opened"'),
    );
  });
});

describe("pathsIn", () => {
  it("takes File Explorer's Copy as path, one or many", () => {
    expect(pathsIn('"D:\\Trip\\Pier.jpg"')).toEqual(["D:\\Trip\\Pier.jpg"]);
    expect(pathsIn('"D:\\Trip\\Pier.jpg"\r\n"\\\\nas\\photos\\Lake.heic"\r\n')).toEqual([
      "D:\\Trip\\Pier.jpg",
      "\\\\nas\\photos\\Lake.heic",
    ]);
  });

  it("takes a file address as its path", () => {
    expect(pathsIn("file:///D:/Fotos%20del%20viaje/%C5%8Csaka.jpg")).toEqual([
      "D:\\Fotos del viaje\\Ōsaka.jpg",
    ]);
    expect(pathsIn("file://nas/photos/Lake.heic")).toEqual(["\\\\nas\\photos\\Lake.heic"]);
  });

  it("takes nothing from words that aren't paths", () => {
    expect(pathsIn("A shopping list")).toEqual([]);
    expect(pathsIn("D:\\Trip\\Pier.jpg\nand a note")).toEqual([]);
    expect(pathsIn("")).toEqual([]);
  });
});
