// Turns Mado's design canvases' boards (.dc.html) into plain HTML pages in docs/design/,
// so every screen opens in a browser without the canvas.
//
//   node scripts/design-snapshot.mjs --<canvas> <folder> [--<canvas> <folder> ...]
//
// Each canvas as Claude's Artifact tool saves it: a folder holding project/canvas.json. Its Main
// board becomes docs/design/<canvas>.html and every other board docs/design/<canvas>/<board>.html;
// only the canvases given are written again. See docs/design/README.md.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

// Mado's canvases by name, each added here as it's drawn.
const CANVASES = {
  looks: "https://claude.ai/artifact/3te6hjNWp42cxk5EXcsDXv",
  screens: "https://claude.ai/artifact/TJcDDQ5XmVTNPMvRdE3Jfb",
};
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "docs", "design");
const today = new Date().toISOString().slice(0, 10);

const folders = foldersIn(process.argv.slice(2));
if (!folders) {
  const names = Object.keys(CANVASES).map((name) => `--${name} <folder>`);
  console.error(`Usage: node scripts/design-snapshot.mjs ${names.join(" ") || "--<canvas> <folder>"}`);
  process.exit(1);
}
let written = 0;

for (const [name, folder] of Object.entries(folders)) {
  const canvas = readCanvas(folder);
  mkdirSync(join(out, name), { recursive: true });
  for (const file of canvas.order) {
    const board = file.replace(".dc.html", "");
    const isMain = board === "Main";
    const link = (target) => {
      if (isMain) return `${name}/${target}.html`;
      return target === "Main" ? `../${name}.html` : `${target}.html`;
    };
    const page = toPage(canvas, file, { canvas: CANVASES[name], link });
    writeFileSync(join(out, isMain ? `${name}.html` : `${name}/${board}.html`), page);
    written += 1;
  }
}

console.log(`Wrote ${written} pages to ${out}`);

/** The canvases' folders by name (`--design <folder>`), or nothing when the arguments don't read. */
function foldersIn(args) {
  const found = {};
  for (let index = 0; index < args.length; index += 2) {
    const name = args[index].replace(/^--/, "");
    if (!(name in CANVASES) || !args[index + 1]) return null;
    found[name] = args[index + 1];
  }
  return Object.keys(found).length > 0 ? found : null;
}

function readCanvas(folder) {
  const index = JSON.parse(readFileSync(join(folder, "project", "canvas.json"), "utf8"));
  const source = (file) => readFileSync(join(folder, "project", file), "utf8");
  return { ...index, source };
}

function toPage(canvas, file, { canvas: url, link }) {
  const source = canvas.source(file);
  const title = canvas.boards[file]?.title ?? file;
  const helmet = source.match(/<helmet>([\s\S]*?)<\/helmet>/)?.[1] ?? "";
  // A board's own handlers (a drag, a ref) are the canvas's to run, not the page's.
  const board = source
    .match(/<x-dc>([\s\S]*?)<\/x-dc>/)[1]
    .replace(/<helmet>[\s\S]*?<\/helmet>/, "")
    .replace(/\s(?:ref|on[A-Z]\w*)="\{\{[^}]+\}\}"/g, "");
  const body = importBoards(canvas, expand(board, renderValues(source))).replace(
    /href="([\w.-]+)\.dc\.html"/g,
    (_, target) => `href="${link(target)}"`,
  );
  return `<!doctype html>
<!-- Mado design snapshot of "${title}" (${url}), taken ${today}.
     Change the canvas, then re-run scripts/design-snapshot.mjs; don't edit this file. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title} · Mado design</title>
${helmet.trim()}
</head>
<body>
${body.trim()}
</body>
</html>
`;
}

// A board placed inside another (`<dc-import name="Pic" kind="dusk" hint-size="92px,60px">`) is
// drawn in place, at the size the canvas gives it, its other attributes as its props.
function importBoards(canvas, html, depth = 0) {
  return html.replace(/<dc-import\b([^>]*)>\s*<\/dc-import>/g, (_, attributes) => {
    const found = Object.fromEntries(
      [...attributes.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, key, value]) => [key, value]),
    );
    const [width, height] = (found["hint-size"] ?? "100%,100%").split(",");
    const props = Object.fromEntries(Object.entries(found).filter(([key]) => key !== "name" && !key.startsWith("hint-")));
    const source = canvas.source(`${found.name}.dc.html`);
    const inner = source
      .match(/<x-dc>([\s\S]*?)<\/x-dc>/)[1]
      .replace(/<helmet>[\s\S]*?<\/helmet>/, "")
      .replace(/\s(?:ref|on[A-Z]\w*)="\{\{[^}]+\}\}"/g, "");
    const drawn = depth < 3 ? importBoards(canvas, expand(inner, renderValues(source, props)), depth + 1) : "";
    return `<div style="position:relative;width:${width};height:${height};overflow:hidden">${drawn}</div>`;
  });
}

// A board's script builds the data its template repeats over. It only computes
// values, so it runs in an empty sandbox with nothing but the base class it needs.
function renderValues(source, props = {}) {
  const script = source.match(/<script type="text\/x-dc"[^>]*>([\s\S]*?)<\/script>/)?.[1];
  if (!script) return {};
  const sandbox = vm.createContext({
    DCLogic: class {
      props = {};
    },
    props,
  });
  const run = `${script}\n;const component = new Component(); component.props = props; component.renderVals()`;
  return vm.runInContext(run, sandbox, { timeout: 1000 });
}

// Expands <sc-for>, <sc-if> and {{holes}} the way the canvas renders them.
function expand(html, scope) {
  let result = "";
  let rest = html;
  for (;;) {
    const open = rest.match(/<sc-(for|if)\b([^>]*)>/);
    if (!open) return result + fillHoles(rest, scope);
    const [tag, kind, attributes] = open;
    const close = findClose(rest, kind, open.index + tag.length);
    const inner = rest.slice(open.index + tag.length, close);
    const binding = (name) =>
      attributes.match(new RegExp(`${name}="\\{\\{([^}]+)\\}\\}"`))?.[1].trim();

    result += fillHoles(rest.slice(0, open.index), scope);
    if (kind === "for") {
      const as = attributes.match(/as="([^"]+)"/)[1];
      for (const item of lookup(scope, binding("list")) ?? []) {
        result += expand(inner, { ...scope, [as]: item });
      }
    } else if (lookup(scope, binding("value"))) {
      result += expand(inner, scope);
    }
    rest = rest.slice(close + `</sc-${kind}>`.length);
  }
}

function findClose(html, kind, from) {
  const tags = new RegExp(`<sc-${kind}\\b|</sc-${kind}>`, "g");
  tags.lastIndex = from;
  let depth = 1;
  for (let tag = tags.exec(html); tag; tag = tags.exec(html)) {
    depth += tag[0].startsWith("</") ? -1 : 1;
    if (depth === 0) return tag.index;
  }
  throw new Error(`<sc-${kind}> is never closed`);
}

function fillHoles(html, scope) {
  return html.replace(/\{\{([^}]+)\}\}/g, (_, path) => escapeHtml(lookup(scope, path.trim()) ?? ""));
}

function lookup(scope, path) {
  return path.split(".").reduce((value, key) => value?.[key], scope);
}

function escapeHtml(value) {
  const entities = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
  return String(value).replace(/[&<>"]/g, (character) => entities[character]);
}
