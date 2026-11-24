import { type ReactNode, useId } from "react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { pickFolder } from "@/lib/dialogs";
import {
  type DepthRead,
  type DepthStep,
  type MotionFacts,
  type PictureDetails,
  type Plan,
  type Quality,
  type Recipe,
  type Tool,
  useDownloadTool,
  useMotionFacts,
  useTools,
} from "@/lib/engine";
import { showInFolder, useExplorer } from "@/lib/explorer";
import { about, size as sizeOf, split } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  APERTURES,
  DEPTH_MODEL,
  FOG_COLOURS,
  FOG_START,
  hasDepth,
  PORTRAIT_START,
  readsDepth,
  stopWords,
  TILT_START,
} from "./depth";
import { ModelCard } from "./edit-tab";
import type { MotionChoices, MotionMaker } from "./motion";
import { SaveSection } from "./save-section";

export type DepthMode = "picture" | "motion";

const MODES = [
  { value: "picture", label: "Blur and fog" },
  { value: "motion", label: "3D photo" },
] as const;

const QUALITIES = [
  { value: "fast", label: "Fast" },
  { value: "best", label: "Best" },
] as const;

const WITH_SUITS = [{ value: "auto", label: "As this PC suits" }, ...QUALITIES] as const;

const MOVEMENTS = [
  { value: "push", label: "Push in" },
  { value: "sway", label: "Sway" },
  { value: "circle", label: "Circle" },
] as const;

const HUGE = 40; // megapixels: past this, the depth tools take long enough to say so first

/**
 * The Depth tab: Mado reads how far away each part of the picture is, then blurs it as a lens
 * would (portrait blur, in focus where it's clicked), hazes it with distance (fog), keeps a band
 * in focus as a miniature looks (tilt-shift), or makes a 3D photo, a short video of it with the
 * view moving gently through it. No board draws it, so it's the Fix tab's patterns: a card of
 * rows, each a tool with its switch and its settings once on; and, as "3D photo", what the video
 * is and its own Save. The depth model is downloaded the first time it's needed.
 */
export function DepthTab(props: {
  picture: PictureDetails;
  depth: DepthStep;
  onDepth: (depth: DepthStep) => void;
  mode: DepthMode;
  onMode: (mode: DepthMode) => void;
  read: DepthRead | null;
  readProblem: string | null;
  recipe: Recipe | null;
  plan: Plan | null;
  settling: boolean;
  choices: MotionChoices;
  onChoices: (choices: MotionChoices) => void;
  maker: MotionMaker;
}) {
  const { picture, depth, read } = props;
  const tools = useTools();
  const model = tools.data?.find((tool) => tool.id === DEPTH_MODEL);
  const waiting = model && model.state !== "ready" ? model : null;
  const on = hasDepth(depth);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3.5">
      <Segmented
        label="Depth"
        value={props.mode}
        options={MODES}
        onChange={props.onMode}
        className="flex [&>button]:flex-1"
      />
      <Read read={read} problem={props.readProblem} />
      {props.mode === "picture" ? (
        <>
          <DepthControls depth={depth} onDepth={props.onDepth} read={read} />
          <DepthNotes picture={picture} depth={depth} read={read} plan={props.plan} />
          {waiting && (readsDepth(depth) || !on) && (
            <ModelCard
              tool={waiting}
              doing="Mado reads how far away each part is"
              offline="Tilt-shift goes by place, so it works now."
            />
          )}
          <SaveSection
            picture={picture}
            recipe={props.recipe}
            plan={props.settling ? null : props.plan}
            ready={props.recipe !== null && on}
            quiet={!on}
            caption={
              !on
                ? "Turn a tool on to see it: nothing changes until you save."
                : waiting && readsDepth(depth)
                  ? `Save waits for ${waiting.name}, still to download.`
                  : `As a new picture beside the original, ${
                      picture.raw ? "the RAW staying as it is." : "unless you choose to replace it."
                    }`
            }
          />
        </>
      ) : (
        <MotionPanel
          picture={picture}
          read={read}
          waiting={waiting}
          choices={props.choices}
          onChoices={props.onChoices}
          maker={props.maker}
        />
      )}
    </div>
  );
}

/** What Mado read of the picture's depth: how long it took, and where. */
function Read({ read, problem }: { read: DepthRead | null; problem: string | null }) {
  if (problem) {
    return (
      <p role="alert" className="text-13 text-broken-fg leading-normal">
        {problem}
      </p>
    );
  }
  if (!read?.read) return null;
  return (
    <p className="text-13 text-fg-muted leading-normal">
      {read.seconds === null ? (
        "Mado read how far away each part of it is."
      ) : (
        <>
          Mado read how far away each part of it is in{" "}
          <span className="font-mono text-fg">{read.seconds.toFixed(1)} s</span>
          {read.place === "processor" ? " on the processor" : ""}.
        </>
      )}{" "}
      {read.subject ? "Its subject stays sharp by its own edges." : ""}
    </p>
  );
}

/**
 * Portrait blur, fog and tilt-shift, a row each, as the Depth tab and a batch's Depth step ask
 * for them: a switch to turn each on, and its settings once it's on. `many`: a batch's, where
 * portrait blur is in focus at each picture's own subject.
 */
export function DepthControls(props: {
  depth: DepthStep;
  onDepth: (depth: DepthStep) => void;
  read?: DepthRead | null;
  many?: boolean;
}) {
  const { depth, onDepth } = props;
  const change = (part: Partial<DepthStep>) => onDepth({ ...depth, ...part });
  const portrait = depth.portrait;
  const stop = portrait
    ? APERTURES.reduce(
        (best, each, at) =>
          Math.abs(each - portrait.aperture) < Math.abs((APERTURES[best] ?? 0) - portrait.aperture)
            ? at
            : best,
        0,
      )
    : 0;
  return (
    <section
      aria-label="Depth tools"
      className="flex flex-col rounded-6 border border-edge bg-glass [&>*:first-child]:border-t-0"
    >
      <ToolRow
        title="Portrait blur"
        detail="What's farther or nearer than the point in focus blurs as a lens's does, more the farther it is, bright places turning to round discs. Blur what's behind it, on the Edit tab, blurs everything behind a part evenly and needs no depth."
        on={portrait !== null}
        onChange={(on) => change({ portrait: on ? PORTRAIT_START : null })}
      >
        {portrait && (
          <>
            <div className="flex items-center gap-3 text-13">
              <span className="shrink-0">Aperture</span>
              <Slider
                label="Aperture: the wider, the more blur"
                value={APERTURES.length - 1 - stop}
                max={APERTURES.length - 1}
                onChange={(value) =>
                  change({
                    portrait: {
                      ...portrait,
                      aperture: APERTURES[APERTURES.length - 1 - value] ?? 2.8,
                    },
                  })
                }
                valueText={stopWords(portrait.aperture)}
              />
              <span className="w-12 text-right font-mono">{stopWords(portrait.aperture)}</span>
            </div>
            <span className="text-13">The subject's edges</span>
            <Segmented
              label="How the subject's edges are found"
              value={portrait.quality ?? "auto"}
              options={WITH_SUITS}
              onChange={(chosen) =>
                change({
                  portrait: {
                    ...portrait,
                    quality: chosen === "auto" ? null : (chosen as Quality),
                  },
                })
              }
              className="flex [&>button]:flex-1"
            />
            <p className="text-12 text-fg-faint leading-normal">
              {props.many
                ? "Each picture is in focus at its own subject, found as Cut out finds it."
                : portrait.focus
                  ? "In focus where you clicked. Click the picture to choose again."
                  : props.read?.subject === false
                    ? "Mado found no subject in it, so it's in focus where it found the most to look at. Click the picture to choose what's in focus."
                    : "In focus at its subject, found as Cut out finds it. Click the picture to choose what's in focus."}
            </p>
            {!props.many && portrait.focus && (
              <Button
                size="sm"
                variant="ghost"
                className="self-start"
                onClick={() => change({ portrait: { ...portrait, focus: null } })}
              >
                In focus at its subject
              </Button>
            )}
          </>
        )}
      </ToolRow>
      <ToolRow
        title="Fog"
        detail="Haze that thickens with distance, the near clear and the far fading into it."
        on={depth.fog !== null}
        onChange={(on) => change({ fog: on ? FOG_START : null })}
      >
        {depth.fog && (
          <>
            <Amount
              label="How thick the fog is"
              said="Density"
              value={depth.fog.density}
              onChange={(density) => depth.fog && change({ fog: { ...depth.fog, density } })}
            />
            <div role="radiogroup" aria-label="Its colour" className="flex flex-wrap gap-2">
              {FOG_COLOURS.map((each) => {
                const chosen = depth.fog?.colour === each.colour;
                return (
                  // biome-ignore lint/a11y/useSemanticElements: a swatch, shown as a radio
                  <button
                    key={each.label}
                    type="button"
                    role="radio"
                    aria-checked={chosen}
                    onClick={() =>
                      depth.fog && change({ fog: { ...depth.fog, colour: each.colour } })
                    }
                    className={cn(
                      "press flex h-8 cursor-pointer items-center gap-2 rounded-full border px-3 text-13",
                      chosen ? "border-accent font-semibold" : "border-edge text-fg-muted",
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className="size-3.5 rounded-full border border-edge"
                      style={{
                        background:
                          each.colour ??
                          "linear-gradient(135deg, var(--color-fg-faint), var(--color-field))",
                      }}
                    />
                    {each.label}
                  </button>
                );
              })}
            </div>
          </>
        )}
      </ToolRow>
      <ToolRow
        title="Tilt-shift"
        detail="A band kept in focus and blur growing away from it, up and down the picture, colours a little richer: a town from above looks like a model of one. It goes by place, so it needs no depth."
        on={depth.tilt !== null}
        onChange={(on) => change({ tilt: on ? TILT_START : null })}
      >
        {depth.tilt && (
          <>
            <Amount
              label="How much blur grows away from the band"
              value={depth.tilt.strength}
              onChange={(strength) => depth.tilt && change({ tilt: { ...depth.tilt, strength } })}
            />
            <p className="text-12 text-fg-faint leading-normal">
              {props.many
                ? `The band is ${Math.round(depth.tilt.height * 100)}% of each picture's height, its middle ${Math.round(depth.tilt.centre * 100)}% of the way down.`
                : "Drag the band on the picture to move it; drag its edges to make it taller or shorter."}
            </p>
          </>
        )}
      </ToolRow>
    </section>
  );
}

/** A tool's row: what it does, its switch, and its settings once on. */
function ToolRow(props: {
  title: string;
  detail: string;
  on: boolean;
  onChange: (on: boolean) => void;
  children?: ReactNode;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-2.5 border-edge border-t px-3.5 py-3">
      <div className="flex items-start gap-3">
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <label htmlFor={id} className="cursor-pointer font-semibold text-14">
            {props.title}
          </label>
          <span id={`${id}-detail`} className="text-13 text-fg-muted leading-normal">
            {props.detail}
          </span>
        </span>
        <Switch
          id={id}
          className="mt-0.5"
          checked={props.on}
          onCheckedChange={props.onChange}
          aria-describedby={`${id}-detail`}
        />
      </div>
      {props.on && props.children}
    </div>
  );
}

/** A tool's amount, 0 to 100%. */
function Amount(props: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  said?: string;
}) {
  const percent = Math.round(props.value * 100);
  return (
    <div className="flex items-center gap-3 text-13">
      <span className="shrink-0">{props.said ?? "Strength"}</span>
      <Slider
        label={props.label}
        value={percent}
        onChange={(value) => props.onChange(value / 100)}
        valueText={`${percent}%`}
      />
      <span className="w-10 text-right font-mono">{percent}%</span>
    </div>
  );
}

/** The small things: a flat picture says so, a huge one says how long, see-through parts and a
 * grey picture stay as they are, and a picture too big to read. */
function DepthNotes(props: {
  picture: PictureDetails;
  depth: DepthStep;
  read: DepthRead | null;
  plan: Plan | null;
}) {
  const { read, plan, depth } = props;
  const said: string[] = [];
  if (read?.seeThrough) said.push("Its see-through parts stay as they are.");
  if (read?.grey) said.push("It stays black and white unless the fog is coloured.");
  const megapixels = read?.megapixels ?? 0;
  // By the depth tools' own plan: the picture's as it is is there a moment as they settle.
  const huge = hasDepth(depth) && megapixels >= HUGE && plan !== null && !plan.asIs;
  return (
    <div className="flex flex-col gap-1.5">
      {read?.flat && (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          Mado finds little depth in it: it reads as flat, as a scan or a screenshot does. Portrait
          blur and fog would barely change it; tilt-shift goes by place, so it still works.
        </p>
      )}
      {read?.tooBig && (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          It's {Math.round(megapixels)} megapixels, and Mado reads depth in pictures up to 100: make
          a smaller copy of it on the Size tab, then give that depth.
        </p>
      )}
      {huge && plan && (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          A big picture: {Math.round(megapixels)} megapixels, so Save takes{" "}
          {about(plan.depthSeconds)} for the depth tools. The stage shows it in moments.
        </p>
      )}
      {said.length > 0 && <p className="text-12 text-fg-faint leading-normal">{said.join(" ")}</p>}
    </div>
  );
}

/**
 * The 3D photo: how the view moves, for how long and how far, what fills what it uncovers, its
 * size and format; then making it, which the stage plays, and saving it beside the picture or
 * into a folder. Its own Save, as it's a video, not the picture.
 */
function MotionPanel(props: {
  picture: PictureDetails;
  read: DepthRead | null;
  waiting: Tool | null;
  choices: MotionChoices;
  onChoices: (choices: MotionChoices) => void;
  maker: MotionMaker;
}) {
  const { picture, choices, maker, read } = props;
  const facts = useMotionFacts(picture.id).data ?? null;
  const tools = useTools();
  const lama = tools.data?.find((tool) => tool.id === "lama");
  const ffmpeg = tools.data?.find((tool) => tool.id === "ffmpeg");
  const explorer = useExplorer();
  const change = (part: Partial<MotionChoices>) => props.onChoices({ ...choices, ...part });
  const noEncoder = facts?.ffmpeg === true && facts.encoder === null;
  const format = noEncoder ? "webp" : choices.format;
  const sizes = facts?.sizes ?? [];
  const chosenSize = sizes.find((each) => each.size === choices.size) ?? sizes[0] ?? null;
  const shown = format === "webp" ? (facts?.webp ?? null) : chosenSize;
  const bytes = shown ? Math.round((shown.bytes * choices.seconds) / 5) : null;
  const motion = maker.motion;
  const making = maker.making || motion?.state === "waiting" || motion?.state === "making";
  const needsLama = choices.fill === "best" && lama && lama.state !== "ready" ? lama : null;
  const needsFfmpeg = format === "mp4" && facts !== null && !facts.ffmpeg && ffmpeg ? ffmpeg : null;
  const can =
    !props.waiting && !needsLama && !needsFfmpeg && facts !== null && !read?.tooBig && !making;
  const ask = { ...choices, format };
  return (
    <>
      <section
        aria-label="3D photo"
        className="flex flex-col gap-3 rounded-6 border border-edge bg-glass px-3.5 py-3"
      >
        <p className="text-13 text-fg-muted leading-normal">
          A short video of the picture, the view moving gently through it by its depth, round and
          round.
        </p>
        <Choice label="How the view moves">
          <Segmented
            label="How the view moves"
            value={choices.motion}
            options={MOVEMENTS}
            onChange={(motion) => change({ motion })}
            className="flex [&>button]:flex-1"
          />
        </Choice>
        <Choice label="How long">
          <Segmented
            label="How long"
            value={String(choices.seconds)}
            options={(facts?.seconds ?? [3, 5, 8]).map((each) => ({
              value: String(each),
              label: `${each} s`,
            }))}
            onChange={(seconds) => change({ seconds: Number(seconds) })}
            className="flex [&>button]:flex-1"
          />
        </Choice>
        <Amount
          label="How far the view moves"
          said="How far"
          value={choices.amount}
          onChange={(amount) => change({ amount })}
        />
        <Choice label="What it uncovers behind near things">
          <Segmented
            label="What it uncovers behind near things"
            value={choices.fill}
            options={QUALITIES}
            onChange={(fill) => change({ fill: fill as Quality })}
            className="flex [&>button]:flex-1"
          />
          <p className="text-12 text-fg-faint leading-normal">
            Fast stretches what's beside it from farther away; Best draws it with LaMa.
          </p>
        </Choice>
        {!noEncoder && (
          <Choice label="As">
            <Segmented
              label="Saved as"
              value={choices.format}
              options={[
                { value: "mp4", label: "MP4 video" },
                { value: "webp", label: "Animated WebP" },
              ]}
              onChange={(chosen) => change({ format: chosen as MotionChoices["format"] })}
              className="flex [&>button]:flex-1"
            />
          </Choice>
        )}
        {format === "mp4" && sizes.length > 1 && (
          <Choice label="Size">
            <Segmented
              label="Size"
              value={choices.size}
              options={sizes.map((each) => ({
                value: each.size,
                label: each.size === "4k" ? "4K" : "1080p",
              }))}
              onChange={(chosen) => change({ size: chosen as MotionChoices["size"] })}
              className="flex [&>button]:flex-1"
            />
          </Choice>
        )}
        {shown && (
          <p className="font-mono text-12 text-fg-muted">
            {shown.width} × {shown.height} · {choices.seconds} s · about {sizeOf(bytes ?? 0)}
          </p>
        )}
        <MotionNotes
          facts={facts}
          read={read}
          format={format}
          hdr={picture.gainMap?.readable === true}
        />
      </section>
      {props.waiting && (
        <ModelCard
          tool={props.waiting}
          doing="Mado reads how far away each part is"
          offline="It waits till you're back."
        />
      )}
      {needsLama && (
        <ModelCard
          tool={needsLama}
          doing="What the view uncovers is drawn"
          offline="Fast stretches it instead, and works now."
        />
      )}
      {needsFfmpeg && <FfmpegCard tool={needsFfmpeg} />}
      <div className="sticky -bottom-4 -mx-4.5 mt-auto -mb-4 flex flex-col gap-2 bg-surface px-4.5 pt-2 pb-4">
        {making ? (
          <MotionProgress progress={motion?.progress ?? 0} onStop={maker.stop} />
        ) : motion?.state === "done" ? (
          <>
            <Button variant="primary" disabled={maker.saving} onClick={() => maker.keep(null)}>
              Save beside the picture
            </Button>
            <Button
              disabled={maker.saving}
              onClick={() =>
                void pickFolder("Save the 3D photo into").then(
                  (folder) => folder && maker.keep(folder),
                )
              }
            >
              Save into a folder…
            </Button>
            <Button variant="ghost" disabled={!can} onClick={() => maker.start(ask)}>
              Make it again as chosen
            </Button>
          </>
        ) : (
          <Button variant="primary" disabled={!can} onClick={() => maker.start(ask)}>
            Make the 3D photo
          </Button>
        )}
        {maker.saved && (
          <p role="status" className="text-center text-13 text-fg-muted leading-normal">
            Saved as <span className="font-mono">{maker.saved.name}</span> in{" "}
            {split(maker.saved.path)[0]}.{" "}
            <button
              type="button"
              className="cursor-pointer underline"
              onClick={() =>
                maker.saved && explorer.run(() => showInFolder(maker.saved?.path ?? ""))
              }
            >
              Show in folder
            </button>
          </p>
        )}
        {(motion?.state === "failed" || maker.problem || maker.saveProblem) && (
          <p role="alert" className="text-center text-13 text-broken-fg leading-normal">
            {motion?.problem ?? maker.problem ?? maker.saveProblem}
          </p>
        )}
        {!making && !motion && !maker.saved && (
          <p className="text-center text-13 text-fg-faint">
            It plays here first; nothing is saved until you say.
          </p>
        )}
      </div>
    </>
  );
}

function Choice(props: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-13">{props.label}</span>
      {props.children}
    </div>
  );
}

/** A 3D photo being made: how far it's got, and Stop. */
function MotionProgress(props: { progress: number; onStop: () => void }) {
  const percent = Math.round(props.progress * 100);
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex justify-between text-13">
        <span>Making the 3D photo…</span>
        <span className="font-mono text-fg-muted">{percent}%</span>
      </span>
      <div
        role="progressbar"
        aria-label="Making the 3D photo"
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
      <Button size="sm" variant="ghost" className="self-center" onClick={props.onStop}>
        Stop
      </Button>
    </div>
  );
}

/** The small things for a 3D photo: no H.264 encoder here, a picture with no depth to move
 * through, see-through parts on black, 4K needing the pixels, an HDR photo made an ordinary
 * video. */
function MotionNotes(props: {
  facts: MotionFacts | null;
  read: DepthRead | null;
  format: "mp4" | "webp";
  hdr: boolean;
}) {
  const { facts, read } = props;
  const said: string[] = [];
  if (props.hdr)
    said.push(
      "A 3D photo is an ordinary video, in sRGB, so an HDR photo's extra brightness isn't kept in it.",
    );
  if (read?.seeThrough) said.push("A video has no see-through parts: they show on black.");
  if (facts && props.format === "mp4" && facts.sizes.length === 1)
    said.push("4K needs a picture 3840 pixels across or more: this one would only be stretched.");
  return (
    <div className="flex flex-col gap-1.5">
      {facts?.ffmpeg && facts.encoder === null && (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          This PC has no H.264 encoder Mado may use (Windows' own, or an NVIDIA, AMD or Intel
          card's), so it makes the 3D photo as an animated WebP, which plays anywhere a picture
          does.
        </p>
      )}
      {read?.flat && (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          Mado finds little depth in it, so the view would barely move through it: it reads as flat,
          as a scan or a screenshot does.
        </p>
      )}
      {facts?.encoderName && props.format === "mp4" && (
        <p className="text-12 text-fg-faint leading-normal">Made with {facts.encoderName}.</p>
      )}
      {said.length > 0 && <p className="text-12 text-fg-faint leading-normal">{said.join(" ")}</p>}
    </div>
  );
}

/** ffmpeg to download first: it makes the video. */
function FfmpegCard({ tool }: { tool: Tool }) {
  const download = useDownloadTool();
  const busy = tool.state === "downloading" || tool.state === "unpacking";
  const percent = tool.size ? Math.round((tool.done / tool.size) * 100) : 0;
  return (
    <section
      aria-label="ffmpeg to download"
      className="flex flex-col gap-2 rounded-6 border border-dash border-dashed p-3"
    >
      <p className="text-13 leading-normal">
        An MP4 is made by ffmpeg, which Mado downloads (
        <span className="font-mono">{sizeOf(tool.size ?? 0)}</span>). An animated WebP needs nothing
        more.
      </p>
      {busy ? (
        <span className="font-mono text-12 text-fg-muted">Downloading · {percent}%</span>
      ) : (
        <Button
          size="sm"
          className="self-start"
          disabled={download.isPending}
          onClick={() => download.mutate({ path: `/tools/${tool.id}/download` })}
        >
          {tool.state === "failed" ? "Try again" : "Download ffmpeg"}
        </Button>
      )}
    </section>
  );
}
