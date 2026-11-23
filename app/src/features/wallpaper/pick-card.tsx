import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogHeader } from "@/components/ui/dialog";
import { Segmented } from "@/components/ui/segmented";
import { type PictureItem, pictureAddress, usePictureImage, usePictures } from "@/lib/engine";
import { stem } from "@/lib/format";
import { useSettled } from "@/lib/settled";

type From = "favourites" | "all";

const FROM = [
  { value: "favourites", label: "Favourites" },
  { value: "all", label: "All pictures" },
] as const;

/**
 * A card for picking the picture a monitor (or every monitor) shows: the owner's favourites first,
 * or any picture in the library, found by a word of its name. A picture dropped on the window or
 * pasted is picked too, card or no card.
 */
export function PickCard(props: {
  /** Who it's for: "Studio 27 · 2560 × 1440". */
  forWhat: string;
  onPick: (picture: PictureItem) => void;
  onClose: () => void;
}) {
  const [from, setFrom] = useState<From>("favourites");
  const [words, setWords] = useState("");
  const q = useSettled(words.trim(), 250);
  const shown = useMemo(
    () => ({
      folder: null,
      dir: "",
      q,
      order: "newest" as const,
      favourites: from === "favourites",
      like: null,
    }),
    [from, q],
  );
  const list = usePictures(shown);
  const pictures = list.data?.pages
    .flatMap((page) => page.pictures)
    .filter((each) => each.state === "ready");
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(46rem,calc(100vw-2rem))]">
        <DialogHeader title="Pick a picture" description={`For ${props.forWhat}`} />
        <DialogBody className="gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Segmented label="Pictures from" value={from} options={FROM} onChange={setFrom} />
            <label className="ml-auto flex h-9 items-center gap-2 rounded-6 border border-field-edge bg-field px-2.5 text-13 text-fg-faint focus-within:border-accent">
              <Search size={15} aria-hidden="true" />
              <span className="sr-only">Search them</span>
              <input
                type="search"
                value={words}
                onChange={(event) => setWords(event.target.value)}
                placeholder={
                  from === "favourites" ? "Search your favourites" : "Search your library"
                }
                className="w-44 border-0 bg-transparent text-13 text-fg outline-none placeholder:text-fg-faint"
              />
            </label>
          </div>
          <EngineProblem queries={[list]} />
          {!pictures ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] gap-2.5">
              {["a", "b", "c", "d"].map((each) => (
                <Skeleton key={each} className="h-22 rounded-4" />
              ))}
            </div>
          ) : pictures.length === 0 ? (
            <None from={from} q={q} onAll={() => setFrom("all")} />
          ) : (
            <ul className="grid max-h-[50vh] grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] gap-2.5 overflow-y-auto p-0.5">
              {pictures.map((picture) => (
                <li key={picture.id} className="list-none">
                  <Choice picture={picture} onPick={() => props.onPick(picture)} />
                </li>
              ))}
            </ul>
          )}
          {list.hasNextPage && (
            <Button
              variant="ghost"
              size="sm"
              className="self-center"
              onClick={() => void list.fetchNextPage()}
            >
              Show more pictures
            </Button>
          )}
          <p className="text-12 text-fg-faint">
            Or drop a picture on the window, or paste one: it goes where this one would.
          </p>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

function Choice({ picture, onPick }: { picture: PictureItem; onPick: () => void }) {
  const image = usePictureImage(pictureAddress(picture, "thumbnail"));
  const name = stem(picture.name);
  return (
    <button
      type="button"
      aria-label={name}
      onClick={onPick}
      className="press flex w-full cursor-pointer flex-col gap-1 rounded-4 text-left outline-offset-2"
    >
      <span className="relative block h-22 overflow-hidden rounded-4 bg-behind">
        {image.address && (
          <img
            src={image.address}
            alt=""
            draggable={false}
            className="size-full animate-fade-in object-cover"
          />
        )}
      </span>
      <span className="truncate text-12 text-fg">{name}</span>
    </button>
  );
}

function None(props: { from: From; q: string; onAll: () => void }) {
  if (props.q) {
    return (
      <p className="text-13 text-fg-muted">
        No pictures with “{props.q}” in the name{" "}
        {props.from === "favourites" ? "among your favourites" : "in your library"}.
      </p>
    );
  }
  if (props.from === "favourites") {
    return (
      <section className="flex flex-col items-start gap-2 rounded-8 border border-dash border-dashed bg-surface px-5 py-5">
        <h3 className="font-semibold text-15">No favourites yet</h3>
        <p className="text-13 text-fg-muted leading-normal">
          Give pictures a heart in the Library or on their pages, and they're here to pick. Any
          picture in your library works meanwhile.
        </p>
        <Button size="sm" onClick={props.onAll}>
          Show all pictures
        </Button>
      </section>
    );
  }
  return (
    <p className="text-13 text-fg-muted">
      Your library has no pictures Mado can show yet.{" "}
      <Link to="/library" className="text-accent-fg underline">
        Open the Library
      </Link>
    </p>
  );
}
