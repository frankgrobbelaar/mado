import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useHeldAction, useHeldJobs } from "@/lib/engine";
import { count } from "@/lib/format";

/**
 * A picture open in another app, as the small things board draws it: a note at the window's foot
 * while the queue or a Save waits for it ("Harbour at dusk.jpg is open in another app"), saying
 * that Mado tries again by itself, with Try again now and Skip it. It stays while it waits.
 */
export function InUse() {
  const held = useHeldJobs();
  const act = useHeldAction();
  const [first, ...more] = held.data ?? [];
  if (!first) return null;
  return (
    <div
      role="status"
      className="flex animate-pop flex-wrap items-center gap-x-4 gap-y-3 rounded-8 border border-field-edge bg-raised px-4 py-3.5 text-fg shadow-toast"
    >
      <Lock size={22} strokeWidth={1.6} aria-hidden="true" className="shrink-0" />
      <span className="flex min-w-0 flex-[1_1_260px] flex-col gap-0.5">
        <span className="font-semibold text-15">
          <span className="font-medium font-mono [overflow-wrap:anywhere]">{first.name}</span> is
          open in another app
        </span>
        <span className="text-13 text-fg-muted">
          Mado can't {first.verb} it while it's open. Close it there and Mado tries again by itself.
        </span>
      </span>
      <span className="flex gap-2">
        <Button
          size="sm"
          className="font-medium"
          disabled={act.isPending}
          onClick={() => act.mutate({ path: `/jobs/${first.job}/try-now` })}
        >
          Try again now
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={act.isPending}
          onClick={() => act.mutate({ path: `/jobs/${first.job}/skip` })}
        >
          Skip it
        </Button>
      </span>
      {more.length > 0 && (
        <span className="basis-full text-12 text-fg-faint">
          {count(more.length)} more {more.length === 1 ? "waits" : "wait"} the same way; each is
          tried again by itself.
        </span>
      )}
      {act.isError && (
        <span role="alert" className="basis-full text-12 text-broken-fg">
          {act.error.message}
        </span>
      )}
    </div>
  );
}
