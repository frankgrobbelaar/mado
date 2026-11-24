import {
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { EmptyState, WindowIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { RawReaderNote, useRawReader, useWhenReaderComes } from "@/components/raw-reader";
import { Loading, PanelSkeleton } from "@/components/skeleton";
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
import { Needs } from "@/features/picture/size-tab";
import {
  type BatchSaving,
  type BatchStep,
  type CutoutStepItem,
  type FixStepItem,
  type KeptRecipe,
  type LookStepItem,
  type PaintStepItem,
  type Picked,
  type SizeStepItem,
  type Starts,
  shownQuery,
  useKeepRecipe,
  useLetGo,
  usePicked,
  usePutInQueue,
  useRecipes,
  useSamples,
  useSeeFirst,
  useSettings,
  useTakes,
} from "@/lib/engine";
import { about, count, size } from "@/lib/format";
import { useSettled } from "@/lib/settled";
import { type BatchStart, useOpenPictures } from "./open";
import { SeeFirst } from "./see-first";
import {
  CutoutDialog,
  FixDialog,
  LookDialog,
  PaintDialog,
  SavingDialog,
  SizeDialog,
} from "./step-dialogs";
import {
  cutoutStep,
  fixStep,
  keepsNothing,
  same,
  savingFor,
  savingFrom,
  withStep,
  wordsFor,
} from "./steps";
import { StepsPanel } from "./steps-panel";

const WHEN: { value: Starts; label: ReactNode }[] = [
  { value: "now", label: "Now" },
  {
    value: "tonight",
    label: (
      <>
        Tonight, from <span className="font-mono">23:00</span>
      </>
    ),
  },
  { value: "after", label: "After what's in the queue" },
];

/**
 * Many at once, as the Batch board draws it: the pictures (ticked in the Library, a folder, what
 * a search found, or dropped and picked from the PC, in the library or not), their steps in the
 * order they're made with Change for each, See it first, when, how they're saved, and what it
 * takes, then "Put 48 in the queue".
 */
export function BatchPage() {
  const start = useLocation().state as BatchStart | null;
  if (!start?.pick) return <NoPictures />;
  return <Batch key={JSON.stringify(start.pick)} start={start} />;
}

function Batch({ start }: { start: BatchStart }) {
  const navigate = useNavigate();
  const asked = usePicked(start.picked ? null : start.pick);
  const found: Picked | undefined = start.picked ?? asked.data;
  const settings = useSettings();
  const recipes = useRecipes();
  const [steps, setSteps] = useState<BatchStep[]>([]);
  const [chosenSaving, setSaving] = useState<BatchSaving | null>(null);
  // Mado can't write camera RAW: a batch with RAWs in it saves new pictures.
  const raw = (found?.pictures ?? []).some((each) => each.raw);
  // A cut-out with nothing behind it keeps its nothing as PNG (or WebP), whatever was chosen.
  const chosen = savingFor(steps, chosenSaving ?? savingFrom(settings.data));
  const saving: BatchSaving = raw && chosen.how === "replace" ? { ...chosen, how: "new" } : chosen;
  // Camera RAWs left out while Mado's RAW reader comes join once it's here: asked again then,
  // and every few seconds after while the scan reads them.
  const reader = useRawReader();
  const readerWaited = found?.leftOut.some((each) => each.waiting) ?? false;
  const { refetch: pickAgain } = asked;
  const askAgain = useCallback(() => {
    if (readerWaited) void pickAgain();
  }, [readerWaited, pickAgain]);
  useWhenReaderComes(reader, askAgain);
  const reading = readerWaited && reader?.state === "ready";
  useEffect(() => {
    if (!reading) return;
    const every = window.setInterval(() => void pickAgain(), 3000);
    return () => window.clearInterval(every);
  }, [reading, pickAgain]);
  const [recipe, setRecipe] = useState<number | null>(start.recipe ?? null);
  const [when, setWhen] = useState<Starts>(start.starts ?? "now");
  const [editing, setEditing] = useState<string | null>(null);
  const [keeping, setKeeping] = useState(false);
  const applied = useRef(false);

  // A recipe to start from, once the recipes are here.
  useEffect(() => {
    if (applied.current || start.recipe === undefined || !recipes.data) return;
    const kept = recipes.data.find((each) => each.id === start.recipe);
    applied.current = true;
    if (!kept) return;
    setSteps(kept.steps);
    setSaving(kept.saving);
  }, [recipes.data, start.recipe]);

  const kept = recipes.data?.find((each) => each.id === recipe) ?? null;
  const fromRecipe = kept && same({ steps, saving }, kept) ? kept : null;
  const pictures = found?.pictures ?? [];

  // See it first: three made in full once the steps settle, and again when they change.
  const seen = useSeeFirst();
  const letGo = useLetGo();
  const [sample, setSample] = useState<{ id: string; round: number } | null>(null);
  const samples = useSamples(sample?.id ?? null);
  const making = useMemo(
    () =>
      JSON.stringify({
        steps,
        format: saving.format,
        quality: saving.quality,
        camera: saving.keepCamera,
        colours: saving.keepColours,
        place: saving.keepLocation,
      }),
    [steps, saving],
  );
  const settledMaking = useSettled(making, 800);
  const shown = useRef<string | null>(null);
  const { mutate: see } = seen;
  const { mutate: drop } = letGo;

  function ask(round: number) {
    if (!steps.length || !pictures.length) return;
    see(
      { path: "/batches/samples", body: { pictures, steps, saving, round } },
      {
        onSuccess: (made) => {
          if (shown.current && shown.current !== made.id) {
            drop({ path: `/batches/samples/${shown.current}` });
          }
          shown.current = made.id;
          setSample({ id: made.id, round: made.round });
        },
      },
    );
  }
  const asking = useRef(ask);
  useLayoutEffect(() => {
    asking.current = ask;
  });
  useEffect(() => {
    if (settledMaking !== making) return;
    asking.current(0);
  }, [settledMaking, making]);
  // Leaving lets them go.
  useEffect(
    () => () => {
      if (shown.current) drop({ path: `/batches/samples/${shown.current}` });
    },
    [drop],
  );

  const takes = useTakes(
    found && steps.length
      ? { pictures, steps, saving, shared: found.shared, sample: sample?.id ?? null }
      : null,
  );
  const madeSoFar = samples.data?.samples.filter((each) => each.state === "done").length ?? 0;
  const { refetch } = takes;
  useEffect(() => {
    if (madeSoFar > 0) void refetch();
  }, [madeSoFar, refetch]);

  const put = usePutInQueue();
  const words = takes.data?.words ?? wordsFor(steps, saving);
  const size_ = steps.find((each): each is SizeStepItem => each.step === "size") ?? null;
  const cut = steps.find((step): step is CutoutStepItem => step.step === "cutout") ?? null;
  const fixing = steps.find((step): step is FixStepItem => step.step === "fix") ?? null;
  const look = steps.find((each): each is LookStepItem => each.step === "look") ?? null;
  const paint = steps.find((each): each is PaintStepItem => each.step === "paint") ?? null;
  const library = pictures.find((each) => each.id !== null);
  const ready =
    steps.length > 0 && takes.data !== undefined && !takes.data.needs.length && !put.isPending;

  function queue() {
    if (!found) return;
    put.mutate(
      {
        path: "/batches",
        body: {
          name: fromRecipe?.name ?? null,
          source: found.source,
          shared: found.shared,
          pictures,
          steps,
          saving,
          starts: when,
          recipe: fromRecipe?.id ?? null,
          sample: sample?.id ?? null,
        },
      },
      {
        onSuccess: () => {
          shown.current = null; // the batch keeps them now
          void navigate("/queue");
        },
      },
    );
  }

  function changeWhich() {
    const pick = start.pick;
    if (pick.paths?.length) {
      // From anywhere (dropped, picked, pasted, opened from File Explorer): Home is where more
      // are dropped or picked.
      void navigate("/");
      return;
    }
    const query = shownQuery({
      favourites: false,
      folder: pick.folder ?? null,
      dir: pick.dir ?? "",
      q: pick.how === "search" ? (pick.q ?? "") : "",
      order: "newest",
      like: pick.how === "search" ? (pick.like ?? null) : null,
    });
    void navigate(query ? `/library?${query}` : "/library");
  }

  return (
    <>
      <header className="page-top flex animate-fade-up flex-wrap items-center gap-x-4 gap-y-2.5">
        <h1 className="type-title">Many at once</h1>
        {found && (
          <p className="text-14 text-fg-muted">
            <span className="font-mono text-fg">{count(pictures.length)}</span>{" "}
            {pictures.length === 1 ? "picture" : "pictures"} {found.words} ·{" "}
            <span className="font-mono text-fg">{size(found.bytes)}</span>
          </p>
        )}
        <Button size="sm" className="ml-auto bg-transparent font-medium" onClick={changeWhich}>
          Change which
        </Button>
      </header>

      <EngineProblem queries={[asked, settings]} />
      {!found && (
        <Loading label="Finding the pictures" queries={[asked]}>
          <PanelSkeleton rows={3} />
        </Loading>
      )}
      {found && found.leftOut.length > 0 && <LeftOut picked={found} />}
      {readerWaited && reader?.state !== "ready" && (
        <RawReaderNote tool={reader} className="max-w-150" />
      )}
      {found && pictures.length === 0 && (
        <EmptyState title="None of these can be made" illustration={<WindowIllustration />}>
          Pictures that won't open are left out, as they are, and camera RAW till Mado's RAW reader
          is here. Pick others.
        </EmptyState>
      )}

      {found && pictures.length > 0 && (
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-4">
            <StepsPanel
              steps={steps}
              words={words}
              onChange={setEditing}
              onAdd={(kind) => {
                if (kind === "cutout") setSteps(withStep(steps, cutoutStep(), "cutout"));
                if (kind === "fix") setSteps(withStep(steps, fixStep(), "fix"));
                setEditing(kind);
              }}
              recipes={recipes.data}
              recipe={fromRecipe?.id ?? null}
              onRecipe={(chosen: KeptRecipe) => {
                setSteps(chosen.steps);
                setSaving(chosen.saving);
                setRecipe(chosen.id);
              }}
              aside={
                fromRecipe ? (
                  <>
                    From the recipe <span className="text-fg">{fromRecipe.name}</span>
                  </>
                ) : steps.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => setKeeping(true)}
                    className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
                  >
                    Keep as a recipe…
                  </button>
                ) : null
              }
            />
            {takes.isError && steps.length > 0 && (
              <p role="alert" className="text-13 text-broken-fg">
                {takes.error.message}
              </p>
            )}
            <SeeFirst
              samples={sample ? samples.data : undefined}
              total={pictures.length}
              asking={seen.isPending}
              problem={seen.error?.message ?? null}
              onOthers={() => ask((sample?.round ?? 0) + 1)}
            />
          </div>

          <aside
            aria-label="When and how"
            className="flex min-w-0 max-w-100 flex-[1_1_320px] flex-col gap-4"
          >
            <WhenPanel when={when} onWhen={setWhen} />
            <SavingPanel
              saving={saving}
              raw={raw}
              into={takes.data?.into ?? null}
              example={takes.data?.example ?? null}
              onSaving={setSaving}
            />
            <section
              aria-labelledby="takes"
              className="flex animate-fade-up flex-col gap-2.5 rounded-8 border border-edge bg-glass px-4.5 pt-3.5 pb-4"
            >
              <h2 id="takes" className="type-eyebrow">
                What it takes
              </h2>
              {takes.data ? (
                <>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3.5 gap-y-1.5 text-13">
                    <dt className="text-fg-muted">Time</dt>
                    <dd className="text-right font-mono">{about(takes.data.seconds)}</dd>
                    <dt className="text-fg-muted">Space</dt>
                    <dd className="text-right font-mono">about {size(takes.data.bytes)}</dd>
                    {takes.data.free !== null && (
                      <>
                        <dt className="text-fg-muted">Free on {takes.data.drive}</dt>
                        <dd className="text-right font-mono">{size(takes.data.free)}</dd>
                      </>
                    )}
                  </dl>
                  <p className="text-12 text-fg-faint leading-normal">
                    {takes.data.measured
                      ? `Timed on this PC's ${takes.data.place === "card" ? "graphics card" : "processor"}, one picture at a time.`
                      : "A guess till this PC is timed: each picture made times it, and Settings › About tests it."}
                  </p>
                  {!takes.data.fits && takes.data.drive && (
                    <p role="alert" className="text-12 text-broken-fg leading-normal">
                      {takes.data.drive} hasn't room for them all. The queue pauses itself when it
                      fills, and says what it needs.
                    </p>
                  )}
                  {takes.data.needs.length > 0 && (
                    <Needs
                      needs={takes.data.needs}
                      onFast={
                        size_ && takes.data.needs.some((need) => need.id !== "lama")
                          ? () => setSteps(withStep(steps, { ...size_, quality: "fast" }, "size"))
                          : null
                      }
                      onCrop={
                        size_ && takes.data.needs.some((need) => need.id === "lama")
                          ? () => setSteps(withStep(steps, { ...size_, shape: "crop" }, "size"))
                          : null
                      }
                      onReady={() => void refetch()}
                    />
                  )}
                </>
              ) : (
                <p className="text-13 text-fg-muted">
                  {steps.length ? "Working it out…" : "Pick a step to see what it takes."}
                </p>
              )}
              {put.isError && (
                <p role="alert" className="text-13 text-broken-fg">
                  {put.error.message}
                </p>
              )}
              <Button variant="primary" disabled={!ready} onClick={queue}>
                Put {count(pictures.length)} in the queue
              </Button>
            </section>
          </aside>
        </div>
      )}

      {editing === "size" && (
        <SizeDialog
          step={size_}
          onStep={(step) => setSteps(withStep(steps, step, "size"))}
          onRemove={size_ ? () => removed("size") : null}
          onClose={() => setEditing(null)}
          cleanedFirst={Boolean(fixing?.noise?.strength || fixing?.jpeg)}
        />
      )}
      {editing === "look" && (
        <LookDialog
          step={look}
          picture={library?.id ? { id: library.id, version: library.version } : null}
          onStep={(step) => setSteps(withStep(steps, step, "look"))}
          onRemove={look ? () => removed("look") : null}
          onClose={() => {
            if (look?.look === "original" && !Object.values(look.touches).some(Boolean)) {
              setSteps(withStep(steps, null, "look")); // a look that changes nothing isn't a step
            }
            setEditing(null);
          }}
        />
      )}
      {editing === "paint" && (
        <PaintDialog
          step={paint}
          onStep={(step) => setSteps(withStep(steps, step, "paint"))}
          onRemove={paint ? () => removed("paint") : null}
          onClose={() => setEditing(null)}
        />
      )}
      {editing === "cutout" && cut && (
        <CutoutDialog
          step={cut}
          onStep={(step) => setSteps(withStep(steps, step, "cutout"))}
          onRemove={() => removed("cutout")}
          onClose={() => setEditing(null)}
        />
      )}
      {editing === "fix" && fixing && (
        <FixDialog
          step={fixing}
          onStep={(step) => setSteps(withStep(steps, step, "fix"))}
          onRemove={() => removed("fix")}
          onClose={() => {
            if (!fixing.noise && !fixing.blur && !fixing.jpeg && !fixing.dark) {
              setSteps(withStep(steps, null, "fix")); // fixes all off aren't a step
            }
            setEditing(null);
          }}
        />
      )}
      {editing === "save" && (
        <SavingDialog
          saving={saving}
          onSaving={setSaving}
          clear={keepsNothing(steps)}
          raw={raw}
          onClose={() => setEditing(null)}
        />
      )}
      {keeping && (
        <KeepRecipe
          steps={steps}
          saving={saving}
          onClose={() => setKeeping(false)}
          onKept={(made) => {
            setRecipe(made.id);
            setKeeping(false);
          }}
        />
      )}
    </>
  );

  function removed(kind: BatchStep["step"]) {
    setSteps(withStep(steps, null, kind));
    setEditing(null);
  }
}

/** When: now, tonight from 23:00 (till 07:00), or after what's in the queue. */
function WhenPanel(props: { when: Starts; onWhen: (when: Starts) => void }) {
  const name = useId();
  return (
    <section
      aria-labelledby="when"
      className="flex animate-fade-up flex-col gap-2.5 rounded-8 border border-edge bg-glass px-4.5 pt-3.5 pb-4"
    >
      <h2 id="when" className="type-eyebrow">
        When
      </h2>
      <div role="radiogroup" aria-labelledby="when" className="flex flex-col gap-1.5 text-14">
        {WHEN.map((each) => (
          <label key={each.value} className="flex cursor-pointer items-center gap-2.5">
            <input
              type="radio"
              name={name}
              checked={props.when === each.value}
              onChange={() => props.onWhen(each.value)}
              className="size-4 accent-[var(--color-accent)]"
            />
            {each.label}
          </label>
        ))}
      </div>
    </section>
  );
}

/** Saving: new pictures or the originals replaced, and where they go, in a line. A batch with
 * camera RAW saves new pictures, and says why. */
function SavingPanel(props: {
  saving: BatchSaving;
  raw: boolean;
  into: string | null;
  example: string | null;
  onSaving: (saving: BatchSaving) => void;
}) {
  const { saving } = props;
  return (
    <section
      aria-labelledby="saving"
      className="flex animate-fade-up flex-col gap-2.5 rounded-8 border border-edge bg-glass px-4.5 pt-3.5 pb-4"
    >
      <h2 id="saving" className="type-eyebrow">
        Saving
      </h2>
      {props.raw ? (
        <p className="text-12 text-fg-muted leading-normal">
          Replacing the originals isn't offered: some are camera RAW, which Mado can't write, so it
          saves new pictures.
        </p>
      ) : (
        <Segmented
          label="Saving"
          value={saving.how}
          options={[
            { value: "new", label: "New pictures" },
            { value: "replace", label: "Replace the originals" },
          ]}
          onChange={(how) => props.onSaving({ ...saving, how })}
          className="flex [&>button]:flex-1 [&>button]:whitespace-nowrap [&>button]:px-2 [&>button]:text-12"
        />
      )}
      <p className="text-12 text-fg-muted leading-normal">
        {saving.how === "new" ? (
          props.into ? (
            <>
              {props.into === "beside the originals" ? (
                "Beside the originals"
              ) : (
                <>
                  Into <span className="font-mono text-fg">{props.into}</span>
                </>
              )}
              {props.example && (
                <>
                  , as <span className="font-mono text-fg">{props.example}</span>
                </>
              )}
              . The originals stay as they are.
            </>
          ) : (
            // Till what it takes is known (a step picked), it can't say where they go.
            "The originals stay as they are."
          )
        ) : (
          "Each picture made takes its original's place; the originals wait in quarantine for 30 days, and History puts them back."
        )}
      </p>
    </section>
  );
}

/** Those left out of a batch, and why. */
function LeftOut({ picked }: { picked: Picked }) {
  const shown = picked.leftOut.slice(0, 3);
  const more = picked.leftOut.length - shown.length;
  return (
    <p role="note" className="text-13 text-fg-muted leading-normal">
      Left out, as they are:{" "}
      {shown.map((each, at) => (
        <span key={each.name}>
          {at > 0 && "; "}
          <span className="text-fg">{each.name}</span> ({each.why.replace(/\.$/, "")})
        </span>
      ))}
      {more > 0 && `; and ${count(more)} more`}.
    </p>
  );
}

/** Keeps a batch's steps and how it saves as a recipe, by name. */
function KeepRecipe(props: {
  steps: BatchStep[];
  saving: BatchSaving;
  onClose: () => void;
  onKept: (recipe: KeptRecipe) => void;
}) {
  const [name, setName] = useState("");
  const keep = useKeepRecipe();
  const id = useId();
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(28rem,calc(100vw-2rem))]">
        <DialogHeader
          title="Keep as a recipe"
          description="Its steps and how it saves, by name, to use on any batch or a watch folder."
        />
        <form
          className="contents"
          onSubmit={(event) => {
            event.preventDefault();
            keep.mutate(
              { path: "/recipes", body: { name, steps: props.steps, saving: props.saving } },
              { onSuccess: props.onKept },
            );
          }}
        >
          <DialogBody>
            <label htmlFor={id} className="text-13 text-fg-muted">
              Its name
            </label>
            <Input
              id={id}
              value={name}
              maxLength={60}
              placeholder="Holiday prints"
              onChange={(event) => setName(event.target.value)}
            />
            {keep.isError && (
              <p role="alert" className="text-13 text-broken-fg">
                {keep.error.message}
              </p>
            )}
          </DialogBody>
          <DialogFooter>
            <span />
            <span className="flex gap-2">
              <Button variant="ghost" type="button" onClick={props.onClose}>
                Cancel
              </Button>
              <Button variant="primary" type="submit" disabled={!name.trim() || keep.isPending}>
                Keep it
              </Button>
            </span>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Many at once with no pictures yet: where they come from. */
function NoPictures() {
  const opening = useOpenPictures();
  return (
    <>
      <header className="page-top flex animate-fade-up items-center">
        <h1 className="type-title">Many at once</h1>
      </header>
      <EmptyState
        title="Pick the pictures first"
        illustration={<WindowIllustration />}
        action={
          <span className="flex flex-wrap justify-center gap-2">
            <Button
              variant="primary"
              disabled={opening.busy}
              onClick={() => void opening.choosePictures()}
            >
              Pick pictures
            </Button>
            <Button disabled={opening.busy} onClick={() => void opening.chooseFolder()}>
              Pick a folder
            </Button>
          </span>
        }
        note={opening.problem ?? undefined}
      >
        Tick them in the{" "}
        <Link to="/library" className="text-accent-fg underline-offset-3 hover:underline">
          Library
        </Link>
        , pick a folder there, or drop them on the window, from anywhere on your PC.
      </EmptyState>
    </>
  );
}
