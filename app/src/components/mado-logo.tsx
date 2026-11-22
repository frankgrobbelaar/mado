import { useId } from "react";

/** Mado's mark: a round window (窓, mado, is a window) lit in volt, with a hill seen through it.
 * It keeps its own colours in light and dark, as an app's icon does (app/src-tauri/icons/mado.svg). */
export function MadoLogo({ size = 22 }: { size?: number }) {
  const clip = `mado-window-${useId().replace(/[^\w-]/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <clipPath id={clip}>
          <circle cx="32" cy="32" r="20" />
        </clipPath>
      </defs>
      <rect width="64" height="64" rx="15" fill="#2a2b2e" />
      <rect
        x="1"
        y="1"
        width="62"
        height="62"
        rx="14"
        fill="none"
        stroke="#46474d"
        strokeWidth="2"
      />
      <circle cx="32" cy="32" r="20" fill="#c9f24d" />
      <path
        clipPath={`url(#${clip})`}
        d="M10 40 C19 34 27 34 34 38 C41 42 47 41 54 37 L54 56 L10 56 Z"
        fill="#2a2b2e"
      />
    </svg>
  );
}
