import { Toolbar } from "radix-ui";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { PictureItem } from "@/lib/engine";
import { showFiles } from "@/lib/explorer";
import { count, split } from "@/lib/format";
import { cn } from "@/lib/utils";

const MOST_FOLDERS = 3; // Explorer opens a window for each folder: more than this is a nuisance

/**
 * What can be done with the ticked pictures now: make them many at once, show them in Explorer,
 * copy their paths, or clear the ticks. A toolbar: Tab reaches it once, and the arrow keys go
 * along its buttons.
 */
export function TickedBar({
  ticked,
  onClear,
  onBatch,
}: {
  ticked: PictureItem[];
  onClear: () => void;
  /** Many at once with them: only those that can be made (not camera RAW, not broken). */
  onBatch: () => void;
}) {
  const [note, setNote] = useState<{ text: string; problem: boolean } | null>(null);
  const days = new Set(ticked.map((picture) => picture.takenAt.slice(0, 10))).size;
  const folders = new Set(ticked.map((picture) => split(picture.path)[1].toLowerCase())).size;
  const paths = ticked.map((picture) => picture.path);

  function show() {
    setNote(null);
    showFiles(paths).catch((error: unknown) => setNote({ text: String(error), problem: true }));
  }

  function copy() {
    navigator.clipboard.writeText(paths.join("\n")).then(
      () =>
        setNote({
          text: paths.length === 1 ? "Copied its path." : `Copied ${count(paths.length)} paths.`,
          problem: false,
        }),
      () => setNote({ text: "Windows didn't let Mado copy them. Try again.", problem: true }),
    );
  }

  return (
    <Toolbar.Root
      aria-label="Ticked pictures"
      className="flex animate-fade-up flex-wrap items-center gap-x-2.5 gap-y-2 rounded-8 border border-edge bg-glass px-3 py-2.5"
    >
      <span className="font-semibold text-14">
        <span className="font-mono">{count(ticked.length)}</span> ticked
      </span>
      <span className="text-13 text-fg-muted">
        from {days} {days === 1 ? "day" : "days"}
      </span>
      <div className="ml-auto flex flex-wrap gap-2">
        <Toolbar.Button asChild>
          <Button
            variant="primary"
            size="sm"
            disabled={!ticked.some((picture) => picture.state === "ready")}
            onClick={onBatch}
          >
            Many at once…
          </Button>
        </Toolbar.Button>
        {folders <= MOST_FOLDERS && (
          <Toolbar.Button asChild>
            <Button size="sm" className="font-medium" onClick={show}>
              {folders === 1 ? "Show in folder" : `Show in ${folders} folders`}
            </Button>
          </Toolbar.Button>
        )}
        <Toolbar.Button asChild>
          <Button size="sm" className="font-medium" onClick={copy}>
            {ticked.length === 1 ? "Copy path" : "Copy paths"}
          </Button>
        </Toolbar.Button>
        <Toolbar.Button asChild>
          <Button variant="ghost" size="sm" className="font-medium" onClick={onClear}>
            Clear
          </Button>
        </Toolbar.Button>
      </div>
      {note && (
        <p
          role={note.problem ? "alert" : "status"}
          className={cn("basis-full text-12", note.problem ? "text-broken-fg" : "text-fg-muted")}
        >
          {note.text}
        </p>
      )}
    </Toolbar.Root>
  );
}
