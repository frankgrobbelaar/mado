import { type PointerEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import {
  type EditStep,
  type PictureDetails,
  type Place,
  pictureAddress,
  type Stroke,
  usePictureImage,
  usePreview,
  useQueueNow,
} from "@/lib/engine";
import { stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Picked } from "./editing";
import { fitted, useBox } from "./stage-box";

const LABEL = "absolute rounded-4 bg-black/70 px-2.5 py-1 text-12 text-white";
const STEP = 128; // the preview's size moves in steps this big, so a window resized a little asks again only once
const SLOW = 600; // milliseconds after which a click or an edit says why it's waiting

export type EditTool = "select" | "erase" | "cutout";

const NAMES: Record<EditTool, string> = { select: "Select", erase: "Erase", cutout: "Cut out" };

/**
 * The picture on the Edit tab, as Picture-Edit draws it: as its edits leave it (or the original
 * while "\" is held), what's picked drawn round with the volt dashed line and the label of the
 * click that picked it, and the brush's strokes on the Erase tool. A click picks (Alt takes
 * away), the wheel steps the last part bigger or smaller, and dragging paints. What's
 * see-through after a cut-out shows the check behind it.
 */
export function EditStage(props: {
  picture: PictureDetails;
  /** The edits made, or null for none. */
  edit: EditStep | null;
  tool: EditTool;
  picked: Picked;
  /** A click or an edit on its way, and what it's doing ("Erasing…"). */
  working: string | null;
  /** Where that runs: only work on the card waits for the queue's picture. */
  workingOn?: Place | null;
  problem: string | null;
  strokes: Stroke[];
  brush: number;
  held: boolean;
  /** What the label over the picture says, in place of the tool's name. */
  label?: string;
  onClick: (x: number, y: number, alt: boolean) => void;
  onStep: (by: 1 | -1) => void;
  onStroke: (stroke: Stroke) => void;
}) {
  const { picture, picked, tool, held } = props;
  const area = useRef<HTMLDivElement>(null);
  const box = useBox(area);
  const width = picture.width ?? 1;
  const height = picture.height ?? 1;
  const fit = fitted(box, width / height);
  const pixels = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const wanted = {
    width: Math.min(4096, Math.ceil((fit.width * pixels) / STEP) * STEP),
    height: Math.min(4096, Math.ceil((fit.height * pixels) / STEP) * STEP),
  };
  const view = usePictureImage(pictureAddress(picture, "view"));
  const edited = usePreview(
    picture.id,
    props.edit && box.measured
      ? { recipe: { edit: props.edit, size: null, look: null }, side: "after", fit: wanted }
      : null,
    { keep: true },
  );
  const shown = props.edit && !held ? (edited.address ?? view.address) : view.address;
  const [drawing, setDrawing] = useState<Stroke | null>(null);
  const [pointer, setPointer] = useState<[number, number] | null>(null);
  const slow = useSlow(props.working !== null);
  const queue = useQueueNow().data;
  const mask = useId();

  function at(event: PointerEvent<HTMLElement>): [number, number] {
    const frame = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - frame.left) / frame.width;
    const y = (event.clientY - frame.top) / frame.height;
    return [Math.min(Math.max(x, 0), 1), Math.min(Math.max(y, 0), 1)];
  }

  function down(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const [x, y] = at(event);
    if (tool === "select") {
      props.onClick(x, y, event.altKey);
      return;
    }
    if (tool !== "erase") return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrawing({ points: [[x, y]], size: props.brush, take: event.altKey });
  }

  function move(event: PointerEvent<HTMLDivElement>) {
    if (tool !== "erase") return;
    const [x, y] = at(event);
    setPointer([x, y]);
    if (!drawing) return;
    const [lastX, lastY] = drawing.points.at(-1) ?? [x, y];
    if (Math.hypot((x - lastX) * width, (y - lastY) * height) < Math.min(width, height) * 0.004)
      return; // a point only where the pointer has moved
    setDrawing({ ...drawing, points: [...drawing.points, [x, y]] });
  }

  function up() {
    if (drawing) props.onStroke(drawing);
    setDrawing(null);
  }

  const strokes = drawing ? [...props.strokes, drawing] : props.strokes;
  const short = Math.min(width, height);
  const last = picked.parts.at(-1);
  const clicks = last ? last.clicks.length : 0;
  // A moment's work says nothing; longer, what it's doing, or, for work on the card, that the
  // queue has it.
  const waiting = !slow
    ? null
    : queue?.working && props.workingOn === "card"
      ? `Waiting for the graphics card: ${queue.batch} lets it go after the tile it's on`
      : props.working;

  return (
    <div ref={area} className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
      <div
        data-picture
        className={cn(
          "checks absolute touch-none select-none",
          tool === "select" && "cursor-crosshair",
          tool === "erase" && "cursor-none",
        )}
        style={{ left: fit.left, top: fit.top, width: fit.width, height: fit.height }}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onPointerLeave={() => setPointer(null)}
        onWheel={(event) => {
          if (tool === "select" && picked.parts.length) props.onStep(event.deltaY < 0 ? 1 : -1);
        }}
      >
        {shown ? (
          <img
            src={shown}
            alt={stem(picture.name)}
            draggable={false}
            className="pointer-events-none absolute inset-0 size-full animate-fade-in object-fill"
          />
        ) : (
          <span role="status" aria-label="Loading the picture" className="absolute inset-0" />
        )}
        {picked.outline && tool === "select" && !held && (
          <svg
            viewBox="0 0 1000 1000"
            preserveAspectRatio="none"
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 size-full"
          >
            <path
              d={picked.outline}
              fillRule="evenodd"
              className="fill-accent/25 stroke-accent"
              strokeWidth={1.5}
              strokeDasharray="5 4"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        )}
        {tool === "erase" && !held && (
          <svg
            viewBox={`0 0 ${width} ${height}`}
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 size-full"
          >
            <defs>
              <mask id={mask} maskUnits="userSpaceOnUse" x={0} y={0} width={width} height={height}>
                {strokes.map((stroke, index) => (
                  <Painted
                    // biome-ignore lint/suspicious/noArrayIndexKey: strokes are only added in order
                    key={index}
                    stroke={stroke}
                    width={width}
                    height={height}
                    short={short}
                  />
                ))}
              </mask>
            </defs>
            <rect width={width} height={height} mask={`url(#${mask})`} className="fill-accent/45" />
            {pointer && (
              <circle
                cx={pointer[0] * width}
                cy={pointer[1] * height}
                r={(props.brush * short) / 2}
                className="fill-none stroke-white"
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
              />
            )}
          </svg>
        )}
        {tool === "select" && last && picked.last && picked.outline && !held && (
          <>
            <span
              aria-hidden="true"
              className="pointer-events-none absolute size-3.5 -translate-1/2 rounded-full border-2 border-white shadow-[0_0_0_2px_rgb(0_0_0/0.35)]"
              style={{ left: `${picked.last.x * 100}%`, top: `${picked.last.y * 100}%` }}
            />
            <span
              className={cn(LABEL, "pointer-events-none mt-3 ml-2.5 whitespace-nowrap")}
              style={{ left: `${picked.last.x * 100}%`, top: `${picked.last.y * 100}%` }}
            >
              {last.name} · picked with {clicks === 1 ? "one click" : `${clicks} clicks`}
            </span>
          </>
        )}
      </div>
      <span className={cn(LABEL, "top-3 left-3 font-semibold")}>
        {held ? "Original" : (props.label ?? NAMES[tool])}
      </span>
      {(waiting || props.problem || edited.problem || picked.missed) && (
        <Note alert={Boolean(props.problem || edited.problem)}>
          {props.problem ??
            edited.problem ??
            waiting ??
            "Alt-click a part you picked to take some of it away."}
        </Note>
      )}
    </div>
  );
}

/** One stroke of the brush: painting in white, taking away in black. */
function Painted(props: { stroke: Stroke; width: number; height: number; short: number }) {
  const { stroke, width, height } = props;
  const colour = stroke.take ? "black" : "white";
  const thickness = stroke.size * props.short;
  if (stroke.points.length === 1) {
    const [[x, y]] = stroke.points as [[number, number]];
    return <circle cx={x * width} cy={y * height} r={thickness / 2} fill={colour} />;
  }
  return (
    <polyline
      points={stroke.points.map(([x, y]) => `${x * width},${y * height}`).join(" ")}
      fill="none"
      stroke={colour}
      strokeWidth={thickness}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  );
}

function Note(props: { alert: boolean; children: ReactNode }) {
  return (
    <p
      role={props.alert ? "alert" : "status"}
      className={cn(LABEL, "bottom-3 left-3 max-w-[80%] bg-black/80 text-12")}
    >
      {props.children}
    </p>
  );
}

/** Whether something has been on its way longer than a moment. */
function useSlow(busy: boolean): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setTimeout(() => setSlow(true), SLOW);
    return () => {
      window.clearTimeout(timer);
      setSlow(false);
    };
  }, [busy]);
  return slow && busy;
}
