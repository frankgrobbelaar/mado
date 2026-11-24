import type { Fixes, RestoreStep } from "@/lib/engine";

/** Nothing restored. */
export const NO_RESTORE: RestoreStep = {
  version: null,
  scratches: null,
  colour: null,
  faded: null,
};

/** Restoring's models, by their ids in Mado's list of downloads (engine/src/mado/downloads.json):
 * the scratch detector finds scratches and dust, LaMa fills them, DDColor colours. */
export const RESTORE_MODELS = {
  detector: "oldphoto-scratch-detector",
  filler: "lama",
  colourer: "ddcolor-tiny",
} as const;

/** The brush for the scratches' mask: as a fraction of the picture's shorter side, at first and
 * at most (a scratch is thin: much finer than the Edit tab's brush). */
export const SCRATCH_BRUSH = { first: 0.01, least: 0.005, most: 0.1 } as const;

/** The most strokes the scratches' mask keeps, as the engine takes them
 * (engine/src/mado/api/restore.py's `ScratchesIn`). */
export const SCRATCH_STROKES = 512;

/** A mask covering this much of the picture is a lot to fill; past `MOST_MASK`, Mado won't. */
export const MUCH_MASK = 0.25;
export const MOST_MASK = 0.5;

/** Whether any of restoring is on. */
export function hasRestore(step: RestoreStep | null | undefined): step is RestoreStep {
  return Boolean(step && (step.scratches || step.colour || step.faded));
}

/** A recipe with its restoring, when any is on: one without carries none, as before Mado had
 * it. */
export function restored<T extends object>(
  recipe: T,
  step: RestoreStep | null | undefined,
): T & { restore?: RestoreStep } {
  return hasRestore(step) ? { ...recipe, restore: step } : recipe;
}

/** The models restoring needs, each once, in the order they're used. */
export function restoreModels(step: RestoreStep): string[] {
  const found: string[] = [];
  if (step.scratches) found.push(RESTORE_MODELS.detector, RESTORE_MODELS.filler);
  if (step.colour && step.colour.strength > 0) found.push(RESTORE_MODELS.colourer); // 0%: no guess
  return found;
}

/** Restoring as the stage's label names it: "Scratches, Colour". */
export function restoreNames(step: RestoreStep): string {
  const names = [
    step.scratches && "Scratches",
    step.colour && "Colour",
    step.faded && "Faded colours",
  ].filter(Boolean);
  return names.join(", ");
}

/** Which way the Colour row starts for a picture: colouring one that's black and white or a toned
 * print, bringing back a colour photo's faded colours. */
export function colourWay(fixes: Fixes | null): "colour" | "faded" {
  return fixes?.colours === "colour" ? "faded" : "colour";
}

/** What a picture's colours are, in words: "black and white", "a sepia print". */
export function colourWords(fixes: Fixes): string {
  if (fixes.colours === "grey") return "black and white";
  if (fixes.colours === "toned") return fixes.tone === "sepia" ? "a sepia print" : "a toned print";
  return "in colour";
}
