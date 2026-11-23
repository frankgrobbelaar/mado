import { Segmented } from "@/components/ui/segmented";
import { ReadingNote } from "@/features/library/search-results";
import {
  type Settings,
  type Tool,
  useSaveSettings,
  useSearchState,
  useSettings,
} from "@/lib/engine";
import { languages, size } from "@/lib/format";
import { Panel } from "./panel";

const READERS = [
  { value: "auto", label: "As this PC suits" },
  { value: "fast", label: "Fast" },
  { value: "best", label: "Best" },
] as const;

/**
 * Search, in Settings › General, as no board draws it, in the Saving panel's pattern: how far
 * reading the library has got (with Pause), and which reader reads the words in pictures: Fast,
 * Windows' own, with nothing to download; Best, PP-OCRv6, a download; or as this PC suits (Best on
 * a graphics card). Changing it reads the words again in the background.
 */
export function SearchPanel() {
  const settings = useSettings();
  const save = useSaveSettings();
  const state = useSearchState().data;
  const stored = settings.data;
  const change = (part: Partial<Settings>) =>
    stored && save.mutate({ path: "/settings", body: { ...stored, ...part } });
  const words = state?.words;
  const tags = words?.languages ?? [];
  const best = words?.model;
  const describer = state?.describer;
  return (
    <Panel
      title="Search"
      note="Mado reads your library in the background, so a search finds pictures by what they show and by the words in them, as well as by name. It all stays on this PC."
    >
      <div className="flex flex-col gap-1.5">
        <span className="font-semibold text-14">Reading your library</span>
        {state && describer?.state !== "ready" ? (
          <span className="text-13 text-fg-muted">
            Its reader of pictures, SigLIP ({size(describer?.size ?? 0)}), comes the first time you
            search your library, as the installer's first page listed.
          </span>
        ) : (
          state && <ReadingNote state={state} always />
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5 border-rule border-t pt-3">
        <span className="flex min-w-0 flex-[1_1_300px] flex-col gap-0.5">
          <span className="font-semibold text-14">Words in pictures</span>
          <span className="text-13 text-fg-muted">
            {wordsText(stored?.wordsReader ?? "auto", words?.reader ?? "best", tags)}
          </span>
          {best && (
            <span className="font-mono text-12 text-fg-faint">
              Best: PP-OCRv6 small, {size(best.size)}
              {bestState(best)}
              {best.state === "ready" && words?.place === "processor" && ", on the processor"}
            </span>
          )}
        </span>
        <Segmented
          label="Words in pictures"
          value={stored?.wordsReader ?? "auto"}
          options={READERS}
          onChange={(wordsReader) => change({ wordsReader })}
        />
      </div>
      {save.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {save.error.message}
        </p>
      )}
    </Panel>
  );
}

/** Where Best's download has got. */
function bestState(model: Tool): string {
  switch (model.state) {
    case "ready":
      return ", here";
    case "downloading":
    case "unpacking":
      return `, downloading: ${Math.round((model.done / Math.max(model.size, 1)) * 100)}%`;
    case "failed":
      return ", didn't download: a search in the Library has Try again";
    default:
      return ", downloaded when it's first needed";
  }
}

/** What the chosen reader of words does here. */
function wordsText(
  chosen: Settings["wordsReader"],
  reader: "fast" | "best",
  tags: string[],
): string {
  const windows =
    tags.length > 0
      ? `Fast is Windows' own reader: nothing to download, but it reads only the languages Windows has (here ${languages(tags)}).`
      : "Fast is Windows' own reader, but Windows has no language to read words in here.";
  const best =
    "Best reads small print, and Greek, Chinese and Japanese too, whatever languages Windows has.";
  const now =
    chosen === "auto"
      ? ` As this PC suits, that's ${reader === "best" ? "Best" : "Fast"}.`
      : " Changing it reads the words again, in the background.";
  return `${windows} ${best}${now}`;
}
