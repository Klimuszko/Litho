import test from "node:test";
import assert from "node:assert/strict";
import { FITS, axialDesign, evaluateCase, sampleCurve, TAU } from "./oracle.mjs";

const cases = [
  ...[0.03, 0.04, 0.05].map(e1 => ({ lobes: 4, e1 })),
  ...[0.04, 0.06, 0.08].map(e1 => ({ lobes: 3, e1 })),
];

test("1: obwód i stała podziałka są okresowe", () => {
  for (const c of cases) {
    const curve = sampleCurve({ radius: 18, ...c });
    const perLobe = curve.length / c.lobes;
    assert.ok(Math.abs(perLobe * c.lobes - curve.length) < 1e-10);
    const teethPerLobe = Math.round(perLobe / Math.PI);
    const module = perLobe / (Math.PI * teethPerLobe);
    assert.ok(module >= 0.6 && module <= 1.6);
  }
});

test("2–3: wstępna kinematyka centroid i domknięcie", () => {
  for (const c of cases) {
    const r = evaluateCase({ ...c, samples: 2048 });
    assert.ok(r.closureError < 1e-8, JSON.stringify(r));
    assert.ok(Math.abs(r.k - 1) <= 0.005, JSON.stringify(r));
    assert.ok(r.orbitBreathing <= 0.01, JSON.stringify(r));
    assert.ok(r.curvature.finite && r.curvature.minConvex >= 2.5, JSON.stringify(r));
  }
});

test("7a: algebra przekroju dwóch pasów, kanału, rampy i retencji", () => {
  for (const fit of FITS) {
    const a = axialDesign(1, fit, 8.4);
    assert.ok(a.valid, `${fit.name}: ${JSON.stringify(a)}`);
    assert.ok(a.lockMargin >= 0.15 - 1e-9);
    assert.ok(a.shelf <= 0.7);
    assert.ok(a.contactShare >= 0.60 && a.contactShare <= 0.70);
    assert.ok(fit.axialGap >= 0.2);
    assert.ok(fit.channelGap >= 0.8);
  }
});

test("phasing: liczby płatów i planet są zgodne", () => {
  for (const { lobes } of cases) assert.equal((3 * lobes) % lobes, 0);
  assert.equal(TAU / 4 * 4, TAU);
});
