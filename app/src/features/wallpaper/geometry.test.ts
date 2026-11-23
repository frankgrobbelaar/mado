import { describe, expect, it } from "vitest";
import { areaOf, boundsOf, framed, laidAcross } from "./geometry";

describe("framed", () => {
  it("crops the biggest part with the target's shape around the subject", () => {
    const made = framed(
      4032,
      3024,
      [2560, 1440],
      "crop",
      { x: null, y: null, zoom: 1 },
      {
        x: 0.5,
        y: 0.4,
      },
    );

    expect(made.canvas.width).toBeCloseTo(4032);
    expect(made.canvas.height).toBeCloseTo((4032 * 1440) / 2560);
    expect(made.canvas.y + made.canvas.height / 2).toBeCloseTo(0.4 * 3024);
  });

  it("zooms into a smaller part around where the owner moved it, held inside the picture", () => {
    const near = framed(4032, 3024, [2560, 1440], "crop", { x: 0.25, y: 0.5, zoom: 2 }, null);
    expect(near.canvas.width).toBeCloseTo(2016);
    expect(near.canvas.x + near.canvas.width / 2).toBeCloseTo(1008);

    const edge = framed(4032, 3024, [2560, 1440], "crop", { x: 1, y: 0, zoom: 9 }, null);
    expect(edge.canvas.width).toBeCloseTo(1008); // held at four times nearer
    expect(edge.canvas.x + edge.canvas.width).toBeCloseTo(4032);
    expect(edge.canvas.y).toBeCloseTo(0);
  });

  it("extends a picture with all of it in the middle of the target's shape", () => {
    const made = framed(3000, 3000, [2560, 1440], "extend", { x: 0.1, y: 0.1, zoom: 3 }, null);

    expect(made.canvas.width / made.canvas.height).toBeCloseTo(2560 / 1440);
    expect(made.canvas.x).toBeCloseTo(-(made.canvas.width - 3000) / 2);
    expect(made.canvas.height).toBeCloseTo(3000);
  });
});

describe("laid across", () => {
  it("gives each monitor its part of the canvas where it sits", () => {
    const whole = boundsOf([
      { x: 0, y: 0, width: 2560, height: 1440 },
      { x: 2600, y: 0, width: 1920, height: 1080 },
    ]);
    expect(whole).toEqual({ x: 0, y: 0, width: 4520, height: 1440 });
    const canvas = { x: 0, y: 0, width: 9040, height: 2880 };

    const side = laidAcross(canvas, whole, { x: 2600, y: 0, width: 1920, height: 1080 });

    expect(side.x).toBeCloseTo(5200);
    expect(side.width).toBeCloseTo(3840);
    expect(areaOf(side, 9040, 2880).height).toBeCloseTo(0.75);
  });
});
