import { Plus } from "lucide-react";
import { Navigate } from "react-router";
import { WindowIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, PanelSkeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { useAddFolderPicker } from "@/features/library/add-folder";
import { EmptyLibrary } from "@/features/library/empty-library";
import { type Library, type Scan, useEngineQuery, useLibrary, useSettings } from "@/lib/engine";
import { count, dayAndTime, size } from "@/lib/format";
import { cn } from "@/lib/utils";

// The bar's shares, in the greys the boards give them, in the order the folders were added.
const SHARES = ["bg-fg", "bg-fg-faint", "bg-control"];

/** Home: the library in numbers, and adding a folder to it. Until setup is done, it leads
 * there. */
export function HomePage() {
  const settings = useSettings();
  const library = useLibrary();
  const scan = useEngineQuery<Scan>("/scan");
  const adding = useAddFolderPicker();

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
          <Coming />
          <YourLibrary library={found} />
        </div>
      )}
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

/** Where the tools go, once they come: said quietly, without pretending to be them. */
function Coming() {
  return (
    <section
      aria-labelledby="coming"
      className="flex animate-fade-up flex-wrap items-center gap-x-8 gap-y-5 rounded-8 border border-edge bg-surface px-7 py-6 standard:col-span-2"
    >
      <WindowIllustration />
      <div className="flex flex-[1_1_300px] flex-col gap-1.5">
        <h2 id="coming" className="font-semibold text-20">
          The tools come next
        </h2>
        <p className="text-14 text-fg-muted leading-normal">
          Making pictures right for a phone, a TV or a print, giving them a look, and cutting
          something out come in Mado's next pieces. Until then it reads your folders and changes
          nothing in them.
        </p>
      </div>
    </section>
  );
}

/** The library at a glance: its pictures, and each folder's share of them. */
function YourLibrary({ library }: { library: Library }) {
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
        {library.raw > 0 && <Row label="Camera RAW, not readable yet" value={count(library.raw)} />}
        {library.broken > 0 && <Row label="Won't open" value={count(library.broken)} />}
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
