import {describe, expect, it} from "vitest";
import {initialPuzzle, puzzleFrameSize, puzzleGridSize, puzzleTotalThickness, validatePuzzle} from "./PuzzleGenerator";

describe("generator puzzli", () => {
  it("starts with the recommended 100-piece, four-filament preset", () => {
    expect(initialPuzzle.width_mm).toBe(150);
    expect(initialPuzzle.height_mm).toBe(200);
    expect(initialPuzzle.piece_count).toBe(100);
    expect(initialPuzzle.color_count).toBe(4);
    expect(initialPuzzle.color_layout).toBe("layered");
    expect(initialPuzzle.available_colors).toHaveLength(20);
    expect(initialPuzzle.color_thickness_mm).toBe(.2);
    expect(puzzleTotalThickness(initialPuzzle)).toBeCloseTo(2.6);
  });

  it("uses one common color band in the AMS layout", () => {
    expect(puzzleTotalThickness({...initialPuzzle, color_layout: "same_layer"})).toBeCloseTo(2.2);
  });

  it("uses square piece grids", () => {
    expect(puzzleGridSize(36)).toBe(6);
    expect(puzzleGridSize(225)).toBe(15);
  });

  it("keeps the default frame on a 250 mm plate", () => {
    expect(puzzleFrameSize(initialPuzzle)).toEqual({width: 170, height: 220, printHeight: 227});
    expect(validatePuzzle(initialPuzzle)).toBe("");
  });

  it("rejects pieces smaller than 9 mm", () => {
    expect(validatePuzzle({...initialPuzzle, width_mm: 120, height_mm: 160, piece_count: 225})).toContain("9 mm");
  });

  it("rejects a frame larger than the target plate", () => {
    expect(validatePuzzle({...initialPuzzle, width_mm: 230, height_mm: 230})).toContain("250");
  });

  it("requires enough unique filament colors", () => {
    expect(validatePuzzle({...initialPuzzle, color_count: 4, available_colors: ["#000000", "#FFFFFF", "#FF0000"]})).toContain("co najmniej");
    expect(validatePuzzle({...initialPuzzle, available_colors: ["#000000", "#FFFFFF", "#FF0000", "#FF0000"]})).toContain("inny");
  });
});
