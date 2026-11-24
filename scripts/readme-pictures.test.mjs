// Run with: node --test "scripts/*.test.mjs"
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  boxesToRetake,
  EDGE_SWITCHES,
  FRAME,
  framePage,
  PICTURES,
  parseArgs,
  SCREEN,
  screenPage,
  splitClip,
  strayFonts,
  withFonts,
} from "./readme-pictures.mjs";
import { drawScene, filterPrimitives, LOOKS, parseScene, placeScenes, SCENES, STYLES, sceneAddress } from "./readme-scenes.mjs";

describe("the README's pictures", () => {
  it("finds the built CSS's fonts beside it, not at the drive's root", () => {
    const css = `@font-face{src:url(/assets/ibm-plex-sans-latin-wght-normal-IvpUvPa2.woff2) format("woff2")}
@font-face{src:url("/assets/ibm-plex-mono-latin-400-normal-DMJ8VG8y.woff2")}.a{background:url(/elsewhere/x.png)}`;
    const fixed = withFonts(css);
    assert.match(fixed, /url\(ibm-plex-sans-latin-wght-normal-IvpUvPa2\.woff2\)/);
    assert.match(fixed, /url\("ibm-plex-mono-latin-400-normal-DMJ8VG8y\.woff2"\)/);
    assert.doesNotMatch(fixed, /\/assets\//);
    assert.match(fixed, /url\(\/elsewhere\/x\.png\)/); // only the build's own assets move
  });

  it("wraps a screen in the built CSS, in the scheme asked for, its scenes drawn", () => {
    const body = '<div class="flex"><img src="blob:scene/harbour" alt=""></div>';
    const dark = screenPage(body, "index-abc.css", "dark");
    const light = screenPage(body, "index-abc.css", "light");
    assert.match(dark, /<html lang="en" style="color-scheme: dark">/);
    assert.match(light, /<html lang="en" style="color-scheme: light">/);
    assert.match(dark, /<link rel="stylesheet" href="assets\/index-abc\.css">/);
    assert.match(dark, /<img src="data:image\/svg\+xml;base64,[A-Za-z0-9+/=]+" alt="">/);
    assert.doesNotMatch(dark, /blob:/);
  });

  it("frames the window as the README's are: 1216 across, rounded, with a soft shadow", () => {
    assert.deepEqual(SCREEN, { width: 1440, height: 960 });
    const { window: box } = FRAME;
    assert.equal(box.left * 2 + box.width, FRAME.width);
    assert.equal(box.height, Math.round((SCREEN.height * box.width) / SCREEN.width));
    assert.equal(box.top + box.height + 48, FRAME.height); // room below for the shadow
    const page = framePage({ dark: "home-dark.png", light: null, split: null });
    assert.match(page, /width: 1216px; height: 811px;/);
    assert.match(page, /border-radius: 14px;/);
    assert.match(page, /box-shadow: 0 10px 32px/);
    assert.match(page, /<img src="home-dark.png"/);
    assert.equal(page.match(/<img /g)?.length, 1);
    assert.match(page, /inset 0 0 0 1px #55565c/); // the dark edge only
  });

  it("cuts Home diagonally, the light half right of the line, each half with its own edge", () => {
    assert.equal(splitClip([720, 360]), "polygon(50% 0, 100% 0, 100% 100%, 25% 100%)");
    const page = framePage({ dark: "d.png", light: "l.png", split: [720, 360] });
    const light = page.slice(page.indexOf("polygon"));
    assert.match(light, /^polygon\(50% 0, 100% 0, 100% 100%, 25% 100%\)"><img src="l.png"/);
    assert.match(light, /#a6a7ad/);
    assert.ok(page.indexOf('src="d.png"') < page.indexOf('src="l.png"'), "light over dark");
  });

  it("names every picture the README shows, Home cut in two among them", () => {
    assert.deepEqual(
      PICTURES.map((each) => each.file),
      ["home.png", "size.png", "looks.png", "edit.png", "fix.png", "batch.png", "library.png", "wallpaper.png", "light-dark.png", "save.png"],
    );
    const split = PICTURES.find((each) => each.split);
    assert.equal(split?.screen, "home");
    for (const x of split?.split ?? []) assert.ok(x > 0 && x < SCREEN.width);
  });

  it("takes a screen again only when a stage it told a size is laid out otherwise", () => {
    const right = [
      { at: 0, told: "916x590", width: 916, height: 590 },
      { at: 1, told: "16x16", width: 16, height: 17 }, // a pixel's rounding is right enough
    ];
    assert.equal(boxesToRetake(right), null);
    const wrong = [
      { at: 1, told: "16x16", width: 16, height: 16 },
      { at: 0, told: "900x600", width: 916, height: 590 },
    ];
    assert.deepEqual(boxesToRetake(wrong), [
      { width: 916, height: 590 },
      { width: 16, height: 16 },
    ]);
    // One watched and gone before the screen was written isn't there to measure: it stays a guess.
    const gone = [{ at: 2, told: "900x600", width: 916, height: 654 }];
    assert.deepEqual(boxesToRetake(gone), [null, null, { width: 916, height: 654 }]);
  });

  it("starts Edge headless, on the processor, words in greys, signed out, without sync or extensions", () => {
    for (const flag of [
      "--headless=new",
      "--disable-gpu",
      "--disable-lcd-text",
      "--disable-features=msImplicitSignin",
      "--disable-sync",
      "--disable-extensions",
    ])
      assert.ok(EDGE_SWITCHES.includes(flag), flag);
  });

  it("reads which pictures to take, or another test's screens", () => {
    assert.deepEqual(parseArgs([]), { names: [], screens: null, out: null, build: true, keep: false });
    assert.deepEqual(parseArgs(["home", "size.png", "--no-build"]).names, ["home", "size"]);
    assert.equal(parseArgs(["--no-build"]).build, false);
    assert.equal(parseArgs(["--out", "C:\\pictures"]).out, "C:\\pictures"); // the README's, elsewhere
    assert.deepEqual(parseArgs(["--screens", "src/x.test.tsx", "--out", "C:\\shots", "--keep"]), {
      names: [],
      screens: "src/x.test.tsx",
      out: "C:\\shots",
      build: true,
      keep: true,
    });
    assert.throws(() => parseArgs(["homepage"]), /no picture called homepage/);
    assert.throws(() => parseArgs(["home", "--screens", "x"]), /not both/);
    assert.throws(() => parseArgs(["--fast"]), /doesn't know --fast/);
  });

  it("never puts another test's screens among the README's, nor takes a flag without its value", () => {
    assert.throws(() => parseArgs(["--screens", "src/x.test.tsx"]), /--screens needs --out/);
    assert.throws(() => parseArgs(["--screens"]), /--screens needs a value/);
    assert.throws(() => parseArgs(["--out"]), /--out needs a value/);
    assert.throws(() => parseArgs(["--screens", "--out", "C:\\shots"]), /--screens needs a value/);
    assert.throws(() => parseArgs(["--out", "--keep"]), /--out needs a value/);
  });

  it("says which of Windows' fonts drew words in Mado's place, with what they drew", () => {
    assert.equal(strayFonts("batch", []), null);
    assert.equal(
      strayFonts("batch", [{ font: "Consolas", words: "2.7 MB → 7.9 MB" }]),
      'batch has words in Consolas ("2.7 MB → 7.9 MB"), not Mado\'s own fonts: a glyph IBM Plex as Mado bundles it hasn\'t got?',
    );
  });
});

describe("the made-up scenes", () => {
  it("reads what's asked of a scene from its address", () => {
    assert.deepEqual(parseScene("harbour/look=warm-film/strength=.6/grain=20/vignette=35/part=sky"), {
      name: "harbour",
      style: null,
      paint: 1,
      look: "warm-film",
      strength: 0.6,
      grain: 20,
      vignette: 35,
      part: "sky",
      cutout: null,
      region: null,
      blur: 0,
      dark: 0,
      blocks: 0,
      bokeh: 0,
      focus: null,
      fog: 0,
      tilt: null,
      flip: false,
    });
    assert.deepEqual(parseScene("harbour/region=0.1,0.2,0.3,0.4/blur=1.5/flip"), {
      ...parseScene("harbour"),
      region: [0.1, 0.2, 0.3, 0.4],
      blur: 1.5,
      flip: true,
    });
    assert.throws(() => parseScene("harbour/sepia=1"), /can't be asked for "sepia=1"/);
  });

  it("draws each scene the boards draw, as an SVG that fills its place", () => {
    assert.equal(Object.keys(SCENES).length, 12);
    for (const name of Object.keys(SCENES)) {
      const svg = drawScene(name);
      assert.match(svg, /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" viewBox="0 0 400 300"/, name);
      assert.match(svg, /preserveAspectRatio="xMidYMid slice"/, name);
      assert.match(svg, /fill="url\(#sky\)"/, name);
    }
    assert.match(drawScene("garden-rose"), /<radialGradient id="sky" cx="200" cy="138" r="257"/);
    assert.throws(() => drawScene("beach"), /no scene called "beach"/);
  });

  it("gives every part shapes alone, as a clip takes nothing else", () => {
    for (const [name, scene] of Object.entries(SCENES))
      for (const [part, shape] of Object.entries(scene.parts)) {
        assert.doesNotMatch(shape, /<g[\s>]/, `${name}'s ${part}`);
        assert.match(shape, /^<(path|ellipse|circle|rect|polygon)\b/, `${name}'s ${part}`);
      }
  });

  it("puts a look on all of a scene, or only on a part, at its strength", () => {
    const whole = drawScene("misty-pines/look=warm-film/strength=.6");
    assert.match(whole, /<filter id="look" color-interpolation-filters="sRGB">/);
    assert.match(whole, /<g opacity="0.6"><g filter="url\(#look\)">/);
    assert.doesNotMatch(whole, /clipPath/);
    const sky = drawScene("harbour/look=warm-film/vignette=35/grain=20/part=sky");
    assert.match(sky, /<clipPath id="part"><path d="M0 0 L400 0/);
    assert.match(sky, /<g clip-path="url\(#part\)"><g><g filter="url\(#look\)">/);
    assert.match(sky, /stop-opacity="0.35"/);
    assert.match(sky, /<feTurbulence/);
    assert.throws(() => drawScene("harbour/look=sparkle"), /no look called "sparkle"/);
    assert.throws(() => drawScene("harbour/look=warm-film/part=boat"), /no part called "boat"/);
    for (const look of Object.keys(LOOKS)) assert.ok(drawScene(`harbour/look=${look}`), look);
  });

  it("paints a scene in a style before its look, at its strength, on all of it or a part", () => {
    assert.deepEqual(parseScene("harbour/style=monet/paint=.8"), {
      ...parseScene("harbour"),
      style: "monet",
      paint: 0.8,
    });
    const painted = drawScene("harbour/style=monet/paint=.8");
    assert.match(painted, /<filter id="style" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">/);
    assert.match(painted, /<g opacity="0.8"><g filter="url\(#style\)">/);
    // The look grades what's painted, and both go on just the part.
    const both = drawScene("harbour/style=hokusai/look=warm-film/part=sky");
    assert.equal(both.match(/<clipPath id="part">/g)?.length, 1);
    assert.match(both, /<g filter="url\(#look\)"><rect width="400" height="300" fill="url\(#sky\)"\/>[^]*<g filter="url\(#style\)">/);
    // One of the owner's styles is drawn as a picture's own.
    assert.match(drawScene("harbour/style=yours-3"), /<filter id="style"/);
    assert.throws(() => drawScene("harbour/style=klimt"), /no style called "klimt"/);
    for (const style of Object.keys(STYLES)) assert.ok(drawScene(`harbour/style=${style}`), style);
  });

  it("cuts out a part on nothing, blurs, mirrors, and shows a region stretched to its place", () => {
    const cut = drawScene("garden-rose/cutout=flower");
    assert.match(cut, /<clipPath id="cut"><ellipse cx="0" cy="-50" rx="22" ry="46" transform="translate\(200 146\) rotate\(0\)"\/>/);
    assert.match(cut, /<\/defs><g clip-path="url\(#cut\)">/);
    assert.match(drawScene("harbour/blur=2"), /<feGaussianBlur stdDeviation="2"\/>/);
    assert.match(drawScene("night-market/flip"), /<g transform="matrix\(-1 0 0 1 400 0\)">/);
    const region = drawScene("harbour/region=0.5,0.5,0.25,0.25");
    assert.match(region, /viewBox="200 150 100 75" width="100" height="75" preserveAspectRatio="none"/);
  });

  it("darkens a scene by stops and squeezes it into blocks, for a picture the Fix tab mends", () => {
    assert.deepEqual(parseScene("harbour/dark=3/blocks=6"), {
      ...parseScene("harbour"),
      dark: 3,
      blocks: 6,
    });
    const dark = drawScene("harbour/dark=3");
    assert.match(dark, /<filter id="dark" color-interpolation-filters="linearRGB">/);
    assert.match(dark, /<feFuncR type="linear" slope="0.125" intercept="0"\/>/);
    assert.match(dark, /<g filter="url\(#dark\)">/);
    const blocky = drawScene("harbour/blocks=6");
    assert.match(blocky, /<feFuncG type="discrete" tableValues="0 0.2 0.4 0.6 0.8 1"\/>/);
    assert.match(blocky, /<g filter="url\(#blocks\)">/);
  });

  it("blurs a scene but its part in focus, keeps a band in focus, and hazes it, for the Depth tab", () => {
    assert.deepEqual(parseScene("little-sail/bokeh=3/focus=boat/fog=60/tilt=0.4,0.6"), {
      ...parseScene("little-sail"),
      bokeh: 3,
      focus: "boat",
      fog: 60,
      tilt: [0.4, 0.6],
    });
    const portrait = drawScene("little-sail/bokeh=3/focus=boat");
    assert.match(portrait, /<filter id="bokeh"[^>]*><feGaussianBlur stdDeviation="3"\/><\/filter>/);
    assert.match(portrait, /<clipPath id="focus"><path d="M262 120/);
    assert.match(portrait, /<g filter="url\(#bokeh\)">[\s\S]*<\/g><g clip-path="url\(#focus\)">/);
    assert.throws(() => drawScene("harbour/bokeh=3/focus=boat"), /no part called "boat"/);
    const tilted = drawScene("harbour/tilt=0.5,0.7");
    assert.match(tilted, /<stop offset="0.4" stop-color="#fff" stop-opacity="0"\/><stop offset="0.5" stop-color="#fff"\/><stop offset="0.7" stop-color="#fff"\/><stop offset="0.8"/);
    assert.match(tilted, /<g filter="url\(#richer\)"><g filter="url\(#tilt\)">[\s\S]*<g mask="url\(#band-mask\)">/);
    const foggy = drawScene("harbour/fog=60");
    assert.match(foggy, /<stop offset="0" stop-color="#e4e8ec" stop-opacity="0.51"\/>/);
    assert.match(foggy, /<rect width="400" height="300" fill="url\(#fog\)"\/><\/svg>$/);
  });

  it("turns CSS filters into the Filter Effects spec's own matrices", () => {
    assert.equal(filterPrimitives("saturate(1.3)"), '<feColorMatrix type="saturate" values="1.3"/>');
    assert.equal(filterPrimitives("hue-rotate(-14deg)"), '<feColorMatrix type="hueRotate" values="-14"/>');
    assert.match(filterPrimitives("contrast(1.2)"), /<feFuncR type="linear" slope="1.2" intercept="-0.1"\/>/);
    assert.match(filterPrimitives("brightness(1.1)"), /<feFuncB type="linear" slope="1.1" intercept="0"\/>/);
    // Full sepia is the spec's matrix; none of it changes nothing.
    assert.match(filterPrimitives("sepia(1)"), /values="0.393 0.769 0.189 0 0 0.349 0.686 0.168 0 0 0.272 0.534 0.131 0 0 0 0 0 1 0"/);
    assert.match(filterPrimitives("grayscale(0)"), /values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 1 0"/);
    assert.equal(filterPrimitives("sepia(.3) saturate(1.3)").match(/<feColorMatrix/g)?.length, 2);
    assert.throws(() => filterPrimitives("blur(2px)"), /can't draw the filter blur/);
  });

  it("draws every scene a page shows in its place, in attributes and styles alike", () => {
    const page = `<img src="blob:scene/harbour"><image href="blob:scene/snowfield/look=silver"></image><div style="background: url(&quot;blob:scene/low-tide&quot;)"></div>`;
    const placed = placeScenes(page);
    assert.doesNotMatch(placed, /blob:/);
    assert.ok(placed.includes(`src="${sceneAddress("harbour")}"`));
    assert.ok(placed.includes(`href="${sceneAddress("snowfield/look=silver")}"`));
    assert.ok(placed.includes(`url(&quot;${sceneAddress("low-tide")}&quot;)`));
    assert.throws(() => placeScenes('<img src="blob:scene/missing">'), /no scene called "missing"/);
  });
});
