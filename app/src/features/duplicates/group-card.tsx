import { Maximize2 } from "lucide-react";
import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { useNear } from "@/features/library/near";
import {
  type DuplicateGroup,
  type GroupPicture,
  pictureAddress,
  usePictureImage,
} from "@/lib/engine";
import { count, size, takenOn } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * A group, as a panel the way History's days are: what it is ("Burst · 5 shots"), which one is
 * kept and why, and its pictures as thumbnails with their size, pixels, folder and when taken.
 * A click on one keeps it instead; its tick keeps it as well; its corner button opens it big
 * beside the one kept. "Not the same" lets the group go; "Set aside 4" sets the rest aside.
 */
export function GroupCard(props: {
  group: DuplicateGroup;
  busy: boolean;
  onKeep: (ids: number[]) => void;
  onNotSame: () => void;
  onSetAside: () => void;
  onOpen: (picture: GroupPicture) => void;
}) {
  const { group } = props;
  const kept = group.pictures.filter((each) => each.keep).map((each) => each.id);
  const [title, detail] = groupWords(group);
  const missing = group.pictures.find((each) => each.there === "gone" || each.there === "changed");
  return (
    <section
      aria-label={title}
      className="flex animate-fade-up flex-col rounded-8 border border-edge bg-glass"
    >
      <header className="flex flex-wrap items-center gap-x-3.5 gap-y-2 px-4.5 pt-3 pb-3">
        <span aria-hidden="true" className="status-waiting size-3 shrink-0 rounded-full" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 className="font-semibold text-15">{title}</h2>
          <span className="text-13 text-fg-muted">{detail}</span>
        </span>
        <span className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" disabled={props.busy} onClick={props.onNotSame}>
            Not the same
          </Button>
          {group.aside > 0 && (
            <Button
              size="sm"
              className="font-medium"
              disabled={props.busy || !group.ready}
              onClick={props.onSetAside}
            >
              Set aside {count(group.aside)}
            </Button>
          )}
        </span>
      </header>
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(168px,1fr))] gap-3 px-4.5 pb-4">
        {group.pictures.map((picture) => (
          <Tile
            key={picture.id}
            picture={picture}
            burst={group.kind === "burst"}
            busy={props.busy}
            only={picture.keep && kept.length === 1}
            onKeepOnly={() => props.onKeep([picture.id])}
            onToggle={() =>
              props.onKeep(
                picture.keep ? kept.filter((id) => id !== picture.id) : [...kept, picture.id],
              )
            }
            onOpen={() => props.onOpen(picture)}
          />
        ))}
      </ul>
      {(group.problem || missing) && (
        <p className="border-edge border-t px-4.5 py-2.5 text-13 text-fg-muted">
          {group.problem ??
            (missing?.there === "gone"
              ? `${missing.name} isn't there any more: it was moved or deleted since. Mado sees to it as it looks again.`
              : `${missing?.name} changed since Mado compared it; Mado looks at it again.`)}
        </p>
      )}
    </section>
  );
}

/** "Burst · 5 shots", "Kept: IMG_2042.jpg, the sharpest"; "Duplicates · 3 copies"… */
export function groupWords(group: DuplicateGroup): [string, string] {
  const shown = group.pictures.length;
  const kept = group.pictures.filter((each) => each.keep);
  const title =
    group.kind === "burst"
      ? `Burst · ${count(shown)} shots`
      : `Duplicates · ${count(shown)} ${group.exact ? "identical files" : "copies"}`;
  const why = group.chosen ? "as you chose" : REASONS[group.reason];
  const names = kept.map((each) => each.name);
  const keeping =
    names.length === 1
      ? `Keeping ${names[0]}, ${why}`
      : `Keeping ${count(names.length)} of them, ${why}`;
  return [
    title,
    `${keeping}. ${group.kind === "burst" ? "Shots a second or two apart." : group.exact ? "The same bytes." : "One picture saved more than once."}`,
  ];
}

function Tile(props: {
  picture: GroupPicture;
  burst: boolean;
  busy: boolean;
  /** The only one kept: its tick can't come off (one is always kept). */
  only: boolean;
  onKeepOnly: () => void;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const { picture } = props;
  const box = useRef<HTMLLIElement>(null);
  const near = useNear(box);
  const image = usePictureImage(near ? pictureAddress(picture, "thumbnail") : null);
  const away = picture.there !== "there";
  return (
    <li ref={box} className="flex min-w-0 flex-col gap-1.5">
      <div
        className={cn(
          "relative h-28 overflow-hidden rounded-4 bg-behind",
          picture.keep && "outline-2 outline-accent outline-offset-1",
        )}
      >
        <button
          type="button"
          aria-pressed={picture.keep}
          aria-label={picture.keep ? `${picture.name}, kept` : `Keep ${picture.name} instead`}
          disabled={props.busy || (picture.keep && props.only)}
          onClick={props.onKeepOnly}
          className="absolute inset-0 cursor-pointer disabled:cursor-default"
        >
          {image.address && (
            <img
              src={image.address}
              alt=""
              draggable={false}
              className={cn("size-full animate-fade-in object-cover", away && "opacity-40")}
            />
          )}
        </button>
        <input
          type="checkbox"
          checked={picture.keep}
          disabled={props.busy || props.only}
          onChange={props.onToggle}
          aria-label={picture.keep ? `Keep ${picture.name}` : `Keep ${picture.name} too`}
          className="absolute top-1.5 left-1.5 size-4.5 cursor-pointer accent-accent"
        />
        <button
          type="button"
          aria-label={`See ${picture.name} big beside the one kept`}
          onClick={props.onOpen}
          className="press absolute top-1 right-1 inline-flex size-7 cursor-pointer items-center justify-center rounded-4 bg-tag text-fg"
        >
          <Maximize2 size={14} aria-hidden="true" />
        </button>
        {picture.keep && (
          <span className="absolute bottom-1.5 left-1.5 rounded-4 bg-accent px-1.5 py-px font-semibold text-11 text-on-accent">
            Keep
          </span>
        )}
        {away && (
          <span className="absolute right-1.5 bottom-1.5 rounded-4 bg-tag px-1.5 py-px font-mono text-11 text-fg">
            {THERE[picture.there]}
          </span>
        )}
      </div>
      <span className="flex min-w-0 flex-col text-12 leading-snug">
        <span className="truncate font-medium text-13" title={picture.path}>
          {picture.name}
        </span>
        <span className="font-mono text-fg-muted">
          {picture.width} × {picture.height} · {size(picture.size)}
        </span>
        <span className="truncate text-fg-muted" title={picture.folder}>
          {folderWords(picture.folder)}
        </span>
        <span className="font-mono text-fg-faint">
          {props.burst ? picture.takenAt.slice(11, 19) : takenOn(picture.takenAt)}
        </span>
      </span>
    </li>
  );
}

const THERE = { there: "", away: "Not connected", gone: "Gone since", changed: "Changed since" };

/** What decided which Mado keeps, as the group's line says it. */
const REASONS = {
  sharpest: "the sharpest",
  pixels: "the most pixels",
  larger: "the larger file",
  name: "the name that isn't a copy's",
  older: "the older file",
} as const;

/** The folder a picture's in, as its last two names: "Phone › 2026". */
export function folderWords(folder: string): string {
  const names = folder.split(/[\\/]/).filter(Boolean);
  return names.slice(-2).join(" › ") || folder;
}
