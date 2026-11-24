import { ImageOff } from "lucide-react";
import { useRef } from "react";
import { coming, percentOf, useRawReader } from "@/components/raw-reader";
import { type PictureItem, pictureAddress, usePictureImage } from "@/lib/engine";
import { cn } from "@/lib/utils";
import { useNear } from "./near";

/**
 * A picture's thumbnail, filling its box: fetched once it comes near the view and let go once
 * it's far away, so the grid can hold thousands. Until it's there, and for a picture with none
 * (a camera RAW waiting for Mado's RAW reader, one that won't open), a quiet stand-in says why,
 * in fewer words in a small box (`small`, a picture page's strip).
 */
export function Thumbnail({
  picture,
  lazy = true,
  small = false,
}: {
  picture: PictureItem;
  lazy?: boolean;
  small?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const near = useNear(box);
  const wanted = (near || !lazy) && picture.state === "ready";
  const { address, problem } = usePictureImage(
    wanted ? pictureAddress(picture, "thumbnail") : null,
  );

  return (
    <div ref={box} className="absolute inset-0 bg-behind">
      {address ? (
        <img
          src={address}
          alt=""
          draggable={false}
          className="size-full animate-fade-in object-cover"
        />
      ) : (
        <StandIn picture={picture} problem={problem} small={small} />
      )}
    </div>
  );
}

function StandIn(props: { picture: PictureItem; problem: string | null; small: boolean }) {
  const { picture, problem } = props;
  if (picture.state === "broken") {
    return (
      <span className="flex size-full flex-col items-center justify-center gap-1.5 bg-surface text-11 text-fg-muted">
        <span aria-hidden="true" className="status-problem size-3 rounded-2" />
        Won't open
      </span>
    );
  }
  if (picture.state === "waiting") return <ReaderComing small={props.small} />;
  return (
    <span
      title={problem ?? undefined}
      className={cn(
        "flex size-full items-center justify-center text-fg-faint",
        !problem && "opacity-0",
      )}
    >
      <ImageOff size={18} aria-hidden="true" />
    </span>
  );
}

/** A camera RAW's tile while Mado's RAW reader comes: how it's coming, in a few words (fewer in
 * a small box, the whole on hover). */
function ReaderComing({ small }: { small: boolean }) {
  const reader = useRawReader();
  const said = coming(reader)
    ? `Getting the RAW reader · ${percentOf(reader)}%`
    : reader?.state === "failed"
      ? "Needs the RAW reader"
      : "Waiting for the RAW reader";
  return (
    <span
      title={small ? said : undefined}
      className={cn(
        "flex size-full items-center justify-center bg-surface text-center text-11 text-fg-faint",
        small ? "px-1" : "px-2",
      )}
    >
      {small ? (coming(reader) ? `RAW · ${percentOf(reader)}%` : "RAW") : said}
    </span>
  );
}

/** The tag a picture's tile wears: what kind it is, where that's worth saying (an HDR photo's
 * HDR first, as what shows it differently on an HDR screen). */
export function tagOf(picture: PictureItem): string | null {
  if (picture.raw) return "RAW";
  if (picture.hdr) return "HDR";
  if (picture.format === "HEIC" || picture.format === "HEIF") return picture.format;
  return null;
}
