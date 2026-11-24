import { X } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from "react";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { pickCube } from "@/lib/dialogs";
import {
  type EditStep,
  type FixStep,
  type Look,
  type LookStep,
  lookAddress,
  type Need,
  type PickedPart,
  type PictureDetails,
  type Plan,
  type Recipe,
  type TouchName,
  useDeleteLook,
  useImportLook,
  useKeepLook,
  useLooks,
  usePictureImage,
  useRenameLook,
  type YourLook,
} from "@/lib/engine";
import { cn } from "@/lib/utils";
import { ModelCard, TooBig } from "./edit-tab";
import { MODELS, useNeed } from "./editing";
import { brightening } from "./fixes";
import { SaveSection } from "./save-section";

export const ORIGINAL = "original";

/** The touches as the board lists them, and the amount each turns on at. */
export const TOUCHES: { name: TouchName; label: string; first: number }[] = [
  { name: "grain", label: "Grain", first: 20 },
  { name: "vignette", label: "Vignette", first: 35 },
  { name: "glow", label: "Glow", first: 30 },
  { name: "fade", label: "Fade", first: 30 },
  { name: "leak", label: "Light leak", first: 40 },
  { name: "dust", label: "Dust", first: 30 },
];

/** No look and no touches: the picture as it is. */
export const PLAIN: LookStep = {
  look: ORIGINAL,
  strength: 1,
  touches: { grain: 0, vignette: 0, glow: 0, fade: 0, leak: 0, dust: 0 },
};

/** Whether a look step changes the picture at all. */
export function changes(step: LookStep): boolean {
  const looked = step.look !== ORIGINAL && step.strength > 0;
  return looked || Object.values(step.touches).some((amount) => amount > 0);
}

/**
 * The Looks tab, as Picture-Looks draws it: every look as a small copy of this picture (going
 * through them, by the arrow keys or the mouse, shows each on the big picture), its strength, the
 * painting styles (a group of their own, styles-section.tsx), the finishing touches, the owner's
 * own looks (a .cube file imported, or the mix kept), and Save, which makes the whole recipe: the
 * look, the style, and the size chosen on the Size tab.
 */
export function LooksTab(props: {
  picture: PictureDetails;
  step: LookStep;
  onStep: (step: LookStep) => void;
  /** A look pointed at, shown on the big picture till the pointer leaves; null when none. */
  onPoint: (step: LookStep | null) => void;
  /** The whole recipe Save makes, and its plan. */
  recipe: Recipe | null;
  plan: Plan | null;
  /** The look is still changing, so the plan for it isn't here yet. */
  settling: boolean;
  /** The edits made on the Edit tab, which the small copies show; null or missing for none. */
  edit?: EditStep | null;
  /** The fixes chosen on the Fix tab: the small copies show a dark photo brightened. */
  fix?: FixStep | null;
  /** "Only on a part", as the page holds the parts. */
  part?: ReactNode;
  /** The painting styles, as the page holds the painting chosen: a group of their own. */
  styles?: ReactNode;
}) {
  const { picture, step, onStep, onPoint } = props;
  const looks = useLooks();
  const mine = looks.data?.yours ?? [];
  const chosenMine = mine.find((each) => each.id === step.look) ?? null;
  const original = step.look === ORIGINAL;

  /** A look as it's picked: a kept mix at its own strength with its touches, any other at the
   * strength and with the touches set. */
  function stepFor(look: Look | YourLook): LookStep {
    const kept = "kind" in look && look.kind === "mix";
    return {
      look: look.id,
      strength: kept ? 1 : step.strength,
      touches: kept ? look.touches : step.touches,
    };
  }
  const pick = (look: Look | YourLook) => onStep(stepFor(look));
  const point = (look: Look | YourLook | null) => onPoint(look ? stepFor(look) : null);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3.5">
      <section aria-labelledby="looks" className="flex flex-col gap-2">
        <h2 id="looks" className="type-eyebrow">
          Looks
        </h2>
        {looks.isError ? (
          <p role="alert" className="text-13 text-broken-fg">
            Mado couldn't list the looks: {looks.error.message}
          </p>
        ) : looks.data ? (
          <LookGrid
            picture={picture}
            edit={props.edit ?? null}
            fix={props.fix ?? null}
            looks={looks.data.looks}
            chosen={step.look}
            onPick={pick}
            onPoint={point}
          />
        ) : (
          <div role="status" aria-label="Loading the looks" className="grid grid-cols-3 gap-2">
            {Array.from({ length: 12 }, (_, at) => `place ${at + 1}`).map((place) => (
              <span key={place} className="flex flex-col gap-1">
                <Skeleton className="h-14.5 rounded-4" />
                <Skeleton className="h-3 w-14" />
              </span>
            ))}
          </div>
        )}
        <div className="flex items-center gap-3 text-13">
          <span>Strength</span>
          <Slider
            label="Strength"
            value={Math.round(step.strength * 100)}
            onChange={(value) => onStep({ ...step, strength: value / 100 })}
            disabled={original}
            valueText={`${Math.round(step.strength * 100)}%`}
          />
          <span className="w-10 text-right font-mono">{Math.round(step.strength * 100)}%</span>
        </div>
      </section>

      {props.styles}

      <Touches step={step} onStep={onStep} />

      {props.part}

      <YourLooks
        mine={mine}
        chosen={chosenMine}
        step={step}
        onPick={pick}
        onPoint={point}
        onGone={() => onStep({ ...step, look: ORIGINAL, strength: 1 })}
      />

      <SaveSection
        picture={picture}
        recipe={props.recipe}
        plan={props.settling ? null : props.plan}
        ready={props.recipe !== null}
        caption={props.settling ? undefined : waitsFor(props.plan?.needs ?? [])}
      />
    </div>
  );
}

/** What Save waits for: a painting style's network downloads under Painting styles, the rest on
 * the Size tab. */
function waitsFor(needs: Need[]): string | undefined {
  if (!needs.length) return undefined;
  const names = needs.map((need) => need.name).join(" and ");
  return needs.every((need) => need.id.startsWith("style-") || need.id === "microast")
    ? `Save waits for ${names}, which downloads under Painting styles.`
    : `Save waits for ${names}, which the Size tab downloads.`;
}

/** Every look as a small copy of the picture in it (as its edits leave it, once it has some),
 * three to a row: picked by a click or the arrow keys (which move along it, a row at a time up
 * and down), shown on the big picture while the pointer rests on one. */
export function LookGrid(props: {
  picture: { id: number; version: string };
  edit?: EditStep | null;
  /** The fixes chosen: the small copies show a dark photo brightened. */
  fix?: FixStep | null;
  looks: Look[];
  chosen: string;
  onPick: (look: Look) => void;
  onPoint: (look: Look | null) => void;
}) {
  const { looks, chosen } = props;
  const tiles = useRef<(HTMLButtonElement | null)[]>([]);
  const at = looks.findIndex((each) => each.id === chosen);

  function move(event: KeyboardEvent<HTMLDivElement>) {
    const steps: Record<string, number> = {
      ArrowRight: 1,
      ArrowLeft: -1,
      ArrowDown: 3,
      ArrowUp: -3,
    };
    const step = steps[event.key];
    const last = looks.length - 1;
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? last
          : step !== undefined
            ? Math.min(Math.max(Math.max(at, 0) + step, 0), last)
            : null;
    const look = next === null ? undefined : looks[next];
    if (next === null || !look) return;
    event.preventDefault();
    props.onPick(look);
    tiles.current[next]?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label="Looks"
      onKeyDown={move}
      onPointerLeave={() => props.onPoint(null)}
      className="grid grid-cols-3 gap-2"
    >
      {looks.map((look, index) => (
        <LookTile
          key={look.id}
          picture={props.picture}
          edit={props.edit ?? null}
          fix={props.fix ?? null}
          look={look}
          chosen={look.id === chosen}
          focusable={look.id === chosen || (at < 0 && index === 0)}
          refTo={(tile) => {
            tiles.current[index] = tile;
          }}
          onPick={() => props.onPick(look)}
          onPoint={() => props.onPoint(look)}
        />
      ))}
    </div>
  );
}

function LookTile(props: {
  picture: { id: number; version: string };
  edit: EditStep | null;
  fix: FixStep | null;
  look: Look;
  chosen: boolean;
  focusable: boolean;
  refTo: (tile: HTMLButtonElement | null) => void;
  onPick: () => void;
  onPoint: () => void;
}) {
  const { look, chosen } = props;
  // Of the fixes, a small copy shows a dark photo's brightening: the rest are too small to see.
  const lit = brightening(props.fix);
  const copy = usePictureImage(
    lookAddress(props.picture, look),
    props.edit || lit
      ? {
          edit: props.edit ?? { version: props.picture.version, edits: [] },
          ...(lit ? { fix: lit } : {}),
        }
      : undefined,
  );
  return (
    // biome-ignore lint/a11y/useSemanticElements: a radio that is a small copy of the picture, which an input can't hold
    <button
      ref={props.refTo}
      type="button"
      role="radio"
      aria-checked={chosen}
      tabIndex={props.focusable ? 0 : -1}
      onClick={props.onPick}
      onPointerEnter={props.onPoint}
      className={cn(
        "press flex min-w-0 cursor-pointer flex-col gap-1 text-left text-12",
        chosen ? "font-semibold text-fg" : "font-medium text-fg-muted hover:text-fg",
      )}
    >
      <span
        className={cn(
          "relative block h-14.5 w-full overflow-hidden rounded-4 bg-behind",
          chosen && "outline-2 outline-accent outline-offset-1",
        )}
      >
        {copy.address ? (
          <img
            src={copy.address}
            alt=""
            draggable={false}
            className="size-full animate-fade-in object-cover"
          />
        ) : copy.problem ? (
          <span aria-hidden="true" className="status-problem absolute inset-0 opacity-50" />
        ) : (
          <Skeleton className="size-full rounded-4" />
        )}
      </span>
      <span className="truncate">{look.name}</span>
    </button>
  );
}

/** "Only on a part", as Picture-Looks draws it: the parts the look and its touches go on, picked
 * by clicking the picture as Select picks them, with a feathered edge; "Whole picture" goes
 * back. */
export function OnlyOnAPart(props: {
  parts: PickedPart[];
  pending: boolean;
  problem: string | null;
  /** Why the picture is too big to pick parts on, or null. */
  tooBig?: string | null;
  onSize?: () => void;
  onRemove: (at: number) => void;
  onWhole: () => void;
}) {
  const sam = useNeed(MODELS.select);
  const whole = props.parts.length === 0;
  return (
    <section
      aria-labelledby="part"
      className="flex flex-col gap-2 rounded-6 border border-edge bg-glass p-3"
    >
      <h2 id="part" className="font-semibold text-13">
        Only on a part
      </h2>
      {props.tooBig ? (
        <TooBig said={props.tooBig} onSize={props.onSize} />
      ) : sam ? (
        <ModelCard tool={sam} doing="Picking a part" />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {props.parts.map((part, at) => (
              <span
                key={part.name}
                className="inline-flex h-7.5 items-center gap-1.5 rounded-full bg-accent/15 pr-1 pl-2.5 font-medium text-13"
              >
                {part.name}
                <button
                  type="button"
                  aria-label={`Take ${part.name} away`}
                  onClick={() => props.onRemove(at)}
                  className="press grid size-6 cursor-pointer place-items-center rounded-full text-accent-fg hover:bg-tint/8"
                >
                  <X size={12} strokeWidth={2.2} aria-hidden="true" />
                </button>
              </span>
            ))}
            <button
              type="button"
              aria-pressed={whole}
              onClick={props.onWhole}
              className={cn(
                "press inline-flex h-7.5 cursor-pointer items-center rounded-full border px-2.5 font-medium text-13",
                whole
                  ? "border-accent bg-accent/10 text-fg"
                  : "border-field-edge text-fg-muted hover:bg-tint/6",
              )}
            >
              Whole picture
            </button>
          </div>
          <p className="text-13 text-fg-muted leading-normal">
            Click the picture to pick a part: the sky, a person, the background. Click again to add,
            Alt-click to take away.
          </p>
        </>
      )}
      {props.problem && (
        <p role="alert" className="text-12 text-broken-fg">
          {props.problem}
        </p>
      )}
    </section>
  );
}

/** Finishing touches, as the board's chips: each on or off with its amount, and while it's on a
 * line to set how much. */
export function Touches(props: { step: LookStep; onStep: (step: LookStep) => void }) {
  const { step, onStep } = props;
  const set = (name: TouchName, amount: number) =>
    onStep({ ...step, touches: { ...step.touches, [name]: amount } });
  const on = TOUCHES.filter((touch) => step.touches[touch.name] > 0);
  return (
    <section aria-labelledby="touches" className="flex flex-col gap-2">
      <h2 id="touches" className="type-eyebrow">
        Finishing touches
      </h2>
      <div className="flex flex-wrap gap-1.5">
        {TOUCHES.map((touch) => {
          const amount = step.touches[touch.name];
          return (
            <button
              key={touch.name}
              type="button"
              aria-pressed={amount > 0}
              onClick={() => set(touch.name, amount > 0 ? 0 : touch.first)}
              className={cn(
                "press inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border px-2.75 font-medium text-13",
                amount > 0
                  ? "border-accent bg-accent/10 text-fg"
                  : "border-field-edge text-fg-muted hover:bg-tint/6",
              )}
            >
              {touch.label}
              {amount > 0 && (
                <>
                  {" "}
                  <span className="font-mono text-accent-fg">{amount}</span>
                </>
              )}
            </button>
          );
        })}
      </div>
      {on.map((touch) => (
        <div key={touch.name} className="flex items-center gap-3 text-13">
          <span className="w-18 text-fg-muted">{touch.label}</span>
          <Slider
            label={touch.label}
            min={1}
            value={step.touches[touch.name]}
            onChange={(amount) => set(touch.name, amount)}
          />
          <span className="w-10 text-right font-mono">{step.touches[touch.name]}</span>
        </div>
      ))}
    </section>
  );
}

/** The owner's own looks: picked like Mado's (a kept mix brings its touches back), the one
 * picked renamed or deleted (asked first), a .cube file imported, and the mix kept. */
function YourLooks(props: {
  mine: YourLook[];
  chosen: YourLook | null;
  step: LookStep;
  onPick: (look: YourLook) => void;
  onPoint: (look: YourLook | null) => void;
  onGone: () => void;
}) {
  const { mine, chosen, step } = props;
  const importing = useImportLook();
  const [keeping, setKeeping] = useState(false);
  // What's open, for which of your looks: picking another closes it.
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const something = changes(step);

  async function importCube() {
    importing.reset();
    const path = await pickCube("Import a look");
    if (!path) return;
    importing.mutate(
      { path: "/looks/import", body: { path } },
      { onSuccess: (look) => props.onPick(look) },
    );
  }

  return (
    <section aria-labelledby="own" className="flex flex-col gap-2">
      <h2 id="own" className="type-eyebrow">
        Your looks
      </h2>
      <div className="flex flex-wrap gap-1.5" onPointerLeave={() => props.onPoint(null)}>
        {mine.map((look) => (
          <button
            key={look.id}
            type="button"
            aria-pressed={look.id === chosen?.id}
            onClick={() => props.onPick(look)}
            onPointerEnter={() => props.onPoint(look)}
            className={cn(
              "press inline-flex h-8 max-w-full cursor-pointer items-center rounded-full border px-2.75 font-medium text-13",
              look.id === chosen?.id
                ? "border-accent bg-accent/10 text-fg"
                : "border-field-edge text-fg hover:bg-tint/6",
            )}
          >
            <span className="truncate">{look.name}</span>
          </button>
        ))}
        <button
          type="button"
          disabled={importing.isPending}
          onClick={() => void importCube()}
          className="press inline-flex h-8 cursor-pointer items-center rounded-full border border-dash border-dashed px-2.75 font-medium text-13 text-fg-muted hover:bg-tint/6 disabled:cursor-default disabled:opacity-60"
        >
          {importing.isPending ? "Importing…" : "Import a .cube file"}
        </button>
        <button
          type="button"
          aria-expanded={keeping}
          disabled={!something}
          title={something ? undefined : "Pick a look or a touch first"}
          onClick={() => setKeeping(true)}
          className="press inline-flex h-8 cursor-pointer items-center rounded-full border border-dash border-dashed px-2.75 font-medium text-13 text-fg-muted hover:bg-tint/6 disabled:cursor-default disabled:opacity-50"
        >
          Keep this mix as a look
        </button>
      </div>
      {importing.isError && (
        <p role="alert" className="text-13 text-broken-fg leading-normal">
          {importing.error.message}
        </p>
      )}
      {keeping && (
        <NameForm
          kind="keep"
          label="Its name"
          initial=""
          path="/looks"
          body={(name) => ({ name, look: step })}
          onCancel={() => setKeeping(false)}
          onDone={(look) => {
            setKeeping(false);
            props.onPick(look);
          }}
        />
      )}
      {chosen && renaming !== chosen.id && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-12 text-fg-muted">
          <span className="min-w-0 truncate">
            {chosen.kind === "cube" ? `From ${chosen.source}` : chosen.source}
          </span>
          <button
            type="button"
            onClick={() => setRenaming(chosen.id)}
            className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
          >
            Rename
          </button>
          <button
            type="button"
            onClick={() => setDeleting(chosen.id)}
            className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
          >
            Delete…
          </button>
        </p>
      )}
      {chosen && renaming === chosen.id && (
        <NameForm
          key={chosen.id}
          kind="rename"
          label={`A new name for ${chosen.name}`}
          initial={chosen.name}
          path={`/looks/${chosen.id}`}
          body={(name) => ({ name })}
          onCancel={() => setRenaming(null)}
          onDone={() => setRenaming(null)}
        />
      )}
      {chosen && deleting === chosen.id && (
        <DeleteLook
          look={chosen}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null);
            props.onGone();
          }}
        />
      )}
    </section>
  );
}

/** A name to give a look, the mix kept or one renamed: why one won't do is said under it. */
function NameForm(props: {
  kind: "keep" | "rename";
  label: string;
  initial: string;
  path: string;
  body: (name: string) => unknown;
  onCancel: () => void;
  onDone: (look: YourLook) => void;
}) {
  const [name, setName] = useState(props.initial);
  const keep = useKeepLook();
  const rename = useRenameLook();
  const doing = props.kind === "keep" ? keep : rename;
  const id = useId();
  return (
    <form
      className="flex flex-col gap-2 rounded-6 border border-edge bg-glass p-2.5"
      onSubmit={(event) => {
        event.preventDefault();
        doing.mutate({ path: props.path, body: props.body(name) }, { onSuccess: props.onDone });
      }}
    >
      <label htmlFor={id} className="text-12 text-fg-muted">
        {props.label}
      </label>
      <span className="flex items-center gap-2">
        <Input
          id={id}
          value={name}
          maxLength={60}
          placeholder="Holiday warm"
          onChange={(event) => setName(event.target.value)}
          className="h-8 text-13"
        />
        <Button size="sm" type="submit" disabled={!name.trim() || doing.isPending}>
          {props.kind === "keep" ? "Keep" : "Rename"}
        </Button>
        <Button size="sm" variant="ghost" type="button" onClick={props.onCancel}>
          Cancel
        </Button>
      </span>
      {doing.isError && (
        <p role="alert" className="text-12 text-broken-fg">
          {doing.error.message}
        </p>
      )}
    </form>
  );
}

/** Deleting one of the owner's looks, asked first: pictures made with it stay as they are. */
function DeleteLook(props: { look: YourLook; onClose: () => void; onDeleted: () => void }) {
  const remove = useDeleteLook();
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(28rem,calc(100vw-2rem))]">
        <DialogHeader
          title={`Delete ${props.look.name}?`}
          description="It leaves your looks. Pictures you made with it stay as they are."
        />
        <DialogBody>
          <p className="text-13 text-fg-muted leading-normal">
            {props.look.kind === "cube"
              ? `Your ${props.look.source} stays where it is, so you can import it again.`
              : "A mix can't be brought back once it's deleted, though you can make it again."}
          </p>
          {remove.isError && (
            <p role="alert" className="text-13 text-broken-fg">
              {remove.error.message}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <span />
          <span className="flex gap-2">
            <Button variant="ghost" onClick={props.onClose}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate({ path: `/looks/${props.look.id}` }, { onSuccess: props.onDeleted })
              }
            >
              Delete
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
