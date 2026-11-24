import { type PointerEvent, useEffect, useId, useRef, useState } from "react";
import {
  type EditStep,
  type PictureDetails,
  pictureAddress,
  type Scratches,
  type Stroke,
  usePictureImage,
  usePreview,
  useQueueNow,
} from "@/lib/engine";
import { stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { fitted, useBox } from "./stage-box";

const LABEL = "absolute rounded-4 bg-black/70 px-2.5 py-1 text-12 text-white";
const STEP = 128; // the preview's size moves in steps this big, so a window resized a little asks again only once
const SLOW = 600; // milliseconds after which finding them says why it's waiting

/**
 * The scratches' mask on the Fix tab's stage, before anything is filled: the picture as its edits
 * leave it, what Mado found over it in the accent (as the Edit tab's brush paints), and the
 * owner's strokes: painting adds what it missed, Alt takes away what isn't a scratch. Fitted, as
 * the Edit tab's stage is, so the brush paints the whole picture.
 */
export function ScratchStage(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  scratches: Scratches;
  strokes: Stroke[];
  brush: number;
  /** Finding them runs on the graphics card, so it can wait for the queue's picture. */
  card: boolean;
  onStroke: (stroke: Stroke) => void;
}) {
  const { picture, scratches } = props;
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
  const view = usePictureImage(props.edit ? null : pictureAddress(picture, "view"));
  const edited = usePreview(
    picture.id,
    props.edit && box.measured
      ? { recipe: { edit: props.edit, size: null, look: null }, side: "after", fit: wanted }
      : null,
    { keep: true },
  );
  const shown = props.edit ? edited.address : view.address;
  const [drawing, setDrawing] = useState<Stroke | null>(null);
  const [pointer, setPointer] = useState<[number, number] | null>(null);
  const slow = useSlow(scratches.busy);
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
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrawing({ points: [at(event)], size: props.brush, take: event.altKey });
  }

  function move(event: PointerEvent<HTMLDivElement>) {
    const [x, y] = at(event);
    setPointer([x, y]);
    if (!drawing) return;
    const [lastX, lastY] = drawing.points.at(-1) ?? [x, y];
    if (Math.hypot((x - lastX) * width, (y - lastY) * height) < Math.min(width, height) * 0.002)
      return; // a point only where the pointer has moved
    setDrawing({ ...drawing, points: [...drawing.points, [x, y]] });
  }

  function up() {
    if (drawing) props.onStroke(drawing);
    setDrawing(null);
  }

  const strokes = drawing ? [...props.strokes, drawing] : props.strokes;
  const short = Math.min(width, height);
  const problem = scratches.problem ?? edited.problem ?? view.problem;
  const working = scratches.busy
    ? slow && props.card && queue?.working
      ? `Waiting for the graphics card: ${queue.batch} lets it go after the tile it's on`
      : "Looking for scratches and dust…"
    : null;

  return (
    <div ref={area} className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
      <div
        data-picture
        className="checks absolute cursor-none touch-none select-none"
        style={{ left: fit.left, top: fit.top, width: fit.width, height: fit.height }}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onPointerLeave={() => setPointer(null)}
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
        <svg
          viewBox={`0 0 ${width} ${height}`}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 size-full"
        >
          <defs>
            <mask id={mask} maskUnits="userSpaceOnUse" x={0} y={0} width={width} height={height}>
              {scratches.address && (
                <image
                  href={scratches.address}
                  width={width}
                  height={height}
                  preserveAspectRatio="none"
                />
              )}
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
          <rect width={width} height={height} mask={`url(#${mask})`} className="fill-accent/55" />
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
      </div>
      <span className={cn(LABEL, "top-3 left-3 font-semibold")}>The mask</span>
      {(working || problem) && (
        <p
          role={problem ? "alert" : "status"}
          className={cn(LABEL, "bottom-3 left-3 max-w-[80%] bg-black/80")}
        >
          {problem ?? working}
        </p>
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
