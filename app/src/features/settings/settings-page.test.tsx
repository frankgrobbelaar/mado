import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type Backup, type DataSizes, EngineProvider, type Health } from "@/lib/engine";
import type { ReadyUpdate } from "@/lib/updates";
import { fakeEngine, PC, READY, SETTINGS } from "@/test/engine";
import { SettingsPage } from "./settings-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const HEALTH: Health = {
  status: "ok",
  version: "0.1.0",
  dataDir: "C:\\Users\\Someone\\AppData\\Local\\Mado",
  schemaVersion: 1,
};

const DATA: DataSizes = {
  folder: "C:\\Users\\Someone\\AppData\\Local\\Mado",
  database: 48_000_000,
  cache: 20_000_000,
  logs: 12_000_000,
  backups: 0,
  tools: 180_000_000,
  pasted: 0,
};

/** A local time `daysAgo` days back, as the engine writes a backup's: "2026-11-22T03:00". */
function stamp(daysAgo: number, time: string): string {
  const day = new Date();
  day.setDate(day.getDate() - daysAgo);
  const date = [day.getFullYear(), day.getMonth() + 1, day.getDate()]
    .map((part) => String(part).padStart(2, "0"))
    .join("-");
  return `${date}T${time}`;
}

function backup(made: string): Backup {
  const [date, time] = made.split("T");
  const name = `mado ${date} ${time?.replace(":", "")}.db`;
  return { name, made, size: 47_000_000, beforeRestoring: false, fromExport: false, byHand: false };
}

const TONIGHT = backup(stamp(0, "03:00"));
const LAST_NIGHT = backup(stamp(1, "03:00"));

function renderSettings(section = "general", shellAnswers = true) {
  if (shellAnswers) {
    shell.invoke.mockImplementation(
      async (command: string, args?: { on?: boolean; look?: string }) => {
        if (command === "engine_status") return READY;
        if (command === "pick_folder") return "D:\\Backups";
        if (command === "start_with_windows") return false;
        if (command === "set_start_with_windows") return args?.on;
        if (command === "keep_in_tray") return false;
        if (command === "set_keep_in_tray") return args?.on;
        if (command === "open_in_explorer") return true;
        if (command === "set_open_in_explorer") return args?.on;
        if (command === "look") return "windows";
        if (command === "set_look") return args?.look;
        return undefined;
      },
    );
  }
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[`/settings/${section}`]}>
          <Routes>
            <Route path="/settings/:section" element={<SettingsPage />} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

/** The shell's answers when Mado checks for updates, in turn (the last one repeats): an update,
 * none (null), or why it couldn't check (a string, as the shell's errors are). */
function answerUpdates(answers: (ReadyUpdate | null | string)[]) {
  shell.invoke.mockImplementation((command: string) => {
    if (command === "engine_status") return Promise.resolve(READY);
    if (command !== "prepare_update") return Promise.resolve(undefined);
    const answer = answers.length > 1 ? answers.shift() : answers[0];
    return typeof answer === "string" ? Promise.reject(answer) : Promise.resolve(answer);
  });
}

function checks() {
  return shell.invoke.mock.calls.filter(([command]) => command === "prepare_update").length;
}

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) =>
      (init?.method ?? "GET") === method && new URL(String(input)).pathname === path,
  );
}

function body(fetch: ReturnType<typeof fakeEngine>, method: string, path: string): unknown {
  const [[, init]] = sent(fetch, method, path) as [[unknown, RequestInit]];
  return JSON.parse(String(init.body));
}

describe("SettingsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    shell.invoke.mockReset();
  });

  it("starts Mado with Windows, waiting in the tray, when asked", async () => {
    fakeEngine({});
    renderSettings("general");

    const start = await screen.findByRole("switch", { name: "Start Mado when Windows starts" });
    await waitFor(() => expect(start).toHaveAttribute("aria-checked", "false"));
    start.click();

    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("set_start_with_windows", { on: true }),
    );
    await waitFor(() => expect(start).toHaveAttribute("aria-checked", "true"));
  });

  it("keeps Mado running in the tray when its window closes, when asked", async () => {
    fakeEngine({});
    renderSettings("general");

    const keep = await screen.findByRole("switch", {
      name: "Keep Mado running when you close the window",
    });
    await waitFor(() => expect(keep).toHaveAttribute("aria-checked", "false"));
    keep.click();

    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("set_keep_in_tray", { on: true }),
    );
    await waitFor(() => expect(keep).toHaveAttribute("aria-checked", "true"));
    expect(shell.invoke).not.toHaveBeenCalledWith("set_start_with_windows", expect.anything());
  });

  it("offers Open in Mado in File Explorer, on till it's turned off", async () => {
    fakeEngine({});
    renderSettings("general");

    const explorer = await screen.findByRole("switch", { name: "Open in Mado in File Explorer" });
    await waitFor(() => expect(explorer).toHaveAttribute("aria-checked", "true"));
    expect(screen.getByText(/under Show more options/)).toBeInTheDocument();
    explorer.click();

    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("set_open_in_explorer", { on: false }),
    );
    await waitFor(() => expect(explorer).toHaveAttribute("aria-checked", "false"));
  });

  it("is light or dark as Windows is, or as the owner picks", async () => {
    fakeEngine({});
    renderSettings("general");

    const looks = await screen.findByRole("radiogroup", { name: "Light or dark" });
    const radio = (name: string) => within(looks).getByRole("radio", { name });
    await waitFor(() => expect(radio("Same as Windows")).toHaveAttribute("aria-checked", "true"));
    radio("Light").click();

    await waitFor(() => expect(shell.invoke).toHaveBeenCalledWith("set_look", { look: "light" }));
    await waitFor(() => expect(radio("Light")).toHaveAttribute("aria-checked", "true"));
    expect(radio("Same as Windows")).toHaveAttribute("aria-checked", "false");
  });

  it("shows where the data lives and how big each part is", async () => {
    fakeEngine({ "/data": DATA, "/backups": { backups: [], restored: null } });
    renderSettings("data");

    expect(await screen.findByText(DATA.folder)).toBeInTheDocument();
    expect(screen.getByText("48 MB")).toBeInTheDocument();
    expect(screen.getByText("mado.db, one SQLite file")).toBeInTheDocument();
    expect(screen.getByText(/Your pictures are never touched/)).toBeInTheDocument();
    expect(screen.queryByText("Pasted")).toBeNull(); // nothing pasted: not a part yet
  });

  it("shows what's pasted as a part of the data folder once there is some", async () => {
    fakeEngine({
      "/data": { ...DATA, pasted: 24_000_000 },
      "/backups": { backups: [], restored: null },
    });
    renderSettings("data");

    expect(await screen.findByText("Pasted")).toBeInTheDocument();
    expect(screen.getByText("24 MB")).toBeInTheDocument();
    expect(screen.getByText("a month after last opened")).toBeInTheDocument();
  });

  it("opens the data folder in Explorer", async () => {
    fakeEngine({ "/data": DATA, "/backups": { backups: [], restored: null } });
    renderSettings("data");

    (await screen.findByRole("button", { name: "Open folder" })).click();

    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("open_folder", { path: DATA.folder }),
    );
  });

  it("exports everything to a folder the owner picks", async () => {
    const fetch = fakeEngine({
      "/data": DATA,
      "/backups": { backups: [], restored: null },
      "POST /export": { path: "D:\\Backups\\Mado export 2026-11-22.zip", size: 912_000_000 },
    });
    renderSettings("data");

    (await screen.findByRole("button", { name: "Export everything" })).click();

    expect(
      await screen.findByText("D:\\Backups\\Mado export 2026-11-22.zip · 912 MB"),
    ).toBeInTheDocument();
    expect(body(fetch, "POST", "/export")).toEqual({ folder: "D:\\Backups" });
  });

  it("imports an export once asked, as the engine starts again", async () => {
    shell.invoke.mockImplementation(async (command: string) => {
      if (command === "engine_status") return READY;
      if (command === "pick_export") return "D:\\Backups\\Mado export 2026-11-21.zip";
      return undefined;
    });
    const fetch = fakeEngine({
      "/data": DATA,
      "/backups": { backups: [], restored: null },
      "POST /backups/import": null,
    });
    renderSettings("data", false);

    (await screen.findByRole("button", { name: "Import an export" })).click();
    const asking = await screen.findByRole("group", { name: "Import Mado export 2026-11-21.zip?" });
    within(asking).getByRole("button", { name: "Import it" }).click();

    await waitFor(() => expect(shell.invoke).toHaveBeenCalledWith("restart_engine"));
    expect(body(fetch, "POST", "/backups/import")).toEqual({
      path: "D:\\Backups\\Mado export 2026-11-21.zip",
    });
  });

  it("shows last night's backup, and makes one now", async () => {
    const fetch = fakeEngine({
      "/data": DATA,
      "/backups": { backups: [TONIGHT, LAST_NIGHT], restored: null },
      "POST /backups": backup(stamp(0, "14:12")),
    });
    renderSettings("data");

    expect(await screen.findByText("Last backup today 03:00")).toBeInTheDocument();
    expect(screen.getByText("47 MB · checked")).toBeInTheDocument();
    screen.getByRole("button", { name: "Back up now" }).click();

    await waitFor(() => expect(sent(fetch, "POST", "/backups")).toHaveLength(1));
  });

  it("says when no backup has been made yet", async () => {
    fakeEngine({ "/data": DATA, "/backups": { backups: [], restored: null } });
    renderSettings("data");

    expect(await screen.findByText("No backup yet")).toBeInTheDocument();
    expect(screen.getByText("The first is made tonight at 03:00.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restore a backup" })).toBeDisabled();
  });

  it("restores the backup the owner picks, as the engine starts again", async () => {
    const restore = `/backups/${encodeURIComponent(LAST_NIGHT.name)}/restore`;
    const fetch = fakeEngine({
      "/data": DATA,
      "/backups": { backups: [TONIGHT, LAST_NIGHT], restored: null },
      [`POST ${restore}`]: null,
    });
    renderSettings("data");

    await screen.findByText("Last backup today 03:00");
    screen.getByRole("button", { name: "Restore a backup" }).click();
    (await screen.findByRole("radio", { name: /Yesterday 03:00/ })).click();
    const go = screen.getByRole("button", { name: "Restore it" });
    await waitFor(() => expect(go).toBeEnabled());
    go.click();

    await waitFor(() => expect(sent(fetch, "POST", restore)).toHaveLength(1));
    await waitFor(() => expect(shell.invoke).toHaveBeenCalledWith("restart_engine"));
    expect(
      await screen.findByText(/^Mado is starting again to restore the backup from yesterday/),
    ).toBeInTheDocument();
  });

  it("says what kind each backup is", async () => {
    const byHand = { ...backup(stamp(0, "14:12")), byHand: true };
    const imported = `mado ${stamp(0, "14:20").replace("T", " ").replace(":", "")} from an export (2).db`;
    fakeEngine({
      "/data": DATA,
      "/backups": {
        backups: [byHand, TONIGHT],
        restored: { name: imported, at: new Date().toISOString(), problem: null },
      },
    });
    renderSettings("data");

    expect(await screen.findByText("Imported the export.")).toBeInTheDocument();
    screen.getByRole("button", { name: "Restore a backup" }).click();
    expect(
      await screen.findByRole("radio", { name: "Today 14:12 · by hand, 47 MB" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Today 03:00, 47 MB" })).toBeInTheDocument();
  });

  it("says how today's restore went", async () => {
    fakeEngine({
      "/data": DATA,
      "/backups": {
        backups: [TONIGHT, LAST_NIGHT],
        restored: { name: LAST_NIGHT.name, at: new Date().toISOString(), problem: null },
      },
    });
    renderSettings("data");

    expect(
      await screen.findByText("Restored the backup from yesterday 03:00."),
    ).toBeInTheDocument();
  });

  it("says what this copy of Mado is up to", async () => {
    fakeEngine({ "/health": HEALTH });
    renderSettings("about");

    expect(await screen.findByText("0.1.0")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText(HEALTH.dataDir)).toBeInTheDocument();
    expect(screen.getByText("Ready · schema version 1")).toBeInTheDocument();
    expect(screen.getByText("Checked in installed copies of Mado")).toBeInTheDocument();
    expect(
      screen.getByText("MIT. Anyone may fork it; the repo takes no contributions."),
    ).toBeInTheDocument();
  });

  it("says Mado keeps to this PC, and never fetches pictures", async () => {
    fakeEngine({ "/health": HEALTH });
    renderSettings("about");

    expect(await screen.findByText(/looks after pictures already on this PC/)).toHaveTextContent(
      "it never searches for or downloads pictures",
    );
  });

  it("says when the engine isn't running", async () => {
    shell.invoke.mockImplementation(async (command: string) =>
      command === "engine_status"
        ? { state: "failed", message: "It stopped unexpectedly.", details: "" }
        : undefined,
    );
    fakeEngine({});
    renderSettings("about", false);

    expect(await screen.findByText("Not running")).toBeInTheDocument();
  });

  it("opens the downloads page to show every version and what changed", async () => {
    fakeEngine({ "/health": HEALTH });
    renderSettings("about");

    (await screen.findByRole("button", { name: "Every version and what changed" })).click();

    expect(shell.invoke).toHaveBeenCalledWith("open_downloads_page");
  });

  it("checks for a new version when asked, and installs the one it finds", async () => {
    vi.stubEnv("PROD", true); // only installed copies check for updates
    answerUpdates([null, { version: "0.3.0", notes: "- Check for a new version." }]);
    fakeEngine({ "/health": HEALTH });
    renderSettings("updates", false);

    expect(
      await screen.findByText(/^Up to date · last checked today \d\d:\d\d$/),
    ).toBeInTheDocument();
    expect(await screen.findByText("0.1.0")).toBeInTheDocument();
    screen.getByRole("button", { name: "Check for a new version" }).click();

    expect(await screen.findByText("Mado 0.3.0 is ready to install")).toBeInTheDocument();
    expect(checks()).toBe(2);
    expect(screen.queryByRole("button", { name: "Check for a new version" })).toBeNull();
    screen.getByRole("button", { name: "Restart and update" }).click();

    await waitFor(() => expect(shell.invoke).toHaveBeenCalledWith("install_update"));
  });

  it("says why it couldn't check, and checks again when asked", async () => {
    vi.stubEnv("PROD", true);
    answerUpdates(["error sending request", null]);
    fakeEngine({ "/health": HEALTH });
    renderSettings("updates", false);

    expect(
      await screen.findByText("Can't check right now: error sending request"),
    ).toBeInTheDocument();
    screen.getByRole("button", { name: "Check for a new version" }).click();

    expect(await screen.findByText(/^Up to date · last checked today/)).toBeInTheDocument();
  });

  it("leaves checking for updates to installed copies", async () => {
    fakeEngine({ "/health": HEALTH });
    renderSettings("updates");

    expect(await screen.findByText("Checked in installed copies of Mado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check for a new version" })).toBeNull();
    expect(checks()).toBe(0);
  });

  it("takes an unknown section to the first", async () => {
    fakeEngine({});
    renderSettings("nowhere");

    expect(
      await screen.findByRole("switch", { name: "Start Mado when Windows starts" }),
    ).toBeInTheDocument();
  });
});

describe("Settings: saving, this PC, downloads and what's set aside", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("keeps what Save offers first, where new pictures go and whether they keep the place", async () => {
    let saved = { ...SETTINGS };
    const fetch = fakeEngine({
      "/health": HEALTH,
      "/settings": () => saved,
      "PUT /settings": (init?: RequestInit) => {
        saved = JSON.parse(String(init?.body));
        return saved;
      },
    });
    renderSettings("general");

    const saving = await screen.findByRole("region", { name: "Saving" });
    await waitFor(() =>
      expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/settings"))).toBe(true),
    );
    await new Promise((settle) => setTimeout(settle, 0));
    fireEvent.click(within(saving).getByRole("radio", { name: "Replace the original" }));
    await waitFor(() => expect(saved.saveFirst).toBe("replace"));
    fireEvent.click(within(saving).getByRole("radio", { name: "In a folder…" }));
    await waitFor(() => expect(saved.newFolder).toBe("D:\\Backups"));
    expect(saved.newPictures).toBe("folder");
    fireEvent.click(within(saving).getByRole("switch", { name: "Keep where a picture was taken" }));
    await waitFor(() => expect(saved.keepLocation).toBe(true));
    expect(fetch).toHaveBeenCalled();
  });

  it("says what this PC can do, which way each kind starts, and tests it again", async () => {
    const fetch = fakeEngine({
      "/health": HEALTH,
      "/pc": PC,
      "POST /pc/test": { ...PC, testing: true, timing: true },
      "/tools": [],
    });
    renderSettings("about");

    const panel = await screen.findByRole("region", { name: "This PC" });
    expect(await within(panel).findByText(/NVIDIA GeForce GTX 1660 SUPER/)).toBeInTheDocument();
    expect(within(panel).getByText(/6 GB of its own/)).toBeInTheDocument();
    expect(within(panel).getByText(/The AI models run on the graphics card/)).toBeInTheDocument();
    const photos = within(panel).getByRole("row", { name: /Photos/ });
    expect(within(photos).getByText("about 1 min")).toBeInTheDocument();
    expect(within(photos).getByText("starts on")).toBeInTheDocument();
    expect(within(photos).getByText("RealESRGAN x4plus, a download")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Test again" }));
    await waitFor(() =>
      expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/pc/test"))).toBe(true),
    );
  });

  it("fetches a tool again when it's gone missing", async () => {
    const fetch = fakeEngine({
      "/health": HEALTH,
      "/pc": PC,
      "/tools": [
        {
          id: "ffmpeg",
          name: "ffmpeg",
          version: "9.0.2",
          purpose: "Reads HEIC.",
          licence: "LGPL-2.1-or-later",
          size: 76_972_461,
          when: "setup",
          state: "missing",
          done: 0,
          problem: null,
        },
      ],
      "POST /tools/ffmpeg/download": {},
    });
    renderSettings("about");

    const tools = await screen.findByRole("region", { name: "What Mado downloads" });
    expect(await within(tools).findByText(/missing: Mado needs it again/)).toBeInTheDocument();
    fireEvent.click(within(tools).getByRole("button", { name: "Download it again" }));
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([input]) => String(input).endsWith("/tools/ffmpeg/download")),
      ).toBe(true),
    );
  });

  it("empties a drive's quarantine only after asking once more", async () => {
    const fetch = fakeEngine({
      "/health": HEALTH,
      "/data": DATA,
      "/backups": { backups: [], restored: null },
      "/quarantine": [{ drive: "D:", folder: "D:\\Mado quarantine", bytes: 1_900_000_000 }],
      "POST /quarantine/empty": { bytes: 1_900_000_000 },
    });
    renderSettings("data");

    const panel = await screen.findByRole("region", { name: "Set aside" });
    expect(await within(panel).findByText("D:\\Mado quarantine")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Empty now…" }));
    const dialog = await screen.findByRole("dialog", { name: "Empty D:'s quarantine?" });
    expect(within(dialog).getByText(/deletes 1.9 GB for good/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Empty it for good" }));
    await waitFor(() => {
      const emptied = fetch.mock.calls.find(([input]) =>
        String(input).endsWith("/quarantine/empty"),
      );
      expect(JSON.parse(String(emptied?.[1]?.body))).toEqual({ drive: "D:" });
    });
  });
});
