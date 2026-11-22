import { ChevronLeft, ChevronRight } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import {
  EngineError,
  type Job,
  type LookStep,
  type PictureDetails,
  type Plan,
  type Recipe,
  type SizeStep,
  shownFrom,
  shownQuery,
  useFolders,
  useLooks,
  useNeighbours,
  usePicture,
  usePictureJobs,
  usePlan,
  useReadAgain,
} from "@/lib/engine";
import { showInFolder, useExplorer } from "@/lib/explorer";
import { madeWith, size, split, stem, takenOn } from "@/lib/format";
import { useSettled } from "@/lib/settled";
import { cn } from "@/lib/utils";
import { LooksStage } from "./looks-stage";
import { changes, ORIGINAL, PLAIN, TOUCHES } from "./looks-tab";
import { NeighbourStrip } from "./neighbour-strip";
import { SizeStage } from "./size-stage";
import { Stage, type Zoom } from "./stage";
import { type Tool, ToolsColumn } from "./tools-column";

// Controls that keep the arrow keys to themselves.
const CONTROLS =
  "input, textarea, select, [role='group'], [role='radiogroup'], [role='dialog'], [role='slider'], [role='tablist']";
const NOT_HERE = "That picture isn't in your library any more.";
const HOLD_KEY = "\\"; // held down, it shows the original, as "Hold to see the original" does

const ZOOMS = [
  { value: "fit", label: "Fit" },
  { value: "100", label: "100%" },
  { value: "400", label: "400%" },
] as const;

/**
 * A picture's page, opened from the Library: the picture large, its facts, and its tools'
 * column. On the Size tab: fitted or at 100% or 400%, the strip of its neighbours in the list it
 * came from (the arrow keys go along it), and with a size chosen the picture as it'd be made: its
 * shape over it, and before and after at full detail when zoomed in. On the Looks tab, as
 * Picture-Looks draws it: the picture with its look, and "Hold to see the original". What the two
 * tabs set together is one recipe, made by one Save.
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
  const [shownFor, setShownFor] = useState(id);
  const opened = useLocation().state as { fresh?: boolean } | null;
  if (shownFor !== id) {
    setShownFor(id);
    setPointed(null);
    if (opened?.fresh) {
      // A picture Mado just made, opened from its job: shown as it is, not made again.
      setSized(null);
      setLook(PLAIN);
    } else if (sized && (sized.focus || sized.kind)) {
      setSized({ ...sized, focus: null, kind: null });
    }
  }
  const jobs = usePictureJobs(id);
  // The plan follows the look once it stops changing (a strength being dragged, say).
  const settled = useSettled(look, 300);
  const ready = picture.data?.state === "ready";
  const looked = changes(settled) ? settled : null;
  const recipe: Recipe | null = ready && (sized || looked) ? { size: sized, look: looked } : null;
  const plan = usePlan(id, recipe);

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

  // On the Looks tab, holding the key shows the original, as the button beside the title does.
  useEffect(() => {
    if (tool !== "looks") return;
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

  const gone = picture.error instanceof EngineError && picture.error.message === NOT_HERE;
  const listed =
    shown.folder === null ? undefined : folders.data?.find((f) => f.id === shown.folder);
  const back = shown.dir ? (shown.dir.split("/").at(-1) ?? shown.dir) : (listed?.name ?? "Library");
  const looking = tool === "looks";

  return (
    <div className="-mx-7 -mb-12 flex h-[calc(100vh-4.25rem)]">
      <div className="flex min-w-0 flex-1 flex-col gap-3 px-5.5 pt-4 pb-4">
        <header className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5">
          <Button asChild size="sm" className="gap-1.5 pr-2.5 pl-1.5 font-normal">
            <Link to={`/library${context ? `?${context}` : ""}`}>
              <ChevronLeft size={16} aria-hidden="true" />
              {back}
            </Link>
          </Button>
          <div className="flex min-w-0 flex-col gap-0.5">
            <h1 className="truncate font-semibold text-18">
              {picture.data ? stem(picture.data.name) : gone ? "Not in your library" : "…"}
            </h1>
            {picture.data && (
              <p className="font-mono text-12 text-fg-muted">{factsOf(picture.data)}</p>
            )}
          </div>
          {looking ? (
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
        </header>

        {gone ? (
          <Gone
            back={`/library${context ? `?${context}` : ""}`}
            replaced={replacedBy(jobs.data?.[0])}
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
                sized={sized}
                plan={plan.data ?? null}
                look={pointed ?? look}
                held={held}
              />
            )}
            {picture.data && !looking && (
              <OnStage
                picture={picture.data}
                zoom={zoom}
                sized={sized}
                look={looked}
                plan={sized ? (plan.data ?? null) : null}
                onFocus={(focus) => sized && setSized({ ...sized, focus })}
              />
            )}
          </>
        )}

        {picture.data && neighbours.data && !looking && (
          <NeighbourStrip
            label={`Pictures in ${back === "Library" ? "your library" : back}`}
            current={picture.data}
            before={neighbours.data.before}
            after={neighbours.data.after}
            to={to}
          />
        )}
      </div>
      {picture.data && (
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
  sized: SizeStep | null;
  plan: Plan | null;
  look: LookStep;
  held: boolean;
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
        size={decided}
        plan={decided ? plan : null}
        look={changes(look) ? look : null}
        label={label}
        held={props.held}
      />
      <p className="flex flex-wrap gap-x-4.5 gap-y-1 text-13 text-fg-muted">
        <span>Every look is shown on this picture as you go through them</span>
        <span>Nothing changes until you save</span>
      </p>
    </>
  );
}

/** The picture, and the line under it: or, for one that can't be shown, why, in its place. With
 * a size chosen, the picture as it'd be made. */
function OnStage({
  picture,
  zoom,
  sized,
  look,
  plan,
  onFocus,
}: {
  picture: PictureDetails;
  zoom: Zoom;
  sized: SizeStep | null;
  look: LookStep | null;
  plan: Plan | null;
  onFocus: (focus: [number, number]) => void;
}) {
  const explorer = useExplorer();
  const [copied, setCopied] = useState<{ text: string; problem: boolean } | null>(null);
  const show = () => explorer.run(() => showInFolder(picture.path));
  const copy = () =>
    navigator.clipboard.writeText(picture.path).then(
      () => setCopied({ text: "Copied its path.", problem: false }),
      () => setCopied({ text: "Windows didn't let Mado copy it. Try again.", problem: true }),
    );
  const actions = (
    <span className="flex flex-wrap gap-2">
      <Button size="sm" className="font-medium" onClick={show}>
        Show in folder
      </Button>
      <Button variant="ghost" size="sm" className="font-medium" onClick={() => void copy()}>
        Copy path
      </Button>
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
          plan={plan}
          size={sized}
          look={look}
          zoom={zoom}
          onFocus={onFocus}
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
        <span className="min-w-0 truncate font-mono text-12">{split(picture.path)[1]}</span>
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

/** A picture that can't be shown, in its place: camera RAW, one that won't open, or one Mado
 * couldn't show (why, in the engine's words). */
function Unshown(props: {
  picture: PictureDetails;
  onShow: () => void;
  problem: string | null;
  children: ReactNode;
}) {
  const read = useReadAgain();
  const { picture } = props;
  const raw = picture.state === "raw";
  const broken = picture.state === "broken";
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
            {raw ? (
              "Camera RAW isn't readable yet"
            ) : (
              <>
                <span className="font-medium font-mono">{picture.name}</span>{" "}
                {broken ? "won't open" : "can't be shown"}
              </>
            )}
          </h2>
          <span className="max-w-150 text-13 text-fg-muted leading-normal">
            {raw &&
              `Mado lists ${picture.name} and leaves it exactly as it is. Reading camera RAW comes with a reader Mado downloads the first time it's needed.`}
            {broken &&
              "The file is damaged or was only half copied. Mado left it exactly as it is and carried on with the others."}
            {!raw && !broken && props.children}
          </span>
          {broken && picture.problem && (
            <span className="max-w-150 font-mono text-12 text-fg-faint">{picture.problem}</span>
          )}
        </span>
      </span>
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
      </span>
      {(props.problem ?? (read.isError ? read.error.message : null)) && (
        <p role="alert" className="text-12 text-broken-fg">
          {props.problem ?? read.error?.message}
        </p>
      )}
    </section>
  );
}

/** The job that replaced a picture with one in another format, which the library lists apart. */
function replacedBy(job: Job | undefined): Job | null {
  if (job?.how !== "replace" || job.state !== "done" || !job.resultName) return null;
  return job.resultName !== job.name ? job : null;
}

/** The picture isn't in the library any more: gone from its folder, or the folder taken out; or
 * Mado replaced it, as asked, with one in another format. */
function Gone({ back, replaced }: { back: string; replaced: Job | null }) {
  return (
    <section className="flex min-h-60 flex-1 flex-col items-start justify-center gap-3 rounded-6 border border-dash border-dashed bg-surface px-7 py-6">
      <h2 className="font-semibold text-16">
        {replaced ? "Mado replaced this picture" : "This picture isn't in your library any more"}
      </h2>
      <p className="max-w-150 text-13 text-fg-muted">
        {replaced
          ? `Mado replaced it with ${replaced.resultName}, made ${madeWith(replaced)}, as you asked. The original waits in quarantine for 30 days, and History puts it back.`
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
          <Link to={back}>Back to the library</Link>
        </Button>
      </span>
    </section>
  );
}
