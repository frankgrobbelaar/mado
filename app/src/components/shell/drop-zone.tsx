import { Upload, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useOpenPictures } from "@/features/batch/open";
import { useDroppedFiles } from "@/lib/drop";

/**
 * Pictures dropped anywhere on the window: while they're over it, the window says what dropping
 * does; dropped, one picture in the library opens its page, and anything else Many at once. What
 * isn't a picture Mado makes is said in a note at the window's foot.
 */
export function DropZone() {
  const opening = useOpenPictures();
  const { open } = opening;
  const { over } = useDroppedFiles((paths) => open(paths, "dropped"));
  const [said, setSaid] = useState<string | null>(null);

  useEffect(() => {
    if (opening.problem) setSaid(opening.problem);
  }, [opening.problem]);

  return (
    <>
      {over && (
        <div
          role="status"
          className="pointer-events-none fixed inset-3 z-50 flex animate-fade-in flex-col items-center justify-center gap-3 rounded-10 border-2 border-dash border-dashed bg-window/85"
        >
          <span className="flex size-14 items-center justify-center rounded-10 bg-raised">
            <Upload size={22} strokeWidth={1.7} aria-hidden="true" />
          </span>
          <span className="font-semibold text-20">Drop them here</span>
          <span className="text-14 text-fg-muted">
            One picture from your library opens its page; any others open Many at once.
          </span>
        </div>
      )}
      {said && (
        <div
          role="alert"
          className="pointer-events-auto fixed bottom-12 left-1/2 z-50 flex w-[min(30rem,calc(100vw-3rem))] -translate-x-1/2 animate-fade-up items-start gap-3 rounded-8 border border-edge bg-dialog px-4 py-3 shadow-toast"
        >
          <span className="flex-1 text-13 leading-normal">{said}</span>
          <button
            type="button"
            aria-label="Close"
            onClick={() => setSaid(null)}
            className="press -mt-1 -mr-1 inline-flex size-7 cursor-pointer items-center justify-center rounded-full text-fg-muted hover:bg-tint/8 hover:text-fg"
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      )}
    </>
  );
}
