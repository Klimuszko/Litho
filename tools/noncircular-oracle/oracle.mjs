export const TAU = 2 * Math.PI;

export const FITS = [
  { name: "Ciasny", backlash: 0.22, tip: 0.08, spacing: 0.25, axialGap: 0.2, channelGap: 0.8 },
  { name: "Standardowy", backlash: 0.32, tip: 0.14, spacing: 0.40, axialGap: 0.2, channelGap: 1.0 },
  { name: "Luźny", backlash: 0.44, tip: 0.22, spacing: 0.58, axialGap: 0.3, channelGap: 1.2 },
];

const mod = (x, n) => ((x % n) + n) % n;
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];
const cross = (a, b) => a[0] * b[1] - a[1] * b[0];
const norm = a => Math.hypot(a[0], a[1]);
const rot = (p, a) => [p[0] * Math.cos(a) - p[1] * Math.sin(a), p[0] * Math.sin(a) + p[1] * Math.cos(a)];
const unwrapDelta = d => d > Math.PI ? d - TAU : d < -Math.PI ? d + TAU : d;

export function polarPoint(theta, { radius, lobes, e1, e2 = 0 }) {
  const r = radius * (1 + e1 * Math.cos(lobes * theta) + e2 * Math.cos(2 * lobes * theta));
  return [r * Math.cos(theta), r * Math.sin(theta)];
}

export function sampleCurve(spec, count = 8192) {
  const points = Array.from({ length: count }, (_, i) => polarPoint(TAU * i / count, spec));
  const cumulative = [0];
  for (let i = 1; i <= count; i++) cumulative.push(cumulative[i - 1] + norm(sub(points[i % count], points[i - 1])));
  return { spec, points, cumulative, length: cumulative[count] };
}

export function poseAtArc(curve, s) {
  const target = mod(s, curve.length);
  let lo = 0, hi = curve.points.length;
  while (lo + 1 < hi) { const mid = (lo + hi) >> 1; if (curve.cumulative[mid] <= target) lo = mid; else hi = mid; }
  const ds = curve.cumulative[lo + 1] - curve.cumulative[lo];
  const f = ds ? (target - curve.cumulative[lo]) / ds : 0;
  const a = curve.points[lo], b = curve.points[(lo + 1) % curve.points.length];
  const tangent = mul(sub(b, a), 1 / ds);
  // Curves are sampled counter-clockwise, hence the right-hand normal points
  // outside.  The normal, rather than the radius vector, is the line of action
  // used by the generating cutter.
  return { point: add(a, mul(sub(b, a), f)), tangent, normal: [tangent[1], -tangent[0]] };
}

function farRayIntersection(origin, direction, polygon) {
  let far = -Infinity;
  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i], edge = sub(polygon[(i + 1) % polygon.length], a);
    const den = cross(direction, edge);
    if (Math.abs(den) < 1e-11) continue;
    const ao = sub(a, origin);
    const t = cross(ao, edge) / den;
    const u = cross(ao, direction) / den;
    if (t >= 0 && u >= 0 && u <= 1) far = Math.max(far, t);
  }
  if (!Number.isFinite(far)) throw new Error("ray missed planet");
  return add(origin, mul(direction, far));
}

export function solveKinematics({ lobes, ringLobes, e1, e2 = 0, radius = 18, samples = 4096 }) {
  const curve = sampleCurve({ radius, lobes, e1, e2 }, Math.max(2048, samples));
  const lobeLength = curve.length / lobes;
  const phase = lobeLength / 2;
  const frames = [];
  let betaPrev;
  for (let i = 0; i <= samples; i++) {
    const s = lobeLength * i / samples;
    const sun = poseAtArc(curve, s);
    const planet = poseAtArc(curve, phase - s);
    let beta = Math.atan2(-sun.tangent[1], -sun.tangent[0]) - Math.atan2(planet.tangent[1], planet.tangent[0]);
    if (betaPrev !== undefined) beta = betaPrev + unwrapDelta(beta - betaPrev);
    betaPrev = beta;
    const center = sub(sun.point, rot(planet.point, beta));
    const ray = mul(sun.point, 1 / norm(sun.point));
    const localOrigin = rot(mul(center, -1), -beta);
    const localDirection = rot(ray, -beta);
    const localHit = farRayIntersection(localOrigin, localDirection, curve.points);
    const c2 = add(center, rot(localHit, beta));
    frames.push({ s, c1: sun.point, c2, center, beta });
  }
  let chi = 0;
  frames[0].chiKin = 0;
  for (let i = 1; i < frames.length; i++) {
    const a = frames[i - 1], b = frames[i];
    const db = b.beta - a.beta;
    const q1 = norm(sub(a.c2, a.c1)) / norm(a.c2);
    const q2 = norm(sub(b.c2, b.c1)) / norm(b.c2);
    chi += db * (q1 + q2) / 2;
    frames[i].chiKin = chi;
  }
  const c2Angle = frames.map(f => Math.atan2(f.c2[1], f.c2[0])).reduce((acc, x, i, xs) => i ? acc + unwrapDelta(x - xs[i - 1]) : 0, 0);
  const naturalPeriod = Math.abs(c2Angle - chi);
  const naturalRingLobes = TAU / naturalPeriod;
  const targetPeriod = TAU / ringLobes;
  const targetChi = c2Angle - Math.sign(c2Angle - chi) * targetPeriod;
  const k = targetChi / chi;
  const orbit = frames.map(f => norm(f.center));
  const orbitBreathing = (Math.max(...orbit) - Math.min(...orbit)) / (2 * orbit.reduce((a, b) => a + b, 0) / orbit.length);
  return { curve, frames, chi, c2Angle, k, naturalRingLobes, orbitBreathing };
}

export function curvatureStats(spec, samples = 32768) {
  let minConvex = Infinity, minConcave = Infinity, finite = true;
  for (let i = 0; i < samples; i++) {
    const t = TAU * i / samples, h = 1e-4;
    const p0 = polarPoint(t - h, spec), p1 = polarPoint(t, spec), p2 = polarPoint(t + h, spec);
    const d1 = mul(sub(p2, p0), 1 / (2 * h));
    const d2 = mul(add(sub(p2, mul(p1, 2)), p0), 1 / (h * h));
    const numerator = cross(d1, d2), rho = Math.pow(norm(d1), 3) / Math.max(Math.abs(numerator), 1e-12);
    if (!Number.isFinite(rho)) finite = false;
    if (numerator >= 0) minConvex = Math.min(minConvex, rho); else minConcave = Math.min(minConcave, rho);
  }
  return { minConvex, minConcave, finite };
}

const ceilLayer = x => Math.ceil((x - 1e-9) / 0.2) * 0.2;
export function axialDesign(module, fit, height = 8.4, pressureAngleDeg = 25) {
  const alpha = pressureAngleDeg * Math.PI / 180;
  // Przesunięcie jest długością łuku, a nie granicą Z; nie kwantyzujemy go do warstwy.
  const delta = fit.backlash / Math.cos(alpha) + 0.15;
  const ramp = ceilLayer(Math.max(0, 2.25 * module + fit.tip + 0.5 - 0.8));
  const bandMin = ceilLayer(Math.max(2.2, 2.2 * module));
  const channel = 0.6;
  const minimumHeight = ceilLayer(2 * bandMin + channel + ramp);
  const band = (height - channel - ramp) / 2;
  const pitch = Math.PI * module;
  return {
    delta, ramp, bandMin, channel, minimumHeight, band,
    shelf: delta * Math.cos(alpha), lockMargin: delta - fit.backlash / Math.cos(alpha),
    headLimit: 0.35 * pitch, contactShare: Math.max(0, 2 * band - 0.4) / height,
    valid: height + 1e-9 >= minimumHeight && band >= bandMin && delta * Math.cos(alpha) <= 0.7 && delta <= 0.35 * pitch,
  };
}

export function evaluateCase({ lobes, e1, module = 1, height = 8.4, samples = 4096 }) {
  const ringLobes = 3 * lobes;
  const kin = solveKinematics({ lobes, ringLobes, e1, radius: 18, samples });
  const curvature = curvatureStats({ radius: 18, lobes, e1 });
  const axial = FITS.map(fit => ({ fit: fit.name, ...axialDesign(module, fit, height) }));
  const closureError = Math.abs((kin.c2Angle - kin.k * kin.chi) - Math.sign(kin.c2Angle - kin.chi) * TAU / ringLobes);
  return {
    lobes, ringLobes, e1, module, k: kin.k, naturalRingLobes: kin.naturalRingLobes,
    closureError, orbitBreathing: kin.orbitBreathing, curvature, axial,
    preliminaryPass: closureError < 1e-8 && Math.abs(kin.k - 1) <= 0.005 && kin.orbitBreathing <= 0.01 &&
      curvature.finite && curvature.minConvex >= 2.5 * module && axial.every(x => x.valid),
  };
}
