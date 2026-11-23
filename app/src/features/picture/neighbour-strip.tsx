import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { Thumbnail } from "@/features/library/thumbnail";
import type { PictureItem } from "@/lib/engine";
import { stem } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The pictures either side of this one, in the list it was opened from: a strip of small
 * pictures, this one lit, any opened with a click. */
export function NeighbourStrip(props: {
  label: string;
  current: PictureItem;
  before: PictureItem[];
  after: PictureItem[];
  to: (id: number) => string;
}) {
  const lit = useRef<HTMLAnchorElement>(null);
  const items = [...props.before, props.current, ...props.after];

  // This picture stays in sight in the strip as the pictures change.
  const here = props.current.id;
  useEffect(() => {
    if (here) lit.current?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [here]);

  return (
    <nav
      aria-label={props.label}
      className="flex shrink-0 gap-2 overflow-x-auto px-0.5 pt-0.5 pb-1"
    >
      {items.map((item) => {
        const current = item.id === here;
        return (
          <Link
            key={item.id}
            ref={current ? lit : undefined}
            to={props.to(item.id)}
            aria-label={stem(item.name)}
            aria-current={current ? "true" : undefined}
            className={cn(
              "relative h-12.5 w-18 shrink-0 overflow-hidden rounded-4",
              current
                ? "outline-2 outline-accent outline-offset-1"
                : "opacity-80 hover:opacity-100",
            )}
          >
            <Thumbnail picture={item} lazy={false} small />
          </Link>
        );
      })}
    </nav>
  );
}
