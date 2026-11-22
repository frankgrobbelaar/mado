import { type ReactNode, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

// The pieces every setup step is built from.

export function Panel(props: {
  title: string;
  labelledBy: string;
  intro?: string;
  children?: ReactNode;
}) {
  const panel = useRef<HTMLElement>(null);

  // A new step comes into view as it opens, below the steps already done.
  useEffect(() => {
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    panel.current?.scrollIntoView?.({ block: "nearest", behavior: still ? "auto" : "smooth" });
  }, []);

  return (
    <section
      ref={panel}
      aria-labelledby={props.labelledBy}
      className="flex animate-pop scroll-mt-6 flex-col gap-5 rounded-8 border border-accent/35 bg-raised p-6 shadow-panel"
    >
      <div className="flex flex-col gap-1">
        <h2 id={props.labelledBy} className="font-semibold text-24 tracking-[-0.02em]">
          {props.title}
        </h2>
        {props.intro && <p className="text-14 text-fg-muted">{props.intro}</p>}
      </div>
      {props.children}
    </section>
  );
}

export function Footer({ note, children }: { note: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="flex-[1_1_320px] text-13 text-fg-muted">{note}</p>
      <div className="flex gap-2.5">{children}</div>
    </div>
  );
}

export type Step = "tools" | "folders" | "done";

const STEPS: { step: Step; label: string }[] = [
  { step: "tools", label: "1 · Tools" },
  { step: "folders", label: "2 · Your folders" },
  { step: "done", label: "3 · Done" },
];

/** Where setup is: each step done (solid), the one now (a ring lit at its top) or still to
 * come (hollow), by shape as much as by colour. */
export function Steps({ now }: { now: Step }) {
  const at = STEPS.findIndex((each) => each.step === now);
  return (
    <ol aria-label="Setup" className="flex flex-wrap gap-x-5 gap-y-1.5 text-13">
      {STEPS.map(({ step, label }, index) => (
        <li
          key={step}
          aria-current={index === at ? "step" : undefined}
          className={cn("flex items-center gap-2", index === at ? "text-fg" : "text-fg-muted")}
        >
          <span
            aria-hidden="true"
            className={cn(
              "size-3 rounded-full",
              index < at && "status-done",
              index === at && "border-2 border-line border-t-accent",
              index > at && "status-waiting",
            )}
          />
          {label}
        </li>
      ))}
    </ol>
  );
}
