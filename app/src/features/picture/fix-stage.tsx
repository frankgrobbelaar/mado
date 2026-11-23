import { useRef, useState } from "react";
import {
  type EditStep,
  type FixStep,
  type PictureDetails,
  type Plan,
  pictureAddress,
  usePictureImage,
  usePreview,
  useQueueNow,
  useTools,
} from "@/lib/engine";
import { about, stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { brightening, fixModels, fixNames, hasFix } from "./fixes";
import { capitalised, LABEL, PartsCompared, Side, Slider, useSlow } from "./size-stage";
import type { Zoom } from "./stage";
import { fitted, useBox } from "./stage-box";

const STEP = 128; // the preview's size moves in steps this big, so a window resized a little asks again only once

/**
 * The picture on the Fix tab, before and after its fixes, as the Size tab compares: fitted, the
 * line between them dragged across all of it, after showing a dark photo brightened (noise,
 * blur and blocks are too small to judge there, so they wait for 100%); at 100% or 400%, a part
 * made at full detail with every fix, moved by dragging. Before is the picture as its edits
 * leave it; after, with its fixes, at its own size: the Size tab's after carries them made
 * bigger.
 */
export function FixStage(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  /** The fixes, settled: the previews follow them once a slider stops. */
  fix: FixStep;
  plan: Plan | null;
  zoom: Zoom;
}) {
  const { picture, fix, plan, zoom } = props;
  const tools = useTools();
  const on = hasFix(fix);
  const quality = plan?.fixQuality ?? fix.jpeg?.quality ?? null;
  const missing = fixModels(fix, quality)
    .map((id) => tools.data?.find((tool) => tool.id === id))
    .filter((tool) => tool !== undefined && tool.state !== "ready")
    .map((tool) => tool?.name ?? "");
  // The fixes on find nothing to do in it (Dark photo on a picture that isn't dark).
  const idle = on && plan !== null && plan.fix === null;
  const waiting = idle
    ? "Nothing changes: the fixes on find nothing to do in it"
    : missing.length
      ? `After shows once ${missing.join(" and ")} is downloaded`
      : null;
  const label = on ? `After · ${fixNames(fix)}` : "After";
  const card = (plan?.fixPlace ?? plan?.place) === "card";
  const before = { edit: props.edit, size: null, look: null };
  const after = on && !waiting ? { edit: props.edit, fix, size: null, look: null } : null;
  // All of it shows the brightening only, which needs no model.
  const lit = idle ? null : brightening(fix);
  return (
    <>
      {zoom === "fit" ? (
        <FittedCompare
          picture={picture}
          edit={props.edit}
          after={lit ? { edit: props.edit, fix: lit, size: null, look: null } : null}
          label={`After · ${fixNames(lit ?? fix)}`}
          waiting={
            lit
              ? null
              : idle
                ? waiting
                : on
                  ? "Noise, blur and blocks show at 100%: zoom in to compare them"
                  : "Turn a fix on to compare before and after"
          }
          card={card}
        />
      ) : (
        <PartsCompared
          picture={picture}
          width={picture.width ?? 1}
          height={picture.height ?? 1}
          start={[0.5, 0.5]}
          before={before}
          after={after}
          label={label}
          waiting={on ? waiting : "Turn a fix on to compare before and after"}
          scale={zoom === "400" ? 4 : 1}
          card={card}
          compare={on && !idle}
        />
      )}
      <p className="flex flex-wrap gap-x-4.5 gap-y-1 text-13 text-fg-muted">
        {on && plan && plan.fixSeconds > 0 && (
          <span>
            {capitalised(about(plan.fixSeconds))} on {card ? "your graphics card" : "the processor"}
            , as Save makes it
          </span>
        )}
        <span>
          {zoom === "fit"
            ? "Drag the line to compare · zoom to 100% to judge noise, blur and blocks"
            : "Drag the line to compare · drag the picture to move round it"}
        </span>
      </p>
    </>
  );
}

/** Before and after over the whole picture, fitted to the stage, the line between them dragged
 * or moved with the arrow keys. */
function FittedCompare(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  after: { edit: EditStep | null; fix: FixStep; size: null; look: null } | null;
  label: string;
  waiting: string | null;
  card: boolean;
}) {
  const { picture } = props;
  const area = useRef<HTMLDivElement>(null);
  const box = useBox(area);
  const fit = fitted(box, (picture.width ?? 1) / (picture.height ?? 1));
  const pixels = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const wanted = {
    width: Math.min(4096, Math.ceil((fit.width * pixels) / STEP) * STEP),
    height: Math.min(4096, Math.ceil((fit.height * pixels) / STEP) * STEP),
  };
  const view = usePictureImage(props.edit ? null : pictureAddress(picture, "view"));
  const edited = usePreview(
    picture.id,
    props.edit && box.measured
      ? {
          recipe: { edit: props.edit, size: null, look: null },
          side: "after",
          fit: wanted,
        }
      : null,
    { keep: true },
  );
  const fixed = usePreview(
    picture.id,
    props.after && box.measured ? { recipe: props.after, side: "after", fit: wanted } : null,
    { keep: true },
  );
  const [split, setSplit] = useState(0.5);
  const queue = useQueueNow().data;
  const slow = useSlow(fixed.busy);
  const original = props.edit ? edited.address : view.address;
  const shown = { width: fit.width, height: fit.height };
  const problem = fixed.problem ?? edited.problem ?? view.problem;
  return (
    <div ref={area} className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
      <div
        className="absolute"
        style={{ left: fit.left, top: fit.top, width: fit.width, height: fit.height }}
      >
        <div className="relative size-full">
          <Side
            address={original}
            shown={shown}
            offset={undefined}
            label={stem(picture.name)}
            clip={null}
          />
          {props.after && (
            <Side
              address={fixed.address}
              shown={shown}
              offset={undefined}
              label={`${stem(picture.name)}, fixed`}
              clip={`inset(0 0 0 ${split * 100}%)`}
            />
          )}
          {props.after && <Slider split={split} onSplit={setSplit} />}
        </div>
      </div>
      <span className={cn(LABEL, "top-3 left-3 font-semibold")}>Before</span>
      {props.after && (
        <span className={cn(LABEL, "top-3 right-3 font-semibold")}>{props.label}</span>
      )}
      {props.waiting && !problem && (
        <span role="status" className={cn(LABEL, "bottom-3 left-3")}>
          {props.waiting}
        </span>
      )}
      {!props.waiting && fixed.busy && !problem && (
        <span role="status" className={cn(LABEL, "bottom-3 left-3")}>
          {slow && props.card && queue?.working
            ? `Waiting for the graphics card: ${queue.batch} lets it go after the tile it's on`
            : "Making the preview…"}
        </span>
      )}
      {!props.waiting && !fixed.busy && fixed.seconds !== null && !problem && (
        <span className={cn(LABEL, "bottom-3 left-3")}>
          Preview made in {fixed.seconds.toFixed(1)} s
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
