import type { PictureDetails } from "@/lib/engine";
import { size, split, takenOn } from "@/lib/format";

const ORIENTATIONS: Record<number, string> = {
  1: "As taken",
  2: "Mirrored",
  3: "Turned half round",
  4: "Mirrored upside down",
  5: "Mirrored and turned",
  6: "Turned a quarter clockwise",
  7: "Mirrored and turned",
  8: "Turned a quarter anticlockwise",
};

/**
 * The column beside the picture where its tools go: Size, Looks and Edit come in Mado's next
 * pieces, so for now it says so quietly, under them what Mado read of the picture.
 */
export function ToolsColumn({ picture }: { picture: PictureDetails }) {
  const megapixels =
    picture.width && picture.height ? (picture.width * picture.height) / 1e6 : null;
  return (
    <aside
      aria-label="Tools"
      className="sticky top-0 flex h-[calc(100vh-4.25rem)] w-90 shrink-0 flex-col gap-3.5 overflow-y-auto border-chrome-edge border-l bg-surface px-4.5 pt-3.5 pb-4"
    >
      <div aria-hidden="true" className="flex rounded-6 bg-well p-0.75">
        {["Size", "Looks", "Edit"].map((tool) => (
          <span
            key={tool}
            className="flex h-8 flex-1 items-center justify-center rounded-4 font-medium text-13 text-fg-faint"
          >
            {tool}
          </span>
        ))}
      </div>
      <section aria-labelledby="coming" className="flex flex-col gap-2">
        <h2 id="coming" className="type-eyebrow">
          Coming next
        </h2>
        <p className="text-13 text-fg-muted leading-normal">
          Size, Looks and Edit arrive here in Mado's next pieces: this picture made right for any
          screen or print, given a look, or edited with a click. Nothing here changes it.
        </p>
      </section>
      <section aria-labelledby="details" className="flex flex-col gap-2">
        <h2 id="details" className="type-eyebrow">
          Details
        </h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-13">
          <dt className="text-fg-muted">Taken</dt>
          <dd>
            <span className="font-mono">{takenOn(picture.takenAt)}</span>
            <span className="block text-12 text-fg-faint">
              {picture.takenFrom === "camera"
                ? "By the camera's clock"
                : "The file's time: the picture doesn't say"}
            </span>
          </dd>
          {picture.camera && (
            <>
              <dt className="text-fg-muted">Camera</dt>
              <dd>{picture.camera}</dd>
            </>
          )}
          {picture.width && picture.height && (
            <>
              <dt className="text-fg-muted">Size</dt>
              <dd className="font-mono">
                {picture.width} × {picture.height}
                {megapixels !== null && (
                  <span className="text-fg-faint"> · {megapixels.toFixed(1)} MP</span>
                )}
              </dd>
            </>
          )}
          <dt className="text-fg-muted">File</dt>
          <dd className="font-mono">
            {picture.format ?? "?"} · {size(picture.size)}
          </dd>
          {picture.orientation && picture.orientation !== 1 && (
            <>
              <dt className="text-fg-muted">Turned</dt>
              <dd>{ORIENTATIONS[picture.orientation] ?? "As taken"}</dd>
            </>
          )}
          <dt className="text-fg-muted">Place</dt>
          <dd>{picture.located ? "It carries where it was taken" : "It doesn't say"}</dd>
          <dt className="text-fg-muted">Folder</dt>
          <dd className="font-mono text-12 [overflow-wrap:anywhere]">{split(picture.path)[1]}</dd>
        </dl>
      </section>
    </aside>
  );
}
