import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
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
import { useSettled } from "./settled";

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

/** What the engine said, in its words, and the status it answered with (404: not there). */
export class EngineError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
  ) {
    super(message);
  }
}

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
      response.status,
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
  keep = false,
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
    // `keep`: the last answer stays while another address is asked, rather than a skeleton.
    placeholderData: keep ? keepPreviousData : undefined,
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

/** What the engine changes by itself: a nightly backup made, a download finished, a scan, a
 * picture made. */
const CHANGED_ON_ITS_OWN = [
  "/backups",
  "/data",
  "/tools",
  "/library",
  "/folders",
  "/pictures",
  "/jobs",
  "/history",
  "/quarantine",
  "/pc",
  "/queue",
  "/batches/done",
  "/recipes",
  "/watch-folders",
  "/duplicates",
  "/space",
  "/search",
];

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
  /** What Save offers first (Settings › General › Saving). */
  saveFirst: "new" | "replace";
  /** Where new pictures go: beside their original, or into one folder. */
  newPictures: "beside" | "folder";
  newFolder: string | null;
  /** New pictures keep where a picture was taken. */
  keepLocation: boolean;
  /** A watch folder's batch of more than 20 pictures waits for the night. */
  bigBatchesAtNight: boolean;
  /** Which reader reads the words in pictures for search: as this PC suits, Windows' own
   * (Fast) or PP-OCRv6 (Best). */
  wordsReader: "auto" | "fast" | "best";
}

export const useSettings = () => useEngineQuery<Settings>("/settings");
/** Saves the preferences: `save.mutate({ path: "/settings", body: settings })`. */
/** Saves the owner's choices; search follows a new reader of words at once. */
export const useSaveSettings = () => useEngineAction<Settings>(["/settings", "/search"], "PUT");

/** How big each part of Mado's data is (Settings > Your data). */
export interface DataSizes {
  /** The data folder. */
  folder: string;
  database: number;
  cache: number;
  logs: number;
  backups: number;
  tools: number;
  /** Pictures pasted from the clipboard, kept till they're saved. */
  pasted: number;
  /** The wallpapers Mado made and set, and its copy of the owner's own. */
  wallpapers: number;
  /** What SigLIP read each picture into, for search: read again when it's lost. */
  search: number;
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
  /** Listed in the grid: read, camera RAW waiting for its reader, or won't open. */
  pictures: number;
  /** Found and still to read. */
  reading: number;
  /** Camera RAW. */
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
  /** Camera RAW. */
  raw: number;
  /** Won't open. */
  broken: number;
  /** Of those, marked as damaged by the owner: not asked about again. */
  damaged: number;
  /** Each library folder's pictures, in the order they were added. */
  parts: { folderId: number; name: string; pictures: number }[];
  /** Pictures given a heart and there now, from outside the library too. */
  favourites: number;
  /** Camera RAWs listed while they wait for Mado's RAW reader. */
  rawWaiting: number;
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

/** "waiting": a camera RAW listed while Mado's RAW reader comes; "broken": won't open. */
export type PictureState = "ready" | "waiting" | "broken";

export interface PictureItem {
  id: number;
  /** Its file's name. */
  name: string;
  path: string;
  /** "JPEG", "HEIC"…; a RAW file's own ("CR3"). */
  format: string | null;
  state: PictureState;
  /** A camera RAW: read by Mado's RAW reader, and never written over. */
  raw: boolean;
  /** As it's shown. */
  width: number | null;
  height: number | null;
  size: number;
  /** Local time: "2026-11-12T18:42:07". */
  takenAt: string;
  /** Changes when its file does: its copies' addresses carry it. */
  version: string;
  /** In the grid, a group's kept picture: "burst of 5", "2 copies". */
  group: GroupTag | null;
  /** The owner gave it a heart. */
  favourite: boolean;
  /** Opened from outside the library: dropped, picked, pasted, from File Explorer. */
  outside: boolean;
}

/** A group of duplicates or a burst, on the tile of a picture kept from it. */
export interface GroupTag {
  /** The group's number, which opens its review there. */
  key: number;
  kind: "duplicates" | "burst";
  /** In the group. */
  pictures: number;
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
  /** Its library folder's number; null outside the library. */
  folderId: number | null;
  /** Its library folder; outside the library, the folder it's in. */
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
  /** The owner marked it as damaged: not asked about again till its file changes. */
  damaged: boolean;
  /** Pasted from the clipboard, kept in Mado's data folder till it's saved. */
  pasted: boolean;
  /** It waits in a quarantine: opened to look at only. */
  aside: boolean;
  /** Where Save puts a new picture first, when not beside it: a pasted one's. */
  savesTo: string | null;
}

/** A picture's page: the Library's address for one in it, its own for one from outside. */
export function pageOf(picture: { id: number; outside: boolean }): string {
  return picture.outside ? `/pictures/${picture.id}` : `/library/pictures/${picture.id}`;
}

export interface Neighbours {
  /** The pictures before it in the list, the nearest last. */
  before: PictureItem[];
  /** After it, the nearest first. */
  after: PictureItem[];
}

export type Order = "newest" | "oldest";

/** Which pictures a list shows: a library folder (and a folder inside it), every word of a
 * search, the order, and only the favourites (from outside the library too). */
export interface Shown {
  folder: number | null;
  dir: string;
  q: string;
  order: Order;
  favourites: boolean;
  /** The pictures most like this one (More like this). */
  like: number | null;
}

/** A list's address's query: "folder=3&dir=2026&order=oldest", leaving out what's as usual. */
export function shownQuery(shown: Shown): string {
  const query = new URLSearchParams();
  if (shown.favourites) query.set("favourites", "1");
  if (shown.folder !== null) query.set("folder", String(shown.folder));
  if (shown.folder !== null && shown.dir) query.set("dir", shown.dir);
  if (shown.q.trim()) query.set("q", shown.q.trim());
  if (shown.like !== null) query.set("like", String(shown.like));
  if (shown.order !== "newest") query.set("order", shown.order);
  return query.toString();
}

/** What a list shows, from its address's query (the Library's, or a picture's opened from it). */
export function shownFrom(query: URLSearchParams): Shown {
  const folder = Number(query.get("folder"));
  const like = Number(query.get("like"));
  return {
    folder: Number.isInteger(folder) && folder > 0 ? folder : null,
    dir: query.get("dir") ?? "",
    q: query.get("q") ?? "",
    order: query.get("order") === "oldest" ? "oldest" : "newest",
    favourites: query.get("favourites") === "1",
    like: Number.isInteger(like) && like > 0 ? like : null,
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
      void refresh(["/library", "/folders", "/pictures", "/duplicates", "/space"]);
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
export function usePictures(shown: Shown, enabled = true) {
  const engine = useEngine();
  const query = shownQuery({ ...shown, like: null });
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
    enabled: engine.state === "ready" && enabled,
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

/** Gives a picture a heart, or takes it back:
 * `heart.mutate({ path: "/pictures/7/favourite", body: { favourite: true } })`. */
export const useSetFavourite = () =>
  useEngineAction<PictureDetails>([...LIBRARY, "/wallpaper"], "PUT");

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
 * `path` lets it go (a thumbnail scrolled far away), so only what's near is kept. With a `body`,
 * it's asked for by POST with that JSON (a look's small copy of the picture as its edits leave
 * it).
 */
export function usePictureImage(
  path: string | null,
  body?: unknown,
): {
  address: string | null;
  problem: string | null;
} {
  const engine = useEngine();
  const sent = body === undefined ? null : JSON.stringify(body);
  const asked = path === null ? null : sent === null ? path : `${path} ${sent}`;
  const [shown, setShown] = useState<{
    asked: string;
    address: string | null;
    problem: string | null;
  } | null>(null);
  useEffect(() => {
    if (path === null || asked === null || engine.state !== "ready") return;
    let address: string | null = null;
    let cancelled = false;
    // A picture no longer wanted (scrolled past, or the next one opened) lets its request go,
    // so the window's few connections to the engine go to what's in view.
    const stop = new AbortController();
    const headers = { Authorization: `Bearer ${engine.token}` };
    const init: RequestInit =
      sent === null
        ? { headers, signal: stop.signal }
        : {
            method: "POST",
            headers: { ...headers, "Content-Type": "application/json" },
            body: sent,
            signal: stop.signal,
          };
    fetch(new URL(path, engine.url), init)
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) {
          const problem = (await problemIn(response)) ?? "Mado couldn't show this picture.";
          if (!cancelled) setShown({ asked, address: null, problem });
          return;
        }
        const blob = await response.blob();
        if (cancelled) return;
        address = URL.createObjectURL(blob);
        setShown({ asked, address, problem: null });
      })
      .catch(() => {
        if (!cancelled) setShown({ asked, address: null, problem: "Mado's engine didn't answer." });
      });
    return () => {
      cancelled = true;
      stop.abort();
      if (address) URL.revokeObjectURL(address);
    };
  }, [engine, path, sent, asked]);
  if (shown === null || shown.asked !== asked) return { address: null, problem: null };
  return { address: shown.address, problem: shown.problem };
}

// Search: by name, by what a picture shows and by the words in it, and More like this.

/** A stretch of a picture's words, marked when it's a word the search matched. */
export interface WordsPiece {
  text: string;
  marked: boolean;
}

/** A picture a search found. */
export interface SearchHit extends PictureItem {
  /** SigLIP's score for it (described), or how alike it is (like). */
  score: number | null;
  /** Its words, those the search matched marked (words). */
  words: WordsPiece[] | null;
  /** Its drive isn't connected: found by what Mado read of it before. */
  away: boolean;
}

export type SearchKind = "words" | "described" | "name" | "like";

export interface SearchGroup {
  /** How its pictures were found. */
  kind: SearchKind;
  /** Best first; a picture found two ways is in the first group only. */
  pictures: SearchHit[];
  /** All it found, of which it shows 500 at most. */
  total: number;
}

/** The reader of the words in pictures: the owner's choice, the one in use, its model (Best) or
 * Windows' languages (Fast), and where Best reads. */
export interface WordsReader {
  chosen: "auto" | "fast" | "best";
  reader: "fast" | "best";
  /** PP-OCRv6's download (Best's). */
  model: Tool | null;
  /** The languages Windows reads words in here ("en-GB"). */
  languages: string[];
  place: Place;
}

/** How far reading the library for search has got, and what it waits for. */
export interface SearchState {
  /** Pictures read as they are now. */
  read: number;
  /** The library's pictures that open, on drives connected (or read before). */
  of: number;
  /** Reading now. */
  reading: boolean;
  /** The owner paused it. */
  paused: boolean;
  /** The queue has the graphics card: reading takes its turns more slowly. */
  busy: boolean;
  /** Pictures that couldn't be read now: tried again after the next scan, or once they change. */
  failed: number;
  /** A reader that couldn't run, which reading waits on till Go on (`/search/resume`). */
  problem: SearchProblem | null;
  /** SigLIP's download. */
  describer: Tool | null;
  words: WordsReader;
}

export interface SearchProblem {
  /** SigLIP's ("pictures") or the reader of words'. */
  reader: "pictures" | "words";
  /** What went wrong, in words. */
  said: string;
}

export interface SearchResults {
  /** What was searched for: the words, or (like) the picture's name. */
  search: string;
  /** Those that found anything: words, then described, then name. */
  groups: SearchGroup[];
  /** Pictures found, each once. */
  total: number;
  /** Describing works in English: a search in another language isn't described. */
  english: boolean;
  /** A writing its words are in that the words reader can't read: "Greek". */
  unreadable: string | null;
  state: SearchState;
}

/** Whether reading the library for search is under way, or a model it needs is on its way. */
const searching = (state: SearchState | undefined) =>
  !!state &&
  !state.paused &&
  !state.problem &&
  (state.reading ||
    (readable(state) && state.read + state.failed < state.of) || // between turns, or the scan
    (state.describer !== null && busy(state.describer.state)) ||
    (state.words.model !== null && busy(state.words.model.state)));

/** Whether a reader is here to read the library: SigLIP, or the reader of words in use. */
export const readable = (state: SearchState) =>
  state.describer?.state === "ready" ||
  (state.words.reader === "best"
    ? state.words.model?.state === "ready"
    : state.words.languages.length > 0);

/** What the Library's search box finds, asked again every few seconds while the library is read
 * or a model it needs comes, so the results grow as it goes. */
export function useSearch(shown: Shown, enabled = true) {
  const query = shownQuery({ ...shown, like: null });
  return useEngineQuery<SearchResults>(
    `/search?${query}`,
    (found) => (searching(found?.state) ? 3000 : false),
    enabled && !!shown.q.trim(),
    true,
  );
}

/** The library's pictures most like one, asked again while SigLIP comes or the library is read
 * (more are found as it's read). */
export const useLike = (id: number | null) =>
  useEngineQuery<SearchResults>(
    `/search/like/${id}`,
    (found) => (searching(found?.state) ? 3000 : false),
    id !== null,
  );

/** How far reading the library for search has got, asked again while it reads. */
export const useSearchState = () =>
  useEngineQuery<SearchState>("/search/state", (state) => (searching(state) ? 2000 : false));

/** Pauses reading, or goes on: `reading.mutate({ path: "/search/pause" })`. */
export const useSearchReading = () => useEngineAction<SearchState>(["/search"]);

// Making a picture right for a screen or a print (the Size tab), the jobs that make them, History
// and the quarantine, and this PC.

/** A size a picture can be made for. */
export interface MadeSize {
  /** "tv-8k", "print-a4", "yours-3440x1440", "other-5000x3000", "other-20x30cm" */
  id: string;
  name: string;
  width: number;
  height: number;
  group: "screens" | "yours" | "prints" | "other";
  /** phone, tablet, laptop, monitor, ultrawide, tv, print, screen */
  purpose: string;
  /** What a new picture's name says it was made for: "TV 8K". */
  label: string;
}

export interface Sizes {
  screens: MadeSize[];
  /** The owner's screens Mado remembers. */
  yours: MadeSize[];
  prints: MadeSize[];
}

export const useSizes = () => useEngineQuery<Sizes>("/sizes");
/** Remembers this PC's screens: `remember.mutate({ path: "/screens", body: { seen } })`. */
export const useRememberScreens = () => useEngineAction<MadeSize[]>(["/sizes"]);

export type PictureKind = "photo" | "drawing" | "pixels" | "screenshot";
export type Quality = "fast" | "best";
export type Shape = "crop" | "extend";
export type SaveFormat = "JPEG" | "PNG" | "WebP" | "AVIF";

/** The size step: what the owner asks for on the Size tab. */
export interface SizeStep {
  size: string;
  shape: Shape;
  /** The point to crop around, as fractions across and down; null: as Mado finds it. */
  focus: [number, number] | null;
  /** null: as Mado guesses. */
  kind: PictureKind | null;
  /** null: as this PC starts on. */
  quality: Quality | null;
  clean: boolean;
}

export type TouchName = "grain" | "vignette" | "glow" | "fade" | "leak" | "dust";
/** Each finishing touch's amount, 0 (off) to 100. */
export type Touches = Record<TouchName, number>;

/** The look step: what the owner asks for on the Looks tab. */
export interface LookStep {
  /** A look's id: "warm-film", or one of the owner's, "yours-3". */
  look: string;
  /** 0 to 1. */
  strength: number;
  touches: Touches;
  /** Only on these parts ("Only on a part"), picked as Select picks them; none or missing: the
   * whole picture. */
  parts?: Part[];
}

// Editing by clicking: the parts picked, the brush's strokes, and the edits made with them.

/** A click on the picture, as fractions of it: one that picks, or, with Alt, one that takes
 * away. */
export interface Click {
  x: number;
  y: number;
  keep: boolean;
}

/** A part: the clicks that picked it, and which of SAM's three answers (smallest first) is
 * shown; null: as Mado picks. */
export interface Part {
  clicks: Click[];
  choice: number | null;
}

/** A stroke of the brush: its points as fractions of the picture, its width as a fraction of the
 * picture's shorter side, and whether it takes away (Alt). */
export interface Stroke {
  points: [number, number][];
  size: number;
  take: boolean;
}

/** What's behind a cut-out: nothing (see-through), a colour, or the rest of the picture
 * blurred. */
export type Behind = "nothing" | "colour" | "blurred";

export interface EraseEdit {
  kind: "erase";
  parts: Part[];
  strokes: Stroke[];
  quality: Quality;
}

export interface CutOutEdit {
  kind: "cutout";
  parts: Part[];
  behind: Behind;
  /** "#rrggbb", for a colour behind it. */
  colour: string | null;
}

export interface BlurEdit {
  kind: "blur";
  parts: Part[];
}

export interface SubjectEdit {
  kind: "subject";
  /** null: as this PC suits. */
  quality: Quality | null;
  behind: Behind;
  colour: string | null;
}

/** An edit, made on the picture as the edits before it left it. */
export type Edit = EraseEdit | CutOutEdit | BlurEdit | SubjectEdit;

/** The edits, in order, made on the picture as it was at `version`. */
export interface EditStep {
  version: string;
  edits: Edit[];
}

/** The quick fixes, each off (null) or on at its one setting: what the Fix tab asks for. */
export interface FixStep {
  /** Noise: how much of SCUNet's change is kept, 0 to 1. */
  noise: { strength: number } | null;
  /** Blur from a shaking camera or a moving subject: how much of NAFNet's change is kept. */
  blur: { strength: number } | null;
  /** JPEG blocks: Fast (SCUNet) or Best (FBCNN), null as this PC has them; how hard, 0 to 1 (at
   * Best, FBCNN's quality setting: 0.7 takes it for a JPEG saved at 30), or null as hard as each
   * JPEG was squeezed (a batch's: a picture that isn't a JPEG is left as it is). */
  jpeg: { quality: Quality | null; strength: number | null } | null;
  /** A dark photo, brightened as it measures: how much local contrast after it, 0 to 1. */
  dark: { contrast: number } | null;
}

/** Portrait blur: in focus at a point (fractions across and down; null, its subject), blurred
 * as a lens at `aperture` would (f/1.4 to f/16), the subject's edges found at Fast or Best (null:
 * as this PC suits). */
export interface PortraitStep {
  focus: [number, number] | null;
  aperture: number;
  quality: Quality | null;
}

/** Fog: how thick, 0 to 1, in a colour ("#rrggbb"; null, the picture's own haze). */
export interface FogStep {
  density: number;
  colour: string | null;
}

/** Tilt-shift: the band kept in focus (its middle and height, fractions of the picture's height)
 * and how much blur grows away from it, 0 to 1. */
export interface TiltStep {
  centre: number;
  height: number;
  strength: number;
}

/** The depth tools, each off (null) or on: what the Depth tab asks for. */
export interface DepthStep {
  portrait: PortraitStep | null;
  fog: FogStep | null;
  tilt: TiltStep | null;
}

/** Restoring an old photo, each part off (null) or on: what the Fix tab's Restore asks for. */
export interface RestoreStep {
  /** The picture's version the scratches' strokes were painted on; null for none painted yet. */
  version: string | null;
  /** Scratches and dust filled: what Mado found, with the owner's strokes over it (painting adds,
   * Alt takes away). */
  scratches: { strokes: Stroke[] } | null;
  /** A black-and-white or toned picture coloured: how much of DDColor's colours, 0 to 1. */
  colour: { strength: number } | null;
  /** Faded colours brought back from the picture's own levels, 0 to 1. */
  faded: { strength: number } | null;
}

/** One picture, one recipe: what the Edit, Fix, Size, Depth and Looks tabs set together, made by
 * one Save. */
export interface Recipe {
  edit?: EditStep | null;
  /** Restoring, made after the edits and before the fixes. */
  restore?: RestoreStep | null;
  fix?: FixStep | null;
  size: SizeStep | null;
  depth?: DepthStep | null;
  /** A painting style, made after the size and the depth tools, before the look. */
  paint?: PaintStep | null;
  look: LookStep | null;
}

/** The painting step: what the owner asks for in the Looks tab's painting styles. */
export interface PaintStep {
  /** "van-gogh", "pencil", one of the owner's ("yours-3"), or "picture" with its `code`. */
  style: string;
  /** 0 to 1: mixed with the picture as it was. */
  strength: number;
  /** The picture's own colours, the painting's lightness. */
  colours: boolean;
  /** A classic one's one setting, 0 to 100; null: where it starts. */
  setting: number | null;
  /** A picture's own style: its 512 numbers, as the engine read them. */
  code?: string | null;
  /** What that picture is called: "Night market". */
  named?: string | null;
  /** Only on these parts, as a look's ("Only on a part"); none or missing: the whole picture. */
  parts?: Part[];
}

/** A part as picked: plain names, never a guess at what it is. */
export interface PickedPart extends Part {
  /** "Part 1" */
  name: string;
  choice: number;
  /** How many answers there are to step through. */
  choices: number;
}

/** The parts picked, and the outline round them. */
export interface Selection {
  parts: PickedPart[];
  /** An SVG path in a frame 1000 across and 1000 down, stretched over the picture. */
  outline: string;
  /** Seconds reading the picture took, when this pick read it. */
  read: number | null;
  place: "card" | "processor";
  seconds: number;
  /** Seconds it waited for the graphics card, while the queue's picture had it. */
  waited: number;
  /** An Alt-click outside every part. */
  missed: boolean;
}

/** What an edit came to. */
export interface Edited {
  seconds: number;
  place: "card" | "processor" | null;
  waited: number;
  /** An erase much smoother than what's round it: Best may do better. */
  smeared: boolean;
}

/** Picks parts: `select.mutate({ path: "/pictures/7/select", body })`. */
export const useSelect = () => useEngineAction<Selection>([]);
/** Makes edits for the previews: `edit.mutate({ path: "/pictures/7/edit", body })`. */
export const useEdit = () => useEngineAction<Edited>([]);

/** A part of the picture as fractions of its width and height. */
export interface Fraction {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A download a plan waits for: the Best photo model, or LaMa to extend edges. */
export interface Need {
  id: string;
  name: string;
  size: number;
}

/** How a picture would be made to a recipe. */
export interface Plan {
  width: number;
  height: number;
  /** What the size makes it for: "TV 8K"; empty with no size. */
  label: string;
  shape: Shape;
  sides: "none" | "top and bottom" | "sides";
  /** The part of the picture kept. */
  kept: Fraction;
  /** What's made: more than the picture when extending. */
  canvas: Fraction;
  focus: [number, number];
  focusFound: boolean;
  /** What the shape does, in a sentence. */
  note: string;
  kind: PictureKind;
  kindGuessed: boolean;
  quality: Quality;
  /** "keep": no size, its pixels as they are. */
  method: "ai" | "pixels" | "smooth" | "shrink" | "keep";
  model: string | null;
  how: string;
  warning: string | null;
  /** Cleaning first changes the model (Fast keeps grain without it). */
  cleanMatters: boolean;
  /** The fixes take noise and blocks out first, so the model doesn't clean them again. */
  cleanedFirst: boolean;
  /** The look, as Save says it after "with": "Warm film at 60%"; null with no look. */
  look: string | null;
  /** The edits, as Save and History say them: "erased a part"; null with none. */
  edit: string | null;
  /** The fixes, as Save and History say them: "took out noise"; null with none. */
  fix: string | null;
  /** JPEG blocks at Fast or Best, as decided; null without them. */
  fixQuality: Quality | null;
  /** Of `seconds`, about how long the fixes take. */
  fixSeconds: number;
  /** Where the fixes' models run: the processor when the card has no room left for them; null
   * without fixes. */
  fixPlace: "card" | "processor" | null;
  /** The depth tools, as Save and History say them: "portrait blur at f/2.8"; null with none. */
  depth: string | null;
  /** Of `seconds`, about how long the depth tools take. */
  depthSeconds: number;
  /** Where the depth model runs; null without the depth tools. */
  depthPlace: "card" | "processor" | null;
  /** Restoring, as Save and History say it: "filled its scratches and dust"; null without. */
  restore: string | null;
  /** Of `seconds`, about how long restoring takes. */
  restoreSeconds: number;
  /** Where the scratch detector and DDColor run: the processor when the card has no room left
   * for them; null without restoring that needs them. */
  restorePlace: "card" | "processor" | null;
  /** How much of the picture the scratches' mask covers, as found and painted, 0 to 1; null
   * without scratches, or while the detector isn't downloaded. */
  restoreCovers: number | null;
  /** Where its scratches are found (the detector's place); null without scratches. */
  scratchPlace: "card" | "processor" | null;
  /** Where its painting style is made; null without one. */
  paintPlace: "card" | "processor" | null;
  /** A painting made far bigger than it's painted: seen close, its strokes are soft. */
  paintNote: string | null;
  seconds: number;
  place: "card" | "processor";
  /** The time is this PC's own, not a guess. */
  measured: boolean;
  format: SaveFormat;
  formatQuality: number | null;
  fits: string;
  colour: string;
  bytes: number;
  /** It has see-through parts, which JPEG makes white. */
  seeThrough: boolean;
  /** A cut-out with nothing behind it: only PNG and WebP keep it. */
  nothingBehind: boolean;
  needs: Need[];
}

/**
 * A POST that asks rather than changes (a plan, a name): a query, keyed by its body, waiting
 * until the engine is ready and `enabled`. `once`: asked once for each body, not again as the
 * window comes back into focus (the pictures a batch is made of stay as they were found).
 */
function useEnginePost<T>(path: string, body: unknown, enabled = true, once = false) {
  const engine = useEngine();
  const sent = JSON.stringify(body);
  const asking = engineKey(engine, path);
  return useQuery({
    queryKey: [...asking, sent],
    queryFn: () => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      return callEngine<T>(engine, path, {
        method: "POST",
        body: sent,
        headers: { "Content-Type": "application/json" },
      });
    },
    enabled: engine.state === "ready" && enabled,
    // The last answer stays while the next is asked, for the same picture only.
    placeholderData: (before, previous) =>
      previous && JSON.stringify(previous.queryKey.slice(0, -1)) === JSON.stringify(asking)
        ? before
        : undefined,
    retry: false, // an answer that fails says why at once
    ...(once ? { staleTime: Number.POSITIVE_INFINITY, refetchOnWindowFocus: false } : {}),
  });
}

/** How a picture would be made to a recipe (null: nothing chosen yet). */
export const usePlan = (id: number, recipe: Recipe | null) =>
  useEnginePost<Plan>(`/pictures/${id}/plan`, recipe, recipe !== null);

/** What Mado measures of a picture for the Fix tab: only what it can measure cheaply and
 * reliably. */
export interface Fixes {
  /** A JPEG's own quality, from its tables; null for any other file. */
  jpegQuality: number | null;
  /** Mado suggests taking its JPEG blocks out. */
  blocks: boolean;
  /** How many stops brighter the dark photo fix makes it: 0 when it isn't dark. */
  stops: number;
  /** Mado suggests brightening it. */
  dark: boolean;
  /** Black and white: the fixes keep it so. */
  grey: boolean;
  /** Its see-through parts stay as they are. */
  seeThrough: boolean;
  /** Its colours, kept: "sRGB", "Display P3". */
  colour: string;
  megapixels: number;
  /** What its colours are, for restoring: black and white or a toned print (offered colouring),
   * or a colour photo (offered its faded colours back). */
  colours: "grey" | "toned" | "colour";
  /** A toned print's tone: sepia's brown, or another; null for any other picture. */
  tone: "sepia" | "toned" | null;
}

/** What the scratch detector found on a picture, as its mask (an address the page can show, white
 * where it found scratches and dust), and how finding it went. */
export interface Scratches {
  address: string | null;
  /** How much of the picture it found, 0 to 1. */
  found: number | null;
  /** Seconds finding took; 0 when it was kept from before. */
  seconds: number | null;
  /** Where it ran; null when it was kept. */
  place: Place | null;
  problem: string | null;
  busy: boolean;
}

/** What the scratch detector finds on a picture as its edits leave it, its mask fetched as the
 * previews are (null `ask`: let go). */
export function useScratches(
  id: number,
  ask: { version: string; edits: Edit[] } | null,
): Scratches {
  const engine = useEngine();
  const wanted = ask ? JSON.stringify(ask) : null;
  const [shown, setShown] = useState<{
    id: number;
    sent: string;
    found: Omit<Scratches, "busy">;
  } | null>(null);
  const current = useRef<string | null>(null);
  const showing = useCallback((next: string | null) => {
    if (current.current && current.current !== next) URL.revokeObjectURL(current.current);
    current.current = next;
  }, []);
  useEffect(() => () => showing(null), [showing]);
  useEffect(() => {
    if (wanted === null || engine.state !== "ready") return;
    let cancelled = false;
    const stop = new AbortController();
    const failed = (problem: string) =>
      setShown({
        id,
        sent: wanted,
        found: { address: null, found: null, seconds: null, place: null, problem },
      });
    fetch(new URL(`/pictures/${id}/scratches`, engine.url), {
      method: "POST",
      body: wanted,
      headers: { Authorization: `Bearer ${engine.token}`, "Content-Type": "application/json" },
      signal: stop.signal,
    })
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) {
          failed((await problemIn(response)) ?? "Mado couldn't look for scratches.");
          return;
        }
        const number = (name: string) => {
          const said = response.headers.get(name);
          const value = said === null || said === "" ? Number.NaN : Number(said);
          return Number.isFinite(value) ? value : null;
        };
        const place = response.headers.get("X-Place");
        const blob = await response.blob();
        if (cancelled) return;
        const address = URL.createObjectURL(blob);
        showing(address);
        setShown({
          id,
          sent: wanted,
          found: {
            address,
            found: number("X-Found"),
            seconds: number("X-Made-In"),
            place: place === "card" || place === "processor" ? place : null,
            problem: null,
          },
        });
      })
      .catch(() => {
        if (!cancelled) failed("Mado's engine didn't answer.");
      });
    return () => {
      cancelled = true;
      stop.abort();
    };
  }, [engine, id, wanted, showing]);
  const nothing = { address: null, found: null, seconds: null, place: null, problem: null };
  if (wanted === null) return { ...nothing, busy: false };
  if (shown === null || shown.id !== id || shown.sent !== wanted) return { ...nothing, busy: true };
  return { ...shown.found, busy: false };
}

/** What Mado read of a picture's depth, for the Depth tab. */
export interface DepthRead {
  /** The depth model, while it isn't downloaded: nothing else is read till then. */
  needs: Need[];
  /** Its depth was read (or kept from before). */
  read: boolean;
  /** No depth to speak of: a scan, a screenshot. */
  flat: boolean;
  /** Where the depth model runs. */
  place: "card" | "processor";
  /** What reading it took, when this asked it to be read; null when it was kept. */
  seconds: number | null;
  /** Of which waiting for the graphics card, while the queue's picture had it. */
  waited: number;
  /** Mado found a subject, which portrait blur keeps sharp by its own edges. */
  subject: boolean;
  /** Where portrait blur is in focus without a click: its subject's middle. */
  focus: [number, number] | null;
  /** Its see-through parts stay as they are. */
  seeThrough: boolean;
  grey: boolean;
  megapixels: number;
  /** Past what Mado edits: the Size tab makes a smaller copy first. */
  tooBig: boolean;
}

/** What Mado reads of a picture's depth, as its edits leave it (null: not asked yet). */
export const useDepthRead = (id: number, ask: { version: string; edits: Edit[] } | null) =>
  useEnginePost<DepthRead>(`/pictures/${id}/depth`, ask, ask !== null);

/** A size a 3D photo can be made at. */
export interface MotionSize {
  size: "1080p" | "4k";
  width: number;
  height: number;
  /** About how big it comes out at the length asked for. */
  bytes: number;
}

/** What this PC can make a picture's 3D photo with. */
export interface MotionFacts {
  /** Mado's ffmpeg is downloaded: an MP4 needs it. */
  ffmpeg: boolean;
  /** The H.264 encoder that works here ("h264_mf"); null with none. */
  encoder: string | null;
  /** "Windows' own video encoder" */
  encoderName: string | null;
  /** 1080p, and 4K when the picture has the pixels for it. */
  sizes: MotionSize[];
  /** An animated WebP's size. */
  webp: MotionSize;
  /** The lengths it can be, in seconds. */
  seconds: number[];
  /** The downloads it waits for: the depth model. */
  needs: string[];
}

export const useMotionFacts = (id: number | null) =>
  useEngineQuery<MotionFacts>(id === null ? "" : `/pictures/${id}/motion`, undefined, id !== null);

export type Movement = "push" | "sway" | "circle";

/** A 3D photo asked for: of the picture as its edits leave it. */
export interface MotionAsk {
  version: string;
  edits: Edit[];
  motion: Movement;
  seconds: number;
  /** How much the view moves, 0 to 1. */
  amount: number;
  /** What the moving view uncovers: stretched from beside it (Fast) or drawn by LaMa (Best). */
  fill: Quality;
  size: "1080p" | "4k";
  format: "mp4" | "webp";
}

/** A 3D photo, as it's coming on. */
export interface Motion {
  id: string;
  state: "waiting" | "making" | "done" | "failed";
  progress: number;
  /** What making it took. */
  seconds: number | null;
  width: number;
  height: number;
  bytes: number;
  format: "mp4" | "webp";
  /** What made an MP4: "Windows' own video encoder". */
  encoderName: string | null;
  problem: string | null;
}

/** A 3D photo saved: where, and its line in History. */
export interface MotionSaved {
  path: string;
  name: string;
  historyId: number;
}

/** Makes a 3D photo into Mado's cache: `make.mutate({ path: "/pictures/7/motion", body })`. */
export const useMakeMotion = () => useEngineAction<Motion>([]);
/** How a 3D photo is coming on, asked again while it's made. */
export const useMotion = (id: string | null) =>
  useEngineQuery<Motion>(
    id === null ? "" : `/motion/${id}`,
    (found) => (found && (found.state === "waiting" || found.state === "making") ? 300 : false),
    id !== null,
  );
/** Saves one: `save.mutate({ path: "/motion/ab12/save", body: { folder } })`. */
export const useSaveMotion = () => useEngineAction<MotionSaved>(["/history"]);
/** Lets one go: `drop.mutate({ path: "/motion/ab12" })`. */
export const useDropMotion = () => useEngineAction<void>([], "DELETE");

/** What the Fix tab suggests for a picture, asked again once its file changes. */
export const useFixes = (picture: { id: number; version: string } | null) =>
  useEngineQuery<Fixes>(
    picture ? `/pictures/${picture.id}/fixes?v=${encodeURIComponent(picture.version)}` : "",
    undefined,
    picture !== null,
  );

// Looks: Mado's and the owner's own (the Looks tab).

/** One of Mado's looks. */
export interface Look {
  /** "warm-film"; the owner's are "yours-3". */
  id: string;
  name: string;
  /** Changes when its table does: its small copies' addresses carry it. */
  version: string;
}

/** One of the owner's looks: a .cube file imported, or a mix kept from the Looks tab. */
export interface YourLook {
  /** "yours-3" */
  id: string;
  name: string;
  kind: "cube" | "mix";
  /** Its table's points a side. */
  points: number;
  /** A mix's, which picking it brings back. */
  touches: Touches;
  /** The .cube file's name, or what the mix is made of: "Warm film at 60%, grain 20". */
  source: string;
  addedAt: string;
}

export interface Looks {
  /** Mado's, the original first. */
  looks: Look[];
  /** The owner's, oldest first. */
  yours: YourLook[];
}

export const useLooks = () => useEngineQuery<Looks>("/looks");

/** A small copy of a picture in a look: its address carries both their versions, so a picture
 * or a look that changes is shown anew. */
export function lookAddress(picture: { id: number; version: string }, look: Look) {
  return `/pictures/${picture.id}/looks/${look.id}?v=${encodeURIComponent(picture.version)}-${look.version}`;
}

// Painting styles: Mado's painters and classic means, and the owner's own (the Looks tab).

/** One of Mado's painting styles: after a public-domain painter, or drawn by code. */
export interface PaintingStyle {
  /** "van-gogh", "oil" */
  id: string;
  /** "After Van Gogh" */
  name: string;
  kind: "painter" | "classic";
  /** A painter's: the painting it learned from. */
  painting: string | null;
  /** A painter's network, as /tools lists it. */
  download: string | null;
  /** A classic one's one setting: "Darkness". */
  setting: string | null;
  /** Where that setting starts. */
  first: number;
}

/** One of the owner's styles: a picture's style kept, as its numbers and a small copy. */
export interface YourStyle {
  /** "yours-3" */
  id: string;
  name: string;
  /** The picture it came from, by name. */
  source: string;
  addedAt: string;
}

export interface Styles {
  painters: PaintingStyle[];
  classics: PaintingStyle[];
  yours: YourStyle[];
  /** The download that reads a picture's style and paints with it. */
  reader: string;
}

/** A picture's style as the engine read it. */
export interface ReadStyle {
  code: string;
  /** "Night market" */
  named: string;
  /** The picture's version, which the address of its small copy carries. */
  version: string;
}

export const useStyles = () => useEngineQuery<Styles>("/styles");

/** A small copy of a picture in a style: its address carries the picture's version, and a kept
 * style's id, never given again, says which. */
export function styleAddress(picture: { id: number; version: string }, style: string) {
  return `/pictures/${picture.id}/styles/${style}?v=${encodeURIComponent(picture.version)}`;
}

/** The small copy of the picture one of the owner's styles came from. */
export const styleThumbnailAddress = (style: string) => `/styles/${style}/thumbnail`;

/** Reads a picture's style: `read.mutate({ path: "/pictures/7/style" })`. */
export const useReadStyle = () => useEngineAction<ReadStyle>([]);
/** Keeps a picture's style: `keep.mutate({ path: "/styles", body: { name, code, picture } })`. */
export const useKeepStyle = () => useEngineAction<YourStyle>(["/styles"]);
/** Renames one: `rename.mutate({ path: "/styles/yours-3", body: { name } })`. */
export const useRenameStyle = () => useEngineAction<YourStyle>(["/styles"], "PUT");
/** Deletes one: `remove.mutate({ path: "/styles/yours-3" })`. */
export const useDeleteStyle = () => useEngineAction<void>(["/styles"], "DELETE");

/** Imports a .cube file: `importing.mutate({ path: "/looks/import", body: { path } })`. */
export const useImportLook = () => useEngineAction<YourLook>(["/looks"]);
/** Keeps the mix: `keep.mutate({ path: "/looks", body: { name, look } })`. */
export const useKeepLook = () => useEngineAction<YourLook>(["/looks"]);
/** Renames one: `rename.mutate({ path: "/looks/yours-3", body: { name } })`. */
export const useRenameLook = () => useEngineAction<YourLook>(["/looks"], "PUT");
/** Deletes one: `remove.mutate({ path: "/looks/yours-3" })`. */
export const useDeleteLook = () => useEngineAction<void>(["/looks"], "DELETE");

/** A part of the picture made, in its pixels. */
export interface Region {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PreviewAsk {
  recipe: Recipe;
  side: "before" | "after";
  /** A part at full detail. */
  region?: Region;
  /** Or all of it, no bigger than this. */
  fit?: { width: number; height: number };
}

/**
 * A preview of a picture made (a part at full detail, or all of it fitted), as an address the page
 * can show, how long it took to make, and why it couldn't be. A null `ask` lets it go. Asked once
 * the ask stops changing; an answer to an ask since changed is dropped. With `keep`, the last
 * preview of the same picture stays shown while the next is made, so going from look to look
 * never flashes back; another picture's never stands in.
 */
export function usePreview(
  id: number,
  ask: PreviewAsk | null,
  { keep = false }: { keep?: boolean } = {},
): { address: string | null; problem: string | null; seconds: number | null; busy: boolean } {
  const engine = useEngine();
  const wanted = ask ? JSON.stringify(ask) : null;
  // Asked once the picture stops moving: a preview takes the card a moment.
  const settled = useSettled(wanted, 150);
  const sent = settled === wanted ? wanted : null;
  const [shown, setShown] = useState<{
    id: number;
    sent: string;
    address: string | null;
    problem: string | null;
    seconds: number | null;
  } | null>(null);
  // The address shown now: let go once the next one is shown, or the preview is.
  const current = useRef<string | null>(null);
  const showing = useCallback((next: string | null) => {
    if (current.current && current.current !== next) URL.revokeObjectURL(current.current);
    current.current = next;
  }, []);
  useEffect(() => () => showing(null), [showing]);
  useEffect(() => {
    if (wanted !== null) return;
    showing(null); // let go, and forgotten: it's never shown again
    setShown(null);
  }, [wanted, showing]);
  useEffect(() => {
    if (sent === null || engine.state !== "ready") return;
    let cancelled = false;
    const stop = new AbortController();
    fetch(new URL(`/pictures/${id}/preview`, engine.url), {
      method: "POST",
      body: sent,
      headers: { Authorization: `Bearer ${engine.token}`, "Content-Type": "application/json" },
      signal: stop.signal,
    })
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) {
          const problem = (await problemIn(response)) ?? "Mado couldn't make the preview.";
          if (!cancelled) setShown({ id, sent, address: null, problem, seconds: null });
          return;
        }
        // How long it took, when the engine says (a header it lets the window read).
        const said = response.headers.get("X-Made-In");
        const seconds = said === null ? null : Number(said);
        const blob = await response.blob();
        if (cancelled) return;
        const address = URL.createObjectURL(blob);
        showing(address);
        setShown({
          id,
          sent,
          address,
          problem: null,
          seconds: seconds !== null && Number.isFinite(seconds) ? seconds : null,
        });
      })
      .catch(() => {
        if (!cancelled)
          setShown({
            id,
            sent,
            address: null,
            problem: "Mado's engine didn't answer.",
            seconds: null,
          });
      });
    return () => {
      cancelled = true;
      stop.abort();
    };
  }, [engine, id, sent, showing]);
  if (wanted === null) return { address: null, problem: null, seconds: null, busy: false };
  const ours = shown !== null && shown.id === id && shown.address === current.current;
  if (shown === null || shown.id !== id || shown.sent !== wanted) {
    const last = keep && ours ? shown.address : null;
    return { address: last, problem: null, seconds: null, busy: true };
  }
  return { address: shown.address, problem: shown.problem, seconds: shown.seconds, busy: false };
}

export interface SavingAsk {
  recipe: Recipe;
  how: "new" | "replace";
  format: SaveFormat;
  quality: number | null;
  folder: string | null;
  keepColours: boolean;
}

/** What a picture made would be saved as. */
export interface SavingName {
  name: string;
  folder: string;
  /** The name it would have had, already there. */
  taken: string | null;
  takenAt: string | null;
  bytes: number;
  colour: string;
}

export const useSavingName = (id: number, ask: SavingAsk | null) =>
  useEnginePost<SavingName>(`/pictures/${id}/saving`, ask, ask !== null);

export interface Saving {
  how: "new" | "replace";
  format: SaveFormat;
  quality: number | null;
  /** New pictures: into this folder; null beside the original. */
  folder: string | null;
  keepCamera: boolean;
  keepColours: boolean;
  keepLocation: boolean;
  /** Save starts on this way from now on. */
  always: boolean;
}

/** A picture in the library, enough to show its thumbnail or open it. */
export interface PictureRef {
  id: number;
  version: string;
}

export type JobState = "queued" | "running" | "done" | "failed" | "cancelled";

/** A job making a picture. */
export interface Job {
  id: number;
  pictureId: number | null;
  /** The original's file name. */
  name: string;
  /** What its size makes it for: "TV 8K"; null with no size. */
  madeFor: string | null;
  /** What it's made with: "Warm film at 60%"; null with no look. */
  look: string | null;
  /** What's edited first: "erased a part"; null with no edits. */
  edit: string | null;
  /** What the fixes do: "took out noise"; null with no fixes. */
  fix: string | null;
  /** The depth tools: "portrait blur at f/2.8"; null without. */
  depth: string | null;
  /** What restoring does: "filled its scratches and dust"; null without. */
  restore: string | null;
  how: "new" | "replace";
  state: JobState;
  stage:
    | "reading"
    | "editing"
    | "restoring"
    | "shaping"
    | "fixing"
    | "making"
    | "depthing"
    | "painting"
    | "looking"
    | "saving"
    | null;
  /** 0 to 1. */
  progress: number;
  secondsLeft: number | null;
  queuedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  result: string | null;
  resultName: string | null;
  resultPicture: PictureRef | null;
  /** Why it didn't work; while it waits, why it waits. */
  problem: string | null;
  /** Its picture is open in another app: it tries again then. */
  heldUntil: string | null;
}

const JOBS = ["/jobs", "/history", "/library", "/folders", "/pictures", "/quarantine"];
const active = (jobs: Job[] | undefined) =>
  jobs?.some((job) => job.state === "queued" || job.state === "running") ?? false;

/** Makes a picture: `make.mutate({ path: "/pictures/7/make", body: { recipe, saving } })`. Its
 * "Always save this way" changes the settings. */
export const useMake = () => useEngineAction<Job>(["/jobs", "/settings"]);
/** A new picture saved a moment ago (or one that replaced its original in another format) that
 * the library hasn't read yet: asked for again till it has, so it can be offered to open. */
const unread = (jobs: Job[] | undefined) => {
  const last = jobs?.[0];
  if (last?.state !== "done" || last.resultPicture || !last.finishedAt) return false;
  if (last.how === "replace" && last.resultName === last.name) return false; // the same file
  return Date.now() - new Date(last.finishedAt).getTime() < 60_000;
};

/** A picture's latest jobs, asked again every half second while one is under way, and every two
 * while what it saved waits to be read. */
export const usePictureJobs = (id: number) =>
  useEngineQuery<Job[]>(`/jobs?picture=${id}&limit=1`, (jobs) =>
    active(jobs) ? 500 : unread(jobs) ? 2000 : false,
  );
/** Jobs waiting or under way, for the status bar. */
export const useActiveJobs = () =>
  useEngineQuery<Job[]>("/jobs?active=true", (jobs) => (active(jobs) ? 1000 : 5000));
/** Cancels a job: `cancel.mutate({ path: "/jobs/3/cancel" })`. */
export const useCancelJob = () => useEngineAction<Job>(["/jobs"]);

/** One thing in History. */
export interface HistoryEntry {
  id: number;
  /** Local time, with its offset. */
  at: string;
  /** "aside": set aside from a group of duplicates or a burst. */
  kind: "made" | "replaced" | "emptied" | "aside";
  /** The original's file name; the drive, for a quarantine emptied; a picture set aside's own. */
  name: string;
  /** What its size made it for: "TV 8K". */
  madeFor: string | null;
  /** What it was made with: "Warm film at 60%". */
  look: string | null;
  /** What was edited first: "erased a part". */
  edit: string | null;
  /** What restoring did: "filled its scratches and dust". */
  restore: string | null;
  /** What the fixes did: "took out noise". */
  fix: string | null;
  /** The depth tools: "portrait blur at f/2.8"; a 3D photo: "into a 3D photo, swaying for 5 s". */
  depth: string | null;
  original: string | null;
  result: string | null;
  resultName: string | null;
  /** What waits in quarantine for it now. */
  aside: string | null;
  /** The day the clear-out takes it: "2026-12-22". */
  asideUntil: string | null;
  clearedAt: string | null;
  /** The clear-out after its days, or the owner emptying the quarantine. */
  clearedBy: "days" | "owner" | null;
  undoneAt: string | null;
  bytes: number | null;
  picture: PictureRef | null;
  canUndo: boolean;
  canRedo: boolean;
  /** The batch it was made in, which History shows as one line. */
  batch: number | null;
  /** A picture set aside: the one of its group that was kept. */
  keptName: string | null;
  /** A picture set aside: the review it was set aside in, which History shows as one line. */
  review: number | null;
}

/** A review of duplicates and bursts as History's one line for it. */
export interface ReviewLine {
  id: number;
  at: string;
  /** Groups of duplicates whose rest it set aside. */
  duplicates: number;
  bursts: number;
  /** Pictures it set aside. */
  pictures: number;
  /** What setting them aside freed. */
  bytes: number;
  /** Put back since. */
  back: number;
  /** Cleared out of quarantine since: after their days, or emptied. */
  cleared: number;
  canUndo: boolean;
  /** Where what it set aside waits: "D:". */
  drives: string[];
  asideUntil: string | null;
  /** A picture it kept. */
  picture: PictureRef | null;
}

export interface HistoryPage {
  entries: HistoryEntry[];
  /** The day the next page starts before; null: that's all. */
  older: string | null;
  /** The batches its lines were made in. */
  batches: BatchLine[];
  /** The reviews its lines were set aside in. */
  reviews: ReviewLine[];
}

/** History, a week of days at a time: `fetchNextPage()` brings the week before. */
export function useHistory(query: string) {
  const engine = useEngine();
  const path = `/history${query ? `?q=${encodeURIComponent(query)}` : ""}`;
  return useInfiniteQuery({
    queryKey: engineKey(engine, path),
    queryFn: ({ pageParam }) => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      const before = pageParam ? `${query ? "&" : "?"}before=${pageParam}` : "";
      return callEngine<HistoryPage>(engine, `${path}${before}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.older,
    enabled: engine.state === "ready",
  });
}

/** Undoes a line: `undo.mutate({ path: "/history/3/undo" })` (or `/redo`). */
export const useHistoryAction = () =>
  useEngineAction<HistoryEntry>([...JOBS, "/duplicates", "/space"]);
/** Clears History: `clear.mutate({ path: "/history/clear", body: { keep } })`. */
export const useClearHistory = () => useEngineAction<{ cleared: number }>(["/history"]);

/** What waits in quarantine on a drive. */
export interface DriveAside {
  drive: string;
  folder: string;
  bytes: number;
}

export const useQuarantine = () => useEngineQuery<DriveAside[]>("/quarantine");
/** Empties a drive's quarantine: `empty.mutate({ path: "/quarantine/empty", body: { drive } })`. */
export const useEmptyQuarantine = () =>
  useEngineAction<{ bytes: number }>(["/quarantine", "/history"]);

/** This PC, as Settings › About and Setup show it. */
export interface Pc {
  card: {
    name: string;
    maker: "nvidia" | "amd" | "intel" | "other";
    memory: number | null;
    integrated: boolean;
    driver: string | null;
  } | null;
  processor: string | null;
  cores: number | null;
  memory: number | null;
  /** null before it's tested. */
  checkedAt: string | null;
  /** The AI models run on the card; null before it's tested. */
  onCard: boolean | null;
  problem: string | null;
  place: "card" | "processor";
  testing: boolean;
  timing: boolean;
  measured: { at: string; tested: boolean; pictures: number } | null;
  startsOn: { photo: Quality; drawing: Quality };
  abilities: {
    kind: "photo" | "drawing";
    quality: Quality;
    model: string;
    pace: "ready" | "slow";
    /** A phone's 12-megapixel photo made for a 4K screen. */
    seconds: number;
    download: boolean;
  }[];
  /** Where each editing model runs now. */
  editing: EditingPlaces;
}

/** Where each editing model runs now: on the card when it has room, else on the processor. */
export interface EditingPlaces {
  /** SAM reading a picture; each click after that is on the processor. */
  select: Place;
  eraseFast: Place;
  eraseBest: Place;
  cutFast: Place;
  cutBest: Place;
}

export type Place = "card" | "processor";

/** This PC, asked again every second while it's being tested. */
export const usePc = () => useEngineQuery<Pc>("/pc", (pc) => (pc?.testing ? 1000 : false));
/** Tests this PC again: `test.mutate({ path: "/pc/test" })`. */
export const useTestPc = () => useEngineAction<Pc>(["/pc"]);

// Many at once: batches, the queue, recipes and watch folders.

/** Make it for a screen, as a batch's step: the Size tab's choices, each picture its own
 * subject. */
export interface SizeStepItem extends Omit<SizeStep, "focus"> {
  step: "size";
}

/** A look, as a batch's step: the Looks tab's choices. */
export interface LookStepItem extends LookStep {
  step: "look";
}

/** The fixes, as a batch's step: the Fix tab's choices. */
export interface FixStepItem extends FixStep {
  step: "fix";
}

/** A painting style, as a batch's step: the Looks tab's choices, on the whole of each picture. A
 * picture's own style goes in a batch once it's kept as a style. */
export interface PaintStepItem extends Omit<PaintStep, "parts" | "code" | "named"> {
  step: "paint";
}

/** Cut out the subject, as a batch's step: found without a click in each picture. */
export interface CutoutStepItem {
  step: "cutout";
  /** null: as this PC suits. */
  quality: Quality | null;
  behind: Behind;
  colour: string | null;
}

/** The depth tools, as a batch's step: portrait blur in focus at each picture's subject. */
export interface DepthStepItem extends DepthStep {
  step: "depth";
}

/** Restoring, as a batch's step: each picture as it needs, a black-and-white or sepia one
 * coloured, a colour photo's faded colours brought back. Never scratches: those are checked on
 * each picture's own page. */
export interface RestoreStepItem {
  step: "restore";
  colour: { strength: number } | null;
  faded: { strength: number } | null;
  /** Never sent: a batch leaves scratches to each picture's page, and the engine refuses them. */
  scratches?: null;
}

/** A batch's step. Later pieces add kinds of their own. */
export type BatchStep =
  | CutoutStepItem
  | RestoreStepItem
  | FixStepItem
  | SizeStepItem
  | DepthStepItem
  | PaintStepItem
  | LookStepItem;

/** How a batch saves: new pictures (beside the originals, into a folder by name beside each,
 * or into a folder of their own), or in the originals' places, each original to quarantine. */
export interface BatchSaving {
  how: "new" | "replace";
  format: SaveFormat;
  quality: number | null;
  /** null: beside the originals; "Edited": a folder by that name beside each; or a path. */
  folder: string | null;
  keepCamera: boolean;
  keepColours: boolean;
  keepLocation: boolean;
}

/** Which pictures a batch is made of. */
export interface Pick {
  how: "ticked" | "folder" | "search" | "favourites" | "dropped" | "picked" | "pasted" | "opened";
  ids?: number[];
  paths?: string[];
  folder?: number | null;
  dir?: string;
  q?: string;
  /** A search: the pictures More like this found, most like this one first. */
  like?: number | null;
}

/** One of a batch's pictures. */
export interface BatchPicture {
  /** In the library; null for one outside it. */
  id: number | null;
  path: string;
  name: string;
  size: number;
  width: number;
  height: number;
  version: string;
  /** A camera RAW: its batch saves new pictures, as Mado can't write RAW. */
  raw: boolean;
}

export interface Picked {
  pictures: BatchPicture[];
  bytes: number;
  /** Where they're from: "Holiday". */
  source: string;
  /** The folder they share. */
  shared: string | null;
  /** "ticked in Holiday", "found by “beach”", "dropped from Desktop". */
  words: string;
  leftOut: BatchLeftOut[];
}

/** A picture left out, and why. */
export interface BatchLeftOut {
  name: string;
  why: string;
  /** A camera RAW, left out only till Mado's RAW reader has read it (asked again till then). */
  waiting: boolean;
}

/** A step, or a batch's save, as the steps and a recipe's line say it. */
export interface StepWords {
  kind: string;
  title: string;
  detail: string;
  chip: string;
  /** A look's strength: "60". */
  amount: string | null;
}

/** What a batch takes. */
export interface Takes {
  words: StepWords[];
  seconds: number;
  bytes: number;
  free: number | null;
  drive: string | null;
  fits: boolean;
  /** Timed on this PC, not a guess. */
  measured: boolean;
  /** Reckoned by what See it first found. */
  reckoned: boolean;
  place: "card" | "processor";
  needs: Need[];
  /** "Name (TV 8K).jpg" */
  example: string;
  /** "Holiday › Edited", "beside the originals". */
  into: string;
  madeFor: string | null;
  look: string | null;
}

export interface Sample {
  /** Its place in the batch. */
  index: number;
  name: string;
  picture: number | null;
  state: "waiting" | "making" | "done" | "failed";
  progress: number;
  seconds: number | null;
  bytes: number;
  madeBytes: number | null;
  width: number | null;
  height: number | null;
  problem: string | null;
}

/** See it first's three. */
export interface Samples {
  id: string;
  round: number;
  samples: Sample[];
  /** All of them, once made. */
  seconds: number | null;
}

export type Starts = "now" | "tonight" | "after";

/** A batch, as the queue and Home show it. */
export interface Batch {
  id: number;
  name: string;
  source: string;
  shared: string | null;
  recipe: number | null;
  /** The watch folder that made it. */
  watch: string | null;
  starts: Starts;
  addedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  /** Its pictures, those cancelled not counted. */
  total: number;
  done: number;
  failed: number;
  waiting: number;
  cancelled: number;
  progress: number;
  secondsLeft: number | null;
  seenFirst: boolean;
  how: "new" | "replace";
  /** "Holiday › Edited" */
  into: string;
  /** The folder to open, when its pictures share one. */
  folder: string | null;
  madeFor: string | null;
  look: string | null;
  /** What its size made them for: "tv". */
  purpose: string | null;
  words: StepWords[];
  /** Bytes of its pictures made, as they were and as made. */
  before: number;
  after: number;
}

/** One of a batch's pictures in the queue. */
export interface QueueRow {
  job: number;
  batch: number;
  name: string;
  path: string;
  picture: PictureRef | null;
  state: "running" | "queued" | "done" | "failed" | "cancelled";
  /** What it's at while it's made: "A look 2/3". */
  step: string | null;
  progress: number;
  bytes: number | null;
  madeBytes: number | null;
  resultName: string | null;
  problem: string | null;
  /** Why it waits: "D: isn't connected; it waits for it". */
  waits: string | null;
}

/** A drive without room for what waits on it. */
export interface Room {
  drive: string;
  /** What fits there is being made while the rest wait. */
  fit: boolean;
  free: number;
  needed: number;
  /** What's wanted there past what's free, a margin kept free. */
  more: number;
  fitting: number;
  /** Bytes its quarantine would free, emptied. */
  aside: number;
  batch: string | null;
}

export interface Queue {
  paused: boolean;
  working: boolean;
  room: Room | null;
  batch: Batch | null;
  /** Nothing waits: the batch is the latest whose pictures didn't all work, till it's cleared. */
  finished: boolean;
  rows: QueueRow[];
  waitingMore: number;
  doneMore: number;
  later: Batch[];
  night: boolean;
  /** The 07:00 that ends tonight's run. */
  morning: string;
  waitsForNight: boolean;
  secondsLeft: number | null;
}

/** The queue in a word, for the rail's badge and the status bar. */
export interface QueueNow {
  working: boolean;
  paused: boolean;
  batch: string | null;
  over: number;
  total: number;
  progress: number;
  waiting: number;
}

/** A recipe: steps kept by name. */
export interface KeptRecipe {
  id: number;
  name: string;
  steps: BatchStep[];
  saving: BatchSaving;
  words: StepWords[];
  used: number;
  usedAt: string | null;
  /** A batch of it waits for tonight. */
  tonight: boolean;
}

export interface WatchFolder {
  id: number;
  path: string;
  recipe: number;
  recipeName: string;
  results: string;
  watching: boolean;
  connected: boolean;
  /** When it last took pictures. */
  ranAt: string | null;
  /** How many its latest batch holds. */
  ranOn: number;
  /** Why its new pictures couldn't go in the queue, lately: it tries again in a few minutes. */
  problem: string | null;
}

/** A batch as History's one line for it. */
export interface BatchLine {
  id: number;
  name: string;
  source: string;
  watch: string | null;
  how: "new" | "replace";
  madeFor: string | null;
  look: string | null;
  /** "cut out the subject" */
  edit: string | null;
  /** "coloured it" */
  restore: string | null;
  /** "took out noise" */
  fix: string | null;
  /** "portrait blur at f/2.8" */
  depth: string | null;
  purpose: string | null;
  into: string;
  made: number;
  undone: number;
  failed: string[];
  overnight: boolean;
  canUndo: boolean;
  canRedo: boolean;
  /** Some of its pictures are still in the queue: it's undone as a whole once they're done. */
  working: boolean;
  drive: string | null;
  asideUntil: string | null;
  picture: PictureRef | null;
}

export interface MadeToday {
  id: number;
  name: string;
  madeFor: string | null;
  look: string | null;
  edit: string | null;
  restore: string | null;
  fix: string | null;
  depth: string | null;
}

// "/batches/done", not "/batches": that would ask again for the pictures a batch is made of.
const QUEUE = ["/queue", "/batches/done", "/jobs", "/history", "/recipes"];

/** The pictures a batch would be made of, found once. */
export const usePicked = (pick: Pick | null) =>
  useEnginePost<Picked>("/batches/pictures", pick, pick !== null, true);
/** Finds the pictures in files and folders dropped or picked, once:
 * `find.mutate({ path: "/batches/pictures", body: pick })`. */
export const useFindPictures = () => useEngineAction<Picked>([]);

/** How paths came: dropped on the window, picked, pasted (files copied in File Explorer, or a
 * path copied as words), or opened from File Explorer, Open with or the command line. */
export type OpenHow = "dropped" | "picked" | "pasted" | "opened";

/** What paths open as: one picture's page, or Many at once with them. */
export interface Opened {
  /** One picture: its page. */
  picture: PictureDetails | null;
  /** Several pictures, or a folder: Many at once, with them chosen. */
  picked: Picked | null;
  /** Beside one picture, what wasn't taken, and why. */
  leftOut: BatchLeftOut[];
}

/** Opens paths: `open.mutate({ path: "/open", body: { paths, how } })`. */
export const useOpenPaths = () => useEngineAction<Opened>([]);

/** Keeps a picture pasted from the clipboard (as the window has it, PNG) in Mado's data folder,
 * and says it as a picture outside the library. */
export function usePastePicture() {
  const engine = useEngine();
  return useMutation({
    mutationFn: (picture: Blob) => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      return callEngine<PictureDetails>(engine, "/pasted", {
        method: "POST",
        body: picture,
        headers: { "Content-Type": "image/png" },
      });
    },
  });
}

/** What a batch would take (null: nothing to make yet). */
export const useTakes = (
  ask: {
    pictures: BatchPicture[];
    steps: BatchStep[];
    saving: BatchSaving;
    shared: string | null;
    sample: string | null;
  } | null,
) => useEnginePost<Takes>("/batches/takes", ask, ask !== null && ask.steps.length > 0);

/** Asks for See it first's three: `see.mutate({ path: "/batches/samples", body })`. */
export const useSeeFirst = () => useEngineAction<Samples>([]);
/** See it first's three, asked again every second while any is being made. */
export const useSamples = (id: string | null) =>
  useEngineQuery<Samples>(
    `/batches/samples/${id ?? ""}`,
    (shown) =>
      shown?.samples.some((each) => each.state === "waiting" || each.state === "making")
        ? 1000
        : false,
    id !== null,
  );
/** Lets See it first's three go: `letGo.mutate({ path: "/batches/samples/abc" })`. */
export const useLetGo = () => useEngineAction<void>([], "DELETE");
/** Puts a batch in the queue: `queue.mutate({ path: "/batches", body })`. */
export const usePutInQueue = () => useEngineAction<Batch>(QUEUE);

/** The queue, asked again every second while it works, every five otherwise. */
export const useQueue = (all = false) =>
  useEngineQuery<Queue>(
    all ? "/queue?all=true" : "/queue",
    (queue) => (queue?.working ? 1000 : 5000),
    true,
    true,
  );
/** The queue in a word, for the rail and the status bar. */
export const useQueueNow = () =>
  useEngineQuery<QueueNow>("/queue/now", (now) => (now?.working ? 1500 : 5000));
/** Pauses, resumes, cancels, moves ticked pictures: `act.mutate({ path: "/queue/pause" })`. */
export const useQueueAction = <T = unknown>() => useEngineAction<T>([...QUEUE, "/quarantine"]);

/** Batches done that Home tells of. */
export const useDoneBatches = () => useEngineQuery<Batch[]>("/batches/done");
/** Home's card for a batch done was seen: `seen.mutate({ path: "/batches/3/seen" })`. */
export const useSeenBatch = () => useEngineAction<void>(["/batches/done"]);

export const useRecipes = () => useEngineQuery<KeptRecipe[]>("/recipes");
/** Keeps or changes a recipe: `keep.mutate({ path: "/recipes", body })`. */
export const useKeepRecipe = () => useEngineAction<KeptRecipe>(["/recipes"]);
export const useChangeRecipe = () => useEngineAction<KeptRecipe>(["/recipes"], "PUT");
export const useDeleteRecipe = () => useEngineAction<void>(["/recipes"], "DELETE");

export const useWatchFolders = () => useEngineQuery<WatchFolder[]>("/watch-folders");
/** Watches a folder: `watch.mutate({ path: "/watch-folders", body })`. */
export const useAddWatch = () => useEngineAction<WatchFolder>(["/watch-folders"]);
export const useChangeWatch = () => useEngineAction<WatchFolder>(["/watch-folders"], "PUT");
export const useStopWatching = () => useEngineAction<void>(["/watch-folders"], "DELETE");

/** Undoes a whole batch: `undo.mutate({ path: "/history/batches/3/undo" })` (or `/redo`). */
export const useBatchUndo = () =>
  useEngineAction<{ done: number; problems: string[] }>([...JOBS, "/batches/done", "/queue"]);

/** The pictures made today, for Home. */
export const useMadeToday = () => useEngineQuery<MadeToday[]>("/history/today");
/** A picture a line of History made, as a thumbnail. */
export const madeAddress = (id: number) => `/history/${id}/thumbnail`;
/** See it first's picture: a copy before or after, or as it was made, in full. */
export const sampleAddress = (set: string, index: number, side: "before" | "after" | "full") =>
  `/batches/samples/${set}/${index}/${side}`;

// Looking after the library: duplicates and bursts, pictures that won't open, room on the drives,
// and a picture open in another app.

/** One of a group's pictures. */
export interface GroupPicture {
  id: number;
  name: string;
  path: string;
  /** The folder it's in. */
  folder: string;
  width: number;
  height: number;
  size: number;
  format: string | null;
  /** Local time: "2026-11-14T10:02:14". */
  takenAt: string;
  takenFrom: "camera" | "file";
  version: string;
  /** Kept: as Mado suggests, or as the owner chose. */
  keep: boolean;
  /** The one Mado suggests keeping. */
  suggested: boolean;
  /** As it was when compared; "away" on a drive that isn't connected; gone or changed since. */
  there: "there" | "away" | "gone" | "changed";
}

/** Duplicates (one picture saved more than once) or a burst (shots of one moment). */
export interface DuplicateGroup {
  /** Its first picture's number, which names it. */
  key: number;
  kind: "duplicates" | "burst";
  /** Every one the same bytes. */
  exact: boolean;
  /** A burst's in time, else biggest first. */
  pictures: GroupPicture[];
  /** The owner chose which to keep. */
  chosen: boolean;
  /** Pictures setting it aside sets aside now, and what that frees. */
  aside: number;
  bytes: number;
  /** What decided which Mado keeps. */
  reason: "sharpest" | "pixels" | "larger" | "name" | "older";
  /** It can be set aside now. */
  ready: boolean;
  /** Why not: "F: isn't connected. Connect it to set these aside." */
  problem: string | null;
}

export interface Duplicates {
  /** Still looking: how far it's got. */
  looking: { looked: number; of: number } | null;
  /** This page. */
  groups: DuplicateGroup[];
  /** Where the next page starts; null on the last. */
  next: number | null;
  /** Groups of each kind, in all. */
  duplicates: number;
  bursts: number;
  /** What setting every group aside sets aside now, and frees. */
  pictures: number;
  bytes: number;
  /** Pictures in groups waiting for a drive to be connected. */
  away: number;
  /** The latest review, every picture of it put back. */
  putBack: { at: string; pictures: number } | null;
  /** The groups and what's kept of them as they are now: setting them all aside names it. */
  version: string;
}

/** A group as the review showed it, which setting it aside names: the engine leaves one that
 * changed since. */
export interface ShownGroup {
  key: number;
  members: number[];
  keep: number[];
}

export type DuplicateKind = "all" | "duplicates" | "bursts";

/** What setting aside did. */
export interface AsideDone {
  review: number | null;
  pictures: number;
  bytes: number;
  /** What was left as it is, and why. */
  left: { name: string; why: string }[];
}

const DUPLICATES = [
  "/duplicates",
  "/history",
  "/library",
  "/pictures",
  "/folders",
  "/quarantine",
  "/space",
];

/** The groups found, a page at a time: `fetchNextPage()` brings the next. Asked again every two
 * seconds while Mado is still looking, and now and then otherwise, for what a scan brings. */
export function useDuplicates(kind: DuplicateKind, reach: number | null = null) {
  const engine = useEngine();
  // `reach`: the first page is long enough to hold that group, as the Library's tag opens it.
  const path = `/duplicates?kind=${kind}${reach !== null ? `&reach=${reach}` : ""}`;
  return useInfiniteQuery({
    queryKey: engineKey(engine, path),
    queryFn: ({ pageParam }) => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      return callEngine<Duplicates>(engine, `${path}&offset=${pageParam}`);
    },
    initialPageParam: 0,
    getNextPageParam: (last) => last.next,
    enabled: engine.state === "ready",
    refetchInterval: (query) => (query.state.data?.pages[0]?.looking ? 2000 : 20_000),
    placeholderData: keepPreviousData,
  });
}

/** What Home tells of duplicates and bursts: the counts alone, asked again while Mado looks, and
 * now and then otherwise. */
export const useDuplicateCounts = () =>
  useEngineQuery<Duplicates>("/duplicates?limit=0", (found) => (found?.looking ? 3000 : 10_000));
/** Which of a group to keep, of its pictures as shown:
 * `keep.mutate({ path: "/duplicates/12/keep", body: { keep, members } })`. */
export const useKeep = () => useEngineAction<DuplicateGroup>(["/duplicates"], "PUT");
/** A group isn't the same: `notSame.mutate({ path: "/duplicates/12/not-same" })`. */
export const useNotSame = () => useEngineAction<void>(["/duplicates"]);
/** Sets aside the rest of groups as shown (`groups`), or of every one of a kind (`groups: null`,
 * `kind`, and the `version` the review saw). */
export const useSetAside = () => useEngineAction<AsideDone>(DUPLICATES);
/** Puts back all a review set aside: `undo.mutate({ path: "/history/reviews/3/undo" })`. */
export const useReviewUndo = () =>
  useEngineAction<{ done: number; problems: string[] }>(DUPLICATES);

/** A picture that won't open. */
export interface Unopened {
  id: number;
  name: string;
  path: string;
  folder: string;
  format: string | null;
  size: number;
  /** Why, in a sentence. */
  problem: string;
  version: string;
}

export interface WontOpen {
  /** Those not marked as damaged, newest file first. */
  pictures: Unopened[];
  /** Marked as damaged, so not listed. */
  damaged: number;
}

export const useWontOpen = (enabled = true) =>
  useEngineQuery<WontOpen>("/library/wont-open", undefined, enabled);
/** Marks one as damaged: `mark.mutate({ path: "/pictures/7/damaged" })`. */
export const useMarkDamaged = () => useEngineAction<PictureDetails>(LIBRARY);

/** Room on a drive the library uses. */
export interface DriveSpace {
  /** "D:" */
  drive: string;
  connected: boolean;
  /** Bytes; null while it isn't connected. */
  free: number | null;
  total: number | null;
  /** The library's pictures on it. */
  pictures: number;
  /** What waits in its quarantine. */
  quarantine: number;
  /** What the pictures waiting in the queue want there. */
  queue: number;
}

/** The drives the library is on, the one with the most of it first. */
export const useSpace = () => useEngineQuery<DriveSpace[]>("/space");

/** A job waiting while its picture is open in another app. */
export interface Held {
  job: number;
  name: string;
  path: string;
  /** What Mado can't do while it's open. */
  verb: "read" | "replace";
  since: string;
  /** When it tries again by itself. */
  until: string;
  batch: string | null;
}

/** The jobs waiting while their pictures are open in another app, asked again every few seconds. */
export const useHeldJobs = () =>
  useEngineQuery<Held[]>("/jobs/held", (held) => (held?.length ? 2000 : 5000));
/** Tries one again now (`/jobs/3/try-now`) or skips it (`/jobs/3/skip`). */
export const useHeldAction = () => useEngineAction<void>(["/jobs", "/queue", "/batches/done"]);

// The wallpaper studio (features/wallpaper/): the owner's monitors as Windows arranges them, the
// picture each has (or one across all), each part as it'll be made, and the daily change.

export type Layout = "each" | "across";

/** Where a monitor sits with the gap for its bezels, in pixels. */
export interface MonitorPlace {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Monitor {
  /** A short name for it that stays the same. */
  key: string;
  /** Its own name ("Studio 27"), or "Screen 2". */
  name: string;
  /** Windows' number for it. */
  number: number;
  /** In Windows' arrangement, in its pixels. */
  x: number;
  y: number;
  /** Its pixels, as it's turned. */
  width: number;
  height: number;
  /** Windows' scale for it: 1.25 for 125%. */
  scale: number;
  /** 0, 90, 180 or 270. */
  rotation: number;
  main: boolean;
  /** Where it sits with the gap for the bezels: one across all lays a picture here. */
  place: MonitorPlace;
  /** The file Windows says it shows. */
  wallpaper: string | null;
  /** That's one of Mado's wallpapers. */
  mine: boolean;
  /** Its wallpaper can be shown: the file is there. */
  shown: boolean;
  /** The wallpaper file's, which its thumbnail's address carries. */
  version: string | null;
}

export interface ChosenPicture {
  id: number;
  name: string;
  path: string;
  width: number | null;
  height: number | null;
  version: string;
  /** From outside the library. */
  outside: boolean;
  /** Where Mado found its subject, as fractions; null till it's seen. */
  focus: { x: number; y: number } | null;
}

export interface PictureChoice {
  /** Its monitor's key; null for the one across all. */
  monitor: string | null;
  picture: ChosenPicture;
  shape: Shape;
  /** The part's middle as fractions; null around its subject. */
  x: number | null;
  y: number | null;
  /** 1: the biggest part with the monitor's shape; up to 4. */
  zoom: number;
  /** Null as this PC suits. */
  quality: Quality | null;
  /** Its monitor is connected now (one across all: always). */
  connected: boolean;
  /** Why Mado can't make a wallpaper from it (it won't open), in words. */
  problem: string | null;
}

/** A part of the picture, as fractions of it: past 0 and 1 where its edges are drawn. */
export interface Area {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PartPlan {
  /** Its monitor's key. */
  monitor: string;
  picture: number;
  /** Exactly its monitor's pixels. */
  width: number;
  height: number;
  area: Area;
  /** How many times bigger it's made from the picture. */
  scale: number;
  method: "ai" | "pixels" | "smooth" | "shrink" | "keep";
  quality: Quality;
  /** "Made with the photo model, guessed from the picture." */
  how: string;
  /** What it can't make look real. */
  warning: string | null;
  /** Downloads it waits for. */
  needs: string[];
}

/** A wallpaper Mado makes, or made. */
export interface Making {
  id: number;
  purpose: "set" | "save" | "daily";
  state: "waiting" | "making" | "ready" | "set" | "saved" | "failed" | "cancelled";
  /** 0 to 1. */
  progress: number;
  /** By the pace so far; null till it's far enough along to say. */
  secondsLeft: number | null;
  problem: string | null;
  setAt: string | null;
  /** The pictures a Save wrote. */
  saved: string[];
}

export interface YourWallpaper {
  /** Its monitor's key. */
  monitor: string;
  /** The monitor's name then. */
  name: string;
  /** Their own file; null for a colour, no picture. */
  path: string | null;
  /** Their file, or Mado's copy of it, is there to put back. */
  there: boolean;
}

/** Mado's record of the owner's own wallpaper, from before it set one. */
export interface Yours {
  kept: YourWallpaper[];
  /** Windows' slideshow was on: putting back starts it again. */
  slideshow: boolean;
  /** Windows spotlight was on: only Windows turns it on again. */
  spotlight: boolean;
  /** One of Mado's wallpapers is on a monitor now. */
  showingMine: boolean;
}

export interface DailyState {
  on: boolean;
  /** "07:00" */
  at: string;
  layout: Layout;
  /** A library folder's pictures; null for the favourites. */
  folder: number | null;
  /** When it next changes the wallpaper, local time. */
  next: string | null;
  /** That change's wallpaper is made already. */
  ready: boolean;
  /** Pictures it can show. */
  candidates: number;
  /** Not there now: gone, moved since, or on a drive that isn't connected. */
  skipped: number;
  /** The day it last made its change. */
  changedOn: string | null;
  /** Why it couldn't, that day. */
  problem: string | null;
}

export interface StudioState {
  /** Windows lets Mado set wallpapers here. */
  desktop: boolean;
  /** Why Windows didn't say what monitors there are. */
  problem: string | null;
  /** The main one first. */
  monitors: Monitor[];
  /** Changes once a monitor's pixels, place or turn do. */
  arrangement: string;
  layout: Layout;
  /** Pixels left between monitors for their bezels, one across all. */
  gap: number;
  /** The monitors laid out (one across all: with the gap). */
  width: number;
  height: number;
  choices: PictureChoice[];
  parts: PartPlan[];
  /** The latest wallpaper set or saved from the studio. */
  making: Making | null;
  /** Windows' slideshow is on now: Mado's wallpaper turns it off. */
  slideshow: boolean;
  /** Windows spotlight is on now: Mado's wallpaper turns it off. */
  spotlight: boolean;
  yours: Yours;
  daily: DailyState;
  /** Bytes Mado's own wallpapers take. */
  kept: number;
}

export interface YoursBack {
  studio: StudioState;
  /** What couldn't be put back, and how the owner can. */
  told: string[];
}

const WALLPAPER = ["/wallpaper"];
const busyWallpaper = (state: StudioState | undefined) =>
  state?.making?.state === "waiting" || state?.making?.state === "making";

/** The studio, asked again every few seconds so a monitor plugged in or out, or changed, shows
 * soon; every second while a wallpaper is being made. */
export const useStudio = () =>
  useEngineQuery<StudioState>(WALLPAPER[0] ?? "/wallpaper", (state) =>
    busyWallpaper(state) ? 1000 : 4000,
  );
/** One for each or one across all, and the gap: `arrange.mutate({ path: "/wallpaper", body })`. */
export const useArrange = () => useEngineAction<StudioState>(WALLPAPER, "PUT");
/** A monitor's picture (`monitor` null: one across all), where it's cut, Fast or Best. */
export const useChooseWallpaper = () => useEngineAction<StudioState>(WALLPAPER, "PUT");
/** A monitor's picture let go: `/wallpaper/pictures?monitor=key` (none: the one across all). */
export const useLetGoOfWallpaper = () => useEngineAction<StudioState>(WALLPAPER, "DELETE");
/** Makes the parts and sets them: `/wallpaper/set`. */
export const useSetWallpaper = () => useEngineAction<StudioState>(WALLPAPER);
/** Stops the wallpaper being made to set or save: `/wallpaper/cancel`. */
export const useCancelWallpaper = () => useEngineAction<StudioState>(WALLPAPER);
/** Makes the parts and saves them as pictures: `/wallpaper/save`. */
export const useSaveWallpaper = () =>
  useEngineAction<StudioState>([...WALLPAPER, "/history", "/pictures"]);
/** The owner's own wallpaper back: `/wallpaper/put-back`, every monitor or one. */
export const usePutBack = () => useEngineAction<YoursBack>(WALLPAPER);
/** The daily change's choices: `/wallpaper/daily`. */
export const useDaily = () => useEngineAction<StudioState>(WALLPAPER, "PUT");

/** What Windows shows on a monitor now, small; its address carries the file's version. */
export const monitorWallpaperAddress = (monitor: Monitor) =>
  `/wallpaper/monitors/${monitor.key}/wallpaper?v=${encodeURIComponent(monitor.version ?? "")}`;
