import { useId } from "react";
import { cn } from "@/lib/utils";

/** One of Settings' panels: a title, a note under it, an action beside it. */
export function Panel(props: {
  title: string;
  note?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section
      aria-labelledby={id}
      className={cn(
        "flex animate-fade-up flex-col gap-3 rounded-8 border border-edge bg-glass p-5",
        props.className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 id={id} className="font-semibold text-16">
            {props.title}
          </h2>
          {props.note && <span className="text-13 text-fg-muted">{props.note}</span>}
        </div>
        {props.action}
      </div>
      {props.children}
    </section>
  );
}
