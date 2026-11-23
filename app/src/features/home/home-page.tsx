import { Plus, Upload } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, PanelSkeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { useOpenPictures } from "@/features/batch/open";
import { useAddFolderPicker } from "@/features/library/add-folder";
import { EmptyLibrary } from "@/features/library/empty-library";
import {
  type Batch,
  type Library,
  type MadeToday,
  madeAddress,
  type Scan,
  useDoneBatches,
  useDuplicateCounts,
  useEngineQuery,
  useLibrary,
  useMadeToday,
  usePictureImage,
  useSearchState,
  useSeenBatch,
  useSettings,
} from "@/lib/engine";
import { openFolder, useExplorer } from "@/lib/explorer";
import { count, dayAndTime, editedAs, size } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SpaceCard } from "./space-card";
import { WontOpen } from "./wont-open";

// The bar's shares, in the greys the boards give them, in the order the folders were added.
const SHARES = ["bg-fg", "bg-fg-faint", "bg-control"];

/** Home, as the Home board draws it: the library in numbers, pictures dropped or picked from the
 * PC to make, what needs the owner (duplicates and bursts to review, pictures that won't open, a
 * batch done), the space on the drives the library uses, what was made today, and adding a
 * folder. Until setup is done, it leads there. */
export function HomePage() {
  const settings = useSettings();
  const library = useLibrary();
  const scan = useEngineQuery<Scan>("/scan");
  const adding = useAddFolderPicker();
  const [seeing, setSeeing] = useState(false);

  if (settings.data && !settings.data.setUp) return <Navigate to="/setup" replace />;
  const found = library.data;
  const empty = found?.folders === 0;

  return (
    <>
      <header className="page-top flex animate-fade-up flex-wrap items-center gap-x-4 gap-y-2.5">
        <h1 className="type-title">Home</h1>
        {found && !empty && <Summary library={found} scan={scan.data} />}
        {found && !empty && (
          <Button className="ml-auto font-medium" disabled={adding.busy} onClick={adding.pick}>
            <Plus size={16} aria-hidden="true" />
            Add a folder
          </Button>
        )}
      </header>
      {adding.problem && !empty && (
        <p role="alert" className="-mt-3 text-13 text-broken-fg">
          {adding.problem}
        </p>
      )}

      <EngineProblem queries={[settings, library]} />
      {(!settings.data || !found) && (
        <Loading label="Loading Home" queries={[settings, library]}>
          <PanelSkeleton rows={3} />
        </Loading>
      )}
      {found && empty && (
        <EmptyLibrary
          className="min-h-90"
          onAdd={adding.pick}
          adding={adding.busy}
          problem={adding.problem}
        />
      )}
      {found && !empty && (
        <div className="grid grid-cols-1 gap-4 standard:grid-cols-3">
          <DropHere />
          <YourLibrary library={found} />
          <NeedsYou library={found} onSeeWhich={() => setSeeing(true)} />
          <SpaceCard />
          <Today />
        </div>
      )}
      {/* Apart from Needs you, which goes once nothing needs the owner: the card stays to say so. */}
      {seeing && <WontOpen onClose={() => setSeeing(false)} />}
    </>
  );
}

/** "4,812 pictures · 3 folders · 38 GB · read today 09:14, 6 new" */
function Summary({ library, scan }: { library: Library; scan: Scan | undefined }) {
  const reading = scan?.state === "running";
  const when = scan?.finishedAt ? dayAndTime(new Date(scan.finishedAt)) : null;
  const changed = [
    scan?.added ? `${count(scan.added)} new` : "",
    scan?.gone ? `${count(scan.gone)} gone` : "",
  ].filter(Boolean);
  return (
    <p className="text-14 text-fg-muted">
      <Figure value={count(library.pictures)} /> pictures ·{" "}
      <Figure value={count(library.folders)} /> {library.folders === 1 ? "folder" : "folders"} ·{" "}
      <Figure value={size(library.size)} />
      {reading && (
        <>
          {" · reading "}
          <Figure value={count(scan.read)} /> of <Figure value={count(scan.toRead)} />
        </>
      )}
      {!reading && when && (
        <>
          {" · read "}
          <Figure value={when} />
          {changed.length > 0 && <>, {changed.join(", ")}</>}
        </>
      )}
    </p>
  );
}

function Figure({ value }: { value: string }) {
  return <span className="font-mono text-fg">{value}</span>;
}

/** Pictures from anywhere on the PC: dropped on the window (anywhere on it), pasted (Ctrl+V,
 * anywhere on it) or picked. One picture opens its page, in the library or not; several, or a
 * folder, open Many at once. */
function DropHere() {
  const opening = useOpenPictures();
  return (
    <section
      aria-labelledby="drop"
      className="flex min-h-53 animate-fade-up flex-wrap items-center gap-x-8 gap-y-5 rounded-8 border border-dash border-dashed bg-surface px-7 py-6 standard:col-span-2"
    >
      <span
        aria-hidden="true"
        className="flex size-14 shrink-0 items-center justify-center rounded-10 bg-raised text-fg"
      >
        <Upload size={26} strokeWidth={1.6} />
      </span>
      <div className="flex flex-[1_1_300px] flex-col gap-1.5">
        <h2 id="drop" className="font-semibold text-20">
          Drop pictures here
        </h2>
        <p className="text-14 text-fg-muted leading-normal">
          Or paste one, or pick them from your PC. Make them right for a phone, a TV or a print,
          give them a look, or cut something out. They don't need to be in your library.
        </p>
        <p className="mt-1 font-mono text-12 text-fg-faint">
          JPEG PNG HEIC RAW WebP AVIF TIFF BMP GIF
        </p>
        {opening.problem && (
          <p role="alert" className="text-13 text-broken-fg">
            {opening.problem}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
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
      </div>
    </section>
  );
}

/** What needs the owner, as the Home board draws it: duplicates and bursts to review (and how far
 * looking for them has got), pictures that won't open, and a batch done ("Holiday is ready for
 * the TV") with its folder to open, which lets it go. Nothing to show, it isn't there. */
function NeedsYou({ library, onSeeWhich }: { library: Library; onSeeWhich: () => void }) {
  const done = useDoneBatches();
  const seen = useSeenBatch();
  const duplicates = useDuplicateCounts().data;
  const explorer = useExplorer();
  const navigate = useNavigate();
  const unopened = Math.max(library.broken - library.damaged, 0);
  const review = duplicates && (duplicates.pictures > 0 || duplicates.looking !== null);
  if (!done.data?.length && !review && unopened === 0) return null;
  return (
    <section
      aria-labelledby="needs"
      className="flex animate-fade-up flex-col rounded-8 border border-edge bg-glass standard:col-span-2"
    >
      <h2 id="needs" className="type-eyebrow px-4.5 pt-3.5 pb-2.5">
        Needs you
      </h2>
      {review && duplicates && (
        <div className="flex items-center gap-3.5 border-edge border-t px-4.5 py-3">
          <span
            aria-hidden="true"
            className={cn(
              "size-3 shrink-0 rounded-full",
              duplicates.looking ? "status-working" : "status-waiting",
            )}
          />
          <span className="w-10.5 font-mono text-15">{count(duplicates.pictures)}</span>
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="font-semibold text-15">Duplicates and bursts</span>
            <span className="text-13 text-fg-muted">
              {duplicates.looking
                ? `Still looking: ${count(duplicates.looking.looked)} of ${count(duplicates.looking.of)} looked at. Keep the sharpest of each; the rest wait in quarantine.`
                : "Keep the sharpest of each; the rest wait in quarantine for 30 days."}
            </span>
          </span>
          <Button
            size="sm"
            className="border-0 bg-fg text-window"
            onClick={() => void navigate("/duplicates")}
          >
            Review
          </Button>
        </div>
      )}
      {unopened > 0 && (
        <div className="flex items-center gap-3.5 border-edge border-t px-4.5 py-3">
          <span aria-hidden="true" className="status-problem size-3 shrink-0 rounded-2" />
          <span className="w-10.5 font-mono text-15">{count(unopened)}</span>
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="font-semibold text-15">Won't open</span>
            <span className="text-13 text-fg-muted">
              Their files are damaged or were only half copied. They're left as they are.
            </span>
          </span>
          <Button size="sm" className="bg-transparent font-medium" onClick={onSeeWhich}>
            See which
          </Button>
        </div>
      )}
      {done.data?.map((batch) => (
        <div key={batch.id} className="flex items-center gap-3.5 border-edge border-t px-4.5 py-3">
          <span aria-hidden="true" className="status-done size-3 shrink-0 rounded-full" />
          <span className="w-10.5 font-mono text-15">{count(batch.done)}</span>
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="font-semibold text-15">{readyWords(batch)}</span>
            <span className="text-13 text-fg-muted">{madeWords(batch)}</span>
          </span>
          {batch.folder ? (
            <Button
              size="sm"
              className="bg-transparent font-medium"
              onClick={() => {
                const folder = batch.folder;
                if (!folder) return;
                explorer.run(() => openFolder(folder));
                seen.mutate({ path: `/batches/${batch.id}/seen` });
              }}
            >
              Open folder
            </Button>
          ) : (
            <Button
              size="sm"
              className="bg-transparent font-medium"
              onClick={() => seen.mutate({ path: `/batches/${batch.id}/seen` })}
            >
              Done
            </Button>
          )}
        </div>
      ))}
      {explorer.problem && (
        <p role="alert" className="border-edge border-t px-4.5 py-2.5 text-13 text-broken-fg">
          {explorer.problem}
        </p>
      )}
    </section>
  );
}

const FOR: Record<string, string> = {
  phone: "the phone",
  tablet: "the tablet",
  laptop: "the laptop",
  monitor: "the monitor",
  ultrawide: "the ultrawide",
  tv: "the TV",
  screen: "your screen",
};

/** "Holiday is ready for the TV", "Scans is ready to print", "Holiday has Warm film". */
export function readyWords(batch: Batch): string {
  if (batch.purpose === "print") return `${batch.source} is ready to print`;
  if (batch.purpose) return `${batch.source} is ready for ${FOR[batch.purpose] ?? "its screen"}`;
  return batch.look ? `${batch.source} has ${batch.look}` : `${batch.source} is ready`;
}

/** "Made for TV 8K overnight, as new pictures in Holiday › Edited." */
function madeWords(batch: Batch): string {
  const what = [
    batch.madeFor ? `for ${batch.madeFor}` : null,
    batch.look ? `with ${batch.look}` : null,
  ]
    .filter(Boolean)
    .join(", ");
  const started = batch.startedAt ? new Date(batch.startedAt).getHours() : 12;
  const overnight = started >= 23 || started < 7 ? " overnight" : "";
  const where =
    batch.how === "replace"
      ? "in place of their originals"
      : batch.into === "beside the originals"
        ? "as new pictures beside the originals"
        : `as new pictures in ${batch.into}`;
  const failed = batch.failed ? ` ${count(batch.failed)} didn't work: the queue says why.` : "";
  return `Made ${what}${overnight}, ${where}.${failed}`;
}

/** What was made today, newest first, each with what it was made for. */
function Today() {
  const today = useMadeToday();
  if (!today.data?.length) return null;
  return (
    <section
      aria-labelledby="today"
      className="flex animate-fade-up flex-col gap-3 rounded-8 border border-edge bg-glass px-4.5 pt-3.5 pb-4 standard:col-span-3"
    >
      <div className="flex items-baseline gap-3">
        <h2 id="today" className="type-eyebrow">
          Made today
        </h2>
        <Link
          to="/history"
          className="ml-auto text-13 text-accent-fg underline underline-offset-3 hover:text-accent-fg-hover"
        >
          History
        </Link>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        {today.data.slice(0, 6).map((made) => (
          <Made key={made.id} made={made} />
        ))}
      </div>
    </section>
  );
}

function Made({ made }: { made: MadeToday }) {
  const image = usePictureImage(madeAddress(made.id));
  const caption = made.madeFor ?? made.look?.replace(/ at \d+%$/, "") ?? editedAs(made.edit) ?? "";
  return (
    <figure className="m-0 flex min-w-0 flex-col gap-1.5">
      <span className="relative block h-23 overflow-hidden rounded-4 bg-behind">
        {image.address && (
          <img src={image.address} alt="" className="size-full animate-fade-in object-cover" />
        )}
      </span>
      <figcaption className="flex min-w-0 justify-between gap-1.5 text-12">
        <span className="truncate">{made.name}</span>
        <span className="shrink-0 font-mono text-fg-muted">{caption}</span>
      </figcaption>
    </figure>
  );
}

/** The library at a glance: its pictures, each folder's share of them, and how far it's been
 * read for search while it's being read. */
function YourLibrary({ library }: { library: Library }) {
  const search = useSearchState().data;
  const parts = library.parts.filter((part) => part.pictures > 0);
  const whole = parts.reduce((sum, part) => sum + part.pictures, 0);
  return (
    <section
      aria-labelledby="your-library"
      className="flex animate-fade-up flex-col gap-3 rounded-8 border border-edge bg-glass px-4.5 py-4"
    >
      <h2 id="your-library" className="type-eyebrow">
        Your library
      </h2>
      <div className="flex items-baseline justify-between">
        <span className="font-medium font-mono text-30">{count(library.pictures)}</span>
        <span className="text-13 text-fg-muted">
          {library.pictures === 1 ? "picture" : "pictures"}
        </span>
      </div>
      {whole > 0 && (
        <div
          role="img"
          aria-label={parts.map((part) => `${part.name} ${count(part.pictures)}`).join(", ")}
          className="flex h-2 origin-left animate-grow-x gap-0.5 overflow-hidden rounded-4"
        >
          {parts.map((part, at) => (
            <span
              key={part.folderId}
              className={cn(SHARES[at % SHARES.length])}
              style={{ width: `${(part.pictures / whole) * 100}%` }}
            />
          ))}
        </div>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3.5 gap-y-1.5 text-13">
        {library.parts.map((part) => (
          <Row key={part.folderId} label={part.name} value={count(part.pictures)} />
        ))}
        {library.reading > 0 && <Row label="Still to read" value={count(library.reading)} />}
        {library.raw > 0 && <Row label="Camera RAW" value={count(library.raw)} />}
        {library.rawWaiting > 0 && (
          <Row label="Waiting for the RAW reader" value={count(library.rawWaiting)} />
        )}
        {library.broken > 0 && <Row label="Won't open" value={count(library.broken)} />}
        {search &&
          search.describer?.state === "ready" &&
          search.read + search.failed < search.of && (
            <Row
              label={search.paused ? "Read for search, paused" : "Read for search"}
              value={`${count(search.read)} of ${count(search.of)}`}
            />
          )}
      </dl>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-fg-muted">{label}</dt>
      <dd className="text-right font-mono">{value}</dd>
    </>
  );
}
