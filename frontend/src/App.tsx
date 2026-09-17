import { ChangeEvent, PointerEvent as ReactPointerEvent, useEffect, useRef, useState } from "react";
import "./formats.css";
import HousingGenerator from "./HousingGenerator";

export type Params = {
  width_mm: number; height_mm: number; min_thickness_mm: number; max_thickness_mm: number;
  gamma: number; brightness: number; contrast: number;
  nozzle_diameter_mm: 0.2 | 0.4; quality_profile: "economic" | "optimal" | "maximum";
  orientation: "portrait" | "landscape"; border_width_mm: number; border_height_mm: number;
  border_widths_mm: BorderWidths | null; mounting_flange: boolean;
  removable_support: boolean; invert: boolean; mirror: boolean; rotation_degrees: number;
  crop: {x: number; y: number; width: number; height: number};
};
type Crop = Params["crop"];
type BorderWidths = {top: number; right: number; bottom: number; left: number};
export const MOUNTING_FLANGE_WIDTH_MM = 2;
export const MOUNTING_FLANGE_HEIGHT_MM = 1.6;

export function automaticCrop(imageWidth: number, imageHeight: number, modelWidth: number, modelHeight: number): Crop {
  const sourceAspect = imageWidth / imageHeight;
  const targetAspect = modelWidth / modelHeight;
  if (sourceAspect > targetAspect) {
    const width = targetAspect / sourceAspect;
    return {x: (1 - width) / 2, y: 0, width, height: 1};
  }
  if (sourceAspect < targetAspect) {
    const height = sourceAspect / targetAspect;
    return {x: 0, y: (1 - height) / 2, width: 1, height};
  }
  return {x: 0, y: 0, width: 1, height: 1};
}

// Zooms into `base` (the "cover" crop for the current preset) around the pan
// position already recorded in `current`. Width and height are always scaled
// by the same factor, so the result keeps base's aspect ratio for any zoom.
export function zoomCrop(base: Crop, current: Crop, zoom: number): Crop {
  const width = base.width / zoom;
  const height = base.height / zoom;
  const centerX = current.x + current.width / 2;
  const centerY = current.y + current.height / 2;
  return {
    x: Math.max(0, Math.min(1 - width, centerX - width / 2)),
    y: Math.max(0, Math.min(1 - height, centerY - height / 2)),
    width,
    height,
  };
}

export function zoomCropAt(base: Crop, current: Crop, zoom: number, focalX: number, focalY: number): Crop {
  const width = base.width / zoom;
  const height = base.height / zoom;
  const sourceX = current.x + current.width * focalX;
  const sourceY = current.y + current.height * focalY;
  return {
    x: Math.max(0, Math.min(1 - width, sourceX - width * focalX)),
    y: Math.max(0, Math.min(1 - height, sourceY - height * focalY)),
    width,
    height,
  };
}

export function panCrop(crop: Crop, deltaX: number, deltaY: number): Crop {
  return {
    ...crop,
    x: Math.max(0, Math.min(1 - crop.width, crop.x + deltaX)),
    y: Math.max(0, Math.min(1 - crop.height, crop.y + deltaY)),
  };
}

export function rotatedSize(size: {width: number; height: number}, rotation: number) {
  return inscribedSize(size.width, size.height, rotation);
}

export function inscribedSize(width: number, height: number, angleDegrees: number) {
  let angle = Math.abs(angleDegrees) % 180 * Math.PI / 180;
  if (angle > Math.PI / 2) angle = Math.PI - angle;
  if (angle < 1e-10) return {width, height};
  const sin = Math.sin(angle); const cos = Math.cos(angle);
  if (Math.abs(cos) < 1e-10) return {width: height, height: width};
  const longSide = Math.max(width, height); const shortSide = Math.min(width, height);
  let resultWidth: number; let resultHeight: number;
  if (shortSide <= 2 * sin * cos * longSide) {
    const halfShort = .5 * shortSide;
    [resultWidth, resultHeight] = width >= height ? [halfShort / sin, halfShort / cos] : [halfShort / cos, halfShort / sin];
  } else {
    const cos2 = cos * cos - sin * sin;
    resultWidth = (width * cos - height * sin) / cos2;
    resultHeight = (height * cos - width * sin) / cos2;
  }
  return {width: Math.max(1, resultWidth), height: Math.max(1, resultHeight)};
}

export const FORMATS = [{label: "10 × 15 cm", short: 100, long: 150}, {label: "13 × 18 cm", short: 130, long: 180}, {label: "15 × 20 cm", short: 150, long: 200}] as const;
export const QUALITY = {
  0.2: {economic: {pitch: .2, layer: .16, line: .22}, optimal: {pitch: .125, layer: .1, line: .22}, maximum: {pitch: .1, layer: .08, line: .22}},
  0.4: {economic: {pitch: .4, layer: .2, line: .44}, optimal: {pitch: .25, layer: .12, line: .44}, maximum: {pitch: .2, layer: .08, line: .44}},
} as const;
const MAX_GRID_POINTS = 3_100_000;

export function effectiveGrid(width: number, height: number, pitch: number, border: number | BorderWidths) {
  const borders = typeof border === "number" ? {top: border, right: border, bottom: border, left: border} : border;
  let scale = 1 / pitch;
  let cols = 2; let rows = 2; let totalCols = 2; let totalRows = 2;
  for (let i = 0; i < 8; i++) {
    cols = Math.max(2, Math.round(width * scale) + 1);
    rows = Math.max(2, Math.round(height * scale) + 1);
    const dx = width / (cols - 1); const dy = height / (rows - 1);
    totalCols = cols + Math.ceil(borders.left / dx) + Math.ceil(borders.right / dx);
    totalRows = rows + Math.ceil(borders.top / dy) + Math.ceil(borders.bottom / dy);
    const points = totalCols * totalRows;
    if (points <= MAX_GRID_POINTS) break;
    scale *= Math.sqrt(MAX_GRID_POINTS / points) * .999;
  }
  return {cols, rows, totalCols, totalRows, pitch: Math.max(width / (cols - 1), height / (rows - 1))};
}
export function imageArea(width: number, height: number, border: number | BorderWidths) {
  const borders = typeof border === "number" ? {top: border, right: border, bottom: border, left: border} : border;
  return {width: width - borders.left - borders.right, height: height - borders.top - borders.bottom};
}
export const initial: Params = {width_mm: 150, height_mm: 100, min_thickness_mm: .8, max_thickness_mm: 3.2, gamma: 1, brightness: 1, contrast: 1.25, nozzle_diameter_mm: .4, quality_profile: "optimal", orientation: "landscape", border_width_mm: 0, border_widths_mm: null, border_height_mm: 3.2, mounting_flange: false, removable_support: false, invert: false, mirror: false, rotation_degrees: 0, crop: {x: 0, y: 0, width: 1, height: 1}};

export function resolvedBorders(p: Params): BorderWidths {
  if (p.mounting_flange) return {top: MOUNTING_FLANGE_WIDTH_MM, right: MOUNTING_FLANGE_WIDTH_MM, bottom: MOUNTING_FLANGE_WIDTH_MM, left: MOUNTING_FLANGE_WIDTH_MM};
  return p.border_widths_mm || {top: p.border_width_mm, right: p.border_width_mm, bottom: p.border_width_mm, left: p.border_width_mm};
}

export function effectiveBorderHeight(p: Params): number {
  return p.mounting_flange ? MOUNTING_FLANGE_HEIGHT_MM : p.border_height_mm;
}

export function validateParams(p: Params): string {
  if (!Number.isFinite(p.width_mm) || !Number.isFinite(p.height_mm) || p.width_mm < 20 || p.height_mm < 20 || p.width_mm > 256 || p.height_mm > 256) return "Wymiary niestandardowe muszą mieć od 20 do 256 mm.";
  if (p.width_mm !== p.height_mm && (p.orientation === "landscape") !== (p.width_mm > p.height_mm)) return "Orientacja musi odpowiadać wymiarom modelu.";
  if (p.max_thickness_mm <= p.min_thickness_mm) return "Maksymalna grubość musi być większa od minimalnej.";
  if (p.max_thickness_mm - p.min_thickness_mm > 12) return "Zakres grubości nie może przekraczać 12 mm.";
  const borders = resolvedBorders(p);
  if (Object.values(borders).some(value => value < 0 || value > 20)) return "Każdy bok ramki musi mieć od 0 do 20 mm.";
  if (Object.values(borders).some(value => value > 0) && effectiveBorderHeight(p) < 2 * p.nozzle_diameter_mm) return `Grubość ramki musi mieć co najmniej ${(2 * p.nozzle_diameter_mm).toFixed(1)} mm dla wybranej dyszy.`;
  if (borders.left + borders.right >= p.width_mm || borders.top + borders.bottom >= p.height_mm) return "Ramka nie może zajmować całego obszaru zdjęcia.";
  return "";
}

function Slider({label, value, min, max, step, unit = "", onChange}: {label: string; value: number; min: number; max: number; step: number; unit?: string; onChange: (n: number) => void}) {
  return <label className="control"><span>{label}<output>{value}{unit}</output></span><input type="range" value={value} min={min} max={max} step={step} onChange={e => onChange(Number(e.target.value))}/></label>;
}

function LithophaneGenerator({onOpenHousing}: {onOpenHousing: () => void}) {
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<string>("");
  const [params, setParams] = useState(initial);
  const [view, setView] = useState<"photo" | "lithophane">("photo");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [customFormat, setCustomFormat] = useState(false);
  const [customWidthInput, setCustomWidthInput] = useState(String(initial.width_mm));
  const [customHeightInput, setCustomHeightInput] = useState(String(initial.height_mm));
  const [customRotationInput, setCustomRotationInput] = useState("0");
  const [customBorder, setCustomBorder] = useState(false);
  const [sourceSize, setSourceSize] = useState<{width: number; height: number} | null>(null);
  const [rotatedPreview, setRotatedPreview] = useState<HTMLCanvasElement | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const drag = useRef<{pointerId: number; x: number; y: number; crop: Crop} | null>(null);
  const busyRef = useRef(false);
  const effectiveSourceSize = sourceSize ? rotatedSize(sourceSize, params.rotation_degrees) : null;
  const quality = QUALITY[params.nozzle_diameter_mm][params.quality_profile];
  const borders = resolvedBorders(params);
  const inner = imageArea(params.width_mm, params.height_mm, borders);
  const grid = effectiveGrid(inner.width, inner.height, quality.pitch, borders);
  const gridX = grid.cols;
  const gridY = grid.rows;
  const anyBorder = Object.values(borders).some(value => value > 0);
  const set = <K extends keyof Params>(key: K, value: Params[K]) => setParams(p => ({...p, [key]: value}));
  const setCrop = (key: keyof Params["crop"], value: number) => setParams(p => ({...p, crop: {...p.crop, [key]: value}}));
  const fitCrop = (width: number, height: number, border: number | BorderWidths = borders) => { const area = imageArea(width, height, border); return effectiveSourceSize ? automaticCrop(effectiveSourceSize.width, effectiveSourceSize.height, area.width, area.height) : params.crop; };
  const setFormat = (short: number, long: number) => { setCustomFormat(false); setParams(p => {
    const width = p.orientation === "landscape" ? long : short; const height = p.orientation === "landscape" ? short : long;
    const area = imageArea(width, height, resolvedBorders(p));
    const size = sourceSize ? rotatedSize(sourceSize, p.rotation_degrees) : null;
    return {...p, width_mm: width, height_mm: height, crop: size ? automaticCrop(size.width, size.height, area.width, area.height) : p.crop};
  }); };
  const setOrientation = (orientation: Params["orientation"]) => setParams(p => {
    const shouldSwap = orientation === "portrait" ? p.width_mm > p.height_mm : p.height_mm > p.width_mm;
    const width = shouldSwap ? p.height_mm : p.width_mm; const height = shouldSwap ? p.width_mm : p.height_mm;
    const area = imageArea(width, height, resolvedBorders(p));
    const size = sourceSize ? rotatedSize(sourceSize, p.rotation_degrees) : null;
    return {...p, orientation, width_mm: width, height_mm: height, crop: size ? automaticCrop(size.width, size.height, area.width, area.height) : p.crop};
  });
  const setZoom = (zoom: number) => setParams(p => {
    if (!sourceSize) return p;
    const area = imageArea(p.width_mm, p.height_mm, resolvedBorders(p));
    const size = rotatedSize(sourceSize, p.rotation_degrees);
    const base = automaticCrop(size.width, size.height, area.width, area.height);
    return {...p, crop: zoomCrop(base, p.crop, zoom)};
  });
  const setRotation = (rotation: number) => {
    rotation = ((rotation % 360) + 360) % 360;
    setCustomRotationInput(String(Number(rotation.toFixed(1))));
    setParams(p => {
    if (!sourceSize) return {...p, rotation_degrees: rotation};
    const size = rotatedSize(sourceSize, rotation);
    const area = imageArea(p.width_mm, p.height_mm, resolvedBorders(p));
      return {...p, rotation_degrees: rotation, crop: automaticCrop(size.width, size.height, area.width, area.height)};
    });
  };
  const setCustomDimension = (key: "width_mm" | "height_mm", value: number) => setParams(p => {
    value = Math.max(20, Math.min(256, Number.isFinite(value) ? value : 20));
    const width = key === "width_mm" ? value : p.width_mm;
    const height = key === "height_mm" ? value : p.height_mm;
    const orientation = width >= height ? "landscape" : "portrait";
    const size = sourceSize ? rotatedSize(sourceSize, p.rotation_degrees) : null;
    const area = imageArea(width, height, resolvedBorders(p));
    return {...p, [key]: value, orientation, crop: size && area.width > 0 && area.height > 0 ? automaticCrop(size.width, size.height, area.width, area.height) : p.crop};
  });
  const commitCustomDimension = (key: "width_mm" | "height_mm", raw: string) => {
    const value = Math.max(20, Math.min(256, Number.isFinite(Number(raw)) ? Number(raw) : 20));
    setCustomDimension(key, value);
    if (key === "width_mm") setCustomWidthInput(String(value)); else setCustomHeightInput(String(value));
  };
  const setBorderSide = (key: keyof BorderWidths, value: number) => setParams(p => {
    const current = resolvedBorders(p);
    const next = {...current, [key]: value};
    const size = sourceSize ? rotatedSize(sourceSize, p.rotation_degrees) : null;
    const area = imageArea(p.width_mm, p.height_mm, next);
    return {...p, border_widths_mm: next, crop: size && area.width > 0 && area.height > 0 ? automaticCrop(size.width, size.height, area.width, area.height) : p.crop};
  });
  const setMountingFlange = (enabled: boolean) => setParams(p => {
    const next = {...p, mounting_flange: enabled};
    const nextBorders = resolvedBorders(next);
    const size = sourceSize ? rotatedSize(sourceSize, p.rotation_degrees) : null;
    const area = imageArea(p.width_mm, p.height_mm, nextBorders);
    return {...next, crop: size ? automaticCrop(size.width, size.height, area.width, area.height) : p.crop};
  });

  const beginDrag = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (busyRef.current) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {pointerId: event.pointerId, x: event.clientX, y: event.clientY, crop: params.crop};
  };
  const moveDrag = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (busyRef.current) return;
    const start = drag.current;
    if (!start || start.pointerId !== event.pointerId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const innerWidth = rect.width * inner.width / params.width_mm;
    const innerHeight = rect.height * inner.height / params.height_mm;
    const directionX = params.mirror ? 1 : -1;
    setParams(p => ({...p, crop: panCrop(start.crop, directionX * (event.clientX - start.x) / innerWidth * start.crop.width, -(event.clientY - start.y) / innerHeight * start.crop.height)}));
  };
  const endDrag = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (drag.current?.pointerId === event.pointerId) drag.current = null;
  };
  useEffect(() => () => { if (source) URL.revokeObjectURL(source); }, [source]);
  useEffect(() => {
    if (!source) { setRotatedPreview(null); return; }
    let cancelled = false;
    const image = new Image();
    image.onload = () => {
      const angle = params.rotation_degrees * Math.PI / 180;
      const cosine = Math.abs(Math.cos(angle)) < 1e-10 ? 0 : Math.cos(angle);
      const sine = Math.abs(Math.sin(angle)) < 1e-10 ? 0 : Math.sin(angle);
      const expanded = document.createElement("canvas");
      expanded.width = Math.ceil(Math.abs(image.width * cosine) + Math.abs(image.height * sine));
      expanded.height = Math.ceil(Math.abs(image.width * sine) + Math.abs(image.height * cosine));
      const expandedContext = expanded.getContext("2d")!;
      expandedContext.translate(expanded.width / 2, expanded.height / 2);
      expandedContext.rotate(angle);
      expandedContext.drawImage(image, -image.width / 2, -image.height / 2);
      const inscribed = inscribedSize(image.width, image.height, params.rotation_degrees);
      const rotated = document.createElement("canvas");
      rotated.width = Math.max(1, Math.round(inscribed.width));
      rotated.height = Math.max(1, Math.round(inscribed.height));
      const rotatedContext = rotated.getContext("2d")!;
      rotatedContext.drawImage(expanded, (expanded.width - inscribed.width) / 2, (expanded.height - inscribed.height) / 2, inscribed.width, inscribed.height, 0, 0, rotated.width, rotated.height);
      if (!cancelled) setRotatedPreview(rotated);
    };
    image.src = source;
    return () => { cancelled = true; };
  }, [source, params.rotation_degrees]);
  useEffect(() => {
    if (!rotatedPreview || !canvas.current) return;
    const c = canvas.current; const ctx = c.getContext("2d")!;
    const crop = params.crop; const w = 1200; const h = Math.max(320, Math.round(w * params.height_mm / params.width_mm));
      c.width = w; c.height = h;
      ctx.filter = `brightness(${params.brightness}) contrast(${params.contrast}) grayscale(1) ${view === "lithophane" ? "invert(1)" : ""}`;
      ctx.save();
      if (params.mirror) { ctx.translate(w, 0); ctx.scale(-1, 1); }
      const bx = w * borders.left / params.width_mm; const by = h * borders.top / params.height_mm;
      const right = w * borders.right / params.width_mm; const bottom = h * borders.bottom / params.height_mm;
      ctx.fillStyle = "#302b27"; ctx.fillRect(0, 0, w, h);
      ctx.drawImage(rotatedPreview, crop.x * rotatedPreview.width, crop.y * rotatedPreview.height, crop.width * rotatedPreview.width, crop.height * rotatedPreview.height, bx, by, w - bx - right, h - by - bottom);
      ctx.restore();
      if (view === "lithophane") { ctx.globalCompositeOperation = "screen"; ctx.fillStyle = `rgba(255,177,82,${Math.min(.42, params.gamma / 10)})`; ctx.fillRect(0, 0, w, h); }
  }, [rotatedPreview, params, view]);
  useEffect(() => {
    const element = canvas.current;
    if (!element || !effectiveSourceSize) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      if (busyRef.current) return;
      const rect = element.getBoundingClientRect();
      const borderX = rect.width * borders.left / params.width_mm;
      const borderY = rect.height * borders.top / params.height_mm;
      const right = rect.width * borders.right / params.width_mm;
      const bottom = rect.height * borders.bottom / params.height_mm;
      const screenFocalX = Math.max(0, Math.min(1, (event.clientX - rect.left - borderX) / Math.max(1, rect.width - borderX - right)));
      const focalX = params.mirror ? 1 - screenFocalX : screenFocalX;
      const focalY = Math.max(0, Math.min(1, (event.clientY - rect.top - borderY) / Math.max(1, rect.height - borderY - bottom)));
      const base = automaticCrop(effectiveSourceSize.width, effectiveSourceSize.height, inner.width, inner.height);
      const zoom = Math.max(1, Math.min(5, base.width / params.crop.width * Math.exp(-event.deltaY * .0015)));
      setParams(p => ({...p, crop: zoomCropAt(base, p.crop, zoom, focalX, focalY)}));
    };
    element.addEventListener("wheel", onWheel, {passive: false});
    return () => element.removeEventListener("wheel", onWheel);
  }, [effectiveSourceSize?.width, effectiveSourceSize?.height, inner.width, inner.height, borders.top, borders.right, borders.bottom, borders.left, params.width_mm, params.height_mm, params.crop.width, params.mirror]);

  const choose = (e: ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] || null;
    if (!selected) return;
    if (!/^image\/(jpeg|png)$/.test(selected.type)) { setError("Obsługiwane są wyłącznie pliki JPG i PNG."); return; }
    if (source) URL.revokeObjectURL(source);
    const url = URL.createObjectURL(selected);
    setFile(selected); setSource(url); setError("");
    const image = new Image();
    image.onload = () => {
      setSourceSize({width: image.width, height: image.height});
      setParams(p => {
        const orientation = image.height > image.width ? "portrait" : "landscape";
        const short = Math.min(p.width_mm, p.height_mm); const long = Math.max(p.width_mm, p.height_mm);
        const width = orientation === "landscape" ? long : short; const height = orientation === "landscape" ? short : long;
        const area = imageArea(width, height, resolvedBorders(p));
        return {...p, orientation, width_mm: width, height_mm: height, crop: automaticCrop(image.width, image.height, area.width, area.height)};
      });
    };
    image.src = url;
  };

  const generate = async () => {
    if (busyRef.current) return;
    if (!file) { setError("Najpierw wybierz zdjęcie."); return; }
    const invalid = validateParams(params); if (invalid) { setError(invalid); return; }
    busyRef.current = true;
    drag.current = null;
    setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("image", file); body.append("params", JSON.stringify(params));
      const response = await fetch("/api/generate", {method: "POST", body});
      if (!response.ok) { const problem = await response.json(); throw new Error(problem.detail?.message || "Generowanie nie powiodło się."); }
      const blob = await response.blob(); const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = "lithophane.stl"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : "Nieznany błąd"); } finally { busyRef.current = false; setBusy(false); }
  };

  return <main className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span className="mark">L</span><div><strong>Litho</strong><small>Generator litofanii 3D</small></div><span className="version">V1</span></div>
        <div className="product-switch"><button className="active">Litofania</button><button onClick={onOpenHousing}>Obudowa</button></div>
        <div className="sidebar-scroll">
        <h2><span>01</span> Obraz</h2>
        <label className="drop"><input type="file" accept="image/jpeg,image/png" onChange={choose}/><b>{file ? file.name : "Wybierz zdjęcie"}</b><small>JPG lub PNG · maks. 20 MB</small></label>
        <h3>Kadrowanie</h3>
        <button className="auto-crop" disabled={!sourceSize} onClick={() => setParams(p => ({...p, crop: fitCrop(p.width_mm, p.height_mm)}))}>Dopasuj automatycznie</button>
        <Slider label="Pozycja X" value={params.crop.x} min={0} max={1 - params.crop.width} step={.01} onChange={n => setCrop("x", n)}/>
        <Slider label="Pozycja Y" value={params.crop.y} min={0} max={1 - params.crop.height} step={.01} onChange={n => setCrop("y", n)}/>
        <Slider label="Powiększenie" value={effectiveSourceSize ? Number((automaticCrop(effectiveSourceSize.width, effectiveSourceSize.height, inner.width, inner.height).width / params.crop.width).toFixed(2)) : 1} min={1} max={5} step={.05} unit="×" onChange={setZoom}/>
        <div className="rotate-row"><span>Obrót zdjęcia</span><div className="rotate-actions"><button onClick={() => setRotation(params.rotation_degrees - 90)}>↶ 90°</button><label><input type="number" min="0" max="359.9" step="0.1" value={customRotationInput} onChange={e => setCustomRotationInput(e.target.value)} onBlur={e => setRotation(Number.isFinite(Number(e.target.value)) ? Number(e.target.value) : 0)} onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }}/><span>°</span></label><button onClick={() => setRotation(params.rotation_degrees + 90)}>90° ↷</button></div></div>
        <p className="interaction-hint">Na podglądzie: przeciągnij zdjęcie, aby je przesunąć · użyj kółka myszy, aby przybliżyć.</p>
        <h2><span>02</span> Model</h2>
        <div className="orientation"><button className={params.orientation === "landscape" ? "active" : ""} onClick={() => setOrientation("landscape")}>Pozioma</button><button className={params.orientation === "portrait" ? "active" : ""} onClick={() => setOrientation("portrait")}>Pionowa</button></div>
        <h3>Format obrazu</h3>
        <div className="formats format-options">{FORMATS.map(format => { const selected = !customFormat && Math.min(params.width_mm, params.height_mm) === format.short && Math.max(params.width_mm, params.height_mm) === format.long; return <button key={format.label} className={selected ? "active" : ""} onClick={() => setFormat(format.short, format.long)}>{format.label}</button>; })}<button className={customFormat ? "active" : ""} onClick={() => { setCustomWidthInput(String(params.width_mm)); setCustomHeightInput(String(params.height_mm)); setCustomFormat(true); }}>Custom</button></div>
        {customFormat && <div className="custom-size"><label>Szerokość<input type="number" min="20" max="256" step="1" value={customWidthInput} onChange={e => setCustomWidthInput(e.target.value)} onBlur={e => commitCustomDimension("width_mm", e.target.value)} onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }}/><span>mm</span></label><label>Wysokość<input type="number" min="20" max="256" step="1" value={customHeightInput} onChange={e => setCustomHeightInput(e.target.value)} onBlur={e => commitCustomDimension("height_mm", e.target.value)} onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }}/><span>mm</span></label></div>}
        <Slider label="Minimalna grubość" value={params.min_thickness_mm} min={.4} max={4} step={.1} unit=" mm" onChange={n => set("min_thickness_mm", n)}/>
        <Slider label="Maksymalna grubość" value={params.max_thickness_mm} min={.5} max={10} step={.1} unit=" mm" onChange={n => {set("max_thickness_mm", n); if (params.border_height_mm < n) set("border_height_mm", n);}}/>
        <Slider label="Gamma" value={params.gamma} min={.1} max={5} step={.1} onChange={n => set("gamma", n)}/>
        <Slider label="Jasność" value={params.brightness} min={.25} max={2} step={.05} onChange={n => set("brightness", n)}/>
        <Slider label="Kontrast" value={params.contrast} min={.25} max={3} step={.05} onChange={n => set("contrast", n)}/>
        <h3>Średnica dyszy</h3>
        <div className="orientation"><button className={params.nozzle_diameter_mm === .2 ? "active" : ""} onClick={() => setParams(p => ({...p, nozzle_diameter_mm: .2}))}>0,2 mm · detal</button><button className={params.nozzle_diameter_mm === .4 ? "active" : ""} onClick={() => setParams(p => ({...p, nozzle_diameter_mm: .4, border_height_mm: p.border_height_mm < .8 ? .8 : p.border_height_mm}))}>0,4 mm · standard</button></div>
        <h3>Jakość geometrii</h3>
        <div className="formats"><button className={params.quality_profile === "economic" ? "active" : ""} onClick={() => set("quality_profile", "economic")}>Ekonomiczna</button><button className={params.quality_profile === "optimal" ? "active" : ""} onClick={() => set("quality_profile", "optimal")}>Optymalna</button><button className={params.quality_profile === "maximum" ? "active" : ""} onClick={() => set("quality_profile", "maximum")}>Maksymalna</button></div>
        <p className="quality-note">Próbka XY: {grid.pitch.toFixed(3)} mm · linia: {quality.line} mm · warstwa: {quality.layer} mm · siatka obrazu: {gridX} × {gridY}{anyBorder ? ` · z ramką: ${grid.totalCols} × ${grid.totalRows}` : ""}</p>
        <h3>Krawędź panelu</h3>
        <label className="check"><input type="checkbox" checked={params.mounting_flange} onChange={e => setMountingFlange(e.target.checked)}/><span>Kołnierz montażowy Litho Mount V1</span></label>
        {params.mounting_flange && <p className="quality-note flange-note">Stały kołnierz 2,0 mm wokół panelu · grubość 1,6 mm · wewnątrz wybranego formatu. Ręczne ustawienia ramki pozostają zapamiętane.</p>}
        {params.mounting_flange && params.max_thickness_mm > MOUNTING_FLANGE_HEIGHT_MM && <p className="quality-note warning-note">Relief obrazu będzie wystawał ponad kołnierz montażowy. Jest to zamierzone: strefa mocowana w obudowie zachowuje stałą grubość 1,6 mm.</p>}
        {!params.mounting_flange && <>
          {!customBorder && <Slider label="Szerokość ramki (wewnątrz formatu)" value={params.border_width_mm} min={0} max={20} step={.5} unit=" mm" onChange={n => setParams(p => ({...p, border_width_mm: n, border_widths_mm: null, crop: fitCrop(p.width_mm, p.height_mm, n)}))}/>}
          <label className="check compact-check"><input type="checkbox" checked={customBorder} onChange={e => { const enabled = e.target.checked; setCustomBorder(enabled); setParams(p => { const current = resolvedBorders(p); const next = enabled ? current : {top: current.top, right: current.top, bottom: current.top, left: current.top}; const size = sourceSize ? rotatedSize(sourceSize, p.rotation_degrees) : null; const area = imageArea(p.width_mm, p.height_mm, next); return {...p, border_width_mm: next.top, border_widths_mm: enabled ? current : null, crop: size ? automaticCrop(size.width, size.height, area.width, area.height) : p.crop}; }); }}/><span>Ustaw każdy bok ramki osobno</span></label>
          {customBorder && <div className="border-grid"><Slider label="Góra" value={borders.top} min={0} max={20} step={.5} unit=" mm" onChange={n => setBorderSide("top", n)}/><Slider label="Prawo" value={borders.right} min={0} max={20} step={.5} unit=" mm" onChange={n => setBorderSide("right", n)}/><Slider label="Dół" value={borders.bottom} min={0} max={20} step={.5} unit=" mm" onChange={n => setBorderSide("bottom", n)}/><Slider label="Lewo" value={borders.left} min={0} max={20} step={.5} unit=" mm" onChange={n => setBorderSide("left", n)}/></div>}
          {anyBorder && <Slider label="Grubość ramki" value={params.border_height_mm} min={params.nozzle_diameter_mm * 2} max={10} step={.1} unit=" mm" onChange={n => set("border_height_mm", n)}/>}
          {anyBorder && params.border_height_mm < params.max_thickness_mm && <p className="quality-note warning-note">Cienka ramka: ciemne fragmenty reliefu będą wystawały ponad jej powierzchnię. Do ramki ochronnej zalecamy grubość co najmniej równą maksymalnej grubości obrazu.</p>}
        </>}
        <label className="check"><input type="checkbox" checked={params.removable_support} onChange={e => set("removable_support", e.target.checked)}/><span>Dodaj odrywaną stopę do druku pionowego</span></label>
        {params.removable_support && <p className="quality-note">Kompaktowa podpora seryjna · 2 zastrzały, a dla dużych formatów 3 · maks. 45 mm wysokości i 25 mm wysunięcia na stronę · bez brimu w STL · lekko wzmocnione bezpieczniki nadal łatwe do odłamania</p>}
        <label className="check"><input type="checkbox" checked={params.invert} onChange={e => set("invert", e.target.checked)}/><span>Odwróć obraz</span></label>
        <label className="check"><input type="checkbox" checked={params.mirror} onChange={e => set("mirror", e.target.checked)}/><span>Odbij zdjęcie lustrzanie</span></label>
        </div>
        <div className="sidebar-foot">Lokalne przetwarzanie · STL manifold</div>
      </aside>
      <section className="workbench">
      <article className="preview">
        <div className="preview-head"><div><p className="eyebrow">PODGLĄD NA ŻYWO</p><h2>{view === "photo" ? "Przygotowane zdjęcie" : "Symulacja światła"}</h2></div><div className="tabs"><button className={view === "photo" ? "active" : ""} onClick={() => setView("photo")}>Obraz</button><button className={view === "lithophane" ? "active" : ""} onClick={() => setView("lithophane")}>Litofania</button></div></div>
        <div className={`stage crop-stage${busy ? " interaction-locked" : ""}`} aria-busy={busy} style={{aspectRatio: `${params.width_mm} / ${params.height_mm}`, width: `min(100%, ${720 * params.width_mm / params.height_mm}px)`}}>{source ? <canvas ref={canvas} aria-disabled={busy} onPointerDown={beginDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}/> : <div className="empty"><span>＋</span><b>Dodaj fotografię</b><small>Tutaj pojawi się jej podgląd</small></div>}{busy && <div className="interaction-lock" role="status">Generowanie STL — kadr zablokowany</div>}</div>
        <div className="stats"><span><small>WYMIAR</small><b>{params.width_mm} × {params.height_mm} mm</b></span><span><small>GRUBOŚĆ</small><b>{params.min_thickness_mm}–{params.max_thickness_mm} mm</b></span><span><small>SIATKA</small><b>{gridX} × {gridY}</b></span></div>
        {(error || validateParams(params)) && <p className="error">{error || validateParams(params)}</p>}
        <button className="generate" disabled={busy || !file || Boolean(validateParams(params))} onClick={generate}>{busy ? "Generowanie…" : "Generuj i pobierz STL"}<span>→</span></button>
      </article>
      <footer>Pliki są przetwarzane w pamięci i nie są przechowywane na serwerze.</footer>
      </section>
  </main>;
}

export default function App() {
  const [product, setProduct] = useState<"lithophane" | "housing">("lithophane");
  return product === "housing"
    ? <HousingGenerator onOpenLithophane={() => setProduct("lithophane")}/>
    : <LithophaneGenerator onOpenHousing={() => setProduct("housing")}/>;
}
