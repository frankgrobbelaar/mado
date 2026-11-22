import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Graphite's own scales (src/styles/tokens.css). tailwind-merge has to know them,
// or it would read text-13 as a colour and drop it next to text-fg-muted.
export const fontSizes = ["10", "11", "12", "13", "14", "15", "16", "18", "20", "24", "30", "32"];
export const radii = ["2", "3", "4", "6", "8", "10"];

const twMerge = extendTailwindMerge({
  extend: { theme: { text: fontSizes, radius: radii } },
});

/** Joins class names; when two classes set the same thing, the later one wins. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
