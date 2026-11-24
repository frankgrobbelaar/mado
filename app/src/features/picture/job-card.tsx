import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { type Job, useCancelJob } from "@/lib/engine";
import { showInFolder, useExplorer } from "@/lib/explorer";
import { about, madeWith, split, stem } from "@/lib/format";

const STAGES = {
  reading: "Reading the picture",
  editing: "Making the edits",
  shaping: "Drawing the new edges",
  fixing: "Fixing it",
  making: "Making it bigger",
  depthing: "Giving it depth",
  painting: "Painting it",
  looking: "Giving it its look",
  saving: "Saving it",
} as const;

const RECENT = 60 * 60 * 1000; // a job over this long ago is History's to show, not this card's

/**
 * The job making a picture, in the Size and Looks tabs: its stage, how far it is and the time
 * left, with Cancel till it saves; then what it saved, why it didn't work, or that it was
 * cancelled.
 */
export function JobCard({ job }: { job: Job }) {
  const cancel = useCancelJob();
  const explorer = useExplorer();
  const finished = job.finishedAt ? Date.now() - new Date(job.finishedAt).getTime() : 0;
  if (finished > RECENT) return null;
  const name = stem(job.name);
  if (job.state === "queued" || job.state === "running") {
    const percent = Math.round(job.progress * 100);
    return (
      <section
        aria-label={`Making ${name}`}
        className="flex flex-col gap-2 rounded-6 border border-edge bg-glass p-3"
      >
        <div className="flex items-baseline gap-2 text-13">
          <span className="font-semibold">
            {job.state === "queued"
              ? job.heldUntil
                ? "Waiting: it's open in another app"
                : "Waiting to start"
              : STAGES[job.stage ?? "reading"]}
          </span>
          <span className="ml-auto font-mono text-12">{percent}%</span>
        </div>
        {job.state === "queued" && job.heldUntil && (
          <p className="text-12 text-fg-muted leading-normal">
            Close it there and Mado tries again by itself, every 30 seconds for 10 minutes.
          </p>
        )}
        <div
          role="progressbar"
          aria-label={`Making ${name} ${madeWith(job)}`}
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-1.5 overflow-hidden rounded-3 bg-track"
        >
          <div
            className="h-full bg-accent transition-[width] duration-320 ease-mado"
            style={{ width: `${percent}%` }}
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-12 text-fg-muted">
            {job.secondsLeft !== null ? `${about(job.secondsLeft)} left` : "Working out the time…"}
          </span>
          {job.stage !== "saving" && (
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate({ path: `/jobs/${job.id}/cancel` })}
            >
              Cancel
            </Button>
          )}
        </div>
      </section>
    );
  }
  if (job.state === "done" && job.result) {
    const [file, folder] = split(job.result);
    return (
      <section
        role="status"
        aria-label="Saved"
        className="flex flex-col gap-1.5 rounded-6 border border-edge bg-glass p-3"
      >
        <span className="flex items-start gap-2">
          <span aria-hidden="true" className="status-done mt-1 size-2.5 shrink-0 rounded-full" />
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="font-semibold text-13">
              Saved <span className="font-medium font-mono [overflow-wrap:anywhere]">{file}</span>
            </span>
            <span className="text-12 text-fg-muted">
              {job.how === "replace"
                ? "In its original's place. The original waits in quarantine; History puts it back."
                : `As a new picture in ${split(folder)[0] || folder}. History can take it away.`}
            </span>
          </span>
        </span>
        <span className="flex flex-wrap gap-1.5">
          <Button size="sm" onClick={() => explorer.run(() => showInFolder(job.result ?? ""))}>
            Show in folder
          </Button>
          {job.resultPicture && job.resultPicture.id !== job.pictureId && (
            <Button asChild size="sm" variant="ghost">
              {/* As it is: the size and look that made it aren't kept for it. */}
              <Link to={`/library/pictures/${job.resultPicture.id}`} state={{ fresh: true }}>
                Open it
              </Link>
            </Button>
          )}
        </span>
        {explorer.problem && (
          <p role="alert" className="text-12 text-broken-fg">
            {explorer.problem}
          </p>
        )}
      </section>
    );
  }
  if (job.state === "failed") {
    return (
      <section
        role="alert"
        className="flex items-start gap-2 rounded-6 border border-edge bg-glass p-3 text-13"
      >
        <span aria-hidden="true" className="status-problem mt-1 size-3 shrink-0 rounded-2" />
        <span className="flex flex-col gap-0.5">
          <span className="font-semibold">
            {name} wasn't made {madeWith(job)}
          </span>
          <span className="text-fg-muted leading-normal">{job.problem}</span>
        </span>
      </section>
    );
  }
  if (job.state === "cancelled") {
    return (
      <p role="status" className="text-13 text-fg-muted">
        Cancelled. Nothing was saved, and the original is as it was.
      </p>
    );
  }
  return null;
}
