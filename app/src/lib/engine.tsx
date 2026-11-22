import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  createContext,
  type ReactNode,
  use,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

/** The engine as Mado's shell reports it. Mirrors `EngineStatus` in src-tauri/src/engine.rs. */
export type EngineStatus =
  | { state: "starting" }
  | { state: "ready"; url: string; token: string }
  | { state: "failed"; message: string; details: string };

export type ReadyEngine = Extract<EngineStatus, { state: "ready" }>;

const EngineContext = createContext<EngineStatus>({ state: "starting" });

/** Follows the engine's status: asks the shell once, then listens for changes. */
export function EngineProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<EngineStatus>({ state: "starting" });

  useEffect(() => {
    let heardEvent = false;
    const stopListening = listen<EngineStatus>("engine-status", (event) => {
      heardEvent = true;
      setStatus(event.payload);
    });
    invoke<EngineStatus>("engine_status").then((current) => {
      if (!heardEvent) setStatus(current); // an event is always newer than this answer
    });
    return () => {
      stopListening.then((unlisten) => unlisten());
    };
  }, []);

  return <EngineContext value={status}>{children}</EngineContext>;
}

export function useEngine(): EngineStatus {
  return use(EngineContext);
}

/** Asks the shell to start the engine again, after it failed. */
export function restartEngine(): Promise<void> {
  return invoke("restart_engine");
}

export class EngineError extends Error {}

/** Calls the engine's HTTP API with this launch's token. */
export async function callEngine<T>(
  engine: ReadyEngine,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${engine.token}`);
  let response: Response;
  try {
    response = await fetch(new URL(path, engine.url), { ...init, headers });
  } catch {
    throw new EngineError("Mado's engine didn't answer.");
  }
  if (!response.ok) {
    throw new EngineError(
      (await problemIn(response)) ??
        `The engine answered ${response.status} to ${init?.method ?? "GET"} ${path}.`,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** The sentence the engine sends with a refusal (FastAPI's `detail`), if it sent one. */
async function problemIn(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // not JSON: fall back to the status
  }
  return null;
}

function engineKey(engine: EngineStatus, path: string) {
  return ["engine", engine.state === "ready" ? engine.url : null, path];
}

/**
 * A query for one engine endpoint. It waits until the engine is ready (and `enabled`). `poll`
 * asks again every that many milliseconds while it returns a number for the latest answer (a
 * download in progress).
 */
export function useEngineQuery<T>(
  path: string,
  poll?: (data: T | undefined) => number | false,
  enabled = true,
) {
  const engine = useEngine();
  return useQuery({
    queryKey: engineKey(engine, path),
    queryFn: () => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      return callEngine<T>(engine, path);
    },
    enabled: engine.state === "ready" && enabled,
    refetchInterval: poll ? (query) => poll(query.state.data) : false,
  });
}

/**
 * Asks the engine again for what these paths' queries show, so screens catch up with a change.
 * A path covers everything under it: "/backups" also refreshes "/backups?all" and "/backups/3".
 */
function useRefresh() {
  const engine = useEngine();
  const queries = useQueryClient();
  return useCallback(
    (paths: string[]) => {
      const url = engine.state === "ready" ? engine.url : null;
      return queries.invalidateQueries({
        predicate: ({ queryKey: [scope, address, asked] }) =>
          scope === "engine" &&
          address === url &&
          typeof asked === "string" &&
          paths.some(
            (path) =>
              asked === path || asked.startsWith(`${path}?`) || asked.startsWith(`${path}/`),
          ),
      });
    },
    [engine, queries],
  );
}

/**
 * A change sent to the engine: `send(path, body?)` posts it, then refreshes the queries for
 * `refreshes` so the screen shows the result.
 */
export function useEngineAction<T>(
  refreshes: string[],
  method: "POST" | "PUT" | "DELETE" = "POST",
) {
  const engine = useEngine();
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      const init: RequestInit = { method };
      if (body !== undefined) {
        init.body = JSON.stringify(body);
        init.headers = { "Content-Type": "application/json" };
      }
      return callEngine<T>(engine, path, init);
    },
    onSettled: () => refresh(refreshes),
  });
}

/** What the engine changes by itself: a nightly backup made, a download finished, a scan. */
const CHANGED_ON_ITS_OWN = ["/backups", "/data", "/tools", "/library", "/folders", "/pictures"];

/** Asks again for what the engine may have changed by itself, once it tells of something. */
export function useEngineChanged(): () => void {
  const refresh = useRefresh();
  return useCallback(() => void refresh(CHANGED_ON_ITS_OWN), [refresh]);
}

// The engine's API. These types mirror engine/openapi.json: change both together.

export interface Health {
  status: "ok";
  version: string;
  dataDir: string;
  schemaVersion: number;
}

export const useHealth = () => useEngineQuery<Health>("/health");

/** Mado's records are damaged (mado.db won't open): what's wrong, and the newest backup that opens. */
export interface Damage {
  /** In SQLite's words: "file is not a database". */
  problem: string;
  /** The disk couldn't read them (a drive away a moment): trying again may be all it needs. */
  badRead: boolean;
  /** The backup's name ("mado 2026-11-22 0300.db"), or null when none opens. */
  backup: string | null;
  /** When it was made, local time. */
  made: string | null;
}

/** Whether Mado's records are damaged; null while they're fine. */
export const useRecords = () => useEngineQuery<Damage | null>("/records");
/**
 * The way back from damaged records: `/records/restore` (the newest backup that opens) or
 * `/records/new`. The app starts the engine again right after (`restartEngine`).
 */
export const useRecordsAction = () => useEngineAction<void>([]);

export type ToolState = "missing" | "downloading" | "unpacking" | "ready" | "failed";

/** Something Mado downloads to work with, such as ffmpeg (engine/src/mado/downloads.json). */
export interface Tool {
  id: string;
  name: string;
  version: string;
  purpose: string;
  licence: string;
  size: number;
  /** Fetched on the setup's Tools step, or the first time the owner asks for what needs it. */
  when: "setup" | "asked";
  state: ToolState;
  done: number;
  problem: string | null;
}

const busy = (state: ToolState) => state === "downloading" || state === "unpacking";

/** Mado's tools, asked again every second while one is downloading. */
export const useTools = () =>
  useEngineQuery<Tool[]>("/tools", (tools) =>
    tools?.some((tool) => busy(tool.state)) ? 1000 : false,
  );

/** Starts downloading a tool: `download.mutate({ path: "/tools/ffmpeg/download" })`. */
export const useDownloadTool = () => useEngineAction<Tool>(["/tools"]);

/** Mado's preferences, chosen during setup and changed later in Settings. */
export interface Settings {
  /** The first-run steps are done. */
  setUp: boolean;
}

export const useSettings = () => useEngineQuery<Settings>("/settings");
/** Saves the preferences: `save.mutate({ path: "/settings", body: settings })`. */
export const useSaveSettings = () => useEngineAction<Settings>(["/settings"], "PUT");

/** How big each part of Mado's data is (Settings > Your data). */
export interface DataSizes {
  /** The data folder. */
  folder: string;
  database: number;
  cache: number;
  logs: number;
  backups: number;
  tools: number;
}

export const useDataSizes = () => useEngineQuery<DataSizes>("/data");
/** Writes the export zip: `exporting.mutate({ path: "/export", body: { folder } })`. */
export const useExport = () => useEngineAction<{ path: string; size: number }>(["/data"]);

/** A backup of Mado's records, made each night (Settings > Your data). */
export interface Backup {
  /** "mado 2026-11-22 0300.db" */
  name: string;
  /** Local time, to the minute: "2026-11-22T03:00". */
  made: string;
  size: number;
  /** Made just before another backup was restored. */
  beforeRestoring: boolean;
  /** The database an imported export held. */
  fromExport: boolean;
  /** Made when the owner asked ("Back up now"); kept apart from the nightly ones. */
  byHand: boolean;
}

export interface Backups {
  /** Newest first. */
  backups: Backup[];
  /** How the last restore went. */
  restored: { name: string; at: string; problem: string | null } | null;
}

export const useBackups = () => useEngineQuery<Backups>("/backups");
/** Makes a backup now: `backUp.mutate({ path: "/backups" })`. */
export const useBackUp = () => useEngineAction<Backup>(["/backups", "/data"]);
/**
 * Asks for a backup to be restored as the engine starts again, which the caller asks the shell
 * for next: `restore.mutate({ path: "/backups/<name>/restore" })`.
 */
export const useRestoreBackup = () => useEngineAction<void>([]);
/**
 * Asks for an export's records to be put in place as the engine starts again, the way a backup
 * is restored: `importing.mutate({ path: "/backups/import", body: { path } })`.
 */
export const useImportExport = () => useEngineAction<void>([]);

// The library: the folders the owner added, and the pictures in them.

/** A folder inside a library folder. */
export interface FolderNode {
  name: string;
  /** Where it is in its library folder: "2026/Trip". */
  dir: string;
  /** In it and the folders inside it. */
  pictures: number;
  /** The folder with the newest pictures first. */
  children: FolderNode[];
}

export interface LibraryFolder {
  id: number;
  path: string;
  /** Its own name: "Phone". */
  name: string;
  addedAt: string;
  /** False while its drive is unplugged. */
  available: boolean;
  /** A scan has looked all through it since it was added. */
  looked: boolean;
  /** Listed in the grid: read, camera RAW, or won't open. */
  pictures: number;
  /** Found and still to read. */
  reading: number;
  raw: number;
  /** Won't open. */
  broken: number;
  children: FolderNode[];
}

/** The whole library in numbers, for Home. */
export interface Library {
  folders: number;
  /** Listed in the grid. */
  pictures: number;
  /** Bytes, every picture found. */
  size: number;
  reading: number;
  raw: number;
  broken: number;
  /** Each library folder's pictures, in the order they were added. */
  parts: { folderId: number; name: string; pictures: number }[];
}

export type ScanState = "idle" | "running" | "done" | "failed" | "stopped";

/** How the latest scan went, or is going. */
export interface Scan {
  /** "stopped": Mado closed, or crashed, before it finished. */
  state: ScanState;
  stage: "finding" | "reading" | "done" | null;
  startedAt: string | null;
  finishedAt: string | null;
  /** Pictures this scan found. */
  found: number;
  /** Of those, the new and changed ones to read. */
  toRead: number;
  read: number;
  current: string | null;
  secondsLeft: number | null;
  /** Library folders that aren't there (a drive unplugged). */
  unavailable: string[];
  problem: string | null;
  /** Pictures it found that weren't there before. */
  added: number | null;
  gone: number | null;
}

/** "raw": listed, not readable yet; "broken": won't open. */
export type PictureState = "ready" | "raw" | "broken";

export interface PictureItem {
  id: number;
  /** Its file's name. */
  name: string;
  path: string;
  /** "JPEG", "HEIC"…; a RAW file's own ("CR3"). */
  format: string | null;
  state: PictureState;
  /** As it's shown. */
  width: number | null;
  height: number | null;
  size: number;
  /** Local time: "2026-11-12T18:42:07". */
  takenAt: string;
  /** Changes when its file does: its copies' addresses carry it. */
  version: string;
}

export interface PicturePage {
  pictures: PictureItem[];
  /** The days on this page, in its order, each with all its pictures counted. */
  days: { day: string; pictures: number }[];
  /** Pictures in the whole list. */
  total: number;
  /** Where the next page starts; null on the last. */
  next: string | null;
}

export interface PictureDetails extends PictureItem {
  folderId: number;
  /** Its library folder. */
  folder: string;
  /** The folders between that and it: "2026/Trip". */
  dir: string;
  /** The file's time, local. */
  modifiedAt: string;
  /** Whose clock says when it was taken. */
  takenFrom: "camera" | "file";
  camera: string | null;
  /** EXIF's 1 to 8. */
  orientation: number | null;
  /** It carries where it was taken. */
  located: boolean;
  /** Why it won't open. */
  problem: string | null;
}

export interface Neighbours {
  /** The pictures before it in the list, the nearest last. */
  before: PictureItem[];
  /** After it, the nearest first. */
  after: PictureItem[];
}

export type Order = "newest" | "oldest";

/** Which pictures a list shows: a library folder (and a folder inside it), every word of a
 * search, and the order. */
export interface Shown {
  folder: number | null;
  dir: string;
  q: string;
  order: Order;
}

/** A list's address's query: "folder=3&dir=2026&order=oldest", leaving out what's as usual. */
export function shownQuery(shown: Shown): string {
  const query = new URLSearchParams();
  if (shown.folder !== null) query.set("folder", String(shown.folder));
  if (shown.folder !== null && shown.dir) query.set("dir", shown.dir);
  if (shown.q.trim()) query.set("q", shown.q.trim());
  if (shown.order !== "newest") query.set("order", shown.order);
  return query.toString();
}

/** What a list shows, from its address's query (the Library's, or a picture's opened from it). */
export function shownFrom(query: URLSearchParams): Shown {
  const folder = Number(query.get("folder"));
  return {
    folder: Number.isInteger(folder) && folder > 0 ? folder : null,
    dir: query.get("dir") ?? "",
    q: query.get("q") ?? "",
    order: query.get("order") === "oldest" ? "oldest" : "newest",
  };
}

const LIBRARY = ["/folders", "/library", "/scan", "/pictures"];

export const useFolders = () => useEngineQuery<LibraryFolder[]>("/folders");
export const useLibrary = () => useEngineQuery<Library>("/library");
/** Adds a folder, which a scan then reads: `add.mutate({ path: "/folders", body: { path } })`. */
export const useAddFolder = () => useEngineAction<LibraryFolder>(LIBRARY);
/** Takes a folder out of the library: `remove.mutate({ path: "/folders/3" })`. Its pictures stay
 * where they are. */
export const useRemoveFolder = () => useEngineAction<void>(LIBRARY, "DELETE");

/** The scan each query client last caught up after: several parts of a screen follow scans, and
 * one catching up is enough. */
const caughtUp = new WeakMap<object, string>();

/**
 * The latest scan, asked again every second while it runs and every three seconds otherwise, so
 * one the engine starts by itself (a picture added) shows soon too. While it runs, the library's
 * numbers follow it, and the grid every few seconds; once it ends, everything catches up.
 */
export function useScan() {
  const scan = useEngineQuery<Scan>("/scan", (now) => (now?.state === "running" ? 1000 : 3000));
  const refresh = useRefresh();
  const queries = useQueryClient();
  const now = scan.data;
  const key = now ? `${now.startedAt}:${now.state}` : null;
  const progress = now?.state === "running" ? `${now.found}:${now.read}` : null;
  const seen = useRef<{ key: string | null; gridAt: number }>({ key: null, gridAt: 0 });
  useEffect(() => {
    if (key === null) return;
    const before = seen.current.key;
    seen.current.key = key;
    const ended = before !== null && before !== key && !key.endsWith(":running");
    if (ended && caughtUp.get(queries) !== key) {
      caughtUp.set(queries, key);
      void refresh(["/library", "/folders", "/pictures"]);
      return;
    }
    if (progress !== null) {
      const grid = Date.now() - seen.current.gridAt > 5000;
      if (grid) seen.current.gridAt = Date.now();
      void refresh(grid ? ["/library", "/folders", "/pictures"] : ["/library", "/folders"]);
    }
  }, [key, progress, refresh, queries]);
  return scan;
}

/** The pictures a list shows, a page at a time: `fetchNextPage()` brings the next. */
export function usePictures(shown: Shown) {
  const engine = useEngine();
  const query = shownQuery(shown);
  const path = `/pictures?${query}`;
  return useInfiniteQuery({
    queryKey: engineKey(engine, path),
    queryFn: ({ pageParam }) => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      const after = pageParam ? `${query ? "&" : ""}after=${encodeURIComponent(pageParam)}` : "";
      return callEngine<PicturePage>(engine, `${path}${after}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
    enabled: engine.state === "ready",
  });
}

export const usePicture = (id: number) => useEngineQuery<PictureDetails>(`/pictures/${id}`);

/** The pictures either side of one, in the list it was opened from. */
export function useNeighbours(id: number, shown: Shown) {
  const query = shownQuery(shown);
  return useEngineQuery<Neighbours>(
    `/pictures/${id}/neighbours?${query ? `${query}&` : ""}count=8`,
  );
}

/** Reads a picture again now: `read.mutate({ path: "/pictures/7/read" })`. */
export const useReadAgain = () => useEngineAction<PictureDetails>(LIBRARY);

/** A picture's copy the window shows: its thumbnail, its view the size of a screen, or itself at
 * full size. The address carries its version, so a picture that changes is shown anew. */
export function pictureAddress(
  picture: { id: number; version: string },
  copy: "thumbnail" | "view" | "full",
) {
  return `/pictures/${picture.id}/${copy}?v=${encodeURIComponent(picture.version)}`;
}

/**
 * A picture the engine serves, as an address the page can show (an object URL), or why it
 * can't: fetched with this launch's token, since the engine answers nothing without it. A null
 * `path` lets it go (a thumbnail scrolled far away), so only what's near is kept.
 */
export function usePictureImage(path: string | null): {
  address: string | null;
  problem: string | null;
} {
  const engine = useEngine();
  const [shown, setShown] = useState<{
    path: string;
    address: string | null;
    problem: string | null;
  } | null>(null);
  useEffect(() => {
    if (path === null || engine.state !== "ready") return;
    let address: string | null = null;
    let cancelled = false;
    // A picture no longer wanted (scrolled past, or the next one opened) lets its request go,
    // so the window's few connections to the engine go to what's in view.
    const stop = new AbortController();
    const headers = { Authorization: `Bearer ${engine.token}` };
    fetch(new URL(path, engine.url), { headers, signal: stop.signal })
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) {
          const problem = (await problemIn(response)) ?? "Mado couldn't show this picture.";
          if (!cancelled) setShown({ path, address: null, problem });
          return;
        }
        const blob = await response.blob();
        if (cancelled) return;
        address = URL.createObjectURL(blob);
        setShown({ path, address, problem: null });
      })
      .catch(() => {
        if (!cancelled) setShown({ path, address: null, problem: "Mado's engine didn't answer." });
      });
    return () => {
      cancelled = true;
      stop.abort();
      if (address) URL.revokeObjectURL(address);
    };
  }, [engine, path]);
  if (shown === null || shown.path !== path) return { address: null, problem: null };
  return { address: shown.address, problem: shown.problem };
}
