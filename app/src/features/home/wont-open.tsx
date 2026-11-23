import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogHeader } from "@/components/ui/dialog";
import { folderWords } from "@/features/duplicates/group-card";
import { type Unopened, useMarkDamaged, useReadAgain, useWontOpen } from "@/lib/engine";
import { showInFolder, useExplorer } from "@/lib/explorer";
import { count } from "@/lib/format";

/**
 * The pictures that won't open, in a card over Home, each as the small things board's card in
 * its place: why, with Show in folder, Try again (read again: one mended since opens) and Mark
 * as damaged (not asked about again unless its file changes). Mado leaves every one as it is.
 */
export function WontOpen({ onClose }: { onClose: () => void }) {
  const found = useWontOpen();
  const pictures = found.data?.pictures ?? [];
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[min(44rem,calc(100vw-2rem))]">
        <DialogHeader
          title="Won't open"
          description="Their files are damaged or were only half copied. Mado left each exactly as it is and carried on with the others."
        />
        <DialogBody>
          {found.isPending && (
            <p role="status" className="text-13 text-fg-muted">
              Finding them…
            </p>
          )}
          {found.isError && (
            <p role="alert" className="text-13 text-broken-fg">
              Mado couldn't list them: {found.error.message}
            </p>
          )}
          {found.data && pictures.length === 0 && (
            <p role="status" className="text-13 text-fg-muted">
              Every picture opens now, or you've marked it as damaged.
            </p>
          )}
          <ul className="flex flex-col gap-3">
            {pictures.map((picture) => (
              <Card key={picture.id} picture={picture} />
            ))}
          </ul>
          {found.data && found.data.damaged > 0 && (
            <p className="text-12 text-fg-faint">
              {count(found.data.damaged)} marked as damaged{" "}
              {found.data.damaged === 1 ? "isn't" : "aren't"} listed. Mado asks again if{" "}
              {found.data.damaged === 1 ? "its file changes" : "their files change"}.
            </p>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

/** One picture that won't open: its card, as the small things board draws it. */
function Card({ picture }: { picture: Unopened }) {
  const read = useReadAgain();
  const mark = useMarkDamaged();
  const explorer = useExplorer();
  const [still, setStill] = useState(false);
  return (
    <li className="flex flex-col gap-3 rounded-8 border border-edge bg-glass px-4.5 py-4">
      <span className="flex items-start gap-3">
        <span aria-hidden="true" className="status-problem mt-1 size-4 shrink-0 rounded-3" />
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="font-semibold text-15">
            <span className="font-medium font-mono [overflow-wrap:anywhere]">{picture.name}</span>{" "}
            won't open
          </span>
          <span className="text-13 text-fg-muted leading-normal">{picture.problem}</span>
          <span className="truncate text-12 text-fg-faint" title={picture.folder}>
            In {folderWords(picture.folder)}
          </span>
        </span>
      </span>
      <span className="flex flex-wrap gap-2">
        <Button
          size="sm"
          className="font-medium"
          onClick={() => explorer.run(() => showInFolder(picture.path))}
        >
          Show in folder
        </Button>
        <Button
          size="sm"
          className="font-medium"
          disabled={read.isPending}
          onClick={() =>
            read.mutate(
              { path: `/pictures/${picture.id}/read` },
              { onSuccess: (done) => setStill(done.state === "broken") },
            )
          }
        >
          Try again
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={mark.isPending}
          onClick={() => mark.mutate({ path: `/pictures/${picture.id}/damaged` })}
        >
          Mark as damaged
        </Button>
      </span>
      {still && !read.isPending && (
        <p role="status" className="text-12 text-fg-muted">
          It still won't open, so Mado left it as it is.
        </p>
      )}
      {(read.isError || mark.isError || explorer.problem) && (
        <p role="alert" className="text-12 text-broken-fg">
          {read.error?.message ?? mark.error?.message ?? explorer.problem}
        </p>
      )}
    </li>
  );
}
