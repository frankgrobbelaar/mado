/**
 * Where a wallpaper's parts are cut, as the engine works it out (engine/src/mado/core/wallpaper.py,
 * `framed` and `laid_across`), so a part being dragged or zoomed is drawn as it moves. The engine's
 * own plan is what's made: it follows each change. Pixels are the picture's, as it's shown.
 */

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Where the owner cut a picture: the part's middle as fractions (null: around its subject), and
 * how near it comes (1: the biggest part with the monitor's shape). */
export interface Cut {
  x: number | null;
  y: number | null;
  zoom: number;
}

export const ZOOM_MOST = 4;
const SAME = 0.004; // shapes this close are the same

/** The canvas a `width` by `height` picture is made from for a `target` of pixels: cropped, the
 * biggest part with the target's shape made `cut.zoom` times nearer around its middle, held
 * inside the picture; or extended, all of it in the middle of a canvas with the target's shape. */
export function framed(
  width: number,
  height: number,
  target: [number, number],
  shape: "crop" | "extend",
  cut: Cut,
  focus: { x: number; y: number } | null,
): { canvas: Box } {
  const ratio = width / height;
  const wanted = target[0] / target[1];
  const same = Math.abs(ratio - wanted) / wanted < SAME;
  if (shape === "extend") {
    if (same) return { canvas: { x: 0, y: 0, width, height } };
    if (wanted > ratio) {
      const canvasWidth = height * wanted;
      return { canvas: { x: -(canvasWidth - width) / 2, y: 0, width: canvasWidth, height } };
    }
    const canvasHeight = width / wanted;
    return { canvas: { x: 0, y: -(canvasHeight - height) / 2, width, height: canvasHeight } };
  }
  const [biggestWidth, biggestHeight] = same
    ? [width, height]
    : wanted > ratio
      ? [width, width / wanted]
      : [height * wanted, height];
  const zoom = Math.min(Math.max(cut.zoom, 1), ZOOM_MOST);
  const keptWidth = biggestWidth / zoom;
  const keptHeight = biggestHeight / zoom;
  const middleX = (cut.x ?? focus?.x ?? 0.5) * width;
  const middleY = (cut.y ?? focus?.y ?? 0.5) * height;
  return {
    canvas: {
      x: held(middleX - keptWidth / 2, 0, width - keptWidth),
      y: held(middleY - keptHeight / 2, 0, height - keptHeight),
      width: keptWidth,
      height: keptHeight,
    },
  };
}

/** The part of `canvas` (the picture's pixels) that falls on `place`, the canvas laid over `whole`
 * (the monitors' pixels). */
export function laidAcross(canvas: Box, whole: Box, place: Box): Box {
  const across = canvas.width / whole.width;
  const down = canvas.height / whole.height;
  return {
    x: canvas.x + (place.x - whole.x) * across,
    y: canvas.y + (place.y - whole.y) * down,
    width: place.width * across,
    height: place.height * down,
  };
}

/** The smallest box holding every one. */
export function boundsOf(boxes: Box[]): Box {
  const left = Math.min(...boxes.map((box) => box.x));
  const top = Math.min(...boxes.map((box) => box.y));
  const right = Math.max(...boxes.map((box) => box.x + box.width));
  const bottom = Math.max(...boxes.map((box) => box.y + box.height));
  return { x: left, y: top, width: right - left, height: bottom - top };
}

/** A part as fractions of a `width` by `height` picture. */
export function areaOf(box: Box, width: number, height: number): Box {
  return {
    x: box.x / width,
    y: box.y / height,
    width: box.width / width,
    height: box.height / height,
  };
}

function held(value: number, low: number, high: number) {
  return Math.min(Math.max(value, low), Math.max(high, low));
}
