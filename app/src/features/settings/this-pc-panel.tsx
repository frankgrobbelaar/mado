import { READER } from "@/components/raw-reader";
import { Button } from "@/components/ui/button";
import { type Pc, type Tool, useDownloadTool, usePc, useTestPc, useTools } from "@/lib/engine";
import { about, dayAndTime, size } from "@/lib/format";
import { Panel } from "./panel";

const GIB = 1024 ** 3;

/**
 * This PC, in Settings › About: its graphics card, processor and memory, where the AI models run
 * and how long a typical picture takes each way, Fast or Best and which each kind starts on, and
 * testing it again, as Kura's PC check does. Times are this PC's own once it's been tested.
 */
export function ThisPcPanel() {
  const pc = usePc();
  const test = useTestPc();
  const found = pc.data;
  return (
    <Panel
      title="This PC"
      note={found ? summary(found) : "Looking at this PC…"}
      action={
        <Button
          disabled={!found || found.testing || test.isPending}
          onClick={() => test.mutate({ path: "/pc/test" })}
        >
          {found?.testing ? "Testing…" : "Test again"}
        </Button>
      }
    >
      {found && (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-13">
            <dt className="text-fg-muted">Graphics card</dt>
            <dd>
              {found.card ? (
                <>
                  {found.card.name}
                  {found.card.memory ? (
                    <span className="font-mono text-fg-muted">
                      {" "}
                      · {Math.round(found.card.memory / GIB)} GB of its own
                    </span>
                  ) : null}
                </>
              ) : (
                "None Mado can use"
              )}
            </dd>
            <dt className="text-fg-muted">Processor</dt>
            <dd>
              {found.processor ?? "Unknown"}
              {found.cores ? <span className="text-fg-muted"> · {found.cores} cores</span> : null}
            </dd>
            <dt className="text-fg-muted">Memory</dt>
            <dd className="font-mono">
              {found.memory ? `${Math.round(found.memory / GIB)} GB` : "Unknown"}
            </dd>
          </dl>
          <p className="text-13 text-fg-soft leading-normal">{where(found)}</p>
          <table className="w-full text-13">
            <caption className="sr-only">How long a picture takes on this PC</caption>
            <thead>
              <tr className="text-left text-12 text-fg-muted">
                <th scope="col" className="pb-1 font-medium">
                  For
                </th>
                <th scope="col" className="pb-1 font-medium">
                  Fast
                </th>
                <th scope="col" className="pb-1 font-medium">
                  Best
                </th>
              </tr>
            </thead>
            <tbody>
              {(["photo", "drawing"] as const).map((kind) => (
                <tr key={kind} className="border-rule border-t">
                  <th scope="row" className="py-1.5 pr-4 text-left font-medium">
                    {kind === "photo" ? "Photos" : "Drawings"}
                  </th>
                  {(["fast", "best"] as const).map((quality) => {
                    const ability = found.abilities.find(
                      (each) => each.kind === kind && each.quality === quality,
                    );
                    const first = found.startsOn[kind] === quality;
                    return (
                      <td key={quality} className="py-1.5 pr-4">
                        {ability && (
                          <span className="flex flex-col">
                            <span>
                              <span className="font-mono">{about(ability.seconds)}</span>
                              {first && (
                                <span className="ml-2 rounded-full bg-accent/12 px-2 py-0.5 text-12 text-accent-fg">
                                  starts on
                                </span>
                              )}
                            </span>
                            <span className="text-12 text-fg-faint">
                              {ability.model}
                              {ability.download && ", a download"}
                              {ability.pace === "slow" && ", slow here"}
                            </span>
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-12 text-fg-faint">
            Each time is a phone's 12-megapixel photo made for a 4K screen.{" "}
            {found.measured
              ? `Measured on this PC ${found.measured.tested ? "by a test" : "as pictures were made"}, ${dayAndTime(new Date(found.measured.at))}${found.measured.pictures ? `, and by ${found.measured.pictures} ${found.measured.pictures === 1 ? "picture" : "pictures"} made since` : ""}.`
              : "A guess till Mado has timed this PC."}
          </p>
        </>
      )}
      {(pc.isError || test.isError) && (
        <p role="alert" className="text-13 text-broken-fg">
          {(pc.error ?? test.error)?.message}
        </p>
      )}
    </Panel>
  );
}

/**
 * What Mado downloads, in Settings › About: each with where it stands, and fetching it (again)
 * when it's gone missing, ffmpeg and the AI models alike.
 */
export function ToolsPanel() {
  const tools = useTools();
  const download = useDownloadTool();
  return (
    <Panel
      title="What Mado downloads"
      note="Each is checked against the list Mado ships with before it's used."
    >
      <ul className="flex flex-col">
        {tools.data?.map((tool) => (
          <li
            key={tool.id}
            className="flex flex-wrap items-center gap-3 border-rule border-t py-2.5 first:border-t-0"
          >
            <span className="flex min-w-0 flex-[1_1_260px] flex-col gap-0.5">
              <span className="font-semibold text-14">
                {tool.name}{" "}
                <span className="font-mono font-normal text-12 text-fg-muted">{tool.version}</span>
              </span>
              <span className="text-12 text-fg-muted">
                {size(tool.size)} · {tool.licence} · {standing(tool)}
              </span>
              {tool.state === "failed" && tool.problem && (
                <span role="alert" className="text-12 text-broken-fg">
                  {tool.problem}
                </span>
              )}
            </span>
            {(tool.state === "missing" || tool.state === "failed") && (
              <Button
                size="sm"
                disabled={download.isPending}
                onClick={() => download.mutate({ path: `/tools/${tool.id}/download` })}
              >
                {tool.state === "failed"
                  ? "Try again"
                  : tool.when === "setup"
                    ? "Download it again"
                    : "Download"}
              </Button>
            )}
            {(tool.state === "downloading" || tool.state === "unpacking") && (
              <span className="font-mono text-12 text-fg-muted">
                {tool.state === "unpacking"
                  ? "Checking…"
                  : `${Math.round((tool.done / (tool.size || 1)) * 100)}%`}
              </span>
            )}
          </li>
        ))}
      </ul>
      {download.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {download.error.message}
        </p>
      )}
    </Panel>
  );
}

function standing(tool: Tool): string {
  switch (tool.state) {
    case "ready":
      return "ready";
    case "downloading":
      return "downloading";
    case "unpacking":
      return "checking";
    case "failed":
      return "didn't come";
    case "missing":
      if (tool.when === "setup") return "missing: Mado needs it again";
      return tool.id === READER
        ? "fetched the first time Mado reads a camera RAW"
        : "fetched the first time it's asked for";
  }
}

function summary(pc: Pc): string {
  if (pc.testing) return pc.timing ? "Testing and timing this PC…" : "Checking this PC…";
  if (!pc.checkedAt) return "Not tested yet.";
  return `Tested ${dayAndTime(new Date(pc.checkedAt))}.`;
}

function where(pc: Pc): string {
  if (pc.onCard === false) {
    return `The AI models don't run on this PC's graphics card${pc.problem ? ` (${pc.problem.replace(/\.$/, "")})` : ""}, so they run on the processor: slower, and Fast goes first.`;
  }
  if (!pc.card) return "Mado's AI models run on the graphics card when there is one.";
  return "The AI models run on the graphics card, through DirectX 12: a picture in seconds.";
}
