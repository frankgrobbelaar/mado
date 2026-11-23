import { useRef, useState } from "react";
import {
  type Click,
  type Edit,
  type Part,
  type PickedPart,
  type Place,
  type Quality,
  type Tool,
  useSelect,
  useTools,
} from "@/lib/engine";

/** The biggest picture Mado edits, as the engine's editing.MOST_PIXELS: a hundred megapixels. */
export const MOST_PIXELS = 100_000_000;

/** What a picture too big to edit says, or null for one Mado edits. */
export function tooBig(picture: { width: number | null; height: number | null }): string | null {
  const pixels = (picture.width ?? 0) * (picture.height ?? 0);
  if (pixels <= MOST_PIXELS) return null;
  return `It's ${Math.round(pixels / 1e6)} megapixels, and Mado edits pictures up to ${MOST_PIXELS / 1e6}. Make a smaller copy of it on the Size tab, then edit that.`;
}

/** The downloads each tool waits for, by their ids in Mado's list of downloads. */
export const MODELS = {
  select: "sam2.1-hiera-tiny",
  fast: "mi-gan",
  best: "lama",
  cut: "birefnet-lite",
} as const;

/** The parts picked, and what the picture showed of them. */
export interface Picked {
  parts: PickedPart[];
  /** Round every part, as an SVG path in a frame 1000 square, stretched over the picture. */
  outline: string;
  /** Seconds the last reading of the picture took (the first click's). */
  read: number | null;
  /** Where it was read. */
  place: Place | null;
  /** The click that picked the last part, where its label goes. */
  last: Click | null;
  /** An Alt-click outside every part. */
  missed: boolean;
}

export const NOTHING: Picked = {
  parts: [],
  outline: "",
  read: null,
  place: null,
  last: null,
  missed: false,
};

/** What's asked of the engine: the parts so far, and a click. */
interface Ask {
  parts: PickedPart[];
  click: Click | null;
}

/** Something done to what's picked, worked out from what's picked by the time it's made: what to
 * ask, "nothing" for every part let go, or null for nothing to do. */
type Intent = (now: Picked) => Ask | "nothing" | null;

const same = (one: PickedPart, other: PickedPart) =>
  JSON.stringify(one.clicks) === JSON.stringify(other.clicks);

/** Parts as the engine takes them back. */
export function bare(parts: PickedPart[]): Part[] {
  return parts.map(({ clicks, choice }) => ({ clicks, choice }));
}

/**
 * Picking parts of a picture with clicks, on the picture as `before` (the edits so far) left it:
 * a click starts a part, an Alt-click takes from the part it's in, the last part steps between
 * SAM's three answers, a part can be let go, and Esc lets them all go. One click at a time: a
 * click, a step or a part let go while one is on its way is made in turn once it's back, on what
 * that picked, so none is lost (the first click waits for the picture to be read).
 */
export function usePicking(
  id: number,
  version: string,
  before: Edit[],
  { keyedByEdits }: { keyedByEdits: boolean },
) {
  const select = useSelect();
  // What's picked belongs to this picture as it is (and, for the Edit tab, to the edits so far:
  // an edit uses what was picked), so another picture, or another edit, starts with nothing.
  const key = `${id}|${version}${keyedByEdits ? `|${JSON.stringify(before)}` : ""}`;
  const [held, setHeld] = useState<{ key: string; picked: Picked }>({ key, picked: NOTHING });
  const picked = held.key === key ? held.picked : NOTHING;
  // What's asked for while a pick is on its way, made in turn; and whether one is on its way.
  const waiting = useRef<{ key: string; intents: Intent[] }>({ key, intents: [] });
  const busy = useRef(false);

  function send(ask: Ask, was: Picked) {
    busy.current = true;
    const asked = key;
    select.mutate(
      {
        path: `/pictures/${id}/select`,
        body: { version, edits: before, parts: bare(ask.parts), click: ask.click },
      },
      {
        onSuccess: (found) => {
          const now: Picked = {
            parts: found.parts,
            outline: found.outline,
            read: found.read ?? was.read,
            place: found.read !== null ? found.place : was.place,
            // The label goes by the click that started the last part.
            last: found.parts.at(-1)?.clicks[0] ?? null,
            missed: found.missed,
          };
          setHeld({ key: asked, picked: now });
          latest.current.next(asked, now);
        },
        onError: () => {
          busy.current = false;
          waiting.current = { key: latest.current.key, intents: [] };
        },
      },
    );
  }

  /** The next thing asked for while the last pick was on its way: made on what that picked, or,
   * once the picture or its edits changed meanwhile, on what's picked on it as it is now. Always
   * this render's, so what's asked goes with the edits as they are. */
  function next(asked: string, now: Picked) {
    const queue = waiting.current.key === key ? waiting.current.intents : [];
    let shown = asked === key ? now : picked;
    for (let intent = queue.shift(); intent; intent = queue.shift()) {
      const ask = intent(shown);
      if (ask === "nothing") {
        shown = NOTHING;
        setHeld({ key, picked: NOTHING });
      } else if (ask !== null) {
        send(ask, shown);
        return;
      }
    }
    busy.current = false;
  }

  const latest = useRef({ key, next });
  latest.current = { key, next };

  function act(intent: Intent) {
    if (busy.current) {
      if (waiting.current.key !== key) waiting.current = { key, intents: [] };
      waiting.current.intents.push(intent);
      return;
    }
    const ask = intent(picked);
    if (ask === "nothing") setHeld({ key, picked: NOTHING });
    else if (ask !== null) send(ask, picked);
  }

  return {
    picked,
    pending: select.isPending,
    problem: select.isError ? select.error.message : null,
    /** A click on the picture, as fractions of it. */
    click: (click: Click) => act((now) => ({ parts: now.parts, click })),
    /** The last part's answer one bigger (1) or smaller (-1). */
    step: (by: 1 | -1) =>
      act((now) => {
        const last = now.parts.at(-1);
        if (!last) return null;
        const choice = Math.min(Math.max(last.choice + by, 0), last.choices - 1);
        if (choice === last.choice) return null;
        return { parts: [...now.parts.slice(0, -1), { ...last, choice }], click: null };
      }),
    /** A part let go. */
    remove: (at: number) => {
      const gone = picked.parts[at];
      if (!gone) return;
      act((now) => {
        const parts = now.parts.filter((part) => !same(part, gone));
        if (parts.length === now.parts.length) return null;
        return parts.length ? { parts, click: null } : "nothing";
      });
    },
    /** Every part let go, and anything still to be asked. */
    clear: () => {
      select.reset();
      busy.current = false;
      waiting.current = { key, intents: [] };
      setHeld({ key, picked: NOTHING });
    },
    /** Parts picked elsewhere (the Edit tab's, for a look on them). */
    adopt: (from: Picked) => setHeld({ key, picked: from }),
    /** The outline again, for the picture as different edits leave it. */
    refresh: () => act((now) => (now.parts.length ? { parts: now.parts, click: null } : null)),
  };
}

/** A download a tool waits for, and how it's getting on; null once it's there. */
export function useNeed(model: string | null): Tool | null {
  const tools = useTools();
  if (model === null) return null;
  const found = tools.data?.find((each) => each.id === model);
  return found && found.state !== "ready" ? found : null;
}

/** The model an erase uses at each quality. */
export function eraseModel(quality: Quality): string {
  return quality === "best" ? MODELS.best : MODELS.fast;
}
