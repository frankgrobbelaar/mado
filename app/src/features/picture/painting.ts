import type { PaintingStyle, PaintStep, Part, Styles, YourStyle } from "@/lib/engine";

/** A picture of the owner's as the style, read but not kept: its numbers, what it's called, and
 * the picture it came from (whose thumbnail its tile shows). */
export interface PictureStyle {
  code: string;
  named: string;
  from: { id: number; version: string };
}

/** The painting step as the recipe carries it, on the parts the look's on too ("Only on a part"
 * is the Looks tab's, for its look and its style alike); null for none, or none at all of it. */
export function painted(step: PaintStep | null, parts: Part[]): PaintStep | null {
  if (!step || step.strength <= 0) return null;
  return parts.length ? { ...step, parts } : step;
}

/** A style as it's picked: at the strength and with the colours chosen so far (all of it, the
 * first time), a classic one at its own first setting; a picture's carrying its numbers. */
export function stepFor(
  style: string,
  before: PaintStep | null,
  extra: { code?: string; named?: string } = {},
): PaintStep {
  return {
    style,
    strength: before?.strength ?? 1,
    colours: before?.colours ?? false,
    setting: null,
    ...(extra.code ? { code: extra.code, named: extra.named ?? null } : {}),
  };
}

/** What a style is called: Mado's and the owner's by their ids, a picture's after it ("Night
 * market style"). */
export function styleName(step: PaintStep, styles: Styles | undefined): string {
  if (step.style === "picture") return `${step.named ?? "A picture"} style`;
  return found(step.style, styles)?.name ?? "";
}

/** The download a style paints with: a painter's network, or MicroAST for a picture's own style
 * (kept or not); none for a classic one, which code draws. */
export function networkOf(step: PaintStep, styles: Styles | undefined): string | null {
  if (step.style === "picture" || step.style.startsWith("yours-")) return styles?.reader ?? null;
  return styles?.painters.find((each) => each.id === step.style)?.download ?? null;
}

/** One of Mado's styles, or the owner's, by its id. */
export function found(
  id: string,
  styles: Styles | undefined,
): PaintingStyle | YourStyle | undefined {
  const all = [...(styles?.painters ?? []), ...(styles?.classics ?? []), ...(styles?.yours ?? [])];
  return all.find((each) => each.id === id);
}

/** One of Mado's classic means, which have a setting of their own. */
export function classicOf(id: string, styles: Styles | undefined): PaintingStyle | undefined {
  return styles?.classics.find((each) => each.id === id);
}

/** Whether a style can keep the picture's own colours: a painter's or a picture's; a classic
 * one's colours are its own anyway. */
export function keepsColours(id: string, styles: Styles | undefined): boolean {
  return !classicOf(id, styles);
}
