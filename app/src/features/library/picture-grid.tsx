import { type ChangeEvent, useEffect, useId, useRef } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { type PictureItem, type PicturePage, type Shown, shownQuery } from "@/lib/engine";
import { clock, dayHeading, pictures as picturesWord, stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useNear } from "./near";
import { Thumbnail, tagOf } from "./thumbnail";

/** One day of the grid: its pictures, in the list's order. */
export interface Day {
  day: string;
  /** All of that day's pictures, loaded yet or not. */
  count: number;
  pictures: PictureItem[];
}

/** The loaded pages as days: each day's pictures together, counted whole. */
export function daysOf(pages: PicturePage[]): Day[] {
  const counts = new Map(pages.flatMap((page) => page.days.map((day) => [day.day, day.pictures])));
  const days: Day[] = [];
  for (const picture of pages.flatMap((page) => page.pictures)) {
    const day = picture.takenAt.slice(0, 10);
    const last = days.at(-1);
    if (last?.day === day) last.pictures.push(picture);
    else days.push({ day, count: counts.get(day) ?? 0, pictures: [picture] });
  }
  return days;
}

/**
 * The grid by the day pictures were taken, each picture ticked by its box (Shift ticks the run
 * from the one ticked last), opened by its picture or its name. The next page comes as its end
 * nears, or on asking.
 */
export function PictureGrid(props: {
  days: Day[];
  shown: Shown;
  ticked: ReadonlySet<number>;
  onTick: (id: number, run: boolean) => void;
  more: boolean;
  loadingMore: boolean;
  /** The next page didn't come last time: it's asked for again only on asking. */
  moreFailed: boolean;
  onMore: () => void;
}) {
  const query = shownQuery(props.shown);
  const opened = (id: number) => `/library/pictures/${id}${query ? `?${query}` : ""}`;
  return (
    <div className="flex flex-col gap-6">
      {props.days.map((day) => (
        <DaySection
          key={day.day}
          day={day}
          opened={opened}
          ticked={props.ticked}
          onTick={props.onTick}
        />
      ))}
      {props.more && (
        <More loading={props.loadingMore} failed={props.moreFailed} onMore={props.onMore} />
      )}
    </div>
  );
}

function DaySection(props: {
  day: Day;
  opened: (id: number) => string;
  ticked: ReadonlySet<number>;
  onTick: (id: number, run: boolean) => void;
}) {
  const id = useId();
  const { day } = props;
  return (
    // Days far out of view aren't drawn till they come near: the grid holds many thousands.
    <section
      aria-labelledby={id}
      className="flex flex-col gap-2.5 [contain-intrinsic-size:auto_15rem] [content-visibility:auto]"
    >
      <h2 id={id} className="flex items-baseline gap-2.5 font-semibold text-15">
        {dayHeading(day.day)}{" "}
        <span className="font-mono font-normal text-12 text-fg-faint">
          {picturesWord(day.count)}
        </span>
      </h2>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-2.5">
        {day.pictures.map((picture) => (
          <Tile
            key={picture.id}
            picture={picture}
            to={props.opened(picture.id)}
            ticked={props.ticked.has(picture.id)}
            onTick={props.onTick}
          />
        ))}
      </div>
    </section>
  );
}

function Tile(props: {
  picture: PictureItem;
  to: string;
  ticked: boolean;
  onTick: (id: number, run: boolean) => void;
}) {
  const { picture } = props;
  const name = stem(picture.name);
  const tag = tagOf(picture);
  const tick = (event: ChangeEvent<HTMLInputElement>) => {
    const native = event.nativeEvent; // a click, for a box: it knows whether Shift was down
    props.onTick(picture.id, "shiftKey" in native && native.shiftKey === true);
  };
  return (
    <figure className="m-0 flex min-w-0 flex-col gap-1.25">
      <div
        className={cn(
          "relative h-26 overflow-hidden rounded-4",
          props.ticked && "outline-2 outline-accent outline-offset-1",
        )}
      >
        <Link to={props.to} aria-label={name} className="absolute inset-0 outline-offset-[-2px]">
          <Thumbnail picture={picture} />
        </Link>
        <input
          type="checkbox"
          aria-label={`Tick ${name}`}
          checked={props.ticked}
          onChange={tick}
          className="absolute top-1.5 left-1.5 size-4.5 cursor-pointer accent-accent"
        />
        {tag && (
          <span
            className={cn(
              "pointer-events-none absolute right-1.5 bottom-1.5 rounded-4 px-1.5 py-px font-medium font-mono text-11",
              // Over a picture it's white on black; on a stand-in, the interface's own colours.
              picture.state === "ready" ? "bg-black/70 text-white" : "bg-tag text-fg",
            )}
          >
            {tag}
          </span>
        )}
      </div>
      <figcaption className="flex min-w-0 justify-between gap-1 text-12">
        <span className="truncate text-fg">{name}</span>
        <span className="shrink-0 font-mono text-fg-faint">{clock(picture.takenAt)}</span>
      </figcaption>
    </figure>
  );
}

/** The grid's end: the next page comes as it nears the view, or when asked. */
function More(props: { loading: boolean; failed: boolean; onMore: () => void }) {
  const { loading, failed, onMore } = props;
  const end = useRef<HTMLDivElement>(null);
  const near = useNear(end, "600px 0px");
  const watched = typeof IntersectionObserver !== "undefined"; // else it waits to be asked
  useEffect(() => {
    if (watched && near && !loading && !failed) onMore();
  }, [watched, near, loading, failed, onMore]);
  return (
    <div ref={end} className="flex justify-center py-2">
      <Button variant="ghost" size="sm" disabled={loading} onClick={onMore}>
        {loading
          ? "Bringing more pictures…"
          : failed
            ? "Couldn't bring more pictures. Try again"
            : "Show more pictures"}
      </Button>
    </div>
  );
}
