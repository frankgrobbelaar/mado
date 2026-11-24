/** How Mado writes sizes, times and file names, on every screen. */

/** A path's file name and its folder. */
export function split(path: string): [string, string] {
  const at = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return [path.slice(at + 1), path.slice(0, at)];
}

/** When a backup was made, as the owner reads it: "today 03:00", "yesterday 03:00", "11 October 03:00". */
export function madeAt(made: string): string {
  const moment = new Date(made);
  if (Number.isNaN(moment.getTime())) return "a backup Mado no longer has";
  return dayAndTime(moment);
}

/** A moment as the owner reads it: "today 03:00", "yesterday 03:00", "11 October 03:00". */
export function dayAndTime(moment: Date): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const time = moment.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  if (moment.toDateString() === today.toDateString()) return `today ${time}`;
  if (moment.toDateString() === yesterday.toDateString()) return `yesterday ${time}`;
  return `${moment.toLocaleDateString("en-GB", { day: "numeric", month: "long" })} ${time}`;
}

/** Sizes as the boards write them: "3.1 MB" and "38.2 GB" with a tenth under a hundred, "233 MB"
 * and "412 GB" whole above it, "320 KB" under a million bytes; a whole number keeps no ".0". */
export function size(bytes: number): string {
  if (bytes >= 1e12) return `${tenths(bytes / 1e12)} TB`;
  if (bytes >= 1e11) return `${Math.round(bytes / 1e9)} GB`;
  if (bytes >= 1e9) return `${tenths(bytes / 1e9)} GB`;
  if (bytes >= 1e8) return `${Math.round(bytes / 1e6)} MB`;
  if (bytes >= 1e6) return `${tenths(bytes / 1e6)} MB`;
  return `${bytes > 0 ? Math.max(1, Math.round(bytes / 1e3)) : 0} KB`;
}

function tenths(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "");
}

/** A count with its thousands marked, as the boards write it: "4,812". */
export function count(n: number): string {
  return n.toLocaleString("en-GB");
}

/** "1 picture", "3,104 pictures". */
export function pictures(n: number): string {
  return `${count(n)} ${n === 1 ? "picture" : "pictures"}`;
}

/** A day's heading in the grid: "Saturday 14 November", with its year when it isn't this one. */
export function dayHeading(day: string, now = new Date()): string {
  const moment = new Date(`${day}T00:00:00`); // local midnight: "2026-11-14" alone means UTC
  if (Number.isNaN(moment.getTime())) return day;
  const weekday = moment.toLocaleDateString("en-GB", { weekday: "long" });
  const month = moment.toLocaleDateString("en-GB", { month: "long" });
  const year = moment.getFullYear() === now.getFullYear() ? "" : ` ${moment.getFullYear()}`;
  return `${weekday} ${moment.getDate()} ${month}${year}`;
}

/** When on its day a picture was taken: "18:42", from "2026-11-12T18:42:07". */
export function clock(takenAt: string): string {
  return takenAt.slice(11, 16);
}

/** When a picture was taken, in full: "12 Nov 2026, 18:42". */
export function takenOn(takenAt: string): string {
  const moment = new Date(takenAt);
  if (Number.isNaN(moment.getTime())) return takenAt;
  const date = moment.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `${date}, ${clock(takenAt)}`;
}

/** What's left, the way a person says it: "about 40 s", "about 3 min", "about 1 h 20 min". */
export function about(seconds: number): string {
  if (seconds < 60) return `about ${Math.max(5, Math.round(seconds / 5) * 5)} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `about ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `about ${hours} h ${rest} min` : `about ${hours} h`;
}

/** What a picture was made for and with, after its name: "for TV 8K", "with Warm film at 60%",
 * "for TV 8K, with portrait blur at f/2.8 and Warm film at 60%"; a 3D photo, "into a 3D photo,
 * swaying for 5 s". */
export function madeWith(made: {
  madeFor: string | null;
  look: string | null;
  edit?: string | null;
  restore?: string | null;
  fix?: string | null;
  depth?: string | null;
}): string {
  if (made.depth?.startsWith(MOTION_WORDS)) return made.depth;
  const withs = [made.depth, made.look].filter(Boolean).join(" and ");
  const parts = [made.madeFor ? `for ${made.madeFor}` : null, withs ? `with ${withs}` : null];
  const said = parts.filter(Boolean).join(", ");
  // The edits, restoring and fixes, made first, come after in brackets: "for TV 8K (erased a
  // part; coloured it; took out noise)".
  const first = [made.edit, made.restore, made.fix].filter(Boolean).join("; ");
  return first ? `${said} (${first})`.trimStart() : said;
}

/** The same as a version of it is called: "TV 8K", "Warm film at 60%", "TV 8K, Warm film at 60%";
 * "edited" for one only edited, "restored" for one only restored, "fixed" for one only fixed, its
 * depth tools' name for one given only those ("Portrait blur"). */
export function versionOf(made: {
  madeFor: string | null;
  look: string | null;
  edit?: string | null;
  restore?: string | null;
  fix?: string | null;
  depth?: string | null;
}): string {
  return (
    [made.madeFor, made.look].filter(Boolean).join(", ") ||
    (made.edit
      ? "edited"
      : made.restore
        ? "restored"
        : made.fix
          ? "fixed"
          : (depthAs(made.depth)?.toLowerCase() ?? ""))
  );
}

/** What restoring made a picture, as its new name says it ("Coloured" when that's all, else
 * "Restored"), from History's words for it, as `label` writes them in
 * engine/src/mado/core/restore.py. */
export function restoredAs(restore: string | null | undefined): string | null {
  if (!restore) return null;
  return restore === "coloured it" ? "Coloured" : "Restored";
}

/** How History's words for a 3D photo start (engine/src/mado/core/motion.py's MOTION_WORDS). */
export const MOTION_WORDS = "into a 3D photo";

/** What the depth tools made a picture, as its new name says it ("Portrait blur", "Fog",
 * "Tilt-shift", or "Depth" for more than one; "3D photo"), from History's words for them, as
 * `label` writes them in engine/src/mado/core/depth.py. */
export function depthAs(depth: string | null | undefined): string | null {
  if (!depth) return null;
  if (depth.startsWith(MOTION_WORDS)) return "3D photo";
  const kinds = [/portrait blur/, /fog/, /tilt-shift/].filter((each) => each.test(depth));
  if (kinds.length > 1) return "Depth";
  if (/portrait blur/.test(depth)) return "Portrait blur";
  if (/fog/.test(depth)) return "Fog";
  return "Tilt-shift";
}

/** What the fixes made a picture, as its new name says it ("Cleaned", "Sharpened", "Brightened",
 * or "Fixed" for more than one kind), from History's words for them ("took out noise"), as
 * `label` writes them in engine/src/mado/core/fixes.py. */
export function fixedAs(fix: string | null | undefined): string | null {
  if (!fix) return null;
  const kinds = new Set<string>();
  if (/took out/.test(fix)) kinds.add("Cleaned");
  if (/mended the blur/.test(fix)) kinds.add("Sharpened");
  if (/brightened/.test(fix)) kinds.add("Brightened");
  const [only] = kinds;
  return kinds.size === 1 && only ? only : "Fixed";
}

const EDITED: Record<string, string> = {
  erased: "Erased",
  "cut out": "Cut out",
  "blurred what's behind": "Blurred",
};

/** What the edits made a picture, as its new name says it ("Erased", "Cut out", "Blurred", or
 * "Edited" for more than one kind), from History's words for them ("erased a part"): each edit's
 * words start with its verb, as `phrase` writes them in engine/src/mado/core/edits.py. */
export function editedAs(edit: string | null): string | null {
  if (!edit) return null;
  const kinds = new Set(
    [...edit.matchAll(/\b(erased|cut out|blurred what's behind)/g)].map((found) => found[1]),
  );
  const [only] = kinds;
  return kinds.size === 1 && only ? (EDITED[only] ?? "Edited") : "Edited";
}

/** A file's name without its extension: "Harbour at dusk" from "Harbour at dusk.heic". */
export function stem(name: string): string {
  const at = name.lastIndexOf(".");
  return at > 0 ? name.slice(0, at) : name;
}

/** Languages as people say them: "English", "English and German", from Windows' tags ("en-GB",
 * "de-DE"), each language once. */
export function languages(tags: string[]): string {
  const named = new Intl.DisplayNames(["en"], { type: "language" });
  const names = [...new Set(tags.map((tag) => named.of(tag.split("-")[0] ?? tag) ?? tag))];
  if (names.length <= 1) return names[0] ?? "English";
  return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}
