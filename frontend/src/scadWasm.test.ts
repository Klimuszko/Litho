import {describe, expect, it} from "vitest";
import {buildScadDefinitions, serializeScadValue} from "./scadWasm";

describe("OpenSCAD WASM parameter serialization", () => {
  it("serializes supported values", () => {
    expect(serializeScadValue(true, "boolean")).toBe("true");
    expect(serializeScadValue(8, "integer")).toBe("8");
    expect(serializeScadValue(1.25, "float")).toBe("1.25");
    expect(serializeScadValue('Fine "teeth"', "string")).toBe('"Fine \\"teeth\\""');
  });

  it("adds model mode when the module does not expose it", () => {
    expect(buildScadDefinitions([{name: "count", type: "integer"}], {count: 7})).toEqual([
      "-Dcount=7",
      '-Dmode="model"',
    ]);
  });
});
