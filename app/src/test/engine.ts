import { vi } from "vitest";
import type {
  Backups,
  DataSizes,
  EngineStatus,
  Library,
  LibraryFolder,
  PictureItem,
  PicturePage,
  Scan,
  Settings,
} from "@/lib/engine";

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

/** Three made-up library folders, as the boards draw them. */
export const FOLDERS: LibraryFolder[] = [
  {
    id: 1,
    path: "D:\\Pictures\\Phone",
    name: "Phone",
    addedAt: "2026-11-22T09:00:00+02:00",
    available: true,
    looked: true,
    pictures: 3104,
    reading: 0,
    raw: 0,
    broken: 0,
    children: [
      { name: "2026", dir: "2026", pictures: 1840, children: [] },
      { name: "2025", dir: "2025", pictures: 1264, children: [] },
    ],
  },
  {
    id: 2,
    path: "D:\\Pictures\\Camera",
    name: "Camera",
    addedAt: "2026-11-22T09:01:00+02:00",
    available: true,
    looked: true,
    pictures: 1422,
    reading: 0,
    raw: 318,
    broken: 0,
    children: [{ name: "Trip", dir: "Trip", pictures: 400, children: [] }],
  },
  {
    id: 3,
    path: "E:\\Scans",
    name: "Scans",
    addedAt: "2026-11-22T09:02:00+02:00",
    available: true,
    looked: true,
    pictures: 286,
    reading: 0,
    raw: 0,
    broken: 9,
    children: [],
  },
];

export const LIBRARY: Library = {
  folders: 3,
  pictures: 4812,
  size: 38_200_000_000,
  reading: 0,
  raw: 318,
  broken: 9,
  parts: [
    { folderId: 1, name: "Phone", pictures: 3104 },
    { folderId: 2, name: "Camera", pictures: 1422 },
    { folderId: 3, name: "Scans", pictures: 286 },
  ],
};

/** A scan that finished today at 09:14, having found six new pictures. */
export function scanDone(overrides: Partial<Scan> = {}): Scan {
  const today = new Date();
  today.setHours(9, 14, 0, 0);
  return {
    state: "done",
    stage: "done",
    startedAt: today.toISOString(),
    finishedAt: today.toISOString(),
    found: 4812,
    toRead: 6,
    read: 6,
    current: null,
    secondsLeft: null,
    unavailable: [],
    problem: null,
    added: 6,
    gone: 0,
    ...overrides,
  };
}

/** A made-up picture in the grid. */
export function picture(
  id: number,
  name: string,
  takenAt: string,
  overrides: Partial<PictureItem> = {},
): PictureItem {
  return {
    id,
    name,
    path: `D:\\Pictures\\Phone\\${name}`,
    format: name.toUpperCase().endsWith(".HEIC") ? "HEIC" : "JPEG",
    state: "ready",
    width: 4032,
    height: 3024,
    size: 3_100_000,
    takenAt,
    version: `v${id}`,
    ...overrides,
  };
}

/** Three days of made-up pictures, newest first. */
export const PICTURES: PictureItem[] = [
  picture(11, "Harbour at dusk.heic", "2026-11-14T18:42:07"),
  picture(12, "Little sail.jpg", "2026-11-14T16:05:00"),
  picture(13, "Spring meadow.heic", "2026-11-14T11:31:00"),
  picture(21, "Snowfield.jpg", "2026-11-13T10:02:00"),
  picture(22, "Red canyon.jpg", "2026-11-13T12:30:00", {
    path: "D:\\Pictures\\Camera\\Red canyon.jpg",
  }),
  picture(31, "Green sky.CR3", "2026-11-11T23:51:00", {
    format: "CR3",
    state: "raw",
    width: null,
    height: null,
  }),
  picture(32, "Old pier.tif", "2026-11-11T13:22:00", {
    format: "TIF",
    state: "broken",
    width: null,
    height: null,
  }),
];

/** One page holding `pictures`, its days counted from them. */
export function page(
  pictures: PictureItem[],
  next: string | null = null,
  total?: number,
): PicturePage {
  const days = new Map<string, number>();
  for (const each of pictures)
    days.set(each.takenAt.slice(0, 10), (days.get(each.takenAt.slice(0, 10)) ?? 0) + 1);
  return {
    pictures,
    days: [...days].map(([day, count]) => ({ day, pictures: count })),
    total: total ?? pictures.length,
    next,
  };
}
