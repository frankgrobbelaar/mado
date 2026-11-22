import { vi } from "vitest";
import type { Backups, DataSizes, EngineStatus, Settings } from "@/lib/engine";

/** The engine as tests see it: ready, on a made-up address. */
export const READY: EngineStatus = {
  state: "ready",
  url: "http://127.0.0.1:5000",
  token: "secret",
};

export const SETTINGS: Settings = { setUp: true };

/** A data folder with a little of everything in it. */
export const DATA: DataSizes = {
  folder: "C:\\Users\\owner\\AppData\\Local\\Mado",
  database: 4 * 1024 ** 2,
  cache: 0,
  logs: 64 * 1024,
  backups: 12 * 1024 ** 2,
  tools: 168 * 1024 ** 2,
};

export const NO_BACKUPS: Backups = { backups: [], restored: null };

type Answer = unknown | ((init: RequestInit | undefined, url: URL) => unknown);

/**
 * Stands in for the engine's HTTP API: `answers` maps "GET /tools" (or just "/tools" for GET) to
 * the JSON to send back, or to a function of the request (its init and address, query and all).
 * Anything else gets a 404.
 */
export function fakeEngine(answers: Record<string, Answer>) {
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    const method = init?.method ?? "GET";
    // An answer of null is a 204, so it's looked for by its key: `??` would pass it over.
    const asked = `${method} ${url.pathname}`;
    const key = asked in answers ? asked : method === "GET" ? url.pathname : null;
    const answer = key !== null && key in answers ? answers[key] : undefined;
    if (answer === undefined) return Response.json({ detail: "Not found" }, { status: 404 });
    const body =
      typeof answer === "function"
        ? (answer as (init: RequestInit | undefined, url: URL) => unknown)(init, url)
        : answer;
    if (body instanceof Response) return body;
    return body === null ? new Response(null, { status: 204 }) : Response.json(body);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
