import { useState } from "react";
import { Arrow } from "@/components/arrow";
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogHeader } from "@/components/ui/dialog";
import { Segmented } from "@/components/ui/segmented";
import { type Zoom, Zoomed } from "@/features/picture/stage";
import { type Sample, type Samples, sampleAddress, usePictureImage } from "@/lib/engine";
import { count, size, stem } from "@/lib/format";

const ZOOMS = [
  { value: "fit", label: "Fit" },
  { value: "100", label: "100%" },
  { value: "400", label: "400%" },
] as const;

/**
 * See it first, as the Batch board draws it: three of the pictures made in full but not saved,
 * each before and after with a line between them and its size before and after; "Try three
 * others"; and one opened to look closely, at 100% or 400%.
 */
export function SeeFirst(props: {
  samples: Samples | undefined;
  total: number;
  asking: boolean;
  problem: string | null;
  onOthers: () => void;
  /** No steps: they're saved as they are, so there's nothing to see first. */
  asIs?: boolean;
}) {
  const { samples } = props;
  const [open, setOpen] = useState<Sample | null>(null);
  const made = samples?.samples ?? [];
  return (
    <section
      aria-labelledby="see-first"
      className="flex animate-fade-up flex-col gap-3 rounded-8 border border-edge bg-glass px-4.5 pt-3.5 pb-4"
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
        <h2 id="see-first" className="type-eyebrow">
          See it first
        </h2>
        <span className="text-13 text-fg-muted">
          {props.asIs ? (
            "Saved as they are, there's nothing to see first: each one's copy is the picture itself, in the format chosen."
          ) : made.length === 0 ? (
            "Three of them are made in full, not saved, once there's something to make."
          ) : samples?.seconds != null ? (
            <>
              {made.length === props.total ? "All" : "Three"} of the {count(props.total)}, made in{" "}
              <span className="font-mono text-fg">{took(samples.seconds)}</span>
            </>
          ) : (
            `Making ${made.length === props.total ? "them" : `three of the ${count(props.total)}`}, one at a time…`
          )}
        </span>
      </div>
      {props.problem && (
        <p role="alert" className="text-13 text-broken-fg">
          {props.problem}
        </p>
      )}
      {made.length > 0 && samples && (
        <div className="grid grid-cols-1 gap-3 standard:grid-cols-3">
          {made.map((sample) => (
            <Figure
              key={`${samples.id}-${sample.index}`}
              set={samples.id}
              sample={sample}
              onOpen={() => setOpen(sample)}
            />
          ))}
        </div>
      )}
      {!props.asIs && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            className="bg-transparent font-medium"
            disabled={props.asking || made.length === 0 || props.total <= made.length}
            onClick={props.onOthers}
          >
            Try three others
          </Button>
          <span className="text-13 text-fg-muted">Open one to look closely, at 100% or 400%.</span>
        </div>
      )}
      {open && samples && <Closer set={samples.id} sample={open} onClose={() => setOpen(null)} />}
    </section>
  );
}

/** One picture seen first: before and after, a line between them, its sizes under it. */
function Figure(props: { set: string; sample: Sample; onOpen: () => void }) {
  const { sample } = props;
  const done = sample.state === "done";
  const before = usePictureImage(done ? sampleAddress(props.set, sample.index, "before") : null);
  const after = usePictureImage(done ? sampleAddress(props.set, sample.index, "after") : null);
  const name = stem(sample.name);
  return (
    <figure className="m-0 flex min-w-0 flex-col gap-1.5">
      <button
        type="button"
        disabled={!done}
        onClick={props.onOpen}
        aria-label={`Look closely at ${name}`}
        className="press relative h-29.5 cursor-pointer overflow-hidden rounded-4 bg-behind disabled:cursor-default"
      >
        {done && before.address && after.address ? (
          <>
            <img
              src={before.address}
              alt=""
              draggable={false}
              className="absolute inset-0 size-full animate-fade-in object-cover"
            />
            <img
              src={after.address}
              alt=""
              draggable={false}
              className="absolute inset-0 size-full animate-fade-in object-cover [clip-path:inset(0_0_0_50%)]"
            />
            <span
              aria-hidden="true"
              className="absolute inset-y-0 left-1/2 -ml-px w-0.5 bg-white"
            />
          </>
        ) : sample.state === "failed" ? (
          <span className="flex size-full flex-col items-center justify-center gap-1.5 bg-surface px-3 text-center text-12 text-fg-muted">
            <span aria-hidden="true" className="status-problem size-3 rounded-2" />
            Didn't work
          </span>
        ) : (
          <span role="status" className="absolute inset-0">
            <Skeleton className="size-full rounded-4" />
            <span className="absolute inset-x-0 bottom-2 text-center font-mono text-11 text-fg-muted">
              {sample.state === "making"
                ? `Making · ${Math.round(sample.progress * 100)}%`
                : "Waiting"}
            </span>
          </span>
        )}
      </button>
      <figcaption className="flex min-w-0 justify-between gap-2 text-12">
        <span className="truncate">{name}</span>
        <span className="shrink-0 font-mono text-fg-muted">
          {size(sample.bytes)}
          {sample.madeBytes !== null && (
            <>
              {" "}
              <Arrow said="to" /> {size(sample.madeBytes)}
            </>
          )}
        </span>
      </figcaption>
      {sample.problem && <p className="text-12 text-broken-fg leading-normal">{sample.problem}</p>}
    </figure>
  );
}

/** One picture seen first, as it was made, to look closely at: fitted, or at 100% or 400%. */
function Closer(props: { set: string; sample: Sample; onClose: () => void }) {
  const { sample } = props;
  const [zoom, setZoom] = useState<Zoom>("fit");
  const full = usePictureImage(sampleAddress(props.set, sample.index, "full"));
  const name = stem(sample.name);
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="h-[min(48rem,calc(100vh-3.25rem-6vh-2rem))] w-[min(72rem,calc(100vw-2rem))]">
        <DialogHeader
          title={name}
          description={
            sample.width && sample.height ? (
              <span className="font-mono">
                {sample.width} × {sample.height}
                {sample.madeBytes !== null && ` · ${size(sample.madeBytes)}`}
                {sample.seconds !== null && ` · made in ${took(sample.seconds)}`}
              </span>
            ) : (
              "As it would be saved"
            )
          }
        />
        <DialogBody className="gap-3">
          <Segmented
            label="Zoom"
            value={zoom}
            options={ZOOMS}
            onChange={setZoom}
            className="self-start"
          />
          {full.problem && (
            <p role="alert" className="text-13 text-broken-fg">
              {full.problem}
            </p>
          )}
          {zoom === "fit" ? (
            <div className="relative min-h-60 flex-1 overflow-hidden rounded-6 bg-behind">
              {full.address && (
                <img
                  src={full.address}
                  alt={name}
                  draggable={false}
                  className="absolute inset-0 size-full animate-fade-in object-contain"
                />
              )}
            </div>
          ) : (
            <Zoomed
              address={full.address}
              name={name}
              width={sample.width ?? 0}
              height={sample.height ?? 0}
              scale={zoom === "100" ? 1 : 4}
              whole={full.address !== null}
            />
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

/** How long something took: "1 min 50 s", "12 s". */
export function took(seconds: number): string {
  const whole = Math.max(1, Math.round(seconds));
  if (whole < 60) return `${whole} s`;
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}
