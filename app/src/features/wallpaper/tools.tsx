import { CheckCircle2, X } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Slider } from "@/components/ui/slider";
import { Needs } from "@/features/picture/size-tab";
import {
  type PartPlan,
  type PictureChoice,
  pictureAddress,
  type Quality,
  type Shape,
  type StudioState,
  usePictureImage,
  useTools,
} from "@/lib/engine";
import { about, clock, stem } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Tab = "now" | "daily";

const TABS = [
  { key: "now", label: "This wallpaper" },
  { key: "daily", label: "Every day" },
] as const;

const SHAPES = [
  { value: "crop", label: "Crop around the subject" },
  { value: "extend", label: "Extend the edges" },
] as const;

const QUALITIES = [
  { value: "fast", label: "Fast" },
  { value: "best", label: "Best" },
] as const;

/** The studio column's two tabs, as the picture page's tools column has its own: this wallpaper,
 * and every day's change. The arrow keys, Home and End go from one to the other. */
export function Tabs({ tab, onTab }: { tab: Tab; onTab: (tab: Tab) => void }) {
  const tabs = useRef<Partial<Record<Tab, HTMLButtonElement | null>>>({});
  function move(event: KeyboardEvent<HTMLDivElement>) {
    const next: Tab | null =
      event.key === "ArrowRight" || event.key === "ArrowLeft"
        ? tab === "now"
          ? "daily"
          : "now"
        : event.key === "Home"
          ? "now"
          : event.key === "End"
            ? "daily"
            : null;
    if (!next) return;
    event.preventDefault();
    onTab(next);
    tabs.current[next]?.focus();
  }
  return (
    <div
      role="tablist"
      aria-label="This wallpaper, or every day's"
      onKeyDown={move}
      className="flex rounded-6 bg-well p-0.75"
    >
      {TABS.map((each) => {
        const chosen = each.key === tab;
        return (
          <button
            key={each.key}
            ref={(button) => {
              tabs.current[each.key] = button;
            }}
            id={`studio-${each.key}`}
            type="button"
            role="tab"
            aria-selected={chosen}
            aria-controls={chosen ? "studio-panel" : undefined}
            tabIndex={chosen ? 0 : -1}
            onClick={() => onTab(each.key)}
            className={cn(
              "press flex h-8 flex-1 items-center justify-center rounded-4 text-13",
              chosen
                ? "bg-raised font-semibold text-fg"
                : "cursor-pointer font-medium text-fg-muted hover:text-fg",
            )}
          >
            {each.label}
          </button>
        );
      })}
    </div>
  );
}

/** The picture a monitor (or every monitor) shows: picked, changed, or let go. */
export function Chosen(props: {
  choice: PictureChoice | null;
  busy: boolean;
  onPick: () => void;
  onLetGo: () => void;
}) {
  const { choice } = props;
  const image = usePictureImage(choice ? pictureAddress(choice.picture, "thumbnail") : null);
  if (!choice) {
    return (
      <div className="flex flex-col items-start gap-2.5 rounded-8 border border-dash border-dashed px-4 py-4">
        <p className="text-13 text-fg-muted leading-normal">
          No picture yet. Pick one from your favourites or the library, or drop one on the window,
          or paste it.
        </p>
        <Button size="sm" disabled={props.busy} onClick={props.onPick}>
          Pick a picture…
        </Button>
      </div>
    );
  }
  const { picture } = choice;
  return (
    <div className="flex items-center gap-3">
      <span className="relative h-14 w-20 shrink-0 overflow-hidden rounded-4 bg-behind">
        {image.address && <img src={image.address} alt="" className="size-full object-cover" />}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate font-semibold text-14">{stem(picture.name)}</span>
        {picture.width && picture.height && (
          <span className="font-mono text-12 text-fg-muted">
            {picture.width} × {picture.height}
            {picture.outside ? " · from outside the library" : ""}
          </span>
        )}
      </span>
      <span className="flex shrink-0 gap-1.5">
        <Button size="sm" disabled={props.busy} onClick={props.onPick}>
          Change…
        </Button>
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Let ${stem(picture.name)} go`}
          title="Let it go"
          className="w-9 px-0"
          disabled={props.busy}
          onClick={props.onLetGo}
        >
          <X size={16} aria-hidden="true" />
        </Button>
      </span>
    </div>
  );
}

/** How the chosen picture is cut and made: its shape, how near, the gap for the bezels one across
 * all, what each part comes to, honestly, and Fast or Best where the AI makes it bigger. A picture
 * Mado can't read says why, and nothing else. */
export function ChoiceTools(props: {
  studio: StudioState;
  choice: PictureChoice;
  parts: PartPlan[];
  zoom: number;
  onZoom: (zoom: number) => void;
  gap: number;
  onGap: (gap: number) => void;
  onChange: (next: { shape?: Shape; quality?: Quality | null; x?: null; y?: null }) => void;
}) {
  const { studio, choice, parts } = props;
  const across = studio.layout === "across";
  const ai = parts.some((each) => each.method === "ai");
  const quality = choice.quality ?? parts.find((each) => each.method === "ai")?.quality ?? "fast";
  const names = new Map(studio.monitors.map((each) => [each.key, each.name]));
  if (choice.problem) {
    return (
      <p
        role="alert"
        className="flex items-start gap-2 rounded-8 border border-edge bg-glass px-3.5 py-3 text-13 text-broken-fg leading-normal"
      >
        <span aria-hidden="true" className="status-problem mt-1 size-2.5 shrink-0 rounded-2" />
        {choice.problem}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-2">
        <h2 className="type-eyebrow">Shape</h2>
        <Segmented
          label="Shape"
          value={choice.shape}
          options={SHAPES}
          onChange={(shape: Shape) => props.onChange({ shape })}
          className="self-start"
        />
        {choice.shape === "extend" && (
          <p className="text-12 text-fg-faint leading-normal">
            Mado draws more at the edges with its model: it suits skies, walls and water; faces and
            busy detail at an edge smear.
          </p>
        )}
      </section>
      {choice.shape === "crop" && (
        <section className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="type-eyebrow">Zoom</h2>
            <span className="font-mono text-12 text-fg-muted">{props.zoom.toFixed(2)}×</span>
          </div>
          <Slider
            label="Zoom"
            value={props.zoom}
            min={1}
            max={4}
            step={0.05}
            valueText={`${props.zoom.toFixed(2)} times nearer`}
            onChange={props.onZoom}
          />
          <p className="text-12 text-fg-faint leading-normal">
            Drag the picture on a monitor to move where it's cut.{" "}
            {(choice.x !== null || choice.y !== null || choice.zoom !== 1) && (
              <button
                type="button"
                onClick={() => {
                  props.onZoom(1);
                  props.onChange({ x: null, y: null });
                }}
                className="cursor-pointer text-accent-fg underline"
              >
                Around its subject again
              </button>
            )}
          </p>
        </section>
      )}
      {across && (
        <section className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="type-eyebrow">Gap for the bezels</h2>
            <span className="font-mono text-12 text-fg-muted">{props.gap} px</span>
          </div>
          <Slider
            label="Gap for the bezels"
            value={props.gap}
            min={0}
            max={200}
            step={1}
            valueText={`${props.gap} pixels`}
            onChange={props.onGap}
          />
          <p className="text-12 text-fg-faint leading-normal">
            What the bezels hide is left out, so a line across them stays straight.
          </p>
        </section>
      )}
      <section className="flex flex-col gap-2.5 rounded-8 border border-edge bg-glass px-3.5 py-3">
        {parts.map((part) => (
          <PartWords
            key={part.monitor}
            part={part}
            name={across ? names.get(part.monitor) : null}
          />
        ))}
        {parts.length === 0 && (
          <p className="text-13 text-fg-muted">Mado is looking at the picture…</p>
        )}
        {ai && (
          <div className="flex flex-wrap items-center gap-2.5">
            <Segmented
              label="Quality"
              value={quality}
              options={QUALITIES}
              onChange={(next: Quality) => props.onChange({ quality: next })}
            />
            <span className="text-12 text-fg-faint">Best takes longer and looks finer.</span>
          </div>
        )}
      </section>
    </div>
  );
}

function PartWords({ part, name }: { part: PartPlan; name: string | null | undefined }) {
  const bigger = part.scale > 1;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-13 leading-normal">
        {name && <span className="font-semibold">{name}: </span>}
        <span className="font-mono">
          {part.width} × {part.height}
        </span>
        {bigger ? `, made ${times(part.scale)} times bigger. ` : ". "}
        <span className="text-fg-muted">{part.how}</span>
      </p>
      {part.warning && (
        <p className="flex items-start gap-2 text-13 text-broken-fg leading-normal">
          <span aria-hidden="true" className="status-problem mt-1 size-2.5 shrink-0 rounded-2" />
          {part.warning}
        </p>
      )}
    </div>
  );
}

/** How many times bigger, as people say it: "2.5", "8". */
export function times(scale: number): string {
  return scale.toFixed(1).replace(/\.0$/, "");
}

/** A model a part waits for: downloaded the first time it's asked for, as the Size tab does. */
export function NeedsFor({ ids }: { ids: string[] }) {
  const tools = useTools();
  const needs = ids.flatMap((id) => {
    const tool = tools.data?.find((each) => each.id === id);
    return tool ? [{ id: tool.id, name: tool.name, size: tool.size }] : [];
  });
  if (!needs.length) return null;
  return <Needs needs={needs} onFast={null} onCrop={null} onReady={() => undefined} />;
}

/** The column's foot, as Save is on a picture's: the wallpaper being made, set or saved, and the
 * one primary action, Set as wallpaper, with Save as pictures beside it. */
export function Foot(props: {
  studio: StudioState;
  ready: boolean;
  busy: boolean;
  onSet: () => void;
  onSave: () => void;
  onStop: () => void;
  stopping: boolean;
  problem: string | null;
}) {
  const making = props.studio.making;
  const percent = Math.round((making?.progress ?? 0) * 100);
  const working = making?.state === "waiting" || making?.state === "making";
  return (
    <div className="sticky -bottom-4 -mx-4.5 mt-auto -mb-4 flex flex-col gap-2 bg-surface px-4.5 pt-2 pb-4 before:pointer-events-none before:absolute before:inset-x-0 before:-top-4 before:h-4 before:bg-linear-to-t before:from-surface before:to-transparent">
      {working && making && (
        <div className="flex flex-col gap-1.5">
          <span className="text-13">
            {making.purpose === "save" ? "Making the pictures to save…" : "Making the wallpaper…"}
          </span>
          <div
            role="progressbar"
            aria-label="Making the wallpaper"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-1.5 overflow-hidden rounded-3 bg-track"
          >
            <div
              className="h-full bg-accent transition-[width] duration-320 ease-mado"
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-12 text-fg-muted">
              {making.secondsLeft !== null
                ? `${about(making.secondsLeft)} left`
                : "Working out the time…"}
            </span>
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto"
              disabled={props.stopping}
              onClick={props.onStop}
            >
              Stop
            </Button>
          </div>
        </div>
      )}
      {making?.state === "set" && making.setAt && (
        <p role="status" className="flex items-center gap-2 text-13 text-fg-muted">
          <CheckCircle2 size={15} aria-hidden="true" />
          Set at {clock(making.setAt)}, at exactly each monitor's pixels.
        </p>
      )}
      {making?.state === "saved" && (
        <p role="status" className="flex items-center gap-2 text-13 text-fg-muted">
          <CheckCircle2 size={15} aria-hidden="true" />
          Saved {making.saved.length} {making.saved.length === 1 ? "picture" : "pictures"}
          {making.saved[0]
            ? ` in ${making.saved[0].slice(0, making.saved[0].lastIndexOf("\\"))}`
            : ""}
          .
        </p>
      )}
      {making?.state === "failed" && making.problem && (
        <p role="alert" className="text-13 text-broken-fg leading-normal">
          {making.problem}
        </p>
      )}
      {props.problem && (
        <p role="alert" className="text-13 text-broken-fg leading-normal">
          {props.problem}
        </p>
      )}
      <Button variant="primary" disabled={!props.ready || props.busy} onClick={props.onSet}>
        Set as wallpaper
      </Button>
      <Button disabled={!props.ready || props.busy} onClick={props.onSave}>
        Save as pictures…
      </Button>
      <p className="text-center text-13 text-fg-faint">
        Made into Mado's own folder; your pictures stay as they are.
      </p>
    </div>
  );
}

/** A note in the studio: an icon, what's so, and, when it can go, its cross. */
export function Note(props: { icon: ReactNode; children: ReactNode; onClose?: () => void }) {
  return (
    <p
      role="status"
      className="flex items-start gap-2.5 rounded-8 border border-edge bg-glass px-3.5 py-3 text-13 leading-normal"
    >
      <span className="mt-0.5 shrink-0 text-fg-muted">{props.icon}</span>
      <span className="min-w-0 flex-1">{props.children}</span>
      {props.onClose && (
        <button
          type="button"
          aria-label="Close the note"
          onClick={props.onClose}
          className="press inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-4 text-fg-muted hover:bg-tint/6 hover:text-fg"
        >
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </p>
  );
}

/** No monitors to draw: Mado isn't on Windows' own desktop, or Windows didn't say, and why. */
export function NoMonitors({ studio, onAgain }: { studio: StudioState; onAgain: () => void }) {
  return (
    <section className="flex flex-col items-start gap-2 rounded-8 border border-dash border-dashed bg-surface px-5 py-6">
      <h2 className="font-semibold text-16">
        {studio.desktop
          ? "Windows didn't say what monitors there are"
          : "Mado sets wallpapers on Windows' own desktop"}
      </h2>
      <p className="text-13 text-fg-muted leading-normal">
        {studio.problem ??
          (studio.desktop
            ? "Mado asks again by itself every few seconds. Nothing on your desktop changed."
            : "Mado reads the monitors and sets the wallpaper through Windows, so there's nothing to set here.")}
      </p>
      {studio.desktop && (
        <Button size="sm" onClick={onAgain}>
          Look again
        </Button>
      )}
    </section>
  );
}
