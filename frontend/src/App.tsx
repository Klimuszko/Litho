import { ChangeEvent, useEffect, useRef, useState } from "react";
import "./formats.css";

export type Params = {
  width_mm: number; height_mm: number; min_thickness_mm: number; max_thickness_mm: number;
  gamma: number; brightness: number; contrast: number; resolution: number;
  orientation: "portrait" | "landscape"; border_width_mm: number; border_height_mm: number;
  invert: boolean; mirror: boolean; crop: {x: number; y: number; width: number; height: number};
};
type Crop = Params["crop"];

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

export const FORMATS = [{label: "10 × 15 cm", short: 100, long: 150}, {label: "13 × 18 cm", short: 130, long: 180}, {label: "15 × 20 cm", short: 150, long: 200}] as const;
const initial: Params = {width_mm: 150, height_mm: 100, min_thickness_mm: .8, max_thickness_mm: 3.2, gamma: 1, brightness: 1, contrast: 1, resolution: 180, orientation: "landscape", border_width_mm: 0, border_height_mm: 3.2, invert: false, mirror: false, crop: {x: 0, y: 0, width: 1, height: 1}};

export function validateParams(p: Params): string {
  const dimensions = [Math.min(p.width_mm, p.height_mm), Math.max(p.width_mm, p.height_mm)].join("x");
  if (!["100x150", "130x180", "150x200"].includes(dimensions)) return "Wybierz jeden z trzech obsługiwanych formatów.";
  if (p.max_thickness_mm <= p.min_thickness_mm) return "Maksymalna grubość musi być większa od minimalnej.";
  if (p.max_thickness_mm - p.min_thickness_mm > 12) return "Zakres grubości nie może przekraczać 12 mm.";
  if (p.border_width_mm > 0 && p.border_height_mm < p.max_thickness_mm) return "Ramka nie może być niższa od reliefu.";
  if (p.width_mm + 2 * p.border_width_mm > 256 || p.height_mm + 2 * p.border_width_mm > 256) return "Model z ramką musi zmieścić się w obszarze 256 × 256 mm.";
  return "";
}

function Slider({label, value, min, max, step, unit = "", onChange}: {label: string; value: number; min: number; max: number; step: number; unit?: string; onChange: (n: number) => void}) {
  return <label className="control"><span>{label}<output>{value}{unit}</output></span><input type="range" value={value} min={min} max={max} step={step} onChange={e => onChange(Number(e.target.value))}/></label>;
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<string>("");
  const [params, setParams] = useState(initial);
  const [view, setView] = useState<"photo" | "lithophane">("photo");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sourceSize, setSourceSize] = useState<{width: number; height: number} | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const set = <K extends keyof Params>(key: K, value: Params[K]) => setParams(p => ({...p, [key]: value}));
  const setCrop = (key: keyof Params["crop"], value: number) => setParams(p => ({...p, crop: {...p.crop, [key]: value}}));
  const fitCrop = (width: number, height: number) => sourceSize ? automaticCrop(sourceSize.width, sourceSize.height, width, height) : params.crop;
  const setFormat = (short: number, long: number) => setParams(p => {
    const width = p.orientation === "landscape" ? long : short; const height = p.orientation === "landscape" ? short : long;
    return {...p, width_mm: width, height_mm: height, crop: sourceSize ? automaticCrop(sourceSize.width, sourceSize.height, width, height) : p.crop};
  });
  const setOrientation = (orientation: Params["orientation"]) => setParams(p => {
    const shouldSwap = orientation === "portrait" ? p.width_mm > p.height_mm : p.height_mm > p.width_mm;
    const width = shouldSwap ? p.height_mm : p.width_mm; const height = shouldSwap ? p.width_mm : p.height_mm;
    return {...p, orientation, width_mm: width, height_mm: height, crop: sourceSize ? automaticCrop(sourceSize.width, sourceSize.height, width, height) : p.crop};
  });
  const setZoom = (zoom: number) => setParams(p => {
    if (!sourceSize) return p;
    const base = automaticCrop(sourceSize.width, sourceSize.height, p.width_mm, p.height_mm);
    return {...p, crop: zoomCrop(base, p.crop, zoom)};
  });

  useEffect(() => () => { if (source) URL.revokeObjectURL(source); }, [source]);
  useEffect(() => {
    if (!source || !canvas.current) return;
    const image = new Image();
    image.onload = () => {
      const c = canvas.current!; const ctx = c.getContext("2d")!;
      const crop = params.crop; const w = 760; const h = Math.max(240, Math.round(w * params.height_mm / params.width_mm));
      c.width = w; c.height = h;
      ctx.filter = `brightness(${params.brightness}) contrast(${params.contrast}) grayscale(1) ${view === "lithophane" ? "invert(1)" : ""}`;
      ctx.save();
      if (params.mirror) { ctx.translate(w, 0); ctx.scale(-1, 1); }
      ctx.drawImage(image, crop.x * image.width, crop.y * image.height, crop.width * image.width, crop.height * image.height, 0, 0, w, h);
      ctx.restore();
      if (view === "lithophane") { ctx.globalCompositeOperation = "screen"; ctx.fillStyle = `rgba(255,177,82,${Math.min(.42, params.gamma / 10)})`; ctx.fillRect(0, 0, w, h); }
    };
    image.src = source;
  }, [source, params, view]);

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
        return {...p, orientation, width_mm: width, height_mm: height, crop: automaticCrop(image.width, image.height, width, height)};
      });
    };
    image.src = url;
  };

  const generate = async () => {
    if (!file) { setError("Najpierw wybierz zdjęcie."); return; }
    const invalid = validateParams(params); if (invalid) { setError(invalid); return; }
    setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("image", file); body.append("params", JSON.stringify(params));
      const response = await fetch("/api/generate", {method: "POST", body});
      if (!response.ok) { const problem = await response.json(); throw new Error(problem.detail?.message || "Generowanie nie powiodło się."); }
      const blob = await response.blob(); const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = "lithophane.stl"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : "Nieznany błąd"); } finally { setBusy(false); }
  };

  return <main>
    <header><div className="brand"><span className="mark">L</span><div><strong>Lumina</strong><small>Generator litofanii 3D</small></div></div><span className="badge">V1 · własny silnik</span></header>
    <section className="hero"><p className="eyebrow">ŚWIATŁO ZAPISANE W MATERIALE</p><h1>Zamień fotografię<br/>w <em>drukowalne wspomnienie.</em></h1><p>Przygotuj obraz, dobierz grubość i pobierz zamknięty model STL gotowy do slicera.</p></section>
    <section className="workspace">
      <aside>
        <h2><span>01</span> Obraz</h2>
        <label className="drop"><input type="file" accept="image/jpeg,image/png" onChange={choose}/><b>{file ? file.name : "Wybierz zdjęcie"}</b><small>JPG lub PNG · maks. 20 MB</small></label>
        <h3>Kadrowanie</h3>
        <button className="auto-crop" disabled={!sourceSize} onClick={() => setParams(p => ({...p, crop: fitCrop(p.width_mm, p.height_mm)}))}>Dopasuj automatycznie</button>
        <Slider label="Pozycja X" value={params.crop.x} min={0} max={1 - params.crop.width} step={.01} onChange={n => setCrop("x", n)}/>
        <Slider label="Pozycja Y" value={params.crop.y} min={0} max={1 - params.crop.height} step={.01} onChange={n => setCrop("y", n)}/>
        <Slider label="Powiększenie" value={sourceSize ? Number((automaticCrop(sourceSize.width, sourceSize.height, params.width_mm, params.height_mm).width / params.crop.width).toFixed(2)) : 1} min={1} max={3} step={.05} unit="×" onChange={setZoom}/>
        <h2><span>02</span> Model</h2>
        <div className="orientation"><button className={params.orientation === "landscape" ? "active" : ""} onClick={() => setOrientation("landscape")}>Pozioma</button><button className={params.orientation === "portrait" ? "active" : ""} onClick={() => setOrientation("portrait")}>Pionowa</button></div>
        <h3>Format obrazu</h3>
        <div className="formats">{FORMATS.map(format => { const selected = Math.min(params.width_mm, params.height_mm) === format.short && Math.max(params.width_mm, params.height_mm) === format.long; return <button key={format.label} className={selected ? "active" : ""} onClick={() => setFormat(format.short, format.long)}>{format.label}</button>; })}</div>
        <Slider label="Minimalna grubość" value={params.min_thickness_mm} min={.4} max={4} step={.1} unit=" mm" onChange={n => set("min_thickness_mm", n)}/>
        <Slider label="Maksymalna grubość" value={params.max_thickness_mm} min={.5} max={10} step={.1} unit=" mm" onChange={n => {set("max_thickness_mm", n); if (params.border_height_mm < n) set("border_height_mm", n);}}/>
        <Slider label="Gamma" value={params.gamma} min={.1} max={5} step={.1} onChange={n => set("gamma", n)}/>
        <Slider label="Jasność" value={params.brightness} min={.25} max={2} step={.05} onChange={n => set("brightness", n)}/>
        <Slider label="Kontrast" value={params.contrast} min={.25} max={3} step={.05} onChange={n => set("contrast", n)}/>
        <Slider label="Rozdzielczość" value={params.resolution} min={24} max={600} step={12} unit=" pkt" onChange={n => set("resolution", n)}/>
        <Slider label="Szerokość ramki (na stronę)" value={params.border_width_mm} min={0} max={20} step={.5} unit=" mm" onChange={n => set("border_width_mm", n)}/>
        <label className="check"><input type="checkbox" checked={params.invert} onChange={e => set("invert", e.target.checked)}/><span>Odwróć obraz</span></label>
        <label className="check"><input type="checkbox" checked={params.mirror} onChange={e => set("mirror", e.target.checked)}/><span>Odbij lustrzanie</span></label>
      </aside>
      <article className="preview">
        <div className="preview-head"><div><p className="eyebrow">PODGLĄD NA ŻYWO</p><h2>{view === "photo" ? "Przygotowane zdjęcie" : "Symulacja światła"}</h2></div><div className="tabs"><button className={view === "photo" ? "active" : ""} onClick={() => setView("photo")}>Obraz</button><button className={view === "lithophane" ? "active" : ""} onClick={() => setView("lithophane")}>Litofania</button></div></div>
        <div className="stage">{source ? <canvas ref={canvas}/> : <div className="empty"><span>＋</span><b>Dodaj fotografię</b><small>Tutaj pojawi się jej podgląd</small></div>}</div>
        <div className="stats"><span><small>WYMIAR</small><b>{params.width_mm} × {params.height_mm} mm</b></span><span><small>GRUBOŚĆ</small><b>{params.min_thickness_mm}–{params.max_thickness_mm} mm</b></span><span><small>SIATKA</small><b>do {params.resolution} pkt</b></span></div>
        {(error || validateParams(params)) && <p className="error">{error || validateParams(params)}</p>}
        <button className="generate" disabled={busy || !file || Boolean(validateParams(params))} onClick={generate}>{busy ? "Generowanie…" : "Generuj i pobierz STL"}<span>→</span></button>
      </article>
    </section>
    <footer>Pliki są przetwarzane w pamięci i nie są przechowywane na serwerze.</footer>
  </main>;
}
