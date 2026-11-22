import { type ReactNode, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { LookGrid, Touches } from "@/features/picture/looks-tab";
import { Chip, OtherSize, SizeButton } from "@/features/picture/size-tab";
import { pickFolder } from "@/lib/dialogs";
import {
  type BatchSaving,
  type LookStepItem,
  type Quality,
  type SaveFormat,
  type SizeStepItem,
  useLooks,
  useSizes,
} from "@/lib/engine";
import { cn } from "@/lib/utils";
import { lookStep, sizeStep } from "./steps";

const SHAPES = [
  { value: "crop", label: "Crop around the subject" },
  { value: "extend", label: "Extend the edges" },
] as const;

const MODELS = [
  { value: "suits", label: "As this PC suits" },
  { value: "fast", label: "Fast" },
  { value: "best", label: "Best" },
] as const;

const WRITES: SaveFormat[] = ["JPEG", "PNG", "WebP", "AVIF"];
const LOSSY = new Set<SaveFormat>(["JPEG", "WebP", "AVIF"]);

/** A step's card: its choices, "Take this step out" and Done. */
function StepCard(props: {
  title: string;
  description: string;
  onClose: () => void;
  onRemove?: (() => void) | null;
  children: ReactNode;
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(44rem,calc(100vw-2rem))]">
        <DialogHeader title={props.title} description={props.description} />
        <DialogBody>{props.children}</DialogBody>
        <DialogFooter>
          {props.onRemove ? (
            <Button variant="ghost" size="sm" className="text-danger" onClick={props.onRemove}>
              Take this step out
            </Button>
          ) : (
            <span />
          )}
          <Button variant="primary" size="sm" onClick={props.onClose}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Make them for a screen, as the Size tab chooses it: the devices, the owner's screens and
 * prints, any other size, the shape and the model. Each picture keeps its own subject to crop
 * around and the model that suits what it is, unless Fast or Best is said.
 */
export function SizeDialog(props: {
  step: SizeStepItem | null;
  onStep: (step: SizeStepItem) => void;
  onRemove: (() => void) | null;
  onClose: () => void;
}) {
  const { step, onStep } = props;
  const sizes = useSizes();
  const clean = useId();
  const pick = (size: string) => onStep(sizeStep(size, step ?? undefined));
  const change = (part: Partial<SizeStepItem>) => step && onStep({ ...step, ...part });
  return (
    <StepCard
      title="Make them for a screen"
      description="Each picture is cropped around its own subject, or its edges extended, and made with the model that suits what it is."
      onClose={props.onClose}
      onRemove={props.onRemove}
    >
      <section aria-labelledby="batch-screens" className="flex flex-col gap-2">
        <h3 id="batch-screens" className="type-eyebrow">
          Make it for a screen
        </h3>
        <div className="grid grid-cols-2 gap-1.5 standard:grid-cols-3">
          {sizes.data?.screens.map((each) => (
            <SizeButton
              key={each.id}
              size={each}
              chosen={step?.size === each.id}
              onPick={() => pick(each.id)}
            />
          ))}
        </div>
        {sizes.isError && (
          <p role="alert" className="text-13 text-broken-fg">
            {sizes.error.message}
          </p>
        )}
      </section>
      <section aria-labelledby="batch-yours" className="flex flex-col gap-2">
        <h3 id="batch-yours" className="type-eyebrow">
          Your screens · print at 300 dpi
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {[...(sizes.data?.yours ?? []), ...(sizes.data?.prints ?? [])].map((each) => (
            <Chip
              key={each.id}
              chosen={step?.size === each.id}
              onClick={() => pick(each.id)}
              name={each.name}
              pixels={each.group === "yours" ? `${each.width} × ${each.height}` : null}
            />
          ))}
          <OtherSize chosen={step?.size.startsWith("other-") ?? false} onSize={pick} />
        </div>
      </section>
      {step && (
        <section aria-labelledby="batch-shape" className="flex flex-col gap-2">
          <h3 id="batch-shape" className="type-eyebrow">
            Shape and model
          </h3>
          <Segmented
            label="Shape"
            value={step.shape}
            options={SHAPES}
            onChange={(shape) => change({ shape })}
            className="flex [&>button]:flex-1"
          />
          {step.shape === "extend" && (
            <p className="text-12 text-fg-faint leading-normal">
              LaMa draws the new edges softly: skies, walls and water carry on well; people and busy
              detail at an edge come out smeared, so crop those instead.
            </p>
          )}
          <Segmented
            label="The model"
            value={step.quality ?? "suits"}
            options={MODELS}
            onChange={(quality) =>
              change({ quality: quality === "suits" ? null : (quality as Quality) })
            }
            className="flex [&>button]:flex-1"
          />
          <div className="flex items-center gap-2.5 text-13">
            <Switch
              id={clean}
              checked={step.clean}
              onCheckedChange={(on) => change({ clean: on })}
            />
            <label htmlFor={clean} className="cursor-pointer">
              Clean noise and blocks first
            </label>
          </div>
        </section>
      )}
    </StepCard>
  );
}

/**
 * Give them a look, as the Looks tab chooses it: every look (as small copies of one of the
 * pictures, when one is in the library), its strength, the finishing touches and the owner's
 * own looks.
 */
export function LookDialog(props: {
  step: LookStepItem | null;
  picture: { id: number; version: string } | null;
  onStep: (step: LookStepItem) => void;
  onRemove: (() => void) | null;
  onClose: () => void;
}) {
  const { step, onStep } = props;
  const looks = useLooks();
  const current = step ?? lookStep("original");
  const pick = (look: string, kept?: { touches: LookStepItem["touches"] }) =>
    onStep(
      kept
        ? { ...current, look, strength: 1, touches: kept.touches }
        : { ...current, look, strength: step ? current.strength : 1 },
    );
  return (
    <StepCard
      title="Give them a look"
      description="The same look on every picture, at its strength, with its touches, made after the size so grain never grows."
      onClose={props.onClose}
      onRemove={props.onRemove}
    >
      <section aria-labelledby="batch-looks" className="flex flex-col gap-2">
        <h3 id="batch-looks" className="type-eyebrow">
          Looks
        </h3>
        {looks.isError && (
          <p role="alert" className="text-13 text-broken-fg">
            Mado couldn't list the looks: {looks.error.message}
          </p>
        )}
        {looks.data && props.picture ? (
          <div className="max-w-md">
            <LookGrid
              picture={props.picture}
              looks={looks.data.looks}
              chosen={current.look}
              onPick={(look) => pick(look.id)}
              onPoint={() => {}}
            />
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {looks.data?.looks.map((look) => (
              <Pill key={look.id} chosen={look.id === current.look} onClick={() => pick(look.id)}>
                {look.name}
              </Pill>
            ))}
          </div>
        )}
        <div className="flex max-w-md items-center gap-3 text-13">
          <span>Strength</span>
          <Slider
            label="Strength"
            value={Math.round(current.strength * 100)}
            onChange={(value) => onStep({ ...current, strength: value / 100 })}
            disabled={current.look === "original"}
            valueText={`${Math.round(current.strength * 100)}%`}
          />
          <span className="w-10 text-right font-mono">{Math.round(current.strength * 100)}%</span>
        </div>
      </section>
      <div className="max-w-md">
        <Touches step={current} onStep={(next) => onStep({ ...current, ...next, step: "look" })} />
      </div>
      {looks.data && looks.data.yours.length > 0 && (
        <section aria-labelledby="batch-yours-looks" className="flex flex-col gap-2">
          <h3 id="batch-yours-looks" className="type-eyebrow">
            Your looks
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {looks.data.yours.map((look) => (
              <Pill
                key={look.id}
                chosen={look.id === current.look}
                onClick={() => pick(look.id, look.kind === "mix" ? look : undefined)}
              >
                {look.name}
              </Pill>
            ))}
          </div>
        </section>
      )}
    </StepCard>
  );
}

/**
 * How they're saved, as the Save dialog asks one picture: new pictures (beside the originals,
 * into a folder by name beside each, or into one folder) or in the originals' places; the
 * format and quality; and what's kept of each original.
 */
export function SavingDialog(props: {
  saving: BatchSaving;
  onSaving: (saving: BatchSaving) => void;
  onClose: () => void;
}) {
  const { saving, onSaving } = props;
  const change = (part: Partial<BatchSaving>) => onSaving({ ...saving, ...part });
  const [name, setName] = useState(
    saving.folder && !absolute(saving.folder) ? saving.folder : "Edited",
  );
  const where = !saving.folder ? "beside" : absolute(saving.folder) ? "folder" : "named";
  const ids = { quality: useId(), camera: useId(), colours: useId(), place: useId() };
  const lossy = LOSSY.has(saving.format);

  async function chooseFolder() {
    const chosen = await pickFolder("Where should the new pictures go?");
    if (chosen) change({ folder: chosen });
  }

  return (
    <StepCard
      title="How they're saved"
      description="Each picture made is checked before it's kept. Replaced originals wait in quarantine for 30 days, and History puts them back."
      onClose={props.onClose}
    >
      <Segmented
        label="Saving"
        value={saving.how}
        options={[
          { value: "new", label: "New pictures" },
          { value: "replace", label: "Replace the originals" },
        ]}
        onChange={(how) => change({ how })}
        className="flex [&>button]:flex-1"
      />
      {saving.how === "new" ? (
        <fieldset className="flex flex-col gap-2 text-13">
          <legend className="pb-1 text-fg-muted">Where they go</legend>
          <Radio chosen={where === "beside"} onChoose={() => change({ folder: null })}>
            Beside the originals
          </Radio>
          <Radio chosen={where === "named"} onChoose={() => change({ folder: name || "Edited" })}>
            <span className="flex flex-wrap items-center gap-2">
              In a folder called
              <Input
                aria-label="The folder's name"
                value={name}
                maxLength={60}
                onChange={(event) => {
                  const typed = event.target.value.replace(/[<>:"/\\|?*]/g, "");
                  setName(typed);
                  if (typed.trim()) change({ folder: typed.trim() });
                }}
                className="h-8 w-36 text-13"
              />
              beside each
            </span>
          </Radio>
          <Radio
            chosen={where === "folder"}
            onChoose={() => {
              if (where !== "folder") void chooseFolder();
            }}
          >
            <span className="flex flex-wrap items-center gap-2">
              Into one folder
              {where === "folder" && (
                <span className="font-mono text-12 text-fg-muted">{saving.folder}</span>
              )}
              <Button
                size="sm"
                className="min-h-8"
                onClick={(event) => {
                  event.stopPropagation(); // the radio around it would ask too
                  void chooseFolder();
                }}
              >
                Choose…
              </Button>
            </span>
          </Radio>
        </fieldset>
      ) : (
        <p className="text-13 text-fg-muted leading-normal">
          Each picture made takes its original's place, under its name; the original waits in
          quarantine for 30 days.
        </p>
      )}
      <div className="flex flex-col gap-3 border-rule border-t pt-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="w-16 text-13 text-fg-muted">Format</span>
          <Segmented
            label="Format"
            value={saving.format}
            options={WRITES.map((each) => ({ value: each, label: each }))}
            onChange={(format) =>
              change({
                format,
                quality: LOSSY.has(format) ? (saving.quality ?? qualityOf(format)) : null,
              })
            }
          />
        </div>
        {lossy && (
          <div className="flex items-center gap-3 text-13">
            <label htmlFor={ids.quality} className="w-16 text-fg-muted">
              Quality
            </label>
            <input
              id={ids.quality}
              type="range"
              min={50}
              max={100}
              value={saving.quality ?? qualityOf(saving.format)}
              onChange={(event) => change({ quality: Number(event.target.value) })}
              className="flex-1 accent-[var(--color-accent)]"
            />
            <span className="w-8 font-mono">{saving.quality ?? qualityOf(saving.format)}</span>
          </div>
        )}
        <fieldset className="flex flex-col gap-1.5 text-13">
          <legend className="pb-1 text-fg-muted">Keep from each original</legend>
          <Check
            id={ids.camera}
            checked={saving.keepCamera}
            onChange={(on) => change({ keepCamera: on })}
          >
            The date taken and the camera's details
          </Check>
          <Check
            id={ids.colours}
            checked={saving.keepColours}
            onChange={(on) => change({ keepColours: on })}
          >
            Its colours (the colour profile)
          </Check>
          <Check
            id={ids.place}
            checked={saving.keepLocation && saving.keepCamera}
            disabled={!saving.keepCamera}
            onChange={(on) => change({ keepLocation: on })}
          >
            Where it was taken (the location)
          </Check>
        </fieldset>
      </div>
    </StepCard>
  );
}

function qualityOf(format: SaveFormat): number {
  return format === "AVIF" ? 80 : format === "WebP" ? 90 : 92;
}

/** A folder's full path, rather than a name for one beside each picture. */
export function absolute(folder: string): boolean {
  return /^[a-z]:[\\/]/i.test(folder) || folder.startsWith("\\\\");
}

function Pill(props: { chosen: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={props.chosen}
      onClick={props.onClick}
      className={cn(
        "press inline-flex h-8 cursor-pointer items-center rounded-full border px-2.75 font-medium text-13",
        props.chosen ? "border-accent bg-accent/10 text-fg" : "border-field-edge hover:bg-tint/6",
      )}
    >
      {props.children}
    </button>
  );
}

function Radio(props: { chosen: boolean; onChoose: () => void; children: ReactNode }) {
  return (
    // biome-ignore lint/a11y/useSemanticElements: a radio holding a field and a button
    <div
      role="radio"
      aria-checked={props.chosen}
      tabIndex={0}
      onClick={props.onChoose}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          props.onChoose();
        }
      }}
      className="flex cursor-pointer items-center gap-2.5"
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-4 shrink-0 rounded-full",
          props.chosen ? "border-5 border-accent" : "border-[1.5px] border-fg-faint",
        )}
      />
      {props.children}
    </div>
  );
}

function Check(props: {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <label htmlFor={props.id} className="flex cursor-pointer items-center gap-2">
      <input
        id={props.id}
        type="checkbox"
        checked={props.checked}
        disabled={props.disabled}
        onChange={(event) => props.onChange(event.target.checked)}
        className="size-4 accent-[var(--color-accent)]"
      />
      {props.children}
    </label>
  );
}
