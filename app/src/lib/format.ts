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

/** "233 MB", "1.1 GB" from a billion bytes, "16 GB" from ten billion, "320 KB" under a million. */
export function size(bytes: number): string {
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(1)} TB`;
  if (bytes >= 1e10) return `${Math.round(bytes / 1e9)} GB`;
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${Math.round(bytes / 1e6)} MB`;
  return `${bytes > 0 ? Math.max(1, Math.round(bytes / 1e3)) : 0} KB`;
}
