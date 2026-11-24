import type {
  BatchSaving,
  BatchStep,
  CutoutStepItem,
  DepthStepItem,
  FixStepItem,
  LookStepItem,
  PaintStepItem,
  RestoreStepItem,
  Settings,
  SizeStepItem,
  StepWords,
} from "@/lib/engine";

/** How a batch saves till it's told otherwise: as Save starts (Settings › General › Saving), in
 * JPEG, which every screen and print shop takes. */
export function savingFrom(settings: Settings | undefined): BatchSaving {
  return {
    how: settings?.saveFirst ?? "new",
    format: "JPEG",
    quality: 92,
    folder: settings?.newPictures === "folder" ? settings.newFolder : null,
    keepCamera: true,
    keepColours: true,
    keepLocation: settings?.keepLocation ?? false,
  };
}

/** A size step for a size: cropped around each picture's subject, the model as this PC suits. */
export function sizeStep(size: string, before?: SizeStepItem): SizeStepItem {
  return {
    step: "size",
    size,
    shape: before?.shape ?? "crop",
    kind: before?.kind ?? null,
    quality: before?.quality ?? null,
    clean: before?.clean ?? true,
  };
}

/** A look step: Mado's or the owner's look, at a strength, with touches. */
export function lookStep(look: string, before?: LookStepItem): LookStepItem {
  return {
    step: "look",
    look,
    strength: before?.strength ?? 1,
    touches: before?.touches ?? { grain: 0, vignette: 0, glow: 0, fade: 0, leak: 0, dust: 0 },
  };
}

/** A painting style step: Mado's style or the owner's, at its strength and with the colours chosen
 * so far (all of it, the first time), a classic one at its own first setting. */
export function paintStep(style: string, before?: PaintStepItem): PaintStepItem {
  return {
    step: "paint",
    style,
    strength: before?.strength ?? 1,
    colours: before?.colours ?? false,
    setting: before?.style === style ? before.setting : null,
  };
}

/** Cut out the subject: as this PC suits, with nothing behind it, as the Recipes board's
 * "Cut-outs for cards" has it. */
export function cutoutStep(before?: CutoutStepItem): CutoutStepItem {
  return {
    step: "cutout",
    quality: before?.quality ?? null,
    behind: before?.behind ?? "nothing",
    colour: before?.colour ?? null,
  };
}

/** Restoring old photos a batch at a time: each picture as it needs, a black-and-white or sepia
 * one coloured and a colour one's faded colours brought back. Scratches are each picture's own,
 * checked and filled on its page, so a batch never fills them. */
export function restoreStep(before?: RestoreStepItem): RestoreStepItem {
  return {
    step: "restore",
    colour: before ? before.colour : { strength: 1 },
    faded: before ? before.faded : { strength: 1 },
  };
}

/** The fixes: noise taken out to start with, as the most common fix a batch of photos wants;
 * the rest as the Fix tab turns them on. */
export function fixStep(before?: FixStepItem): FixStepItem {
  return {
    step: "fix",
    noise: before ? before.noise : { strength: 1 },
    blur: before?.blur ?? null,
    jpeg: before?.jpeg ?? null,
    dark: before?.dark ?? null,
  };
}

/** The depth tools: portrait blur to start with, at f/2.8, each picture in focus at its own
 * subject; fog and tilt-shift as the Depth tab turns them on. */
export function depthStep(before?: DepthStepItem): DepthStepItem {
  return {
    step: "depth",
    portrait: before ? before.portrait : { focus: null, aperture: 2.8, quality: null },
    fog: before?.fog ?? null,
    tilt: before?.tilt ?? null,
  };
}

/** Saving that keeps a cut-out's nothing: only PNG and WebP keep see-through parts, so a batch
 * saving as anything else moves to PNG once it cuts out with nothing behind. */
export function savingFor(steps: BatchStep[], saving: BatchSaving): BatchSaving {
  return keepsNothing(steps) && !SEE_THROUGH.includes(saving.format)
    ? { ...saving, format: "PNG", quality: null }
    : saving;
}

/** Whether a batch's steps cut out with nothing behind. */
export function keepsNothing(steps: BatchStep[]): boolean {
  return steps.some((step) => step.step === "cutout" && step.behind === "nothing");
}

/** The formats that keep see-through parts. */
export const SEE_THROUGH: BatchSaving["format"][] = ["PNG", "WebP"];

/** The steps with one put in its place (the subject cut out, restoring, the fixes, the size, the
 * depth tools, the painting style, then the look), or taken out. */
export function withStep(steps: BatchStep[], step: BatchStep | null, kind: BatchStep["step"]) {
  const rest = steps.filter((each) => each.step !== kind);
  const next = step ? [...rest, step] : rest;
  return next.sort((a, b) => ORDER.indexOf(a.step) - ORDER.indexOf(b.step));
}

const ORDER: BatchStep["step"][] = ["cutout", "restore", "fix", "size", "depth", "paint", "look"];

/** What a step is called, before the engine's words for it come. */
export const TITLES: Record<string, string> = {
  cutout: "Cut out the subject",
  restore: "Restore",
  fix: "Fix",
  size: "Make it for a screen",
  depth: "Depth",
  paint: "A painting style",
  look: "A look",
  save: "Save",
};

/** Words for the steps and the save while the engine's are on their way. */
export function wordsFor(steps: BatchStep[], saving: BatchSaving): StepWords[] {
  return [
    ...steps.map((step) => ({
      kind: step.step,
      title: TITLES[step.step] ?? step.step,
      detail: "…",
      chip:
        step.step === "size"
          ? step.size
          : step.step === "look"
            ? step.look
            : step.step === "paint"
              ? step.style
              : step.step === "fix"
                ? "Fix"
                : step.step === "depth"
                  ? "Depth"
                  : step.step === "restore"
                    ? "Restore"
                    : "Cut out the subject",
      amount: null,
    })),
    {
      kind: "save",
      title: "Save",
      detail: "…",
      chip: saving.format,
      amount: null,
    },
  ];
}

/** Two batches' steps and saving the same, as a recipe kept is to its batch. */
export function same(a: { steps: BatchStep[]; saving: BatchSaving }, b: typeof a): boolean {
  return JSON.stringify(normal(a)) === JSON.stringify(normal(b));
}

function normal({ steps, saving }: { steps: BatchStep[]; saving: BatchSaving }) {
  return {
    steps: steps.map((step) => Object.fromEntries(Object.entries(step).sort())),
    saving: Object.fromEntries(Object.entries(saving).sort()),
  };
}
