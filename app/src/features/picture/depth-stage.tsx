import { GripHorizontal } from "lucide-react";
import {
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  useRef,
  useState,
} from "react";
import {
  type DepthStep,
  type EditStep,
  type FixStep,
  type PictureDetails,
  type Plan,
  pictureAddress,
  type Recipe,
  type RestoreStep,
  usePictureImage,
  usePreview,
  useQueueNow,
} from "@/lib/engine";
import { about, stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { bandAt, bandOf, bandTo, depthNames, hasDepth, readsDepth } from "./depth";
import type { MotionMaker } from "./motion";
import { restored } from "./restore";
import { capitalised, LABEL, PartsCompared, useSlow } from "./size-stage";
import type { Zoom } from "./stage";
import { fitted, useBox } from "./stage-box";

const STEP = 128; // the preview's size moves in steps this big, so a window resized a little asks again only once
const EDGE = 10; // pixels either side of the band's edge that drag the edge, not the band

/**
 * The picture on the Depth tab, as its tools make it: fitted, a click choosing what portrait blur
 * keeps in focus (a ring marks it) and tilt-shift's band dragged into place (its edges dragged to
 * make it taller), the original shown while \ or "Hold to see the original" is held; at 100% or
 * 400%, before and after at full detail, as the Fix tab compares. As "3D photo", the video
 * playing once it's made.
 */
export function DepthStage(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  /** Restoring chosen on the Fix tab, which before and after both show once its models are here;
   * null with none. */
  restore?: RestoreStep | null;
  fix: FixStep | null;
  depth: DepthStep;
  onDepth: (depth: DepthStep) => void;
  /** Where portrait blur is in focus without a click: its subject's middle, once read. */
  focus: [number, number] | null;
  plan: Plan | null;
  zoom: Zoom;
  held: boolean;
  /** The depth model is still to download: what needs it waits. */
  waiting: string | null;
}) {
  const { picture, depth, plan, zoom } = props;
  const on = hasDepth(depth);
  const card = (plan?.depthPlace ?? plan?.place) === "card";
  const before = restored(
    { edit: props.edit, fix: props.fix, size: null, look: null },
    props.restore,
  );
  const shownDepth = props.waiting && readsDepth(depth) ? null : on ? depth : null;
  const after = shownDepth ? { ...before, depth: shownDepth } : null;
  const label = on ? `After · ${depthNames(depth)}` : "After";
  return (
    <>
      {zoom === "fit" ? (
        <Fitted {...props} after={after} label={label} card={card} />
      ) : (
        <PartsCompared
          picture={picture}
          width={picture.width ?? 1}
          height={picture.height ?? 1}
          start={depth.portrait?.focus ?? props.focus ?? [0.5, 0.5]}
          before={withoutNull(before)}
          after={after ? withoutNull(after) : null}
          label={label}
          waiting={on ? props.waiting : "Turn a tool on to compare before and after"}
          scale={zoom === "400" ? 4 : 1}
          card={card}
          compare={after !== null}
        />
      )}
      <p className="flex flex-wrap gap-x-4.5 gap-y-1 text-13 text-fg-muted">
        {on && plan && plan.depthSeconds > 0 && (
          <span>
            {capitalised(about(plan.depthSeconds))} on{" "}
            {card ? "your graphics card" : "the processor"}, as Save makes it
          </span>
        )}
        <span>
          {zoom !== "fit"
            ? "Drag the line to compare · drag the picture to move round it"
            : depth.portrait
              ? "Click what should be in focus · hold \\ to see the original"
              : depth.tilt
                ? "Drag the band into place · hold \\ to see the original"
                : "Nothing changes until you save"}
        </span>
      </p>
    </>
  );
}

/** A recipe without a fix step that's off. */
function withoutNull(recipe: Recipe & { fix: FixStep | null }): Recipe {
  const { fix, ...rest } = recipe;
  return fix ? { ...rest, fix } : rest;
}

function Fitted(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  restore?: RestoreStep | null;
  fix: FixStep | null;
  depth: DepthStep;
  onDepth: (depth: DepthStep) => void;
  focus: [number, number] | null;
  held: boolean;
  waiting: string | null;
  after: Recipe | null;
  label: string;
  card: boolean;
}) {
  const { picture, depth } = props;
  const area = useRef<HTMLDivElement>(null);
  const box = useBox(area);
  const fit = fitted(box, (picture.width ?? 1) / (picture.height ?? 1));
  const pixels = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const wanted = {
    width: Math.min(4096, Math.ceil((fit.width * pixels) / STEP) * STEP),
    height: Math.min(4096, Math.ceil((fit.height * pixels) / STEP) * STEP),
  };
  const plain = props.edit || props.fix || props.restore;
  const view = usePictureImage(plain ? null : pictureAddress(picture, "view"));
  const before = usePreview(
    picture.id,
    plain && box.measured
      ? {
          recipe: restored(
            {
              edit: props.edit,
              ...(props.fix ? { fix: props.fix } : {}),
              size: null,
              look: null,
            },
            props.restore,
          ),
          side: "after",
          fit: wanted,
        }
      : null,
    { keep: true },
  );
  const made = usePreview(
    picture.id,
    props.after && box.measured ? { recipe: props.after, side: "after", fit: wanted } : null,
    { keep: true },
  );
  const queue = useQueueNow().data;
  const slow = useSlow(made.busy);
  const original = plain ? before.address : view.address;
  const shown = props.held || !props.after ? original : (made.address ?? original);
  const problem = made.problem ?? before.problem ?? view.problem;
  const [dragging, setDragging] = useState<"band" | "top" | "bottom" | null>(null);
  const tilt = depth.tilt;
  const band = tilt ? bandOf(tilt) : null;
  const focus = depth.portrait ? (depth.portrait.focus ?? props.focus) : null;

  function at(event: ReactPointerEvent<HTMLDivElement>): [number, number] {
    const rect = event.currentTarget.getBoundingClientRect();
    return [
      Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
    ];
  }

  function down(event: ReactPointerEvent<HTMLDivElement>) {
    const [x, y] = at(event);
    if (tilt && band) {
      const near = EDGE / Math.max(fit.height, 1);
      // With portrait blur on too, a click inside the band chooses what's in focus: the band
      // moves by its edges and its grip.
      const grabbed =
        Math.abs(y - band.top) <= near
          ? "top"
          : Math.abs(y - band.bottom) <= near
            ? "bottom"
            : !depth.portrait && y > band.top && y < band.bottom
              ? "band"
              : null;
      if (grabbed) {
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragging(grabbed);
        return;
      }
    }
    if (depth.portrait) props.onDepth({ ...depth, portrait: { ...depth.portrait, focus: [x, y] } });
  }

  function move(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging || !tilt) return;
    const [, y] = at(event);
    props.onDepth({ ...depth, tilt: dragging === "band" ? bandAt(tilt, y) : bandTo(tilt, y) });
  }

  /** The arrow keys on the focus: across and down, by a little (more with Shift). */
  function nudgeFocus(event: ReactKeyboardEvent<HTMLButtonElement>) {
    const step = event.shiftKey ? 0.1 : 0.02;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const by = moves[event.key];
    if (!by || !focus || !depth.portrait) return;
    event.preventDefault();
    const held = (value: number) => Math.round(Math.min(1, Math.max(0, value)) * 1000) / 1000;
    props.onDepth({
      ...depth,
      portrait: { ...depth.portrait, focus: [held(focus[0] + by[0]), held(focus[1] + by[1])] },
    });
  }

  /** The arrow keys on the band's grip: up and down move it, left and right make it shorter or
   * taller. */
  function nudgeBand(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (!tilt) return;
    const step = event.shiftKey ? 0.1 : 0.02;
    const round = (value: number) => Math.round(value * 1000) / 1000;
    const edge = tilt.centre + tilt.height / 2;
    const next =
      event.key === "ArrowUp"
        ? bandAt(tilt, round(tilt.centre - step))
        : event.key === "ArrowDown"
          ? bandAt(tilt, round(tilt.centre + step))
          : event.key === "ArrowLeft"
            ? bandTo(tilt, round(edge - step / 2))
            : event.key === "ArrowRight"
              ? bandTo(tilt, round(edge + step / 2))
              : null;
    if (!next) return;
    event.preventDefault();
    props.onDepth({ ...depth, tilt: next });
  }

  return (
    <div ref={area} className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
      <div
        className={cn(
          "absolute touch-none select-none",
          depth.portrait ? "cursor-crosshair" : tilt ? "cursor-ns-resize" : "",
        )}
        style={{ left: fit.left, top: fit.top, width: fit.width, height: fit.height }}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={() => setDragging(null)}
        onPointerCancel={() => setDragging(null)}
      >
        {shown && (
          <img
            src={shown}
            alt={`${stem(picture.name)}${props.held || !props.after ? "" : `, ${props.label}`}`}
            draggable={false}
            className="pointer-events-none size-full animate-fade-in object-contain"
          />
        )}
        {band && !props.held && (
          <>
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 border-accent border-y-2 border-dashed bg-accent/5"
              style={{ top: `${band.top * 100}%`, height: `${(band.bottom - band.top) * 100}%` }}
            />
            <button
              type="button"
              aria-label="Tilt-shift's band: drag it, or move it with the up and down arrow keys; left and right make it shorter or taller"
              className="absolute right-2 flex h-8 w-5 -translate-y-1/2 cursor-ns-resize touch-none items-center justify-center rounded-full border border-accent bg-black/40 text-accent shadow-float"
              style={{ top: `${((band.top + band.bottom) / 2) * 100}%` }}
              onPointerDown={(event) => {
                event.stopPropagation();
                event.currentTarget.parentElement?.setPointerCapture(event.pointerId);
                setDragging("band");
              }}
              onKeyDown={nudgeBand}
            >
              <GripHorizontal aria-hidden="true" className="size-3.5 rotate-90" />
            </button>
          </>
        )}
        {focus && !props.held && (
          <button
            type="button"
            aria-label="What's in focus: click the picture to choose it, or move it with the arrow keys"
            className="absolute size-7 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-black/30 shadow-float"
            style={{ left: `${focus[0] * 100}%`, top: `${focus[1] * 100}%` }}
            onPointerDown={(event) => event.stopPropagation()}
            onKeyDown={nudgeFocus}
          />
        )}
      </div>
      <span className={cn(LABEL, "top-3 left-3 font-semibold")}>
        {props.held || !props.after ? "Original" : props.label}
      </span>
      {props.waiting && !problem && (
        <span role="status" className={cn(LABEL, "bottom-3 left-3")}>
          {props.waiting}
        </span>
      )}
      {!props.waiting && made.busy && !problem && (
        <span role="status" className={cn(LABEL, "bottom-3 left-3")}>
          {slow && props.card && queue?.working
            ? `Waiting for the graphics card: ${queue.batch} lets it go after the tile it's on`
            : "Making the preview…"}
        </span>
      )}
      {!props.waiting && !made.busy && made.seconds !== null && props.after && !problem && (
        <span className={cn(LABEL, "bottom-3 left-3")}>
          Preview made in {made.seconds.toFixed(1)} s
        </span>
      )}
      {problem && (
        <p role="alert" className={cn(LABEL, "bottom-3 left-3 max-w-[80%] bg-black/80")}>
          {problem}
        </p>
      )}
    </div>
  );
}

/** The 3D photo on the stage: the picture till it's made, how it's coming on, then the video
 * playing round and round (an animated WebP shown as a picture). */
export function MotionStage(props: { picture: PictureDetails; maker: MotionMaker }) {
  const { picture, maker } = props;
  const motion = maker.motion;
  const done = motion?.state === "done";
  const video = usePictureImage(done && motion ? `/motion/${motion.id}/video` : null);
  const view = usePictureImage(pictureAddress(picture, "view"));
  const making = maker.making || motion?.state === "waiting" || motion?.state === "making";
  return (
    <>
      <div className="relative flex min-h-60 flex-1 items-center justify-center overflow-hidden rounded-6 bg-behind">
        {done && video.address ? (
          motion?.format === "webp" ? (
            <img
              src={video.address}
              alt={`${stem(picture.name)}, moving through its depth`}
              className="max-h-full max-w-full animate-fade-in object-contain"
            />
          ) : (
            <video
              src={video.address}
              poster={view.address ?? undefined}
              aria-label={`${stem(picture.name)}, moving through its depth`}
              autoPlay
              loop
              muted
              playsInline
              className="size-full animate-fade-in object-contain"
            />
          )
        ) : (
          view.address && (
            <img
              src={view.address}
              alt={stem(picture.name)}
              className={cn(
                "max-h-full max-w-full object-contain",
                making && "opacity-60 transition-opacity duration-320 ease-mado",
              )}
            />
          )
        )}
        <span className={cn(LABEL, "top-3 left-3 font-semibold")}>
          {done ? "3D photo" : "Original"}
        </span>
        {making && (
          <span role="status" className={cn(LABEL, "bottom-3 left-3")}>
            Making the 3D photo · {Math.round((motion?.progress ?? 0) * 100)}%
          </span>
        )}
        {done && motion && (
          <span className={cn(LABEL, "bottom-3 left-3 font-mono")}>
            {motion.width} × {motion.height} · made in {motion.seconds?.toFixed(0) ?? "?"} s
          </span>
        )}
      </div>
      <p className="flex flex-wrap gap-x-4.5 gap-y-1 text-13 text-fg-muted">
        <span>
          {done
            ? "It plays round and round, as it will saved"
            : "Make the 3D photo to see it move: nothing is saved until you say"}
        </span>
      </p>
    </>
  );
}
