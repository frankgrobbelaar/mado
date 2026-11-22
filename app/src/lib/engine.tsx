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
}

/** One picture, one recipe: what the Size and Looks tabs set together, made by one Save. */
export interface Recipe {
  size: SizeStep | null;
  look: LookStep | null;
}

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
  /** The look, as Save says it after "with": "Warm film at 60%"; null with no look. */
  look: string | null;
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
  how: "new" | "replace";
  state: JobState;
  stage: "reading" | "shaping" | "making" | "looking" | "saving" | null;
  /** 0 to 1. */
  progress: number;
  secondsLeft: number | null;
  queuedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  result: string | null;
  resultName: string | null;
  resultPicture: PictureRef | null;
  problem: string | null;
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
  kind: "made" | "replaced" | "emptied";
  /** The original's file name; the drive, for a quarantine emptied. */
  name: string;
  /** What its size made it for: "TV 8K". */
  madeFor: string | null;
  /** What it was made with: "Warm film at 60%". */
  look: string | null;
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
}

export interface HistoryPage {
  entries: HistoryEntry[];
  /** The day the next page starts before; null: that's all. */
  older: string | null;
  /** The batches its lines were made in. */
  batches: BatchLine[];
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
export const useHistoryAction = () => useEngineAction<HistoryEntry>(JOBS);
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
}

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

/** A batch's step. Later pieces add kinds of their own. */
export type BatchStep = SizeStepItem | LookStepItem;

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
  how: "ticked" | "folder" | "search" | "dropped" | "picked";
  ids?: number[];
  paths?: string[];
  folder?: number | null;
  dir?: string;
  q?: string;
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
  leftOut: { name: string; why: string }[];
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
}

// "/batches/done", not "/batches": that would ask again for the pictures a batch is made of.
const QUEUE = ["/queue", "/batches/done", "/jobs", "/history", "/recipes"];

/** The pictures a batch would be made of, found once. */
export const usePicked = (pick: Pick | null) =>
  useEnginePost<Picked>("/batches/pictures", pick, pick !== null, true);
/** Finds the pictures in files and folders dropped or picked, once:
 * `find.mutate({ path: "/batches/pictures", body: pick })`. */
export const useFindPictures = () => useEngineAction<Picked>([]);

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
