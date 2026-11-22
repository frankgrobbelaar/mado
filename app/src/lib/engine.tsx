import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { createContext, type ReactNode, use, useCallback, useEffect, useState } from "react";

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

/** What the engine changes by itself: a nightly backup made, a download finished. */
const CHANGED_ON_ITS_OWN = ["/backups", "/data", "/tools"];

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
