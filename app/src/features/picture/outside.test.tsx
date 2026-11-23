import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type PictureDetails } from "@/lib/engine";
import { fakeEngine, outsidePicture, PC, READY, SETTINGS, SIZES } from "@/test/engine";
import { PicturePage } from "./picture-page";
import { SaveDialog } from "./save-dialog";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function Address() {
  const location = useLocation();
  return <p data-testid="address">{location.pathname}</p>;
}

function wrap(children: React.ReactNode, at: string) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[at]}>
          {children}
          <Address />
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function renderPage(at = "/pictures/42") {
  return wrap(
    <Routes>
      <Route path="/pictures/:id" element={<PicturePage />} />
      <Route path="/library/pictures/:id" element={<PicturePage />} />
      <Route path="/history" element={<p>History</p>} />
      <Route path="/" element={<p>Home</p>} />
    </Routes>,
    at,
  );
}

const blob = () => new Response(new Blob(["made-up picture"], { type: "image/webp" }));

/** A plan for the Size tab, as the engine words it. */
const PLAN = {
  width: 7680,
  height: 4320,
  label: "TV 8K",
  shape: "crop",
  sides: "none",
  kept: { x: 0, y: 0, width: 1, height: 1 },
  canvas: { x: 0, y: 0, width: 1, height: 1 },
  focus: [0.5, 0.5],
  focusFound: true,
  note: "",
  kind: "photo",
  kindGuessed: true,
  quality: "fast",
  method: "ai",
  model: null,
  how: "",
  warning: null,
  cleanMatters: false,
  look: null,
  edit: null,
  seconds: 1,
  place: "card",
  measured: false,
  format: "PNG",
  formatQuality: null,
  fits: true,
  colour: "sRGB",
  bytes: 9_000_000,
  needs: [],
  nothingBehind: false,
  seeThrough: false,
};

function engine(picture: PictureDetails, answers: Record<string, unknown> = {}) {
  return fakeEngine({
    [`/pictures/${picture.id}`]: picture,
    [`/pictures/${picture.id}/neighbours`]: { before: [], after: [] },
    [`/pictures/${picture.id}/view`]: blob,
    [`/pictures/${picture.id}/thumbnail`]: blob,
    "/folders": [],
    "/sizes": SIZES,
    "/pc": PC,
    ...answers,
  });
}

function sent(fetch: ReturnType<typeof fakeEngine>, path: string) {
  return fetch.mock.calls
    .filter(([input, init]) => new URL(String(input)).pathname === path && init?.method === "POST")
    .map(([, init]) => init);
}

describe("A picture from outside the library", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:made-up");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows where it lives in place of the breadcrumb, and has no neighbours", async () => {
    engine(outsidePicture());
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Pier at dawn", level: 1 }),
    ).toBeInTheDocument();
    const folder = await screen.findByRole("button", {
      name: "Show Pier at dawn.jpg in its folder, Elsewhere",
    });
    expect(folder).toHaveTextContent("Elsewhere");
    expect(screen.getByRole("button", { name: "Add its folder to the library" })).toBeEnabled();
    expect(screen.queryByRole("link", { name: "Library" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Previous picture" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: /Pictures in/ })).toBeNull();
    // Its folder is shown from the header: the line under the picture only copies its path.
    expect(screen.queryByRole("button", { name: "Show in folder" })).toBeNull();
    expect(screen.getByRole("button", { name: "Copy path" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Tools" })).toBeInTheDocument();

    fireEvent.click(folder);
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("show_in_folder", {
        path: "E:\\Elsewhere\\Pier at dawn.jpg",
      }),
    );
  });

  it("adds its folder to the library on asking", async () => {
    const fetch = engine(outsidePicture(), {
      "POST /folders": { id: 4, path: "E:\\Elsewhere", name: "Elsewhere" },
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Add its folder to the library" }));

    expect(
      await screen.findByRole("button", { name: "Mado is reading Elsewhere…" }),
    ).toBeDisabled();
    expect(JSON.parse(String(sent(fetch, "/folders")[0]?.body))).toEqual({
      path: "E:\\Elsewhere",
    });
  });

  it("says why its folder can't be added, in the engine's words", async () => {
    engine(outsidePicture(), {
      "POST /folders": () =>
        Response.json(
          { detail: "E:\\Elsewhere is already in your library, as part of E:\\." },
          { status: 400 },
        ),
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Add its folder to the library" }));

    expect(
      await screen.findByText("E:\\Elsewhere is already in your library, as part of E:\\."),
    ).toHaveAttribute("role", "alert");
  });

  it("is pasted: kept in Mado till it's saved, with no folder of yours", async () => {
    engine(
      outsidePicture({
        id: 7,
        name: "Pasted 2026-11-23 14.05.png",
        path: "C:\\Users\\owner\\AppData\\Local\\Mado\\pasted\\Pasted 2026-11-23 14.05.png",
        folder: "C:\\Users\\owner\\AppData\\Local\\Mado\\pasted",
        format: "PNG",
        pasted: true,
        savesTo: "C:\\Users\\owner\\Pictures",
      }),
    );
    renderPage("/pictures/7");

    expect(
      await screen.findByRole("heading", { name: "Pasted 2026-11-23 14.05", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Pasted · not saved yet")).toBeInTheDocument();
    expect(screen.getByText("Kept in Mado till you save it")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add its folder to the library" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy path" })).toBeNull();
    expect(screen.queryByText(/AppData/)).toBeNull();
  });

  it("waits in a quarantine: opened to look at only", async () => {
    engine(
      outsidePicture({
        path: "E:\\Mado quarantine\\2026-11-22\\Pier at dawn.jpg",
        folder: "E:\\Mado quarantine\\2026-11-22",
        aside: true,
      }),
    );
    renderPage();

    const tools = await screen.findByRole("complementary", { name: "Tools" });
    expect(within(tools).getByRole("heading", { name: "Opened to look at only" })).toBeVisible();
    expect(within(tools).queryByRole("tab", { name: "Size" })).toBeNull();
    expect(within(tools).getByRole("link", { name: "Open History" })).toHaveAttribute(
      "href",
      "/history",
    );
    expect(screen.getByRole("button", { name: /in its folder, Mado quarantine/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add its folder to the library" })).toBeNull();
  });

  it("says when it isn't there any more, in the engine's words, with the way back Home", async () => {
    engine(outsidePicture(), {
      "/pictures/42": () =>
        Response.json(
          {
            detail:
              "Pier at dawn.jpg is on E:, which isn't connected. Connect it, then open it again.",
          },
          { status: 404 },
        ),
    });
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "This picture isn't there any more" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Pier at dawn.jpg is on E:, which isn't connected. Connect it, then open it again.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Home" })).toHaveAttribute("href", "/");
  });

  it("shows itself anew once the Save that made it is done", async () => {
    let asked = 0;
    const job = {
      id: 3,
      pictureId: 42,
      name: "Pier at dawn.jpg",
      how: "replace",
      stage: "saving",
      progress: 0.9,
      secondsLeft: 1,
      queuedAt: "2026-11-23T09:00:00+02:00",
      result: null,
      resultName: null,
      resultPicture: null,
      problem: null,
      madeFor: "TV 8K",
      look: null,
      edit: null,
    };
    const fetch = engine(outsidePicture(), {
      "/jobs": () => {
        asked += 1;
        return [asked === 1 ? { ...job, state: "running" } : { ...job, state: "done" }];
      },
    });
    renderPage();

    await screen.findByRole("heading", { name: "Pier at dawn", level: 1 });
    await waitFor(
      () =>
        expect(
          fetch.mock.calls.filter(([input]) => new URL(String(input)).pathname === "/pictures/42"),
        ).toHaveLength(2),
      { timeout: 4000 },
    );
  });

  it("is pasted and saved as it is, with nothing chosen", async () => {
    const pasted = outsidePicture({
      id: 7,
      name: "Pasted 2026-11-23 14.05.png",
      format: "PNG",
      pasted: true,
      savesTo: "C:\\Users\\owner\\Pictures",
    });
    const fetch = engine(pasted, {
      "/settings": SETTINGS,
      "POST /pictures/7/plan": { ...PLAN, width: 4032, height: 3024, label: "", method: "keep" },
      "POST /pictures/7/saving": {
        name: "Pasted 2026-11-23 14.05.png",
        folder: "C:\\Users\\owner\\Pictures",
        taken: null,
        takenAt: null,
        bytes: 9_000_000,
        colour: "sRGB",
      },
    });
    renderPage("/pictures/7");

    const save = await screen.findByRole("button", { name: "Save…" });
    await waitFor(() => expect(save).toBeEnabled());
    expect(screen.getByText(/Save keeps it as it is/)).toBeInTheDocument();
    const plan = fetch.mock.calls.find(
      ([input]) => new URL(String(input)).pathname === "/pictures/7/plan",
    );
    expect(JSON.parse(String(plan?.[1]?.body))).toEqual({ edit: null, size: null, look: null });
    fireEvent.click(save);
    expect(await screen.findByText(/As it is,/)).toHaveTextContent("As it is, 4032 × 3024");
    expect(await screen.findByRole("radio", { name: /As a new picture/ })).toBeVisible();
    expect(screen.queryByRole("radio", { name: /Replace the original/ })).toBeNull();
  });

  it("can't be marked as damaged when it won't open, as it isn't the library's", async () => {
    engine(outsidePicture({ state: "broken", problem: "The file is damaged." }));
    renderPage();

    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as damaged" })).toBeNull();
  });
});

describe("Saving a pasted picture", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  const PASTED = outsidePicture({
    id: 7,
    name: "Pasted 2026-11-23 14.05.png",
    format: "PNG",
    pasted: true,
    savesTo: "C:\\Users\\owner\\Pictures",
  });
  const recipe = { edit: null, size: null, look: null };

  function renderSave(settings = SETTINGS) {
    const fetch = fakeEngine({
      "/settings": settings,
      "POST /pictures/7/saving": {
        name: "Pasted 2026-11-23 14.05 (TV 8K).png",
        folder: "C:\\Users\\owner\\Pictures",
        taken: null,
        takenAt: null,
        bytes: 9_000_000,
        colour: "sRGB",
      },
      "POST /pictures/7/make": { id: 3, state: "queued" },
    });
    wrap(
      <SaveDialog
        picture={PASTED}
        plan={PLAN as never}
        recipe={recipe as never}
        onClose={() => {}}
      />,
      "/pictures/7",
    );
    return fetch;
  }

  it("saves only as a new picture, into Pictures first", async () => {
    const fetch = renderSave();

    expect(
      await screen.findByText(/In Pictures: till you save it, it's only in Mado/),
    ).toBeVisible();
    expect(screen.queryByRole("radio", { name: /Replace the original/ })).toBeNull();
    expect(screen.queryByLabelText("Always save this way")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetch, "/pictures/7/make")).toHaveLength(1));
    const saving = JSON.parse(String(sent(fetch, "/pictures/7/make")[0]?.body)).saving;
    expect([saving.how, saving.folder]).toEqual(["new", "C:\\Users\\owner\\Pictures"]);
  });

  it("goes to the owner's own folder for new pictures, when they chose one", async () => {
    const fetch = renderSave({ ...SETTINGS, newPictures: "folder", newFolder: "D:\\Edited" });

    expect(await screen.findByText(/In Edited: till you save it/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetch, "/pictures/7/make")).toHaveLength(1));
    expect(JSON.parse(String(sent(fetch, "/pictures/7/make")[0]?.body)).saving.folder).toBe(
      "D:\\Edited",
    );
  });
});
