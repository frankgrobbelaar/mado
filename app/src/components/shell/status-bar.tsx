import { useEngine, useHealth } from "@/lib/engine";
import { cn } from "@/lib/utils";

const STATES = { starting: "Starting", ready: "Ready", failed: "Stopped" } as const;

/** The line of facts at the window's foot: how Mado's engine is, Mado's version, and where your
 * pictures stay. */
export function StatusBar() {
  const engine = useEngine();
  const version = useHealth().data?.version;
  return (
    <footer className="flex h-8 shrink-0 items-center gap-4 border-chrome-edge border-t bg-statusbar px-4 font-mono text-12 text-fg-muted">
      <span className="inline-flex items-center gap-2">
        <span
          aria-hidden="true"
          className={cn(
            "size-1.5 rounded-full",
            engine.state === "ready" && "bg-accent",
            engine.state === "failed" && "bg-danger",
            engine.state === "starting" && "status-working",
          )}
        />
        {STATES[engine.state]}
      </span>
      {version && <span>Mado {version}</span>}
      <span className="ml-auto truncate">Your pictures stay on this PC</span>
    </footer>
  );
}
