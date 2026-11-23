import { FolderOpen, MoreVertical, Search } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import type { BatchStart } from "@/features/batch/open";
import {
  type LibraryFolder,
  type PictureItem,
  type Scan,
  type SearchResults,
  type Shown,
  shownFrom,
  shownQuery,
  useEngineQuery,
  useFolders,
  useLibrary,
  useLike,
  usePictures,
  useRemoveFolder,
  useSearch,
} from "@/lib/engine";
import { openFolder, useExplorer } from "@/lib/explorer";
import { about, count, pictures as picturesWord, stem } from "@/lib/format";
import { useAddFolderPicker } from "./add-folder";
import { EmptyLibrary } from "./empty-library";
import { FolderTree } from "./folder-tree";
import { daysOf, PictureGrid } from "./picture-grid";
import { FoundGroups, NothingFound, SearchNotes } from "./search-results";
import { TickedBar } from "./ticked-bar";

const NONE: ReadonlySet<number> = new Set();

/**
 * The Library: the folders down its side as a tree, and the pictures of the one chosen (or all of
 * them) by the day they were taken, newest first, ticked to do things with many at once; or what
 * a search found, by the words in the pictures, what they show and their names, or the pictures
 * most like one (More like this). What it shows lives in its address, so a picture opened from
 * it, and Back, keep the place.
 */
export function LibraryPage() {
  const [query, setQuery] = useSearchParams();
  const shown = useMemo(() => shownFrom(query), [query]);
  const folders = useFolders();
  const favourites = useLibrary().data?.favourites ?? 0;
  const adding = useAddFolderPicker();

  // A folder no longer in the library (taken out, then Back): all the pictures instead.
  const missing =
    shown.folder !== null && folders.data && !folders.data.some((f) => f.id === shown.folder);
  if (missing) {
    const rest = shownQuery({ ...shown, folder: null, dir: "" });
    return <Navigate to={rest ? `/library?${rest}` : "/library"} replace />;
  }

  return (
    <div className="-mx-7 -mb-12 flex flex-1">
      <aside className="sticky top-0 flex h-[calc(100vh-4.25rem)] w-58 shrink-0 flex-col overflow-y-auto border-chrome-edge border-r bg-surface px-3 pt-4.5 pb-4">
        {folders.data && folders.data.length > 0 ? (
          <FolderTree
            folders={folders.data}
            favourites={favourites}
            shown={shown}
            onAdd={adding.pick}
            adding={adding.busy}
            problem={adding.problem}
          />
        ) : (
          <nav aria-label="Folders" className="flex flex-col gap-2">
            <h2 className="type-eyebrow mx-2">Folders</h2>
            <p className="mx-2 text-13 text-fg-faint leading-normal">
              {folders.data ? "No folders yet. The ones you add show here as a tree." : "…"}
            </p>
          </nav>
        )}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col gap-3.5 px-6 pb-12">
        {folders.data?.length === 0 ? (
          <>
            <header className="page-top pt-4.5">
              <h1 className="type-title">Library</h1>
            </header>
            <EmptyLibrary
              className="min-h-90 flex-1"
              onAdd={adding.pick}
              adding={adding.busy}
              problem={adding.problem}
            />
          </>
        ) : (
          <Pictures
            key={`${shown.favourites}:${shown.folder}:${shown.dir}`}
            shown={shown}
            folders={folders.data}
            foldersQuery={folders}
            onShow={(next) => setQuery(shownQuery(next), { replace: true })}
          />
        )}
      </div>
    </div>
  );
}

function Pictures(props: {
  shown: Shown;
  folders: LibraryFolder[] | undefined;
  foldersQuery: ReturnType<typeof useFolders>;
  onShow: (shown: Shown) => void;
}) {
  const { shown, folders } = props;
  const liking = shown.like !== null;
  const searching = liking || shown.q.trim() !== "";
  const list = usePictures(shown, !searching);
  const search = useSearch(shown, !liking);
  const like = useLike(shown.like);
  const finding = liking ? like : search;
  const found = searching ? finding.data : undefined;
  const scan = useEngineQuery<Scan>("/scan");
  const chosen = shown.folder === null ? null : folders?.find((each) => each.id === shown.folder);
  const pages = list.data?.pages;
  const days = useMemo(() => daysOf(pages ?? []), [pages]);
  const loaded: PictureItem[] = useMemo(
    () =>
      searching
        ? (found?.groups.flatMap((group) => group.pictures) ?? [])
        : days.flatMap((day) => day.pictures),
    [searching, found, days],
  );
  // Ticks belong to the list they were made in: another search or order starts with none.
  const listKey = shownQuery(shown);
  const [ticks, setTicks] = useState<{ list: string; ids: ReadonlySet<number> }>({
    list: listKey,
    ids: new Set(),
  });
  const ticked = ticks.list === listKey ? ticks.ids : NONE;
  const last = useRef<number | null>(null); // the picture ticked last, where a Shift run starts
  const { onShow } = props;
  const navigate = useNavigate();
  const [words, setWords] = useState(shown.q);
  const searched = useRef(shown.q); // the search this page last put in the address

  // The search narrows the grid as it's typed, a moment after the last key.
  useEffect(() => {
    if (words.trim() === shown.q.trim()) return;
    const timer = setTimeout(() => {
      searched.current = words.trim();
      onShow({ ...shown, q: words, like: null });
    }, 250);
    return () => clearTimeout(timer);
  }, [words, shown, onShow]);

  // A search changed from outside (a folder in the tree opened afresh, Back) shows in the box.
  useEffect(() => {
    if (shown.q === searched.current) return;
    searched.current = shown.q;
    setWords(shown.q);
  }, [shown.q]);

  function tick(id: number, run: boolean) {
    const anchor = last.current; // read once: React may run the change below twice
    last.current = id;
    setTicks((now) => {
      const before = now.list === listKey ? now.ids : NONE;
      const next = new Set(before);
      const order = loaded.map((picture) => picture.id);
      const from = anchor === null ? -1 : order.indexOf(anchor);
      const to = order.indexOf(id);
      if (run && from >= 0 && to >= 0) {
        const on = !before.has(id);
        for (const each of order.slice(Math.min(from, to), Math.max(from, to) + 1)) {
          if (on) next.add(each);
          else next.delete(each);
        }
      } else if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return { list: listKey, ids: next };
    });
  }

  const { fetchNextPage } = list;
  const more = useCallback(() => void fetchNextPage(), [fetchNextPage]);
  const total = searching ? found?.total : pages?.[0]?.total;
  const clear = () => {
    setWords("");
    onShow({ ...shown, q: "", like: null });
  };
  const tickedPictures = loaded.filter((picture) => ticked.has(picture.id));
  const place = chosen ? placeOf(chosen, shown.dir) : null;

  return (
    <>
      <div className="page-top flex flex-col gap-3.5 pt-4.5">
        <Header
          shown={shown}
          chosen={chosen ?? null}
          place={place}
          total={total}
          found={found}
          words={words}
          onWords={setWords}
          onShow={onShow}
        />
        {tickedPictures.length > 0 && (
          <TickedBar
            ticked={tickedPictures}
            onClear={() => setTicks({ list: listKey, ids: NONE })}
            onBatch={() => {
              const start: BatchStart = {
                pick: { how: "ticked", ids: tickedPictures.map((picture) => picture.id) },
              };
              void navigate("/batch", { state: start });
            }}
          />
        )}
      </div>
      <Situation scan={scan.data} chosen={chosen ?? null} />
      {searching ? (
        <>
          <EngineProblem queries={[props.foldersQuery, finding]} />
          {!found && (
            <Loading label="Searching your pictures" queries={[finding]}>
              <GridSkeleton />
            </Loading>
          )}
          {found && <SearchNotes found={found} like={liking} />}
          {found && found.total === 0 && (
            <NothingFound
              found={found}
              where={shown.favourites ? "your favourites" : (place?.name ?? "your library")}
              like={liking}
              onClear={clear}
            />
          )}
          {found && found.total > 0 && (
            <FoundGroups found={found} shown={shown} ticked={ticked} onTick={tick} />
          )}
        </>
      ) : (
        <>
          <EngineProblem queries={[props.foldersQuery, list]} />
          {!pages && (
            <Loading label="Loading your pictures" queries={[list]}>
              <GridSkeleton />
            </Loading>
          )}
          {pages && days.length === 0 && (
            <Nothing shown={shown} name={place?.name ?? null} scan={scan.data} />
          )}
          {pages && days.length > 0 && (
            <PictureGrid
              days={days}
              shown={shown}
              ticked={ticked}
              onTick={tick}
              more={list.hasNextPage}
              loadingMore={list.isFetchingNextPage}
              moreFailed={list.isFetchNextPageError}
              onMore={more}
            />
          )}
        </>
      )}
    </>
  );
}

/** The folder showing: a library folder, or a folder inside it. */
function placeOf(folder: LibraryFolder, dir: string): { name: string; path: string } {
  if (!dir) return { name: folder.name, path: folder.path };
  return {
    name: dir.split("/").at(-1) ?? dir,
    path: `${folder.path}\\${dir.replaceAll("/", "\\")}`,
  };
}

function Header(props: {
  shown: Shown;
  chosen: LibraryFolder | null;
  place: { name: string; path: string } | null;
  total: number | undefined;
  found: SearchResults | undefined;
  words: string;
  onWords: (words: string) => void;
  onShow: (shown: Shown) => void;
}) {
  const { shown, place, onShow } = props;
  const navigate = useNavigate();
  const loved = shown.favourites;
  const liking = shown.like !== null;
  const title = loved ? "Favourites" : (place?.name ?? "Library");
  const newest = shown.order === "newest";
  const searching = loved ? "your favourites" : place ? place.name : "your library";
  const searched = shown.q.trim() !== "" || liking;
  return (
    <header className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5">
      <h1 className="type-title">{title}</h1>
      {/* A long path stays on one line, whole on hovering. */}
      <p className="min-w-0 max-w-full truncate text-14 text-fg-muted" title={place?.path}>
        {props.total === undefined ? (
          "…"
        ) : liking ? (
          <>
            <span className="font-mono text-fg">{count(props.total)}</span>{" "}
            {props.total === 1 ? "picture" : "pictures"} most like{" "}
            {props.found ? stem(props.found.search) : "it"}
          </>
        ) : shown.q.trim() ? (
          <>
            <span className="font-mono text-fg">{count(props.total)}</span>{" "}
            {props.total === 1 ? "picture" : "pictures"} found for “{shown.q.trim()}”
          </>
        ) : loved ? (
          <>
            <span className="font-mono text-fg">{count(props.total)}</span>{" "}
            {props.total === 1 ? "picture" : "pictures"} you gave a heart, by the day they were
            taken
          </>
        ) : (
          <>
            <span className="font-mono text-fg">{count(props.total)}</span>{" "}
            {props.total === 1 ? "picture" : "pictures"} by the day they were taken
          </>
        )}
        {place && (
          <>
            {" · "}
            <span className="font-mono">{place.path}</span>
          </>
        )}
      </p>
      {props.chosen && (
        <FolderMenu folder={props.chosen} dir={shown.dir} path={place?.path ?? props.chosen.path} />
      )}
      {(searched || loved) && (props.total ?? 0) > 0 && (
        <Button
          size="sm"
          className="font-medium"
          onClick={() => {
            const start: BatchStart = {
              pick: liking
                ? { how: "search", like: shown.like }
                : loved
                  ? { how: "favourites", q: shown.q.trim() }
                  : { how: "search", folder: shown.folder, dir: shown.dir, q: shown.q.trim() },
            };
            void navigate("/batch", { state: start });
          }}
        >
          Many at once…
        </Button>
      )}
      <div className="ml-auto flex flex-wrap gap-2">
        <label className="flex h-9 items-center gap-2 rounded-6 border border-field-edge bg-field px-2.5 text-13 text-fg-faint focus-within:border-accent">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">{`Search ${searching}`}</span>
          <input
            type="search"
            value={props.words}
            onChange={(event) => props.onWords(event.target.value)}
            placeholder={`Search ${searching}`}
            className="w-37.5 border-0 bg-transparent text-13 text-fg outline-none placeholder:text-fg-faint"
          />
        </label>
        {!searched && (
          <Button
            size="sm"
            className="font-medium"
            title={newest ? "Show the oldest first" : "Show the newest first"}
            onClick={() => onShow({ ...shown, order: newest ? "oldest" : "newest" })}
          >
            Date taken, {newest ? "newest" : "oldest"} first
          </Button>
        )}
      </div>
    </header>
  );
}

/** A folder's own menu: make all its pictures many at once, show it in Explorer, or (a library
 * folder) take it out of the library. */
function FolderMenu({ folder, dir, path }: { folder: LibraryFolder; dir: string; path: string }) {
  const [asking, setAsking] = useState(false);
  const explorer = useExplorer();
  const remove = useRemoveFolder();
  const navigate = useNavigate();
  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger
          aria-label={`More for ${dir ? (dir.split("/").at(-1) ?? dir) : folder.name}`}
          className="press inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full text-fg-muted hover:bg-tint/8 hover:text-fg"
        >
          <MoreVertical size={16} aria-hidden="true" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="start"
            sideOffset={4}
            className="z-60 flex min-w-52 flex-col rounded-8 border border-edge bg-dialog p-1.5 text-13 shadow-float"
          >
            <DropdownMenu.Item
              disabled={!folder.available}
              onSelect={() => {
                const start: BatchStart = { pick: { how: "folder", folder: folder.id, dir } };
                void navigate("/batch", { state: start });
              }}
              className="cursor-pointer rounded-6 px-3 py-2 font-semibold text-fg-soft outline-none data-disabled:opacity-50 data-highlighted:bg-tint/6 data-highlighted:text-fg"
            >
              Many at once…
            </DropdownMenu.Item>
            <DropdownMenu.Item
              disabled={!folder.available}
              onSelect={() => explorer.run(() => openFolder(path))}
              className="flex cursor-pointer items-center gap-2 rounded-6 px-3 py-2 font-semibold text-fg-soft outline-none data-disabled:opacity-50 data-highlighted:bg-tint/6 data-highlighted:text-fg"
            >
              <FolderOpen size={15} aria-hidden="true" />
              Show in folder
            </DropdownMenu.Item>
            {!dir && (
              <>
                <DropdownMenu.Separator className="mx-2 my-1 h-px bg-rule" />
                <DropdownMenu.Item
                  onSelect={() => setAsking(true)}
                  className="cursor-pointer rounded-6 px-3 py-2 font-semibold text-danger outline-none data-highlighted:bg-tint/6"
                >
                  Take out of your library…
                </DropdownMenu.Item>
              </>
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {explorer.problem && (
        <p role="alert" className="basis-full text-12 text-broken-fg">
          {explorer.problem}
        </p>
      )}
      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent className="w-[min(30rem,calc(100vw-2rem))]">
          <DialogHeader
            title={`Take ${folder.name} out of your library?`}
            description={folder.path}
          />
          <DialogBody>
            <p className="text-14 text-fg-muted">
              Mado forgets what it read of its {picturesWord(folder.pictures)} and stops watching
              it. The pictures stay exactly where they are, and you can add the folder again any
              time.
            </p>
            {remove.isError && (
              <p role="alert" className="text-13 text-broken-fg">
                {remove.error.message}
              </p>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setAsking(false)}>
              Keep it
            </Button>
            <Button
              variant="danger"
              size="sm"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(
                  { path: `/folders/${folder.id}` },
                  {
                    onSuccess: () => {
                      setAsking(false);
                      void navigate("/library", { replace: true });
                    },
                  },
                )
              }
            >
              Take it out
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** What's going on with the library now: a scan reading, or the folder's drive away. */
function Situation({ scan, chosen }: { scan: Scan | undefined; chosen: LibraryFolder | null }) {
  if (chosen && !chosen.available) {
    return (
      <p role="status" className="flex items-center gap-2 text-13 text-fg-muted">
        <span aria-hidden="true" className="status-waiting size-2.5 shrink-0 rounded-full" />
        <span>
          <span className="font-mono">{chosen.path}</span> isn't connected. Its pictures show as
          Mado last saw them, and it looks again once the drive is back.
        </span>
      </p>
    );
  }
  if (scan?.state !== "running") return null;
  const left = scan.secondsLeft !== null ? ` · ${about(scan.secondsLeft)} left` : "";
  return (
    <p role="status" className="flex items-center gap-2 text-13 text-fg-muted">
      <span aria-hidden="true" className="status-working size-2 shrink-0 rounded-full" />
      {scan.stage === "reading" ? (
        <span>
          Reading new pictures: <span className="font-mono text-fg">{count(scan.read)}</span> of{" "}
          <span className="font-mono text-fg">{count(scan.toRead)}</span>
          {left}
        </span>
      ) : (
        <span>
          Looking through your folders:{" "}
          <span className="font-mono text-fg">{count(scan.found)}</span> found so far
        </span>
      )}
    </p>
  );
}

/** An empty grid, saying why: no favourites yet, or the folder has no pictures yet (a search
 * says what it found in its own place). */
function Nothing(props: { shown: Shown; name: string | null; scan: Scan | undefined }) {
  const where = props.shown.favourites ? "your favourites" : (props.name ?? "your library");
  if (props.shown.favourites) {
    return (
      <section className="flex flex-col items-start gap-2 rounded-8 border border-dash border-dashed bg-surface px-5 py-6">
        <h2 className="font-semibold text-16">No favourites yet</h2>
        <p className="text-13 text-fg-muted leading-normal">
          Give a picture a heart on its page, or on its tile here in the Library, and it's kept
          here, wherever its file goes. The wallpaper can change to one of them every day.
        </p>
        <Button asChild size="sm" className="mt-1">
          <Link to="/library">Show all your pictures</Link>
        </Button>
      </section>
    );
  }
  const reading = props.scan?.state === "running";
  return (
    <section className="flex flex-col gap-2 rounded-8 border border-dash border-dashed bg-surface px-5 py-6">
      <h2 className="font-semibold text-16">
        {reading ? `Mado is reading ${where}` : `No pictures in ${where} yet`}
      </h2>
      <p className="text-13 text-fg-muted">
        {reading
          ? "They show here, by the day they were taken, as Mado reads them."
          : "Pictures put here show by themselves: Mado watches the folder. It reads JPEG, HEIC, PNG, WebP, AVIF, TIFF, BMP, GIF and camera RAW."}
      </p>
    </section>
  );
}

function GridSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      {["first", "second"].map((day) => (
        <div key={day} className="flex flex-col gap-2.5">
          <Skeleton className="h-4 w-48" />
          <div className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-2.5">
            {["a", "b", "c", "d", "e", "f"].map((tile) => (
              <div key={tile} className="flex flex-col gap-1.25">
                <Skeleton className="h-26 rounded-4" />
                <Skeleton className="h-3 w-24" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
