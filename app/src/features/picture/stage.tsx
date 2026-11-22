import { type PointerEvent, type ReactNode, useLayoutEffect, useRef } from "react";
import { type PictureDetails, pictureAddress, usePictureImage } from "@/lib/engine";
import { stem } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Zoom = "fit" | "100" | "400";

const SCALE = { fit: 0, "100": 1, "400": 4 } as const;

/**
 * The picture, large, on the grey behind pictures: fitted to the space (its view the size of a
 * screen), or at 100% or 400% (the picture itself at full size), where dragging it moves round
 * it. A picture that can't be shown says why, in the engine's words.
 */
export function Stage({
  picture,
  zoom,
  problem,
}: {
  picture: PictureDetails;
  zoom: Zoom;
  problem: (why: string) => ReactNode;
}) {
  const view = usePictureImage(pictureAddress(picture, "view"));
  const full = usePictureImage(zoom === "fit" ? null : pictureAddress(picture, "full"));
  const name = stem(picture.name);

  const why = (zoom === "fit" ? view.problem : (full.problem ?? view.problem)) ?? null;
  if (why && !(zoom === "fit" ? view.address : (full.address ?? view.address))) {
    return <>{problem(why)}</>;
  }
  if (zoom === "fit") {
    return (
      <div className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
        {view.address ? (
          <img
            src={view.address}
            alt={name}
            draggable={false}
            className="absolute inset-0 size-full animate-fade-in object-contain"
          />
        ) : (
          <Waiting />
        )}
      </div>
    );
  }
  return (
    <Zoomed
      address={full.address ?? view.address}
      name={name}
      width={picture.width ?? 0}
      height={picture.height ?? 0}
      scale={SCALE[zoom]}
      whole={full.address !== null}
    />
  );
}

/** A picture larger than its space: scrolled, or dragged, to see round it. */
export function Zoomed(props: {
  address: string | null;
  name: string;
  width: number;
  height: number;
  scale: number;
  whole: boolean;
}) {
  const area = useRef<HTMLDivElement>(null);
  const dragging = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  // At 100% a pixel of the picture is a pixel of the screen, however Windows scales the window.
  const ratio = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const width = (props.width * props.scale) / ratio;
  const height = (props.height * props.scale) / ratio;

  // Zooming starts at the picture's middle.
  useLayoutEffect(() => {
    const here = area.current;
    if (!here || props.scale === 0) return;
    here.scrollLeft = (here.scrollWidth - here.clientWidth) / 2;
    here.scrollTop = (here.scrollHeight - here.clientHeight) / 2;
  }, [props.scale]);

  function grab(event: PointerEvent<HTMLDivElement>) {
    const here = area.current;
    if (!here || event.button !== 0) return;
    here.setPointerCapture(event.pointerId);
    dragging.current = {
      x: event.clientX,
      y: event.clientY,
      left: here.scrollLeft,
      top: here.scrollTop,
    };
  }

  function move(event: PointerEvent<HTMLDivElement>) {
    const here = area.current;
    const from = dragging.current;
    if (!here || !from) return;
    here.scrollLeft = from.left - (event.clientX - from.x);
    here.scrollTop = from.top - (event.clientY - from.y);
  }

  return (
    <div
      ref={area}
      onPointerDown={grab}
      onPointerMove={move}
      onPointerUp={() => {
        dragging.current = null;
      }}
      onPointerCancel={() => {
        dragging.current = null;
      }}
      className="relative min-h-60 flex-1 cursor-grab touch-none overflow-auto rounded-6 bg-behind active:cursor-grabbing"
    >
      <div
        className="grid min-h-full min-w-full place-items-center"
        style={{ width: "max-content" }}
      >
        {props.address ? (
          <img
            src={props.address}
            alt={props.name}
            draggable={false}
            className="max-w-none select-none [image-rendering:pixelated]"
            style={{ width, height }}
          />
        ) : (
          <Waiting />
        )}
      </div>
      {!props.whole && props.address && (
        <span
          role="status"
          className="absolute top-3 left-3 rounded-4 bg-black/70 px-2.5 py-1 font-semibold text-12 text-white"
        >
          Bringing the picture at full size…
        </span>
      )}
    </div>
  );
}

/** The picture is on its way. */
function Waiting() {
  return (
    <span
      role="status"
      aria-label="Loading the picture"
      className="absolute inset-0 grid place-items-center"
    >
      <span aria-hidden="true" className={cn("size-2.5 rounded-full", "status-working")} />
    </span>
  );
}
