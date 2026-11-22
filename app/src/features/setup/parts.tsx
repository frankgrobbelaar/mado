import { type ReactNode, useEffect, useRef } from "react";

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
      className="flex animate-pop scroll-mt-6 flex-col gap-5 rounded-24 border border-accent/35 bg-raised p-6 shadow-panel"
    >
      <div className="flex flex-col gap-1">
        <h2 id={props.labelledBy} className="font-extrabold text-24 tracking-[-0.02em]">
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
