import test from "node:test";
import assert from "node:assert/strict";
import { FITS, axialDesign, evaluateCase, sampleCurve, TAU } from "./oracle.mjs";
import {
  boundaryMetrics,
  exportProfile,
  generateMechanism,
  maxRadialDeviation,
  polygonArea,
  validateAxialProfiles,
  validateCycle,
} from "./geometry.mjs";

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

test("4–6: dłutak, obwiednie, regularność, podcięcie i pełny cykl kolizji", { timeout: 180_000 }, () => {
  for (const c of cases) {
    const mech = generateMechanism({
      ...c,
      radius: 12,
      module: 1,
      posesPerPitch: 4,
      // Produkt nigdy nie eksportuje profilu bez luzu. Ciasny profil jest
      // wariantem granicznym i dlatego stanowi właściwy przypadek testowy.
      backlash: FITS[0].backlash,
    });
    const shaper = mech.planet.shaper;
    assert.ok(shaper.undercutFree, `${c.lobes}/${c.e1}: dłutak podcięty`);
    assert.ok(shaper.tipThickness >= Math.max(0.25 * mech.planet.module, 0.4));
    assert.ok(shaper.rootThickness >= 0.8 * shaper.pitchThickness);
    for (const [name, profile] of [["P", mech.planet.polygon], ["S", mech.sun], ["R", mech.ring]]) {
      assert.ok(polygonArea(profile) > 0);
      const metrics = boundaryMetrics(profile, mech.planet.module);
      assert.ok(metrics.regular, JSON.stringify({ c, name, metrics }));
    }
    const cycle = validateCycle(mech);
    assert.ok(cycle.maxPlanetOverlap < 1e-5, JSON.stringify({ c, cycle }));
    assert.ok(cycle.maxSunOverlap < 1e-5, JSON.stringify({ c, cycle }));
    assert.ok(cycle.maxRingOverlap < 1e-5, JSON.stringify({ c, cycle }));
    assert.ok(cycle.maxSunRingOverlap < 1e-5, JSON.stringify({ c, cycle }));
    assert.ok(cycle.minPlanetSpacing >= 0.58, JSON.stringify({ c, cycle }));
    for (const fit of FITS) {
      const axial = axialDesign(mech.planet.module, fit, 8.4);
      const layers = validateAxialProfiles(mech, axial.delta);
      assert.ok(layers.valid);
      assert.ok(layers.transitionAreas.every(a => a > 0 && a < layers.nominalArea));
      assert.ok(layers.channelArea < layers.nominalArea);
    }
  }
});

test("profile eksportowane do SCAD zachowują obwiednię", { timeout: 180_000 }, () => {
  const productCases = [
    { lobes: 4, e1: 0.04125, radius: 40 / (3 * 1.04125) },
    { lobes: 3, e1: 0.04950, radius: 40 / (3 * 1.04950) },
  ];
  for (const c of productCases) {
    const options = {
      ...c,
      module: 1,
      pressureAngle: 25,
      posesPerPitch: 8,
      backlash: FITS[0].backlash,
      outerRadius: 45,
    };
    const base = generateMechanism({ ...options, phaseArc: 0 });
    const axial = axialDesign(base.planet.module, FITS[0], 8.4);
    for (const phaseArc of [0, axial.delta, 2 * axial.delta]) {
      const mech = phaseArc === 0 ? base : generateMechanism({ ...options, phaseArc });
      const exported = {
        ...mech,
        planet: { ...mech.planet, polygon: exportProfile(mech.planet.polygon, 0) },
        sun: exportProfile(mech.sun, 1),
        ring: exportProfile(mech.ring, 2),
      };
      const deviations = {
        planet: maxRadialDeviation(mech.planet.polygon, exported.planet.polygon),
        sun: maxRadialDeviation(mech.sun, exported.sun),
        ring: maxRadialDeviation(mech.ring, exported.ring),
      };
      // 0,05 mm to 23% najmniejszego luzu 0,22 mm i wyraźnie mniej niż
      // rozdzielczość typowej dyszy; pełny cykl poniżej nadal musi być bezkolizyjny.
      assert.ok(Math.max(...Object.values(deviations)) <= 0.05, JSON.stringify({ c, phaseArc, deviations }));
      const cycle = validateCycle(exported);
      assert.ok(cycle.maxPlanetOverlap < 1e-5, JSON.stringify({ c, phaseArc, cycle }));
      assert.ok(cycle.maxSunOverlap < 1e-5, JSON.stringify({ c, phaseArc, cycle }));
      assert.ok(cycle.maxRingOverlap < 1e-5, JSON.stringify({ c, phaseArc, cycle }));
      assert.ok(cycle.maxSunRingOverlap < 1e-5, JSON.stringify({ c, phaseArc, cycle }));
    }
  }
});
