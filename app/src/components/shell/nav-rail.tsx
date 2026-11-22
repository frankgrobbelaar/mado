import { Link, useLocation } from "react-router";
import { MadoLogo } from "@/components/mado-logo";
import { type QueueNow, useQueueNow } from "@/lib/engine";
import { cn } from "@/lib/utils";
import { type Section, sectionOf, sections } from "./sections";

/**
 * The rail: Mado's mark at the top, its places under it, Settings at its foot. It runs the
 * window's full height beside the page and never scrolls with it. The place a page sits in stays
 * lit while it's open. Drag the mark to move the window, as the title bar does. The Queue's badge
 * says how far the batch being made has got, or how many pictures wait.
 */
export function NavRail() {
  const location = useLocation();
  const lit = sectionOf(location.pathname);
  const queue = useQueueNow().data;
  return (
    <nav
      aria-label="Main"
      className="flex w-20 shrink-0 flex-col gap-1 border-chrome-edge border-r bg-chrome px-2 pt-2.5 pb-2.5"
    >
      <div data-tauri-drag-region className="mb-2 flex h-12 items-center justify-center">
        <span className="pointer-events-none flex">
          <MadoLogo size={36} />
        </span>
      </div>
      {sections
        .filter((section) => !section.foot)
        .map((section) => (
          <Place
            key={section.path}
            section={section}
            lit={section.path === lit}
            badge={section.path === "/queue" ? badgeOf(queue) : null}
          />
        ))}
      <div className="mt-auto flex flex-col gap-1">
        {sections
          .filter((section) => section.foot)
          .map((section) => (
            <Place key={section.path} section={section} lit={section.path === lit} badge={null} />
          ))}
      </div>
    </nav>
  );
}

/** The Queue's badge: "37%" while a batch is being made, else how many pictures wait. */
export function badgeOf(queue: QueueNow | undefined): { text: string; label: string } | null {
  if (!queue) return null;
  if (queue.working) {
    const percent = Math.round(queue.progress * 100);
    return { text: `${percent}%`, label: `${queue.batch ?? "a batch"} is ${percent}% made` };
  }
  if (queue.waiting > 0) {
    return {
      text: String(queue.waiting),
      label: `${queue.waiting} ${queue.waiting === 1 ? "picture waits" : "pictures wait"}`,
    };
  }
  return null;
}

function Place(props: {
  section: Section;
  lit: boolean;
  badge: { text: string; label: string } | null;
}) {
  const { section, lit, badge } = props;
  const { path, label, icon: Icon } = section;
  return (
    <Link
      to={path}
      aria-current={lit ? "page" : undefined}
      aria-label={badge ? `${label}, ${badge.label}` : undefined}
      className={cn(
        "press relative flex flex-col items-center gap-1 rounded-8 px-1 py-2 font-semibold text-11",
        lit ? "bg-raised text-fg" : "text-fg-muted hover:bg-tint/6 hover:text-fg",
      )}
    >
      <Icon size={20} strokeWidth={1.7} aria-hidden="true" />
      {label}
      {badge && (
        <span
          aria-hidden="true"
          className="absolute top-0.75 right-1.25 rounded-full bg-accent px-1.25 py-px font-mono font-semibold text-10 text-on-accent"
        >
          {badge.text}
        </span>
      )}
    </Link>
  );
}
