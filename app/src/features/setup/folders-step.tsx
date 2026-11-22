import { Folder, Plus, X } from "lucide-react";
import { useNavigate } from "react-router";
import { MadeUpPicture } from "@/components/made-up-picture";
import { Button } from "@/components/ui/button";
import { useAddFolderPicker } from "@/features/library/add-folder";
import {
  type LibraryFolder,
  type Scan,
  useEngineQuery,
  useFolders,
  useRemoveFolder,
  useSaveSettings,
  useSettings,
} from "@/lib/engine";
import { about, count } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Setup's second step, as Setup-Folders draws it: the folders pictures live in, each with what
 * Mado has found there so far, and starting to use Mado, with folders or without.
 */
export function FoldersStep({ onBack }: { onBack: () => void }) {
  const folders = useFolders();
  const scan = useEngineQuery<Scan>("/scan");
  const adding = useAddFolderPicker();
  const remove = useRemoveFolder();
  const stored = useSettings();
  const save = useSaveSettings();
  const navigate = useNavigate();
  const added = folders.data ?? [];

  function start() {
    if (!stored.data) return;
    save.mutate(
      { path: "/settings", body: { ...stored.data, setUp: true } },
      { onSuccess: () => void navigate("/", { replace: true }) },
    );
  }

  return (
    <>
      <section
        aria-label="Folders added"
        className="flex animate-fade-up flex-col rounded-8 border border-edge bg-glass"
      >
        {added.map((folder) => (
          <FolderRow
            key={folder.id}
            folder={folder}
            onRemove={() => remove.mutate({ path: `/folders/${folder.id}` })}
          />
        ))}
        <div
          className={cn(
            "flex flex-wrap items-center gap-x-4 gap-y-2.5 px-4.5 py-3",
            added.length > 0 && "border-rule border-t",
          )}
        >
          <Button
            variant={added.length === 0 ? "primary" : "secondary"}
            className="font-medium"
            disabled={adding.busy}
            onClick={adding.pick}
          >
            <Plus size={16} aria-hidden="true" />
            Add a folder
          </Button>
          <span className="text-13 text-fg-faint">
            Folders on a drive that isn't connected wait for it.
          </span>
        </div>
      </section>
      {(adding.problem ?? remove.error?.message) && (
        <p role="alert" className="text-13 text-broken-fg">
          {adding.problem ?? remove.error?.message}
        </p>
      )}

      <section
        aria-labelledby="ready"
        className="flex animate-fade-up flex-wrap items-center gap-x-6 gap-y-4 rounded-8 border border-edge bg-glass px-5 py-4.5"
      >
        <div aria-hidden="true" className="flex shrink-0 gap-1.5">
          <MadeUpPicture kind="meadow" className="h-12 w-16" />
          <MadeUpPicture kind="lake" className="h-12 w-16" />
          <MadeUpPicture kind="bloom" className="h-12 w-16" />
        </div>
        <div className="flex flex-[1_1_380px] flex-col gap-1">
          <h2 id="ready" className="font-semibold text-18">
            That's it: Mado is ready
          </h2>
          <p className="text-14 text-fg-muted leading-normal">
            <Reading folders={added} scan={scan.data} />
          </p>
        </div>
        <Button variant="primary" disabled={!stored.data || save.isPending} onClick={start}>
          Start using Mado
        </Button>
        {save.isError && (
          <p role="alert" className="basis-full text-13 text-broken-fg">
            Setup couldn't finish: {save.error.message}
          </p>
        )}
      </section>

      <footer className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" className="font-medium" onClick={onBack}>
          Back
        </Button>
        <p className="flex-[1_1_360px] text-13 text-fg-faint">
          No folders yet? Skip this: start using Mado now, and add folders later from Home or the
          Library.
        </p>
      </footer>
    </>
  );
}

/** One folder added, with what Mado found there so far. */
function FolderRow({ folder, onRemove }: { folder: LibraryFolder; onRemove: () => void }) {
  const found = folder.pictures + folder.reading;
  const looking = folder.available && !folder.looked;
  return (
    <div className="flex items-center gap-3.5 border-rule border-b px-4.5 py-3 last:border-b-0">
      <Folder size={20} strokeWidth={1.6} aria-hidden="true" className="shrink-0 text-fg-muted" />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate font-mono text-13">{folder.path}</span>
        <span className="text-12 text-fg-muted">
          {!folder.available && "Its drive isn't connected: Mado reads it once it is."}
          {looking && (
            <>
              Looking… <span className="font-mono text-fg">{count(found)}</span> so far
            </>
          )}
          {folder.available && folder.looked && (
            <>
              Found <span className="font-mono text-fg">{count(found)}</span>{" "}
              {found === 1 ? "picture" : "pictures"}
              {folder.raw > 0 && (
                <>
                  , <span className="font-mono text-fg">{count(folder.raw)}</span> of them camera
                  RAW
                </>
              )}
            </>
          )}
        </span>
      </span>
      <span
        aria-hidden="true"
        className={cn(
          "size-3 shrink-0 rounded-full",
          !folder.available && "status-waiting",
          folder.available &&
            (looking || folder.reading > 0) &&
            "border-2 border-line border-t-accent",
          folder.available && folder.looked && folder.reading === 0 && "status-done",
        )}
      />
      <Button
        variant="ghost"
        size="sm"
        aria-label={`Take ${folder.path} out`}
        className="w-9 px-0"
        onClick={onRemove}
      >
        <X size={18} strokeWidth={1.6} aria-hidden="true" />
      </Button>
    </div>
  );
}

/** What Mado does next with the folders: read them in the background, and keep watching. */
function Reading({ folders, scan }: { folders: LibraryFolder[]; scan: Scan | undefined }) {
  if (folders.length === 0) {
    return (
      <>Add the folders your pictures live in whenever you like. Nothing on this PC changes.</>
    );
  }
  const total = folders.reduce((sum, folder) => sum + folder.pictures + folder.reading, 0);
  if (scan?.state === "running" && scan.secondsLeft !== null) {
    return (
      <>
        It reads the rest in the background, about{" "}
        <span className="font-mono text-fg">{about(scan.secondsLeft).replace(/^about /, "")}</span>{" "}
        for <span className="font-mono text-fg">{count(total)}</span>{" "}
        {total === 1 ? "picture" : "pictures"}, and keeps watching these folders for new ones.
      </>
    );
  }
  if (scan?.state === "running") {
    return <>It reads them in the background, and keeps watching these folders for new ones.</>;
  }
  return (
    <>
      It has read <span className="font-mono text-fg">{count(total)}</span>{" "}
      {total === 1 ? "picture" : "pictures"}, and keeps watching these folders for new ones.
    </>
  );
}
