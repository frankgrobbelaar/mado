import { useRef, useState } from "react";
import {
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
  useTools,
} from "@/lib/engine";
import { about, stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { brightening, fixed, fixModels, fixNames, hasFix } from "./fixes";
import { hasRestore, restored, restoreModels, restoreNames } from "./restore";
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
  /** Restoring, settled, made before the fixes: its scratches filled and its colour show fitted
   * as at full detail. */
  restore?: RestoreStep | null;
  plan: Plan | null;
  zoom: Zoom;
}) {
  const { picture, fix, plan, zoom } = props;
  const tools = useTools();
  const restore = hasRestore(props.restore) ? props.restore : null;
  const fixing = hasFix(fix);
  const on = fixing || restore !== null;
  const quality = plan?.fixQuality ?? fix.jpeg?.quality ?? null;
  const missingFixes = fixModels(fix, quality);
  const missing = [...(restore ? restoreModels(restore) : []), ...missingFixes]
    .map((id) => tools.data?.find((tool) => tool.id === id))
    .filter((tool) => tool !== undefined && tool.state !== "ready")
    .map((tool) => tool?.name ?? "");
  // The fixes on find nothing to do in it (Dark photo on a picture that isn't dark).
  // (A plan for the picture as it is, still there as the fixes settle, says nothing of them.)
  const idle = on && plan !== null && !plan.asIs && plan.fix === null && plan.restore === null;
  // Only an empty mask leaves restoring nothing to do: colour and faded colours always change it.
  const waiting = idle
    ? fixing
      ? "Nothing changes: the fixes on find nothing to do in it"
      : "Nothing changes: there are no scratches or dust to fill"
    : missing.length
      ? `After shows once ${[...new Set(missing)].join(" and ")} is downloaded`
      : null;
  const names = [restore ? restoreNames(restore) : "", fixing ? fixNames(fix) : ""]
    .filter(Boolean)
    .join(", ");
  const label = on ? `After · ${names}` : "After";
  const card = (plan?.fixPlace ?? plan?.restorePlace ?? plan?.place) === "card";
  const before = { edit: props.edit, size: null, look: null };
  const after =
    on && !waiting
      ? restored(fixed({ edit: props.edit, size: null, look: null }, fixing ? fix : null), restore)
      : null;
  // All of it shows restoring and the brightening, which need no model past restoring's own.
  const lit = idle ? null : brightening(fix);
  const fittedAfter =
    (lit || restore) && !(restore && waiting)
      ? restored(fixed({ edit: props.edit, size: null, look: null }, lit), restore)
      : null;
  const fittedNames = [restore ? restoreNames(restore) : "", lit ? fixNames(lit) : ""]
    .filter(Boolean)
    .join(", ");
  return (
    <>
      {zoom === "fit" ? (
        <FittedCompare
          picture={picture}
          edit={props.edit}
          after={fittedAfter}
          label={`After · ${fittedNames}`}
          waiting={
            fittedAfter
              ? null
              : idle || waiting
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
        {on && plan && plan.fixSeconds + plan.restoreSeconds > 0 && (
          <span>
            {capitalised(about(plan.fixSeconds + plan.restoreSeconds))} on{" "}
            {card ? "your graphics card" : "the processor"}, as Save makes it
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
  after: Recipe | null;
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
