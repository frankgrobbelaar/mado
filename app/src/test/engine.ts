import { vi } from "vitest";
import type {
  Backups,
  DataSizes,
  EngineStatus,
  HistoryEntry,
  Job,
  Library,
  LibraryFolder,
  Looks,
  Pc,
  PictureItem,
  PicturePage,
  Plan,
  Scan,
  Settings,
  Sizes,
} from "@/lib/engine";

/** The engine as tests see it: ready, on a made-up address. */
export const READY: EngineStatus = {
  state: "ready",
  url: "http://127.0.0.1:5000",
  token: "secret",
};

export const SETTINGS: Settings = {
  setUp: true,
  saveFirst: "new",
  newPictures: "beside",
  newFolder: null,
  keepLocation: false,
};

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

/** The sizes the Size tab offers, as the engine lists them. */
export const SIZES: Sizes = {
  screens: [
    {
      id: "phone",
      name: "Phone",
      width: 1290,
      height: 2796,
      group: "screens",
      purpose: "phone",
      label: "Phone",
    },
    {
      id: "tablet",
      name: "Tablet",
      width: 2048,
      height: 2732,
      group: "screens",
      purpose: "tablet",
      label: "Tablet",
    },
    {
      id: "laptop",
      name: "Laptop",
      width: 2560,
      height: 1600,
      group: "screens",
      purpose: "laptop",
      label: "Laptop",
    },
    {
      id: "monitor-4k",
      name: "Monitor 4K",
      width: 3840,
      height: 2160,
      group: "screens",
      purpose: "monitor",
      label: "Monitor 4K",
    },
    {
      id: "ultrawide",
      name: "Ultrawide",
      width: 3440,
      height: 1440,
      group: "screens",
      purpose: "ultrawide",
      label: "Ultrawide",
    },
    {
      id: "tv-8k",
      name: "TV 8K",
      width: 7680,
      height: 4320,
      group: "screens",
      purpose: "tv",
      label: "TV 8K",
    },
  ],
  yours: [
    {
      id: "yours-3440x1440",
      name: "Main screen",
      width: 3440,
      height: 1440,
      group: "yours",
      purpose: "screen",
      label: "3440 × 1440",
    },
  ],
  prints: [
    {
      id: "print-10x15",
      name: "10 × 15 cm",
      width: 1181,
      height: 1772,
      group: "prints",
      purpose: "print",
      label: "10 × 15 cm print",
    },
    {
      id: "print-a4",
      name: "A4",
      width: 2480,
      height: 3508,
      group: "prints",
      purpose: "print",
      label: "A4 print",
    },
    {
      id: "print-a3",
      name: "A3",
      width: 3508,
      height: 4961,
      group: "prints",
      purpose: "print",
      label: "A3 print",
    },
  ],
};

/** A 4:3 photo made for TV 8K: cropped around what Mado found, with the photo model. */
export function plan(overrides: Partial<Plan> = {}): Plan {
  return {
    width: 7680,
    height: 4320,
    label: "TV 8K",
    shape: "crop",
    sides: "top and bottom",
    kept: { x: 0, y: 0.125, width: 1, height: 0.75 },
    canvas: { x: 0, y: 0.125, width: 1, height: 0.75 },
    focus: [0.5, 0.45],
    focusFound: true,
    note: "A TV is 16:9 and this picture is 4:3, so a little of the top and bottom goes.",
    kind: "photo",
    kindGuessed: true,
    quality: "fast",
    method: "ai",
    model: "Real-ESRGAN general",
    how: "Made with the photo model, guessed from the picture.",
    warning: null,
    cleanMatters: true,
    look: null,
    seconds: 40,
    place: "card",
    measured: true,
    format: "JPEG",
    formatQuality: 95,
    fits: "What every TV shows.",
    colour: "sRGB",
    bytes: 18_000_000,
    seeThrough: false,
    needs: [],
    ...overrides,
  };
}

/** A job making Harbour at dusk for TV 8K. */
export function job(overrides: Partial<Job> = {}): Job {
  return {
    id: 7,
    pictureId: 11,
    name: "Harbour at dusk.heic",
    madeFor: "TV 8K",
    look: null,
    how: "new",
    state: "running",
    stage: "making",
    progress: 0.37,
    secondsLeft: 25,
    queuedAt: new Date().toISOString(),
    startedAt: new Date().toISOString(),
    finishedAt: null,
    result: null,
    resultName: null,
    resultPicture: null,
    problem: null,
    ...overrides,
  };
}

/** This PC: the owner's, as the boards draw it. */
export const PC: Pc = {
  card: {
    name: "NVIDIA GeForce GTX 1660 SUPER",
    maker: "nvidia",
    memory: 6 * 1024 ** 3,
    integrated: false,
    driver: "617.42",
  },
  processor: "Intel Core i5-9600K",
  cores: 6,
  memory: 24 * 1024 ** 3,
  checkedAt: "2026-11-22T09:30:00+02:00",
  onCard: true,
  problem: null,
  place: "card",
  testing: false,
  timing: false,
  measured: { at: "2026-11-22T09:30:00+02:00", tested: true, pictures: 3 },
  startsOn: { photo: "best", drawing: "best" },
  abilities: [
    {
      kind: "photo",
      quality: "fast",
      model: "Real-ESRGAN general",
      pace: "ready",
      seconds: 6,
      download: false,
    },
    {
      kind: "photo",
      quality: "best",
      model: "RealESRGAN x4plus",
      pace: "ready",
      seconds: 68,
      download: true,
    },
    {
      kind: "drawing",
      quality: "fast",
      model: "Real-ESRGAN general",
      pace: "ready",
      seconds: 6,
      download: false,
    },
    {
      kind: "drawing",
      quality: "best",
      model: "RealESRGAN x4plus for drawings",
      pace: "ready",
      seconds: 23,
      download: false,
    },
  ],
};

/** A line of History: a picture made beside its original, today at 14:02. */
export function entry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  const today = new Date();
  today.setHours(14, 2, 0, 0);
  return {
    id: 1,
    at: today.toISOString(),
    kind: "made",
    name: "Harbour at dusk.heic",
    madeFor: "TV 8K",
    look: null,
    original: "D:\\Pictures\\Phone\\Harbour at dusk.heic",
    result: "D:\\Pictures\\Phone\\Harbour at dusk (TV 8K).jpg",
    resultName: "Harbour at dusk (TV 8K).jpg",
    aside: null,
    asideUntil: null,
    clearedAt: null,
    clearedBy: null,
    undoneAt: null,
    bytes: null,
    picture: null,
    canUndo: true,
    canRedo: false,
    ...overrides,
  };
}

/** Mado's looks, as the engine lists them, and one of the owner's: a mix kept. */
export const LOOKS: Looks = {
  looks: [
    { id: "original", name: "Original", version: "00000000" },
    { id: "warm-film", name: "Warm film", version: "1a2b3c4d" },
    { id: "cool-film", name: "Cool film", version: "2b3c4d5e" },
    { id: "faded", name: "Faded", version: "3c4d5e6f" },
    { id: "teal-and-orange", name: "Teal and orange", version: "4d5e6f70" },
    { id: "silver", name: "Silver", version: "5e6f7081" },
    { id: "golden-hour", name: "Golden hour", version: "6f708192" },
    { id: "night-neon", name: "Night neon", version: "708192a3" },
    { id: "duotone", name: "Duotone", version: "8192a3b4" },
  ],
  yours: [
    {
      id: "yours-1",
      name: "Holiday warm",
      kind: "mix",
      points: 33,
      touches: { grain: 20, vignette: 35, glow: 0, fade: 0, leak: 0, dust: 0 },
      source: "Warm film at 60%, grain 20, vignette 35",
      addedAt: "2026-11-20T19:00:00+02:00",
    },
  ],
};
