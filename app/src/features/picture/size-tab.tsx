import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import {
  type MadeSize,
  type Need,
  type PictureDetails,
  type PictureKind,
  type Plan,
  type Quality,
  type Recipe,
  type SizeStep,
  useDownloadTool,
  useRememberScreens,
  useSizes,
  useTools,
} from "@/lib/engine";
import { size as sizeOf } from "@/lib/format";
import { thisPcsScreens } from "@/lib/screens";
import { cn } from "@/lib/utils";
import { DeviceIcon } from "./device-icon";
import { SaveSection } from "./save-section";

const KINDS = [
  { value: "photo", label: "Photo" },
  { value: "drawing", label: "Drawing" },
  { value: "pixels", label: "Pixel art" },
  { value: "screenshot", label: "Screenshot" },
] as const;

const QUALITIES = [
  { value: "fast", label: "Fast" },
  { value: "best", label: "Best" },
] as const;

const SHAPES = [
  { value: "crop", label: "Crop around the subject" },
  { value: "extend", label: "Extend the edges" },
] as const;

/** A new size step for a size: the rest as Mado guesses, the focus as it finds it. */
export function sizeFor(size: string, before: SizeStep | null): SizeStep {
  return {
    size,
    shape: before?.shape ?? "crop",
    focus: null,
    kind: before?.kind ?? null,
    quality: before?.quality ?? null,
    clean: before?.clean ?? true,
  };
}

/**
 * The Size tab, as Picture-Size draws it: making the picture right for a screen (the devices),
 * the owner's own screens and prints at 300 dpi, the shape (cropped around its subject, or its
 * edges extended), the quality line with the model Mado chose, and Save, which makes the whole
 * recipe: the size, and the look chosen on the Looks tab. What it waits for (a model to
 * download) is offered in its place, and the job making it shows its progress here.
 */
export function SizeTab(props: {
  picture: PictureDetails;
  /** The size step chosen; null till one is. */
  chosen: SizeStep | null;
  onChosen: (size: SizeStep) => void;
  /** The whole recipe Save makes, and its plan (the last one shown while the next comes). */
  recipe: Recipe | null;
  plan: UseQueryResult<Plan>;
  /** The plan for the recipe as it is now, which Save opens with; null while it's on its way. */
  saving: Plan | null;
  /** The look is still changing, so the plan for it isn't here yet. */
  settling: boolean;
}) {
  const { picture, chosen, onChosen, plan } = props;
  const sizes = useSizes();
  const remember = useRememberScreens();
  const asked = useRef(false);
  const shown = plan.data && chosen ? plan.data : null;

  // This PC's screens, from the shell, remembered once each time the tab opens.
  useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    void thisPcsScreens().then((seen) => {
      if (seen.length) remember.mutate({ path: "/screens", body: { seen } });
    });
  }, [remember]);

  const pick = (size: MadeSize) => onChosen(sizeFor(size.id, chosen));
  const change = (part: Partial<SizeStep>) => chosen && onChosen({ ...chosen, ...part });

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3.5">
      <section aria-labelledby="for-a-screen" className="flex flex-col gap-2">
        <h2 id="for-a-screen" className="type-eyebrow">
          Make it for a screen
        </h2>
        <div className="grid grid-cols-2 gap-1.5">
          {sizes.data?.screens.map((each) => (
            <SizeButton
              key={each.id}
              size={each}
              chosen={chosen?.size === each.id}
              onPick={() => pick(each)}
            />
          ))}
        </div>
        {sizes.isError && (
          <p role="alert" className="text-13 text-broken-fg">
            {sizes.error.message}
          </p>
        )}
      </section>

      <section aria-labelledby="yours-and-prints" className="flex flex-col gap-2">
        <h2 id="yours-and-prints" className="type-eyebrow">
          Your screens · print at 300 dpi
        </h2>
        <div className="flex flex-wrap gap-1.5">
          {[...(sizes.data?.yours ?? []), ...(sizes.data?.prints ?? [])].map((each) => (
            <Chip
              key={each.id}
              chosen={chosen?.size === each.id}
              onClick={() => pick(each)}
              name={each.name}
              pixels={each.group === "yours" ? `${each.width} × ${each.height}` : null}
            />
          ))}
          <OtherSize
            chosen={chosen?.size.startsWith("other-") ?? false}
            onSize={(id) => onChosen(sizeFor(id, chosen))}
          />
        </div>
      </section>

      {chosen && (
        <section aria-labelledby="shape" className="flex flex-col gap-2">
          <h2 id="shape" className="type-eyebrow">
            Shape
          </h2>
          <Segmented
            label="Shape"
            value={chosen.shape}
            options={SHAPES}
            onChange={(shape) => change({ shape })}
            className="flex [&>button]:flex-1"
          />
          {shown && <p className="text-13 text-fg-faint leading-normal">{shown.note}</p>}
          {shown && chosen.shape === "crop" && shown.sides !== "none" && (
            <p className="text-12 text-fg-faint">
              {shown.focusFound
                ? "Around the most detailed part. Drag the point on the picture to choose."
                : "Around the point you chose. Drag it to move it."}
            </p>
          )}
          {shown && chosen.shape === "extend" && (
            <p className="text-12 text-fg-faint leading-normal">
              LaMa draws the new edges softly: it carries skies, walls and water on well, while
              people and busy detail at an edge come out smeared, so crop those instead.
            </p>
          )}
        </section>
      )}

      {chosen && plan.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {plan.error.message}
        </p>
      )}

      {shown && chosen && (
        <QualityCard
          plan={shown}
          size={chosen}
          onKind={(kind) => change({ kind })}
          onQuality={(quality) => change({ quality })}
          onClean={(clean) => change({ clean })}
        />
      )}

      {shown && shown.needs.length > 0 && (
        <Needs
          needs={shown.needs}
          onFast={
            shown.needs.some((need) => need.id !== "lama")
              ? () => change({ quality: "fast" })
              : null
          }
          onCrop={
            shown.needs.some((need) => need.id === "lama") ? () => change({ shape: "crop" }) : null
          }
          onReady={() => void plan.refetch()}
        />
      )}

      <SaveSection
        picture={picture}
        recipe={props.recipe}
        plan={props.settling ? null : props.saving}
        ready={shown !== null}
        caption={
          !chosen
            ? props.recipe?.look
              ? "Pick a screen or a print, or save the look alone on the Looks tab."
              : picture.pasted
                ? "Save keeps it as it is; pick a screen or a print to make it for one."
                : "Pick a screen or a print to see the picture made for it."
            : picture.pasted
              ? "As a new picture in a folder of yours: till then it's only in Mado."
              : `As a new picture beside the original${shown?.look ? `, with ${shown.look}` : ""}, ${
                  // Mado can't write camera RAW: a RAW is never replaced.
                  picture.raw ? "the RAW staying as it is." : "unless you choose to replace it."
                }`
        }
      />
    </div>
  );
}

export function SizeButton(props: { size: MadeSize; chosen: boolean; onPick: () => void }) {
  const { size, chosen } = props;
  return (
    <button
      type="button"
      aria-pressed={chosen}
      onClick={props.onPick}
      className={cn(
        "press flex h-13 cursor-pointer items-center gap-2.5 rounded-6 border px-2.5 text-left",
        chosen ? "border-accent bg-accent/10" : "border-edge bg-glass hover:bg-raised",
      )}
    >
      <DeviceIcon purpose={size.purpose} className={chosen ? "text-accent-fg" : "text-fg-muted"} />
      <span className="flex flex-col gap-px">
        <span className="font-semibold text-13">{size.name}</span>
        <span className={cn("font-mono text-12", chosen ? "text-accent-fg" : "text-fg-muted")}>
          {size.width} × {size.height}
        </span>
      </span>
    </button>
  );
}

export function Chip(props: {
  name: string;
  pixels: string | null;
  chosen: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={props.chosen}
      onClick={props.onClick}
      className={cn(
        "press inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border px-2.5 font-medium text-13",
        props.chosen ? "border-accent bg-accent/10" : "border-field-edge hover:bg-tint/6",
      )}
    >
      {props.name}
      {props.pixels && (
        <span className={cn("font-mono", props.chosen ? "text-accent-fg" : "text-fg-muted")}>
          {props.pixels}
        </span>
      )}
    </button>
  );
}

/** Any other size: pixels, or centimetres printed at 300 dpi. */
export function OtherSize(props: { chosen: boolean; onSize: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [width, setWidth] = useState("");
  const [height, setHeight] = useState("");
  const [unit, setUnit] = useState<"px" | "cm">("px");
  const id = useId();
  const ok = Number(width) > 0 && Number(height) > 0;
  if (!open) {
    return (
      <button
        type="button"
        aria-pressed={props.chosen}
        onClick={() => setOpen(true)}
        className={cn(
          "press inline-flex h-8 cursor-pointer items-center rounded-full border border-dashed px-2.5 font-medium text-13",
          props.chosen
            ? "border-accent bg-accent/10 text-fg"
            : "border-dash text-fg-muted hover:bg-tint/6",
        )}
      >
        Other size
      </button>
    );
  }
  return (
    <form
      className="flex w-full flex-wrap items-center gap-2 rounded-6 border border-edge bg-glass p-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ok) return;
        props.onSize(`other-${Number(width)}x${Number(height)}${unit === "cm" ? "cm" : ""}`);
        setOpen(false);
      }}
    >
      <label htmlFor={`${id}-w`} className="sr-only">
        Width
      </label>
      <input
        id={`${id}-w`}
        inputMode="decimal"
        placeholder="Width"
        value={width}
        onChange={(event) => setWidth(event.target.value.replace(/[^\d.]/g, ""))}
        className="h-8 w-18 rounded-6 border border-field-edge bg-field px-2 font-mono text-13"
      />
      <span aria-hidden="true" className="text-fg-muted">
        ×
      </span>
      <label htmlFor={`${id}-h`} className="sr-only">
        Height
      </label>
      <input
        id={`${id}-h`}
        inputMode="decimal"
        placeholder="Height"
        value={height}
        onChange={(event) => setHeight(event.target.value.replace(/[^\d.]/g, ""))}
        className="h-8 w-18 rounded-6 border border-field-edge bg-field px-2 font-mono text-13"
      />
      <Segmented
        label="Unit"
        value={unit}
        options={[
          { value: "px", label: "pixels" },
          { value: "cm", label: "cm" },
        ]}
        onChange={setUnit}
      />
      <Button size="sm" type="submit" disabled={!ok}>
        Use it
      </Button>
      <Button size="sm" variant="ghost" type="button" onClick={() => setOpen(false)}>
        Cancel
      </Button>
    </form>
  );
}

/** The quality line: the format, colours and about how big, what it suits, the model and the
 * two switches; "Change" opens what it is and Fast or Best. */
function QualityCard(props: {
  plan: Plan;
  size: SizeStep;
  onKind: (kind: PictureKind) => void;
  onQuality: (quality: Quality) => void;
  onClean: (clean: boolean) => void;
}) {
  const { plan, size } = props;
  const [open, setOpen] = useState(false);
  const clean = useId();
  const format = `${plan.format}${plan.formatQuality ? ` ${plan.formatQuality}` : ""}`;
  return (
    <section
      aria-labelledby="quality"
      className="flex flex-col gap-2 rounded-6 border border-edge bg-glass p-3"
    >
      <h2 id="quality" className="font-semibold text-13">
        Quality{" "}
        <span className="font-mono font-normal text-12 text-fg-muted">
          {format} · {plan.colour} · about {sizeOf(plan.bytes)}
        </span>
      </h2>
      <p className="text-13 text-fg-muted leading-normal">
        {plan.fits} {plan.how}{" "}
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((was) => !was)}
          className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
        >
          {open ? "Done" : "Change"}
        </button>
      </p>
      {open && (
        <div className="flex flex-col gap-2 border-rule border-t pt-2">
          <span className="text-12 text-fg-muted">What it is</span>
          <Segmented
            label="What it is"
            value={plan.kind}
            options={KINDS}
            onChange={props.onKind}
            className="flex flex-wrap [&>button]:flex-1"
          />
          {plan.method === "ai" && (
            <>
              <span className="text-12 text-fg-muted">The model</span>
              <Segmented
                label="The model"
                value={plan.quality}
                options={QUALITIES}
                onChange={props.onQuality}
              />
            </>
          )}
        </div>
      )}
      {plan.warning && (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          {plan.warning}
        </p>
      )}
      {plan.cleanedFirst ? (
        <p className="text-12 text-fg-faint leading-normal">
          {plan.method !== "ai"
            ? "The Fix tab takes noise and blocks out first."
            : plan.quality === "best"
              ? "The Fix tab takes noise and blocks out first, so Best has little left to clean."
              : "The Fix tab takes noise and blocks out first, so Fast doesn't clean them again."}
        </p>
      ) : (
        <>
          <div className="flex items-center gap-2.5 text-13">
            <Switch
              id={clean}
              checked={plan.cleanMatters ? size.clean : true}
              disabled={!plan.cleanMatters}
              onCheckedChange={props.onClean}
            />
            <label htmlFor={clean} className="cursor-pointer">
              Clean noise and blocks first
            </label>
          </div>
          {!plan.cleanMatters && plan.method === "ai" && (
            <p className="text-12 text-fg-faint">Best cleans as it makes the picture bigger.</p>
          )}
        </>
      )}
    </section>
  );
}

/** What a download a plan waits for is for, in a sentence. */
function neededFor(need: Need): string {
  const size = sizeOf(need.size);
  switch (need.id) {
    case "lama":
      return `Extending draws the new edges with ${need.name}, an AI model Mado downloads the first time it's asked for (${size}).`;
    case "realesrgan-x4plus":
      return `Best for photos is ${need.name}, a ${size} download Mado fetches the first time it's asked for.`;
    case "scunet":
      return `Noise comes out with ${need.name}, an AI model Mado downloads the first time a fix needs it (${size}).`;
    case "fbcnn":
      return `JPEG blocks come out at Best with ${need.name}, an AI model Mado downloads the first time it's asked for (${size}).`;
    case "nafnet":
      return `Blur is mended with ${need.name}, an AI model Mado downloads the first time it's asked for (${size}).`;
    case "birefnet-lite":
      return `Cutting out at Best is ${need.name}, an AI model Mado downloads the first time it's asked for (${size}).`;
    case "microast":
      return `A picture's own style is painted with ${need.name}, a small AI model Mado downloads the first time it's asked for (${size}).`;
    default:
      return need.id.startsWith("style-")
        ? `${need.name} paints with a small AI model Mado downloads the first time it's asked for (${size}).`
        : `It needs ${need.name}, an AI model Mado downloads the first time it's asked for (${size}).`;
  }
}

/** A model the plan waits for: downloaded the first time it's asked for, its progress here. */
export function Needs(props: {
  needs: Need[];
  onFast: (() => void) | null;
  onCrop: (() => void) | null;
  onReady: () => void;
}) {
  const tools = useTools();
  const download = useDownloadTool();
  const states = props.needs.map((need) => tools.data?.find((tool) => tool.id === need.id));
  const ready = states.every((tool) => tool?.state === "ready");
  const was = useRef(ready);
  const { onReady } = props;
  // Once what it waits for has come, the plan is asked again: it waits for nothing then.
  useEffect(() => {
    if (ready && !was.current) onReady();
    was.current = ready;
  }, [ready, onReady]);
  return (
    <section
      aria-label="Downloads it needs"
      className="flex flex-col gap-2 rounded-6 border border-dash border-dashed p-3"
    >
      {props.needs.map((need, index) => {
        const tool = states[index];
        const busy = tool?.state === "downloading" || tool?.state === "unpacking";
        const percent = tool?.size ? Math.round((tool.done / tool.size) * 100) : 0;
        return (
          <div key={need.id} className="flex flex-col gap-2">
            <p className="text-13 leading-normal">{neededFor(need)}</p>
            {busy ? (
              <div className="flex flex-col gap-1">
                <span className="font-mono text-12 text-fg-muted">
                  {tool?.state === "unpacking" ? "Checking it…" : `Downloading · ${percent}%`}
                </span>
                <div
                  role="progressbar"
                  aria-label={`Downloading ${need.name}`}
                  aria-valuenow={percent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className="h-1.5 overflow-hidden rounded-3 bg-track"
                >
                  <div
                    className="h-full bg-accent transition-[width] duration-320 ease-mado"
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
            ) : (
              <span className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  disabled={download.isPending}
                  onClick={() => download.mutate({ path: `/tools/${need.id}/download` })}
                >
                  {tool?.state === "failed" ? "Try again" : `Download ${need.name}`}
                </Button>
                {need.id === "lama" && props.onCrop && (
                  <Button size="sm" variant="ghost" onClick={props.onCrop}>
                    Crop instead
                  </Button>
                )}
                {need.id === "realesrgan-x4plus" && props.onFast && (
                  <Button size="sm" variant="ghost" onClick={props.onFast}>
                    Use Fast
                  </Button>
                )}
              </span>
            )}
            {tool?.state === "failed" && tool.problem && (
              <p role="alert" className="text-12 text-broken-fg">
                {tool.problem}
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}
