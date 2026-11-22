import { useId } from "react";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { pickFolder } from "@/lib/dialogs";
import { type Settings, useSaveSettings, useSettings } from "@/lib/engine";
import { split } from "@/lib/format";
import { Panel } from "./panel";

const FIRST = [
  { value: "new", label: "A new picture" },
  { value: "replace", label: "Replace the original" },
] as const;

const WHERE = [
  { value: "beside", label: "Beside the original" },
  { value: "folder", label: "In a folder…" },
] as const;

/** Saving, as Settings-General draws it: what Save offers first, where new pictures go, and
 * whether they keep where a picture was taken. Save still asks each time. */
export function SavingPanel() {
  const settings = useSettings();
  const save = useSaveSettings();
  const place = useId();
  const stored = settings.data;
  const change = (part: Partial<Settings>) =>
    stored && save.mutate({ path: "/settings", body: { ...stored, ...part } });

  async function chooseWhere(where: "beside" | "folder") {
    if (where === "beside") return change({ newPictures: "beside" });
    const chosen = await pickFolder("Where should new pictures go?");
    if (chosen) change({ newPictures: "folder", newFolder: chosen });
  }

  return (
    <Panel title="Saving">
      <Row
        title="What Save offers first"
        text="Mado still asks each time; this is the choice it starts on."
      >
        <Segmented
          label="What Save offers first"
          value={stored?.saveFirst ?? "new"}
          options={FIRST}
          onChange={(saveFirst) => change({ saveFirst })}
        />
      </Row>
      <Row
        title="Where new pictures go"
        text={
          stored?.newPictures === "folder" && stored.newFolder ? (
            <>
              Into <span className="font-mono text-fg">{stored.newFolder}</span>, named after the
              original with what was made.
            </>
          ) : (
            <>
              Named after the original, with what was made:{" "}
              <span className="font-mono text-fg">Beach (4K).jpg</span>
            </>
          )
        }
      >
        <Segmented
          label="Where new pictures go"
          value={stored?.newPictures === "folder" && stored.newFolder ? "folder" : "beside"}
          options={
            stored?.newFolder
              ? [WHERE[0], { value: "folder", label: split(stored.newFolder)[0] || "In a folder…" }]
              : WHERE
          }
          onChange={(where) => void chooseWhere(where)}
        />
      </Row>
      <div className="flex items-center gap-3.5 border-rule border-t pt-3">
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <label htmlFor={place} className="cursor-pointer font-semibold text-14">
            Keep where a picture was taken
          </label>
          <span className="text-13 text-fg-muted">
            Off, new pictures leave the location out, so it doesn't travel when you share them.
          </span>
        </span>
        <Switch
          id={place}
          checked={stored?.keepLocation ?? false}
          onCheckedChange={(keepLocation) => change({ keepLocation })}
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

/** Many at once, in Settings › General: whether a watch folder's big batch waits for the night. */
export function ManyAtOncePanel() {
  const settings = useSettings();
  const save = useSaveSettings();
  const nights = useId();
  const stored = settings.data;
  return (
    <Panel title="Many at once">
      <div className="flex items-center gap-3.5">
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <label htmlFor={nights} className="cursor-pointer font-semibold text-14">
            Big batches wait for the night
          </label>
          <span className="text-13 text-fg-muted">
            A watch folder that finds more than 20 new pictures makes them from 23:00, so the
            graphics card is free by day.
          </span>
        </span>
        <Switch
          id={nights}
          checked={stored?.bigBatchesAtNight ?? false}
          disabled={!stored}
          onCheckedChange={(bigBatchesAtNight) =>
            stored && save.mutate({ path: "/settings", body: { ...stored, bigBatchesAtNight } })
          }
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

function Row(props: { title: string; text: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5 border-rule border-t pt-3 first-of-type:border-t-0 first-of-type:pt-0">
      <span className="flex min-w-0 flex-[1_1_300px] flex-col gap-0.5">
        <span className="font-semibold text-14">{props.title}</span>
        <span className="text-13 text-fg-muted">{props.text}</span>
      </span>
      {props.children}
    </div>
  );
}
