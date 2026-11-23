import { ClipboardPaste, ImageOff, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { type OpeningNote, useOpenPictures } from "@/features/batch/open";
import { useDroppedFiles } from "@/lib/drop";
import { type OpenHow, pageOf, useEngine, usePastePicture } from "@/lib/engine";
import { clipboardFiles, onOpened, takeOpened } from "@/lib/opened";

// Past 2^26 pixels (256 MiB of them) the window's own clipboard gives a page an empty picture: so
// that's as big as a paste can be (measured, docs/stack/tauri.md, "Paste").
const TOO_BIG: OpeningNote = {
  title: "Nothing pasted",
  body: "That picture is too big to paste: Mado takes pictures up to 67 megapixels from the clipboard. Save it as a file, then open that.",
};

const NOTHING: OpeningNote = {
  title: "Nothing to paste",
  body: "There's no picture on the clipboard. Copy a picture, or pictures and folders in File Explorer, then press Ctrl+V.",
};

/**
 * Pictures from anywhere, wherever the window is: dropped on it (while they're over it, it says
 * what dropping does), pasted with Ctrl+V (anywhere but a text field, which pastes words as usual,
 * or a card over the page:
 * files copied in File Explorer as if dropped, a picture on the clipboard kept in Mado's data
 * folder and opened, a path copied as words opened), and handed over by Windows (File Explorer's
 * "Open in Mado", Open with, the command line), taken once the engine is ready. One picture opens
 * its page; several, or a folder, Many at once. `onNote` shows what was left out, or why nothing
 * opened, at the window's foot.
 */
export function Opening({ onNote }: { onNote: (note: OpeningNote | null) => void }) {
  const opening = useOpenPictures();
  const { open, note } = opening;
  const { over } = useDroppedFiles((paths) => open(paths, "dropped"));
  const pasting = usePastePicture();
  const navigate = useNavigate();
  const here = useLocation().pathname;
  const engine = useEngine();
  const ready = engine.state === "ready";
  const told = useRef(onNote);
  told.current = onNote;
  const latest = useRef({ open, paste: pasting.mutate, navigate, here });
  latest.current = { open, paste: pasting.mutate, navigate, here };

  useEffect(() => {
    told.current(note);
  }, [note]);

  // Ctrl+V anywhere in the window, but in a text field.
  useEffect(() => {
    function pasted(event: ClipboardEvent) {
      if (event.defaultPrevented || typing(event.target)) return;
      const data = event.clipboardData;
      const item = data
        ? [...data.items].find((each) => each.kind === "file" && each.type.startsWith("image/"))
        : undefined;
      const picture = item?.getAsFile() ?? null; // only while the event lasts
      const words = data?.getData("text/plain") ?? "";
      event.preventDefault();
      void pasteFrom(picture, words);
    }
    async function pasteFrom(picture: File | null, words: string) {
      const { open, paste, navigate, here } = latest.current;
      told.current(null);
      const files = await Promise.resolve()
        .then(clipboardFiles)
        .catch(() => null);
      if (files?.length) return open(files, "pasted" satisfies OpenHow);
      if (picture?.size === 0) return told.current(TOO_BIG);
      if (picture) {
        told.current({
          title: "Pasting the picture…",
          body: "Mado keeps it in its own folder, not yours, till you save it.",
          busy: true,
        });
        return paste(picture, {
          onSuccess: (made) => {
            told.current(null);
            const page = pageOf(made);
            void navigate(page, { replace: page === here });
          },
          onError: (error) => told.current({ title: "Nothing pasted", body: error.message }),
        });
      }
      const paths = pathsIn(words);
      if (paths.length) return open(paths, "pasted");
      told.current(NOTHING);
    }
    document.addEventListener("paste", pasted);
    return () => document.removeEventListener("paste", pasted);
  }, []);

  // What Windows handed over: taken once the engine is ready, and again whenever more is ready.
  useEffect(() => {
    if (!ready) return;
    let stop: (() => void) | null = null;
    let gone = false;
    const take = () => {
      Promise.resolve()
        .then(takeOpened)
        .then((choices) => {
          for (const paths of choices ?? []) latest.current.open(paths, "opened");
        })
        .catch(() => {
          // outside Mado's window (a test, a browser): nothing is handed over
        });
    };
    onOpened(take)
      .then((unlisten) => {
        if (gone) unlisten();
        else stop = unlisten;
      })
      .catch(() => {
        // the window went before it listened
      });
    take();
    return () => {
      gone = true;
      stop?.();
    };
  }, [ready]);

  return over ? (
    <div
      role="status"
      className="pointer-events-none fixed inset-3 z-50 flex animate-fade-in flex-col items-center justify-center gap-3 rounded-10 border-2 border-dash border-dashed bg-window/85"
    >
      <span className="flex size-14 items-center justify-center rounded-10 bg-raised">
        <Upload size={22} strokeWidth={1.7} aria-hidden="true" />
      </span>
      <span className="font-semibold text-20">Drop them here</span>
      <span className="text-14 text-fg-muted">
        One picture opens its page; several, or a folder, open Many at once.
      </span>
    </div>
  ) : null;
}

const SHOWN_FOR = 12_000; // milliseconds a note stays, unless it's pointed at or focused

/** A note at the window's foot about what was opened, as the small things board draws them:
 * what was left out, or why nothing opened. It goes after a while, or when dismissed. */
export function OpeningNotice({ note, onClose }: { note: OpeningNote; onClose: () => void }) {
  const [held, setHeld] = useState(false);
  const busy = note.busy === true;
  useEffect(() => {
    if (held || busy) return;
    const timer = setTimeout(onClose, SHOWN_FOR);
    return () => clearTimeout(timer);
  }, [held, busy, onClose]);
  const words = (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="font-semibold text-15 [overflow-wrap:anywhere]">{note.title}</span>
      <span className="text-13 text-fg-muted leading-normal [overflow-wrap:anywhere]">
        {note.body}
      </span>
    </span>
  );
  if (busy) {
    // Under way: it stays till it's done.
    return (
      <div role="status" className={NOTE}>
        <ClipboardPaste size={22} strokeWidth={1.6} aria-hidden="true" className="shrink-0" />
        {words}
      </div>
    );
  }
  return (
    <div
      role="alert"
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
      className={NOTE}
    >
      <ImageOff size={22} strokeWidth={1.6} aria-hidden="true" className="shrink-0" />
      {words}
      <button
        type="button"
        aria-label="Close the note"
        onClick={onClose}
        className="press inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-6 text-fg-muted hover:bg-tint/6 hover:text-fg"
      >
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

const NOTE =
  "flex animate-pop items-center gap-x-4 gap-y-3 rounded-8 border border-field-edge bg-raised px-4 py-3.5 text-fg shadow-toast";

/** Whether a paste goes to a text field, which pastes words as usual, or to a card over the page,
 * which is what's in front. */
function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.closest("[role='dialog'], [role='alertdialog']")) return true;
  if (target.isContentEditable || target instanceof HTMLTextAreaElement) return true;
  return target instanceof HTMLInputElement && WORDS.has(target.type);
}

const WORDS = new Set(["text", "search", "url", "email", "tel", "password", "number"]);

/** The paths in words pasted: each line a whole path (a drive's, a network share's, or a
 * file:/// address), quoted or not, as File Explorer's "Copy as path" puts them; none when any
 * line is something else. */
export function pathsIn(words: string): string[] {
  const lines = words
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^"(.*)"$/, "$1"))
    .filter(Boolean);
  const paths = lines.map(pathOf);
  return paths.length && paths.every((path) => path !== null) ? (paths as string[]) : [];
}

function pathOf(line: string): string | null {
  if (/^[a-zA-Z]:[\\/]/.test(line) || /^\\\\[^\\/]+[\\/]/.test(line)) return line;
  if (/^file:\/\//i.test(line)) {
    try {
      const url = new URL(line);
      const path = decodeURIComponent(url.pathname).replace(/^\/([a-zA-Z]:)/, "$1");
      const found = url.host ? `\\\\${url.host}${path}` : path;
      return found.replaceAll("/", "\\");
    } catch {
      return null;
    }
  }
  return null;
}
