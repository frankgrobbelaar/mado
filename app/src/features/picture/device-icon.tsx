/** The devices a picture is made for, drawn as the Picture-Size board draws them. */
const SHAPES: Record<
  string,
  { body: { x: number; y: number; w: number; h: number; r: number }; d: string }
> = {
  phone: { body: { x: 7, y: 3, w: 10, h: 18, r: 2 }, d: "M11 18h2" },
  tablet: { body: { x: 5, y: 3, w: 14, h: 18, r: 2 }, d: "M11 18h2" },
  laptop: { body: { x: 5, y: 5, w: 14, h: 10, r: 1.5 }, d: "M3 19h18" },
  monitor: { body: { x: 3, y: 4, w: 18, h: 12, r: 1.5 }, d: "M9 20h6M12 16v4" },
  ultrawide: { body: { x: 2, y: 7, w: 20, h: 9, r: 1.5 }, d: "M9 20h6M12 16v4" },
  tv: { body: { x: 3, y: 5, w: 18, h: 12, r: 1.5 }, d: "M8 21h8" },
};

export function DeviceIcon({ purpose, className }: { purpose: string; className?: string }) {
  const shape = SHAPES[purpose] ?? SHAPES.monitor;
  if (!shape) return null;
  const { body, d } = shape;
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      aria-hidden="true"
      className={className}
    >
      <rect x={body.x} y={body.y} width={body.w} height={body.h} rx={body.r} />
      <path d={d} />
    </svg>
  );
}
