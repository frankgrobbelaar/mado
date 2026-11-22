import { useRef } from "react";
import {
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
import { fitted, useBox } from "./stage-box";

const LABEL = "absolute rounded-4 bg-black/70 px-2.5 py-1 text-12 text-white";
const STEP = 128; // the preview's size moves in steps this big, so a window resized a little asks again only once

/**
 * The picture with its look, as Picture-Looks draws it: fitted to the stage, every look shown on
 * this picture as the list is gone through, its touches where they'll fall on the picture saved.
 * With a size chosen it shows the picture as that makes it (cropped, or on its extended canvas).
 * Holding "Hold to see the original" shows it without the look. The last preview stays while the
 * next is made.
 */
export function LooksStage(props: {
  picture: PictureDetails;
  /** The size step as the plan decided it (null: the picture keeps its pixels). */
  size: SizeStep | null;
  /** The plan for the whole recipe, while a size is chosen: the picture made's shape. */
  plan: Plan | null;
  /** The look shown: the one pointed at, or the one picked; null when it changes nothing. */
  look: LookStep | null;
  /** What the label over the picture says of it: "Warm film · 60%". */
  label: string;
  held: boolean;
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
  const view = usePictureImage(size ? null : pictureAddress(picture, "view"));
  const plain = usePreview(
    picture.id,
    size && box.measured ? { recipe: { size, look: null }, side: "after", fit: wanted } : null,
  );
  const looked = usePreview(
    picture.id,
    look && box.measured ? { recipe: { size, look }, side: "after", fit: wanted } : null,
    { keep: true },
  );
  const original = size ? plain.address : view.address;
  const problem = looked.problem ?? plain.problem ?? view.problem;

  return (
    <div ref={area} className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
      <div
        className="absolute"
        style={{ left: fit.left, top: fit.top, width: fit.width, height: fit.height }}
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
