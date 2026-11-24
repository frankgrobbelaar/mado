import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Slider } from "@/components/ui/slider";
import type { Fixes, PictureDetails, Plan, RestoreStep, Scratches, Tool } from "@/lib/engine";
import { useTools } from "@/lib/engine";
import { ModelCard, TooBig } from "./edit-tab";
import { MOST_PIXELS } from "./editing";
import { FixRow, Strength } from "./fix-tab";
import {
  colourWay,
  colourWords,
  MOST_MASK,
  MUCH_MASK,
  RESTORE_MODELS,
  restoreModels,
  SCRATCH_BRUSH,
} from "./restore";

const WAYS = [
  { value: "colour", label: "Colour it" },
  { value: "faded", label: "Bring its colours back" },
] as const;

/** What each model does, as its card before it's downloaded says it. */
const DOING: Record<string, string> = {
  [RESTORE_MODELS.detector]: "Scratches and dust are found",
  [RESTORE_MODELS.filler]: "Scratches are filled",
  [RESTORE_MODELS.colourer]: "Black-and-white photos are coloured",
};

/**
 * Restoring an old photo, at the top of the Fix tab, as its steps are made: scratches and dust
 * first (found by Mado, shown on the picture as a mask the owner checks with the brush before
 * anything is filled), then colour (a black-and-white or sepia print coloured, or a colour
 * photo's faded colours brought back), before the fixes below take out noise and JPEG blocks. No
 * board draws it, so it's the Fix tab's own rows. Faces are left as they are.
 */
export function RestoreSection(props: {
  picture: PictureDetails;
  /** What Mado measured of the picture; null while it's on its way. */
  fixes: Fixes | null;
  restore: RestoreStep;
  onRestore: (step: RestoreStep) => void;
  /** The stage shows the mask and the brush. */
  checking: boolean;
  onChecking: (checking: boolean) => void;
  /** What the detector found, while scratches are on. */
  scratches: Scratches;
  brush: number;
  onBrush: (brush: number) => void;
  /** The plan for the recipe as it is now; null while it's on its way. */
  plan: Plan | null;
  /** Goes to the Size tab, to make a smaller copy of a scan too big to restore. */
  onSize?: () => void;
}) {
  const { restore, fixes, scratches, plan } = props;
  const pixels = (props.picture.width ?? 0) * (props.picture.height ?? 0);
  const tools = useTools();
  const waiting = restoreModels(restore)
    .map((id) => tools.data?.find((tool) => tool.id === id))
    .filter((tool): tool is Tool => tool !== undefined && tool.state !== "ready");
  const detectorHere = !waiting.some((tool) => tool.id === RESTORE_MODELS.detector);
  const change = (part: Partial<RestoreStep>) =>
    props.onRestore({ ...restore, version: props.picture.version, ...part });
  const way = restore.faded ? "faded" : "colour";
  const colouring = Boolean(restore.colour || restore.faded);

  return (
    <section aria-labelledby="restore" className="flex flex-col gap-2">
      <h2 id="restore" className="type-eyebrow">
        Restore an old photo
      </h2>
      {pixels > MOST_PIXELS ? (
        <TooBig
          said={`It's ${Math.round(pixels / 1e6)} megapixels, and Mado restores pictures up to ${MOST_PIXELS / 1e6}. Make a smaller copy of it on the Size tab, then restore that.`}
          onSize={props.onSize}
          label="Too big to restore"
        />
      ) : (
        <section
          aria-label="Restoring"
          className="flex flex-col rounded-6 border border-edge bg-glass [&>*:first-child]:border-t-0"
        >
          <FixRow
            title="Scratches and dust"
            detail="Found by Mado and shown on the picture first: you check the mask, then Mado fills them."
            on={restore.scratches !== null}
            onChange={(on) => {
              change({ scratches: on ? { strokes: [] } : null });
              props.onChecking(on);
            }}
          >
            {restore.scratches && (
              <ScratchControls
                strokes={restore.scratches.strokes.length}
                scratches={scratches}
                detectorHere={detectorHere}
                covers={plan?.restoreCovers ?? null}
                checking={props.checking}
                onChecking={props.onChecking}
                brush={props.brush}
                onBrush={props.onBrush}
                onClear={() => change({ scratches: { strokes: [] } })}
              />
            )}
          </FixRow>
          <FixRow
            title="Colour"
            detail={colourDetail(fixes)}
            suggested={fixes !== null && fixes.colours !== "colour"}
            on={colouring}
            onChange={(on) =>
              change(
                !on
                  ? { colour: null, faded: null }
                  : colourWay(fixes) === "faded"
                    ? { colour: null, faded: { strength: 1 } }
                    : { colour: { strength: 1 }, faded: null },
              )
            }
          >
            {colouring && (
              <>
                <Segmented
                  label="What to do with its colours"
                  value={way}
                  options={WAYS}
                  onChange={(chosen) => {
                    const strength = (restore.colour ?? restore.faded)?.strength ?? 1;
                    change(
                      chosen === "faded"
                        ? { colour: null, faded: { strength } }
                        : { colour: { strength }, faded: null },
                    );
                  }}
                  className="flex [&>button]:flex-1 [&>button]:px-1.5 [&>button]:text-12"
                />
                <Strength
                  label={way === "colour" ? "How much colour" : "How far its colours come back"}
                  value={(restore.colour ?? restore.faded)?.strength ?? 1}
                  onChange={(strength) =>
                    change(way === "colour" ? { colour: { strength } } : { faded: { strength } })
                  }
                />
                <ColourNotes way={way} fixes={fixes} />
              </>
            )}
          </FixRow>
        </section>
      )}
      {waiting.map((tool) => (
        <ModelCard
          key={tool.id}
          tool={tool}
          doing={DOING[tool.id] ?? tool.name}
          offline="Faded colours come back without a download, and the fixes whose models are here work now."
        />
      ))}
    </section>
  );
}

/** What the Colour row offers this picture, from what its colours are. */
function colourDetail(fixes: Fixes | null): string {
  if (!fixes)
    return "Colours guessed for a black-and-white or sepia print, or faded ones brought back.";
  if (fixes.colours === "colour")
    return "A colour photo's faded colours brought back from the picture itself.";
  return `It's ${colourWords(fixes)}: Mado can colour it.`;
}

/** The Colour row's honest lines: what a guess is, a sepia print's tone, a picture already in
 * colour asked to be coloured, and a black-and-white one with no colours to bring back. */
function ColourNotes({ way, fixes }: { way: "colour" | "faded"; fixes: Fixes | null }) {
  const said: string[] = [];
  if (way === "colour") {
    said.push(
      "The colours are guessed from what photos usually look like: a coat's colour is a guess.",
    );
    if (fixes?.colours === "colour")
      said.push(
        "It's in colour already: colouring guesses new colours from its light and puts them in place of its own.",
      );
    if (fixes?.colours === "toned" && fixes.tone === "sepia")
      said.push("A sepia print: the strength mixes the colours guessed with its brown.");
  } else {
    said.push(
      "Its colours set from its own darkest and brightest parts, which takes out a tint too.",
    );
    if (fixes && fixes.colours !== "colour")
      said.push(`It's ${colourWords(fixes)}, so there are no colours to bring back.`);
    else if (fixes)
      said.push("Whether its colours faded Mado can't measure: compare before and after.");
  }
  return (
    <div className="flex flex-col gap-1">
      {said.map((line) => (
        <p key={line} className="text-12 text-fg-faint leading-normal">
          {line}
        </p>
      ))}
    </div>
  );
}

/** Scratches and dust once they're on: what Mado found, the brush to check it with, and filling
 * them in; or the mask again. */
function ScratchControls(props: {
  strokes: number;
  scratches: Scratches;
  detectorHere: boolean;
  covers: number | null;
  checking: boolean;
  onChecking: (checking: boolean) => void;
  brush: number;
  onBrush: (brush: number) => void;
  onClear: () => void;
}) {
  const { scratches } = props;
  if (!props.detectorHere) {
    return (
      <p className="text-12 text-fg-faint leading-normal">
        Mado looks for them once its scratch detector is here.
      </p>
    );
  }
  if (scratches.problem) {
    return (
      <p role="alert" className="text-13 text-broken-fg leading-normal">
        {scratches.problem}
      </p>
    );
  }
  if (scratches.busy && scratches.found === null) {
    return (
      <p role="status" className="text-13 text-fg-muted">
        Looking for scratches and dust…
      </p>
    );
  }
  const covers = props.covers ?? scratches.found ?? 0;
  const none = (scratches.found ?? 0) === 0 && props.strokes === 0;
  const percent = covers < 0.001 && covers > 0 ? "under 0.1" : (covers * 100).toFixed(1);
  const most = covers > MOST_MASK;
  return (
    <div className="flex flex-col gap-2.5">
      {none ? (
        <p role="status" className="text-13 leading-normal">
          Mado found no scratches or dust. If you see some, paint over them on the picture: Mado
          fills what you paint.
        </p>
      ) : (
        <p role="status" className="text-13 leading-normal">
          The mask covers <span className="font-mono">{percent}%</span> of the picture.
        </p>
      )}
      {most ? (
        <p
          role="alert"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          That's most of the picture: Mado fills scratches and dust, not most of a picture. Hold Alt
          and paint to take some of the mask away.
        </p>
      ) : covers >= MUCH_MASK ? (
        <p
          role="note"
          className="rounded-4 bg-tint/6 px-2.5 py-2 text-12 text-fg-soft leading-normal"
        >
          That's a lot to fill: the more the mask covers, the more Mado has to invent.
        </p>
      ) : null}
      {props.checking ? (
        <>
          <p className="text-12 text-fg-faint leading-normal">
            Paint over what it missed, and hold Alt to take away what isn't a scratch: dark
            scratches are the ones it misses most, and a thin line that belongs in the picture can
            look like one.
          </p>
          <div className="flex items-center gap-3 text-13">
            <span className="w-10 text-fg-muted">Size</span>
            <Slider
              label="Brush size"
              min={SCRATCH_BRUSH.least * 1000}
              max={SCRATCH_BRUSH.most * 1000}
              step={5}
              value={Math.round(props.brush * 1000)}
              onChange={(value) => props.onBrush(value / 1000)}
              valueText={`${(props.brush * 100).toFixed(1)}% of the picture's shorter side`}
            />
            <span className="w-12 text-right font-mono">{(props.brush * 100).toFixed(1)}%</span>
          </div>
          <span className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              size="sm"
              disabled={most || scratches.busy}
              onClick={() => props.onChecking(false)}
            >
              Fill them in
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={props.strokes === 0}
              onClick={props.onClear}
            >
              Clear what you painted
            </Button>
          </span>
        </>
      ) : (
        <Button size="sm" className="self-start" onClick={() => props.onChecking(true)}>
          Check the mask
        </Button>
      )}
    </div>
  );
}
