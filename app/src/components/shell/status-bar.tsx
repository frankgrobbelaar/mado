import {
  useActiveJobs,
  useEngine,
  useHealth,
  useLibrary,
  usePc,
  useQueueNow,
  useScan,
} from "@/lib/engine";
import { count, madeWith, stem } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATES = { starting: "Starting", ready: "Ready", failed: "Stopped" } as const;

/** The line of facts at the window's foot: how Mado's engine is, Mado's version, the batch or
 * picture it's making ("Graphics card working · Holiday prints 18 of 48"), what it's doing with
 * the library, and where your pictures stay. It follows the scans, the queue and the jobs for
 * every screen. */
export function StatusBar() {
  const engine = useEngine();
  const version = useHealth().data?.version;
  const scan = useScan().data;
  const folders = useLibrary().data?.folders ?? 0;
  const queue = useQueueNow().data;
  const place = usePc().data?.place;
  const making = useActiveJobs().data?.find((job) => job.state === "running");
  const batch = queue?.working ? queue : null;
  return (
    <footer className="flex h-8 shrink-0 items-center gap-4 border-chrome-edge border-t bg-statusbar px-4 font-mono text-12 text-fg-muted">
      <span className="inline-flex items-center gap-2">
        <span
          aria-hidden="true"
          className={cn(
            "size-1.5 rounded-full",
            engine.state === "ready" && "bg-accent",
            engine.state === "failed" && "bg-danger",
            engine.state === "starting" && "status-working",
          )}
        />
        {STATES[engine.state]}
      </span>
      {version && <span>Mado {version}</span>}
      {batch ? (
        <span className="truncate">
          {place === "processor" ? "Processor" : "Graphics card"} working · {batch.batch}{" "}
          {count(batch.over)} of {count(batch.total)}
        </span>
      ) : (
        making && (
          <span>
            Making {stem(making.name)} {madeWith(making)} · {Math.round(making.progress * 100)}%
          </span>
        )
      )}
      {scan?.state === "running" && (
        <span>
          {scan.stage === "reading"
            ? `Reading ${count(scan.read)} of ${count(scan.toRead)}`
            : `Looking: ${count(scan.found)} found`}
        </span>
      )}
      {scan?.state !== "running" && folders > 0 && (
        <span>
          Watching {count(folders)} {folders === 1 ? "folder" : "folders"}
        </span>
      )}
      <span className="ml-auto truncate">Your pictures stay on this PC</span>
    </footer>
  );
}
