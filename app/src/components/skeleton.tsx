import type { ReactNode } from "react";
import { useEngine } from "@/lib/engine";
import { cn } from "@/lib/utils";

/**
 * A shape standing in for what's loading, the size and place of what comes: a page shows its
 * layout at once and fills in. Drawn in the progress tracks' grey, breathing gently, and still
 * when Windows' animation effects are off.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span aria-hidden="true" className={cn("block animate-pulse rounded-6 bg-track", className)} />
  );
}

/** A page's skeletons while its `queries` load, said to screen readers as the page loading.
 * Gone once the engine is down or a query failed: EngineProblem says what happened instead. */
export function Loading(props: {
  label: string;
  queries: { isError: boolean }[];
  children: ReactNode;
}) {
  const engine = useEngine();
  if (engine.state === "failed" || props.queries.some((query) => query.isError)) return null;
  const { label, children } = props;
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-8">
      {children}
    </div>
  );
}

/** A glass panel with a heading and rows. */
export function PanelSkeleton({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-3.5 rounded-22 border border-edge bg-glass p-5 shadow-panel",
        className,
      )}
    >
      <Skeleton className="h-4 w-36" />
      <div className="flex flex-col">
        {places(rows).map((place) => (
          <div
            key={place}
            className="flex min-h-11 items-center gap-3 border-rule border-b last:border-b-0"
          >
            <Skeleton className="h-3 w-16 shrink-0" />
            <Skeleton className="h-3 flex-1" />
            <Skeleton className="h-3 w-12 shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Names for so many shapes, to tell them apart in a list. */
function places(count: number): string[] {
  return Array.from({ length: count }, (_, at) => `place ${at + 1}`);
}
