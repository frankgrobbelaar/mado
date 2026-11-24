import { vi } from "vitest";
import type {
  Backups,
  Batch,
  BatchPicture,
  DataSizes,
  DuplicateGroup,
  Duplicates,
  EngineStatus,
  GroupPicture,
  HistoryEntry,
  Job,
  KeptRecipe,
  Library,
  LibraryFolder,
  Looks,
  Monitor,
  PartPlan,
  Pc,
  Picked,
  PictureChoice,
  PictureDetails,
  PictureItem,
  PicturePage,
  Plan,
  Queue,
  QueueRow,
  Samples,
  Scan,
  SearchGroup,
  SearchHit,
  SearchResults,
  SearchState,
  Settings,
  Sizes,
  StepWords,
  StudioState,
  Styles,
  Takes,
  Tool,
  ToolState,
  WatchFolder,
} from "@/lib/engine";

/** Mado's camera RAW reader as the engine's downloads list it: `done` bytes of it fetched. */
export function rawReader(state: ToolState, done = 0, problem: string | null = null): Tool {
  return {
    id: "libraw",
    name: "LibRaw",
    version: "0.22.3",
    purpose: "Reads camera RAW pictures.",
    licence: "LGPL-2.1-only OR CDDL-1.0",
    size: 3_503_107,
    when: "asked",
    state,
    done: state === "ready" ? 3_503_107 : done,
    problem,
  };
}

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
  bigBatchesAtNight: false,
  wordsReader: "auto",
};

/** A data folder with a little of everything in it. */
export const DATA: DataSizes = {
  folder: "C:\\Users\\owner\\AppData\\Local\\Mado",
  database: 4 * 1024 ** 2,
  cache: 0,
  logs: 64 * 1024,
  backups: 12 * 1024 ** 2,
  tools: 168 * 1024 ** 2,
  pasted: 0,
  wallpapers: 0,
  search: 0,
};

export const NO_BACKUPS: Backups = { backups: [], restored: null };

type Answer = unknown | ((init: RequestInit | undefined, url: URL) => unknown);

/**
 * Stands in for the engine's HTTP API: `answers` maps "GET /tools" (or just "/tools" for GET) to
 * the JSON to send back, or to a function of the request (its init and address, query and all),
 * which may answer later (a promise). Anything else gets a 404.
 */
/** A moment by this PC's clock, as the engine writes one: a test reads the same hours in any
 * time zone (CI's is UTC). */
export function localTime(year: number, month: number, day: number, hours: number, minutes = 0) {
  return new Date(year, month - 1, day, hours, minutes).toISOString();
}

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
        ? await (answer as (init: RequestInit | undefined, url: URL) => unknown)(init, url)
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
  damaged: 0,
  parts: [
    { folderId: 1, name: "Phone", pictures: 3104 },
    { folderId: 2, name: "Camera", pictures: 1422 },
    { folderId: 3, name: "Scans", pictures: 286 },
  ],
  favourites: 0,
  rawWaiting: 0,
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
    raw: false,
    width: 4032,
    height: 3024,
    size: 3_100_000,
    takenAt,
    version: `v${id}`,
    group: null,
    favourite: false,
    outside: false,
    ...overrides,
  };
}

/** A picture's details, from one in the grid: in the library's Phone, unless said. */
export function pictureDetails(
  item: PictureItem,
  overrides: Partial<PictureDetails> = {},
): PictureDetails {
  return {
    ...item,
    folderId: 1,
    folder: "D:\\Pictures\\Phone",
    dir: "",
    modifiedAt: item.takenAt,
    takenFrom: "camera",
    camera: "Testcam T7 Pro",
    orientation: 1,
    located: true,
    damaged: false,
    problem: null,
    outside: false,
    pasted: false,
    aside: false,
    savesTo: null,
    ...overrides,
  };
}

/** A picture opened from outside the library: E:\Elsewhere\Pier at dawn.jpg. */
export function outsidePicture(overrides: Partial<PictureDetails> = {}): PictureDetails {
  const item = picture(42, "Pier at dawn.jpg", "2026-11-20T07:12:00", {
    path: "E:\\Elsewhere\\Pier at dawn.jpg",
  });
  return pictureDetails(item, {
    folderId: null,
    folder: "E:\\Elsewhere",
    camera: null,
    located: false,
    outside: true,
    ...overrides,
  });
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
    path: "D:\\Pictures\\Camera\\Green sky.CR3",
    format: "CR3",
    raw: true,
    width: 6000,
    height: 4000,
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
    cleanedFirst: false,
    look: null,
    edit: null,
    fix: null,
    fixQuality: null,
    fixSeconds: 0,
    fixPlace: null,
    depth: null,
    depthSeconds: 0,
    depthPlace: null,
    paintPlace: null,
    paintNote: null,
    seconds: 40,
    place: "card",
    measured: true,
    format: "JPEG",
    formatQuality: 95,
    fits: "What every TV shows.",
    colour: "sRGB",
    bytes: 18_000_000,
    seeThrough: false,
    nothingBehind: false,
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
    edit: null,
    fix: null,
    depth: null,
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
    heldUntil: null,
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
  editing: {
    select: "card",
    eraseFast: "card",
    eraseBest: "card",
    cutFast: "processor",
    cutBest: "processor",
  },
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
    edit: null,
    fix: null,
    depth: null,
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
    batch: null,
    keptName: null,
    review: null,
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

/** Mado's painting styles, as the engine lists them, and one of the owner's: a picture's style
 * kept. */
export const STYLES: Styles = {
  painters: [
    {
      id: "van-gogh",
      name: "After Van Gogh",
      kind: "painter",
      painting: "Van Gogh's The Starry Night",
      download: "style-van-gogh-starry-night",
      setting: null,
      first: 50,
    },
    {
      id: "hokusai",
      name: "After Hokusai",
      kind: "painter",
      painting: "Hokusai's The Great Wave off Kanagawa",
      download: "style-hokusai-great-wave",
      setting: null,
      first: 50,
    },
    {
      id: "monet",
      name: "After Monet",
      kind: "painter",
      painting: "Monet's Water Lilies (1915)",
      download: "style-monet-water-lilies-1915",
      setting: null,
      first: 50,
    },
    {
      id: "seurat",
      name: "After Seurat",
      kind: "painter",
      painting: "Seurat's The Channel of Gravelines",
      download: "style-seurat-gravelines",
      setting: null,
      first: 50,
    },
  ],
  classics: [
    {
      id: "pencil",
      name: "Pencil sketch",
      kind: "classic",
      painting: null,
      download: null,
      setting: "Darkness",
      first: 50,
    },
    {
      id: "coloured-pencil",
      name: "Coloured pencil",
      kind: "classic",
      painting: null,
      download: null,
      setting: "Darkness",
      first: 50,
    },
    {
      id: "oil",
      name: "Oil paint",
      kind: "classic",
      painting: null,
      download: null,
      setting: "Brush",
      first: 50,
    },
    {
      id: "cartoon",
      name: "Cartoon",
      kind: "classic",
      painting: null,
      download: null,
      setting: "Colours",
      first: 40,
    },
  ],
  yours: [
    {
      id: "yours-1",
      name: "Lantern glow",
      source: "Night market.jpg",
      addedAt: "2026-11-23T20:00:00+02:00",
    },
  ],
  reader: "microast",
};

/** A painting style's network as /tools lists it: downloaded, or not yet. */
export function styleTool(id: string, name: string, state: Tool["state"] = "ready"): Tool {
  return {
    id,
    name,
    version: "models-3",
    purpose: `A painting style for the Looks tab: repaints a picture after ${name}.`,
    licence: "MIT AND BSD-3-Clause",
    size: 6_888_971,
    when: "asked",
    state,
    done: state === "ready" ? 6_888_971 : 0,
    problem: null,
  };
}

/** One of Holiday's made-up pictures, as a batch holds it. */
export function batchPicture(id: number | null, name: string): BatchPicture {
  return {
    id,
    path: `D:\\Pictures\\Holiday\\${name}`,
    name,
    size: 2_700_000,
    width: 4032,
    height: 3024,
    version: `v${id ?? name}`,
    raw: /\.(cr3|nef|arw|dng)$/i.test(name),
  };
}

/** Holiday's pictures, ticked in the Library. */
export const PICKED: Picked = {
  pictures: [
    batchPicture(1, "Warm dunes.jpg"),
    batchPicture(2, "Still lake.heic"),
    batchPicture(3, "Night market.jpg"),
  ],
  bytes: 8_100_000,
  source: "Holiday",
  shared: "D:\\Pictures\\Holiday",
  words: "ticked in Holiday",
  leftOut: [],
};

/** Holiday prints' steps and save, in words. */
export const WORDS: StepWords[] = [
  {
    kind: "size",
    title: "Make it for a screen",
    detail: "TV 8K, 7680 × 4320, cropped around the subject; the right model for each picture",
    chip: "TV 8K",
    amount: null,
  },
  {
    kind: "look",
    title: "A look",
    detail: "Warm film at 60%, grain 20",
    chip: "Warm film",
    amount: "60",
  },
  {
    kind: "save",
    title: "Save",
    detail: "As new pictures, JPEG 95, into a folder called Edited beside each",
    chip: "JPEG 95 into Edited",
    amount: null,
  },
];

/** What Holiday prints takes. */
export function takes(overrides: Partial<Takes> = {}): Takes {
  return {
    words: WORDS,
    seconds: 1920,
    bytes: 480_000_000,
    free: 412_000_000_000,
    drive: "D:",
    fits: true,
    measured: true,
    reckoned: false,
    place: "card",
    needs: [],
    example: "Name (TV 8K, Warm film).jpg",
    into: "Holiday › Edited",
    madeFor: "TV 8K",
    look: "Warm film at 60%",
    ...overrides,
  };
}

/** See it first's three, made. */
export const SAMPLES: Samples = {
  id: "abc123",
  round: 0,
  seconds: 110,
  samples: [
    { index: 0, name: "Warm dunes.jpg", bytes: 2_700_000, madeBytes: 9_800_000 },
    { index: 1, name: "Still lake.heic", bytes: 2_900_000, madeBytes: 10_400_000 },
    { index: 2, name: "Night market.jpg", bytes: 3_300_000, madeBytes: 11_200_000 },
  ].map((each) => ({
    ...each,
    picture: each.index + 1,
    state: "done" as const,
    progress: 1,
    seconds: 36,
    width: 7680,
    height: 4320,
    problem: null,
  })),
};

/** Holiday prints, as Recipes lists it. */
export const RECIPE: KeptRecipe = {
  id: 1,
  name: "Holiday prints",
  steps: [
    { step: "size", size: "tv-8k", shape: "crop", kind: null, quality: null, clean: true },
    {
      step: "look",
      look: "warm-film",
      strength: 0.6,
      touches: { grain: 20, vignette: 0, glow: 0, fade: 0, leak: 0, dust: 0 },
    },
  ],
  saving: {
    how: "new",
    format: "JPEG",
    quality: 95,
    folder: "Edited",
    keepCamera: true,
    keepColours: true,
    keepLocation: false,
  },
  words: WORDS,
  used: 3,
  usedAt: localTime(2026, 11, 22, 23),
  tonight: true,
};

/** Holiday prints being made at night, 18 of 48 over. */
export function batch(overrides: Partial<Batch> = {}): Batch {
  return {
    id: 7,
    name: "Holiday prints",
    source: "Holiday",
    shared: "D:\\Pictures\\Holiday",
    recipe: 1,
    watch: null,
    starts: "tonight",
    addedAt: localTime(2026, 11, 22, 22, 40),
    startedAt: localTime(2026, 11, 22, 23),
    finishedAt: null,
    total: 48,
    done: 17,
    failed: 1,
    waiting: 30,
    cancelled: 0,
    progress: 0.37,
    secondsLeft: 360,
    seenFirst: true,
    how: "new",
    into: "Holiday › Edited",
    folder: "D:\\Pictures\\Holiday\\Edited",
    madeFor: "TV 8K",
    look: "Warm film at 60%",
    purpose: "tv",
    words: WORDS,
    before: 45_900_000,
    after: 166_000_000,
    ...overrides,
  };
}

function row(job: number, name: string, overrides: Partial<QueueRow>): QueueRow {
  return {
    job,
    batch: 7,
    name,
    path: `D:\\Pictures\\Holiday\\${name}`,
    picture: { id: job, version: `v${job}` },
    state: "queued",
    step: null,
    progress: 0,
    bytes: 3_800_000,
    madeBytes: null,
    resultName: null,
    problem: null,
    waits: null,
    ...overrides,
  };
}

/** The queue as the Queue board draws it. */
export function queue(overrides: Partial<Queue> = {}): Queue {
  return {
    paused: false,
    working: true,
    room: null,
    batch: batch(),
    finished: false,
    rows: [
      row(1, "Red canyon.jpg", { state: "running", step: "A look 2/3", progress: 0.6 }),
      row(2, "Misty pines.jpg", { bytes: 4_200_000 }),
      row(3, "Still lake.heic", { bytes: 2_900_000 }),
      row(4, "Old pier.tif", {
        state: "failed",
        picture: null,
        bytes: 61_000_000,
        problem: "The file is damaged, so it was left as it is.",
      }),
      row(5, "Warm dunes.jpg", {
        state: "done",
        bytes: 2_700_000,
        madeBytes: 9_800_000,
        resultName: "Warm dunes (TV 8K).jpg",
      }),
    ],
    waitingMore: 28,
    doneMore: 14,
    later: [],
    night: true,
    morning: "2026-11-23T07:00",
    waitsForNight: false,
    secondsLeft: 360,
    ...overrides,
  };
}

/** Watch folders, as the Recipes board draws them. */
export const WATCH_FOLDERS: WatchFolder[] = [
  {
    id: 1,
    path: "D:\\Pictures\\To TV",
    recipe: 1,
    recipeName: "Holiday prints",
    results: "D:\\Pictures\\To TV\\Done",
    watching: true,
    connected: true,
    ranAt: new Date(new Date().setHours(14, 2, 0, 0)).toISOString(),
    ranOn: 6,
    problem: null,
  },
  {
    id: 2,
    path: "F:\\Phone dump",
    recipe: 1,
    recipeName: "Holiday prints",
    results: "F:\\Wallpapers",
    watching: true,
    connected: false,
    ranAt: null,
    ranOn: 0,
    problem: null,
  },
  {
    id: 3,
    path: "E:\\Scans\\New",
    recipe: 1,
    recipeName: "Holiday prints",
    results: "E:\\Prints",
    watching: false,
    connected: true,
    ranAt: null,
    ranOn: 0,
    problem: null,
  },
];

/** One of a group's made-up pictures. */
export function groupPicture(
  id: number,
  name: string,
  overrides: Partial<GroupPicture> = {},
): GroupPicture {
  return {
    id,
    name,
    path: `D:\\Pictures\\Phone\\2026\\${name}`,
    folder: "D:\\Pictures\\Phone\\2026",
    width: 4032,
    height: 3024,
    size: 3_200_000,
    format: "JPEG",
    takenAt: "2026-11-14T10:02:14",
    takenFrom: "camera",
    version: `v${id}`,
    keep: false,
    suggested: false,
    there: "there",
    ...overrides,
  };
}

/** A burst of three shots on Snowfield, the sharp one kept. */
export function burstGroup(overrides: Partial<DuplicateGroup> = {}): DuplicateGroup {
  return {
    key: 41,
    kind: "burst",
    exact: false,
    pictures: [
      groupPicture(41, "IMG_2041.jpg", { takenAt: "2026-11-14T10:02:14" }),
      groupPicture(42, "IMG_2042.jpg", {
        takenAt: "2026-11-14T10:02:15",
        keep: true,
        suggested: true,
      }),
      groupPicture(43, "IMG_2043.jpg", { takenAt: "2026-11-14T10:02:16" }),
    ],
    chosen: false,
    reason: "sharpest",
    aside: 2,
    bytes: 6_400_000,
    ready: true,
    problem: null,
    ...overrides,
  };
}

/** Harbour at dusk saved twice: the biggest kept. */
export function copiesGroup(overrides: Partial<DuplicateGroup> = {}): DuplicateGroup {
  return {
    key: 11,
    kind: "duplicates",
    exact: false,
    pictures: [
      groupPicture(11, "Harbour at dusk.jpg", {
        keep: true,
        suggested: true,
        takenAt: "2026-11-12T18:42:07",
      }),
      groupPicture(12, "Harbour at dusk small.jpg", {
        path: "D:\\Pictures\\Shared\\Harbour at dusk small.jpg",
        folder: "D:\\Pictures\\Shared",
        width: 2016,
        height: 1512,
        size: 900_000,
        takenAt: "2026-11-12T18:42:07",
      }),
    ],
    chosen: false,
    reason: "pixels",
    aside: 1,
    bytes: 900_000,
    ready: true,
    problem: null,
    ...overrides,
  };
}

/** The review: a burst and a pair of copies, done looking. */
export function duplicates(overrides: Partial<Duplicates> = {}): Duplicates {
  return {
    looking: null,
    groups: [burstGroup(), copiesGroup()],
    next: null,
    duplicates: 1,
    bursts: 1,
    pictures: 3,
    bytes: 7_300_000,
    away: 0,
    putBack: null,
    version: "found-1",
    ...overrides,
  };
}

/** A made-up monitor, as Windows arranges it. */
export function monitor(overrides: Partial<Monitor> = {}): Monitor {
  const width = overrides.width ?? 2560;
  const height = overrides.height ?? 1440;
  const x = overrides.x ?? 0;
  const y = overrides.y ?? 0;
  return {
    key: "studio27",
    name: "Studio 27",
    number: 1,
    x,
    y,
    width,
    height,
    scale: 1.25,
    rotation: 0,
    main: true,
    place: { x, y, width, height },
    wallpaper: "C:\\Users\\owner\\Pictures\\Beach.jpg",
    mine: false,
    shown: true,
    version: "w1",
    ...overrides,
  };
}

/** The second monitor, beside the first. */
export const SIDE: Monitor = monitor({
  key: "side24",
  name: "Side 24",
  number: 2,
  x: 2560,
  width: 1920,
  height: 1080,
  scale: 1,
  main: false,
  wallpaper: "C:\\Users\\owner\\Pictures\\Dunes.png",
  version: "w2",
});

/** A picture chosen for a monitor in the studio. */
export function choice(overrides: Partial<PictureChoice> = {}): PictureChoice {
  return {
    monitor: "studio27",
    picture: {
      id: 11,
      name: "Harbour at dusk.jpg",
      path: "D:\\Pictures\\Phone\\Harbour at dusk.jpg",
      width: 4032,
      height: 3024,
      version: "v11",
      outside: false,
      focus: { x: 0.5, y: 0.45 },
    },
    shape: "crop",
    x: null,
    y: null,
    zoom: 1,
    quality: null,
    connected: true,
    problem: null,
    ...overrides,
  };
}

/** A part as the engine will make it. */
export function part(overrides: Partial<PartPlan> = {}): PartPlan {
  return {
    monitor: "studio27",
    picture: 11,
    width: 2560,
    height: 1440,
    area: { x: 0, y: 0.1, width: 1, height: 0.75 },
    scale: 0.635,
    method: "shrink",
    quality: "fast",
    how: "It's already big enough, so Mado only makes it smaller, sharply.",
    warning: null,
    needs: [],
    ...overrides,
  };
}

/** The studio with two monitors side by side, nothing chosen yet. */
export function studio(overrides: Partial<StudioState> = {}): StudioState {
  return {
    desktop: true,
    problem: null,
    monitors: [monitor(), SIDE],
    arrangement: "a1",
    layout: "each",
    gap: 0,
    width: 4480,
    height: 1440,
    choices: [],
    parts: [],
    making: null,
    slideshow: false,
    spotlight: false,
    yours: { kept: [], slideshow: false, spotlight: false, showingMine: false },
    daily: {
      on: false,
      at: "07:00",
      layout: "each",
      folder: null,
      next: null,
      ready: false,
      candidates: 0,
      skipped: 0,
      changedOn: null,
      problem: null,
    },
    kept: 0,
    ...overrides,
  };
}

/** A model search downloads, as the engine's list of downloads says it. */
export function searchModel(
  id: "siglip-base-patch16-224" | "pp-ocrv6-small",
  overrides: Partial<Tool> = {},
): Tool {
  const siglip = id === "siglip-base-patch16-224";
  return {
    id,
    name: siglip ? "SigLIP base" : "PP-OCRv6 small",
    version: "models-3",
    purpose: siglip ? "Reads what each picture shows." : "Reads the words in pictures at Best.",
    licence: "Apache-2.0",
    size: siglip ? 207_491_162 : 31_195_173,
    when: "asked",
    state: "ready",
    done: siglip ? 207_491_162 : 31_195_173,
    problem: null,
    ...overrides,
  };
}

/** Reading the library for search, all done on a PC whose card reads words at Best. */
export function searchState(overrides: Partial<SearchState> = {}): SearchState {
  return {
    read: 4812,
    of: 4812,
    reading: false,
    paused: false,
    busy: false,
    failed: 0,
    problem: null,
    describer: searchModel("siglip-base-patch16-224"),
    words: {
      chosen: "auto",
      reader: "best",
      model: searchModel("pp-ocrv6-small"),
      languages: ["en-GB"],
      place: "card",
    },
    ...overrides,
  };
}

/** A picture a search found: as it is in the grid, with how it was found. */
export function hit(item: PictureItem, overrides: Partial<SearchHit> = {}): SearchHit {
  return { ...item, score: null, words: null, away: false, ...overrides };
}

/** What a search found: its groups, each picture once. */
export function searchResults(
  search: string,
  groups: SearchGroup[],
  overrides: Partial<SearchResults> = {},
): SearchResults {
  return {
    search,
    groups,
    total: groups.reduce((sum, group) => sum + group.pictures.length, 0),
    english: true,
    unreadable: null,
    state: searchState(),
    ...overrides,
  };
}
