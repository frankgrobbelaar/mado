import { type ReactNode, useId, useState } from "react";
import { Loading, PanelSkeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Segmented } from "@/components/ui/segmented";
import { pickFolder } from "@/lib/dialogs";
import {
  type PictureDetails,
  type Plan,
  type Recipe,
  type SaveFormat,
  type Saving,
  type Settings,
  useMake,
  useSavingName,
  useSettings,
} from "@/lib/engine";
import { showInFolder, useExplorer } from "@/lib/explorer";
import { dayAndTime, size as sizeOf, split, stem } from "@/lib/format";
import { cn } from "@/lib/utils";

const WRITES: SaveFormat[] = ["JPEG", "PNG", "WebP", "AVIF"];
const LOSSY = new Set<SaveFormat>(["JPEG", "WebP", "AVIF"]);

/**
 * Save, as the Save board draws it: as a new picture (beside the original, named after it with
 * what it was made for and with, or into a folder chosen), or in the original's place (the
 * original into quarantine for 30 days); the format and quality; what's kept of the original; and
 * "Always save this way". It saves the whole recipe, the size and the look together. Saving
 * starts the job; its progress shows in the tab Save was opened from.
 */
export function SaveDialog(props: {
  picture: PictureDetails;
  plan: Plan;
  recipe: Recipe;
  onClose: () => void;
}) {
  const settings = useSettings();
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(36rem,calc(100vw-2rem))]">
        {settings.data ? (
          <SaveForm {...props} settings={settings.data} />
        ) : (
          <>
            <DialogHeader
              title={`Save ${stem(props.picture.name)}`}
              description={<MadeAs plan={props.plan} />}
            />
            <DialogBody>
              {settings.isError ? (
                <p role="alert" className="text-13 text-broken-fg">
                  {settings.error.message}
                </p>
              ) : (
                <Loading label="Loading how you save" queries={[settings]}>
                  <PanelSkeleton rows={3} />
                </Loading>
              )}
            </DialogBody>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** The dialog's choices, starting from the settings: the way saved first, the folder new
 * pictures go to, and whether the location's kept. */
function SaveForm(props: {
  picture: PictureDetails;
  plan: Plan;
  recipe: Recipe;
  settings: Settings;
  onClose: () => void;
}) {
  const { picture, plan, recipe, settings } = props;
  const asIs = WRITES.find((each) => each === picture.format) ?? null;
  const [how, setHow] = useState<"new" | "replace">(settings.saveFirst);
  const [format, setFormat] = useState<SaveFormat>(plan.format);
  const [quality, setQuality] = useState(plan.formatQuality ?? 92);
  const [folder, setFolder] = useState<string | null>(
    settings.newPictures === "folder" ? settings.newFolder : null,
  );
  const [keepCamera, setKeepCamera] = useState(true);
  const [keepColours, setKeepColours] = useState(true);
  const [keepLocation, setKeepLocation] = useState(settings.keepLocation);
  const [always, setAlways] = useState(false);
  const make = useMake();
  const explorer = useExplorer();
  const lossy = LOSSY.has(format);
  const name = useSavingName(picture.id, {
    recipe,
    how,
    format,
    quality: lossy ? quality : null,
    folder: how === "new" ? folder : null,
    keepColours,
  });
  const ids = {
    quality: useId(),
    camera: useId(),
    colours: useId(),
    place: useId(),
    always: useId(),
  };
  const where = folder ?? split(picture.path)[1];
  const folderName = split(where)[0] || where;

  function save() {
    const saving: Saving = {
      how,
      format,
      quality: lossy ? quality : null,
      folder: how === "new" ? folder : null,
      keepCamera,
      keepColours,
      keepLocation,
      always,
    };
    make.mutate(
      { path: `/pictures/${picture.id}/make`, body: { recipe, saving } },
      { onSuccess: () => props.onClose() },
    );
  }

  async function chooseFolder() {
    const chosen = await pickFolder("Where should new pictures go?");
    if (chosen) setFolder(chosen);
  }

  return (
    <>
      <DialogHeader title={`Save ${stem(picture.name)}`} description={<MadeAs plan={plan} />} />
      <DialogBody>
        <div role="radiogroup" aria-label="How to save" className="flex flex-col gap-2">
          <Choice
            chosen={how === "new"}
            onChoose={() => setHow("new")}
            title="As a new picture"
            detail={
              <>
                {name.data && (
                  <span className="font-mono text-12 text-accent-fg [overflow-wrap:anywhere]">
                    {name.data.name}
                  </span>
                )}
                <span className="text-13 text-fg-muted">
                  {folder ? `In ${folderName}.` : `Beside the original in ${folderName}.`} The
                  original stays as it is.{" "}
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      void chooseFolder();
                    }}
                    className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
                  >
                    Choose a folder…
                  </button>
                </span>
              </>
            }
          />
          <Choice
            chosen={how === "replace"}
            onChoose={() => setHow("replace")}
            title="Replace the original"
            detail={
              <span className="text-13 text-fg-muted">
                The original waits in quarantine for 30 days, and History puts it back.
              </span>
            }
          />
        </div>

        {name.data?.taken && (
          <p className="flex gap-2.5 rounded-6 bg-glass px-3 py-2.5 text-13 text-fg-muted leading-normal">
            <span>
              <span className="font-mono text-fg">{name.data.taken}</span> is already there
              {name.data.takenAt ? ` from ${dayAndTime(new Date(name.data.takenAt))}` : ""}, so this
              one gets a number.{" "}
              <button
                type="button"
                onClick={() =>
                  explorer.run(() => showInFolder(`${name.data?.folder}\\${name.data?.taken}`))
                }
                className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
              >
                Show it
              </button>
            </span>
          </p>
        )}

        <div className="flex flex-col gap-3 border-rule border-t pt-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="w-16 text-13 text-fg-muted">Format</span>
            <Segmented
              label="Format"
              value={format}
              options={WRITES.map((each) => ({
                value: each,
                label: each === asIs ? `${each}, as it was` : each,
              }))}
              onChange={setFormat}
              className="flex-wrap"
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
                value={quality}
                onChange={(event) => setQuality(Number(event.target.value))}
                className="flex-1 accent-[var(--color-accent)]"
              />
              <span className="font-mono">
                {quality}
                {name.data && ` · about ${sizeOf(name.data.bytes)}`}
              </span>
            </div>
          )}
          {!lossy && name.data && (
            <p className="text-13 text-fg-muted">
              Kept exactly · about <span className="font-mono">{sizeOf(name.data.bytes)}</span>
            </p>
          )}
          {format === "JPEG" && plan.seeThrough && (
            <p className="text-13 text-fg-muted">
              JPEG has no see-through parts, so they'll be white.
            </p>
          )}
          <fieldset className="flex flex-col gap-1.5 text-13">
            <legend className="pb-1 text-fg-muted">Keep from the original</legend>
            <Check id={ids.camera} checked={keepCamera} onChange={setKeepCamera}>
              The date taken and the camera's details
            </Check>
            <Check id={ids.colours} checked={keepColours} onChange={setKeepColours}>
              Its colours (the colour profile
              {name.data ? `: ${name.data.colour}` : ""})
            </Check>
            <Check
              id={ids.place}
              checked={keepLocation && keepCamera}
              onChange={setKeepLocation}
              disabled={!keepCamera}
            >
              Where it was taken (the location)
            </Check>
          </fieldset>
        </div>
        {(make.isError || explorer.problem) && (
          <p role="alert" className="text-13 text-broken-fg">
            {make.error?.message ?? explorer.problem}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <Check id={ids.always} checked={always} onChange={setAlways}>
          <span className="text-13 text-fg-muted">Always save this way</span>
        </Check>
        <span className="flex gap-2">
          <Button variant="ghost" onClick={props.onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={make.isPending} onClick={save}>
            Save
          </Button>
        </span>
      </DialogFooter>
    </>
  );
}

/** What the picture is made for and with, as the Save board's header says it: "Made for TV 8K,
 * 7680 × 4320", "Made for TV 8K (7680 × 4320), with Warm film at 60%", "With Warm film at 60%,
 * 4032 × 3024". */
function MadeAs({ plan }: { plan: Plan }) {
  const pixels = (
    <span className="font-mono text-fg">
      {plan.width} × {plan.height}
    </span>
  );
  const size = <span className="font-mono text-fg">{plan.label}</span>;
  const look = <span className="text-fg">{plan.look}</span>;
  if (plan.label && plan.look)
    return (
      <>
        Made for {size} ({pixels}), with {look}
      </>
    );
  if (plan.label)
    return (
      <>
        Made for {size}, {pixels}
      </>
    );
  return (
    <>
      With {look}, {pixels}
    </>
  );
}

function Choice(props: {
  chosen: boolean;
  onChoose: () => void;
  title: string;
  detail: ReactNode;
}) {
  return (
    // biome-ignore lint/a11y/useSemanticElements: a card-sized radio with links inside it
    <div
      role="radio"
      aria-checked={props.chosen}
      tabIndex={0}
      onClick={props.onChoose}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return; // "Choose a folder…" inside it
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          props.onChoose();
        }
      }}
      className={cn(
        "press flex cursor-pointer items-start gap-3 rounded-8 border px-3.5 py-3 text-left",
        props.chosen ? "border-accent bg-accent/8" : "border-field-edge bg-glass",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "mt-0.5 size-4 shrink-0 rounded-full",
          props.chosen ? "border-5 border-accent" : "border-[1.5px] border-fg-faint",
        )}
      />
      <span className="flex min-w-0 flex-col gap-1">
        <span className="font-semibold text-14">{props.title}</span>
        {props.detail}
      </span>
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
