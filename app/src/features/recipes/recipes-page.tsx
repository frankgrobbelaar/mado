import { DropdownMenu } from "radix-ui";
import { type ReactNode, useId, useState } from "react";
import { Link } from "react-router";
import { Arrow } from "@/components/arrow";
import { EngineProblem } from "@/components/engine-problem";
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
import { Switch } from "@/components/ui/switch";
import { useOpenPictures } from "@/features/batch/open";
import {
  CutoutDialog,
  FixDialog,
  LookDialog,
  SavingDialog,
  SizeDialog,
} from "@/features/batch/step-dialogs";
import {
  cutoutStep,
  fixStep,
  keepsNothing,
  savingFor,
  savingFrom,
  withStep,
  wordsFor,
} from "@/features/batch/steps";
import { RecipeLine, StepsPanel } from "@/features/batch/steps-panel";
import { pickFolder } from "@/lib/dialogs";
import {
  type BatchSaving,
  type BatchStep,
  type CutoutStepItem,
  type FixStepItem,
  type KeptRecipe,
  type LookStepItem,
  type SizeStepItem,
  useAddWatch,
  useChangeRecipe,
  useChangeWatch,
  useDeleteRecipe,
  useKeepRecipe,
  useRecipes,
  useSettings,
  useStopWatching,
  useWatchFolders,
  type WatchFolder,
} from "@/lib/engine";
import { count, dayAndTime, split } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Recipes and watch folders, as the Recipes board draws them: each recipe's steps as a line, how
 * often and when it was used, "Use on pictures…", Edit and New recipe; each watch folder with its
 * recipe and where its new pictures go, what it last did, on or off, Change, and Add a watch
 * folder.
 */
export function RecipesPage() {
  const recipes = useRecipes();
  const folders = useWatchFolders();
  const [editing, setEditing] = useState<KeptRecipe | "new" | null>(null);
  const [watching, setWatching] = useState<WatchFolder | "new" | null>(null);

  return (
    <>
      <header className="page-top flex animate-fade-up flex-wrap items-center gap-x-4 gap-y-2.5">
        <h1 className="type-title">Recipes and watch folders</h1>
        <p className="text-14 text-fg-muted">
          Steps you use again, run on any batch or on every new picture in a folder
        </p>
        <Button variant="primary" className="ml-auto" onClick={() => setEditing("new")}>
          New recipe
        </Button>
      </header>

      <EngineProblem queries={[recipes, folders]} />
      {(!recipes.data || !folders.data) && (
        <Loading label="Loading your recipes" queries={[recipes, folders]}>
          <PanelSkeleton rows={3} />
          <PanelSkeleton rows={2} />
        </Loading>
      )}

      {recipes.data && (
        <section
          aria-labelledby="recipes"
          className="flex animate-fade-up flex-col rounded-8 border border-edge bg-glass"
        >
          <h2 id="recipes" className="type-eyebrow px-4.5 pt-3.5 pb-2.5">
            Recipes
          </h2>
          {recipes.data.length === 0 && (
            <p className="border-edge border-t px-4.5 py-3.5 text-13 text-fg-muted leading-normal">
              No recipes yet. Keep a batch's steps as one from Many at once, or make one here: "4K,
              then Warm film at 60%, then JPEG into Edited".
            </p>
          )}
          {recipes.data.map((recipe) => (
            <RecipeRow key={recipe.id} recipe={recipe} onEdit={() => setEditing(recipe)} />
          ))}
        </section>
      )}

      {folders.data && recipes.data && (
        <section
          aria-labelledby="watch"
          className="flex animate-fade-up flex-col rounded-8 border border-edge bg-glass"
        >
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4.5 pt-3.5 pb-2.5">
            <h2 id="watch" className="type-eyebrow">
              Watch folders
            </h2>
            <Button
              size="sm"
              className="ml-auto font-medium"
              disabled={recipes.data.length === 0}
              title={
                recipes.data.length === 0
                  ? "Keep a recipe first: a watch folder runs one"
                  : undefined
              }
              onClick={() => setWatching("new")}
            >
              Add a watch folder
            </Button>
          </div>
          {folders.data.length === 0 && (
            <p className="border-edge border-t px-4.5 py-3.5 text-13 text-fg-muted leading-normal">
              {recipes.data.length === 0
                ? "Keep a recipe first: a watch folder runs one on every new picture put in it."
                : "No watch folders yet. Add one, and every new picture put in it is made to its recipe."}
            </p>
          )}
          {folders.data.map((folder) => (
            <WatchRow key={folder.id} folder={folder} onChange={() => setWatching(folder)} />
          ))}
          <p className="border-edge border-t px-4.5 py-3 text-13 text-fg-muted leading-normal">
            A watch folder runs its recipe on every new picture put in it and saves the result as a
            new picture; the originals stay as they are. Big batches wait for the night if{" "}
            <Link
              to="/settings"
              className="text-accent-fg underline-offset-3 hover:text-accent-fg-hover hover:underline"
            >
              Settings
            </Link>{" "}
            says so.
          </p>
        </section>
      )}

      {editing && (
        <RecipeDialog
          recipe={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
      {watching && recipes.data && (
        <WatchDialog
          folder={watching === "new" ? null : watching}
          recipes={recipes.data}
          onClose={() => setWatching(null)}
        />
      )}
    </>
  );
}

function RecipeRow({ recipe, onEdit }: { recipe: KeptRecipe; onEdit: () => void }) {
  const opening = useOpenPictures(recipe.id);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 border-edge border-t px-4.5 py-3">
      <span className="flex flex-[0_0_190px] flex-col gap-0.5">
        <span className="font-semibold text-15">{recipe.name}</span>
        <span className="text-12 text-fg-muted">{used(recipe)}</span>
      </span>
      <span className="flex-[1_1_360px]">
        <RecipeLine words={recipe.words} />
      </span>
      <span className="flex gap-1.5">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button size="sm" className="font-medium" disabled={opening.busy}>
              Use on pictures…
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={4}
              className="z-60 flex min-w-48 flex-col rounded-8 border border-edge bg-dialog p-1.5 text-13 shadow-float"
            >
              <DropdownMenu.Item
                onSelect={() => void opening.choosePictures()}
                className="cursor-pointer rounded-6 px-3 py-2 font-semibold text-fg-soft outline-none data-highlighted:bg-tint/6 data-highlighted:text-fg"
              >
                Pick pictures…
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => void opening.chooseFolder()}
                className="cursor-pointer rounded-6 px-3 py-2 font-semibold text-fg-soft outline-none data-highlighted:bg-tint/6 data-highlighted:text-fg"
              >
                Pick a folder…
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        <Button variant="ghost" size="sm" className="font-medium" onClick={onEdit}>
          Edit
        </Button>
      </span>
      {opening.problem && (
        <p role="alert" className="basis-full text-12 text-broken-fg">
          {opening.problem}
        </p>
      )}
    </div>
  );
}

/** "Used 3 times · tonight", "Used once · 2 Nov", "Not used yet". */
function used(recipe: KeptRecipe): string {
  if (recipe.used === 0 && !recipe.tonight) return "Not used yet";
  const times = recipe.used === 1 ? "Used once" : `Used ${count(recipe.used)} times`;
  if (recipe.tonight) return `${times} · tonight`;
  if (!recipe.usedAt) return times;
  const moment = new Date(recipe.usedAt);
  const today = new Date();
  const when =
    moment.toDateString() === today.toDateString()
      ? "today"
      : moment.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return `${times} · ${when}`;
}

function WatchRow({ folder, onChange }: { folder: WatchFolder; onChange: () => void }) {
  const change = useChangeWatch();
  const results = shortResults(folder.path, folder.results);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 border-edge border-t px-4.5 py-3">
      <Switch
        checked={folder.watching}
        aria-label={`Watch ${folder.path}`}
        disabled={change.isPending}
        onCheckedChange={(on) =>
          change.mutate({
            path: `/watch-folders/${folder.id}`,
            body: {
              path: folder.path,
              recipe: folder.recipe,
              results: folder.results,
              watching: on,
            },
          })
        }
      />
      <span className="flex min-w-0 flex-[1_1_380px] flex-col gap-0.75">
        <span className="text-14 [overflow-wrap:anywhere]">
          <span className="font-mono">{folder.path}</span>{" "}
          <span className="text-fg-faint">
            <Arrow said="then" />
          </span>{" "}
          {folder.recipeName}{" "}
          <span className="text-fg-faint">
            <Arrow said="then" />
          </span>{" "}
          <span className="font-mono">{results}</span>
        </span>
        <span className="flex items-center gap-2 text-12 text-fg-muted">
          {!folder.watching ? (
            "Off"
          ) : folder.problem ? (
            <>
              <span aria-hidden="true" className="status-problem size-2.5 shrink-0 rounded-full" />
              <span className="text-broken-fg">{folder.problem}</span>
            </>
          ) : !folder.connected ? (
            <>
              <span aria-hidden="true" className="status-waiting size-2.5 rounded-full" />
              {folder.path.slice(0, 2)} isn't connected; it waits for it
            </>
          ) : folder.ranAt ? (
            <>
              <span aria-hidden="true" className="status-done size-2.5 rounded-full" />
              Ran <Moment at={folder.ranAt} /> on{" "}
              <span className="font-mono text-fg">{count(folder.ranOn)}</span>{" "}
              {folder.ranOn === 1 ? "picture" : "pictures"}
            </>
          ) : (
            <>
              <span aria-hidden="true" className="status-waiting size-2.5 rounded-full" />
              Waiting for new pictures
            </>
          )}
        </span>
        {change.isError && (
          <span role="alert" className="text-12 text-broken-fg">
            {change.error.message}
          </span>
        )}
      </span>
      <Button variant="ghost" size="sm" className="font-medium" onClick={onChange}>
        Change
      </Button>
    </div>
  );
}

/** "today 14:02", the time in the mono, as the board writes it. */
function Moment({ at }: { at: string }) {
  const said = dayAndTime(new Date(at));
  const cut = said.lastIndexOf(" ");
  return (
    <>
      {said.slice(0, cut)} <span className="font-mono text-fg">{said.slice(cut + 1)}</span>
    </>
  );
}

/** Where a watch folder's pictures go, said from the folder it sits in when it's inside it:
 * "To TV\Done". */
function shortResults(folder: string, results: string): string {
  const parent = split(folder)[1];
  return parent && results.toLowerCase().startsWith(`${parent.toLowerCase()}\\`)
    ? results.slice(parent.length + 1)
    : results;
}

/** A recipe made or changed: its name, its steps (each with Change) and how it saves. */
function RecipeDialog({ recipe, onClose }: { recipe: KeptRecipe | null; onClose: () => void }) {
  const settings = useSettings();
  const [name, setName] = useState(recipe?.name ?? "");
  const [steps, setSteps] = useState<BatchStep[]>(recipe?.steps ?? []);
  const [chosenSaving, setSaving] = useState<BatchSaving>(
    recipe?.saving ?? { ...savingFrom(settings.data), how: "new", folder: "Edited" },
  );
  const saving = savingFor(steps, chosenSaving);
  const cut = steps.find((step): step is CutoutStepItem => step.step === "cutout") ?? null;
  const fixing = steps.find((step): step is FixStepItem => step.step === "fix") ?? null;
  const [editing, setEditing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const keep = useKeepRecipe();
  const change = useChangeRecipe();
  const remove = useDeleteRecipe();
  const doing = recipe ? change : keep;
  const id = useId();
  const size_ = steps.find((each): each is SizeStepItem => each.step === "size") ?? null;
  const look = steps.find((each): each is LookStepItem => each.step === "look") ?? null;
  const words = recipe && sameSteps(recipe, steps, saving) ? recipe.words : wordsFor(steps, saving);

  function save() {
    doing.mutate(
      { path: recipe ? `/recipes/${recipe.id}` : "/recipes", body: { name, steps, saving } },
      { onSuccess: onClose },
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[min(46rem,calc(100vw-2rem))]">
        <DialogHeader
          title={recipe ? `Edit ${recipe.name}` : "New recipe"}
          description="Steps kept by name: use them on any batch, or on every new picture in a watch folder."
        />
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
          <StepsPanel
            steps={steps}
            words={words}
            onChange={setEditing}
            onAdd={(kind) => {
              if (kind === "cutout") setSteps(withStep(steps, cutoutStep(), "cutout"));
              if (kind === "fix") setSteps(withStep(steps, fixStep(), "fix"));
              setEditing(kind);
            }}
          />
          {(doing.isError || remove.isError) && (
            <p role="alert" className="text-13 text-broken-fg">
              {doing.error?.message ?? remove.error?.message}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          {recipe ? (
            <Button
              variant="ghost"
              size="sm"
              className="text-danger"
              onClick={() => setDeleting(true)}
            >
              Delete…
            </Button>
          ) : (
            <span />
          )}
          <span className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!name.trim() || steps.length === 0 || doing.isPending}
              onClick={save}
            >
              {recipe ? "Save" : "Keep it"}
            </Button>
          </span>
        </DialogFooter>
        {editing === "size" && (
          <SizeDialog
            step={size_}
            onStep={(step) => setSteps(withStep(steps, step, "size"))}
            onRemove={
              size_
                ? () => {
                    setSteps(withStep(steps, null, "size"));
                    setEditing(null);
                  }
                : null
            }
            onClose={() => setEditing(null)}
          />
        )}
        {editing === "look" && (
          <LookDialog
            step={look}
            picture={null}
            onStep={(step) => setSteps(withStep(steps, step, "look"))}
            onRemove={
              look
                ? () => {
                    setSteps(withStep(steps, null, "look"));
                    setEditing(null);
                  }
                : null
            }
            onClose={() => setEditing(null)}
          />
        )}
        {editing === "cutout" && cut && (
          <CutoutDialog
            step={cut}
            onStep={(step) => setSteps(withStep(steps, step, "cutout"))}
            onRemove={() => {
              setSteps(withStep(steps, null, "cutout"));
              setEditing(null);
            }}
            onClose={() => setEditing(null)}
          />
        )}
        {editing === "fix" && fixing && (
          <FixDialog
            step={fixing}
            onStep={(step) => setSteps(withStep(steps, step, "fix"))}
            onRemove={() => {
              setSteps(withStep(steps, null, "fix"));
              setEditing(null);
            }}
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
            onClose={() => setEditing(null)}
          />
        )}
        {deleting && recipe && (
          <Dialog open onOpenChange={(open) => !open && setDeleting(false)}>
            <DialogContent className="w-[min(28rem,calc(100vw-2rem))]">
              <DialogHeader
                title={`Delete ${recipe.name}?`}
                description="It leaves your recipes. Batches made with it keep their steps, and the pictures stay as they are."
              />
              <DialogFooter>
                <span />
                <span className="flex gap-2">
                  <Button variant="ghost" onClick={() => setDeleting(false)}>
                    Keep it
                  </Button>
                  <Button
                    variant="danger"
                    disabled={remove.isPending}
                    onClick={() =>
                      remove.mutate(
                        { path: `/recipes/${recipe.id}` },
                        {
                          onSuccess: onClose,
                          onSettled: () => setDeleting(false),
                        },
                      )
                    }
                  >
                    Delete
                  </Button>
                </span>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </DialogContent>
    </Dialog>
  );
}

function sameSteps(recipe: KeptRecipe, steps: BatchStep[], saving: BatchSaving): boolean {
  return (
    JSON.stringify(recipe.steps) === JSON.stringify(steps) &&
    JSON.stringify(recipe.saving) === JSON.stringify(saving)
  );
}

/** A watch folder added or changed: the folder, its recipe, where its pictures go, on or off. */
function WatchDialog(props: {
  folder: WatchFolder | null;
  recipes: KeptRecipe[];
  onClose: () => void;
}) {
  const { folder, recipes } = props;
  const [path, setPath] = useState(folder?.path ?? "");
  const [recipe, setRecipe] = useState(folder?.recipe ?? recipes[0]?.id ?? 0);
  const [results, setResults] = useState(folder?.results ?? "Done");
  const [on, setOn] = useState(folder?.watching ?? true);
  const add = useAddWatch();
  const change = useChangeWatch();
  const stop = useStopWatching();
  const doing = folder ? change : add;
  const switchId = useId();

  async function chooseFolder() {
    const chosen = await pickFolder("Which folder should Mado watch?");
    if (chosen) setPath(chosen);
  }

  async function chooseResults() {
    const chosen = await pickFolder("Where should its new pictures go?");
    if (chosen) setResults(chosen);
  }

  function save() {
    doing.mutate(
      {
        path: folder ? `/watch-folders/${folder.id}` : "/watch-folders",
        body: { path, recipe, results, watching: on },
      },
      { onSuccess: props.onClose },
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(36rem,calc(100vw-2rem))]">
        <DialogHeader
          title={folder ? "Change the watch folder" : "Add a watch folder"}
          description="Every new picture put in it is made to its recipe, once it's finished copying, and saved as a new picture. What's in it already is left alone."
        />
        <DialogBody>
          <Field label="The folder">
            <span className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate rounded-6 border border-field-edge bg-field px-2.5 py-2 font-mono text-13">
                {path || "None chosen yet"}
              </span>
              <Button size="sm" onClick={() => void chooseFolder()}>
                Choose…
              </Button>
            </span>
          </Field>
          <Field label="Its recipe">
            <Segmented
              label="Its recipe"
              value={String(recipe)}
              options={recipes.map((each) => ({ value: String(each.id), label: each.name }))}
              onChange={(chosen) => setRecipe(Number(chosen))}
              className="flex-wrap"
            />
          </Field>
          <Field label="Where its new pictures go">
            <span className="flex items-center gap-2">
              <Input
                aria-label="Where its new pictures go"
                value={results}
                onChange={(event) => setResults(event.target.value)}
                className={cn("h-9 flex-1 font-mono text-13")}
              />
              <Button size="sm" onClick={() => void chooseResults()}>
                Choose…
              </Button>
            </span>
            <span className="text-12 text-fg-faint">
              A name is a folder inside it, which it never takes pictures from.
            </span>
          </Field>
          <span className="flex items-center gap-2.5 text-13">
            <Switch id={switchId} checked={on} onCheckedChange={setOn} />
            <label htmlFor={switchId} className="cursor-pointer">
              Watching
            </label>
          </span>
          {(doing.isError || stop.isError) && (
            <p role="alert" className="text-13 text-broken-fg">
              {doing.error?.message ?? stop.error?.message}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          {folder ? (
            <Button
              variant="ghost"
              size="sm"
              className="text-danger"
              disabled={stop.isPending}
              onClick={() =>
                stop.mutate({ path: `/watch-folders/${folder.id}` }, { onSuccess: props.onClose })
              }
            >
              Stop watching it
            </Button>
          ) : (
            <span />
          )}
          <span className="flex gap-2">
            <Button variant="ghost" onClick={props.onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!path || !recipe || !results.trim() || doing.isPending}
              onClick={save}
            >
              {folder ? "Save" : "Watch it"}
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field(props: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-13 text-fg-muted">{props.label}</span>
      {props.children}
    </div>
  );
}
