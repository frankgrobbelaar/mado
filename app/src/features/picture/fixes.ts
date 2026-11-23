import type { FixStep, Quality } from "@/lib/engine";

/** A recipe with its fixes, when any is on: one without carries none, as it did before Mado
 * had them. */
export function fixed<T extends object>(
  recipe: T,
  fix: FixStep | null | undefined,
): T & { fix?: FixStep } {
  return hasFix(fix) ? { ...recipe, fix } : recipe;
}

/** No fix on. */
export const NO_FIX: FixStep = { noise: null, blur: null, jpeg: null, dark: null };

/** The fixes' models, by their ids in Mado's list of downloads (engine/src/mado/downloads.json):
 * SCUNet takes noise out (and JPEG blocks at Fast, and a dark photo's noise), FBCNN JPEG blocks
 * at Best, NAFNet blur. */
export const FIX_MODELS = { scunet: "scunet", fbcnn: "fbcnn", nafnet: "nafnet" } as const;

/** Whether any fix is on. */
export function hasFix(fix: FixStep | null | undefined): fix is FixStep {
  return Boolean(fix && (fix.noise || fix.blur || fix.jpeg || fix.dark));
}

/** The models the fixes need, JPEG blocks at `quality` (as the plan decided), each once, in the
 * order they're made: FBCNN, SCUNet, NAFNet. */
export function fixModels(fix: FixStep, quality: Quality | null): string[] {
  const found: string[] = [];
  if (fix.jpeg && quality === "best") found.push(FIX_MODELS.fbcnn);
  if (fix.noise || fix.dark || (fix.jpeg && quality !== "best")) found.push(FIX_MODELS.scunet);
  if (fix.blur) found.push(FIX_MODELS.nafnet);
  return found;
}

/** The fixes a picture made small shows (all of it on a stage, a look's small copy): a dark
 * photo's brightening and local contrast, or null. Noise, blur and blocks are too small to see at
 * that size, so they show only on a part at full detail, and the engine makes only these there. */
export function brightening(fix: FixStep | null | undefined): FixStep | null {
  return fix?.dark ? { ...NO_FIX, dark: fix.dark } : null;
}

/** How hard JPEG blocks come out to start with: as hard as the JPEG was squeezed (a JPEG saved
 * at 30 starts at 70%), or 60% when Mado can't read its quality. */
export function jpegStrength(quality: number | null): number {
  if (quality === null) return 0.6;
  return Math.min(0.9, Math.max(0.1, Math.round(100 - quality) / 100));
}

/** The fixes on, as the stage's label names them: "Noise, JPEG blocks". */
export function fixNames(fix: FixStep): string {
  const names = [
    fix.noise && "Noise",
    fix.blur && "Blur",
    fix.jpeg && "JPEG blocks",
    fix.dark && "Dark photo",
  ].filter(Boolean);
  return names.join(", ");
}
