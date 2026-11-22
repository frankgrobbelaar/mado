import { X } from "lucide-react";
import { Dialog as Primitive } from "radix-ui";
import {
  type ComponentProps,
  type ReactNode,
  type RefObject,
  useLayoutEffect,
  useRef,
} from "react";
import { cn } from "@/lib/utils";

// Adapted from shadcn/ui's dialog (MIT, see LICENSE-shadcn.txt), restyled to Graphite: a card over
// the page it tells more of, below the title bar, the page dimming behind it, with a header
// (DialogHeader). Escape, the cross or a click beside it closes it; so does the title bar, which
// keeps working (it lets the pointer through: TitleBar).

export const Dialog = Primitive.Root;

export function DialogContent({
  className,
  children,
  onOpenAutoFocus,
  onCloseAutoFocus,
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  const content = useRef<HTMLDivElement>(null);
  // Where the focus goes back to as it closes: what had it outside the card last. Opened from a
  // row's menu, that's the menu's button, which the menu gives the focus back to as it closes. A
  // menu's own items don't count, the card's or a row's: they're gone once it closes.
  const back = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    const outside = (target: unknown): target is HTMLElement =>
      target instanceof HTMLElement &&
      target !== document.body &&
      !content.current?.contains(target) &&
      !target.closest("[data-radix-popper-content-wrapper]");
    if (outside(document.activeElement)) back.current = document.activeElement;
    const note = (event: FocusEvent) => {
      if (outside(event.target)) back.current = event.target;
    };
    document.addEventListener("focusin", note);
    return () => document.removeEventListener("focusin", note);
  }, []);
  return (
    <Primitive.Portal>
      <Primitive.Overlay className="fixed inset-x-0 top-13 bottom-0 z-55 animate-fade-in bg-window/70" />
      <Primitive.Content
        {...props}
        ref={content}
        data-slot="dialog"
        className={cn(
          "fixed inset-x-0 top-[calc(3.25rem+6vh)] z-55 mx-auto flex max-h-[calc(100vh-3.25rem-6vh-2rem)] w-[min(40rem,calc(100vw-2rem))] animate-card-in flex-col overflow-hidden rounded-10 border border-edge bg-dialog shadow-dialog outline-none",
          className,
        )}
        // The card itself takes the focus as it opens, not its first button: the keyboard goes on
        // from there, and nothing in it looks picked before anything is.
        onOpenAutoFocus={(event) => {
          onOpenAutoFocus?.(event);
          if (event.defaultPrevented) return;
          event.preventDefault();
          content.current?.focus({ preventScroll: true });
        }}
        onCloseAutoFocus={(event) => {
          onCloseAutoFocus?.(event);
          if (event.defaultPrevented) return;
          event.preventDefault();
          if (back.current?.isConnected) back.current.focus();
        }}
      >
        {children}
      </Primitive.Content>
    </Primitive.Portal>
  );
}

/** A card's heading: what it's about, which names it for screen readers too. */
export function DialogTitle({ className, ...props }: ComponentProps<typeof Primitive.Title>) {
  return <Primitive.Title className={cn("font-semibold leading-tight", className)} {...props} />;
}

/** The line under a card's heading. Every card has one. */
export function DialogDescription({
  className,
  ...props
}: ComponentProps<typeof Primitive.Description>) {
  return <Primitive.Description className={cn("text-13 text-fg-muted", className)} {...props} />;
}

/** A card's top: its heading, the line under it, and its cross. */
export function DialogHeader({ title, description }: { title: ReactNode; description: ReactNode }) {
  return (
    <header className="flex shrink-0 items-start gap-3 border-rule border-b px-6 pt-5 pb-4">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <DialogTitle className="text-18">{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </div>
      <Primitive.Close
        aria-label="Close"
        className="press -mt-1 -mr-2 inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full text-fg-muted hover:bg-tint/8 hover:text-fg"
      >
        <X size={18} aria-hidden="true" />
      </Primitive.Close>
    </header>
  );
}

/** What a card says, under its header: it scrolls in its place when it's long. */
export function DialogBody({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 pt-4.5 pb-5.5",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** A card's foot, which stays put while its body scrolls. */
export function DialogFooter({
  children,
  at,
}: {
  children: ReactNode;
  at?: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      ref={at}
      className="flex shrink-0 items-center justify-between gap-3 border-rule border-t px-4 py-2.5"
    >
      {children}
    </div>
  );
}
