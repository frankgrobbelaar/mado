import { ClipboardPaste, FolderOpen } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { type PictureDetails, useAddFolder } from "@/lib/engine";
import { showInFolder, useExplorer } from "@/lib/explorer";
import { split } from "@/lib/format";

/**
 * Where a picture from outside the library lives, in place of the library's breadcrumb: its
 * folder, which shows it there in File Explorer, and the quiet "Add its folder to the library".
 * A pasted picture lives in Mado till it's saved; one in a quarantine shows that folder.
 */
export function WhereItLives({ picture }: { picture: PictureDetails }) {
  const explorer = useExplorer();
  const add = useAddFolder();
  if (picture.pasted) {
    return (
      <span className="inline-flex h-8 items-center gap-1.5 rounded-full border border-edge px-3 text-13 text-fg-muted">
        <ClipboardPaste size={15} aria-hidden="true" />
        Pasted · not saved yet
      </span>
    );
  }
  const name = picture.aside ? "Mado quarantine" : split(picture.folder)[0] || picture.folder;
  const problem = explorer.problem ?? (add.isError ? add.error.message : null);
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
      <Button
        size="sm"
        className="gap-1.5 pr-2.5 pl-2 font-normal"
        title={`Show it in ${picture.folder}`}
        aria-label={`Show ${picture.name} in its folder, ${name}`}
        onClick={() => explorer.run(() => showInFolder(picture.path))}
      >
        <FolderOpen size={15} aria-hidden="true" />
        {name}
      </Button>
      {!picture.aside && (
        <Button
          size="sm"
          variant="ghost"
          className="font-medium text-fg-muted"
          disabled={add.isPending || add.isSuccess}
          onClick={() => add.mutate({ path: "/folders", body: { path: picture.folder } })}
        >
          {add.isSuccess ? `Mado is reading ${name}…` : "Add its folder to the library"}
        </Button>
      )}
      {problem && (
        <span role="alert" className="basis-full text-12 text-broken-fg">
          {problem}
        </span>
      )}
    </span>
  );
}

/** In the tools' place, for a picture waiting in a quarantine: it's opened to look at only. */
export function LookOnly() {
  return (
    <aside
      aria-label="Tools"
      className="sticky top-0 flex h-[calc(100vh-4.25rem)] w-100 shrink-0 flex-col gap-3 border-chrome-edge border-l bg-surface px-4.5 pt-5 pb-4"
    >
      <h2 className="font-semibold text-15">Opened to look at only</h2>
      <p className="text-13 text-fg-muted leading-normal">
        It waits in Mado's quarantine, set aside as it was. Put it back from History to make it
        right for a screen, give it a look or edit it.
      </p>
      <Button asChild size="sm" className="self-start font-medium">
        <Link to="/history">Open History</Link>
      </Button>
    </aside>
  );
}
