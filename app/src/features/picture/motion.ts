import { useEffect, useRef, useState } from "react";
import {
  type Edit,
  type Motion,
  type MotionAsk,
  type MotionSaved,
  useDropMotion,
  useMakeMotion,
  useMotion,
  useSaveMotion,
} from "@/lib/engine";

/** How a 3D photo is asked for, as the Depth tab's 3D photo choices set it. */
export type MotionChoices = Omit<MotionAsk, "version" | "edits">;

export const MOTION_START: MotionChoices = {
  motion: "push",
  seconds: 5,
  amount: 0.5,
  fill: "fast",
  size: "1080p",
  format: "mp4",
};

/**
 * A picture's 3D photo: made into Mado's cache when asked (the one before it let go), how it's
 * coming on, and saved when the owner says. Another picture, or the same one changed, lets it go.
 */
export function useMotionMaker(picture: { id: number; version: string } | null, edits: Edit[]) {
  const make = useMakeMotion();
  const save = useSaveMotion();
  const drop = useDropMotion();
  const [asked, setAsked] = useState<{ id: string; for: string } | null>(null);
  const [saved, setSaved] = useState<MotionSaved | null>(null);
  const motion = useMotion(asked?.id ?? null);
  const which = picture ? `${picture.id}:${picture.version}:${JSON.stringify(edits)}` : null;
  // Another picture, or this one changed: its 3D photo is let go.
  const letGo = useRef(drop.mutate);
  letGo.current = drop.mutate;
  useEffect(() => {
    if (asked && asked.for !== which) {
      letGo.current({ path: `/motion/${asked.id}` });
      setAsked(null);
      setSaved(null);
    }
  }, [asked, which]);
  return {
    motion: (asked ? (motion.data ?? null) : null) as Motion | null,
    making: make.isPending,
    problem: make.isError ? make.error.message : motion.isError ? motion.error.message : null,
    saved,
    saving: save.isPending,
    saveProblem: save.isError ? save.error.message : null,
    /** Makes it as `choices` say, the one made before let go. */
    start(choices: MotionChoices) {
      if (!picture || which === null) return;
      if (asked) drop.mutate({ path: `/motion/${asked.id}` });
      setSaved(null);
      make.mutate(
        {
          path: `/pictures/${picture.id}/motion`,
          body: { version: picture.version, edits, ...choices },
        },
        { onSuccess: (found) => setAsked({ id: found.id, for: which }) },
      );
    },
    /** Stops it being made, or lets the one made go. */
    stop() {
      if (asked) drop.mutate({ path: `/motion/${asked.id}` });
      setAsked(null);
      setSaved(null);
    },
    /** Saves it beside the picture (`folder` null) or into a folder. */
    keep(folder: string | null) {
      if (!asked) return;
      save.mutate(
        { path: `/motion/${asked.id}/save`, body: { folder } },
        { onSuccess: (found) => setSaved(found) },
      );
    },
  };
}

export type MotionMaker = ReturnType<typeof useMotionMaker>;
