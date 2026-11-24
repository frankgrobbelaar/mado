import { type PointerEvent, type ReactNode, useEffect, useRef, useState } from "react";
import {
  type DepthStep,
  type EditStep,
  type FixStep,
  type LookStep,
  type PaintStep,
  type PictureDetails,
  type Plan,
  pictureAddress,
  type Recipe,
  type Region,
  type SizeStep,
  usePictureImage,
  usePreview,
  useQueueNow,
} from "@/lib/engine";
import { about, stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { withDepth } from "./depth";
import { brightening, fixed } from "./fixes";
import type { Zoom } from "./stage";
import { fitted, useBox } from "./stage-box";

export const LABEL = "absolute rounded-4 bg-black/70 px-2.5 py-1 text-12 text-white";
const MOST_PREVIEW = 4_000_000; // pixels the engine makes of a part at once
const SLOW = 600; // milliseconds after which a preview on the card says why it waits

/**
 * The picture as the Size tab makes it, as Picture-Size draws it. Fitted: the part kept framed
 * (the rest dimmed), the point it's cropped around to drag; or, extending, the new edges as
 * LaMa draws them. At 100% or 400%: before and after, the line between them dragged to compare,
 * a part of the picture made at full detail, moved by dragging; after carries the look and the
 * painting style chosen on the Looks tab too, as Save makes them.
 */
export function SizeStage(props: {
  picture: PictureDetails;
  /** The edits made on the Edit tab, which before and after both show; null with none. */
  edit: EditStep | null;
  /** The fixes chosen on the Fix tab, which after carries; null with none. */
  fix?: FixStep | null;
  /** The depth tools chosen on the Depth tab, which after carries; null with none. */
  depth?: DepthStep | null;
  plan: Plan;
  size: SizeStep;
  /** The look chosen on the Looks tab, which after carries; null with none. */
  look: LookStep | null;
  /** The painting style chosen on the Looks tab, which after carries too; null with none. */
  paint?: PaintStep | null;
  zoom: Zoom;
  onFocus: (focus: [number, number]) => void;
}) {
  const { picture, plan, size, zoom } = props;
  // Previews are asked for as the plan decided, so they follow it: a model downloaded since
  // makes Best the way, and the preview shows Best.
  const decided: SizeStep = {
    ...size,
    kind: size.kind ?? plan.kind,
    quality: size.quality ?? plan.quality,
    focus: size.focus ?? plan.focus,
  };
  return (
    <>
      {zoom === "fit" ? (
        <Fitted
          picture={picture}
          edit={props.edit}
          fix={props.fix ?? null}
          plan={plan}
          size={size}
          decided={decided}
          onFocus={props.onFocus}
        />
      ) : (
        <Compared
          picture={picture}
          edit={props.edit}
          fix={props.fix ?? null}
          depth={props.depth ?? null}
          plan={plan}
          size={decided}
          look={props.look}
          paint={props.paint ?? null}
          scale={zoom === "400" ? 4 : 1}
        />
      )}
      <p className="flex flex-wrap gap-x-4.5 gap-y-1 text-13 text-fg-muted">
        <span>
          After{" "}
          <span className="font-mono text-fg">
            {plan.width} × {plan.height}
          </span>
        </span>
        {plan.seconds > 0 && (
          <span>
            {capitalised(about(plan.seconds))} on{" "}
            {plan.place === "card" ? "your graphics card" : "the processor"}
            {!plan.measured && plan.method === "ai" && ", a guess till Mado has timed this PC"}
          </span>
        )}
        <span>
          {zoom === "fit" ? "Zoom to 100% to compare at full detail" : "Drag the line to compare"}
        </span>
      </p>
    </>
  );
}

/** The whole picture, the shape it takes drawn over it. */
function Fitted(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  fix: FixStep | null;
  plan: Plan;
  size: SizeStep;
  decided: SizeStep;
  onFocus: (focus: [number, number]) => void;
}) {
  const { picture, plan } = props;
  // Of the fixes, all of it shows a dark photo's brightening: the rest show at 100%.
  const lit = brightening(props.fix);
  const changed = props.edit !== null || lit !== null;
  const view = usePictureImage(changed ? null : pictureAddress(picture, "view"));
  // With edits or brightening, the picture shown under its shape is the picture as they leave it.
  const edited = usePreview(
    picture.id,
    changed
      ? {
          recipe: fixed({ edit: props.edit, size: null, look: null }, lit),
          side: "after",
          fit: { width: 2560, height: 2560 },
        }
      : null,
    { keep: true },
  );
  const shown = changed ? edited.address : view.address;
  const area = useRef<HTMLDivElement>(null);
  const box = useBox(area);
  const extending = plan.shape === "extend" && plan.sides !== "none";
  // What's shown fits the stage: the picture, or the canvas it's extended to.
  const ratio =
    ((picture.width ?? 1) / (picture.height ?? 1)) *
    (extending ? plan.canvas.width / plan.canvas.height : 1);
  const fit = fitted(box, ratio);
  const lama = plan.needs.find((each) => each.id === "lama");
  // The new edges alone, without the look, so they meet the picture under them seamlessly.
  const drawn = usePreview(
    picture.id,
    extending && !lama
      ? {
          recipe: fixed({ edit: props.edit, size: props.decided, look: null }, lit),
          side: "after",
          fit: { width: 1600, height: 1600 },
        }
      : null,
  );
  const [dragging, setDragging] = useState<[number, number] | null>(null);
  // Where the point was last put: the plan for it may still be on its way.
  const placed = props.size.focus ?? plan.focus;
  const focus = dragging ?? placed;

  function at(event: PointerEvent<HTMLElement>): [number, number] {
    const frame = (
      event.currentTarget.closest("[data-picture]") as HTMLElement
    ).getBoundingClientRect();
    const x = (event.clientX - frame.left) / frame.width;
    const y = (event.clientY - frame.top) / frame.height;
    return [Math.min(Math.max(x, 0), 1), Math.min(Math.max(y, 0), 1)];
  }

  // The picture's place within what's shown: all of it, or its middle part when extending.
  const inner = extending
    ? {
        left: (-plan.canvas.x / plan.canvas.width) * 100,
        top: (-plan.canvas.y / plan.canvas.height) * 100,
        width: (1 / plan.canvas.width) * 100,
        height: (1 / plan.canvas.height) * 100,
      }
    : { left: 0, top: 0, width: 100, height: 100 };

  return (
    <div ref={area} className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
      <div
        className="absolute"
        style={{ left: fit.left, top: fit.top, width: fit.width, height: fit.height }}
      >
        {extending && (
          <div aria-hidden="true" className="absolute inset-0 status-waiting opacity-40" />
        )}
        {extending && drawn.address && (
          <img
            src={drawn.address}
            alt=""
            draggable={false}
            className="absolute inset-0 size-full animate-fade-in object-fill"
          />
        )}
        <div
          data-picture
          className="absolute"
          style={{
            left: `${inner.left}%`,
            top: `${inner.top}%`,
            width: `${inner.width}%`,
            height: `${inner.height}%`,
          }}
        >
          {shown ? (
            <img
              src={shown}
              alt={stem(picture.name)}
              draggable={false}
              className="absolute inset-0 size-full animate-fade-in object-fill"
            />
          ) : (
            <span role="status" aria-label="Loading the picture" className="absolute inset-0" />
          )}
          {!extending && plan.sides !== "none" && (
            <>
              <div
                aria-hidden="true"
                className="absolute border border-white/85 border-dashed shadow-[0_0_0_9999px_rgba(12,12,14,0.5)]"
                style={{
                  left: `${plan.kept.x * 100}%`,
                  top: `${plan.kept.y * 100}%`,
                  width: `${plan.kept.width * 100}%`,
                  height: `${plan.kept.height * 100}%`,
                }}
              />
              <button
                type="button"
                aria-label="The point the crop is around: drag it to move it"
                className="absolute size-7 -translate-x-1/2 -translate-y-1/2 cursor-grab touch-none rounded-full border-2 border-white bg-black/30 shadow-float active:cursor-grabbing"
                style={{ left: `${focus[0] * 100}%`, top: `${focus[1] * 100}%` }}
                onPointerDown={(event) => {
                  event.currentTarget.setPointerCapture(event.pointerId);
                  setDragging(at(event));
                }}
                onPointerMove={(event) => dragging && setDragging(at(event))}
                onPointerUp={(event) => {
                  if (dragging) props.onFocus(at(event));
                  setDragging(null);
                }}
                onKeyDown={(event) => {
                  const step = event.shiftKey ? 0.1 : 0.02;
                  const moves: Record<string, [number, number]> = {
                    ArrowLeft: [-step, 0],
                    ArrowRight: [step, 0],
                    ArrowUp: [0, -step],
                    ArrowDown: [0, step],
                  };
                  const move = moves[event.key];
                  if (!move) return;
                  event.preventDefault();
                  props.onFocus([
                    Math.min(Math.max(placed[0] + move[0], 0), 1),
                    Math.min(Math.max(placed[1] + move[1], 0), 1),
                  ]);
                }}
              />
            </>
          )}
        </div>
        {extending && (
          <div
            aria-hidden="true"
            className="absolute border border-white/85 border-dashed"
            style={{ inset: 0 }}
          />
        )}
      </div>
      <span className={cn(LABEL, "bottom-3 left-3")}>
        {lama ? `The new edges show once ${lama.name} is downloaded` : caption(plan, drawn.busy)}
      </span>
      {(drawn.problem ?? edited.problem) && (
        <p role="alert" className={cn(LABEL, "top-3 left-3 max-w-[80%] bg-black/80")}>
          {drawn.problem ?? edited.problem}
        </p>
      )}
    </div>
  );
}

/** Before and after at full detail on the Size tab: the picture made, after carrying the look
 * and the style, as Save makes it; before the picture only stretched. */
function Compared(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  fix: FixStep | null;
  depth: DepthStep | null;
  plan: Plan;
  size: SizeStep;
  look: LookStep | null;
  paint: PaintStep | null;
  scale: number;
}) {
  const { picture, plan, size, look, paint } = props;
  // A model still to download: extending needs LaMa on either side, the rest only after.
  const lama = plan.needs.some((each) => each.id === "lama");
  const waiting = plan.needs.map((each) => each.name).join(" and ");
  return (
    <PartsCompared
      picture={picture}
      width={plan.width}
      height={plan.height}
      start={startingPoint(plan)}
      before={lama ? null : { edit: props.edit, size, look: null }}
      after={
        waiting
          ? null
          : withDepth(fixed({ edit: props.edit, size, paint, look }, props.fix), props.depth)
      }
      label={`After · ${plan.label}`}
      waiting={waiting ? `After shows once ${waiting} is downloaded` : null}
      scale={props.scale}
      card={plan.place === "card"}
    />
  );
}

/** Before and after at full detail, a part of the picture made (`width` by `height`), the line
 * between them dragged or moved with the arrow keys, the part moved by dragging or with the arrow
 * keys, starting at `start` (fractions of it). A side whose recipe is null waits, `waiting` saying
 * why. Work on the graphics card that waits for the queue's picture says so. */
export function PartsCompared(props: {
  picture: PictureDetails;
  width: number;
  height: number;
  start: [number, number];
  before: Recipe | null;
  after: Recipe | null;
  label: string;
  waiting: string | null;
  scale: number;
  /** The previews are made on the graphics card, where the queue's picture may have it. */
  card: boolean;
  /** There's an after to compare with: without one, before alone, no line. */
  compare?: boolean;
}) {
  const { picture, scale } = props;
  const plan = { width: props.width, height: props.height };
  const area = useRef<HTMLDivElement>(null);
  const box = useBox(area);
  const pixels = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  // The part of the picture made that fills the stage at this zoom, in its pixels: on a big,
  // sharp screen no more than a preview may be, shown a little bigger to fill the stage.
  const wanted = { width: (box.width * pixels) / scale, height: (box.height * pixels) / scale };
  const within = Math.min(1, Math.sqrt(MOST_PREVIEW / (wanted.width * wanted.height)));
  const width = Math.max(16, Math.min(plan.width, Math.floor(wanted.width * within)));
  const height = Math.max(16, Math.min(plan.height, Math.floor(wanted.height * within)));
  const startKey = `${props.start[0]},${props.start[1]}`;
  const [centre, setCentre] = useState<[number, number]>(props.start);
  useEffect(() => {
    const [x = 0.5, y = 0.5] = startKey.split(",").map(Number);
    setCentre([x, y]);
  }, [startKey]);
  const region = regionAt(centre, width, height, plan);
  const [moved, setMoved] = useState<{ x: number; y: number } | null>(null);
  const grabbed = useRef<{ x: number; y: number } | null>(null);
  const [split, setSplit] = useState(0.5);
  const after = usePreview(
    picture.id,
    box.measured && props.after ? { recipe: props.after, side: "after", region } : null,
  );
  const before = usePreview(
    picture.id,
    box.measured && props.before ? { recipe: props.before, side: "before", region } : null,
  );
  const queue = useQueueNow().data;
  const slow = useSlow(after.busy);
  const shown = {
    width: (region.width * scale) / (pixels * within),
    height: (region.height * scale) / (pixels * within),
  };
  const offset = moved ? `translate(${moved.x}px, ${moved.y}px)` : undefined;

  function release(event: PointerEvent<HTMLDivElement>) {
    const from = grabbed.current;
    grabbed.current = null;
    setMoved(null);
    if (!from) return;
    const dx = ((event.clientX - from.x) * pixels * within) / scale;
    const dy = ((event.clientY - from.y) * pixels * within) / scale;
    moveBy(-dx, -dy);
  }

  /** The part moved by `dx` and `dy` pixels of the picture made. */
  function moveBy(dx: number, dy: number) {
    setCentre(([x, y]) => [
      Math.min(Math.max(x + dx / plan.width, 0), 1),
      Math.min(Math.max(y + dy / plan.height, 0), 1),
    ]);
  }

  return (
    // biome-ignore lint/a11y/useSemanticElements: a stage to move round, not a form's fieldset
    <div
      ref={area}
      role="group"
      // biome-ignore lint/a11y/noNoninteractiveTabindex: it takes the arrow keys, to move round
      tabIndex={0}
      aria-label="Move round the picture: drag it, or use the arrow keys"
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return; // the line between them has its own
        const step = event.shiftKey ? 1 : 0.25; // of the part shown
        const moves: Record<string, [number, number]> = {
          ArrowLeft: [-region.width * step, 0],
          ArrowRight: [region.width * step, 0],
          ArrowUp: [0, -region.height * step],
          ArrowDown: [0, region.height * step],
        };
        const move = moves[event.key];
        if (!move) return;
        event.preventDefault();
        moveBy(move[0], move[1]);
      }}
      onPointerDown={(event) => {
        if (event.button !== 0 || (event.target as HTMLElement).closest("[role='slider']")) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        grabbed.current = { x: event.clientX, y: event.clientY };
      }}
      onPointerMove={(event) => {
        const from = grabbed.current;
        if (from) setMoved({ x: event.clientX - from.x, y: event.clientY - from.y });
      }}
      onPointerUp={release}
      onPointerCancel={() => {
        grabbed.current = null;
        setMoved(null);
      }}
      className="relative min-h-60 flex-1 cursor-grab touch-none overflow-hidden rounded-6 bg-behind active:cursor-grabbing"
    >
      <Side address={before.address} shown={shown} offset={offset} label="Before" clip={null} />
      <Side
        address={after.address}
        shown={shown}
        offset={offset}
        label={props.label}
        clip={`inset(0 0 0 ${split * 100}%)`}
      />
      {props.compare !== false && <Slider split={split} onSplit={setSplit} />}
      <span className={cn(LABEL, "top-3 left-3 font-semibold")}>Before</span>
      {props.compare !== false && (
        <span className={cn(LABEL, "top-3 right-3 font-semibold")}>{props.label}</span>
      )}
      {props.waiting && (
        <span role="status" className={cn(LABEL, "bottom-3 left-3")}>
          {props.waiting}
        </span>
      )}
      {!props.waiting && (after.busy || before.busy) && (
        <span role="status" className={cn(LABEL, "bottom-3 left-3")}>
          {slow && props.card && queue?.working
            ? `Waiting for the graphics card: ${queue.batch} lets it go after the tile it's on`
            : "Making the preview…"}
        </span>
      )}
      {!after.busy && after.seconds !== null && (
        <span className={cn(LABEL, "bottom-3 left-3")}>
          Preview made in {after.seconds.toFixed(1)} s
        </span>
      )}
      {(after.problem ?? before.problem) && (
        <p role="alert" className={cn(LABEL, "bottom-3 left-3 max-w-[80%] bg-black/80")}>
          {after.problem ?? before.problem}
        </p>
      )}
    </div>
  );
}

export function Side(props: {
  address: string | null;
  shown: { width: number; height: number };
  offset: string | undefined;
  label: string;
  clip: string | null;
}) {
  return (
    <div
      className="absolute inset-0 grid place-items-center"
      style={props.clip ? { clipPath: props.clip } : undefined}
    >
      {props.address && (
        <img
          src={props.address}
          alt={props.label}
          draggable={false}
          className="max-w-none select-none [image-rendering:pixelated]"
          style={{ width: props.shown.width, height: props.shown.height, transform: props.offset }}
        />
      )}
    </div>
  );
}

/** The line between before and after, dragged, or moved with the arrow keys. */
export function Slider(props: { split: number; onSplit: (split: number) => void }) {
  const line = useRef<HTMLDivElement>(null);
  function follow(event: PointerEvent<HTMLElement>) {
    const area = line.current?.parentElement?.getBoundingClientRect();
    if (!area) return;
    props.onSplit(Math.min(Math.max((event.clientX - area.left) / area.width, 0), 1));
  }
  return (
    <div
      ref={line}
      className="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white"
      style={{ left: `${props.split * 100}%` }}
    >
      <div
        role="slider"
        tabIndex={0}
        aria-label="Drag to compare before and after"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(props.split * 100)}
        onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
        onPointerMove={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) follow(event);
        }}
        onKeyDown={(event) => {
          const step = event.key === "ArrowLeft" ? -0.05 : event.key === "ArrowRight" ? 0.05 : 0;
          if (!step) return;
          event.preventDefault();
          props.onSplit(Math.min(Math.max(props.split + step, 0), 1));
        }}
        className="pointer-events-auto absolute top-1/2 left-1/2 flex size-10 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full bg-white text-black shadow-float"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="m9 7-5 5 5 5M15 7l5 5-5 5" />
        </svg>
      </div>
    </div>
  );
}

/** Where the comparing starts, as fractions of the picture made: the point the crop is around. */
function startingPoint(plan: Plan): [number, number] {
  if (plan.shape === "extend") return [0.5, 0.5];
  const x = (plan.focus[0] - plan.kept.x) / plan.kept.width;
  const y = (plan.focus[1] - plan.kept.y) / plan.kept.height;
  return [Math.min(Math.max(x, 0), 1), Math.min(Math.max(y, 0), 1)];
}

/** A part of the picture made, `width` by `height`, centred on `centre` as far as its edges let. */
export function regionAt(
  centre: [number, number],
  width: number,
  height: number,
  plan: Pick<Plan, "width" | "height">,
): Region {
  const x = Math.round(
    Math.min(Math.max(centre[0] * plan.width - width / 2, 0), plan.width - width),
  );
  const y = Math.round(
    Math.min(Math.max(centre[1] * plan.height - height / 2, 0), plan.height - height),
  );
  return { x, y, width, height };
}

/** The words over the picture: what the shape does to it. */
function caption(plan: Plan, drawing: boolean): ReactNode {
  if (plan.sides === "none") return `Already ${plan.label}'s shape: all of it stays`;
  if (plan.shape === "extend")
    return drawing ? "LaMa is drawing the new edges…" : "The new edges are drawn by LaMa";
  return plan.focusFound ? "Cropped around the most detailed part" : "Cropped around your point";
}

export function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Whether something under way has taken long enough to say why it waits. */
export function useSlow(busy: boolean): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!busy) {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), SLOW);
    return () => window.clearTimeout(timer);
  }, [busy]);
  return slow;
}
