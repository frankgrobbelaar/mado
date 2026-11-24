import type { DepthStep, FogStep, PortraitStep, TiltStep } from "@/lib/engine";

/** No depth tool on. */
export const NO_DEPTH: DepthStep = { portrait: null, fog: null, tilt: null };

/** Each tool as it starts when it's turned on: portrait blur at f/2.8, in focus at its subject;
 * fog half as thick as it gets, in the picture's own haze; tilt-shift's band a little below the
 * middle, as a town seen from above is framed. */
export const PORTRAIT_START: PortraitStep = { focus: null, aperture: 2.8, quality: null };
export const FOG_START: FogStep = { density: 0.5, colour: null };
export const TILT_START: TiltStep = { centre: 0.55, height: 0.2, strength: 0.6 };

/** A lens's stops, widest first: portrait blur's strength. */
export const APERTURES = [1.4, 2, 2.8, 4, 5.6, 8, 11, 16] as const;

/** The depth model, by its id in Mado's list of downloads (engine/src/mado/downloads.json). */
export const DEPTH_MODEL = "depth-anything-v2-small";

/** Fog's colours: the picture's own haze (its farthest light, made paler), or one of three. */
export const FOG_COLOURS = [
  { colour: null, label: "Its own haze" },
  { colour: "#e4e8ec", label: "Mist" },
  { colour: "#f1e3cd", label: "Warm" },
  { colour: "#c9d6e8", label: "Cool" },
] as const;

/** Whether any depth tool is on. */
export function hasDepth(depth: DepthStep | null | undefined): depth is DepthStep {
  return Boolean(depth && (depth.portrait || depth.fog || depth.tilt));
}

/** A recipe with its depth tools, when any is on: one without carries none, as it did before Mado
 * had them. */
export function withDepth<T extends object>(
  recipe: T,
  depth: DepthStep | null | undefined,
): T & { depth?: DepthStep } {
  return hasDepth(depth) ? { ...recipe, depth } : recipe;
}

/** Whether the tools on need the picture's depth read: portrait blur and fog do; tilt-shift goes
 * by place alone. */
export function readsDepth(depth: DepthStep | null | undefined): boolean {
  return Boolean(depth && (depth.portrait || depth.fog));
}

/** An aperture as a lens says it: "f/2.8". */
export function stopWords(aperture: number): string {
  return `f/${aperture}`;
}

/** The tools on, as the stage's label names them: "Portrait blur at f/2.8, Fog". */
export function depthNames(depth: DepthStep): string {
  return [
    depth.portrait && `Portrait blur at ${stopWords(depth.portrait.aperture)}`,
    depth.fog && "Fog",
    depth.tilt && "Tilt-shift",
  ]
    .filter(Boolean)
    .join(", ");
}

/** The band tilt-shift keeps in focus, as fractions of the picture's height, held inside it. */
export function bandOf(tilt: TiltStep): { top: number; bottom: number } {
  const half = tilt.height / 2;
  return { top: Math.max(0, tilt.centre - half), bottom: Math.min(1, tilt.centre + half) };
}

/** A band moved so its middle is at `centre`, kept whole inside the picture. */
export function bandAt(tilt: TiltStep, centre: number): TiltStep {
  const half = tilt.height / 2;
  return { ...tilt, centre: Math.min(1 - half, Math.max(half, centre)) };
}

/** A band whose edge was dragged to `edge` (a fraction down the picture): as tall as twice the
 * way from its middle, from 4% to 90% of the picture. */
export function bandTo(tilt: TiltStep, edge: number): TiltStep {
  const height = Math.min(0.9, Math.max(0.04, Math.abs(edge - tilt.centre) * 2));
  return bandAt({ ...tilt, height }, tilt.centre);
}
