import { Folder, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { EmptyState, WindowIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, PanelSkeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Segmented } from "@/components/ui/segmented";
import {
  type BatchLine,
  type HistoryEntry,
  pictureAddress,
  type ReviewLine,
  useBatchUndo,
  useClearHistory,
  useHistory,
  useHistoryAction,
  usePictureImage,
  useReviewUndo,
} from "@/lib/engine";
import { count, MOTION_WORDS, madeWith, size, split, stem, versionOf } from "@/lib/format";
import { useSettled } from "@/lib/settled";

const KEEP = [
  { value: "day", label: "Last 24 hours" },
  { value: "week", label: "Last 7 days" },
  { value: "month", label: "Last 30 days" },
  { value: "nothing", label: "Nothing" },
] as const;

type Keep = (typeof KEEP)[number]["value"];

/**
 * History, as the History board draws it: what Mado did, a week of days at a time, newest
 * first. A new picture can be taken away (into quarantine) and put back; a replaced original
 * put back; a review of duplicates and bursts put back whole, or a picture of it; and History
 * cleared of what's older than a day, a week or a month.
 */
export function HistoryPage() {
  const [typed, setTyped] = useState("");
  const asked = useSettled(typed.trim(), 250);
  const history = useHistory(asked);
  const act = useHistoryAction();
  const [clearing, setClearing] = useState(false);
  const [cleared, setCleared] = useState<number | null>(null);
  const entries = history.data?.pages.flatMap((page) => page.entries) ?? [];
  const batches = new Map(
    (history.data?.pages.flatMap((page) => page.batches ?? []) ?? []).map((line) => [
      line.id,
      line,
    ]),
  );
  const undoBatch = useBatchUndo();
  const undoReview = useReviewUndo();
  const reviews = new Map(
    (history.data?.pages.flatMap((page) => page.reviews ?? []) ?? []).map((line) => [
      line.id,
      line,
    ]),
  );
  const [undone, setUndone] = useState<string[]>([]);
  const answered = history.data !== undefined;

  return (
    <>
      <header className="page-top flex animate-fade-up flex-wrap items-center gap-x-4 gap-y-2.5">
        <h1 className="type-title">History</h1>
        <p className="text-14 text-fg-muted">
          What Mado did, a week at a time. What's set aside can be put back for 30 days.
        </p>
        <div className="ml-auto flex flex-wrap gap-2">
          <label className="flex h-9 items-center gap-2 rounded-6 border border-field-edge bg-field px-2.5 text-13 text-fg-faint">
            <Search size={15} aria-hidden="true" />
            <span className="sr-only">Filter by picture or folder</span>
            <input
              type="search"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder="Filter by picture or folder"
              className="w-48 bg-transparent text-fg outline-none placeholder:text-fg-faint"
            />
          </label>
          {entries.length > 0 && (
            <Button size="sm" onClick={() => setClearing(true)}>
              Clear History…
            </Button>
          )}
        </div>
      </header>

      {cleared !== null && (
        <p role="status" className="text-13 text-fg-muted">
          {cleared === 0
            ? "There was nothing to clear: what's left is newer, or can still be put back."
            : `${cleared} ${cleared === 1 ? "line" : "lines"} cleared from History. Your pictures stay as they are.`}
        </p>
      )}
      <EngineProblem queries={[history]} />
      {!answered && (
        <Loading label="Loading History" queries={[history]}>
          <PanelSkeleton rows={3} />
          <PanelSkeleton rows={2} />
        </Loading>
      )}
      {(act.isError || undoBatch.isError || undoReview.isError) && (
        <p role="alert" className="text-13 text-broken-fg">
          {act.error?.message ?? undoBatch.error?.message ?? undoReview.error?.message}
        </p>
      )}
      {undone.length > 0 && (
        <div role="alert" className="flex flex-col gap-1 text-13 text-broken-fg">
          <span>Some of them couldn't be, so they're as they were:</span>
          {undone.slice(0, 5).map((why) => (
            <span key={why}>{why}</span>
          ))}
        </div>
      )}
      {answered && entries.length === 0 && asked && (
        <p className="text-13 text-fg-muted">Nothing in History goes by “{asked}”.</p>
      )}
      {answered && entries.length === 0 && !asked && (
        <EmptyState title="Nothing yet" illustration={<WindowIllustration />}>
          Mado lists here every picture it makes for you, newest first, and anything it sets aside:
          a new picture can be taken away, and a replaced original put back, from here.
        </EmptyState>
      )}

      {days(entries).map(([day, onDay]) => (
        <section
          key={day}
          aria-label={dayLabel(day).join(" ")}
          className="flex animate-fade-up flex-col rounded-8 border border-edge bg-glass"
        >
          <h2 className="flex items-baseline gap-2.5 px-4.5 pt-3 pb-2.5 font-semibold text-15">
            {dayLabel(day)[0]}
            <span className="font-normal text-13 text-fg-faint">{dayLabel(day)[1]}</span>
          </h2>
          <ul>
            {grouped(onDay).map((each) =>
              "lines" in each && !("batch" in each) ? (
                <Reviewed
                  key={`review-${each.review}`}
                  line={reviews.get(each.review)}
                  lines={each.lines}
                  busy={act.isPending || undoReview.isPending}
                  onPutBack={() =>
                    undoReview.mutate(
                      { path: `/history/reviews/${each.review}/undo` },
                      { onSuccess: (done) => setUndone(done.problems) },
                    )
                  }
                  onUndo={(id) => act.mutate({ path: `/history/${id}/undo` })}
                />
              ) : "lines" in each ? (
                <Batched
                  key={`batch-${each.batch}`}
                  line={batches.get(each.batch)}
                  lines={each.lines}
                  busy={act.isPending || undoBatch.isPending}
                  onBatch={(way) =>
                    undoBatch.mutate(
                      { path: `/history/batches/${each.batch}/${way}` },
                      { onSuccess: (done) => setUndone(done.problems) },
                    )
                  }
                  onUndo={(id) => act.mutate({ path: `/history/${id}/undo` })}
                  onRedo={(id) => act.mutate({ path: `/history/${id}/redo` })}
                />
              ) : (
                <Line
                  key={each.id}
                  entry={each}
                  busy={act.isPending}
                  onUndo={() => act.mutate({ path: `/history/${each.id}/undo` })}
                  onRedo={() => act.mutate({ path: `/history/${each.id}/redo` })}
                />
              ),
            )}
          </ul>
        </section>
      ))}

      {history.hasNextPage && (
        <Button
          className="self-start"
          disabled={history.isFetchingNextPage}
          onClick={() => void history.fetchNextPage()}
        >
          {history.isFetchingNextPage ? "Loading the week before…" : "Show the week before"}
        </Button>
      )}

      {clearing && (
        <ClearHistory
          onClose={() => setClearing(false)}
          onCleared={(gone) => {
            setCleared(gone);
            setClearing(false);
          }}
        />
      )}
    </>
  );
}

function Line(props: {
  entry: HistoryEntry;
  busy: boolean;
  onUndo: () => void;
  onRedo: () => void;
}) {
  const { entry } = props;
  const [title, detail] = words(entry);
  return (
    <li className="flex items-center gap-3.5 border-edge border-t px-4.5 py-3">
      <span className="w-11 shrink-0 font-mono text-13 text-fg-faint">{clock(entry.at)}</span>
      <Thumbnail entry={entry} />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="font-semibold text-14">{title}</span>
        <span className="text-13 text-fg-muted">{detail}</span>
      </span>
      {entry.canUndo && (entry.kind === "replaced" || entry.kind === "aside") && (
        <Button size="sm" disabled={props.busy} onClick={props.onUndo}>
          Put back
        </Button>
      )}
      {entry.canUndo && entry.kind === "made" && (
        <Button size="sm" disabled={props.busy} onClick={props.onUndo}>
          Take it away
        </Button>
      )}
      {entry.canRedo && (
        <Button size="sm" disabled={props.busy} onClick={props.onRedo}>
          {entry.kind === "replaced" ? "Replace it again" : "Put it back"}
        </Button>
      )}
    </li>
  );
}

type Folded =
  | HistoryEntry
  | { batch: number; lines: HistoryEntry[] }
  | { review: number; lines: HistoryEntry[] };

/** A day's lines with each batch's, and each review's, folded into one where its newest line is. */
function grouped(lines: HistoryEntry[]): Folded[] {
  const found: Folded[] = [];
  const seen = new Map<string, { lines: HistoryEntry[] }>();
  for (const line of lines) {
    const key =
      line.batch !== null
        ? `batch-${line.batch}`
        : line.review !== null
          ? `review-${line.review}`
          : null;
    if (key === null) {
      found.push(line);
      continue;
    }
    const group = seen.get(key);
    if (group) {
      group.lines.push(line);
      continue;
    }
    const made =
      line.batch !== null
        ? { batch: line.batch, lines: [line] }
        : { review: line.review ?? 0, lines: [line] };
    seen.set(key, made);
    found.push(made);
  }
  return found;
}

/** A review of duplicates and bursts as one line, as the History board draws it: how many it set
 * aside and what that freed, Put back for all of it, and each picture's own line under it when
 * asked. */
function Reviewed(props: {
  line: ReviewLine | undefined;
  lines: HistoryEntry[];
  busy: boolean;
  onPutBack: () => void;
  onUndo: (id: number) => void;
}) {
  const { line, lines } = props;
  const [open, setOpen] = useState(false);
  const first = lines[0];
  if (!line || !first) return null;
  const [title, detail] = reviewWords(line);
  return (
    <li className="border-edge border-t">
      <div className="flex items-center gap-3.5 px-4.5 py-3">
        <span className="w-11 shrink-0 font-mono text-13 text-fg-faint">{clock(first.at)}</span>
        <Thumbnail entry={{ ...first, picture: line.picture ?? first.picture }} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="font-semibold text-14">{title}</span>
          <span className="text-13 text-fg-muted">
            {detail}{" "}
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setOpen((was) => !was)}
              className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
            >
              {open
                ? lines.length === 1
                  ? "Hide the picture"
                  : "Hide the pictures"
                : lines.length === 1
                  ? "Show the picture"
                  : `Show the ${count(lines.length)} pictures`}
            </button>
          </span>
        </span>
        {line.canUndo && (
          <Button
            size="sm"
            disabled={props.busy}
            onClick={props.onPutBack}
            aria-label={`Put back all ${count(line.pictures - line.back - line.cleared)}`}
          >
            Put back
          </Button>
        )}
      </div>
      {open && (
        <ul className="border-edge border-t bg-tint/3 pl-6">
          {lines.map((each) => (
            <Line
              key={each.id}
              entry={each}
              busy={props.busy}
              onUndo={() => props.onUndo(each.id)}
              onRedo={() => undefined}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

/** What a review's line says: "Set aside 211 duplicates and bursts, freeing 1.4 GB", "Kept the
 * sharpest of each; the rest are in quarantine on D: until 21 Dec"; once all of it is back,
 * "Put back the 211 duplicates and bursts". */
function reviewWords(line: ReviewLine): [string, string] {
  const n = line.pictures;
  const what =
    line.duplicates > 0 && line.bursts > 0
      ? "duplicates and bursts"
      : line.bursts > 0
        ? n === 1
          ? "picture from a burst"
          : "pictures from bursts"
        : n === 1
          ? "duplicate"
          : "duplicates";
  const waiting = n - line.back - line.cleared;
  if (line.back === n) {
    return [
      `Put back the ${count(n)} ${what}`,
      "Everything set aside is back where it was, and the review lists them again.",
    ];
  }
  const title = `Set aside ${count(n)} ${what}, freeing ${size(line.bytes)}`;
  const since = [
    line.back ? `${count(line.back)} since put back` : null,
    line.cleared ? `${count(line.cleared)} since cleared out of quarantine` : null,
  ]
    .filter(Boolean)
    .join(", ");
  const kept = line.duplicates > 0 && line.bursts === 0 ? "the biggest" : "the sharpest";
  if (waiting === 0) {
    return [title, `Kept ${kept} of each.${since ? ` ${capital(since)}.` : ""}`];
  }
  const until = line.asideUntil ? shortDay(line.asideUntil) : "their days are up";
  return [
    title,
    `Kept ${kept} of each; the rest are in quarantine until ${until}${since ? `, ${since}` : ""}.`,
  ];
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A batch as one line, as the History board draws it: what it made and where, what undoes all
 * of it, and its pictures' own lines under it when asked. */
function Batched(props: {
  line: BatchLine | undefined;
  lines: HistoryEntry[];
  busy: boolean;
  onBatch: (way: "undo" | "redo") => void;
  onUndo: (id: number) => void;
  onRedo: (id: number) => void;
}) {
  const { line, lines } = props;
  const [open, setOpen] = useState(false);
  const first = lines[0];
  if (!line || !first) return null;
  const [title, detail] = batchWords(line);
  return (
    <li className="border-edge border-t">
      <div className="flex items-center gap-3.5 px-4.5 py-3">
        <span className="w-11 shrink-0 font-mono text-13 text-fg-faint">{clock(first.at)}</span>
        <Thumbnail entry={{ ...first, picture: line.picture ?? first.picture }} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="font-semibold text-14">{title}</span>
          <span className="text-13 text-fg-muted">
            {detail}{" "}
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setOpen((was) => !was)}
              className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
            >
              {open
                ? lines.length === 1
                  ? "Hide the picture"
                  : "Hide the pictures"
                : lines.length === 1
                  ? "Show the picture"
                  : `Show the ${count(lines.length)} pictures`}
            </button>
          </span>
        </span>
        {line.working && <span className="shrink-0 text-13 text-fg-faint">Still being made</span>}
        {!line.working && line.canUndo && (
          <Button size="sm" disabled={props.busy} onClick={() => props.onBatch("undo")}>
            {line.how === "replace" ? "Put the originals back" : "Take them away"}
          </Button>
        )}
        {!line.working && !line.canUndo && line.canRedo && (
          <Button size="sm" disabled={props.busy} onClick={() => props.onBatch("redo")}>
            {line.how === "replace" ? "Replace them again" : "Put them back"}
          </Button>
        )}
      </div>
      {open && (
        <ul className="border-edge border-t bg-tint/3 pl-6">
          {lines.map((each) => (
            <Line
              key={each.id}
              entry={each}
              busy={props.busy}
              onUndo={() => props.onUndo(each.id)}
              onRedo={() => props.onRedo(each.id)}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

const FOR: Record<string, string> = {
  phone: "the phone",
  tablet: "the tablet",
  laptop: "the laptop",
  monitor: "the monitor",
  ultrawide: "the ultrawide",
  tv: "the TV",
  print: "printing",
  screen: "your screen",
};

/** What a batch's line says: "Made 47 pictures for the TV overnight", "Holiday prints, as new
 * pictures in Holiday › Edited · Old pier.tif didn't work". */
function batchWords(line: BatchLine): [string, string] {
  const pictures = (n: number) => `${count(n)} ${n === 1 ? "picture" : "pictures"}`;
  const until = line.asideUntil ? shortDay(line.asideUntil) : null;
  const waits = `on ${line.drive ?? "its drive"} until ${until ?? "its days are up"}`;
  const failed =
    line.failed.length === 1
      ? ` · ${line.failed[0]} didn't work`
      : line.failed.length > 1
        ? ` · ${count(line.failed.length)} didn't work`
        : "";
  const forWhat = line.purpose ? ` for ${FOR[line.purpose] ?? "its screen"}` : "";
  const night = line.overnight ? " overnight" : "";
  if (line.made === 0 && line.undone > 0) {
    if (line.how === "replace")
      return [
        `Put ${pictures(line.undone)} back`,
        `Their ${versionOf(line)} versions wait in quarantine ${waits}.`,
      ];
    return [
      `Took away ${pictures(line.undone)} made${forWhat}`,
      `They wait in quarantine ${waits}.`,
    ];
  }
  const taken = line.undone ? `, ${count(line.undone)} since put back or taken away` : "";
  if (line.how === "replace") {
    return [
      `Replaced ${pictures(line.made)} with their ${versionOf(line)} versions${night}`,
      `${line.name}; the originals are in quarantine ${waits}${taken}${failed}`,
    ];
  }
  const title = line.savedAs
    ? line.watch
      ? `The watch folder ${line.watch} saved ${pictures(line.made)} as ${line.savedAs}`
      : `Saved ${pictures(line.made)} as ${line.savedAs}${night}`
    : line.watch
      ? `The watch folder ${line.watch} made ${pictures(line.made)}`
      : line.purpose
        ? `Made ${pictures(line.made)}${forWhat}${night}`
        : `Made ${pictures(line.made)} ${madeWith(line)}${night}`;
  const where = line.into === "beside the originals" ? "beside the originals" : `in ${line.into}`;
  return [title, `${line.name}, as new pictures ${where}${taken}${failed}`];
}

function Thumbnail({ entry }: { entry: HistoryEntry }) {
  const image = usePictureImage(entry.picture ? pictureAddress(entry.picture, "thumbnail") : null);
  if (image.address) {
    return (
      <img
        src={image.address}
        alt=""
        className="h-9 w-13 shrink-0 animate-fade-in rounded-3 object-cover"
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className="flex h-9 w-13 shrink-0 items-center justify-center rounded-3 bg-raised text-fg-muted"
    >
      {entry.kind === "emptied" ? <Trash2 size={18} /> : <Folder size={18} />}
    </span>
  );
}

/** What a line says: what Mado did, and where that stands now. */
function words(entry: HistoryEntry): [string, string] {
  const until = entry.asideUntil ? shortDay(entry.asideUntil) : null;
  const drive = entry.aside ? entry.aside.slice(0, 2) : "its drive";
  switch (entry.kind) {
    case "emptied":
      return [
        `Emptied ${entry.name}'s quarantine${entry.bytes ? `, ${size(entry.bytes)}` : ""}`,
        "You asked to, before its 30 days were up. It can't be put back.",
      ];
    case "aside":
      if (entry.undoneAt) return [`Put ${entry.name} back`, "It's back where it was."];
      if (entry.clearedAt)
        return [
          `Set aside ${entry.name}`,
          entry.clearedBy === "owner"
            ? "It went when you emptied the quarantine."
            : "It was cleared out of quarantine after its 30 days.",
        ];
      return [
        `Set aside ${entry.name}`,
        `${entry.keptName ?? "Another"} was kept; this one is in quarantine on ${drive} until ${until ?? "its days are up"}.`,
      ];
    case "replaced":
      if (entry.undoneAt)
        return [
          `Put ${entry.name} back`,
          until
            ? `Its ${versionOf(entry)} version waits in quarantine on ${drive} until ${until}.`
            : `Its ${versionOf(entry)} version was set aside.`,
        ];
      return [
        `Replaced ${entry.name} with its ${versionOf(entry)} version`,
        entry.clearedAt
          ? entry.clearedBy === "owner"
            ? "The original went when you emptied the quarantine."
            : "The original was cleared out of quarantine after its 30 days."
          : `The original is in quarantine on ${drive} until ${until ?? "its days are up"}.`,
      ];
    case "made":
      if (entry.undoneAt)
        return [
          `Took away ${entry.resultName ?? "a picture made"}`,
          entry.clearedAt
            ? entry.clearedBy === "owner"
              ? "It went when you emptied the quarantine."
              : "It was cleared out of quarantine after its 30 days."
            : `It waits in quarantine on ${drive} until ${until ?? "its days are up"}.`,
        ];
      return [
        madeWith(entry)
          ? `Made ${stem(entry.name)} ${madeWith(entry)}`
          : `Saved ${stem(entry.name)} as ${formatOf(entry.resultName)}`, // saved as it is
        `${entry.depth?.startsWith(MOTION_WORDS) ? "As a video" : "As a new picture"}: ${entry.resultName ?? ""}${entry.result ? ` in ${split(split(entry.result)[1])[0]}` : ""}`,
      ];
  }
}

/** The format a picture saved as it is was saved in, by its name: "JPEG", "AVIF". */
function formatOf(name: string | null): string {
  const extension = name?.split(".").pop()?.toLowerCase() ?? "";
  return (
    { jpg: "JPEG", jpeg: "JPEG", png: "PNG", webp: "WebP", avif: "AVIF" }[extension] ??
    "a new picture"
  );
}

function ClearHistory(props: { onClose: () => void; onCleared: (gone: number) => void }) {
  const [keep, setKeep] = useState<Keep>("week");
  const clear = useClearHistory();
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(30rem,calc(100vw-2rem))]">
        <DialogHeader
          title="Clear History?"
          description="Mado forgets these lines. No picture changes, and what's still set aside stays, so it can be put back."
        />
        <DialogBody>
          <span className="text-13 text-fg-muted">Keep</span>
          <Segmented
            label="Keep"
            value={keep}
            options={KEEP}
            onChange={setKeep}
            className="flex-wrap"
          />
          {clear.isError && (
            <p role="alert" className="text-13 text-broken-fg">
              {clear.error.message}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <span />
          <span className="flex gap-2">
            <Button variant="ghost" onClick={props.onClose}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={clear.isPending}
              onClick={() =>
                clear.mutate(
                  { path: "/history/clear", body: { keep } },
                  { onSuccess: (done) => props.onCleared(done.cleared) },
                )
              }
            >
              Clear History
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The lines by day, newest first; a batch's (or a review's) all on the day of its newest (one
 * made overnight runs past midnight). */
function days(entries: HistoryEntry[]): [string, HistoryEntry[]][] {
  const found = new Map<string, HistoryEntry[]>();
  const groupDays = new Map<string, string>();
  for (const each of entries) {
    let day = localDay(each.at);
    const key =
      each.batch !== null
        ? `batch-${each.batch}`
        : each.review !== null
          ? `review-${each.review}`
          : null;
    if (key !== null) {
      day = groupDays.get(key) ?? day;
      groupDays.set(key, day);
    }
    found.set(day, [...(found.get(day) ?? []), each]);
  }
  return [...found];
}

function localDay(at: string): string {
  const moment = new Date(at);
  if (Number.isNaN(moment.getTime())) return at.slice(0, 10);
  const month = String(moment.getMonth() + 1).padStart(2, "0");
  const day = String(moment.getDate()).padStart(2, "0");
  return `${moment.getFullYear()}-${month}-${day}`;
}

/** "Today", "Sunday 22 November"; "Yesterday", "Saturday 21 November"; "Thursday", "19 November". */
function dayLabel(day: string): [string, string] {
  const moment = new Date(`${day}T00:00:00`);
  const today = localDay(new Date().toISOString());
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const weekday = moment.toLocaleDateString("en-GB", { weekday: "long" });
  const date = moment.toLocaleDateString("en-GB", { day: "numeric", month: "long" });
  if (day === today) return ["Today", `${weekday} ${date}`];
  if (day === localDay(yesterday.toISOString())) return ["Yesterday", `${weekday} ${date}`];
  return [weekday, date];
}

function clock(at: string): string {
  const moment = new Date(at);
  if (Number.isNaN(moment.getTime())) return at.slice(11, 16);
  return moment.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** "22 Dec", from "2026-12-22". */
function shortDay(day: string): string {
  const moment = new Date(`${day}T00:00:00`);
  if (Number.isNaN(moment.getTime())) return day;
  return moment.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
