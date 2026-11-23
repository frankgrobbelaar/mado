import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { Toggle } from "@/components/toggle";
import { Segmented } from "@/components/ui/segmented";
import { type DailyState, type Layout, useDaily, useFolders } from "@/lib/engine";
import { clock, count } from "@/lib/format";
import { useSettled } from "@/lib/settled";
import { useSetStartWithWindows, useStartWithWindows } from "@/lib/startup";

const LAYOUTS = [
  { value: "each", label: "One for each" },
  { value: "across", label: "One across all" },
] as const;

/**
 * The daily change, off till it's turned on: a picture that suits each monitor (or one across all)
 * from the favourites or a library folder, never the same again till all have been, changed at the
 * time chosen (07:00 at first), made the evening before so the change is instant. Mado has to be
 * running for it, open or in the tray, so Start with Windows sits beside it.
 */
export function EveryDay(props: { daily: DailyState; monitors: number }) {
  const { daily } = props;
  const change = useDaily();
  const folders = useFolders();
  const starts = useStartWithWindows();
  const setStarts = useSetStartWithWindows();
  const timeId = useId();
  const fromId = useId();
  // The time as it's typed, sent once it settles or the field is left: typing 08:00 passes
  // through 00:00 on the way, which isn't the time meant.
  const [typed, setTyped] = useState<string | null>(null);
  const settled = useSettled(typed, 600);
  const sentAt = useRef<string | null>(null);
  const at = typed ?? daily.at;
  const send = (next: Partial<Pick<DailyState, "on" | "at" | "layout" | "folder">>) =>
    change.mutate(
      {
        path: "/wallpaper/daily",
        body: { on: daily.on, at, layout: daily.layout, folder: daily.folder, ...next },
      },
      { onSettled: () => setTyped((now) => (now === next.at ? null : now)) },
    );
  const sendTime = (time: string | null) => {
    if (!time || time === sentAt.current) return;
    sentAt.current = time;
    if (time !== daily.at) send({ at: time });
    else setTyped(null);
  };
  useEffect(() => {
    sendTime(settled);
  });
  const fromName =
    daily.folder === null
      ? "your favourites"
      : (folders.data?.find((each) => each.id === daily.folder)?.name ?? "that folder");

  return (
    <div className="flex flex-col gap-3.5">
      <Toggle
        label="Change it every day"
        text={`From ${fromName}, a picture that suits each monitor, its way round and big enough; none again till all have been.`}
        checked={daily.on}
        onChange={(on) => send({ on })}
      />
      <div className="flex flex-col gap-3 rounded-8 border border-edge bg-glass px-4 py-3.5">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor={timeId} className="font-semibold text-14">
            At
          </label>
          <input
            id={timeId}
            type="time"
            step={60}
            value={at}
            onChange={(event) => setTyped(event.target.value || null)}
            onBlur={() => sendTime(typed)}
            className="h-9 rounded-6 border border-field-edge bg-field px-2.5 font-mono text-13 text-fg"
          />
        </div>
        {props.monitors > 1 && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-semibold text-14">Layout</span>
            <Segmented
              label="Every day's layout"
              value={daily.layout}
              options={LAYOUTS}
              onChange={(layout: Layout) => send({ layout })}
            />
          </div>
        )}
        <div className="flex items-center justify-between gap-3">
          <label htmlFor={fromId} className="font-semibold text-14">
            From
          </label>
          <select
            id={fromId}
            value={daily.folder ?? ""}
            onChange={(event) =>
              send({ folder: event.target.value ? Number(event.target.value) : null })
            }
            className="h-9 max-w-52 rounded-6 border border-field-edge bg-field px-2 text-13 text-fg"
          >
            <option value="">Favourites</option>
            {folders.data?.map((folder) => (
              <option key={folder.id} value={folder.id}>
                {folder.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <Situation daily={daily} />
      {change.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {change.error.message}
        </p>
      )}
      <p className="text-13 text-fg-muted leading-normal">
        The change needs Mado open, or waiting in the tray. Closed at the time, it changes as Mado
        next starts.
      </p>
      <Toggle
        label="Start with Windows"
        text="Mado starts in the tray when you sign in, so the change happens on time."
        checked={starts.data ?? false}
        onChange={(on) => setStarts.mutate(on)}
      />
    </div>
  );
}

/** Where the daily change stands: when it next changes, what it has to choose from, and why it
 * couldn't, when it couldn't. */
function Situation({ daily }: { daily: DailyState }) {
  const none = daily.candidates === 0 && daily.skipped === 0;
  if (daily.folder === null && none) {
    return (
      <section className="flex flex-col items-start gap-1.5 rounded-8 border border-dash border-dashed bg-surface px-4 py-3.5">
        <h3 className="font-semibold text-14">No favourites yet</h3>
        <p className="text-13 text-fg-muted leading-normal">
          Give pictures a heart in the Library or on their pages, and the wallpaper changes to one
          of them each day.
        </p>
        <Link to="/library?favourites=1" className="text-13 text-accent-fg underline">
          Show your favourites
        </Link>
      </section>
    );
  }
  const lines: string[] = [];
  if (daily.on && daily.next) {
    const at = new Date(daily.next);
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const day =
      at.toDateString() === new Date().toDateString()
        ? "today"
        : at.toDateString() === tomorrow.toDateString()
          ? "tomorrow"
          : at.toLocaleDateString("en-GB", { weekday: "long" });
    lines.push(
      `Next change: ${day} at ${clock(daily.next)}${daily.ready ? ", made already" : ""}.`,
    );
  }
  const has = `${count(daily.candidates)} ${daily.candidates === 1 ? "picture" : "pictures"} to choose from`;
  lines.push(
    daily.skipped
      ? `${has}; ${count(daily.skipped)} aren't there now (gone, moved, or on a drive that isn't connected), so they're skipped.`
      : `${has}.`,
  );
  return (
    <div className="flex flex-col gap-1.5" role="status">
      {lines.map((line) => (
        <p key={line} className="text-13 text-fg-muted leading-normal">
          {line}
        </p>
      ))}
      {daily.problem && (
        <p role="alert" className="text-13 text-broken-fg leading-normal">
          {daily.problem}
        </p>
      )}
    </div>
  );
}
