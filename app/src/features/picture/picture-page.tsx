import { ChevronLeft, ChevronRight } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import {
  EngineError,
  type PictureDetails,
  shownFrom,
  shownQuery,
  useFolders,
  useNeighbours,
  usePicture,
  useReadAgain,
} from "@/lib/engine";
import { showInFolder, useExplorer } from "@/lib/explorer";
import { size, split, stem, takenOn } from "@/lib/format";
import { cn } from "@/lib/utils";
import { NeighbourStrip } from "./neighbour-strip";
import { Stage, type Zoom } from "./stage";
import { ToolsColumn } from "./tools-column";

// Controls that keep the arrow keys to themselves.
const CONTROLS = "input, textarea, select, [role='group'], [role='radiogroup'], [role='dialog']";
const NOT_HERE = "That picture isn't in your library any more.";

const ZOOMS = [
  { value: "fit", label: "Fit" },
  { value: "100", label: "100%" },
  { value: "400", label: "400%" },
] as const;

/**
 * A picture's page, opened from the Library: the picture large (fitted, or at 100% or 400%), its
 * facts, the strip of its neighbours in the list it came from (the arrow keys go along it), and
 * the column its tools come to.
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

  const to = (other: number) => `/library/pictures/${other}${context ? `?${context}` : ""}`;
  const previous = neighbours.data?.before.at(-1);
  const next = neighbours.data?.after[0];

  // The arrow keys go to the picture before and after, unless they're moving round a control.
  useEffect(() => {
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
  }, [previous, next, navigate, context]);

  const gone = picture.error instanceof EngineError && picture.error.message === NOT_HERE;
  const listed =
    shown.folder === null ? undefined : folders.data?.find((f) => f.id === shown.folder);
  const back = shown.dir ? (shown.dir.split("/").at(-1) ?? shown.dir) : (listed?.name ?? "Library");

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
        </header>

        {gone ? (
          <Gone back={`/library${context ? `?${context}` : ""}`} />
        ) : (
          <>
            <EngineProblem queries={[picture]} />
            {!picture.data && (
              <Loading label="Loading the picture" queries={[picture]}>
                <Skeleton className="h-[60vh] rounded-6" />
              </Loading>
            )}
            {picture.data && <OnStage picture={picture.data} zoom={zoom} />}
          </>
        )}

        {picture.data && neighbours.data && (
          <NeighbourStrip
            label={`Pictures in ${back === "Library" ? "your library" : back}`}
            current={picture.data}
            before={neighbours.data.before}
            after={neighbours.data.after}
            to={to}
          />
        )}
      </div>
      {picture.data && <ToolsColumn picture={picture.data} />}
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

/** The picture, and the line under it: or, for one that can't be shown, why, in its place. */
function OnStage({ picture, zoom }: { picture: PictureDetails; zoom: Zoom }) {
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
      <Stage
        picture={picture}
        zoom={zoom}
        problem={(why) => (
          <Unshown picture={picture} onShow={show} problem={explorer.problem}>
            {why}
          </Unshown>
        )}
      />
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

/** The picture isn't in the library any more: gone from its folder, or the folder taken out. */
function Gone({ back }: { back: string }) {
  return (
    <section className="flex min-h-60 flex-1 flex-col items-start justify-center gap-3 rounded-6 border border-dash border-dashed bg-surface px-7 py-6">
      <h2 className="font-semibold text-16">This picture isn't in your library any more</h2>
      <p className="max-w-150 text-13 text-fg-muted">
        It was moved or deleted since, or its folder was taken out of the library. Mado didn't
        change it.
      </p>
      <Button asChild size="sm">
        <Link to={back}>Back to the library</Link>
      </Button>
    </section>
  );
}
