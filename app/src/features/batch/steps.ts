import type {
  BatchSaving,
  BatchStep,
  LookStepItem,
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

/** The steps with one put in its place (the size first, then the look), or taken out. */
export function withStep(steps: BatchStep[], step: BatchStep | null, kind: BatchStep["step"]) {
  const rest = steps.filter((each) => each.step !== kind);
  const next = step ? [...rest, step] : rest;
  return next.sort((a, b) => ORDER.indexOf(a.step) - ORDER.indexOf(b.step));
}

const ORDER: BatchStep["step"][] = ["size", "look"];

/** What a step is called, before the engine's words for it come. */
export const TITLES: Record<string, string> = {
  size: "Make it for a screen",
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
      chip: step.step === "size" ? step.size : step.look,
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
