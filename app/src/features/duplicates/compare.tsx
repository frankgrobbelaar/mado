import { type RefObject, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Segmented } from "@/components/ui/segmented";
import { Zoomed } from "@/features/picture/stage";
import {
  type DuplicateGroup,
  type GroupPicture,
  pictureAddress,
  usePictureImage,
} from "@/lib/engine";
import { size, stem, takenOn } from "@/lib/format";
import { folderWords } from "./group-card";

type Zoom = "fit" | "100";

/**
 * A picture of a group opened big beside the one kept, at Fit (each whole) or 100% (every pixel,
 * the two moving together as either is dragged or scrolled), with what tells them apart under
 * each. From here it can be kept instead, or as well.
 */
export function Compare(props: {
  group: DuplicateGroup;
  picture: GroupPicture;
  busy: boolean;
  onKeep: (ids: number[]) => void;
  onClose: () => void;
}) {
  const { group } = props;
  const picture = group.pictures.find((each) => each.id === props.picture.id) ?? props.picture;
  const kept = group.pictures.filter((each) => each.keep);
  // Beside the one kept; the one kept itself, beside the first that isn't.
  const beside =
    kept.find((each) => each.id !== picture.id) ??
    group.pictures.find((each) => each.id !== picture.id) ??
    picture;
  const [zoom, setZoom] = useState<Zoom>("fit");
  const left = useRef<HTMLDivElement>(null);
  const right = useRef<HTMLDivElement>(null);
  // The side moved to follow the other, a moment ago: its own scroll then isn't the owner's.
  const followed = useRef<{ side: HTMLDivElement | null; until: number }>({ side: null, until: 0 });

  // At 100% the two show the same part: one scrolled, the other follows, by how far along it is.
  function follow(from: RefObject<HTMLDivElement | null>, to: RefObject<HTMLDivElement | null>) {
    const a = from.current;
    const b = to.current;
    if (!a || !b) return;
    if (followed.current.side === a && performance.now() < followed.current.until) return;
    const across =
      a.scrollWidth > a.clientWidth ? a.scrollLeft / (a.scrollWidth - a.clientWidth) : 0;
    const down =
      a.scrollHeight > a.clientHeight ? a.scrollTop / (a.scrollHeight - a.clientHeight) : 0;
    followed.current = { side: b, until: performance.now() + 80 };
    b.scrollLeft = across * (b.scrollWidth - b.clientWidth);
    b.scrollTop = down * (b.scrollHeight - b.clientHeight);
  }

  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(76rem,calc(100vw-2rem))]">
        <DialogHeader
          title={
            picture.id === beside.id ? (
              <span className="font-mono">{picture.name}</span>
            ) : (
              <>
                <span className="font-mono font-medium">{picture.name}</span> beside{" "}
                <span className="font-mono font-medium">{beside.name}</span>
              </>
            )
          }
          description="Fit shows each whole; 100% shows every pixel, and the two move together as you drag either."
        />
        <DialogBody>
          <Segmented
            label="Zoom"
            value={zoom}
            onChange={setZoom}
            className="self-start"
            options={[
              { value: "fit", label: "Fit" },
              { value: "100", label: "100%" },
            ]}
          />
          <div className="grid min-h-0 grid-cols-1 gap-4 standard:grid-cols-2">
            <Side
              picture={picture}
              zoom={zoom}
              burst={group.kind === "burst"}
              area={left}
              onScroll={() => follow(left, right)}
            />
            {beside.id !== picture.id && (
              <Side
                picture={beside}
                zoom={zoom}
                burst={group.kind === "burst"}
                area={right}
                onScroll={() => follow(right, left)}
              />
            )}
          </div>
        </DialogBody>
        <DialogFooter>
          <span className="px-2 text-13 text-fg-muted">
            {picture.keep ? "Kept." : `Set aside with the rest, unless you keep it.`}
          </span>
          <span className="flex gap-2">
            {!picture.keep && (
              <Button
                disabled={props.busy}
                onClick={() => props.onKeep([...kept.map((each) => each.id), picture.id])}
              >
                Keep both
              </Button>
            )}
            {!picture.keep && (
              <Button
                variant="primary"
                disabled={props.busy}
                onClick={() => {
                  props.onKeep([picture.id]);
                  props.onClose();
                }}
              >
                Keep this one instead
              </Button>
            )}
            {picture.keep && (
              <Button variant="primary" onClick={props.onClose}>
                Done
              </Button>
            )}
          </span>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** One picture of the two: whether it's kept, the picture, and its size, pixels, folder and
 * when it was taken. */
function Side(props: {
  picture: GroupPicture;
  zoom: Zoom;
  /** A burst's shots are told apart by their seconds. */
  burst: boolean;
  area: RefObject<HTMLDivElement | null>;
  onScroll: () => void;
}) {
  const { picture } = props;
  const view = usePictureImage(pictureAddress(picture, "view"));
  const full = usePictureImage(props.zoom === "fit" ? null : pictureAddress(picture, "full"));
  return (
    <figure className="m-0 flex min-w-0 flex-col gap-2">
      <figcaption className="flex items-baseline gap-2 text-13">
        <span className={picture.keep ? "font-semibold text-accent-fg" : "font-semibold"}>
          {picture.keep ? "Kept" : "Set aside"}
        </span>
        <span className="truncate font-mono text-fg-muted" title={picture.path}>
          {picture.name}
        </span>
      </figcaption>
      <div className="flex h-[52vh] min-h-60 flex-col">
        {props.zoom === "fit" ? (
          <div className="relative flex-1 overflow-hidden rounded-6 bg-behind">
            {view.address && (
              <img
                src={view.address}
                alt={stem(picture.name)}
                draggable={false}
                className="absolute inset-0 size-full animate-fade-in object-contain"
              />
            )}
            {view.problem && (
              <p role="alert" className="absolute inset-x-3 top-3 text-13 text-broken-fg">
                {view.problem}
              </p>
            )}
          </div>
        ) : (
          <Zoomed
            address={full.address ?? view.address}
            name={stem(picture.name)}
            width={picture.width}
            height={picture.height}
            scale={1}
            whole={full.address !== null}
            area={props.area}
            onScroll={props.onScroll}
          />
        )}
      </div>
      <span className="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-12 text-fg-muted">
        <span>
          {picture.width} × {picture.height}
        </span>
        <span>{size(picture.size)}</span>
        <span className="font-sans" title={picture.folder}>
          {folderWords(picture.folder)}
        </span>
        <span>
          {props.burst
            ? `${takenOn(picture.takenAt)}:${picture.takenAt.slice(17, 19)}`
            : takenOn(picture.takenAt)}
        </span>
      </span>
    </figure>
  );
}
