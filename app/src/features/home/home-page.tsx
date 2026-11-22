import { Navigate } from "react-router";
import { EmptyState, WindowIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, PanelSkeleton } from "@/components/skeleton";
import { useEngine, useSettings } from "@/lib/engine";

/** Home: for now, Mado's first window, saying honestly that Mado is being built. Until setup is
 * done, it leads there. */
export function HomePage() {
  const engine = useEngine();
  const settings = useSettings();

  if (settings.data && !settings.data.setUp) return <Navigate to="/setup" replace />;

  return (
    <>
      <header className="page-top flex animate-fade-up flex-col gap-1.5">
        <h1 className="type-title">Home</h1>
        <p className="text-14 text-fg-muted">窓, a window on your pictures.</p>
      </header>

      <EngineProblem queries={[settings]} />
      {!settings.data && (
        <Loading label="Loading Home" queries={[settings]}>
          <PanelSkeleton rows={2} />
        </Loading>
      )}
      {engine.state !== "failed" && settings.data && (
        <EmptyState title="Mado is being built" illustration={<WindowIllustration />}>
          This is Mado's first window. Your pictures come here once Mado can read your folders;
          until then it changes nothing on this PC.
        </EmptyState>
      )}
    </>
  );
}
