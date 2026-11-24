import { Download, ImagePlus } from "lucide-react";
import { type KeyboardEvent, useId, useRef, useState } from "react";
import { type Taken, useClaim } from "@/components/shell/claim";
import { useOnline } from "@/components/shell/offline";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { PickCard } from "@/features/wallpaper/pick-card";
import {
  type EditStep,
  type PaintStep,
  type PictureDetails,
  type Plan,
  pictureAddress,
  type Styles,
  styleAddress,
  styleThumbnailAddress,
  type Tool,
  useDeleteStyle,
  useDownloadTool,
  useFixes,
  useKeepStyle,
  usePictureImage,
  useReadStyle,
  useRenameStyle,
  useStyles,
  useTools,
  type YourStyle,
} from "@/lib/engine";
import { size as sizeOf, stem } from "@/lib/format";
import { cn } from "@/lib/utils";
import { classicOf, keepsColours, type PictureStyle, stepFor } from "./painting";

/** A tile of the painting styles' grid: Mado's, the owner's, a picture's, or none. */
interface Choice {
  id: string;
  name: string;
  /** The download its network waits for, as /tools has it; none for one that's here. */
  needs: Tool | null;
  /** Where its small copy comes from. */
  copy: { path: string; body?: unknown } | null;
  /** The small copy of the picture it came from, in its corner: a picture's own style. */
  from: string | null;
}

/**
 * The Looks tab's painting styles, a group of their own beside the looks (no board draws them:
 * they follow the looks' patterns): Mado's painters and classic means and the owner's own styles
 * as small copies of the picture, going through them shows each on the picture, its strength, its
 * colours or the picture's own, a classic one's one setting; a picture of the owner's as the style,
 * read from its colours and textures and kept as a style; and each network downloaded the first
 * time it's asked for. A style is a step of its own, made before the look: a look can still warm
 * or cool what's painted, and the touches go on top of both.
 */
export function StylesSection(props: {
  picture: PictureDetails;
  /** The edits made on the Edit tab, which the small copies show; null for none. */
  edit: EditStep | null;
  paint: PaintStep | null;
  onPaint: (step: PaintStep | null) => void;
  /** A style pointed at, shown on the big picture till the pointer leaves; null when none. */
  onPoint: (step: PaintStep | null) => void;
  /** A picture of the owner's as the style, read but not kept. */
  chosen: PictureStyle | null;
  onChosen: (chosen: PictureStyle | null) => void;
  plan: Plan | null;
}) {
  const { picture, paint, onPaint } = props;
  const styles = useStyles();
  const tools = useTools();
  const [asking, setAsking] = useState(false);
  const [keeping, setKeeping] = useState(false);
  const data = styles.data;
  const classic = paint ? classicOf(paint.style, data) : undefined;
  const reader = tools.data?.find((each) => each.id === data?.reader) ?? null;
  const choices = data ? choicesOf(data, props, tools.data ?? []) : null;
  const shown = paint ? choices?.find((each) => each.id === paint.style) : undefined;
  const mine = data?.yours.find((each) => each.id === paint?.style) ?? null;
  // Black and white, as the Fix tab reads it: asked only once a style is chosen, as it's measured
  // from the whole picture.
  const grey = useFixes(paint && picture.state === "ready" ? picture : null).data?.grey ?? false;

  function pick(choice: Choice) {
    if (choice.id === "none") return onPaint(null);
    const extra =
      choice.id === "picture" && props.chosen
        ? { code: props.chosen.code, named: props.chosen.named }
        : {};
    onPaint(stepFor(choice.id, paint, extra));
  }
  function point(choice: Choice | null) {
    if (!choice || choice.id === "none" || choice.needs) return props.onPoint(null);
    const extra =
      choice.id === "picture" && props.chosen
        ? { code: props.chosen.code, named: props.chosen.named }
        : {};
    props.onPoint(stepFor(choice.id, paint, extra));
  }

  return (
    <section aria-labelledby="styles" className="flex flex-col gap-2">
      <h2 id="styles" className="type-eyebrow">
        Painting styles
      </h2>
      {styles.isError ? (
        <p role="alert" className="text-13 text-broken-fg">
          Mado couldn't list the styles: {styles.error.message}
        </p>
      ) : choices ? (
        <StyleGrid
          choices={choices}
          chosen={paint?.style ?? "none"}
          onPick={pick}
          onPoint={point}
          onPicture={() => setAsking(true)}
        />
      ) : (
        <div role="status" aria-label="Loading the styles" className="grid grid-cols-3 gap-2">
          {["a", "b", "c", "d", "e", "f"].map((place) => (
            <span key={place} className="flex flex-col gap-1">
              <Skeleton className="h-14.5 rounded-4" />
              <Skeleton className="h-3 w-14" />
            </span>
          ))}
        </div>
      )}
      {paint && (
        <div className="flex items-center gap-3 text-13">
          <span>Strength</span>
          <Slider
            label="Style strength"
            value={Math.round(paint.strength * 100)}
            onChange={(value) => onPaint({ ...paint, strength: value / 100 })}
            valueText={`${Math.round(paint.strength * 100)}%`}
          />
          <span className="w-10 text-right font-mono">{Math.round(paint.strength * 100)}%</span>
        </div>
      )}
      {paint && classic?.setting && (
        <div className="flex items-center gap-3 text-13">
          <span className="w-18 text-fg-muted">{classic.setting}</span>
          <Slider
            label={classic.setting}
            value={paint.setting ?? classic.first}
            onChange={(value) => onPaint({ ...paint, setting: value })}
          />
          <span className="w-10 text-right font-mono">{paint.setting ?? classic.first}</span>
        </div>
      )}
      {paint && keepsColours(paint.style, data) && <Colours paint={paint} onPaint={onPaint} />}
      {shown?.needs && <StyleDownload tool={shown.needs} name={shown.name} />}
      {paint?.style === "picture" && props.chosen && (
        <PictureChosen
          key={`${props.chosen.from.id}:${props.chosen.named}:${props.chosen.code}`}
          chosen={props.chosen}
          keeping={keeping}
          onKeep={() => setKeeping(true)}
          onKept={(kept) => {
            setKeeping(false);
            props.onChosen(null);
            onPaint({ ...stepFor(kept.id, paint), strength: paint.strength });
          }}
          onCancel={() => setKeeping(false)}
        />
      )}
      {mine && paint && <YourStyleLine key={mine.id} mine={mine} onGone={() => onPaint(null)} />}
      {paint && grey && !paint.colours && keepsColours(paint.style, data) && (
        <p className="text-12 text-fg-muted leading-normal">
          This picture is black and white: the style paints it in its own colours. Keep the
          picture's colours to keep it black and white.
        </p>
      )}
      {paint && props.plan?.paintNote && (
        <p className="text-12 text-fg-muted leading-normal">{props.plan.paintNote}</p>
      )}
      {paint && props.plan?.paintPlace === "processor" && !classic && !shown?.needs && (
        <p className="text-12 text-fg-faint leading-normal">
          Painted on the processor on this PC: each style takes a few seconds to show.
        </p>
      )}
      {asking && (
        <PictureStyleCard
          picture={picture}
          reader={reader}
          onRead={(chosen) => {
            setAsking(false);
            setKeeping(false);
            props.onChosen(chosen);
            onPaint(stepFor("picture", paint, { code: chosen.code, named: chosen.named }));
          }}
          onClose={() => setAsking(false)}
        />
      )}
    </section>
  );
}

/** Every style as a tile: none first, Mado's painters, the classic means, the owner's own and a
 * picture's not kept yet; each a small copy of the picture in it once its network is here. */
function choicesOf(
  styles: Styles,
  props: { picture: PictureDetails; edit: EditStep | null; chosen: PictureStyle | null },
  tools: Tool[],
): Choice[] {
  const asked = (id: string, body?: unknown) =>
    props.edit || body
      ? {
          path: `/pictures/${props.picture.id}/styles/${id}`,
          body: { edit: props.edit, ...(body ?? {}) },
        }
      : { path: styleAddress(props.picture, id) };
  const need = (download: string | null) => {
    const tool = download ? tools.find((each) => each.id === download) : undefined;
    return tool && tool.state !== "ready" ? tool : null;
  };
  const reader = need(styles.reader);
  const found: Choice[] = [
    {
      id: "none",
      name: "None",
      needs: null,
      copy: { path: pictureAddress(props.picture, "thumbnail") },
      from: null,
    },
    ...[...styles.painters, ...styles.classics].map((style) => {
      const needs = need(style.download);
      return {
        id: style.id,
        name: style.name,
        needs,
        copy: needs ? { path: pictureAddress(props.picture, "thumbnail") } : asked(style.id),
        from: null,
      };
    }),
    ...styles.yours.map((mine) => ({
      id: mine.id,
      name: mine.name,
      needs: reader,
      copy: reader ? { path: pictureAddress(props.picture, "thumbnail") } : asked(mine.id),
      from: styleThumbnailAddress(mine.id),
    })),
  ];
  if (props.chosen) {
    found.push({
      id: "picture",
      name: `${props.chosen.named} style`,
      needs: reader,
      copy: reader
        ? { path: pictureAddress(props.picture, "thumbnail") }
        : asked("picture", { code: props.chosen.code, named: props.chosen.named }),
      from: pictureAddress(props.chosen.from, "thumbnail"),
    });
  }
  return found;
}

/** The styles three to a row, as the looks are: picked by a click or the arrow keys, shown on
 * the big picture while the pointer rests on one; a picture of the owner's as the style last. */
function StyleGrid(props: {
  choices: Choice[];
  chosen: string;
  onPick: (choice: Choice) => void;
  onPoint: (choice: Choice | null) => void;
  onPicture: () => void;
}) {
  const { choices, chosen } = props;
  const tiles = useRef<(HTMLButtonElement | null)[]>([]);
  const at = choices.findIndex((each) => each.id === chosen);

  function move(event: KeyboardEvent<HTMLDivElement>) {
    const steps: Record<string, number> = {
      ArrowRight: 1,
      ArrowLeft: -1,
      ArrowDown: 3,
      ArrowUp: -3,
    };
    const step = steps[event.key];
    const last = choices.length - 1;
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? last
          : step !== undefined
            ? Math.min(Math.max(Math.max(at, 0) + step, 0), last)
            : null;
    const choice = next === null ? undefined : choices[next];
    if (next === null || !choice) return;
    event.preventDefault();
    props.onPick(choice);
    tiles.current[next]?.focus();
  }

  return (
    <div className="grid grid-cols-3 gap-2">
      <div
        role="radiogroup"
        aria-label="Painting styles"
        onKeyDown={move}
        onPointerLeave={() => props.onPoint(null)}
        className="contents"
      >
        {choices.map((choice, index) => (
          <StyleTile
            key={choice.id}
            choice={choice}
            chosen={choice.id === chosen}
            focusable={choice.id === chosen || (at < 0 && index === 0)}
            refTo={(tile) => {
              tiles.current[index] = tile;
            }}
            onPick={() => props.onPick(choice)}
            onPoint={() => props.onPoint(choice)}
          />
        ))}
      </div>
      <button
        type="button"
        onClick={props.onPicture}
        className="press flex min-w-0 cursor-pointer flex-col gap-1 text-left font-medium text-12 text-fg-muted hover:text-fg"
      >
        <span className="grid h-14.5 w-full place-items-center rounded-4 border border-dash border-dashed">
          <ImagePlus size={18} aria-hidden="true" />
        </span>
        <span className="truncate">A picture of yours…</span>
      </button>
    </div>
  );
}

function StyleTile(props: {
  choice: Choice;
  chosen: boolean;
  focusable: boolean;
  refTo: (tile: HTMLButtonElement | null) => void;
  onPick: () => void;
  onPoint: () => void;
}) {
  const { choice, chosen } = props;
  const copy = usePictureImage(choice.copy?.path ?? null, choice.copy?.body);
  const from = usePictureImage(choice.from);
  // A network on its way says how far it's got; one still to fetch, its size.
  const fetching = choice.needs ? fetched(choice.needs) : null;
  return (
    // biome-ignore lint/a11y/useSemanticElements: a radio that is a small copy of the picture, which an input can't hold
    <button
      ref={props.refTo}
      type="button"
      role="radio"
      aria-checked={chosen}
      aria-label={
        choice.needs
          ? fetching === null
            ? `${choice.name}, ${sizeOf(choice.needs.size)} to download`
            : `${choice.name}, downloading, ${fetching}%`
          : choice.name
      }
      tabIndex={props.focusable ? 0 : -1}
      onClick={props.onPick}
      onPointerEnter={props.onPoint}
      className={cn(
        "press flex min-w-0 cursor-pointer flex-col gap-1 text-left text-12",
        chosen ? "font-semibold text-fg" : "font-medium text-fg-muted hover:text-fg",
      )}
    >
      <span
        className={cn(
          "relative block h-14.5 w-full overflow-hidden rounded-4 bg-behind",
          chosen && "outline-2 outline-accent outline-offset-1",
        )}
      >
        {copy.address ? (
          <img
            src={copy.address}
            alt=""
            draggable={false}
            className={cn("size-full animate-fade-in object-cover", choice.needs && "opacity-55")}
          />
        ) : copy.problem ? (
          <span aria-hidden="true" className="status-problem absolute inset-0 opacity-50" />
        ) : (
          <Skeleton className="size-full rounded-4" />
        )}
        {from.address && (
          <img
            src={from.address}
            alt=""
            draggable={false}
            className="absolute top-1 left-1 size-5 rounded-full object-cover ring-1 ring-black/40"
          />
        )}
        {choice.needs && (
          <span
            aria-hidden="true"
            className="absolute right-1 bottom-1 inline-flex items-center gap-1 rounded-4 bg-black/70 px-1.5 py-px font-mono text-11 text-white"
          >
            {fetching === null ? (
              <>
                <Download size={10} />
                {sizeOf(choice.needs.size)}
              </>
            ) : (
              `${fetching}%`
            )}
          </span>
        )}
      </span>
      <span className="truncate">{choice.name}</span>
    </button>
  );
}

/** How far a download on its way has got, in percent; null for one not on its way. */
function fetched(tool: Tool): number | null {
  if (tool.state !== "downloading" && tool.state !== "unpacking") return null;
  return tool.size ? Math.round((tool.done / tool.size) * 100) : 0;
}

/** "Keep the picture's colours": the painting's lightness, the picture's own colour. */
function Colours(props: { paint: PaintStep; onPaint: (step: PaintStep) => void }) {
  const id = useId();
  return (
    <div className="flex items-center gap-2.5 text-13">
      <Switch
        id={id}
        checked={props.paint.colours}
        onCheckedChange={(on) => props.onPaint({ ...props.paint, colours: on })}
      />
      <label htmlFor={id} className="cursor-pointer">
        Keep the picture's colours
      </label>
    </div>
  );
}

/** A style's network to download first: what it is and its size, then how far it's got. */
export function StyleDownload(props: { tool: Tool; name: string; doing?: string }) {
  const { tool } = props;
  const download = useDownloadTool();
  const online = useOnline();
  const busy = tool.state === "downloading" || tool.state === "unpacking";
  const percent = tool.size ? Math.round((tool.done / tool.size) * 100) : 0;
  return (
    <section
      aria-label={`${tool.name} to download`}
      className="flex flex-col gap-2 rounded-6 border border-dash border-dashed p-3"
    >
      <p className="text-13 leading-normal">
        {props.doing ??
          `${props.name} paints with a small AI model Mado downloads the first time it's asked for`}{" "}
        (<span className="font-mono">{sizeOf(tool.size)}</span>). It stays on this PC.
      </p>
      {busy ? (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-12 text-fg-muted">
            {tool.state === "unpacking"
              ? "Checking it…"
              : `Downloading · ${sizeOf(tool.done)} of ${sizeOf(tool.size)} · ${percent}%`}
          </span>
          <div
            role="progressbar"
            aria-label={`Downloading ${tool.name}`}
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
        </div>
      ) : online ? (
        <Button
          size="sm"
          className="self-start"
          disabled={download.isPending}
          onClick={() => download.mutate({ path: `/tools/${tool.id}/download` })}
        >
          {tool.state === "failed" ? "Try again" : `Download ${tool.name}`}
        </Button>
      ) : (
        <p className="text-13 text-fg-muted leading-normal">
          You're offline, so it waits till you're back. Pencil, oil paint and cartoon work now:
          they're drawn by code.
        </p>
      )}
      {tool.state === "failed" && tool.problem && (
        <p role="alert" className="text-12 text-broken-fg">
          {tool.problem}
        </p>
      )}
    </section>
  );
}

/** A picture of the owner's as the style, chosen: where it came from, and "Keep as a style". */
function PictureChosen(props: {
  chosen: PictureStyle;
  keeping: boolean;
  onKeep: () => void;
  onKept: (kept: YourStyle) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(props.chosen.named);
  const keep = useKeepStyle();
  const id = useId();
  return (
    <div className="flex flex-col gap-2">
      <p className="text-12 text-fg-muted leading-normal">
        From {props.chosen.named}'s colours and textures, never what it shows.
      </p>
      {props.keeping ? (
        <form
          className="flex flex-col gap-2 rounded-6 border border-edge bg-glass p-2.5"
          onSubmit={(event) => {
            event.preventDefault();
            keep.mutate(
              {
                path: "/styles",
                body: { name, code: props.chosen.code, picture: props.chosen.from.id },
              },
              { onSuccess: props.onKept },
            );
          }}
        >
          <label htmlFor={id} className="text-12 text-fg-muted">
            Its name
          </label>
          <span className="flex items-center gap-2">
            <Input
              id={id}
              value={name}
              maxLength={60}
              onChange={(event) => setName(event.target.value)}
              className="h-8 text-13"
            />
            <Button size="sm" type="submit" disabled={!name.trim() || keep.isPending}>
              Keep
            </Button>
            <Button size="sm" variant="ghost" type="button" onClick={props.onCancel}>
              Cancel
            </Button>
          </span>
          <p className="text-12 text-fg-faint leading-normal">
            Mado keeps its style and a small copy to know it by, never the picture itself.
          </p>
          {keep.isError && (
            <p role="alert" className="text-12 text-broken-fg">
              {keep.error.message}
            </p>
          )}
        </form>
      ) : (
        <button
          type="button"
          onClick={props.onKeep}
          className="press inline-flex h-8 cursor-pointer items-center self-start rounded-full border border-dash border-dashed px-2.75 font-medium text-13 text-fg-muted hover:bg-tint/6"
        >
          Keep as a style
        </button>
      )}
    </div>
  );
}

/** One of the owner's styles, chosen: where it came from, Rename and Delete. */
function YourStyleLine(props: { mine: YourStyle; onGone: () => void }) {
  const { mine } = props;
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [name, setName] = useState(mine.name);
  const rename = useRenameStyle();
  const id = useId();
  if (renaming) {
    return (
      <form
        className="flex flex-col gap-2 rounded-6 border border-edge bg-glass p-2.5"
        onSubmit={(event) => {
          event.preventDefault();
          rename.mutate(
            { path: `/styles/${mine.id}`, body: { name } },
            { onSuccess: () => setRenaming(false) },
          );
        }}
      >
        <label htmlFor={id} className="text-12 text-fg-muted">
          A new name for {mine.name}
        </label>
        <span className="flex items-center gap-2">
          <Input
            id={id}
            value={name}
            maxLength={60}
            onChange={(event) => setName(event.target.value)}
            className="h-8 text-13"
          />
          <Button size="sm" type="submit" disabled={!name.trim() || rename.isPending}>
            Rename
          </Button>
          <Button size="sm" variant="ghost" type="button" onClick={() => setRenaming(false)}>
            Cancel
          </Button>
        </span>
        {rename.isError && (
          <p role="alert" className="text-12 text-broken-fg">
            {rename.error.message}
          </p>
        )}
      </form>
    );
  }
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-12 text-fg-muted">
      <span className="min-w-0 truncate">From {mine.source}</span>
      <button
        type="button"
        onClick={() => setRenaming(true)}
        className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
      >
        Rename
      </button>
      <button
        type="button"
        onClick={() => setDeleting(true)}
        className="cursor-pointer text-accent-fg underline-offset-3 hover:underline"
      >
        Delete…
      </button>
      {deleting && (
        <DeleteStyle
          mine={mine}
          onClose={() => setDeleting(false)}
          onDeleted={() => {
            setDeleting(false);
            props.onGone();
          }}
        />
      )}
    </p>
  );
}

/** Deleting one of the owner's styles, asked first: pictures painted with it stay as they are. */
function DeleteStyle(props: { mine: YourStyle; onClose: () => void; onDeleted: () => void }) {
  const remove = useDeleteStyle();
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(28rem,calc(100vw-2rem))]">
        <DialogHeader
          title={`Delete ${props.mine.name}?`}
          description="It leaves your styles. Pictures you painted with it stay as they are."
        />
        <DialogBody>
          <p className="text-13 text-fg-muted leading-normal">
            Your {props.mine.source} stays where it is, so you can take its style again.
          </p>
          {remove.isError && (
            <p role="alert" className="text-13 text-broken-fg">
              {remove.error.message}
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
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate({ path: `/styles/${props.mine.id}` }, { onSuccess: props.onDeleted })
              }
            >
              Delete
            </Button>
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * A picture of the owner's as the style: this picture, one picked from the library, or one
 * dropped on the window or pasted while the card is open. Mado reads its colours and textures
 * (never what it shows) with MicroAST, downloaded the first time.
 */
function PictureStyleCard(props: {
  picture: PictureDetails;
  reader: Tool | null;
  onRead: (chosen: PictureStyle) => void;
  onClose: () => void;
}) {
  const read = useReadStyle();
  const [picking, setPicking] = useState(false);
  const waiting = props.reader !== null && props.reader.state !== "ready";

  function take(id: number) {
    if (waiting) return;
    read.mutate(
      { path: `/pictures/${id}/style` },
      {
        onSuccess: (found) =>
          props.onRead({
            code: found.code,
            named: found.named,
            from: { id, version: found.version },
          }),
      },
    );
  }
  useClaim({
    take: (taken: Taken) => take(taken.id),
    title: "Drop it to take its style",
    body: "Mado reads its colours and textures, never what it shows.",
  });

  if (picking) {
    return (
      <PickCard
        title="Pick a picture for its style"
        forWhat="Its colours and textures, never what it shows"
        note="Or drop a picture on the window, or paste one."
        onPick={(chosen) => {
          setPicking(false);
          take(chosen.id);
        }}
        onClose={() => setPicking(false)}
      />
    );
  }
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(32rem,calc(100vw-2rem))]">
        <DialogHeader
          title="A picture as the style"
          description="Mado takes a picture's colours and textures, never what it shows: pick one whose paint, light or texture you'd like on this picture."
        />
        <DialogBody>
          {waiting && props.reader ? (
            <StyleDownload
              tool={props.reader}
              name="MicroAST"
              doing="Reading a picture's style takes MicroAST, a small AI model Mado downloads the first time it's asked for"
            />
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={read.isPending || props.picture.state !== "ready"}
                onClick={() => take(props.picture.id)}
              >
                Use this picture
              </Button>
              <Button size="sm" disabled={read.isPending} onClick={() => setPicking(true)}>
                Pick from your library…
              </Button>
            </div>
          )}
          <p className="text-13 text-fg-muted leading-normal">
            Or drop a picture on the window, or paste one: its style comes here.
          </p>
          {read.isPending && (
            <p role="status" className="text-13 text-fg-muted">
              Reading its style…
            </p>
          )}
          {read.isError && (
            <p role="alert" className="text-13 text-broken-fg leading-normal">
              {read.error.message}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <span className="truncate text-12 text-fg-faint">On {stem(props.picture.name)}</span>
          <Button variant="ghost" size="sm" onClick={props.onClose}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
