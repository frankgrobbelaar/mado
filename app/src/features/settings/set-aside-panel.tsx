import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { type DriveAside, useEmptyQuarantine, useQuarantine } from "@/lib/engine";
import { size } from "@/lib/format";
import { Panel } from "./panel";

/**
 * Set aside, in Settings › Your data: what waits in quarantine on each drive (replaced originals
 * and pictures taken away, each kept 30 days, then cleared out), and emptying a drive's now,
 * after asking once more: it can't be put back.
 */
export function SetAsidePanel() {
  const found = useQuarantine();
  const [emptying, setEmptying] = useState<DriveAside | null>(null);
  const drives = found.data ?? [];
  return (
    <Panel
      title="Set aside"
      note="Replaced originals and pictures taken away, each kept 30 days, then cleared out."
    >
      {drives.length === 0 && found.data && (
        <p className="text-13 text-fg-muted">Nothing is set aside.</p>
      )}
      <ul className="flex flex-col">
        {drives.map((drive) => (
          <li
            key={drive.drive}
            className="flex flex-wrap items-center gap-3 border-rule border-t py-2.5 first:border-t-0"
          >
            <span className="flex-[1_1_260px] text-14">
              <span className="font-mono">{drive.folder}</span> ·{" "}
              <span className="font-mono">{size(drive.bytes)}</span>
            </span>
            <Button size="sm" variant="danger" onClick={() => setEmptying(drive)}>
              Empty now…
            </Button>
          </li>
        ))}
      </ul>
      {found.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {found.error.message}
        </p>
      )}
      {emptying && <EmptyNow drive={emptying} onClose={() => setEmptying(null)} />}
    </Panel>
  );
}

function EmptyNow({ drive, onClose }: { drive: DriveAside; onClose: () => void }) {
  const empty = useEmptyQuarantine();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[min(30rem,calc(100vw-2rem))]">
        <DialogHeader
          title={`Empty ${drive.drive}'s quarantine?`}
          description={`This deletes ${size(drive.bytes)} for good, before its 30 days are up. What's in it can't be put back afterwards.`}
        />
        <DialogBody>
          <p className="text-13 text-fg-muted">
            History keeps a line saying you emptied it. Your other pictures don't change.
          </p>
          {empty.isError && (
            <p role="alert" className="text-13 text-broken-fg">
              {empty.error.message}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <span />
          <span className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Keep it
            </Button>
            <Button
              variant="danger"
              disabled={empty.isPending}
              onClick={() =>
                empty.mutate(
                  { path: "/quarantine/empty", body: { drive: drive.drive } },
                  { onSuccess: onClose },
                )
              }
            >
              Empty it for good
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
