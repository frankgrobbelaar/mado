/** Mado's mark for now: a window of four panes (窓, mado, is a window). Its own mark comes with
 * Mado's look, from the design canvas. */
export function MadoLogo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="1" y="1" width="22" height="22" rx="7" className="fill-accent" />
      <rect x="5.5" y="5.5" width="5.7" height="5.7" rx="1.6" className="fill-on-accent" />
      <rect x="12.8" y="5.5" width="5.7" height="5.7" rx="1.6" className="fill-on-accent" />
      <rect x="5.5" y="12.8" width="5.7" height="5.7" rx="1.6" className="fill-on-accent" />
      <rect x="12.8" y="12.8" width="5.7" height="5.7" rx="1.6" className="fill-on-accent" />
    </svg>
  );
}
