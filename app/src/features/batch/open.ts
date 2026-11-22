import { useCallback, useState } from "react";
import { useNavigate } from "react-router";
import { pickFolder, pickPictures } from "@/lib/dialogs";
import { type Pick, type Picked, type Starts, useFindPictures } from "@/lib/engine";

/** What Many at once opens with: the pictures (found already, or to find), and a recipe to
 * start from. */
export interface BatchStart {
  pick: Pick;
  picked?: Picked;
  recipe?: number;
  starts?: Starts;
}

/**
 * Opens pictures dropped on the window or picked from the PC: one picture in the library opens its
 * page; anything else, a picture outside the library, many, or a folder, opens Many at once with
 * them. What isn't a picture Mado makes is said, rather than opened.
 */
export function useOpenPictures(recipe?: number) {
  const navigate = useNavigate();
  const find = useFindPictures();
  const [problem, setProblem] = useState<string | null>(null);

  const open = useCallback(
    (paths: string[], how: "dropped" | "picked") => {
      setProblem(null);
      const pick: Pick = { how, paths };
      find.mutate(
        { path: "/batches/pictures", body: pick },
        {
          onSuccess: (picked) => {
            const [only] = picked.pictures;
            if (!only) {
              const why = picked.leftOut[0]?.why;
              setProblem(
                picked.leftOut.length === 1 && why
                  ? `${picked.leftOut[0]?.name}: ${why}`
                  : "None of those are pictures Mado makes: JPEG, PNG, HEIC, WebP, AVIF, TIFF, BMP or GIF.",
              );
              return;
            }
            if (picked.pictures.length === 1 && only.id !== null && recipe === undefined) {
              void navigate(`/library/pictures/${only.id}`);
              return;
            }
            const start: BatchStart = { pick, picked, recipe };
            void navigate("/batch", { state: start });
          },
          onError: (error) => setProblem(error.message),
        },
      );
    },
    [find, navigate, recipe],
  );

  /** Asks for pictures with Windows' picker, then opens them. */
  const choosePictures = useCallback(async () => {
    const paths = await pickPictures("Pick pictures");
    if (paths.length) open(paths, "picked");
  }, [open]);

  /** Asks for a folder with Windows' picker, then opens the pictures in it. */
  const chooseFolder = useCallback(async () => {
    const folder = await pickFolder("Pick a folder of pictures");
    if (folder) open([folder], "picked");
  }, [open]);

  return { open, choosePictures, chooseFolder, busy: find.isPending, problem };
}
