import { type ReactNode, useId } from "react";
import { Segmented } from "@/components/ui/segmented";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  type Fixes,
  type FixStep,
  type PictureDetails,
  type Plan,
  type Quality,
  type Recipe,
  useFixes,
  useTools,
} from "@/lib/engine";
import { about } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ModelCard } from "./edit-tab";
import { fixModels, jpegStrength } from "./fixes";
import { SaveSection } from "./save-section";

const QUALITIES = [
  { value: "fast", label: "Fast" },
  { value: "best", label: "Best" },
] as const;

const WITH_SUITS = [{ value: "auto", label: "As this PC has it" }, ...QUALITIES] as const;

const HUGE = 40; // megapixels: past this, the fixes take long enough to say so first

/** What each model does, as its card before it's downloaded says it. */
const DOING: Record<string, string> = {
  scunet: "Noise comes out",
  fbcnn: "JPEG blocks come out at Best",
  nafnet: "Blur is mended",
};

/**
 * The Fix tab: noise, blur from a shaking camera or a moving subject, JPEG blocks and a dark
 * photo, each turned on with its one setting, as no board draws it, so in the Edit tab's
 * patterns: a card of rows, each a fix. Mado suggests a fix only where it can measure the need
 * (a JPEG's own quality, how dark it is) and says when it found nothing; each model is
 * downloaded the first time it's needed, its size and progress said. The fixes are a step of the
 * picture's one recipe, made before it grows; nothing changes until Save.
 */
export function FixTab(props: {
  picture: PictureDetails;
  fix: FixStep;
  onFix: (fix: FixStep) => void;
  recipe: Recipe | null;
  /** The plan for the recipe as it is now; null while it's on its way. */
  plan: Plan | null;
  settling: boolean;
}) {
  const { picture, fix, plan } = props;
  const fixes = useFixes(picture);
  const tools = useTools();
  const found = fixes.data ?? null;
  const quality = plan?.fixQuality ?? fix.jpeg?.quality ?? null;
  const waiting = fixModels(fix, quality)
    .map((id) => tools.data?.find((tool) => tool.id === id))
    .filter((tool) => tool !== undefined && tool.state !== "ready");
  const on = Boolean(fix.noise || fix.blur || fix.jpeg || fix.dark);
  const megapixels = found?.megapixels ?? ((picture.width ?? 0) * (picture.height ?? 0)) / 1e6;
  // The fixes on change nothing in it (Dark photo on a picture that isn't dark): nothing to save.
  const nothing =
    on &&
    plan !== null &&
    plan.fix === null &&
    plan.method === "keep" &&
    plan.edit === null &&
    plan.look === null;
  const caption = !on
    ? "Turn a fix on to see it: nothing changes until you save."
    : nothing
      ? fix.dark && found?.stops === 0
        ? "Nothing to save: it isn't dark, so Dark photo leaves it as it is."
        : "Nothing to save: the fixes on change nothing in it."
      : waiting.length
        ? `Save waits for ${waiting.map((tool) => tool?.name).join(" and ")}, still to download.`
        : `As a new picture beside the original, ${
            picture.raw ? "the RAW staying as it is." : "unless you choose to replace it."
          }`;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3.5">
      <section aria-labelledby="fixes" className="flex flex-col gap-2">
        <h2 id="fixes" className="type-eyebrow">
          Fix what's wrong
        </h2>
        {found && <Found fixes={found} raw={picture.raw} />}
        {fixes.isPending && (
          <p role="status" className="text-13 text-fg-muted">
            Looking at what it needs…
          </p>
        )}
        {fixes.isError && (
          <p role="alert" className="text-13 text-broken-fg">
            Mado couldn't look at it: {fixes.error.message}
          </p>
        )}
      </section>

      <FixControls
        fix={fix}
        onFix={props.onFix}
        fixes={found}
        decided={quality}
        raw={picture.raw}
        screenshot={plan?.kind === "screenshot"}
      />

      <Notes picture={picture} fixes={found} plan={plan} on={on} megapixels={megapixels} />

      {waiting.map(
        (tool) =>
          tool && (
            <ModelCard
              key={tool.id}
              tool={tool}
              doing={DOING[tool.id] ?? tool.name}
              offline="The fixes whose models are here already work now."
            />
          ),
      )}

      <SaveSection
        picture={picture}
        recipe={props.recipe}
        plan={props.settling ? null : plan}
        ready={props.recipe !== null && !nothing}
        quiet={!on || nothing}
        caption={caption}
      />
    </div>
  );
}

/** What Mado measured: what it suggests, or that it found nothing it can measure to fix. */
function Found({ fixes, raw }: { fixes: Fixes; raw: boolean }) {
  const said: string[] = [];
  if (fixes.blocks && fixes.jpegQuality !== null)
    said.push(`JPEG blocks: it was saved at quality ${fixes.jpegQuality}`);
  if (fixes.dark) said.push(`dark: about ${fixes.stops.toFixed(1)} stops under`);
  if (said.length > 0) {
    return (
      <p className="text-13 text-fg-muted leading-normal">
        Mado suggests {said.join("; ")}. Noise and shake it can't measure: try them and compare.
      </p>
    );
  }
  const well =
    fixes.jpegQuality !== null
      ? `it's well exposed and saved at JPEG quality ${fixes.jpegQuality}`
      : raw
        ? "it's well exposed, and a camera RAW has no JPEG blocks"
        : "it's well exposed";
  return (
    <p role="status" className="text-13 text-fg-muted leading-normal">
      Nothing Mado can measure needs fixing: {well}. Noise and shake it can't measure: try them and
      compare.
    </p>
  );
}

/**
 * The four fixes, a row each, as the Fix tab and a batch's Fix step ask for them: a switch to
 * turn it on, and its one setting once it's on. `fixes`: what Mado measured of the picture, to
 * mark what it suggests and start JPEG blocks as hard as the picture was squeezed. `many`: a
 * batch's, where JPEG blocks come out as hard as each JPEG was squeezed, with no strength to set.
 */
export function FixControls(props: {
  fix: FixStep;
  onFix: (fix: FixStep) => void;
  fixes?: Fixes | null;
  /** JPEG blocks' model as the plan decided it; a batch's step offers "As this PC has it". */
  decided?: Quality | null;
  raw?: boolean;
  screenshot?: boolean;
  many?: boolean;
}) {
  const { fix, onFix, fixes } = props;
  const change = (part: Partial<FixStep>) => onFix({ ...fix, ...part });
  return (
    <section
      aria-label="Fixes"
      className="flex flex-col rounded-6 border border-edge bg-glass [&>*:first-child]:border-t-0"
    >
      <FixRow
        title="Noise"
        detail="Grain and speckles from a small camera or a dark room."
        on={fix.noise !== null}
        onChange={(on) => change({ noise: on ? { strength: 1 } : null })}
      >
        {fix.noise && (
          <Strength
            label="How much noise comes out"
            value={fix.noise.strength}
            onChange={(strength) => change({ noise: { strength } })}
          />
        )}
      </FixRow>
      <FixRow
        title="Blur"
        detail={
          props.screenshot
            ? "A screenshot isn't shaken: this mends photos taken with a shaking camera or of a moving subject."
            : "From a shaking camera or a moving subject. A picture out of focus only comes a little crisper, and one too small can't get back what it never had."
        }
        on={fix.blur !== null}
        onChange={(on) => change({ blur: on ? { strength: 1 } : null })}
      >
        {fix.blur && (
          <Strength
            label="How much the blur is mended"
            value={fix.blur.strength}
            onChange={(strength) => change({ blur: { strength } })}
          />
        )}
      </FixRow>
      <FixRow
        title="JPEG blocks"
        detail={
          props.raw
            ? "A camera RAW has no JPEG blocks: it was never saved as a JPEG."
            : props.screenshot
              ? "Squares and halos round letters, from saving a screenshot as a JPEG. Best keeps letters crisp."
              : "Squares and halos round edges, from saving a picture small."
        }
        suggested={fixes?.blocks ?? false}
        disabled={props.raw}
        on={fix.jpeg !== null}
        onChange={(on) =>
          change({
            jpeg: on
              ? {
                  quality: props.screenshot ? "best" : null,
                  strength: props.many ? null : jpegStrength(fixes?.jpegQuality ?? null),
                }
              : null,
          })
        }
      >
        {fix.jpeg && (
          <>
            <Segmented
              label="How JPEG blocks come out"
              value={
                fix.jpeg.quality ??
                (props.decided === undefined ? "auto" : (props.decided ?? "fast"))
              }
              options={props.decided === undefined ? WITH_SUITS : QUALITIES}
              onChange={(chosen) =>
                fix.jpeg &&
                change({
                  jpeg: { ...fix.jpeg, quality: chosen === "auto" ? null : (chosen as Quality) },
                })
              }
              className="flex [&>button]:flex-1"
            />
            <p className="text-12 text-fg-faint leading-normal">
              Fast is SCUNet, which takes noise out too; Best is FBCNN, which takes out more.
            </p>
            {fix.jpeg.strength === null ? (
              <p className="text-12 text-fg-faint leading-normal">
                Each JPEG's blocks come out as hard as it was squeezed, read from the file; a
                picture that isn't a JPEG has none, so it's left as it is.
              </p>
            ) : (
              <Strength
                label="How hard JPEG blocks come out"
                value={fix.jpeg.strength}
                onChange={(strength) => fix.jpeg && change({ jpeg: { ...fix.jpeg, strength } })}
              />
            )}
            {fix.jpeg.strength !== null && fixes?.jpegQuality != null && (
              <p className="text-12 text-fg-faint leading-normal">
                It starts as hard as the picture was squeezed: saved at quality {fixes.jpegQuality},{" "}
                {Math.round(jpegStrength(fixes.jpegQuality) * 100)}%.
              </p>
            )}
          </>
        )}
      </FixRow>
      <FixRow
        title="Dark photo"
        detail="Brightened from its brightest parts, so a night stays a night, then the noise that brings out is taken out."
        suggested={fixes?.dark ?? false}
        on={fix.dark !== null}
        onChange={(on) => change({ dark: on ? { contrast: 0 } : null })}
      >
        {fix.dark && (
          <>
            {fixes?.stops !== 0 && (
              <Strength
                label="Local contrast"
                said="Local contrast"
                value={fix.dark.contrast}
                onChange={(contrast) => change({ dark: { contrast } })}
              />
            )}
            {fixes && (
              <p className="text-12 text-fg-faint leading-normal">
                {fixes.stops === 0
                  ? "It isn't dark, so Dark photo leaves it as it is."
                  : `Mado brightens it by about ${fixes.stops.toFixed(1)} stops. Local contrast brings out what's in the shadows.`}
              </p>
            )}
          </>
        )}
      </FixRow>
    </section>
  );
}

/** A fix's row: what it mends, whether Mado suggests it, its switch, and its setting once on. */
function FixRow(props: {
  title: string;
  detail: string;
  on: boolean;
  onChange: (on: boolean) => void;
  suggested?: boolean;
  disabled?: boolean;
  children?: ReactNode;
}) {
  const id = useId();
  // The switch is described by what Mado suggests and what the fix mends, as it's read out.
  const said = props.suggested ? `${id}-suggested ${id}-detail` : `${id}-detail`;
  return (
    <div className="flex flex-col gap-2.5 border-edge border-t px-3.5 py-3">
      <div className="flex items-start gap-3">
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2">
            <label
              htmlFor={id}
              className={cn("font-semibold text-14", !props.disabled && "cursor-pointer")}
            >
              {props.title}
            </label>
            {props.suggested && (
              <span
                id={`${id}-suggested`}
                className="rounded-full bg-accent/15 px-2 py-0.5 font-medium text-12 text-accent-fg"
              >
                Suggested
              </span>
            )}
          </span>
          <span id={`${id}-detail`} className="text-13 text-fg-muted leading-normal">
            {props.detail}
          </span>
        </span>
        <Switch
          id={id}
          className="mt-0.5"
          checked={props.on}
          disabled={props.disabled}
          onCheckedChange={props.onChange}
          aria-describedby={said}
        />
      </div>
      {props.on && props.children}
    </div>
  );
}

/** A fix's one setting, 0 to 100%. */
function Strength(props: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  /** What the row says beside it: "Strength". */
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

/** The small things: a grey picture stays grey, see-through parts stay, wide colours are kept, a
 * huge picture is fixed a tile at a time. */
function Notes(props: {
  picture: PictureDetails;
  fixes: Fixes | null;
  plan: Plan | null;
  on: boolean;
  megapixels: number;
}) {
  const { fixes, plan } = props;
  const said: string[] = [];
  if (fixes?.grey) said.push("It stays black and white.");
  if (fixes?.seeThrough) said.push("Its see-through parts stay as they are.");
  if (fixes && fixes.colour !== "sRGB") said.push(`Its ${fixes.colour} colours are kept.`);
  const huge = props.on && props.megapixels >= HUGE;
  // The card is too full of the models Mado has used to take the fixes': they run slower.
  const crowded = props.on && plan?.place === "card" && plan.fixPlace === "processor";
  if (said.length === 0 && !huge && !crowded) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {said.length > 0 && <p className="text-12 text-fg-faint leading-normal">{said.join(" ")}</p>}
      {crowded && (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          Your graphics card is full of the models Mado has used since it started, so the fixes run
          on the processor, slower. Restarting Mado frees the card.
        </p>
      )}
      {huge && plan && (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          A big picture: {Math.round(props.megapixels)} megapixels, fixed a tile at a time, so Save
          takes {about(plan.fixSeconds)} on{" "}
          {(plan.fixPlace ?? plan.place) === "card" ? "your graphics card" : "the processor"}. Zoom
          to 100% to see any part first: that's made in moments.
        </p>
      )}
    </div>
  );
}
