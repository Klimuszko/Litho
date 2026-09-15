import { describe, expect, it } from "vitest";
import { Params, validateParams } from "./App";

const valid: Params = {width_mm: 100, height_mm: 75, min_thickness_mm: .8, max_thickness_mm: 3.2, gamma: 1, brightness: 1, contrast: 1, resolution: 180, orientation: "landscape", border_width_mm: 0, border_height_mm: 3.2, invert: false, mirror: false, crop: {x: 0, y: 0, width: 1, height: 1}};

describe("client parameter validation", () => {
  it("accepts calibrated defaults", () => expect(validateParams(valid)).toBe(""));
  it("rejects inverted thickness range", () => expect(validateParams({...valid, min_thickness_mm: 4})).toContain("większa"));
  it("rejects a frame below the relief", () => expect(validateParams({...valid, border_width_mm: 2, border_height_mm: 2})).toContain("Ramka"));
});
