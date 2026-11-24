import { describe, expect, it } from "vitest";
import type { Part } from "@/lib/engine";
import { STYLES } from "@/test/engine";
import { keepsColours, networkOf, painted, stepFor, styleName } from "./painting";

const SKY: Part = { clicks: [{ x: 0.5, y: 0.2, keep: true }], choice: null };

describe("A painting style in a recipe", () => {
  it("goes on the parts the look goes on, and isn't a step at nothing", () => {
    const monet = stepFor("monet", null);

    expect(painted(monet, [])).toEqual(monet);
    expect(painted(monet, [SKY])).toEqual({ ...monet, parts: [SKY] });
    expect(painted({ ...monet, strength: 0 }, [SKY])).toBeNull();
    expect(painted(null, [SKY])).toBeNull();
  });

  it("keeps the strength and colours chosen as another is picked, a classic one at its own first setting", () => {
    const before = { ...stepFor("oil", null), strength: 0.6, colours: true, setting: 80 };

    expect(stepFor("hokusai", before)).toEqual({
      style: "hokusai",
      strength: 0.6,
      colours: true,
      setting: null,
    });
    expect(stepFor("picture", null, { code: "c3R5bGU=", named: "Night market" })).toEqual({
      style: "picture",
      strength: 1,
      colours: false,
      setting: null,
      code: "c3R5bGU=",
      named: "Night market",
    });
  });

  it("names Mado's and the owner's by their ids, and a picture's after it", () => {
    expect(styleName(stepFor("seurat", null), STYLES)).toBe("After Seurat");
    expect(styleName(stepFor("yours-1", null), STYLES)).toBe("Lantern glow");
    expect(
      styleName(stepFor("picture", null, { code: "c3R5bGU=", named: "Night market" }), STYLES),
    ).toBe("Night market style");
  });

  it("knows the network each paints with: a painter's own, MicroAST for a picture's, none drawn by code", () => {
    expect(networkOf(stepFor("van-gogh", null), STYLES)).toBe("style-van-gogh-starry-night");
    expect(networkOf(stepFor("yours-1", null), STYLES)).toBe("microast");
    expect(networkOf(stepFor("picture", null, { code: "c3R5bGU=" }), STYLES)).toBe("microast");
    expect(networkOf(stepFor("pencil", null), STYLES)).toBeNull();
    expect(keepsColours("cartoon", STYLES)).toBe(false);
    expect(keepsColours("monet", STYLES)).toBe(true);
  });
});
