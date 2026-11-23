// The made-up pictures in the README's screens, drawn by code: the Mado Screens boards' own
// scenes (docs/design/screens/, the Pic board and the Library board's tiles), as SVG. The screens
// test asks for one by name and what's done to it ("harbour/look=warm-film/part=sky", see
// app/src/test/shots.ts); `placeScenes` draws each where the page shows it. Never a real photo.

/** Each scene: its sky (the boards' CSS gradient, from top to bottom), what's drawn on it in a
 * frame 400 by 300, and its parts, for a look or a cut-out on just that part. */
export const SCENES = {
  harbour: {
    sky: ["#2a2350 0", "#6f3c6c .36", "#e2784f .66", "#f5c16c .8"],
    body: `<circle cx="262" cy="198" r="32" fill="#ffd9a3"/>
<path d="M0 194 L52 180 L118 190 L182 170 L250 186 L322 172 L400 184 L400 216 L0 216 Z" fill="#4b2f5f"/>
<rect x="0" y="214" width="400" height="86" fill="#251c3b"/>
<rect x="228" y="224" width="66" height="3" rx="1.5" fill="#f3a86b" opacity=".75"/>
<rect x="240" y="234" width="44" height="2.5" rx="1.25" fill="#f3a86b" opacity=".55"/>
<rect x="250" y="244" width="26" height="2" rx="1" fill="#f3a86b" opacity=".4"/>
<rect x="18" y="205" width="168" height="5" fill="#140f23"/>
<rect x="38" y="205" width="4" height="34" fill="#140f23"/>
<rect x="92" y="205" width="4" height="34" fill="#140f23"/>
<rect x="146" y="205" width="4" height="34" fill="#140f23"/>
<circle cx="182" cy="198" r="3" fill="#ffd27a"/>`,
    parts: {
      sky: `<path d="M0 0 L400 0 L400 184 L322 172 L250 186 L182 170 L118 190 L52 180 L0 194 Z"/>`,
    },
  },
  "little-sail": {
    sky: ["#8fc1ee 0", "#d4eafb .62"],
    body: `<circle cx="90" cy="70" r="22" fill="#fff6d8" opacity=".9"/>
<rect x="0" y="168" width="400" height="132" fill="#3a7db4"/>
<rect x="0" y="206" width="400" height="94" fill="#2f6898"/>
<rect x="0" y="250" width="400" height="50" fill="#285b86"/>
<path d="M262 120 L262 162 L232 162 Z" fill="#ffffff"/>
<path d="M266 128 L266 162 L288 162 Z" fill="#eeeeee"/>
<path d="M228 164 L296 164 L288 174 L238 174 Z" fill="#7a4b2b"/>
<rect x="40" y="186" width="80" height="2" rx="1" fill="#cfe6f7" opacity=".7"/>
<rect x="300" y="224" width="70" height="2" rx="1" fill="#cfe6f7" opacity=".5"/>`,
    parts: {
      boat: `<path d="M262 120 L262 162 L232 162 Z M266 128 L266 162 L288 162 Z M228 164 L296 164 L288 174 L238 174 Z"/>`,
    },
  },
  "low-tide": {
    sky: ["#bfe2f2 0", "#e9f6fb .52"],
    body: `<circle cx="320" cy="64" r="18" fill="#fffbe6" opacity=".9"/>
<rect x="0" y="140" width="400" height="160" fill="#4ea2c6"/>
<path d="M0 196 Q50 186 100 196 T200 196 T300 196 T400 196 L400 300 L0 300 Z" fill="#7cc1dc"/>
<path d="M0 222 Q60 210 120 222 T240 222 T360 222 L400 220 L400 300 L0 300 Z" fill="#f4fbfd" opacity=".85"/>
<path d="M0 238 Q100 226 220 240 T400 236 L400 300 L0 300 Z" fill="#e8d2a6"/>`,
    parts: {},
  },
  "night-market": {
    sky: ["#0a0f25 0", "#1b2350 .64", "#3a2c5b 1"],
    body: `<circle cx="320" cy="62" r="16" fill="#f1ecd6"/>
<circle cx="327" cy="57" r="14" fill="#111838"/>
<circle cx="60" cy="40" r="1.2" fill="#ffffff"/>
<circle cx="140" cy="28" r="1" fill="#ffffff"/>
<circle cx="230" cy="48" r="1.3" fill="#ffffff"/>
<circle cx="380" cy="30" r="1" fill="#ffffff"/>
<rect x="10" y="150" width="46" height="150" fill="#0c0f1d"/>
<rect x="60" y="120" width="36" height="180" fill="#10142a"/>
<rect x="100" y="170" width="54" height="130" fill="#0c0f1d"/>
<rect x="158" y="96" width="40" height="204" fill="#121733"/>
<rect x="202" y="140" width="50" height="160" fill="#0c0f1d"/>
<rect x="256" y="112" width="34" height="188" fill="#10142a"/>
<rect x="294" y="160" width="58" height="140" fill="#0c0f1d"/>
<rect x="356" y="130" width="44" height="170" fill="#121733"/>
<rect x="18" y="162" width="5" height="7" fill="#ffd27a"/>
<rect x="32" y="180" width="5" height="7" fill="#ffd27a"/>
<rect x="68" y="134" width="5" height="7" fill="#9fd0ff"/>
<rect x="80" y="160" width="5" height="7" fill="#ffd27a"/>
<rect x="110" y="184" width="5" height="7" fill="#ffd27a"/>
<rect x="132" y="200" width="5" height="7" fill="#9fd0ff"/>
<rect x="166" y="110" width="5" height="7" fill="#ffd27a"/>
<rect x="180" y="140" width="5" height="7" fill="#ffd27a"/>
<rect x="166" y="170" width="5" height="7" fill="#9fd0ff"/>
<rect x="212" y="156" width="5" height="7" fill="#ffd27a"/>
<rect x="232" y="186" width="5" height="7" fill="#ffd27a"/>
<rect x="264" y="126" width="5" height="7" fill="#9fd0ff"/>
<rect x="276" y="150" width="5" height="7" fill="#ffd27a"/>
<rect x="304" y="176" width="5" height="7" fill="#ffd27a"/>
<rect x="330" y="200" width="5" height="7" fill="#9fd0ff"/>
<rect x="366" y="146" width="5" height="7" fill="#ffd27a"/>
<rect x="382" y="172" width="5" height="7" fill="#ffd27a"/>
<rect x="0" y="286" width="400" height="14" fill="#2a2140" opacity=".8"/>`,
    parts: {},
  },
  "still-lake": {
    sky: ["#eeaf79 0", "#f6d6b0 .48", "#a6bfcf .484", "#6d8ea7 1"],
    body: `<circle cx="230" cy="112" r="16" fill="#fff0d6" opacity=".9"/>
<path d="M0 145 L60 96 L110 128 L170 70 L230 120 L290 88 L350 126 L400 104 L400 145 Z" fill="#5a6a86"/>
<path d="M0 145 L60 194 L110 162 L170 220 L230 170 L290 202 L350 164 L400 186 L400 145 Z" fill="#5a6a86" opacity=".45"/>
<rect x="60" y="210" width="90" height="2" rx="1" fill="#e9f1f6" opacity=".5"/>
<rect x="230" y="240" width="110" height="2" rx="1" fill="#e9f1f6" opacity=".4"/>
<path d="M0 270 Q120 256 260 272 T400 266 L400 300 L0 300 Z" fill="#3b4a3a"/>`,
    parts: {},
  },
  "spring-meadow": {
    sky: ["#78b1e8 0", "#cde5fa .62"],
    body: `<ellipse cx="90" cy="64" rx="38" ry="14" fill="#ffffff" opacity=".92"/>
<ellipse cx="118" cy="56" rx="26" ry="14" fill="#ffffff" opacity=".92"/>
<ellipse cx="290" cy="90" rx="44" ry="13" fill="#ffffff" opacity=".85"/>
<path d="M0 190 Q120 160 240 182 T400 172 L400 300 L0 300 Z" fill="#86b552"/>
<path d="M0 230 Q160 198 400 226 L400 300 L0 300 Z" fill="#5f9640"/>
<circle cx="40" cy="252" r="3.5" fill="#f5d04a"/>
<circle cx="72" cy="270" r="3" fill="#ffffff"/>
<circle cx="104" cy="246" r="3.5" fill="#e86b8a"/>
<circle cx="138" cy="282" r="3.5" fill="#f5d04a"/>
<circle cx="170" cy="258" r="3" fill="#ffffff"/>
<circle cx="204" cy="276" r="3.5" fill="#e86b8a"/>
<circle cx="236" cy="250" r="3.5" fill="#f5d04a"/>
<circle cx="268" cy="286" r="3" fill="#ffffff"/>
<circle cx="300" cy="262" r="3.5" fill="#f5d04a"/>
<circle cx="334" cy="278" r="3.5" fill="#e86b8a"/>
<circle cx="366" cy="254" r="3" fill="#ffffff"/>
<circle cx="388" cy="284" r="3.5" fill="#f5d04a"/>`,
    parts: {},
  },
  snowfield: {
    sky: ["#4f86d2 0", "#9ec2ec .58", "#e3edf7 1"],
    body: `<path d="M0 205 L64 130 L118 172 L186 78 L248 150 L300 108 L360 160 L400 140 L400 300 L0 300 Z" fill="#8199bb"/>
<path d="M186 78 L168 104 L180 100 L188 110 L196 99 L206 106 Z" fill="#f4f7fb"/>
<path d="M300 108 L286 126 L297 123 L304 131 L312 121 Z" fill="#f4f7fb"/>
<path d="M64 130 L52 146 L62 143 L70 150 L76 141 Z" fill="#f4f7fb"/>
<path d="M0 246 L84 176 L146 216 L228 150 L316 226 L400 196 L400 300 L0 300 Z" fill="#46597a"/>
<path d="M228 150 L212 168 L224 165 L232 174 L242 163 Z" fill="#eef3f8"/>
<path d="M0 266 Q200 238 400 260 L400 300 L0 300 Z" fill="#3d5537"/>`,
    parts: {},
  },
  "misty-pines": {
    sky: ["#cdd8cd 0", "#eef2ea .7"],
    body: `<path d="M0 170 L14 146 L28 170 L40 140 L54 170 L68 150 L82 170 L96 138 L110 170 L124 148 L138 170 L152 142 L166 170 L180 150 L194 170 L208 136 L222 170 L236 148 L250 170 L264 140 L278 170 L292 150 L306 170 L320 142 L334 170 L348 148 L362 170 L376 140 L390 170 L400 158 L400 300 L0 300 Z" fill="#a3b6a6"/>
<path d="M0 206 L18 172 L36 206 L52 166 L70 206 L88 176 L106 206 L124 162 L142 206 L160 174 L178 206 L196 168 L214 206 L232 178 L250 206 L268 164 L286 206 L304 176 L322 206 L340 166 L358 206 L376 178 L394 206 L400 200 L400 300 L0 300 Z" fill="#62836c"/>
<path d="M0 252 L24 204 L48 252 L70 196 L94 252 L118 210 L142 252 L166 198 L190 252 L214 208 L238 252 L262 192 L286 252 L310 206 L334 252 L358 200 L382 252 L400 228 L400 300 L0 300 Z" fill="#2f4b3a"/>
<rect x="0" y="252" width="400" height="48" fill="#26402f"/>`,
    parts: {},
  },
  "red-canyon": {
    sky: ["#8cc3e7 0", "#d4ebf7 .6"],
    body: `<path d="M0 120 L80 118 L96 150 L150 148 L160 176 L0 180 Z" fill="#c9673a"/>
<path d="M400 110 L310 112 L296 146 L250 148 L236 182 L400 186 Z" fill="#c25f33"/>
<path d="M0 150 L96 150" stroke="#e08a58" stroke-width="2"/>
<path d="M400 146 L296 146" stroke="#df8653" stroke-width="2"/>
<path d="M0 180 L160 176 L176 214 L120 300 L0 300 Z" fill="#9a4423"/>
<path d="M400 186 L236 182 L222 222 L270 300 L400 300 Z" fill="#8f3e1f"/>
<path d="M176 214 Q200 250 150 300 L270 300 Q230 262 222 222 Z" fill="#4c8db2"/>`,
    parts: {},
  },
  "warm-dunes": {
    sky: ["#f2d2a0 0", "#f8e7cb .6"],
    body: `<circle cx="300" cy="80" r="20" fill="#fff4dc"/>
<path d="M0 170 Q90 130 180 168 T400 150 L400 300 L0 300 Z" fill="#e3ab6a"/>
<path d="M0 214 Q110 168 230 210 T400 196 L400 300 L0 300 Z" fill="#cd8b4d"/>
<path d="M0 258 Q140 214 280 254 T400 246 L400 300 L0 300 Z" fill="#b2713c"/>
<path d="M180 168 Q230 190 300 186" stroke="#f3c88f" stroke-width="2" fill="none" opacity=".7"/>`,
    parts: {},
  },
  "green-sky": {
    sky: ["#040d18 0", "#0b2131 .6", "#12303f 1"],
    body: `<circle cx="40" cy="30" r="1.2" fill="#ffffff" opacity=".8"/>
<circle cx="110" cy="54" r="1" fill="#ffffff" opacity=".8"/>
<circle cx="170" cy="22" r="1.3" fill="#ffffff" opacity=".8"/>
<circle cx="250" cy="40" r="1" fill="#ffffff" opacity=".8"/>
<circle cx="330" cy="24" r="1.4" fill="#ffffff" opacity=".8"/>
<circle cx="372" cy="60" r="1" fill="#ffffff" opacity=".8"/>
<path d="M0 120 C60 60 120 150 190 90 S320 50 400 110 L400 150 C320 100 260 170 190 130 S70 120 0 170 Z" fill="#3cf0a6" opacity=".35"/>
<path d="M0 100 C80 50 150 120 220 70 S340 40 400 80 L400 105 C330 70 270 120 210 98 S90 90 0 130 Z" fill="#84f6d4" opacity=".25"/>
<path d="M0 230 L70 180 L130 214 L200 160 L270 210 L330 176 L400 214 L400 300 L0 300 Z" fill="#071019"/>`,
    parts: {},
  },
  "garden-rose": {
    // The board's sky here is round: radial-gradient(circle at 50% 46%, #2e3f2b 0%, #141c12 70%).
    sky: { round: [200, 138, 257], stops: ["#2e3f2b 0", "#141c12 .7"] },
    body: `<ellipse cx="90" cy="250" rx="70" ry="18" fill="#3f6b3a" transform="rotate(-24 90 250)"/>
<ellipse cx="318" cy="246" rx="70" ry="18" fill="#365f33" transform="rotate(22 318 246)"/>
<g transform="translate(200 146)">${petals()}
<circle cx="0" cy="0" r="20" fill="#f6cf4d"/>
<circle cx="0" cy="0" r="11" fill="#e8a63a"/>
</g>`,
    parts: {
      // A clip holds shapes only, never a group: each petal is placed itself.
      flower: `${[0, 45, 90, 135, 180, 225, 270, 315]
        .map((turn) => `<ellipse cx="0" cy="-50" rx="22" ry="46" transform="translate(200 146) rotate(${turn})"/>`)
        .join("")}<circle cx="200" cy="146" r="20"/>`,
    },
  },
};

function petals() {
  return [0, 45, 90, 135, 180, 225, 270, 315]
    .map(
      (turn, at) =>
        `<ellipse cx="0" cy="-50" rx="22" ry="46" fill="${at % 2 ? "#f7c3d4" : "#f29bb6"}" transform="rotate(${turn})"/>`,
    )
    .join("");
}

/** Mado's looks as the Looks board draws them, CSS filters on the picture (the five the board
 * hasn't, Mado's own, drawn the same way). */
export const LOOKS = {
  "warm-film": "sepia(.3) saturate(1.3) contrast(1.06) brightness(1.03)",
  "cool-film": "hue-rotate(-14deg) saturate(.85) brightness(1.05)",
  faded: "contrast(.82) saturate(.75) brightness(1.1)",
  "teal-and-orange": "saturate(1.4) hue-rotate(-8deg) contrast(1.12)",
  silver: "grayscale(1) contrast(1.15)",
  "golden-hour": "sepia(.45) saturate(1.5) brightness(1.08)",
  "night-neon": "hue-rotate(40deg) saturate(1.8) contrast(1.15)",
  duotone: "grayscale(1) sepia(1) hue-rotate(190deg) saturate(2.2)",
  "bold-colour": "saturate(1.6) contrast(1.08)",
  "sepia-print": "sepia(.9) contrast(1.05) brightness(1.02)",
  "moody-blue": "sepia(.25) hue-rotate(175deg) saturate(.8) brightness(.9)",
  "cross-processed": "contrast(1.15) saturate(1.3) hue-rotate(-12deg)",
  "soft-pastel": "contrast(.82) saturate(.8) brightness(1.12)",
};

const round = (value) => Number(value.toFixed(4));

/** A CSS filter ("sepia(.3) saturate(1.3)") as SVG filter primitives, by the matrices the
 * Filter Effects spec gives each function. */
export function filterPrimitives(css) {
  const out = [];
  for (const [, name, raw] of css.matchAll(/([a-z-]+)\(([^)]*)\)/g)) {
    const amount = Number.parseFloat(raw);
    const rest = 1 - Math.min(Math.max(amount, 0), 1);
    const matrix = (rows) =>
      out.push(`<feColorMatrix type="matrix" values="${rows.flat().map(round).join(" ")}"/>`);
    const linear = (slope, intercept) =>
      out.push(
        `<feComponentTransfer>${["R", "G", "B"]
          .map((c) => `<feFunc${c} type="linear" slope="${round(slope)}" intercept="${round(intercept)}"/>`)
          .join("")}</feComponentTransfer>`,
      );
    switch (name) {
      case "saturate":
        out.push(`<feColorMatrix type="saturate" values="${round(amount)}"/>`);
        break;
      case "hue-rotate":
        out.push(`<feColorMatrix type="hueRotate" values="${round(amount)}"/>`);
        break;
      case "grayscale":
        matrix([
          [0.2126 + 0.7874 * rest, 0.7152 - 0.7152 * rest, 0.0722 - 0.0722 * rest, 0, 0],
          [0.2126 - 0.2126 * rest, 0.7152 + 0.2848 * rest, 0.0722 - 0.0722 * rest, 0, 0],
          [0.2126 - 0.2126 * rest, 0.7152 - 0.7152 * rest, 0.0722 + 0.9278 * rest, 0, 0],
          [0, 0, 0, 1, 0],
        ]);
        break;
      case "sepia":
        matrix([
          [0.393 + 0.607 * rest, 0.769 - 0.769 * rest, 0.189 - 0.189 * rest, 0, 0],
          [0.349 - 0.349 * rest, 0.686 + 0.314 * rest, 0.168 - 0.168 * rest, 0, 0],
          [0.272 - 0.272 * rest, 0.534 - 0.534 * rest, 0.131 + 0.869 * rest, 0, 0],
          [0, 0, 0, 1, 0],
        ]);
        break;
      case "brightness":
        linear(amount, 0);
        break;
      case "contrast":
        linear(amount, 0.5 - 0.5 * amount);
        break;
      default:
        throw new Error(`The scenes can't draw the filter ${name}().`);
    }
  }
  return out.join("");
}

/** What's asked of a scene, from its address ("harbour/look=warm-film/strength=.6/part=sky"). */
export function parseScene(spec) {
  const [name, ...asks] = decodeURIComponent(spec).split("/");
  const scene = {
    name,
    look: null,
    strength: 1,
    grain: 0,
    vignette: 0,
    part: null,
    cutout: null,
    region: null,
    blur: 0,
    dark: 0,
    blocks: 0,
    flip: false,
  };
  for (const ask of asks) {
    const [key, value = ""] = ask.split("=");
    if (key === "look") scene.look = value;
    else if (["strength", "grain", "vignette", "blur", "dark", "blocks"].includes(key))
      scene[key] = Number(value);
    else if (key === "part") scene.part = value;
    else if (key === "cutout") scene.cutout = value;
    else if (key === "region") scene.region = value.split(",").map(Number);
    else if (key === "flip") scene.flip = true;
    else throw new Error(`A scene can't be asked for "${ask}" (${spec}).`);
  }
  return scene;
}

/** The scene as an SVG document: its sky and drawing, with a look at a strength and finishing
 * touches (grain and a vignette, 0 to 100), on all of it or a part; cut out (only a part, on
 * nothing); blurred (a picture only stretched, or shaken); its colours squeezed into `blocks`
 * steps (a JPEG saved small); darkened by `dark` stops; a region of it (fractions of the picture:
 * x, y, width, height); or mirrored, a scene twice over looking like two. */
export function drawScene(spec) {
  const asked = parseScene(spec);
  const scene = SCENES[asked.name];
  if (!scene) throw new Error(`There's no scene called "${asked.name}" (${spec}).`);
  const defs = [skyOf(scene.sky)];
  const part = (name) => {
    const shape = scene.parts[name];
    if (!shape) throw new Error(`The scene "${asked.name}" has no part called "${name}".`);
    return shape;
  };
  const plain = `<rect width="400" height="300" fill="url(#sky)"/>${scene.body}`;
  let picture = plain;
  let looked = "";
  if (asked.look) {
    const css = LOOKS[asked.look];
    if (!css) throw new Error(`There's no look called "${asked.look}" (${spec}).`);
    defs.push(`<filter id="look" color-interpolation-filters="sRGB">${filterPrimitives(css)}</filter>`);
    const strength = asked.strength < 1 ? ` opacity="${asked.strength}"` : "";
    looked += `<g${strength}><g filter="url(#look)">${plain}</g></g>`;
  }
  if (asked.vignette > 0) {
    defs.push(
      `<radialGradient id="vignette" cx="200" cy="150" r="250" gradientUnits="userSpaceOnUse"><stop offset=".5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="${round(asked.vignette / 100)}"/></radialGradient>`,
    );
    looked += `<rect width="400" height="300" fill="url(#vignette)"/>`;
  }
  if (asked.grain > 0) {
    defs.push(
      `<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="1.4" numOctaves="2" seed="7"/><feColorMatrix type="saturate" values="0"/></filter>`,
    );
    looked += `<rect width="400" height="300" filter="url(#grain)" opacity="${round(asked.grain / 250)}"/>`;
  }
  if (looked) {
    if (asked.part) defs.push(`<clipPath id="part">${part(asked.part)}</clipPath>`);
    picture += asked.part ? `<g clip-path="url(#part)">${looked}</g>` : looked;
  }
  if (asked.cutout) {
    defs.push(`<clipPath id="cut">${part(asked.cutout)}</clipPath>`);
    picture = `<g clip-path="url(#cut)">${picture}</g>`;
  }
  if (asked.blur > 0) {
    defs.push(`<filter id="soft" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="${asked.blur}"/></filter>`);
    picture = `<g filter="url(#soft)">${picture}</g>`;
  }
  if (asked.blocks > 1) {
    // A picture saved small: its colours squeezed into few steps, as a JPEG's blocks flatten them.
    const steps = Array.from({ length: asked.blocks }, (_, at) => round(at / (asked.blocks - 1))).join(" ");
    const funcs = ["R", "G", "B"].map((c) => `<feFunc${c} type="discrete" tableValues="${steps}"/>`).join("");
    defs.push(`<filter id="blocks" color-interpolation-filters="sRGB"><feComponentTransfer>${funcs}</feComponentTransfer></filter>`);
    picture = `<g filter="url(#blocks)">${picture}</g>`;
  }
  if (asked.dark > 0) {
    // An exposure cut in linear light, by stops, as a camera given too little light.
    const slope = round(2 ** -asked.dark);
    const funcs = ["R", "G", "B"].map((c) => `<feFunc${c} type="linear" slope="${slope}" intercept="0"/>`).join("");
    defs.push(`<filter id="dark" color-interpolation-filters="linearRGB"><feComponentTransfer>${funcs}</feComponentTransfer></filter>`);
    picture = `<g filter="url(#dark)">${picture}</g>`;
  }
  if (asked.flip) picture = `<g transform="matrix(-1 0 0 1 400 0)">${picture}</g>`;
  const [x, y, width, height] = asked.region ?? [0, 0, 1, 1];
  const box = [x * 400, y * 300, width * 400, height * 300].map(round).join(" ");
  // A region is the picture's own pixels, stretched to the box it's shown in; the whole picture
  // keeps its shape.
  const fit = asked.region ? "none" : "xMidYMid slice";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box}" width="${round(width * 400)}" height="${round(height * 300)}" preserveAspectRatio="${fit}"><defs>${defs.join("")}</defs>${picture}</svg>`;
}

function skyOf(sky) {
  const stops = (list) =>
    list
      .map((stop) => {
        const [colour, at] = stop.split(" ");
        return `<stop offset="${at}" stop-color="${colour}"/>`;
      })
      .join("");
  if (Array.isArray(sky))
    return `<linearGradient id="sky" x1="0" y1="0" x2="0" y2="300" gradientUnits="userSpaceOnUse">${stops(sky)}</linearGradient>`;
  const [cx, cy, r] = sky.round;
  return `<radialGradient id="sky" cx="${cx}" cy="${cy}" r="${r}" gradientUnits="userSpaceOnUse">${stops(sky.stops)}</radialGradient>`;
}

/** A scene as an address an image can show. */
export function sceneAddress(spec) {
  return `data:image/svg+xml;base64,${Buffer.from(drawScene(spec)).toString("base64")}`;
}

/** Every scene a page shows ("blob:scene/…", in an attribute or a style), drawn in its place. */
export function placeScenes(html) {
  return html.replace(/blob:scene\/([^"'&)\s]+)/g, (_, spec) => sceneAddress(spec));
}
