import { ImageOff } from "lucide-react";
import { useRef } from "react";
import { type PictureItem, pictureAddress, usePictureImage } from "@/lib/engine";
import { cn } from "@/lib/utils";
import { useNear } from "./near";

/**
 * A picture's thumbnail, filling its box: fetched once it comes near the view and let go once
 * it's far away, so the grid can hold thousands. Until it's there, and for a picture with none
 * (camera RAW, one that won't open), a quiet stand-in says why.
 */
export function Thumbnail({ picture, lazy = true }: { picture: PictureItem; lazy?: boolean }) {
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
        <StandIn picture={picture} problem={problem} />
      )}
    </div>
  );
}

function StandIn({ picture, problem }: { picture: PictureItem; problem: string | null }) {
  if (picture.state === "broken") {
    return (
      <span className="flex size-full flex-col items-center justify-center gap-1.5 bg-surface text-11 text-fg-muted">
        <span aria-hidden="true" className="status-problem size-3 rounded-2" />
        Won't open
      </span>
    );
  }
  if (picture.state === "raw") {
    return (
      <span className="flex size-full items-center justify-center bg-surface px-2 text-center text-11 text-fg-faint">
        Not readable yet
      </span>
    );
  }
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

/** The tag a picture's tile wears: what kind it is, where that's worth saying. */
export function tagOf(picture: PictureItem): string | null {
  if (picture.state === "raw") return "RAW";
  if (picture.format === "HEIC" || picture.format === "HEIF") return picture.format;
  return null;
}
