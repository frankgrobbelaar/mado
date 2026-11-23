/**
 * Screens written out to be shot as pictures by scripts/readme-pictures.mjs: the README's
 * (readme-screens.test.tsx), or any piece's own. A test draws a screen with Mado's own components
 * and made-up data, then `dump` writes the page's DOM to the folder MADO_SHOTS names. Pictures
 * come from the made-up engine as `scene`s, which the shoot draws by code in their place
 * (scripts/readme-scenes.mjs). Without MADO_SHOTS nothing is written, and such tests are skipped.
 */
import { vi } from "vitest";

/** The folder screens are written to; unset, the tests that write them are skipped. */
export const SHOTS = import.meta.env.MADO_SHOTS as string | undefined;

// Named here rather than written in the import, so the type check leaves it to Node, which the
// tests run in: the app's own code has no Node.
const NODE_FS: string = "node:fs";

interface Files {
  existsSync(path: string): boolean;
  mkdirSync(path: string, options: { recursive: true }): void;
  readFileSync(path: string, encoding: "utf8"): string;
  writeFileSync(path: string, text: string): void;
}

const files = async () => (await import(/* @vite-ignore */ NODE_FS)) as Files;

/** Writes the page as it is now, rail and cards and all, to `<name>.html` in the shots folder. */
export async function dump(name: string): Promise<void> {
  if (!SHOTS) return;
  // What's ticked, chosen or typed lives in the page, not its markup: written into the markup, it
  // shows.
  for (const input of document.querySelectorAll("input")) {
    if (input.type === "checkbox" || input.type === "radio")
      input.toggleAttribute("checked", input.checked);
    else input.setAttribute("value", input.value);
  }
  for (const option of document.querySelectorAll("option"))
    option.toggleAttribute("selected", option.selected);
  for (const box of document.querySelectorAll("textarea")) box.textContent = box.value;
  const fs = await files();
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.writeFileSync(`${SHOTS}/${name}.html`, document.body.innerHTML);
}

interface Box {
  width: number;
  height: number;
}

/** A stage's space before the shoot has measured it: about what a picture's page has. */
const GUESS: Box = { width: 900, height: 600 };

/**
 * Stands in for ResizeObserver while `name` is drawn. jsdom lays nothing out, so a stage that fits
 * a picture to its space, or a slider's thumb, would measure nothing: each element watched is told
 * the size the shoot measured it at in Edge (`boxes.json` in the shots folder, by screen and in the
 * order they're watched), or a guess till then, and is marked (`data-shot-box`, `data-shot-size`)
 * so the shoot can measure it and take the screen again when a guess was wrong.
 */
export async function measuredBoxes(name: string): Promise<void> {
  const fs = SHOTS ? await files() : null;
  const kept = `${SHOTS}/boxes.json`;
  // A gap (null) is one the shoot couldn't measure: gone before the screen was written.
  const measured: Record<string, (Box | null)[]> =
    fs?.existsSync(kept) === true ? JSON.parse(fs.readFileSync(kept, "utf8")) : {};
  const sizes = measured[name] ?? [];
  let watched = 0;
  class Measured {
    constructor(private readonly told: ResizeObserverCallback) {}
    observe(target: Element) {
      const at = watched++;
      const { width, height } = sizes[at] ?? GUESS;
      target.setAttribute("data-shot-box", String(at));
      target.setAttribute("data-shot-size", `${width}x${height}`);
      const entry = {
        target,
        contentRect: { x: 0, y: 0, top: 0, left: 0, width, height, right: width, bottom: height },
        borderBoxSize: [{ inlineSize: width, blockSize: height }],
        contentBoxSize: [{ inlineSize: width, blockSize: height }],
      };
      this.told([entry as unknown as ResizeObserverEntry], this as unknown as ResizeObserver);
    }
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", Measured);
}

const scenes = new WeakMap<Blob, string>();

/**
 * A made-up picture, as the engine would send it: `what` names the scene the shoot draws in its
 * place, and what's done to it, as path parts ("harbour", "harbour/look=warm-film/part=sky").
 */
export function scene(what: string, headers?: HeadersInit): Response {
  const blob = new Blob([what], { type: "image/svg+xml" });
  scenes.set(blob, what);
  const response = new Response(blob, { headers });
  // The page asks for the picture's bytes, then for an address to show them at: the same blob
  // comes back, so its address can name the scene.
  Object.defineProperty(response, "blob", { value: async () => blob });
  return response;
}

/** Gives each scene an address the shoot finds in the page ("blob:scene/harbour"). */
export function drawScenes(): void {
  URL.createObjectURL = (blob: Blob | MediaSource) =>
    `blob:scene/${(blob instanceof Blob && scenes.get(blob)) || "missing"}`;
  URL.revokeObjectURL = () => {};
}
