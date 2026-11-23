import { useId } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import {
  readable,
  type SearchGroup,
  type SearchHit,
  type SearchResults,
  type SearchState,
  type Shown,
  shownQuery,
  type Tool,
  useDownloadTool,
  useSearchReading,
  type WordsPiece,
} from "@/lib/engine";
import { count, languages, pictures as picturesWord, size, stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Tile } from "./picture-grid";

/**
 * What a search found, as no board draws it: in the Library grid's own pattern, a heading with its
 * count over a grid of tiles, a group for each way a picture was found. The pictures whose words
 * match come first, their words under them with the matched ones bold; then those that look like
 * what was described, the closest first; then those with the words in their name. More like
 * this is one group, the most alike first. A picture found two ways is shown once.
 */
export function FoundGroups(props: {
  found: SearchResults;
  shown: Shown;
  ticked: ReadonlySet<number>;
  onTick: (id: number, run: boolean) => void;
}) {
  const query = shownQuery(props.shown);
  const opened = (picture: SearchHit) =>
    picture.outside
      ? `/pictures/${picture.id}`
      : `/library/pictures/${picture.id}${query ? `?${query}` : ""}`;
  return (
    <div className="flex flex-col gap-6">
      {props.found.groups.map((group) => (
        <FoundGroup
          key={group.kind}
          group={group}
          search={props.found.search}
          opened={opened}
          ticked={props.ticked}
          onTick={props.onTick}
        />
      ))}
    </div>
  );
}

function FoundGroup(props: {
  group: SearchGroup;
  search: string;
  opened: (picture: SearchHit) => string;
  ticked: ReadonlySet<number>;
  onTick: (id: number, run: boolean) => void;
}) {
  const id = useId();
  const { group } = props;
  const more = group.total - group.pictures.length;
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2.5">
      <h2 id={id} className="flex flex-wrap items-baseline gap-x-2.5 font-semibold text-15">
        {headingOf(group, props.search)}{" "}
        <span className="font-mono font-normal text-12 text-fg-faint">
          {picturesWord(group.total)}
          {group.kind === "described" && " · the closest first"}
          {group.kind === "like" && " · the most alike first"}
        </span>
      </h2>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-2.5">
        {group.pictures.map((picture) => (
          <Tile
            key={picture.id}
            picture={picture}
            to={props.opened(picture)}
            ticked={props.ticked.has(picture.id)}
            onTick={props.onTick}
            when={shortDay(picture.takenAt)}
            away={picture.away}
            words={picture.words ? <Words pieces={picture.words} /> : undefined}
          />
        ))}
      </div>
      {more > 0 && (
        <p className="text-13 text-fg-muted">
          And {picturesWord(more)} more: a few more words narrow it down.
        </p>
      )}
    </section>
  );
}

/** "With the words “zumi”", "Looks like “a red boat”", "“boat” in the name", "Most like Harbour at
 * dusk". */
function headingOf(group: SearchGroup, search: string): string {
  switch (group.kind) {
    case "words":
      return `With the words “${search}”`;
    case "described":
      return `Looks like “${search}”`;
    case "name":
      return `“${search}” in the name`;
    case "like":
      return `Most like ${stem(search)}`;
  }
}

/** A picture's words, those the search matched bold. */
function Words({ pieces }: { pieces: WordsPiece[] }) {
  return (
    <>
      {pieces.map((piece, at) =>
        piece.marked ? (
          // biome-ignore lint/suspicious/noArrayIndexKey: the pieces never move
          <strong key={at} className="font-semibold text-fg">
            {piece.text}
          </strong>
        ) : (
          // biome-ignore lint/suspicious/noArrayIndexKey: the pieces never move
          <span key={at}>{piece.text}</span>
        ),
      )}
    </>
  );
}

/** "14 Nov", or "14 Nov 2024" when it isn't this year. */
function shortDay(takenAt: string, now = new Date()): string {
  const moment = new Date(takenAt);
  if (Number.isNaN(moment.getTime())) return takenAt.slice(0, 10);
  const day = moment.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return moment.getFullYear() === now.getFullYear() ? day : `${day} ${moment.getFullYear()}`;
}

/**
 * What search is doing, above what it found, as the Library's own status lines say a scan's:
 * the models it needs on their way (names, and words where Windows reads them, work meanwhile),
 * the library still being read (with Pause), a search in another language, and words in a
 * writing the reader in use can't read.
 */
export function SearchNotes(props: { found: SearchResults; like?: boolean }) {
  const { found } = props;
  const { state } = found;
  const words = state.words;
  const windowsHasNone = words.reader === "fast" && words.languages.length === 0;
  return (
    <>
      <ModelsNote state={state} />
      <ReadingNote state={state} />
      {!props.like && !found.english && (
        <Note shape="status-waiting">
          Describing what's in a picture works in English, so this search looked at names and words
          only.
        </Note>
      )}
      {!props.like && found.unreadable && !windowsHasNone && (
        <Note shape="status-waiting">
          {words.reader === "fast" ? (
            <>
              Windows reads words only in {languages(words.languages)} here, so this search doesn't
              find {found.unreadable} ones. Best reads more: change it in <SettingsLink />.
            </>
          ) : (
            <>
              Mado's reader of words can't read {found.unreadable}, so this search looked for them
              in names only.
            </>
          )}
        </Note>
      )}
      {!props.like && windowsHasNone && (
        <Note shape="status-waiting">
          Windows has no language to read words in here, so the words in pictures aren't searched.
          Best reads them without one: change it in <SettingsLink />.
        </Note>
      )}
    </>
  );
}

/** Settings' General, where Search's reader of words is chosen. */
function SettingsLink() {
  return (
    <Link
      to="/settings/general"
      className="text-accent-fg underline underline-offset-3 hover:text-accent-fg-hover"
    >
      Settings › General
    </Link>
  );
}

/** The models search needs, on their way or not come: SigLIP, and PP-OCRv6 where words are read
 * at Best. Till they're here, a search finds by name (and words, where Windows reads them). */
function ModelsNote({ state }: { state: SearchState }) {
  const download = useDownloadTool();
  const wanted = [state.describer, state.words.reader === "best" ? state.words.model : null]
    .filter((tool): tool is Tool => tool !== null)
    .filter((tool) => tool.state !== "ready");
  if (wanted.length === 0) return null;
  const failed = wanted.find((tool) => tool.state === "failed");
  const total = wanted.reduce((sum, tool) => sum + tool.size, 0);
  const done = wanted.reduce((sum, tool) => sum + tool.done, 0);
  // SigLIP first: without it, a search finds by name alone (and words, where Windows reads them).
  const pictures = state.describer !== null && state.describer.state !== "ready";
  const reader = pictures ? "Mado's reader of pictures" : "Mado's reader of words";
  const meanwhile = !pictures
    ? "Till it's here, a search finds pictures by what they show and by their names."
    : state.words.reader === "fast" && state.words.languages.length > 0
      ? "Till it's here, a search finds pictures by their names and the words in them."
      : "Till it's here, a search finds pictures by their names.";
  if (failed) {
    return (
      <Note shape="status-problem" alert>
        <span>
          Mado couldn't get what search needs: {failed.problem ?? "the download didn't finish"}{" "}
          {meanwhile}
        </span>
        <Button
          size="sm"
          className="ml-auto font-medium"
          disabled={download.isPending}
          onClick={() => {
            for (const tool of wanted) download.mutate({ path: `/tools/${tool.id}/download` });
          }}
        >
          Try again
        </Button>
      </Note>
    );
  }
  const coming = wanted.some((tool) => tool.state === "downloading" || tool.state === "unpacking");
  return (
    <Note shape={coming ? "status-working" : "status-waiting"}>
      <span>
        {coming ? (
          <>
            Getting {reader} for search: <span className="font-mono text-fg">{size(done)}</span> of{" "}
            <span className="font-mono text-fg">{size(total)}</span>. {meanwhile}
          </>
        ) : (
          <>
            {pictures
              ? "Searching by what's in a picture needs Mado's reader of pictures"
              : "Searching by the words in pictures needs Mado's reader of words"}{" "}
            (<span className="font-mono">{size(total)}</span>). {meanwhile}
          </>
        )}
      </span>
      {!coming && (
        <Button
          size="sm"
          className="ml-auto font-medium"
          disabled={download.isPending}
          onClick={() => {
            for (const tool of wanted) download.mutate({ path: `/tools/${tool.id}/download` });
          }}
        >
          Get it
        </Button>
      )}
    </Note>
  );
}

/** The library still being read: how far, that search covers those, and Pause; the queue on the
 * card slowing it; pictures that couldn't be read; a reader that couldn't run, with Try again. */
export function ReadingNote({ state, always = false }: { state: SearchState; always?: boolean }) {
  const reading = useSearchReading();
  const ready = readable(state);
  if (state.problem) {
    const meanwhile =
      state.problem.reader === "words"
        ? "Search still finds pictures by what they show and by their names."
        : "Search still finds pictures by their names and the words in them.";
    return (
      <Note shape="status-problem" alert>
        <span>
          Mado's reader of {state.problem.reader} couldn't run: {state.problem.said} {meanwhile}
        </span>
        <Button
          size="sm"
          className="ml-auto font-medium"
          disabled={reading.isPending}
          onClick={() => reading.mutate({ path: "/search/resume" })}
        >
          Try again
        </Button>
      </Note>
    );
  }
  if (!ready || state.of === 0) return null;
  const done = state.read + state.failed >= state.of;
  if (done && !always && state.failed === 0) return null;
  const failed =
    state.failed > 0 ? (
      <>
        {" "}
        <span className="font-mono text-fg">{count(state.failed)}</span>{" "}
        {state.failed === 1 ? "picture" : "pictures"} couldn't be read for search. Mado tries
        {state.failed === 1 ? " it" : " them"} again the next time it looks through your library.
      </>
    ) : null;
  return (
    <Note shape={state.paused || done ? "status-waiting" : "status-working"}>
      <span>
        {done && state.failed > 0 ? (
          <>
            Read <span className="font-mono text-fg">{count(state.read)}</span> of{" "}
            <span className="font-mono text-fg">{count(state.of)}</span>: search covers those.
            {failed}
          </>
        ) : done ? (
          <>
            Read all <span className="font-mono text-fg">{count(state.of)}</span>: search covers
            your whole library.
          </>
        ) : (
          <>
            {state.paused ? "Reading paused at " : "Read "}
            <span className="font-mono text-fg">{count(state.read)}</span> of{" "}
            <span className="font-mono text-fg">{count(state.of)}</span>
            {state.paused ? "" : " so far"}: search covers those.
            {!state.paused && state.busy && " It takes turns with the queue on the graphics card."}
            {failed}
          </>
        )}
      </span>
      {!done && (
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto font-medium"
          disabled={reading.isPending}
          onClick={() =>
            reading.mutate({ path: state.paused ? "/search/resume" : "/search/pause" })
          }
        >
          {state.paused ? "Go on" : "Pause"}
        </Button>
      )}
    </Note>
  );
}

function Note(props: { shape: string; alert?: boolean; children: React.ReactNode }) {
  return (
    <div
      role={props.alert ? "alert" : "status"}
      className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-13 text-fg-muted"
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-2.5 shrink-0",
          props.shape === "status-problem" ? "rounded-2" : "rounded-full",
          props.shape,
        )}
      />
      {props.children}
    </div>
  );
}

/** A search that found nothing: what it searched, and what to do. */
export function NothingFound(props: {
  found: SearchResults;
  where: string;
  like?: boolean;
  onClear: () => void;
}) {
  const { found } = props;
  const partly = found.state.read < found.state.of;
  const described = found.state.describer?.state === "ready" && found.english;
  return (
    <section className="flex flex-col items-start gap-3 rounded-8 border border-edge bg-glass px-5 py-4.5">
      <h2 className="font-semibold text-16">
        {props.like
          ? `Nothing in your library looks like ${stem(found.search)}`
          : `Nothing in ${props.where} matches “${found.search}”`}
      </h2>
      <p className="max-w-150 text-13 text-fg-muted leading-normal">
        {props.like
          ? "Mado compares what it read of every picture: none came close enough to show."
          : described
            ? "Mado looked at what each picture shows, the words in it and its name, and nothing came close enough to show. Try fewer words, or other ones."
            : "Mado looked at the pictures' names and words."}
        {partly && " It hasn't read the whole library yet: search covers the pictures read so far."}
      </p>
      <Button size="sm" onClick={props.onClear}>
        {props.like ? "Show all your pictures" : "Clear the search"}
      </Button>
    </section>
  );
}
