import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  /** What this place is for, in one or two plain sentences. */
  children: ReactNode;
  illustration?: ReactNode;
  /** The one thing to do next. */
  action?: ReactNode;
  note?: ReactNode;
}

/** A place with nothing in it yet: what it's for and the one next step. */
export function EmptyState({ title, children, illustration, action, note }: EmptyStateProps) {
  return (
    <section className="flex animate-fade-up flex-col items-center gap-3 rounded-20 border border-tint/14 border-dashed bg-tint/3 px-5 py-6.5 text-center">
      {illustration}
      <h2 className="font-extrabold text-17">{title}</h2>
      <p className="max-w-md text-13 text-fg-muted">{children}</p>
      {action}
      {note && <p className="text-12 text-fg-faint">{note}</p>}
    </section>
  );
}

/** A window's four panes, drifting a little: the "nothing here yet" picture. */
export function WindowIllustration() {
  return (
    <div aria-hidden="true" className="grid size-21 grid-cols-2 gap-1.5 p-1.5">
      <span className="animate-float rounded-8 bg-[#2449b8]" />
      <span className="animate-float rounded-8 bg-[#c4561d] [animation-delay:300ms]" />
      <span className="animate-float rounded-8 bg-[#5b2a86] [animation-delay:600ms]" />
      <span className="animate-float rounded-8 bg-[#1f6f5c] [animation-delay:900ms]" />
    </div>
  );
}
