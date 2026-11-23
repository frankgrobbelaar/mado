import { Heart } from "lucide-react";
import { useState } from "react";
import { useSetFavourite } from "@/lib/engine";
import { stem } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * A picture's heart: given, the picture is a favourite, listed in the Library's Favourites and one
 * the daily wallpaper can change to. It shows the change at once, the engine keeping it. On a
 * grid's tile it sits in the corner on dark glass, as the tile's tags do, shown while the tile is
 * pointed at or focused and always once given; on a picture's page, beside its name. Shape says
 * which: filled when given.
 */
export function HeartButton(props: {
  picture: { id: number; name: string; favourite: boolean };
  on: "tile" | "page";
  className?: string;
}) {
  const { picture, on } = props;
  const heart = useSetFavourite();
  // What was asked for, till the picture as the engine has it says the same.
  const [asked, setAsked] = useState<boolean | null>(null);
  if (asked !== null && asked === picture.favourite && !heart.isPending) setAsked(null);
  const given = asked ?? picture.favourite;
  const name = stem(picture.name);
  const title = heart.isError
    ? `Mado couldn't keep that: ${heart.error.message}`
    : given
      ? "A favourite: click to take its heart back"
      : "Give it a heart: a favourite";

  return (
    <button
      type="button"
      aria-pressed={given}
      aria-label={`Favourite ${name}`}
      title={title}
      onClick={(event) => {
        event.preventDefault(); // on a tile, it's not the tile's own link
        event.stopPropagation();
        const next = !given;
        setAsked(next);
        heart.mutate(
          { path: `/pictures/${picture.id}/favourite`, body: { favourite: next } },
          { onError: () => setAsked(null) },
        );
      }}
      className={cn(
        "press inline-flex shrink-0 cursor-pointer items-center justify-center",
        on === "tile"
          ? cn(
              // Over a picture: white on dark glass, as the tile's tags are.
              "absolute top-1.5 right-1.5 size-7 rounded-full bg-black/70 text-white outline-offset-1 transition-opacity duration-120 ease-mado hover:bg-black/85",
              given
                ? "opacity-100"
                : "opacity-0 focus-visible:opacity-100 group-focus-within:opacity-100 group-hover:opacity-100",
            )
          : cn(
              "size-9 rounded-6 border border-field-edge bg-transparent hover:bg-tint/6",
              given ? "text-accent-fg" : "text-fg-muted hover:text-fg",
            ),
        props.className,
      )}
    >
      <Heart
        size={on === "tile" ? 15 : 16}
        strokeWidth={1.8}
        fill={given ? "currentColor" : "none"}
        aria-hidden="true"
      />
    </button>
  );
}
