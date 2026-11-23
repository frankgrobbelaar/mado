import { ImageOff } from "lucide-react";
import {
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  useRef,
  type WheelEvent,
} from "react";
import {
  type Monitor,
  monitorWallpaperAddress,
  type PictureChoice,
  pictureAddress,
  type StudioState,
  usePictureImage,
} from "@/lib/engine";
import { cn } from "@/lib/utils";
import { areaOf, type Box, boundsOf, type Cut, framed, laidAcross, ZOOM_MOST } from "./geometry";

/** A part being moved or zoomed, before the engine has it: whose (a monitor's key; null, the one
 * across all) and where it's cut. */
export interface Moving {
  monitor: string | null;
  cut: Cut;
}

const STEP = 0.05; // of the part seen, an arrow key moves it
const NEARER = 1.25; // + and - zoom by this much

/**
 * The owner's monitors drawn as Windows arranges them (one across all, with the gap for the
 * bezels), each with its name and size, and its part of the picture where it's cut, or the
 * wallpaper Windows has on it till one's chosen. Dragging a part moves where it's cut, the wheel
 * and + and - zoom, the arrow keys move it; a click picks the monitor.
 */
export function Monitors(props: {
  studio: StudioState;
  /** The monitor picked: its key. */
  selected: string | null;
  onSelect: (key: string) => void;
  moving: Moving | null;
  onMove: (moving: Moving) => void;
  /** A part moved or zoomed as far as it goes: the engine keeps it. */
  onCut: (moving: Moving) => void;
}) {
  const { studio } = props;
  const across = studio.layout === "across";
  const rects = studio.monitors.map((each) =>
    across ? each.place : { x: each.x, y: each.y, width: each.width, height: each.height },
  );
  const whole = rects.length ? boundsOf(rects) : { x: 0, y: 0, width: 16, height: 9 };
  const ratio = whole.width / whole.height;
  return (
    <fieldset className="m-0 min-w-0 border-0 p-0">
      <legend className="sr-only">Your monitors</legend>
      {/* A fieldset takes no shape of its own: the box inside it has the arrangement's. */}
      <div
        className="relative mx-auto"
        style={{
          aspectRatio: `${whole.width} / ${whole.height}`,
          width: `min(100%, ${ratio} * 54vh)`,
        }}
      >
        {studio.monitors.map((monitor, index) => {
          const rect = rects[index] as Box;
          const choice = choiceFor(studio, monitor);
          const cut =
            props.moving && sameChoice(props.moving, monitor, across) ? props.moving.cut : null;
          return (
            <Drawn
              key={monitor.key}
              monitor={monitor}
              style={{
                left: `${((rect.x - whole.x) / whole.width) * 100}%`,
                top: `${((rect.y - whole.y) / whole.height) * 100}%`,
                width: `${(rect.width / whole.width) * 100}%`,
                height: `${(rect.height / whole.height) * 100}%`,
              }}
              choice={choice}
              area={choice ? areaFor(studio, monitor, choice, cut) : null}
              pending={cut}
              selected={across ? choice !== null : props.selected === monitor.key}
              onSelect={() => props.onSelect(monitor.key)}
              onMove={(next) => props.onMove({ monitor: across ? null : monitor.key, cut: next })}
              onCut={(next) => props.onCut({ monitor: across ? null : monitor.key, cut: next })}
              cutOf={(next) => clamped(studio, monitor, choice, next)}
            />
          );
        })}
      </div>
    </fieldset>
  );
}

/** The picture chosen for a monitor: its own, or the one across all. */
export function choiceFor(studio: StudioState, monitor: Monitor): PictureChoice | null {
  const wanted = studio.layout === "across" ? null : monitor.key;
  return studio.choices.find((each) => each.monitor === wanted) ?? null;
}

function sameChoice(moving: Moving, monitor: Monitor, across: boolean) {
  return across ? moving.monitor === null : moving.monitor === monitor.key;
}

function cutOf(choice: PictureChoice): Cut {
  return { x: choice.x, y: choice.y, zoom: choice.zoom };
}

/** The part of the picture a monitor shows, as fractions of the picture. */
function areaFor(
  studio: StudioState,
  monitor: Monitor,
  choice: PictureChoice,
  moving: Cut | null,
): Box | null {
  const { width, height, focus } = choice.picture;
  if (!width || !height) return null;
  const cut = moving ?? cutOf(choice);
  if (studio.layout !== "across") {
    const made = framed(width, height, [monitor.width, monitor.height], choice.shape, cut, focus);
    return areaOf(made.canvas, width, height);
  }
  const whole = boundsOf(studio.monitors.map((each) => each.place));
  const made = framed(width, height, targetFor(studio, monitor), choice.shape, cut, focus);
  return areaOf(laidAcross(made.canvas, whole, monitor.place), width, height);
}

/** The pixels a monitor's part is cut for: its own, or the whole arrangement's, one across all. */
function targetFor(studio: StudioState, monitor: Monitor): [number, number] {
  if (studio.layout !== "across") return [monitor.width, monitor.height];
  const whole = boundsOf(studio.monitors.map((each) => each.place));
  return [Math.round(whole.width), Math.round(whole.height)];
}

/** A cut held to what can be shown: its middle where the part it makes sits. */
function clamped(
  studio: StudioState,
  monitor: Monitor,
  choice: PictureChoice | null,
  cut: Cut,
): Cut {
  if (!choice?.picture.width || !choice.picture.height || choice.shape === "extend") return cut;
  const zoom = Math.min(Math.max(cut.zoom, 1), ZOOM_MOST);
  const { width, height, focus } = choice.picture;
  const made = framed(width, height, targetFor(studio, monitor), "crop", { ...cut, zoom }, focus);
  return {
    x: round((made.canvas.x + made.canvas.width / 2) / width),
    y: round((made.canvas.y + made.canvas.height / 2) / height),
    zoom: round(zoom),
  };
}

function round(value: number) {
  return Math.round(value * 10_000) / 10_000;
}

function Drawn(props: {
  monitor: Monitor;
  style: CSSProperties;
  choice: PictureChoice | null;
  area: Box | null;
  /** The cut on its way to the engine, or being moved: where the next move starts. */
  pending: Cut | null;
  selected: boolean;
  onSelect: () => void;
  onMove: (cut: Cut) => void;
  onCut: (cut: Cut) => void;
  cutOf: (cut: Cut) => Cut;
}) {
  const { monitor, choice, area } = props;
  const picture = usePictureImage(choice ? pictureAddress(choice.picture, "view") : null);
  const own = usePictureImage(!choice && monitor.shown ? monitorWallpaperAddress(monitor) : null);
  const drag = useRef<{
    x: number;
    y: number;
    cut: Cut;
    area: Box;
    shown: [number, number];
    last: Cut | null;
  } | null>(null);
  const wheel = useRef<ReturnType<typeof setTimeout> | null>(null);
  const extend = choice?.shape === "extend";

  // Where a move starts: the cut on its way, else the picture's as the engine has it.
  const start = (): Cut | null =>
    !choice
      ? null
      : (props.pending ?? {
          x: choice.x ?? choice.picture.focus?.x ?? 0.5,
          y: choice.y ?? choice.picture.focus?.y ?? 0.5,
          zoom: choice.zoom,
        });

  function down(event: PointerEvent<HTMLButtonElement>) {
    const from = start();
    if (!from || !area || extend || event.button !== 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    // Outside a laid-out window (a test), a monitor is taken as 300 pixels across.
    const shownWidth = rect.width || 300;
    const shownHeight = rect.height || (shownWidth * monitor.height) / monitor.width;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      cut: from,
      area,
      shown: [shownWidth, shownHeight],
      last: null,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function move(event: PointerEvent<HTMLButtonElement>) {
    const now = drag.current;
    if (!now) return;
    const dx = event.clientX - now.x;
    const dy = event.clientY - now.y;
    if (!now.last && Math.hypot(dx, dy) < 3) return;
    const next = props.cutOf({
      x: (now.cut.x ?? 0.5) - (dx / now.shown[0]) * now.area.width,
      y: (now.cut.y ?? 0.5) - (dy / now.shown[1]) * now.area.height,
      zoom: now.cut.zoom,
    });
    now.last = next;
    props.onMove(next);
  }

  function up() {
    const now = drag.current;
    drag.current = null;
    if (now?.last) props.onCut(now.last);
  }

  function keys(event: KeyboardEvent<HTMLButtonElement>) {
    const from = start();
    if (!from || !area || extend) return; // an extended part shows it all: nothing to move
    const moves: Record<string, [number, number, number]> = {
      ArrowLeft: [-STEP, 0, 1],
      ArrowRight: [STEP, 0, 1],
      ArrowUp: [0, -STEP, 1],
      ArrowDown: [0, STEP, 1],
      "+": [0, 0, NEARER],
      "=": [0, 0, NEARER],
      "-": [0, 0, 1 / NEARER],
    };
    const step = moves[event.key];
    if (!step) return;
    event.preventDefault();
    const next = props.cutOf({
      x: (from.x ?? 0.5) + step[0] * area.width,
      y: (from.y ?? 0.5) + step[1] * area.height,
      zoom: from.zoom * step[2],
    });
    props.onCut(next);
  }

  function wheeled(event: WheelEvent<HTMLButtonElement>) {
    const from = start();
    if (!from || extend) return;
    const next = props.cutOf({
      ...from,
      zoom: from.zoom * (event.deltaY < 0 ? NEARER : 1 / NEARER),
    });
    props.onMove(next);
    if (wheel.current) clearTimeout(wheel.current);
    wheel.current = setTimeout(() => props.onCut(next), 300);
  }

  const label = `${monitor.name}, ${monitor.width} × ${monitor.height}${monitor.main ? ", the main one" : ""}${choice ? "" : ", no picture yet"}`;
  return (
    <button
      type="button"
      aria-pressed={props.selected}
      aria-label={label}
      onClick={props.onSelect}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onKeyDown={keys}
      onWheel={wheeled}
      title={choice && !extend ? "Drag to move where it's cut; the wheel, + and - zoom" : undefined}
      style={props.style}
      className={cn(
        "press absolute cursor-pointer touch-none overflow-hidden rounded-4 border border-line-strong bg-behind p-0 outline-offset-2 scheme-dark",
        props.selected && "outline-2 outline-accent",
        choice && !extend && "cursor-grab active:cursor-grabbing",
      )}
    >
      {choice && picture.address && area ? (
        <span className="absolute inset-0">
          {extend && (
            // Where Mado draws more, a soft hint of what's there till it's made.
            <img
              src={picture.address}
              alt=""
              draggable={false}
              className="absolute inset-0 size-full scale-110 object-cover opacity-55 blur-md"
            />
          )}
          <img
            src={picture.address}
            alt=""
            draggable={false}
            className="absolute max-w-none select-none"
            style={{
              left: `${(-area.x / area.width) * 100}%`,
              top: `${(-area.y / area.height) * 100}%`,
              width: `${100 / area.width}%`,
              height: `${100 / area.height}%`,
            }}
          />
          {extend && (
            <span
              aria-hidden="true"
              className="absolute outline-1 outline-white/70 outline-dashed"
              style={{
                left: `${(-area.x / area.width) * 100}%`,
                top: `${(-area.y / area.height) * 100}%`,
                width: `${100 / area.width}%`,
                height: `${100 / area.height}%`,
              }}
            />
          )}
        </span>
      ) : own.address ? (
        <img
          src={own.address}
          alt="Its wallpaper now"
          draggable={false}
          className="absolute inset-0 size-full object-cover opacity-60"
        />
      ) : (
        <span className="absolute inset-0 flex items-center justify-center text-white/45">
          {choice ? null : <ImageOff size={18} aria-hidden="true" />}
        </span>
      )}
      <span className="pointer-events-none absolute right-1.5 bottom-1.5 left-1.5 flex flex-wrap items-center gap-1.5">
        <span className="rounded-4 bg-black/70 px-1.5 py-px font-semibold text-11 text-white">
          {monitor.number ? `${monitor.number} · ` : ""}
          {monitor.name}
        </span>
        <span className="rounded-4 bg-black/70 px-1.5 py-px font-mono text-11 text-white">
          {monitor.width} × {monitor.height}
        </span>
        {monitor.main && (
          <span className="rounded-4 bg-black/70 px-1.5 py-px text-11 text-white">Main</span>
        )}
      </span>
    </button>
  );
}
