import { describe, expect, it } from "vitest";
import { automaticCrop, effectiveGrid, imageArea, panCrop, Params, rotatedSize, validateParams, zoomCrop, zoomCropAt } from "./App";

const valid: Params = {width_mm: 150, height_mm: 100, min_thickness_mm: .8, max_thickness_mm: 3.2, gamma: 1, brightness: 1, contrast: 1, nozzle_diameter_mm: .4, quality_profile: "optimal", orientation: "landscape", border_width_mm: 0, border_height_mm: 3.2, removable_support: false, invert: false, mirror: false, rotation_degrees: 0, crop: {x: 0, y: 0, width: 1, height: 1}};

describe("client parameter validation", () => {
  it("accepts calibrated defaults", () => expect(validateParams(valid)).toBe(""));
  it("rejects inverted thickness range", () => expect(validateParams({...valid, min_thickness_mm: 4})).toContain("większa"));
  it("rejects a frame below the relief", () => expect(validateParams({...valid, border_width_mm: 2, border_height_mm: 2})).toContain("Ramka"));
  it("accepts the largest format with a 20 mm frame", () => expect(validateParams({...valid, width_mm: 200, height_mm: 150, border_width_mm: 20})).toBe(""));
  it("accepts a custom size", () => expect(validateParams({...valid, width_mm: 160})).toBe(""));
  it("rejects a custom size outside the build envelope", () => expect(validateParams({...valid, width_mm: 257})).toContain("256"));
});

describe("direct crop interactions", () => {
  it("clamps dragging to image bounds", () => expect(panCrop({x: .2, y: .2, width: .5, height: .5}, 1, -1)).toEqual({x: .5, y: 0, width: .5, height: .5}));
  it("swaps source dimensions for quarter turns", () => expect(rotatedSize({width: 400, height: 200}, 90)).toEqual({width: 200, height: 400}));
  it("keeps source dimensions for a half turn", () => expect(rotatedSize({width: 400, height: 200}, 180)).toEqual({width: 400, height: 200}));
  it("keeps the source point under the cursor while zooming", () => {
    const current = {x: .1, y: .2, width: .8, height: .6};
    const zoomed = zoomCropAt(current, current, 2, .25, .75);
    expect(zoomed.x + zoomed.width * .25).toBeCloseTo(current.x + current.width * .25);
    expect(zoomed.y + zoomed.height * .75).toBeCloseTo(current.y + current.height * .75);
  });
});

describe("automatic crop", () => {
  it("crops the sides of a wide photo", () => expect(automaticCrop(400, 200, 150, 100)).toEqual({x: .125, y: 0, width: .75, height: 1}));
  it("crops the top and bottom of a tall photo", () => expect(automaticCrop(200, 400, 100, 150)).toEqual({x: 0, y: .125, width: 1, height: .75}));
  it("keeps the full frame when the photo already matches the preset", () => expect(automaticCrop(300, 200, 150, 100)).toEqual({x: 0, y: 0, width: 1, height: 1}));
});

describe("zoom crop", () => {
  const base = {x: .125, y: 0, width: .75, height: 1};

  it("scales width and height by the same factor, preserving aspect ratio", () => {
    const zoomed = zoomCrop(base, base, 2);
    expect(zoomed.width).toBeCloseTo(.375);
    expect(zoomed.height).toBeCloseTo(.5);
    expect(zoomed.width / zoomed.height).toBeCloseTo(base.width / base.height);
  });

  it("re-centers on the current pan position rather than the base crop", () => {
    const pannedLeft = {...base, x: 0};
    const centered = zoomCrop(base, base, 2);
    const zoomed = zoomCrop(base, pannedLeft, 2);
    expect(zoomed.x).toBeLessThan(centered.x);
  });

  it("clamps the pan so the crop never leaves the image bounds", () => {
    const panned = {...base, x: 1 - base.width};
    const zoomed = zoomCrop(base, panned, 1.2);
    expect(zoomed.x + zoomed.width).toBeLessThanOrEqual(1 + 1e-9);
    expect(zoomed.x).toBeGreaterThanOrEqual(0);
  });

  it("staying at zoom 1 returns the base crop", () => expect(zoomCrop(base, base, 1)).toEqual(base));
});

describe("effective mesh grid", () => {
  it("keeps the requested grid when it fits", () => {
    expect(effectiveGrid(150, 100, .25, 0)).toMatchObject({cols: 601, rows: 401});
  });

  it("counts the frame in the global memory budget", () => {
    const grid = effectiveGrid(200, 150, .1, 20);
    expect(grid.totalCols * grid.totalRows).toBeLessThanOrEqual(3_100_000);
    expect(grid.cols).toBeLessThan(2001);
  });
});

describe("frame dimensions", () => {
  it("takes the frame from inside the selected final format", () => {
    expect(imageArea(150, 100, 4)).toEqual({width: 142, height: 92});
  });
});
