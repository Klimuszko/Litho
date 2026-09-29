import polygonClipping from "polygon-clipping";
import { TAU, polarPoint, poseAtArc, sampleCurve, solveKinematics } from "./oracle.mjs";

const pc = polygonClipping;
const rot = (p, a) => [p[0] * Math.cos(a) - p[1] * Math.sin(a), p[0] * Math.sin(a) + p[1] * Math.cos(a)];
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];
const norm = a => Math.hypot(a[0], a[1]);
const unit = a => mul(a, 1 / norm(a));
const ring = pts => [[pts.concat([pts[0]])]];
const snap = x => Math.round(x * 1e5) / 1e5;
const transformRing = (r, a, t = [0, 0]) => r.map(p => { const q = add(rot(p, a), t); return [snap(q[0]), snap(q[1])]; });
export const transformMulti = (mp, a, t = [0, 0]) => mp.map(poly => poly.map(r => transformRing(r.slice(0, -1), a, t).concat([transformRing([r[0]], a, t)[0]])));

function offsetOuter(mp, distance) {
  return mp.map(poly => poly.map((r, ri) => {
    if (ri) return r;
    const pts = r.slice(0, -1), out = pts.map((p, i) => {
      const a = pts[(i + pts.length - 1) % pts.length], b = pts[(i + 1) % pts.length];
      const e0 = unit(sub(p, a)), e1 = unit(sub(b, p));
      const n0 = [e0[1], -e0[0]], n1 = [e1[1], -e1[0]];
      const bis = unit(add(n0, n1));
      const scale = distance / Math.max(0.2, bis[0] * n0[0] + bis[1] * n0[1]);
      return add(p, mul(bis, Math.min(scale, 4 * distance)));
    });
    return out.concat([out[0]]);
  }));
}

function involute(x) { return Math.tan(x) - x; }

/** Pełny, standardowy zewnętrzny dłutak ewolwentowy (20/25°, addendum m, dedendum 1.25m). */
export function involuteShaper({ teeth = 12, module = 1, pressureAngle = 25, flankSamples = 5 }) {
  const alpha = pressureAngle * Math.PI / 180;
  const rp = teeth * module / 2, rb = rp * Math.cos(alpha), ra = rp + module, rf = rp - 1.25 * module;
  const phiP = Math.acos(rb / rp), phiA = Math.acos(rb / ra);
  const invP = involute(phiP), half = Math.PI / (2 * teeth);
  const pts = [];
  for (let tooth = 0; tooth < teeth; tooth++) {
    const c = TAU * tooth / teeth;
    pts.push([rf * Math.cos(c - half), rf * Math.sin(c - half)]);
    for (let i = 0; i <= flankSamples; i++) {
      const phi = phiA * i / flankSamples, rr = rb / Math.cos(phi);
      const a = c - half + invP - involute(phi);
      pts.push([rr * Math.cos(a), rr * Math.sin(a)]);
    }
    for (let i = flankSamples; i >= 0; i--) {
      const phi = phiA * i / flankSamples, rr = rb / Math.cos(phi);
      const a = c + half - invP + involute(phi);
      pts.push([rr * Math.cos(a), rr * Math.sin(a)]);
    }
    pts.push([rf * Math.cos(c + half), rf * Math.sin(c + half)]);
  }
  const tipHalfAngle = half - involute(phiA) + invP;
  return { polygon: ring(pts), teeth, module, pressureAngle, rp, rb, ra, rf,
    pitchThickness: Math.PI * module / 2, tipThickness: 2 * ra * tipHalfAngle,
    rootThickness: 2 * rf * (half + invP), undercutFree: teeth >= 2 / Math.pow(Math.sin(alpha), 2) };
}

function radialBlank(spec, offset, count = 720) {
  return ring(Array.from({ length: count }, (_, i) => {
    const t = TAU * i / count, h = 1e-5, p = polarPoint(t, spec);
    const tangent = unit([polarPoint(t+h,spec)[0]-polarPoint(t-h,spec)[0],
      polarPoint(t+h,spec)[1]-polarPoint(t-h,spec)[1]]);
    return add(p, mul([tangent[1], -tangent[0]], offset));
  }));
}

function largest(mp) {
  if (!mp.length) throw new Error("empty polygon result");
  const area = r => Math.abs(r.slice(0, -1).reduce((s, p, i, a) => { const q = a[(i + 1) % a.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0) / 2);
  return [mp.reduce((best, p) => area(p[0]) > area(best[0]) ? p : best, mp[0])];
}

function unionBatched(polygons, batch = 12) {
  let level = polygons;
  while (level.length > 1) {
    const next = [];
    for (let i = 0; i < level.length; i += batch)
      next.push(pc.union(...level.slice(i, i + batch)));
    level = next;
  }
  return level[0] ?? [];
}

/** Generuje planetę jako obwiednię ujemną jawnego dłutaka toczącego się po centroidzie. */
export function generatePlanet({ lobes, e1, radius = 18, module = 1, pressureAngle = 25, posesPerPitch = 8, phaseArc = 0 }) {
  const curve = sampleCurve({ radius, lobes, e1 }, 4096);
  const teeth = Math.max(lobes * 3, Math.round(curve.length / (Math.PI * module) / lobes) * lobes);
  const actualModule = curve.length / (Math.PI * teeth);
  const alpha = pressureAngle * Math.PI / 180;
  const pitch = Math.PI * actualModule;
  const tipHalf = pitch / 4 - actualModule * Math.tan(alpha);
  const rootHalf = pitch / 4 + 1.25 * actualModule * Math.tan(alpha);
  const shaper = {
    kind: "involute-rack", module: actualModule, pressureAngle,
    pitchThickness: pitch / 2, tipThickness: 2 * tipHalf,
    rootThickness: 2 * rootHalf, undercutFree: tipHalf > 0,
  };
  const count = Math.ceil(teeth * posesPerPitch);
  const cutters = [];
  for (let i = 0; i < count; i++) {
    const s = curve.length * i / count, q = poseAtArc(curve, s), n = q.normal, t = q.tangent;
    // A straight involute-generating rack rolls without slip: in the local
    // tangent frame its tooth train translates by exactly the centroid arc s.
    // Three neighbouring teeth are sufficient because every polygon is local.
    for (let k = -2; k <= 2; k++) {
      const x = k * pitch - ((s + phaseArc) % pitch);
      const local = [[x-tipHalf,-actualModule],[x+tipHalf,-actualModule],
        [x+rootHalf,1.25*actualModule],[x-rootHalf,1.25*actualModule]];
      cutters.push(ring(local.map(([u,v]) => add(q.point, add(mul(t,u), mul(n,v))))));
    }
  }
  const cutterUnion = unionBatched(cutters);
  const blank = radialBlank({ radius, lobes, e1 }, 1.05 * actualModule);
  return { polygon: largest(pc.difference(blank, cutterUnion)), curve, teeth, module: actualModule, shaper };
}

/** Obwiednie koła centralnego i pierścienia są różnicami blanków i pozycji tej samej planety-narzędzia. */
export function generateMechanism(opts) {
  const { lobes, e1, radius = 18, pressureAngle = 25, backlash = 0 } = opts;
  const ringLobes = 3 * lobes;
  const planet = generatePlanet({ ...opts, radius, pressureAngle });
  const sweepSamples = Math.ceil(planet.teeth * (opts.posesPerPitch ?? 8) / lobes);
  const kin = solveKinematics({ lobes, ringLobes, e1, radius, samples: sweepSamples });
  const sunCutters = [], ringCutters = [];
  const envelopeTool = backlash > 0 ? offsetOuter(planet.polygon, backlash / 2) : planet.polygon;
  for (let l = 0; l < lobes; l++) for (const f of kin.frames) {
    const symmetry = TAU * l / lobes;
    sunCutters.push(transformMulti(envelopeTool, f.beta + symmetry, rot(f.center, symmetry)));
  }
  // In ring coordinates one sun/planet lobe traces one ring lobe.  Repeat
  // that independently over every ring lobe; repeating only `lobes` leaves
  // most of the internal gear solid (the K2 failure from the review).
  for (let l = 0; l < ringLobes; l++) for (const f of kin.frames) {
    const chi = kin.k * f.chiKin;
    const symmetry = TAU * l / ringLobes;
    ringCutters.push(transformMulti(envelopeTool, f.beta - chi + symmetry,
      rot(f.center, symmetry - chi)));
  }
  const sunBlank = radialBlank({ radius, lobes, e1 }, 1.05 * planet.module);
  const outerR = opts.outerRadius ?? 3 * radius + 4.5 * planet.module;
  const outer = ring(Array.from({ length: 1080 }, (_, i) => [outerR * Math.cos(TAU * i / 1080), outerR * Math.sin(TAU * i / 1080)]));
  const sun = largest(pc.difference(sunBlank, unionBatched(sunCutters)));
  const ringGear = pc.difference(outer, unionBatched(ringCutters));
  return { planet, sun, ring: largest(ringGear), kin, outerR };
}

export function polygonArea(mp) {
  return mp.reduce((sum, poly) => sum + poly.reduce((s, r, ri) => s + (ri ? -1 : 1) * Math.abs(r.slice(0, -1).reduce((a, p, i, ps) => { const q = ps[(i + 1) % ps.length]; return a + p[0] * q[1] - q[0] * p[1]; }, 0) / 2), 0), 0);
}

const cleanMulti = mp => mp.map(poly => poly.map(r => r.map(p => [snap(p[0]), snap(p[1])])));
export function intersectionArea(a, b) {
  try { const x = pc.intersection(cleanMulti(a), cleanMulti(b)); return x.length ? polygonArea(x) : 0; }
  catch { // Kontakt styczny potrafi być degeneracją sweep-line; jitter jest deterministyczny i konserwatywny.
    const shifted = transformMulti(b, 0, [1e-5, -1e-5]);
    const x = pc.intersection(cleanMulti(a), cleanMulti(shifted)); return x.length ? polygonArea(x) : 0;
  }
}

function pointSegmentDistance(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], d2 = dx * dx + dy * dy;
  const t = d2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d2)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}

export function boundaryDistance(a, b) {
  if (intersectionArea(a, b) > 1e-8) return -1;
  const ar = a[0][0], br = b[0][0]; let best = Infinity;
  for (let i = 0; i < ar.length - 1; i += 2) for (let j = 0; j < br.length - 1; j += 2) {
    best = Math.min(best, pointSegmentDistance(ar[i], br[j], br[j + 1]), pointSegmentDistance(br[j], ar[i], ar[i + 1]));
  }
  return best;
}

export function boundaryMetrics(mp, module) {
  const pts = mp[0][0].slice(0, -1); let minEdge = Infinity, minTurn = Math.PI;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[(i + pts.length - 1) % pts.length], b = pts[i], c = pts[(i + 1) % pts.length];
    minEdge = Math.min(minEdge, norm([c[0] - b[0], c[1] - b[1]]));
    const u = unit([a[0] - b[0], a[1] - b[1]]), v = unit([c[0] - b[0], c[1] - b[1]]);
    minTurn = Math.min(minTurn, Math.acos(Math.max(-1, Math.min(1, u[0] * v[0] + u[1] * v[1]))));
  }
  return { vertices: pts.length, minEdge, minTurn, regular: pts.length > 20 && minTurn > 0.01 && minEdge > module * 1e-6 };
}

export function validateCycle(mech) {
  let maxPlanetOverlap = 0, maxSunOverlap = 0, maxRingOverlap = 0, minPlanetSpacing = Infinity;
  const N = mech.kin.curve.spec.lobes;
  for (const f of mech.kin.frames) {
    const p = transformMulti(mech.planet.polygon, f.beta, f.center);
    const adjacent = transformMulti(p, TAU / N);
    maxPlanetOverlap = Math.max(maxPlanetOverlap, intersectionArea(p, adjacent));
    maxSunOverlap = Math.max(maxSunOverlap, intersectionArea(p, mech.sun));
    const ringAtFrame = transformMulti(mech.ring, mech.kin.k * f.chiKin);
    maxRingOverlap = Math.max(maxRingOverlap, intersectionArea(p, ringAtFrame));
    minPlanetSpacing = Math.min(minPlanetSpacing, boundaryDistance(p, adjacent));
  }
  return { maxPlanetOverlap, maxSunOverlap, maxRingOverlap, minPlanetSpacing };
}

export function validateAxialProfiles(mech, delta, recess = 0.5) {
  const phase = delta / mech.planet.curve.spec.radius;
  const steps = [0, phase, 2 * phase].map(a => transformMulti(mech.planet.polygon, a));
  const transitions = [pc.intersection(steps[0], steps[1]), pc.intersection(steps[1], steps[2])];
  const scale = 1 - recess / mech.planet.curve.spec.radius;
  const channelCore = mech.planet.polygon.map(poly => poly.map(r => r.map(p => [p[0] * scale, p[1] * scale])));
  return {
    steps, transitions, channelCore,
    transitionAreas: transitions.map(polygonArea),
    channelArea: polygonArea(channelCore),
    nominalArea: polygonArea(mech.planet.polygon),
    valid: transitions.every(x => x.length > 0 && polygonArea(x) > 0) && polygonArea(channelCore) < polygonArea(mech.planet.polygon),
  };
}
