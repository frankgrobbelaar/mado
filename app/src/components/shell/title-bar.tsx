import { getCurrentWindow } from "@tauri-apps/api/window";
import { Minus, Square, X } from "lucide-react";
import type { ReactNode } from "react";
import { MadoLogo } from "@/components/mado-logo";
import { cn } from "@/lib/utils";

/**
 * Mado draws its own title bar (the window has no Windows frame): a slim strip over the page
 * with the window's buttons. Drag it to move the window; double-click it to maximise. Beside the
 * rail it needs no name (the rail has the mark); a page without the rail (Setup) gives it one.
 * It takes the pointer even while a card holds the rest of the window, which a press here closes.
 */
export function TitleBar({ title }: { title?: string }) {
  return (
    <header
      data-tauri-drag-region
      className="pointer-events-auto flex h-9 shrink-0 items-center gap-3 select-none"
    >
      <div data-tauri-drag-region className="flex min-w-0 flex-1 items-center pl-4">
        {title && (
          <span className="pointer-events-none flex items-center gap-2">
            <MadoLogo size={18} />
            <span className="font-semibold text-13">{title}</span>
          </span>
        )}
      </div>
      <div className="flex">
        <WindowButton label="Minimize" onClick={() => getCurrentWindow().minimize()}>
          <Minus size={14} strokeWidth={1.6} />
        </WindowButton>
        <WindowButton label="Maximize" onClick={() => getCurrentWindow().toggleMaximize()}>
          <Square size={11} strokeWidth={1.6} />
        </WindowButton>
        <WindowButton label="Close" onClick={() => getCurrentWindow().close()} closes>
          <X size={14} strokeWidth={1.6} />
        </WindowButton>
      </div>
    </header>
  );
}

function WindowButton(props: {
  label: string;
  onClick: () => void;
  closes?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={props.label}
      onClick={props.onClick}
      className={cn(
        "inline-flex h-9 w-11.5 cursor-pointer items-center justify-center text-fg-muted transition-colors duration-120 hover:text-fg",
        props.closes ? "hover:bg-danger hover:text-on-danger" : "hover:bg-tint/8",
      )}
    >
      {props.children}
    </button>
  );
}
