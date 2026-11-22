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
  type HistoryEntry,
  pictureAddress,
  useClearHistory,
  useHistory,
  useHistoryAction,
  usePictureImage,
} from "@/lib/engine";
import { size, split, stem } from "@/lib/format";
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
 * put back; and History cleared of what's older than a day, a week or a month.
 */
export function HistoryPage() {
  const [typed, setTyped] = useState("");
  const asked = useSettled(typed.trim(), 250);
  const history = useHistory(asked);
  const act = useHistoryAction();
  const [clearing, setClearing] = useState(false);
  const [cleared, setCleared] = useState<number | null>(null);
  const entries = history.data?.pages.flatMap((page) => page.entries) ?? [];
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
      {act.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {act.error.message}
        </p>
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
            {onDay.map((each) => (
              <Line
                key={each.id}
                entry={each}
                busy={act.isPending}
                onUndo={() => act.mutate({ path: `/history/${each.id}/undo` })}
                onRedo={() => act.mutate({ path: `/history/${each.id}/redo` })}
              />
            ))}
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
      {entry.canUndo && entry.kind === "replaced" && (
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
    case "replaced":
      if (entry.undoneAt)
        return [
          `Put ${entry.name} back`,
          until
            ? `Its ${entry.madeFor} version waits in quarantine on ${drive} until ${until}.`
            : `Its ${entry.madeFor} version was set aside.`,
        ];
      return [
        `Replaced ${entry.name} with its ${entry.madeFor} version`,
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
        `Made ${stem(entry.name)} for ${entry.madeFor}`,
        `As a new picture: ${entry.resultName ?? ""}${entry.result ? ` in ${split(split(entry.result)[1])[0]}` : ""}`,
      ];
  }
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

/** The lines by their day, newest first. */
function days(entries: HistoryEntry[]): [string, HistoryEntry[]][] {
  const found = new Map<string, HistoryEntry[]>();
  for (const each of entries) {
    const day = localDay(each.at);
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
