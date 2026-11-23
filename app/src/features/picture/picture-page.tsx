import { ChevronLeft, ChevronRight, Monitor, Undo2 } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { HeartButton } from "@/components/heart";
import { RawReaderNote, useRawReader } from "@/components/raw-reader";
import { useStatusNote } from "@/components/shell/status-note";
import { Loading, Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import {
  type Edit,
  type EditingPlaces,
  type EditStep,
  EngineError,
  type Job,
  type LookStep,
  type Part,
  type PictureDetails,
  type Place,
  type Plan,
  type Quality,
  type Recipe,
  type SizeStep,
  type Stroke,
  shownFrom,
  shownQuery,
  useEdit,
  useFolders,
  useLooks,
  useMarkDamaged,
  useNeighbours,
  usePc,
  usePicture,
  usePictureJobs,
  usePlan,
  useReadAgain,
} from "@/lib/engine";
import { showInFolder, useExplorer } from "@/lib/explorer";
import { madeWith, size, split, stem, takenOn } from "@/lib/format";
import { useSettled } from "@/lib/settled";
import { cn } from "@/lib/utils";
import { EditStage, type EditTool } from "./edit-stage";
import { type Backing, EditTab } from "./edit-tab";
import { bare, NOTHING, tooBig, usePicking } from "./editing";
import { LooksStage } from "./looks-stage";
import { changes, OnlyOnAPart, ORIGINAL, PLAIN, TOUCHES } from "./looks-tab";
import { NeighbourStrip } from "./neighbour-strip";
import { LookOnly, WhereItLives } from "./outside";
import { SizeStage } from "./size-stage";
import { Stage, type Zoom } from "./stage";
import { type Tool, ToolsColumn } from "./tools-column";

// Controls that keep the arrow keys to themselves.
const CONTROLS =
  "input, textarea, select, [role='group'], [role='radiogroup'], [role='dialog'], [role='slider'], [role='tablist']";
const NOT_HERE = "That picture isn't in your library any more.";
const OWN = "/pictures/"; // the address of a picture's page from outside the library
const AS_IT_IS: Recipe = { edit: null, size: null, look: null }; // a paste saved unchanged
const HOLD_KEY = "\\"; // held down, it shows the original, as "Hold to see the original" does

const ZOOMS = [
  { value: "fit", label: "Fit" },
  { value: "100", label: "100%" },
  { value: "400", label: "400%" },
] as const;

/**
 * A picture's page, opened from the Library, or from anywhere (dropped, picked, pasted, from File
 * Explorer), in the library or not: the picture large, its facts, and its tools' column. One from
 * outside the library shows where it lives in place of the breadcrumb, with "Add its folder to
 * the library", and has no neighbours; one in a quarantine is opened to look at only. On the Size
 * tab: fitted or at 100% or 400%, the strip of its neighbours in the list it
 * came from (the arrow keys go along it), and with a size chosen the picture as it'd be made: its
 * shape over it, and before and after at full detail when zoomed in. On the Looks tab, as
 * Picture-Looks draws it: the picture with its look, on the whole picture or only a part, and
 * "Hold to see the original". On the Edit tab, as Picture-Edit draws it: parts picked with a
 * click, then erased, cut out, given a look or blurred behind; a brush for what clicking can't
 * pick; and the subject cut out without a click. What the three tabs set together is one recipe,
 * made by one Save.
 */
export function PicturePage() {
  const id = Number(useParams().id);
  const [query] = useSearchParams();
  const shown = useMemo(() => shownFrom(query), [query]);
  const context = shownQuery(shown);
  const picture = usePicture(id);
  const neighbours = useNeighbours(id, shown);
  const folders = useFolders();
  const navigate = useNavigate();
  const [zoom, setZoom] = useState<Zoom>("fit");
  const [tool, setTool] = useState<Tool>("size");
  // The size and the look chosen stay from picture to picture; what the picture is and the point
  // a crop is around are each picture's own.
  const [sized, setSized] = useState<SizeStep | null>(null);
  const [look, setLook] = useState<LookStep>(PLAIN);
  const [pointed, setPointed] = useState<LookStep | null>(null);
  const [held, setHeld] = useState(false);
  // The edits are each picture's own: another picture starts with none, as the parts picked do.
  const [edits, setEdits] = useState<Edit[]>([]);
  const [editedOn, setEditedOn] = useState<string | null>(null);
  const [editedSince, setEditedSince] = useState<number | null>(null);
  const [editTool, setEditTool] = useState<EditTool>("select");
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [brush, setBrush] = useState(0.04);
  const [eraseQuality, setEraseQuality] = useState<Quality>("fast");
  const [cutQuality, setCutQuality] = useState<Quality>("fast");
  const [backing, setBacking] = useState<Backing>({ behind: "nothing", colour: "#ffffff" });
  const [smeared, setSmeared] = useState(false);
  const [letGo, setLetGo] = useState<string | null>(null);
  const [shownFor, setShownFor] = useState(id);
  const location = useLocation();
  const opened = location.state as { fresh?: boolean } | null;
  const own = location.pathname.startsWith(OWN);
  if (shownFor !== id) {
    setShownFor(id);
    setPointed(null);
    setEdits([]);
    setEditedOn(null);
    setEditedSince(null);
    setStrokes([]);
    setSmeared(false);
    setLetGo(null);
    if (opened?.fresh) {
      // A picture Mado just made, opened from its job: shown as it is, not made again.
      setSized(null);
      setLook(PLAIN);
    } else if (sized && (sized.focus || sized.kind)) {
      setSized({ ...sized, focus: null, kind: null });
    }
  }
  const jobs = usePictureJobs(id);
  // Once its Save is done, the picture is asked for again: one from outside the library, which
  // no scan looks after, may have been replaced.
  const latestJob = jobs.data?.[0];
  const jobSeen = useRef<string | null>(null);
  const refetchPicture = picture.refetch;
  useEffect(() => {
    const now = latestJob ? `${latestJob.id}:${latestJob.state}` : null;
    const before = jobSeen.current;
    jobSeen.current = now;
    if (latestJob?.state === "done" && before !== null && before !== now) void refetchPicture();
  }, [latestJob, refetchPicture]);
  const version = picture.data?.version ?? "";
  // A picture whose file changed since its edits were made: they were made on what it was. When
  // it was Mado's own Save in the original's place, the edits are in it now, so they go quietly.
  if (editedOn !== null && picture.data && picture.data.version !== editedOn) {
    setEditedOn(null);
    setEditedSince(null);
    setEdits([]);
    setStrokes([]);
    setSmeared(false);
    setLetGo(
      savedInPlace(jobs.data?.[0], editedSince)
        ? null
        : `${picture.data.name} changed since Mado read it, so your edits were let go. Start again with it as it is now.`,
    );
  }
  const picking = usePicking(id, version, edits, { keyedByEdits: true });
  const lookPicking = usePicking(id, version, edits, { keyedByEdits: false });
  const editing = useEdit();
  // The plan follows the look once it stops changing (a strength being dragged, say).
  const settled = useSettled(look, 300);
  const ready = picture.data?.state === "ready";
  const lookParts = bare(lookPicking.picked.parts);
  const looked = changes(settled)
    ? lookParts.length
      ? { ...settled, parts: lookParts }
      : settled
    : null;
  const editStep: EditStep | null = edits.length ? { version: editedOn ?? version, edits } : null;
  // Parts a look goes on are tied to the picture as it is, as edits are: a Save that finds it
  // changed saves nothing.
  const recipeEdit = editStep ?? (looked?.parts?.length ? { version, edits: [] } : null);
  // A paste can be saved as it is: nothing chosen is still something to save.
  const recipe: Recipe | null =
    ready && (sized || looked || editStep)
      ? { edit: recipeEdit, size: sized, look: looked }
      : ready && picture.data?.pasted
        ? AS_IT_IS
        : null;
  const big = picture.data ? tooBig(picture.data) : null;
  const places = usePc().data?.editing;
  const plan = usePlan(id, recipe);
  const parts = picking.picked.parts.length;
  useStatusNote(
    tool === "edit" && parts > 0
      ? `${parts} ${parts === 1 ? "part" : "parts"} picked`
      : tool === "looks" && lookPicking.picked.read !== null && lookParts.length > 0
        ? `${lookParts.length === 1 ? "Part" : "Parts"} picked in ${lookPicking.picked.read.toFixed(1)} s`
        : null,
  );
  // The parts a look goes on, picked on the picture as its edits leave it: drawn again once
  // the edits change.
  const editsKey = JSON.stringify(edits);
  const drawnFor = useRef(editsKey);
  useEffect(() => {
    if (drawnFor.current === editsKey) return;
    drawnFor.current = editsKey;
    lookPicking.refresh();
  });

  /** An edit made, the next step of the picture's recipe; the previews show it once it's made. */
  function apply(edit: Edit, replacing = false) {
    const all = replacing ? [...edits.slice(0, -1), edit] : [...edits, edit];
    setSmeared(false);
    editing.mutate(
      { path: `/pictures/${id}/edit`, body: { version: editedOn ?? version, edits: all } },
      {
        onSuccess: (facts) => {
          setEdits(all);
          setEditedOn(editedOn ?? version);
          setEditedSince(editedSince ?? Date.now());
          setLetGo(null);
          setSmeared(facts.smeared);
          if (edit.kind === "erase" && edit.strokes.length) setStrokes([]);
        },
      },
    );
  }

  function startAgain() {
    setEdits([]);
    setEditedOn(null);
    setEditedSince(null);
    setStrokes([]);
    setSmeared(false);
    picking.clear();
    editing.reset();
  }

  const to = (other: number) => `/library/pictures/${other}${context ? `?${context}` : ""}`;
  const previous = neighbours.data?.before.at(-1);
  const next = neighbours.data?.after[0];

  // On the Size tab, the arrow keys go to the picture before and after, unless they're moving
  // round a control; the Looks tab, as its board draws it, has no neighbours.
  useEffect(() => {
    if (tool !== "size") return;
    function go(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (target?.closest(CONTROLS)) return;
      const other = event.key === "ArrowLeft" ? previous : event.key === "ArrowRight" ? next : null;
      if (!other) return;
      event.preventDefault();
      void navigate(`/library/pictures/${other.id}${context ? `?${context}` : ""}`, {
        replace: true,
      });
    }
    window.addEventListener("keydown", go);
    return () => window.removeEventListener("keydown", go);
  }, [tool, previous, next, navigate, context]);

  // On the Edit tab, Esc lets go of what's picked, as its board says.
  useEffect(() => {
    if (tool !== "edit") return;
    const clear = picking.clear;
    function letGo(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (event.target instanceof HTMLElement && event.target.closest("[role='dialog']")) return;
      clear();
    }
    window.addEventListener("keydown", letGo);
    return () => window.removeEventListener("keydown", letGo);
  }, [tool, picking.clear]);

  // On the Looks and Edit tabs, holding the key shows the original, as the button beside the
  // title does on Looks.
  useEffect(() => {
    if (tool !== "looks" && tool !== "edit") return;
    function down(event: KeyboardEvent) {
      // Some keyboards type \ with AltGr, which Windows reports as Ctrl and Alt together.
      const altGr = event.getModifierState("AltGraph");
      if (event.key !== HOLD_KEY || event.metaKey) return;
      if ((event.ctrlKey || event.altKey) && !altGr) return;
      if (event.target instanceof HTMLElement && event.target.closest("input, textarea")) return;
      event.preventDefault();
      setHeld(true);
    }
    function up(event: KeyboardEvent) {
      if (event.key === HOLD_KEY) setHeld(false);
    }
    const letGo = () => setHeld(false);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", letGo);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", letGo);
      setHeld(false);
    };
  }, [tool]);

  // Not there: gone from the library, or from outside it, moved, deleted or on a drive not
  // connected (the engine says which).
  const gone =
    picture.error instanceof EngineError &&
    (picture.error.message === NOT_HERE || (own && picture.error.status === 404));
  const outside = picture.data?.outside ?? (own && !picture.data);
  const listed =
    shown.folder === null ? undefined : folders.data?.find((f) => f.id === shown.folder);
  const back = shown.dir ? (shown.dir.split("/").at(-1) ?? shown.dir) : (listed?.name ?? "Library");
  const looking = tool === "looks";
  const editingNow = tool === "edit";
  const editProblem = editing.isError ? editing.error.message : picking.problem;

  return (
    <div className="-mx-7 -mb-12 flex h-[calc(100vh-4.25rem)]">
      <div className="flex min-w-0 flex-1 flex-col gap-3 px-5.5 pt-4 pb-4">
        <header className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5">
          {picture.data?.outside ? (
            <WhereItLives picture={picture.data} />
          ) : (
            <Button asChild size="sm" className="gap-1.5 pr-2.5 pl-1.5 font-normal">
              <Link to={outside ? "/" : `/library${context ? `?${context}` : ""}`}>
                <ChevronLeft size={16} aria-hidden="true" />
                {outside ? "Home" : back}
              </Link>
            </Button>
          )}
          <div className="flex min-w-0 flex-col gap-0.5">
            <h1 className="truncate font-semibold text-18">
              {picture.data
                ? stem(picture.data.name)
                : gone
                  ? outside
                    ? "Not there any more"
                    : "Not in your library"
                  : "…"}
            </h1>
            {picture.data && (
              <p className="font-mono text-12 text-fg-muted">{factsOf(picture.data)}</p>
            )}
          </div>
          {picture.data && !picture.data.aside && (
            // Its heart, and the wallpaper studio with it chosen: the picture's own, on any tab.
            <span className="flex shrink-0 gap-2">
              <HeartButton picture={picture.data} on="page" />
              <Button
                size="sm"
                aria-label="Make it a wallpaper"
                title="Make it a wallpaper"
                className="w-9 bg-transparent px-0"
                disabled={!ready}
                onClick={() => void navigate(`/wallpaper?picture=${id}`)}
              >
                <Monitor size={16} aria-hidden="true" />
              </Button>
            </span>
          )}
          {editingNow ? (
            <span className="ml-auto flex gap-2">
              <Button
                size="sm"
                aria-label="Undo"
                title="Undo the last edit"
                className="w-9 bg-transparent px-0"
                disabled={edits.length === 0 || editing.isPending}
                onClick={() => {
                  const rest = edits.slice(0, -1);
                  setEdits(rest);
                  if (rest.length === 0) {
                    setEditedOn(null);
                    setEditedSince(null);
                  }
                  setSmeared(false);
                }}
              >
                <Undo2 size={16} aria-hidden="true" />
              </Button>
              <Button
                size="sm"
                className="bg-transparent font-medium"
                disabled={
                  edits.length === 0 && picking.picked.parts.length === 0 && strokes.length === 0
                }
                onClick={startAgain}
              >
                Start again
              </Button>
            </span>
          ) : looking ? (
            <HoldButton held={held} onHeld={setHeld} disabled={!ready} />
          ) : (
            <>
              <Segmented
                label="Zoom"
                value={zoom}
                options={ZOOMS}
                onChange={setZoom}
                className="ml-auto [&_button:not(:first-child)]:font-mono"
              />
              {!outside && (
                <>
                  <Button
                    size="sm"
                    aria-label="Previous picture"
                    className="w-9 bg-transparent px-0"
                    disabled={!previous}
                    onClick={() => previous && void navigate(to(previous.id), { replace: true })}
                  >
                    <ChevronLeft size={16} aria-hidden="true" />
                  </Button>
                  <Button
                    size="sm"
                    aria-label="Next picture"
                    className="w-9 bg-transparent px-0"
                    disabled={!next}
                    onClick={() => next && void navigate(to(next.id), { replace: true })}
                  >
                    <ChevronRight size={16} aria-hidden="true" />
                  </Button>
                </>
              )}
            </>
          )}
        </header>

        {gone ? (
          <Gone
            back={outside ? "/" : `/library${context ? `?${context}` : ""}`}
            replaced={replacedBy(jobs.data?.[0])}
            outside={outside}
            why={outside && picture.error?.message !== NOT_HERE ? picture.error?.message : null}
          />
        ) : (
          <>
            <EngineProblem queries={[picture]} />
            {!picture.data && (
              <Loading label="Loading the picture" queries={[picture]}>
                <Skeleton className="h-[60vh] rounded-6" />
              </Loading>
            )}
            {picture.data && looking && (
              <LooksOnStage
                picture={picture.data}
                edit={editStep}
                sized={sized}
                plan={plan.data ?? null}
                look={pointed ?? look}
                held={held}
                outline={lookPicking.picked.outline}
                parts={lookParts}
                onPick={(x, y, alt) => big === null && lookPicking.click({ x, y, keep: !alt })}
              />
            )}
            {picture.data && editingNow && (
              <EditOnStage
                picture={picture.data}
                edit={editStep}
                tool={editTool}
                picking={picking}
                pickable={big === null}
                working={
                  editing.isPending
                    ? "Making the edit…"
                    : picking.pending
                      ? picking.picked.read === null
                        ? "Reading the picture…"
                        : "Picking…"
                      : null
                }
                workingOn={
                  editing.isPending
                    ? placeOf(
                        (editing.variables?.body as EditStep | undefined)?.edits.at(-1),
                        places,
                      )
                    : picking.pending
                      ? picking.picked.read === null
                        ? (places?.select ?? null)
                        : "processor"
                      : null
                }
                problem={letGo ?? editProblem}
                strokes={strokes}
                brush={brush}
                held={held}
                onStroke={(stroke) => setStrokes([...strokes, stroke])}
                edited={edits.length > 0}
              />
            )}
            {picture.data && !looking && !editingNow && (
              <OnStage
                picture={picture.data}
                edit={editStep}
                zoom={zoom}
                sized={sized}
                look={looked}
                plan={sized ? (plan.data ?? null) : null}
                onFocus={(focus) => sized && setSized({ ...sized, focus })}
              />
            )}
          </>
        )}

        {picture.data && !outside && neighbours.data && !looking && !editingNow && (
          <NeighbourStrip
            label={`Pictures in ${back === "Library" ? "your library" : back}`}
            current={picture.data}
            before={neighbours.data.before}
            after={neighbours.data.after}
            to={to}
          />
        )}
      </div>
      {picture.data?.aside && <LookOnly />}
      {picture.data && !picture.data.aside && (
        <ToolsColumn
          picture={picture.data}
          tool={tool}
          onTool={setTool}
          size={sized}
          onSize={setSized}
          look={look}
          onLook={setLook}
          onPoint={setPointed}
          recipe={recipe}
          plan={plan}
          settling={settled !== look}
          edited={editStep}
          part={
            <OnlyOnAPart
              parts={lookPicking.picked.parts}
              pending={lookPicking.pending}
              problem={lookPicking.problem}
              tooBig={big}
              onSize={() => setTool("size")}
              onRemove={lookPicking.remove}
              onWhole={lookPicking.clear}
            />
          }
          edit={
            <EditTab
              picture={picture.data}
              edit={editStep}
              tooBig={big}
              onSize={() => setTool("size")}
              tool={editTool}
              onTool={setEditTool}
              picked={picking.picked}
              onRemove={picking.remove}
              onStep={picking.step}
              edits={edits}
              applying={editing.isPending}
              problem={editProblem}
              onApply={(edit) => apply(edit)}
              smeared={smeared}
              onBest={() => {
                const last = edits.at(-1);
                if (last?.kind !== "erase") return;
                setEraseQuality("best");
                apply({ ...last, quality: "best" }, true);
              }}
              onLook={() => {
                lookPicking.adopt(picking.picked);
                setTool("looks");
              }}
              quality={eraseQuality}
              onQuality={setEraseQuality}
              backing={backing}
              onBacking={setBacking}
              brush={brush}
              onBrush={setBrush}
              strokes={strokes}
              onClearBrush={() => setStrokes([])}
              cutQuality={cutQuality}
              onCutQuality={setCutQuality}
              recipe={recipe}
              plan={plan.isPlaceholderData ? null : (plan.data ?? null)}
              settling={settled !== look}
            />
          }
        />
      )}
    </div>
  );
}

/** "HEIC · 4032 × 3024 · 3.1 MB · 12 Nov 2026, 18:42" */
function factsOf(picture: PictureDetails): string {
  const parts = [
    picture.format ?? "",
    picture.width && picture.height ? `${picture.width} × ${picture.height}` : "",
    size(picture.size),
    takenOn(picture.takenAt),
  ];
  return parts.filter(Boolean).join(" · ");
}

/** "Hold to see the original", as the Looks board draws it: the picture without its look while
 * it's held down, by the pointer, Space or Enter (and the \ key, anywhere on the tab). */
function HoldButton(props: { held: boolean; onHeld: (held: boolean) => void; disabled: boolean }) {
  const { onHeld } = props;
  return (
    <Button
      size="sm"
      aria-pressed={props.held}
      aria-keyshortcuts="Backslash"
      title="Or hold the \ key"
      disabled={props.disabled}
      className="ml-auto touch-none select-none font-medium"
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        onHeld(true);
      }}
      onPointerUp={() => onHeld(false)}
      onPointerCancel={() => onHeld(false)}
      onLostPointerCapture={() => onHeld(false)}
      onKeyDown={(event) => {
        if (event.key !== " " && event.key !== "Enter") return;
        event.preventDefault();
        onHeld(true);
      }}
      onKeyUp={(event) => {
        if (event.key === " " || event.key === "Enter") onHeld(false);
      }}
      onBlur={() => onHeld(false)}
    >
      Hold to see the original
    </Button>
  );
}

/** The picture with its look, and the line under it the Looks board draws; or, for one that
 * can't be shown, why, in its place. */
function LooksOnStage(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  sized: SizeStep | null;
  plan: Plan | null;
  look: LookStep;
  held: boolean;
  /** Round the parts the look goes on, as fractions of the picture (×1000). */
  outline: string;
  parts: Part[];
  onPick: (x: number, y: number, alt: boolean) => void;
}) {
  const { picture, plan, look } = props;
  const looks = useLooks();
  const explorer = useExplorer();
  if (picture.state !== "ready") {
    return (
      <Unshown
        picture={picture}
        onShow={() => explorer.run(() => showInFolder(picture.path))}
        problem={explorer.problem}
      >
        {null}
      </Unshown>
    );
  }
  const all = [...(looks.data?.looks ?? []), ...(looks.data?.yours ?? [])];
  const name = all.find((each) => each.id === look.look)?.name ?? "";
  const touched = TOUCHES.filter((touch) => look.touches[touch.name] > 0)
    .map((touch) => touch.label.toLowerCase())
    .join(", ");
  const label = [
    look.look === ORIGINAL ? "Original" : `${name} · ${Math.round(look.strength * 100)}%`,
    touched,
    props.parts.length > 0 ? `only on ${props.parts.length === 1 ? "a part" : "parts"}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  // A size shown as the plan decided it, so the picture shown is the one Save makes.
  const decided =
    props.sized && plan
      ? {
          ...props.sized,
          kind: props.sized.kind ?? plan.kind,
          quality: props.sized.quality ?? plan.quality,
          focus: props.sized.focus ?? plan.focus,
        }
      : null;
  return (
    <>
      <LooksStage
        picture={picture}
        edit={props.edit}
        size={decided}
        plan={decided ? plan : null}
        look={changes(look) ? (props.parts.length ? { ...look, parts: props.parts } : look) : null}
        label={label}
        held={props.held}
        outline={props.outline}
        onPick={props.onPick}
      />
      <p className="flex flex-wrap gap-x-4.5 gap-y-1 text-13 text-fg-muted">
        <span>Every look is shown on this picture as you go through them</span>
        <span>Nothing changes until you save</span>
      </p>
    </>
  );
}

/** The picture on the Edit tab, and the line under it, as Picture-Edit draws them: or, for one
 * that can't be shown, why, in its place. */
function EditOnStage(props: {
  picture: PictureDetails;
  edit: EditStep | null;
  tool: EditTool;
  picking: ReturnType<typeof usePicking>;
  /** Parts can be picked: not on a picture too big to edit. */
  pickable: boolean;
  working: string | null;
  workingOn: Place | null;
  problem: string | null;
  strokes: Stroke[];
  brush: number;
  held: boolean;
  edited: boolean;
  onStroke: (stroke: Stroke) => void;
}) {
  const { picture, picking, tool } = props;
  const explorer = useExplorer();
  if (picture.state !== "ready") {
    return (
      <Unshown
        picture={picture}
        onShow={() => explorer.run(() => showInFolder(picture.path))}
        problem={explorer.problem}
      >
        {null}
      </Unshown>
    );
  }
  const read = picking.picked.read;
  return (
    <>
      <EditStage
        picture={picture}
        edit={props.edit}
        tool={props.pickable ? tool : "cutout"}
        picked={picking.picked}
        working={props.working}
        workingOn={props.workingOn}
        problem={props.problem}
        strokes={props.strokes}
        brush={props.brush}
        held={props.held}
        label={props.pickable ? undefined : "Too big to edit"}
        onClick={(x, y, alt) => props.pickable && picking.click({ x, y, keep: !alt })}
        onStep={picking.step}
        onStroke={props.onStroke}
      />
      <p className="flex flex-wrap gap-x-4.5 gap-y-1 text-13 text-fg-muted">
        {tool === "select" && read !== null && (
          <span>
            Mado read the picture in <span className="font-mono text-fg">{read.toFixed(1)} s</span>
            {picking.picked.place === "processor" && " on the processor"}
            {"; every click after that is instant"}
          </span>
        )}
        {tool === "select" && props.pickable && (
          <span>Click to add · Alt-click to take away · Esc to start again</span>
        )}
        {tool === "erase" && props.pickable && (
          <span>Paint over what to erase · Alt to take away</span>
        )}
        {tool === "cutout" && props.pickable && (
          <span>Mado finds the subject itself: no click needed</span>
        )}
        {props.edited && <span>Hold \ to see the original</span>}
      </p>
    </>
  );
}

/** The picture, and the line under it: or, for one that can't be shown, why, in its place. With
 * a size chosen, the picture as it'd be made. */
function OnStage({
  picture,
  edit,
  zoom,
  sized,
  look,
  plan,
  onFocus,
}: {
  picture: PictureDetails;
  edit: EditStep | null;
  zoom: Zoom;
  sized: SizeStep | null;
  look: LookStep | null;
  plan: Plan | null;
  onFocus: (focus: [number, number]) => void;
}) {
  const explorer = useExplorer();
  const navigate = useNavigate();
  const [copied, setCopied] = useState<{ text: string; problem: boolean } | null>(null);
  const show = () => explorer.run(() => showInFolder(picture.path));
  const copy = () =>
    navigator.clipboard.writeText(picture.path).then(
      () => setCopied({ text: "Copied its path.", problem: false }),
      () => setCopied({ text: "Windows didn't let Mado copy it. Try again.", problem: true }),
    );
  // From outside the library, its folder is in the header, where the breadcrumb would be; a
  // pasted picture has no folder of the owner's yet.
  const actions = (
    <span className="flex flex-wrap gap-2">
      {!picture.outside && (
        // The library's pictures nearest it, by what Mado read of each for search.
        <Button
          size="sm"
          className="font-medium"
          onClick={() => void navigate(`/library?like=${picture.id}`)}
        >
          More like this
        </Button>
      )}
      {!picture.outside && (
        <Button size="sm" className="font-medium" onClick={show}>
          Show in folder
        </Button>
      )}
      {!picture.pasted && (
        <Button variant="ghost" size="sm" className="font-medium" onClick={() => void copy()}>
          Copy path
        </Button>
      )}
    </span>
  );
  if (picture.state !== "ready") {
    return (
      <Unshown picture={picture} onShow={show} problem={explorer.problem}>
        {null}
      </Unshown>
    );
  }
  return (
    <>
      {sized && plan ? (
        <SizeStage
          picture={picture}
          edit={edit}
          plan={plan}
          size={sized}
          look={look}
          zoom={zoom}
          onFocus={onFocus}
        />
      ) : edit ? (
        <EditStage
          picture={picture}
          edit={edit}
          tool="cutout"
          picked={NOTHING}
          working={null}
          problem={null}
          strokes={[]}
          brush={0}
          held={false}
          label="As edited"
          onClick={() => undefined}
          onStep={() => undefined}
          onStroke={() => undefined}
        />
      ) : (
        <Stage
          picture={picture}
          zoom={zoom}
          problem={(why) => (
            <Unshown picture={picture} onShow={show} problem={explorer.problem}>
              {why}
            </Unshown>
          )}
        />
      )}
      <div className="flex flex-wrap items-center gap-x-4.5 gap-y-1 text-13 text-fg-muted">
        {picture.camera && <span>{picture.camera}</span>}
        <span>{picture.located ? "Carries where it was taken" : "No place in it"}</span>
        {picture.pasted ? (
          <span>Kept in Mado till you save it</span>
        ) : (
          <span className="min-w-0 truncate font-mono text-12">{split(picture.path)[1]}</span>
        )}
        <span className="ml-auto">{actions}</span>
        {explorer.problem && (
          <p role="alert" className="basis-full text-12 text-broken-fg">
            {explorer.problem}
          </p>
        )}
        {copied && (
          <p
            role={copied.problem ? "alert" : "status"}
            className={cn(
              "basis-full text-12",
              copied.problem ? "text-broken-fg" : "text-fg-muted",
            )}
          >
            {copied.text}
          </p>
        )}
      </div>
    </>
  );
}

/** A picture that can't be shown, in its place: a camera RAW waiting for Mado's RAW reader, one
 * that won't open, or one Mado couldn't show (why, in the engine's words). */
function Unshown(props: {
  picture: PictureDetails;
  onShow: () => void;
  problem: string | null;
  children: ReactNode;
}) {
  const read = useReadAgain();
  const mark = useMarkDamaged();
  const { picture } = props;
  const waiting = picture.state === "waiting";
  const broken = picture.state === "broken";
  // A RAW's own sentence says why best: damaged, or a camera its reader doesn't know yet.
  const rawProblem = broken && picture.raw ? picture.problem : null;
  return (
    <section
      aria-labelledby="unshown"
      className="flex min-h-60 flex-1 flex-col items-start justify-center gap-3 rounded-6 border border-edge bg-glass px-7 py-6"
    >
      <span className="flex items-start gap-3">
        {broken && (
          <span aria-hidden="true" className="status-problem mt-1 size-4 shrink-0 rounded-3" />
        )}
        <span className="flex flex-col gap-1">
          <h2 id="unshown" className="font-semibold text-15">
            <span className="font-medium font-mono">{picture.name}</span>{" "}
            {waiting ? "waits for Mado's RAW reader" : broken ? "won't open" : "can't be shown"}
          </h2>
          <span className="max-w-150 text-13 text-fg-muted leading-normal">
            {waiting &&
              "A camera RAW. Mado leaves it exactly as it is, and shows it once its reader is here."}
            {broken &&
              (rawProblem ??
                "The file is damaged or was only half copied. Mado left it exactly as it is and carried on with the others.")}
            {!waiting && !broken && props.children}
          </span>
          {broken && picture.problem && !rawProblem && (
            <span className="max-w-150 font-mono text-12 text-fg-faint">{picture.problem}</span>
          )}
        </span>
      </span>
      {waiting && <ReaderWait picture={picture} />}
      <span className="flex flex-wrap gap-2">
        <Button size="sm" className="font-medium" onClick={props.onShow}>
          Show in folder
        </Button>
        {broken && (
          <Button
            size="sm"
            className="font-medium"
            disabled={read.isPending}
            onClick={() => read.mutate({ path: `/pictures/${picture.id}/read` })}
          >
            Try again
          </Button>
        )}
        {broken && !picture.damaged && !picture.outside && (
          <Button
            size="sm"
            variant="ghost"
            disabled={mark.isPending}
            onClick={() => mark.mutate({ path: `/pictures/${picture.id}/damaged` })}
          >
            Mark as damaged
          </Button>
        )}
      </span>
      {broken && picture.damaged && (
        <p className="text-12 text-fg-muted">
          Marked as damaged: Mado won't ask about it again, unless its file changes.
        </p>
      )}
      {(props.problem ??
        (read.isError ? read.error.message : mark.isError ? mark.error.message : null)) && (
        <p role="alert" className="text-12 text-broken-fg">
          {props.problem ?? read.error?.message ?? mark.error?.message}
        </p>
      )}
    </section>
  );
}

/** Mado's RAW reader on its way, for a camera RAW waiting for it: once it's here, the RAW is read
 * there and then, and its page shows it. */
function ReaderWait({ picture }: { picture: PictureDetails }) {
  const reader = useRawReader();
  const { mutate: read } = useReadAgain();
  const asked = useRef(false);
  useEffect(() => {
    if (reader?.state === "ready" && !asked.current) {
      asked.current = true;
      read({ path: `/pictures/${picture.id}/read` });
    }
  }, [reader?.state, picture.id, read]);
  return <RawReaderNote tool={reader} className="w-full max-w-150" />;
}

/** Where an edit's model runs: erasing and cutting out the subject as this PC has them; a part
 * cut out or blurred behind is refined on the processor. */
function placeOf(edit: Edit | undefined, places: EditingPlaces | undefined): Place | null {
  if (!edit || !places) return null;
  switch (edit.kind) {
    case "erase":
      return edit.quality === "best" ? places.eraseBest : places.eraseFast;
    case "subject":
      return edit.quality === "best" ? places.cutBest : places.cutFast;
    default:
      return "processor";
  }
}

/** The picture's latest job is Mado's own Save in its original's place, asked for since the
 * edits began (`since`), under way or done: what changes its file then is the edits going in. */
function savedInPlace(job: Job | undefined, since: number | null): boolean {
  if (job?.how !== "replace" || since === null) return false;
  if (Date.parse(job.queuedAt) < since - 1000) return false; // the engine's times are to the second
  if (job.state === "queued" || job.state === "running") return true;
  return job.state === "done" && job.resultName === job.name;
}

/** The job that replaced a picture with one in another format, which the library lists apart. */
function replacedBy(job: Job | undefined): Job | null {
  if (job?.how !== "replace" || job.state !== "done" || !job.resultName) return null;
  return job.resultName !== job.name ? job : null;
}

/** The picture isn't in the library any more: gone from its folder, or the folder taken out; or
 * Mado replaced it, as asked, with one in another format. One from outside the library: moved
 * or deleted, or let go after a month unopened. */
function Gone({
  back,
  replaced,
  outside,
  why,
}: {
  back: string;
  replaced: Job | null;
  outside: boolean;
  /** Why, in the engine's words, for one from outside: moved or deleted, or a drive away. */
  why?: string | null;
}) {
  return (
    <section className="flex min-h-60 flex-1 flex-col items-start justify-center gap-3 rounded-6 border border-dash border-dashed bg-surface px-7 py-6">
      <h2 className="font-semibold text-16">
        {replaced
          ? "Mado replaced this picture"
          : outside
            ? "This picture isn't there any more"
            : "This picture isn't in your library any more"}
      </h2>
      <p className="max-w-150 text-13 text-fg-muted">
        {replaced
          ? `Mado replaced it with ${replaced.resultName}, made ${madeWith(replaced)}, as you asked. The original waits in quarantine for 30 days, and History puts it back.`
          : outside
            ? (why ??
              "It was moved or deleted since, or Mado let it go after a month unopened. Mado didn't change it: drop it on the window or paste it to open it again.")
            : "It was moved or deleted since, or its folder was taken out of the library. Mado didn't change it."}
      </p>
      <span className="flex flex-wrap gap-2">
        {replaced?.resultPicture && (
          <Button asChild size="sm" variant="primary">
            <Link to={`/library/pictures/${replaced.resultPicture.id}`}>
              Open {replaced.resultName}
            </Link>
          </Button>
        )}
        <Button asChild size="sm">
          <Link to={back}>{outside ? "Back to Home" : "Back to the library"}</Link>
        </Button>
      </span>
    </section>
  );
}
