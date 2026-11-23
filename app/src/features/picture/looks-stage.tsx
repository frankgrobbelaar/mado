import { type MouseEvent, useId, useRef } from "react";
import {
  type EditStep,
  type FixStep,
  type LookStep,
  type PictureDetails,
  type Plan,
  pictureAddress,
  type SizeStep,
  usePictureImage,
  usePreview,
} from "@/lib/engine";
import { stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { brightening, fixed } from "./fixes";
import { fitted, useBox } from "./stage-box";

const LABEL = "absolute rounded-4 bg-black/70 px-2.5 py-1 text-12 text-white";
const STEP = 128; // the preview's size moves in steps this big, so a window resized a little asks again only once

/**
 * The picture with its look, as Picture-Looks draws it: fitted to the stage, every look shown on
 * this picture as the list is gone through, its touches where they'll fall on the picture saved.
 * With a size chosen it shows the picture as that makes it (cropped, or on its extended canvas).
 * Holding "Hold to see the original" shows it without the look. The last preview stays while the
 * next is made. A click picks a part for "Only on a part" (Alt takes away), on the picture as its
 * edits leave it, through the shape the size step gives it; the part is hatched, as the board
 * draws it.
 */
export function LooksStage(props: {
  picture: PictureDetails;
  /** The edits made on the Edit tab, which the picture shows; null with none. */
  edit: EditStep | null;
  /** The fixes chosen on the Fix tab, which the picture shows; null with none. */
  fix?: FixStep | null;
  /** The size step as the plan decided it (null: the picture keeps its pixels). */
  size: SizeStep | null;
  /** The plan for the whole recipe, while a size is chosen: the picture made's shape. */
  plan: Plan | null;
  /** The look shown: the one pointed at, or the one picked; null when it changes nothing. */
  look: LookStep | null;
  /** What the label over the picture says of it: "Warm film · 60%". */
  label: string;
  held: boolean;
  /** Round the parts the look goes on, in a frame 1000 square over the picture itself. */
  outline: string;
  onPick: (x: number, y: number, alt: boolean) => void;
}) {
  const { picture, plan, look, held } = props;
  const lama = plan?.needs.find((each) => each.id === "lama");
  // A size whose new edges wait for LaMa shows the whole picture meanwhile.
  const size = props.size && plan && !lama ? props.size : null;
  const area = useRef<HTMLDivElement>(null);
  const box = useBox(area);
  const ratio =
    size && plan ? plan.width / plan.height : (picture.width ?? 1) / (picture.height ?? 1);
  const fit = fitted(box, ratio);
  const pixels = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const wanted = {
    width: Math.min(4096, Math.ceil((fit.width * pixels) / STEP) * STEP),
    height: Math.min(4096, Math.ceil((fit.height * pixels) / STEP) * STEP),
  };
  const edit = props.edit;
  // Of the fixes, all of it shows a dark photo's brightening: the rest show at full detail.
  const fix = brightening(props.fix);
  const changed = size !== null || edit !== null || fix !== null;
  const view = usePictureImage(changed ? null : pictureAddress(picture, "view"));
  const plain = usePreview(
    picture.id,
    changed && box.measured
      ? { recipe: fixed({ edit, size, look: null }, fix), side: "after", fit: wanted }
      : null,
  );
  const looked = usePreview(
    picture.id,
    look && box.measured
      ? { recipe: fixed({ edit, size, look }, fix), side: "after", fit: wanted }
      : null,
    { keep: true },
  );
  // What's shown is the picture itself, or the part of it (or more) the size step makes.
  const canvas = size && plan ? plan.canvas : { x: 0, y: 0, width: 1, height: 1 };
  const hatch = useId();

  function pick(event: MouseEvent<HTMLDivElement>) {
    const frame = event.currentTarget.getBoundingClientRect();
    const u = (event.clientX - frame.left) / frame.width;
    const v = (event.clientY - frame.top) / frame.height;
    const x = Math.min(Math.max(canvas.x + u * canvas.width, 0), 1);
    const y = Math.min(Math.max(canvas.y + v * canvas.height, 0), 1);
    props.onPick(x, y, event.altKey);
  }
  const original = changed ? plain.address : view.address;
  const problem = looked.problem ?? plain.problem ?? view.problem;

  return (
    <div ref={area} className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
      {/* biome-ignore lint/a11y/useKeyWithClickEvents lint/a11y/noStaticElementInteractions: a click on the picture picks a part; the keyboard picks none, as there's nothing to point at */}
      <div
        className="checks absolute cursor-crosshair select-none"
        style={{ left: fit.left, top: fit.top, width: fit.width, height: fit.height }}
        onClick={pick}
      >
        {original ? (
          <img
            src={original}
            alt={stem(picture.name)}
            draggable={false}
            className="absolute inset-0 size-full animate-fade-in object-fill"
          />
        ) : (
          <span role="status" aria-label="Loading the picture" className="absolute inset-0" />
        )}
        {looked.address && look && (
          <img
            src={looked.address}
            alt={`${stem(picture.name)} in ${props.label}`}
            draggable={false}
            className={cn(
              "absolute inset-0 size-full object-fill transition-opacity duration-120 ease-mado",
              held ? "opacity-0" : "opacity-100",
            )}
          />
        )}
        {props.outline && !held && fit.width > 0 && (
          <svg
            viewBox={`0 0 ${fit.width} ${fit.height}`}
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 size-full"
          >
            <defs>
              <pattern
                id={`${hatch}-lines`}
                width={10}
                height={10}
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)"
              >
                <rect width={2} height={10} className="fill-accent/40" />
              </pattern>
              <clipPath id={`${hatch}-part`}>
                <path
                  d={props.outline}
                  fillRule="evenodd"
                  transform={`translate(${(-canvas.x / canvas.width) * fit.width} ${(-canvas.y / canvas.height) * fit.height}) scale(${fit.width / (1000 * canvas.width)} ${fit.height / (1000 * canvas.height)})`}
                />
              </clipPath>
            </defs>
            <rect
              width={fit.width}
              height={fit.height}
              fill={`url(#${hatch}-lines)`}
              clipPath={`url(#${hatch}-part)`}
            />
          </svg>
        )}
      </div>
      <span className={cn(LABEL, "top-3 left-3 font-semibold")}>
        {held || !look ? "Original" : props.label}
      </span>
      {lama && (
        <span className={cn(LABEL, "bottom-3 left-3")}>
          The new edges show once {lama.name} is downloaded, on the Size tab
        </span>
      )}
      {!lama && ((look && looked.busy) || (size && plain.busy)) && !problem && (
        <span role="status" className={cn(LABEL, "bottom-3 left-3")}>
          Making the preview…
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
