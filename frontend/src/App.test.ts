import { describe, expect, it } from "vitest";
import { automaticCrop, effectiveBorderHeight, effectiveGrid, imageArea, initial, inscribedSize, panCrop, Params, resolvedBorders, rotatedSize, validateParams, zoomCrop, zoomCropAt } from "./App";
import { housingClipCount, housingOuterSize, initialHousing, validateHousing } from "./HousingGenerator";

const valid: Params = {width_mm: 150, height_mm: 100, min_thickness_mm: .8, max_thickness_mm: 3, gamma: 1, brightness: 1, contrast: 1, nozzle_diameter_mm: .4, quality_profile: "optimal", orientation: "landscape", border_width_mm: 0, border_widths_mm: null, border_height_mm: 3, mounting_flange: false, removable_support: false, invert: false, mirror: false, rotation_degrees: 0, crop: {x: 0, y: 0, width: 1, height: 1}};

describe("client parameter validation", () => {
  it("uses a modest default contrast boost", () => expect(initial.contrast).toBe(1.25));
  it("shows an uploaded photo without a creative mirror by default", () => expect(initial.mirror).toBe(false));
  it("accepts calibrated defaults", () => expect(validateParams(valid)).toBe(""));
  it("rejects inverted thickness range", () => expect(validateParams({...valid, min_thickness_mm: 4})).toContain("większa"));
  it("accepts a lightweight frame below the relief", () => expect(validateParams({...valid, border_width_mm: 2, border_height_mm: .8})).toBe(""));
  it("rejects a frame thinner than two nozzle widths", () => expect(validateParams({...valid, border_width_mm: 2, border_height_mm: .7})).toContain("0.8"));
  it("accepts the largest format with a 20 mm frame", () => expect(validateParams({...valid, width_mm: 200, height_mm: 150, border_width_mm: 20})).toBe(""));
  it("accepts a custom size", () => expect(validateParams({...valid, width_mm: 160})).toBe(""));
  it("rejects a custom size outside the build envelope", () => expect(validateParams({...valid, width_mm: 257})).toContain("256"));
  it("uses the fixed mounting flange without overwriting manual frame values", () => {
    const flange = {...valid, mounting_flange: true, border_width_mm: 8, border_height_mm: .7};
    expect(resolvedBorders(flange)).toEqual({top: 2, right: 2, bottom: 2, left: 2});
    expect(effectiveBorderHeight(flange)).toBe(1.6);
    expect(validateParams(flange)).toBe("");
    expect(flange.border_width_mm).toBe(8);
    expect(flange.border_height_mm).toBe(.7);
  });
});

describe("direct crop interactions", () => {
  it("clamps dragging to image bounds", () => expect(panCrop({x: .2, y: .2, width: .5, height: .5}, 1, -1)).toEqual({x: .5, y: 0, width: .5, height: .5}));
  it("swaps source dimensions for quarter turns", () => expect(rotatedSize({width: 400, height: 200}, 90)).toEqual({width: 200, height: 400}));
  it("keeps source dimensions for a half turn", () => expect(rotatedSize({width: 400, height: 200}, 180)).toEqual({width: 400, height: 200}));
  it("supports arbitrary rotation without empty corners", () => {
    const result = inscribedSize(400, 300, 17.5);
    expect(result.width).toBeCloseTo(355.581, 2);
    expect(result.height).toBeCloseTo(202.444, 2);
  });
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
  it("subtracts every custom border side from the final format", () => {
    expect(imageArea(150, 100, {top: 2, right: 4, bottom: 6, left: 8})).toEqual({width: 138, height: 92});
  });
});

describe("housing generator", () => {
  it("treats preset dimensions as the exact lithophane panel size", () => {
    expect(housingOuterSize(initialHousing)).toEqual({width: 155.6, height: 105.6});
    expect(housingOuterSize({...initialHousing, kind: "frame"})).toEqual({width: 174, height: 124});
  });
  it("rejects a frame that exceeds the 256 mm bed", () => {
    expect(validateHousing({...initialHousing, kind: "frame", panel_width_mm: 240})).toContain("256");
  });
  it("uses four clips for the small panel and six for larger formats", () => {
    expect(housingClipCount(initialHousing)).toBe(4);
    expect(housingClipCount({...initialHousing, panel_width_mm: 180})).toBe(6);
  });
});
