import { useCallback, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { pickFolder, pickPictures } from "@/lib/dialogs";
import {
  type OpenHow,
  type Pick,
  type Picked,
  pageOf,
  type Starts,
  useFindPictures,
  useOpenPaths,
} from "@/lib/engine";

/** What Many at once opens with: the pictures (found already, or to find), and a recipe to
 * start from. */
export interface BatchStart {
  pick: Pick;
  picked?: Picked;
  recipe?: number;
  starts?: Starts;
}

/** A note at the window's foot about what was opened: what was left out, or why nothing was. */
export interface OpeningNote {
  title: string;
  body: string;
  /** Still under way ("Pasting the picture…"): it stays till it's done. */
  busy?: boolean;
}

/**
 * Opens pictures from anywhere: dropped on the window, picked from the PC, pasted, or handed over
 * by Windows (File Explorer, Open with, the command line). One picture opens its page, in the
 * library or not; several, or a folder, open Many at once with them chosen; what isn't a picture
 * Mado reads is said, rather than opened. With a recipe, they always open Many at once with it.
 */
export function useOpenPictures(recipe?: number) {
  const navigate = useNavigate();
  const here = useLocation().pathname;
  const opening = useOpenPaths();
  const find = useFindPictures();
  const [problem, setProblem] = useState<string | null>(null);
  const [note, setNote] = useState<OpeningNote | null>(null);

  const many = useCallback(
    (pick: Pick, picked: Picked) => {
      const start: BatchStart = { pick, picked, recipe };
      void navigate("/batch", { state: start });
    },
    [navigate, recipe],
  );

  const open = useCallback(
    (paths: string[], how: OpenHow) => {
      setProblem(null);
      setNote(null);
      const failed = (error: Error) => {
        setProblem(error.message);
        setNote({ title: "Nothing opened", body: error.message });
      };
      if (recipe !== undefined) {
        const pick: Pick = { how, paths };
        find.mutate(
          { path: "/batches/pictures", body: pick },
          {
            onSuccess: (picked) => {
              if (picked.pictures.length) many(pick, picked);
              else failed(new Error(nothingIn(picked)));
            },
            onError: failed,
          },
        );
        return;
      }
      opening.mutate(
        { path: "/open", body: { paths, how } },
        {
          onSuccess: (opened) => {
            if (opened.picture) {
              const page = pageOf(opened.picture);
              void navigate(page, { replace: page === here });
              if (opened.leftOut.length) setNote(leftOutNote(opened.leftOut));
            } else if (opened.picked?.pictures.length) {
              many({ how, paths }, opened.picked);
            } else if (opened.picked) {
              failed(new Error(nothingIn(opened.picked)));
            }
          },
          onError: failed,
        },
      );
    },
    [opening, find, many, navigate, here, recipe],
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

  return {
    open,
    choosePictures,
    chooseFolder,
    busy: opening.isPending || find.isPending,
    problem,
    note,
    clearNote: useCallback(() => setNote(null), []),
  };
}

/** What's said beside a picture opened, of what came with it and was left out. */
export function leftOutNote(left: { name: string; why: string }[]): OpeningNote {
  const [first] = left;
  if (left.length === 1 && first) return { title: `Left out ${first.name}`, body: first.why };
  return {
    title: `Left out ${left.length} others`,
    body: `${left.map((each) => each.name).join(", ")}: they aren't pictures Mado reads, or aren't there any more.`,
  };
}

function nothingIn(picked: Picked): string {
  const [first] = picked.leftOut;
  return picked.leftOut.length === 1 && first
    ? `${first.name}: ${first.why}`
    : "None of those are pictures Mado reads: JPEG, PNG, HEIC, WebP, AVIF, TIFF, BMP or GIF.";
}
