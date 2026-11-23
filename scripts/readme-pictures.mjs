// Takes the README's pictures again, from Mado's own screens (docs/development.md, "Taking the
// README's pictures again"). app/src/test/readme-screens.test.tsx draws each screen with Mado's
// own components and made-up data and writes out its DOM; this wraps each with the UI's built CSS
// (its fonts too), draws the made-up scenes where its pictures go (readme-scenes.mjs), shoots it
// in headless Edge, and frames it as the README shows it: the window with rounded corners and a
// soft shadow, and Home cut diagonally between dark and light.
//
//   node scripts/readme-pictures.mjs              # every picture, into docs/readme/
//   node scripts/readme-pictures.mjs home size    # just these
//   node scripts/readme-pictures.mjs --screens app/src/features/x/shots.test.tsx --out <folder>
//                                                 # another test's screens, each dark and light
//
// --no-build uses app/dist as it is; --keep keeps the pages it shot, and says where.
import { spawn, spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { placeScenes } from "./readme-scenes.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const app = join(root, "app");

/** The window as the boards draw it, and as the screens are drawn. */
export const SCREEN = { width: 1440, height: 960 };

/** The README's frame: the window scaled to 1216 across, 32 px in from each side, 24 from the
 * top and 48 from the foot, with room for its shadow. */
export const FRAME = { width: 1280, height: 883, window: { left: 32, top: 24, width: 1216, height: 811 }, radius: 14 };

/** The window's edge in each scheme: the tokens' line-strong. */
const EDGE = { dark: "#55565c", light: "#a6a7ad" };

/** The README's pictures: each from a screen the test draws. Home in dark and light is cut along
 * a line from `split[0]` across the window's top to `split[1]` across its foot (the screen's own
 * pixels), chosen where it crosses the fewest words: between them in the captions and the status
 * bar, past the end of "Pick a folder". When Home changes, look at the cut again. */
export const PICTURES = [
  { file: "home.png", screen: "home" },
  { file: "size.png", screen: "size" },
  { file: "looks.png", screen: "looks" },
  { file: "edit.png", screen: "edit" },
  { file: "batch.png", screen: "batch" },
  { file: "library.png", screen: "library" },
  { file: "wallpaper.png", screen: "wallpaper" },
  { file: "light-dark.png", screen: "home", split: [1008, 688] },
  { file: "save.png", screen: "save" },
];

/** The built CSS asks for its fonts at /assets/…, which a page opened from a file looks for at the
 * drive's root: beside the CSS is where they are. */
export function withFonts(css) {
  return css.replace(/url\((['"]?)\/assets\//g, "url($1");
}

/** A screen's DOM as a page, in one scheme, with the built CSS and its scenes drawn. */
export function screenPage(body, css, scheme) {
  return `<!doctype html>
<html lang="en" style="color-scheme: ${scheme}">
<head><meta charset="utf-8"><link rel="stylesheet" href="assets/${css}"></head>
<body>${placeScenes(body)}</body>
</html>
`;
}

/** The light half of a split, as a CSS clip-path: right of the line from `top` across the
 * window's top to `bottom` across its foot (the screen's pixels). */
export function splitClip([top, bottom]) {
  const at = (x) => `${Number(((x / SCREEN.width) * 100).toFixed(3))}%`;
  return `polygon(${at(top)} 0, 100% 0, 100% 100%, ${at(bottom)} 100%)`;
}

/** The README's frame round a screen shot in dark, light or both: `dark` and `light` are the
 * shots' addresses (one may be null), `split` the line between them. */
export function framePage({ dark, light, split }) {
  const { window: box, radius } = FRAME;
  const layer = (src, scheme, clip) =>
    `<div class="layer"${clip ? ` style="clip-path: ${clip}"` : ""}><img src="${src}" alt=""><div class="edge" style="box-shadow: inset 0 0 0 1px ${EDGE[scheme]}"></div></div>`;
  const layers = [];
  if (dark) layers.push(layer(dark, "dark", null));
  if (light) layers.push(layer(light, "light", dark && split ? splitClip(split) : null));
  return `<!doctype html>
<html><head><meta charset="utf-8"><style>
html, body { margin: 0; background: transparent; }
.window { position: absolute; left: ${box.left}px; top: ${box.top}px; width: ${box.width}px; height: ${box.height}px;
  border-radius: ${radius}px; overflow: hidden;
  box-shadow: 0 10px 32px rgb(0 0 0 / 0.3), 0 1px 4px rgb(0 0 0 / 0.2); }
.layer, .layer img, .edge { position: absolute; inset: 0; width: 100%; height: 100%; }
.edge { border-radius: ${radius}px; }
</style></head>
<body><div class="window">${layers.join("")}</div></body></html>
`;
}

/** Elements a screen's stand-in told a size (data-shot-box) that Edge lays out otherwise: the
 * sizes to tell them next time, or null when every one was right. */
export function boxesToRetake(measured) {
  const wrong = measured.some(({ told, width, height }) => {
    const [w, h] = told.split("x").map(Number);
    return Math.abs(w - width) > 1 || Math.abs(h - height) > 1;
  });
  if (!wrong) return null;
  // One watched and gone before the screen was written stays a guess (null), as it was.
  const sizes = Array.from({ length: Math.max(...measured.map(({ at }) => at)) + 1 }, () => null);
  for (const { at, width, height } of measured) sizes[at] = { width, height };
  return sizes;
}

/** What was asked for on the command line. Another test's screens go only where --out says, never
 * among the README's pictures. */
export function parseArgs(args) {
  const asked = { names: [], screens: null, out: null, build: true, keep: false };
  const value = (at) => {
    const given = args[at + 1];
    if (given === undefined || given.startsWith("--")) throw new Error(`${args[at]} needs a value.`);
    return given;
  };
  for (let at = 0; at < args.length; at++) {
    const arg = args[at];
    if (arg === "--screens") asked.screens = value(at++);
    else if (arg === "--out") asked.out = value(at++);
    else if (arg === "--no-build") asked.build = false;
    else if (arg === "--keep") asked.keep = true;
    else if (arg.startsWith("--")) throw new Error(`readme-pictures doesn't know ${arg}.`);
    else asked.names.push(arg.replace(/\.png$/, ""));
  }
  if (asked.screens && asked.names.length) throw new Error("Name pictures, or --screens, not both.");
  if (asked.screens && !asked.out) throw new Error("--screens needs --out: another test's screens aren't the README's.");
  for (const name of asked.names)
    if (!PICTURES.some((each) => each.file === `${name}.png`))
      throw new Error(`The README has no picture called ${name}: ${PICTURES.map((each) => each.file).join(", ")}.`);
  return asked;
}

/** What a font check found (`found`: each font of Windows' that drew words in the page's own
 * fonts' place, with an example of them), as a sentence; null when there are none. */
export function strayFonts(name, found) {
  if (!found.length) return null;
  const said = found.map(({ font, words }) => `${font} ("${words}")`).join(", ");
  return `${name} has words in ${said}, not Mado's own fonts: a glyph IBM Plex as Mado bundles it hasn't got?`;
}

// Running it: the UI built, the screens drawn, Edge.

/** A command run as a line of the shell, as pnpm wants on Windows; what it said, or a stop. None
 * takes ten minutes. */
function run(line, options = {}) {
  const done = spawnSync(line, { stdio: "pipe", encoding: "utf8", shell: true, timeout: 600_000, ...options });
  if (done.status !== 0) {
    process.stderr.write(`${done.stdout ?? ""}${done.stderr ?? ""}`);
    throw new Error(done.error ? `${line} didn't finish: ${done.error.message}` : `${line} failed.`);
  }
  return done.stdout;
}

/** The screens the test draws, written to `into`. */
function drawScreens(test, into) {
  const said = run(`pnpm exec vitest run "${test}"`, { cwd: app, env: { ...process.env, MADO_SHOTS: into } });
  const written = readdirSync(into).filter((name) => name.endsWith(".html"));
  if (!written.length) {
    process.stdout.write(said);
    throw new Error(`${test} drew no screens: does it call dump() from src/test/shots.ts?`);
  }
  return written.map((name) => name.replace(/\.html$/, ""));
}

function edgePath() {
  const places = [
    process.env.MADO_EDGE,
    join(process.env["ProgramFiles(x86)"] ?? "C:\\Program Files (x86)", "Microsoft", "Edge", "Application", "msedge.exe"),
    join(process.env.ProgramFiles ?? "C:\\Program Files", "Microsoft", "Edge", "Application", "msedge.exe"),
    join(process.env.LOCALAPPDATA ?? "", "Microsoft", "Edge", "Application", "msedge.exe"),
  ];
  const found = places.find((place) => place && existsSync(place));
  if (!found) throw new Error("Microsoft Edge isn't where Windows puts it: say where with MADO_EDGE.");
  return found;
}

const pause = (ms) => new Promise((done) => setTimeout(done, ms));

/** How Edge is started: headless, on the processor alone, its words in plain greys (not the
 * coloured edges a screen's subpixels want, which show at other zooms), in a throwaway profile kept
 * to itself. Without the last switches a fresh profile signs in to the Windows account's Microsoft
 * account by itself, syncs it, and loads its extensions and their welcome tabs. */
export const EDGE_SWITCHES = [
  "--headless=new",
  "--disable-gpu",
  "--disable-lcd-text",
  "--hide-scrollbars",
  "--mute-audio",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-features=msImplicitSignin",
  "--disable-sync",
  "--disable-extensions",
  "--disable-component-extensions-with-background-pages",
  "--disable-background-networking",
  "--disable-component-update",
  "--disable-default-apps",
];

/** Headless Edge, driven over its DevTools protocol, its profile and its own temporary files in
 * `folder`, all of it gone with the folder. */
async function openEdge(folder) {
  const profile = join(folder, "profile");
  const temporary = join(folder, "temp");
  mkdirSync(temporary, { recursive: true });
  const child = spawn(
    edgePath(),
    [...EDGE_SWITCHES, "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"],
    { stdio: "ignore", env: { ...process.env, TEMP: temporary, TMP: temporary } },
  );
  let gone = null; // why Edge isn't running any more
  child.once("error", (problem) => (gone ??= `Edge didn't start: ${problem.message}`));
  child.once("exit", () => (gone ??= "Edge closed."));
  const told = join(profile, "DevToolsActivePort");
  let socket;
  try {
    let lines = [];
    for (let waited = 0; lines.length < 2; waited += 100) {
      if (gone) throw new Error(gone);
      if (waited > 30_000) throw new Error("Edge didn't start in 30 s.");
      await pause(100);
      try {
        lines = readFileSync(told, "utf8").trim().split(/\r?\n/);
      } catch {
        // not written yet, or Edge is writing it now: look again
      }
    }
    socket = new WebSocket(`ws://127.0.0.1:${lines[0]}${lines[1]}`);
    await new Promise((open, fail) => {
      socket.onopen = open;
      socket.onerror = () => fail(new Error("Couldn't reach Edge's DevTools."));
    });
  } catch (problem) {
    child.kill(); // a half-started Edge isn't left running
    throw problem;
  }
  const waiting = new Map();
  let last = 0;
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    const answer = waiting.get(message.id);
    if (!answer) return;
    waiting.delete(message.id);
    if (message.error) answer.fail(new Error(`${answer.method}: ${message.error.message}`));
    else answer.done(message.result);
  };
  // Edge gone, nothing it was asked will be answered.
  socket.onclose = () => {
    for (const answer of waiting.values()) answer.fail(new Error(`${gone ?? "Edge closed."} (${answer.method})`));
    waiting.clear();
  };
  const send = (method, params = {}, sessionId = undefined) =>
    new Promise((done, fail) => {
      const id = ++last;
      const late = setTimeout(() => {
        waiting.delete(id);
        fail(new Error(`Edge didn't answer ${method} in a minute.`));
      }, 60_000);
      const answer = {
        done: (result) => (clearTimeout(late), done(result)),
        fail: (problem) => (clearTimeout(late), fail(problem)),
        method,
      };
      waiting.set(id, answer);
      try {
        socket.send(JSON.stringify({ id, method, params, sessionId }));
      } catch (problem) {
        waiting.delete(id);
        answer.fail(problem);
      }
    });
  return {
    send,
    async close() {
      socket.close();
      child.kill();
      await pause(500);
      // The switches keep the profile signed out; should an Edge to come sign it in anyway, say so.
      try {
        const kept = join(profile, "Default", "Preferences");
        if (existsSync(kept) && JSON.parse(readFileSync(kept, "utf8")).account_info?.length)
          console.warn("Edge signed its throwaway profile in to an account: see EDGE_SWITCHES.");
      } catch {
        // a profile Edge left half written says nothing either way
      }
    },
  };
}

// Waits for a page to be whole: loaded, its fonts and pictures in; says which fonts it has.
const READY = `(async () => {
  while (document.readyState !== "complete") await new Promise((done) => setTimeout(done, 20));
  await document.fonts.ready;
  await Promise.all([...document.images].map((image) => image.decode().catch(() => {})));
  await new Promise((done) => setTimeout(done, 50));
  return [...new Set([...document.fonts].filter((face) => face.status === "loaded").map((face) => face.family))];
})()`;

// What each element the screen's stand-in told a size is laid out at in Edge.
const MEASURE = `[...document.querySelectorAll("[data-shot-box]")].map((element) => {
  const style = getComputedStyle(element);
  const across = Number.parseFloat(style.paddingLeft) + Number.parseFloat(style.paddingRight);
  const down = Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom);
  return { at: Number(element.dataset.shotBox), told: element.dataset.shotSize,
    width: Math.round(element.clientWidth - across), height: Math.round(element.clientHeight - down) };
})`;

/** A tab in Edge: open a page at a size, measure it, check its fonts, shoot it. */
async function newTab(edge) {
  const { targetId } = await edge.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await edge.send("Target.attachToTarget", { targetId, flatten: true });
  const send = (method, params) => edge.send(method, params, sessionId);
  const evaluate = async (expression) => {
    const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
    return result.value;
  };
  await send("Page.enable");
  await send("DOM.enable");
  await send("CSS.enable");
  // In front, and focused, as a window being looked at is.
  await send("Page.bringToFront");
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });
  // Mado's own way with Windows' animation effects off: nothing moves, so nothing is caught midway.
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await send("Emulation.setDefaultBackgroundColorOverride", { color: { r: 0, g: 0, b: 0, a: 0 } });
  return {
    async open(path, { width, height, scale = 1, scheme = null }) {
      await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: scale, mobile: false });
      if (scheme) await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }, { name: "prefers-color-scheme", value: scheme }] });
      const url = pathToFileURL(path).href;
      await send("Page.navigate", { url });
      for (let waited = 0; (await evaluate("location.href")) !== url; waited += 50) {
        if (waited > 10_000) throw new Error(`Edge didn't open ${path}.`);
        await pause(50);
      }
      return evaluate(READY);
    },
    measure: () => evaluate(MEASURE),
    /** Every font of Windows' that draws words in the page's own fonts' place, with an example. */
    async strays() {
      const { root } = await send("DOM.getDocument", { depth: -1 });
      const holders = [];
      const walk = (node) => {
        if (node.nodeType === 1 && node.children?.some((kid) => kid.nodeType === 3 && kid.nodeValue.trim())) holders.push(node);
        for (const kid of node.children ?? []) walk(kid);
      };
      walk(root);
      const found = new Map();
      for (const holder of holders) {
        const { fonts } = await send("CSS.getPlatformFontsForNode", { nodeId: holder.nodeId });
        const words = holder.children.filter((kid) => kid.nodeType === 3).map((kid) => kid.nodeValue).join("").trim();
        for (const font of fonts)
          if (!font.isCustomFont && font.glyphCount > 0 && !found.has(font.familyName)) found.set(font.familyName, words.slice(0, 40));
      }
      return [...found].map(([font, words]) => ({ font, words }));
    },
    async shoot() {
      const { data } = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
      return Buffer.from(data, "base64");
    },
  };
}

/** Mado's fonts, loaded and drawing every word, or a clear stop (for another test's screens, a
 * warning): a screen in Segoe UI isn't Mado's. */
async function checkFonts(name, loaded, tab, strict) {
  for (const family of ["IBM Plex Sans Variable", "IBM Plex Mono"])
    if (!loaded.includes(family)) throw new Error(`${name} was drawn without ${family} (it had ${loaded.join(", ") || "no fonts"}).`);
  const stray = strayFonts(name, await tab.strays());
  if (stray && strict) throw new Error(stray);
  if (stray) console.warn(stray);
}

async function main() {
  const asked = parseArgs(process.argv.slice(2));
  const readme = !asked.screens;
  // Vitest runs in app/, so a test named from the repo's root loses its "app/".
  const test = (asked.screens ?? "src/test/readme-screens.test.tsx").replace(/^app[\\/]/, "");
  const out = resolve(asked.out ?? join(root, "docs", "readme"));
  const pictures = readme ? PICTURES.filter((each) => !asked.names.length || asked.names.includes(each.file.replace(/\.png$/, ""))) : [];

  if (asked.build) {
    console.log("Building the UI for its CSS and fonts…");
    run("pnpm build", { cwd: app });
  }
  const dist = join(app, "dist", "assets");
  const css = existsSync(dist) && readdirSync(dist).find((name) => name.endsWith(".css"));
  if (!css) throw new Error("app/dist has no CSS: build the UI first (cd app; pnpm build).");

  const work = mkdtempSync(join(tmpdir(), "mado-pictures-"));
  let edge = null;
  try {
    const screens = join(work, "screens");
    const site = join(work, "site");
    mkdirSync(screens, { recursive: true });
    cpSync(dist, join(site, "assets"), { recursive: true });
    writeFileSync(join(site, "assets", css), withFonts(readFileSync(join(dist, css), "utf8")));
    edge = await openEdge(join(work, "edge"));
    const tab = await newTab(edge);
    const pagesFor = (names) => {
      for (const name of names)
        for (const scheme of ["dark", "light"])
          writeFileSync(join(site, `${name}-${scheme}.html`), screenPage(readFileSync(join(screens, `${name}.html`), "utf8"), css, scheme));
    };

    console.log(`Drawing the screens (${test})…`);
    let names = drawScreens(test, screens);
    pagesFor(names);
    // The stages' space, measured where they're laid out, and the screens drawn again with it
    // till every one is told what it has.
    for (let take = 1; ; take++) {
      const kept = join(screens, "boxes.json");
      const boxes = existsSync(kept) ? JSON.parse(readFileSync(kept, "utf8")) : {};
      let again = false;
      for (const name of names) {
        await tab.open(join(site, `${name}-dark.html`), SCREEN);
        const sizes = boxesToRetake(await tab.measure());
        if (sizes) {
          boxes[name] = sizes;
          again = true;
        }
      }
      if (!again) break;
      if (take === 3) throw new Error("The screens' stages still measure differently after three takes.");
      writeFileSync(kept, JSON.stringify(boxes, null, 1));
      console.log("Drawing the screens again, with their stages' space as Edge lays them out…");
      names = drawScreens(test, screens);
      pagesFor(names);
    }

    mkdirSync(out, { recursive: true });
    if (!readme) {
      for (const name of names)
        for (const scheme of ["dark", "light"]) {
          await checkFonts(name, await tab.open(join(site, `${name}-${scheme}.html`), { ...SCREEN, scheme }), tab, false);
          writeFileSync(join(out, `${name}-${scheme}.png`), await tab.shoot());
          console.log(`  ${name}-${scheme}.png`);
        }
      return;
    }

    // Each screen at twice its size, which the frame then draws at the README's, smoothly.
    const shot = async (name, scheme) => {
      const file = join(site, `${name}-${scheme}@2x.png`);
      if (!existsSync(file)) {
        if (!names.includes(name)) throw new Error(`The screens test drew no screen called ${name}.`);
        await checkFonts(name, await tab.open(join(site, `${name}-${scheme}.html`), { ...SCREEN, scale: 2, scheme }), tab, true);
        writeFileSync(file, await tab.shoot());
      }
      return pathToFileURL(file).href;
    };
    for (const picture of pictures) {
      const dark = await shot(picture.screen, "dark");
      const light = picture.split ? await shot(picture.screen, "light") : null;
      const frame = join(site, `frame-${picture.file.replace(/\.png$/, "")}.html`);
      writeFileSync(frame, framePage({ dark, light, split: picture.split ?? null }));
      await tab.open(frame, { width: FRAME.width, height: FRAME.height });
      writeFileSync(join(out, picture.file), await tab.shoot());
      console.log(`  ${picture.file}`);
    }
  } finally {
    // Tidying up never hides what went wrong before it.
    try {
      await edge?.close();
    } catch (problem) {
      console.warn(`Edge didn't close cleanly: ${problem.message}`);
    }
    if (asked.keep) console.log(`The pages shot are in ${work}`);
    else
      try {
        rmSync(work, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
      } catch (problem) {
        console.warn(`Couldn't remove ${work}: ${problem.message}`);
      }
  }
}

/** Run as `node scripts/readme-pictures.mjs`, not imported by its tests: the same file, through a
 * link or a short name too. */
function runDirectly() {
  try {
    const real = (path) => realpathSync(path).toLowerCase();
    return real(resolve(process.argv[1] ?? "")) === real(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

if (runDirectly()) {
  main().catch((problem) => {
    console.error(problem.message);
    process.exitCode = 1;
  });
}
