import { Eraser, MousePointer2, Scissors, X } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useRef } from "react";
import { useOnline } from "@/components/shell/offline";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Slider } from "@/components/ui/slider";
import {
  type Behind,
  type Edit,
  type EditStep,
  type PictureDetails,
  type Plan,
  pictureAddress,
  type Quality,
  type Recipe,
  type Stroke,
  type Tool,
  useDownloadTool,
  usePc,
  usePictureImage,
  usePreview,
} from "@/lib/engine";
import { size as sizeOf } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { EditTool } from "./edit-stage";
import { bare, eraseModel, MODELS, type Picked, useNeed } from "./editing";
import { SaveSection } from "./save-section";

const TOOLS: { key: EditTool; label: string; icon: ReactNode }[] = [
  { key: "select", label: "Select", icon: <MousePointer2 size={20} strokeWidth={1.6} /> },
  { key: "erase", label: "Erase", icon: <Eraser size={20} strokeWidth={1.6} /> },
  { key: "cutout", label: "Cut out", icon: <Scissors size={20} strokeWidth={1.6} /> },
];

const QUALITIES = [
  { value: "fast", label: "Fast" },
  { value: "best", label: "Best" },
] as const;

const BEHIND = [
  { value: "nothing", label: "Nothing (PNG)" },
  { value: "colour", label: "A colour" },
  { value: "blurred", label: "The rest, blurred" },
] as const;

/** The colours a cut-out can go on: the picture's own greys and the two ends. */
const COLOURS = [
  { value: "#ffffff", label: "White" },
  { value: "#d9d9d9", label: "Light grey" },
  { value: "#7f7f7f", label: "Grey" },
  { value: "#000000", label: "Black" },
];

/** What a cut-out goes on, as the Edit tab keeps it. */
export interface Backing {
  behind: Behind;
  colour: string;
}

/**
 * The Edit tab, as Picture-Edit draws it: Select (click the picture to pick a part, then do
 * something with what's picked: erase it, cut it out, give it a look, blur what's behind it),
 * Erase (a brush for what clicking can't pick) and Cut out (the subject, without a click). Each
 * model is downloaded the first time it's needed, its size and progress said. Every edit is a
 * step of the picture's one recipe, made again at full size by Save; nothing changes till then.
 */
export function EditTab(props: {
  picture: PictureDetails;
  /** The edits made, which the small pictures show; null for none. */
  edit: EditStep | null;
  /** Why the picture is too big to edit, or null for one Mado edits. */
  tooBig: string | null;
  onSize: () => void;
  tool: EditTool;
  onTool: (tool: EditTool) => void;
  picked: Picked;
  onRemove: (at: number) => void;
  onStep: (by: 1 | -1) => void;
  edits: Edit[];
  /** An edit on its way, and why one couldn't be made. */
  applying: boolean;
  problem: string | null;
  onApply: (edit: Edit) => void;
  /** The last erase came out much smoother than what's round it. */
  smeared: boolean;
  onBest: () => void;
  onLook: () => void;
  quality: Quality;
  onQuality: (quality: Quality) => void;
  backing: Backing;
  onBacking: (backing: Backing) => void;
  brush: number;
  onBrush: (brush: number) => void;
  /** What the brush has painted, waiting for Erase. */
  strokes: Stroke[];
  onClearBrush: () => void;
  cutQuality: Quality;
  onCutQuality: (quality: Quality) => void;
  recipe: Recipe | null;
  plan: Plan | null;
  settling: boolean;
}) {
  const { tool, picked } = props;
  const tiles = useRef<Partial<Record<EditTool, HTMLButtonElement | null>>>({});
  const selecting = useNeed(tool === "select" ? MODELS.select : null);
  const erasing = useNeed(
    tool === "erase" || (tool === "select" && picked.parts.length > 0)
      ? eraseModel(props.quality)
      : null,
  );
  const cutting = useNeed(tool === "cutout" && props.cutQuality === "best" ? MODELS.cut : null);
  const bestErase = useNeed(props.smeared ? MODELS.best : null);
  const places = usePc().data?.editing;
  const nothing = picked.parts.length === 0;
  // The small copy "With what you picked" shows: the picture as its edits leave it (a camera
  // RAW's from its view, developed as its stage shows it: its thumbnail is its camera's own).
  const withWhat = tool === "select" && !props.tooBig && !selecting;
  const thumbnail = usePictureImage(
    withWhat && !props.edit
      ? pictureAddress(props.picture, props.picture.raw ? "view" : "thumbnail")
      : null,
  );
  const edited = usePreview(
    props.picture.id,
    withWhat && props.edit
      ? {
          recipe: { edit: props.edit, size: null, look: null },
          side: "after",
          fit: { width: 128, height: 128 },
        }
      : null,
    { keep: true },
  );
  const copy = props.edit ? edited.address : thumbnail.address;
  const painted = props.strokes.some((stroke) => !stroke.take);

  function move(event: KeyboardEvent<HTMLDivElement>) {
    const at = TOOLS.findIndex((each) => each.key === tool);
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    if (step === undefined) return;
    event.preventDefault();
    const next = TOOLS[(at + step + TOOLS.length) % TOOLS.length]?.key ?? tool;
    props.onTool(next);
    tiles.current[next]?.focus();
  }

  function cutOut(): Edit {
    return {
      kind: "cutout",
      parts: bare(picked.parts),
      behind: props.backing.behind,
      colour: props.backing.behind === "colour" ? props.backing.colour : null,
    };
  }

  const saveCaption = props.plan?.needs.length
    ? `Save waits for ${props.plan.needs.map((need) => need.name).join(" and ")}, still to download.`
    : props.edits.length === 0
      ? "Erase or cut out first; nothing changes until you save."
      : undefined;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3.5">
      <div
        role="radiogroup"
        aria-label="Edit tool"
        onKeyDown={move}
        className="grid grid-cols-3 gap-1.5"
      >
        {TOOLS.map((each) => {
          const chosen = each.key === tool;
          return (
            // biome-ignore lint/a11y/useSemanticElements: a tile with its picture, as the board draws it
            <button
              key={each.key}
              ref={(tile) => {
                tiles.current[each.key] = tile;
              }}
              type="button"
              role="radio"
              aria-checked={chosen}
              tabIndex={chosen ? 0 : -1}
              onClick={() => props.onTool(each.key)}
              className={cn(
                "press flex h-15.5 cursor-pointer flex-col items-center justify-center gap-1.25 rounded-6 border text-13",
                chosen
                  ? "border-accent bg-accent/10 font-semibold text-fg [&_svg]:text-accent-fg"
                  : "border-edge bg-glass font-medium text-fg hover:bg-raised [&_svg]:text-fg-muted",
              )}
            >
              <span aria-hidden="true">{each.icon}</span>
              {each.label}
            </button>
          );
        })}
      </div>

      {props.tooBig && <TooBig said={props.tooBig} onSize={props.onSize} />}

      {tool === "select" &&
        !props.tooBig &&
        (selecting ? (
          <ModelCard tool={selecting} doing="Select picks a part with a click" />
        ) : (
          <>
            <section aria-labelledby="picked" className="flex flex-col gap-2">
              <h2 id="picked" className="type-eyebrow">
                Picked
              </h2>
              {nothing ? (
                <p className="text-13 text-fg-muted leading-normal">
                  Nothing picked yet: click the picture to pick a part.
                </p>
              ) : (
                <div className="flex flex-wrap items-center gap-1.5">
                  {picked.parts.map((part, at) => (
                    <span
                      key={part.name}
                      className="inline-flex h-7.5 items-center gap-1.5 rounded-full bg-accent/15 pr-1 pl-2.5 font-medium text-13"
                    >
                      {part.name}
                      <button
                        type="button"
                        aria-label={`Let go of ${part.name}`}
                        onClick={() => props.onRemove(at)}
                        className="press grid size-6 cursor-pointer place-items-center rounded-full text-accent-fg hover:bg-tint/8"
                      >
                        <X size={12} strokeWidth={2.2} aria-hidden="true" />
                      </button>
                    </span>
                  ))}
                  <span className="ml-auto flex gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7.5 px-2 text-12"
                      disabled={(picked.parts.at(-1)?.choice ?? 0) <= 0}
                      onClick={() => props.onStep(-1)}
                    >
                      Smaller
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7.5 px-2 text-12"
                      disabled={
                        (picked.parts.at(-1)?.choice ?? 0) >=
                        (picked.parts.at(-1)?.choices ?? 1) - 1
                      }
                      onClick={() => props.onStep(1)}
                    >
                      Bigger
                    </Button>
                  </span>
                </div>
              )}
            </section>

            <section
              aria-labelledby="with"
              className="flex flex-col rounded-6 border border-edge bg-glass"
            >
              <h2 id="with" className="px-3.5 pt-3 pb-2 font-semibold text-13">
                With what you picked
              </h2>
              <Row
                picture={props.picture}
                copy={copy}
                outline={picked.outline}
                shows="erase"
                title="Erase it"
                detail="Fills it in from what's around it"
                action={
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={nothing || props.applying || erasing !== null}
                    onClick={() =>
                      props.onApply({
                        kind: "erase",
                        parts: bare(picked.parts),
                        strokes: [],
                        quality: props.quality,
                      })
                    }
                  >
                    Erase
                  </Button>
                }
              >
                <Segmented
                  label="How it's erased"
                  value={props.quality}
                  options={QUALITIES}
                  onChange={props.onQuality}
                  className="flex [&>button]:flex-1"
                />
                {erasing && !nothing && (
                  <ModelCard tool={erasing} doing={`Erasing at ${qualityName(props.quality)}`} />
                )}
              </Row>
              <Row
                picture={props.picture}
                copy={copy}
                outline={picked.outline}
                shows="cut"
                title="Cut it out"
                detail="A picture of just what you picked"
                action={
                  <Button
                    size="sm"
                    disabled={nothing || props.applying}
                    onClick={() => props.onApply(cutOut())}
                  >
                    Cut out
                  </Button>
                }
              >
                <BehindIt backing={props.backing} onBacking={props.onBacking} />
              </Row>
              <Row
                title="Give it a look"
                detail="Looks on just what you picked"
                action={
                  <Button size="sm" disabled={nothing} onClick={props.onLook}>
                    Looks
                  </Button>
                }
              />
              <Row
                title="Blur what's behind it"
                detail="Like a big camera lens"
                action={
                  <Button
                    size="sm"
                    disabled={nothing || props.applying}
                    onClick={() => props.onApply({ kind: "blur", parts: bare(picked.parts) })}
                  >
                    Blur
                  </Button>
                }
              />
            </section>
          </>
        ))}

      {tool === "erase" && !props.tooBig && (
        <section aria-labelledby="brush" className="flex flex-col gap-3">
          <h2 id="brush" className="type-eyebrow">
            Brush
          </h2>
          <p className="text-13 text-fg-muted leading-normal">
            Paint over what clicking can't pick: a wire, a scratch, a sign. Hold Alt to take some
            away.
          </p>
          <div className="flex items-center gap-3 text-13">
            <span className="w-10 text-fg-muted">Size</span>
            <Slider
              label="Brush size"
              min={1}
              max={20}
              value={Math.round(props.brush * 100)}
              onChange={(value) => props.onBrush(value / 100)}
              valueText={`${Math.round(props.brush * 100)}% of the picture's shorter side`}
            />
            <span className="w-10 text-right font-mono">{Math.round(props.brush * 100)}%</span>
          </div>
          <Segmented
            label="How it's erased"
            value={props.quality}
            options={QUALITIES}
            onChange={props.onQuality}
            className="flex [&>button]:flex-1"
          />
          {erasing && (
            <ModelCard tool={erasing} doing={`Erasing at ${qualityName(props.quality)}`} />
          )}
          <span className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              size="sm"
              disabled={!painted || props.applying || erasing !== null}
              onClick={() =>
                props.onApply({
                  kind: "erase",
                  parts: [],
                  strokes: props.strokes,
                  quality: props.quality,
                })
              }
            >
              Erase
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={props.strokes.length === 0}
              onClick={props.onClearBrush}
            >
              Clear the brush
            </Button>
          </span>
        </section>
      )}

      {tool === "cutout" && !props.tooBig && (
        <section aria-labelledby="subject" className="flex flex-col gap-3">
          <h2 id="subject" className="type-eyebrow">
            The subject
          </h2>
          <p className="text-13 text-fg-muted leading-normal">
            Mado finds what the picture is of and cuts it out: no click needed.
          </p>
          <Segmented
            label="How it's cut out"
            value={props.cutQuality}
            options={QUALITIES}
            onChange={props.onCutQuality}
            className="flex [&>button]:flex-1"
          />
          {props.cutQuality === "best" && places?.cutBest === "processor" && (
            <p className="text-12 text-fg-muted leading-normal">
              Best runs on the processor on this PC, so it takes a little while.
            </p>
          )}
          <BehindIt backing={props.backing} onBacking={props.onBacking} />
          {cutting && <ModelCard tool={cutting} doing="Cutting out at Best" />}
          <Button
            variant="primary"
            size="sm"
            className="self-start"
            disabled={props.applying || cutting !== null}
            onClick={() =>
              props.onApply({
                kind: "subject",
                quality: props.cutQuality,
                behind: props.backing.behind,
                colour: props.backing.behind === "colour" ? props.backing.colour : null,
              })
            }
          >
            Cut out the subject
          </Button>
        </section>
      )}

      {props.smeared && (
        <section
          aria-label="The erase came out smooth"
          className="flex flex-col gap-2 rounded-6 border border-edge bg-glass p-3"
        >
          <p className="text-13 leading-normal">
            It came out smooth where the picture round it has detail. Best, with LaMa, often does
            better with big parts and busy places.
          </p>
          {bestErase ? (
            <ModelCard tool={bestErase} doing="Erasing at Best" />
          ) : (
            <Button
              size="sm"
              className="self-start"
              disabled={props.applying}
              onClick={props.onBest}
            >
              Try Best
            </Button>
          )}
        </section>
      )}
      {props.problem && (
        <p role="alert" className="text-13 text-broken-fg leading-normal">
          {props.problem}
        </p>
      )}

      <SaveSection
        picture={props.picture}
        recipe={props.recipe}
        plan={props.settling ? null : props.plan}
        ready={props.recipe !== null}
        quiet={props.edits.length === 0}
        caption={saveCaption}
      />
    </div>
  );
}

function qualityName(quality: Quality): string {
  return quality === "best" ? "Best" : "Fast";
}

/** What's behind a cut-out, and its colour when it's a colour. */
export function BehindIt(props: { backing: Backing; onBacking: (backing: Backing) => void }) {
  const { backing, onBacking } = props;
  return (
    <>
      <Segmented
        label="Behind the cut-out"
        value={backing.behind}
        options={BEHIND}
        onChange={(behind) => onBacking({ ...backing, behind })}
        className="flex [&>button]:flex-1 [&>button]:px-1.5 [&>button]:text-12"
      />
      {backing.behind === "colour" && (
        <div role="radiogroup" aria-label="Its colour" className="flex items-center gap-2">
          {COLOURS.map((each) => (
            // biome-ignore lint/a11y/useSemanticElements: a swatch, which an input can't show
            <button
              key={each.value}
              type="button"
              role="radio"
              aria-checked={backing.colour === each.value}
              aria-label={each.label}
              title={each.label}
              onClick={() => onBacking({ ...backing, colour: each.value })}
              className={cn(
                "press size-6 cursor-pointer rounded-full border border-field-edge",
                backing.colour === each.value && "outline-2 outline-accent outline-offset-2",
              )}
              style={{ background: each.value }}
            />
          ))}
          <label className="flex cursor-pointer items-center gap-1.5 text-12 text-fg-muted">
            <input
              type="color"
              value={backing.colour}
              onChange={(event) => onBacking({ ...backing, colour: event.target.value })}
              className="size-6 cursor-pointer rounded-full border-0 bg-transparent p-0"
            />
            Another
          </label>
        </div>
      )}
    </>
  );
}

/** A picture too big to edit: why, and the way to make a smaller copy of it. */
export function TooBig(props: { said: string; onSize?: () => void }) {
  return (
    <section
      aria-label="Too big to edit"
      className="flex flex-col gap-2 rounded-6 border border-dash border-dashed p-3"
    >
      <p className="text-13 leading-normal">{props.said}</p>
      {props.onSize && (
        <Button size="sm" className="self-start" onClick={props.onSize}>
          Go to the Size tab
        </Button>
      )}
    </section>
  );
}

/** A row of "With what you picked": what it does, its button, and its own choices under it. */
function Row(props: {
  title: string;
  detail: string;
  action: ReactNode;
  picture?: PictureDetails;
  copy?: string | null;
  outline?: string;
  shows?: "erase" | "cut";
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 border-edge border-t px-3.5 py-2.5">
      <div className="flex items-center gap-3">
        {props.picture && props.shows && (
          <Small
            picture={props.picture}
            copy={props.copy ?? null}
            outline={props.outline ?? ""}
            shows={props.shows}
          />
        )}
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="font-semibold text-14">{props.title}</span>
          <span className="text-13 text-fg-muted">{props.detail}</span>
        </span>
        {props.action}
      </div>
      {props.children}
    </div>
  );
}

/** A small copy of the picture, as its edits leave it, with what's picked: painted over, for
 * erasing it; alone on the check, for cutting it out. Cropped to fill its place, as the board
 * draws it, never squashed. */
function Small(props: {
  picture: PictureDetails;
  /** The small copy of the picture, as its edits leave it. */
  copy: string | null;
  outline: string;
  shows: "erase" | "cut";
}) {
  const { picture } = props;
  const address = props.copy;
  const clip = `small-${props.shows}-${picture.id}`;
  // The picture's own shape: the outline, drawn in a frame 1000 square, is stretched over it.
  const width = picture.width ?? 4;
  const height = picture.height ?? 3;
  const stretched = `scale(${width / 1000} ${height / 1000})`;
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative h-11.5 w-16 shrink-0 overflow-hidden rounded-4 bg-behind",
        props.shows === "cut" && "checks",
      )}
    >
      {address && (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="xMidYMid slice"
          aria-hidden="true"
          className="absolute inset-0 size-full"
        >
          {props.shows === "cut" && props.outline && (
            <defs>
              <clipPath id={clip}>
                <path d={props.outline} fillRule="evenodd" transform={stretched} />
              </clipPath>
            </defs>
          )}
          <image
            href={address}
            width={width}
            height={height}
            preserveAspectRatio="none"
            clipPath={props.shows === "cut" && props.outline ? `url(#${clip})` : undefined}
          />
          {props.shows === "erase" && props.outline && (
            <path
              d={props.outline}
              fillRule="evenodd"
              transform={stretched}
              className="fill-accent/45"
            />
          )}
        </svg>
      )}
    </span>
  );
}

/** A model a tool waits for: downloaded the first time it's needed, its size and progress here,
 * and what to do while there's no network. */
export function ModelCard(props: { tool: Tool; doing: string }) {
  const { tool } = props;
  const download = useDownloadTool();
  const online = useOnline();
  const busy = tool.state === "downloading" || tool.state === "unpacking";
  const percent = tool.size ? Math.round((tool.done / tool.size) * 100) : 0;
  return (
    <section
      aria-label={`${tool.name} to download`}
      className="flex flex-col gap-2 rounded-6 border border-dash border-dashed p-3"
    >
      <p className="text-13 leading-normal">
        {props.doing} with {tool.name}, an AI model Mado downloads the first time it's needed (
        <span className="font-mono">{sizeOf(tool.size)}</span>). It stays on this PC.
      </p>
      {busy ? (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-12 text-fg-muted">
            {tool.state === "unpacking"
              ? "Checking it…"
              : `Downloading · ${sizeOf(tool.done)} of ${sizeOf(tool.size)} · ${percent}%`}
          </span>
          <div
            role="progressbar"
            aria-label={`Downloading ${tool.name}`}
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
      ) : online ? (
        <Button
          size="sm"
          className="self-start"
          disabled={download.isPending}
          onClick={() => download.mutate({ path: `/tools/${tool.id}/download` })}
        >
          {tool.state === "failed" ? "Try again" : `Download ${tool.name}`}
        </Button>
      ) : (
        <p className="text-13 text-fg-muted leading-normal">
          You're offline, so it waits till you're back. Cutting out the subject at Fast works now:
          its model came with Mado.
        </p>
      )}
      {tool.state === "failed" && tool.problem && (
        <p role="alert" className="text-12 text-broken-fg">
          {tool.problem}
        </p>
      )}
    </section>
  );
}
