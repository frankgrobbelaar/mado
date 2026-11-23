import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { type Tool, useDownloadTool, useTools } from "@/lib/engine";
import { size } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Mado's camera RAW reader in its list of downloads (engine/src/mado/downloads.json). */
export const READER = "libraw";

/** Mado's camera RAW reader, LibRaw, as its downloads have it: on its way, failed, or there. */
export function useRawReader(): Tool | undefined {
  return useTools().data?.find((tool) => tool.id === READER);
}

/** Whether the reader is on its way now. */
export function coming(tool: Tool | undefined): boolean {
  return tool?.state === "downloading" || tool?.state === "unpacking";
}

/** How far the reader's download has got, as a whole percentage. */
export function percentOf(tool: Tool | undefined): number {
  return tool?.size ? Math.round((tool.done / tool.size) * 100) : 0;
}

/** Runs `onReady` once the reader has come, having been on its way or missing. */
export function useWhenReaderComes(tool: Tool | undefined, onReady: () => void) {
  const was = useRef(tool?.state);
  useEffect(() => {
    const now = tool?.state;
    if (now === "ready" && was.current !== undefined && was.current !== "ready") onReady();
    was.current = now;
  }, [tool?.state, onReady]);
}

/**
 * Mado's RAW reader on its way, as the Size tab shows a model's download: what it is, how big, and
 * its progress; or why it didn't come (offline, or not the file the list names), with Try again.
 * Mado fetches it by itself the first time it reads a RAW; "Get it now" asks again at once.
 */
export function RawReaderNote(props: { tool: Tool | undefined; className?: string }) {
  const download = useDownloadTool();
  const { tool } = props;
  const percent = percentOf(tool);
  const weight = tool?.size ? ` (${size(tool.size)})` : "";
  return (
    <section
      aria-label="Mado's RAW reader"
      className={cn(
        "flex flex-col gap-2 rounded-6 border border-dash border-dashed p-3",
        props.className,
      )}
    >
      <p className="text-13 leading-normal">
        {tool?.state === "failed"
          ? `Mado couldn't get its camera RAW reader, LibRaw${weight}.`
          : `Camera RAW is read by LibRaw${weight}, which Mado downloads the first time it reads one, as the installer's first page listed.`}
      </p>
      {coming(tool) ? (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-12 text-fg-muted">
            {tool?.state === "unpacking" ? "Checking it…" : `Downloading · ${percent}%`}
          </span>
          <div
            role="progressbar"
            aria-label="Downloading Mado's RAW reader"
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
      ) : (
        tool?.state !== "ready" && (
          <span className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={download.isPending || !tool}
              onClick={() => download.mutate({ path: `/tools/${READER}/download` })}
            >
              {tool?.state === "failed" ? "Try again" : "Get it now"}
            </Button>
          </span>
        )
      )}
      {tool?.state === "failed" && tool.problem && (
        <p role="alert" className="text-12 text-broken-fg">
          {tool.problem}
        </p>
      )}
    </section>
  );
}
