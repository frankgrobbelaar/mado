import { Check } from "lucide-react";
import { useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { type Tool, useDownloadTool, useSaveSettings, useSettings, useTools } from "@/lib/engine";
import { Footer, Panel } from "./parts";

/** The tools Mado fetches once, checked against the list it ships with; then setup is done. */
export function ToolsStep() {
  const tools = useTools();
  const stored = useSettings();
  const save = useSaveSettings();
  const navigate = useNavigate();
  // What's fetched the first time it's asked for comes then, not now.
  const needed = tools.data?.filter((tool) => tool.when === "setup");
  const ready = needed?.every((tool) => tool.state === "ready") ?? false;

  function finish() {
    if (!stored.data) return;
    save.mutate(
      { path: "/settings", body: { ...stored.data, setUp: true } },
      { onSuccess: () => void navigate("/", { replace: true }) },
    );
  }

  return (
    <Panel
      title="Tools"
      labelledBy="tools-title"
      intro="Mado fetches ffmpeg once and checks it against the list it ships with, before using it."
    >
      <ul className="flex flex-col gap-3">
        {needed?.map((tool) => (
          <li key={tool.id}>
            <ToolRow tool={tool} />
          </li>
        ))}
      </ul>
      {save.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          Setup couldn't finish: {save.error.message}
        </p>
      )}
      <Footer note="The installer's first page lists everything Mado downloads.">
        <Button variant="primary" disabled={!ready || save.isPending} onClick={finish}>
          Finish
        </Button>
      </Footer>
    </Panel>
  );
}

function ToolRow({ tool }: { tool: Tool }) {
  const download = useDownloadTool();
  const busy = tool.state === "downloading" || tool.state === "unpacking";
  const percent = tool.size ? Math.round((tool.done / tool.size) * 100) : 0;

  return (
    <div className="flex flex-col gap-3 rounded-8 border border-edge bg-glass px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-0.5">
          <span className="font-semibold text-15">
            {tool.name} <span className="font-normal text-fg-muted">{tool.version}</span>
          </span>
          <span className="text-13 text-fg-muted">{tool.purpose}</span>
          <span className="font-mono text-11 text-fg-faint">
            {megabytes(tool.size)} · {tool.licence}
          </span>
        </div>
        {tool.state === "ready" && (
          <span className="inline-flex items-center gap-2 font-semibold text-13 text-accent-fg">
            <Check size={16} strokeWidth={3} aria-hidden="true" />
            Ready
          </span>
        )}
        {(tool.state === "missing" || tool.state === "failed") && (
          <Button
            variant={tool.state === "missing" ? "primary" : "secondary"}
            disabled={download.isPending}
            onClick={() => download.mutate({ path: `/tools/${tool.id}/download` })}
          >
            {tool.state === "missing" ? "Download" : "Try again"}
          </Button>
        )}
        {busy && (
          <span className="font-mono text-12 text-fg-muted">
            {tool.state === "unpacking" ? "Unpacking…" : `${percent}%`}
          </span>
        )}
      </div>
      {busy && (
        <div
          role="progressbar"
          aria-label={`Downloading ${tool.name}`}
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-1.5 overflow-hidden rounded-3 bg-track"
        >
          <div
            className="h-full rounded-3 bg-accent transition-[width] duration-320 ease-mado"
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      {tool.state === "failed" && tool.problem && (
        <p role="alert" className="text-13 text-broken-fg">
          {tool.problem}
        </p>
      )}
    </div>
  );
}

function megabytes(bytes: number): string {
  return `${Math.round(bytes / 1e6)} MB`;
}
