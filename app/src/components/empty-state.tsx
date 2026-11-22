import { type ReactNode, useId } from "react";

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
    <section className="flex animate-fade-up flex-col items-center gap-3 rounded-8 border border-dash border-dashed bg-tint/3 px-5 py-8 text-center">
      {illustration}
      <h2 className="font-semibold text-16">{title}</h2>
      <p className="max-w-md text-13 text-fg-muted">{children}</p>
      {action}
      {note && <p className="text-12 text-fg-faint">{note}</p>}
    </section>
  );
}

/** Mado's round window, lit, with a hill seen through it, drifting a little: the "nothing here
 * yet" picture. */
export function WindowIllustration() {
  const clip = `window-${useId().replace(/[^\w-]/g, "")}`;
  return (
    <svg aria-hidden="true" viewBox="0 0 64 64" className="size-16 animate-float">
      <defs>
        <clipPath id={clip}>
          <circle cx="32" cy="32" r="27" />
        </clipPath>
      </defs>
      <circle cx="32" cy="32" r="27" className="fill-accent" />
      <path
        clipPath={`url(#${clip})`}
        d="M1 43 C14 35 25 35 35 40 C45 46 53 45 63 39 L63 66 L1 66 Z"
        className="fill-window"
      />
      <circle cx="32" cy="32" r="27" fill="none" strokeWidth="2" className="stroke-line-strong" />
    </svg>
  );
}
