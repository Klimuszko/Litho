import { useState } from "react";
import "./housing.css";

export type HousingParams = {
  kind: "box" | "frame";
  panel_width_mm: number;
  panel_height_mm: number;
  panel_thickness_mm: number;
  clearance_mm: number;
  depth_mm: number;
  wall_mm: number;
  frame_border_mm: number;
  bezel_overlap_mm: number;
  back_thickness_mm: number;
  cable_width_mm: number;
  cable_height_mm: number;
};

export const HOUSING_FORMATS = [
  {label: "10 × 15 cm", short: 100, long: 150},
  {label: "13 × 18 cm", short: 130, long: 180},
  {label: "15 × 20 cm", short: 150, long: 200},
] as const;

export const initialHousing: HousingParams = {
  kind: "box", panel_width_mm: 150, panel_height_mm: 100,
  panel_thickness_mm: 1.6, clearance_mm: .4, depth_mm: 40,
  wall_mm: 2.4, frame_border_mm: 12, bezel_overlap_mm: 1.2,
  back_thickness_mm: 2.4, cable_width_mm: 12, cable_height_mm: 8,
};

export function housingOuterSize(params: HousingParams) {
  const margin = params.kind === "frame" ? params.frame_border_mm : params.wall_mm + params.clearance_mm;
  return {width: params.panel_width_mm + 2 * margin, height: params.panel_height_mm + 2 * margin};
}

export function housingClipCount(params: HousingParams) {
  return Math.max(params.panel_width_mm, params.panel_height_mm) >= 175 ? 6 : 4;
}

export function validateHousing(params: HousingParams): string {
  if (params.panel_width_mm < 20 || params.panel_height_mm < 20) return "Panel musi mieć co najmniej 20 × 20 mm.";
  const outer = housingOuterSize(params);
  if (outer.width > 256 || outer.height > 256) return "Obudowa nie mieści się na stole 256 × 256 mm.";
  return "";
}

function Range({label, value, min, max, step, onChange}: {label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void}) {
  return <label className="control"><span>{label}<output>{value} mm</output></span><input type="range" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))}/></label>;
}

export default function HousingGenerator({onOpenLithophane}: {onOpenLithophane: () => void}) {
  const [params, setParams] = useState(initialHousing);
  const [custom, setCustom] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const outer = housingOuterSize(params);
  const clipCount = housingClipCount(params);
  const landscape = params.panel_width_mm >= params.panel_height_mm;
  const set = <K extends keyof HousingParams>(key: K, value: HousingParams[K]) => setParams(current => ({...current, [key]: value}));
  const chooseFormat = (short: number, long: number) => {
    setCustom(false);
    setParams(current => ({...current, panel_width_mm: landscape ? long : short, panel_height_mm: landscape ? short : long}));
  };
  const setOrientation = (nextLandscape: boolean) => setParams(current => {
    const short = Math.min(current.panel_width_mm, current.panel_height_mm);
    const long = Math.max(current.panel_width_mm, current.panel_height_mm);
    return {...current, panel_width_mm: nextLandscape ? long : short, panel_height_mm: nextLandscape ? short : long};
  });
  const setDimension = (key: "panel_width_mm" | "panel_height_mm", raw: string) => {
    const value = Math.max(20, Math.min(250, Number(raw) || 20));
    setCustom(true); set(key, value);
  };
  const generate = async () => {
    const invalid = validateHousing(params);
    if (invalid) { setError(invalid); return; }
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/housing/generate", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(params),
      });
      if (!response.ok) {
        const problem = await response.json();
        throw new Error(problem.detail?.message || problem.message || "Generowanie obudowy nie powiodło się.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `litho-${params.kind}-${params.panel_width_mm}x${params.panel_height_mm}.zip`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Nieznany błąd");
    } finally { setBusy(false); }
  };

  const selectedPreset = HOUSING_FORMATS.find(format =>
    Math.min(params.panel_width_mm, params.panel_height_mm) === format.short
    && Math.max(params.panel_width_mm, params.panel_height_mm) === format.long
  );
  const visualBorder = params.kind === "frame" ? Math.max(12, Math.min(30, params.frame_border_mm * .9)) : 4;

  return <main className="app-shell housing-shell">
    <aside className="sidebar">
      <div className="sidebar-brand"><span className="mark">L</span><div><strong>Litho</strong><small>Generator obudów 3D</small></div><span className="version">V1</span></div>
      <div className="product-switch"><button onClick={onOpenLithophane}>Litofania</button><button className="active">Obudowa</button></div>
      <div className="sidebar-scroll">
        <h2><span>01</span> Typ obudowy</h2>
        <div className="housing-kind">
          <button className={params.kind === "box" ? "active" : ""} onClick={() => set("kind", "box")}><b>Box</b><small>Front bez widocznej ramki</small></button>
          <button className={params.kind === "frame" ? "active" : ""} onClick={() => set("kind", "frame")}><b>Ramka</b><small>Obramowanie od frontu</small></button>
        </div>
        <h2><span>02</span> Wymiar Litho</h2>
        <div className="formats"><button className={landscape ? "active" : ""} onClick={() => setOrientation(true)}>Pozioma</button><button className={!landscape ? "active" : ""} onClick={() => setOrientation(false)}>Pionowa</button></div>
        <div className="housing-presets">{HOUSING_FORMATS.map(format => <button key={format.label} className={!custom && selectedPreset === format ? "active" : ""} onClick={() => chooseFormat(format.short, format.long)}>{format.label}</button>)}<button className={custom ? "active" : ""} onClick={() => setCustom(true)}>Custom</button></div>
        {custom && <div className="dimension-grid"><label>Szerokość<input type="number" min="20" max="250" value={params.panel_width_mm} onChange={event => setDimension("panel_width_mm", event.target.value)}/><span>mm</span></label><label>Wysokość<input type="number" min="20" max="250" value={params.panel_height_mm} onChange={event => setDimension("panel_height_mm", event.target.value)}/><span>mm</span></label></div>}
        <p className="quality-note housing-note">Podajesz dokładny wymiar gotowej litofanii. Kieszeń montażowa i obudowa są doliczane automatycznie.</p>
        <p className="quality-note flange-note">Wymagany panel z opcją „Kołnierz montażowy Litho Mount V1”. Panel wkłada się od tyłu i dociska pod sprężyste zatrzaski — bez kleju.</p>
        <h2><span>03</span> Głębokość</h2>
        <Range label="Głębokość obudowy" value={params.depth_mm} min={20} max={80} step={1} onChange={value => set("depth_mm", value)}/>
        <div className="housing-spec">
          <span><small>KIESZEŃ PANELU</small><b>{(params.panel_thickness_mm + params.clearance_mm).toFixed(1)} mm</b></span>
          <span><small>ZATRZASKI</small><b>{clipCount} × 0.4 mm</b></span>
          <span><small>PRZEWÓD</small><b>{params.cable_width_mm} × {params.cable_height_mm} mm</b></span>
        </div>
      </div>
      <div className="sidebar-foot">Zintegrowane zatrzaski · bez kleju · pokrywa serwisowa</div>
    </aside>
    <section className="workbench housing-workbench">
      <article className="preview housing-preview">
        <div className="preview-head"><div><p className="eyebrow">PODGLĄD KONSTRUKCJI</p><h2>{params.kind === "box" ? "Podświetlany Box" : "Podświetlana ramka"}</h2></div><span className="housing-badge">{clipCount} zatrzasków · bez kleju</span></div>
        <div className="housing-stage">
          <div className={`housing-model ${params.kind}`} style={{aspectRatio: `${outer.width} / ${outer.height}`, padding: `${visualBorder}px`}}>
            <div className="housing-panel"><span>LITHO</span><small>{params.panel_width_mm} × {params.panel_height_mm} mm</small></div>
          </div>
          <div className="depth-preview"><div style={{width: `${Math.max(70, params.depth_mm * 2)}px`}}/><span>{params.depth_mm} mm</span></div>
        </div>
        <div className="stats"><span><small>PANEL LITHO</small><b>{params.panel_width_mm} × {params.panel_height_mm} mm</b></span><span><small>OBUDOWA</small><b>{outer.width.toFixed(1)} × {outer.height.toFixed(1)} × {params.depth_mm} mm</b></span><span><small>ZESTAW</small><b>2 pliki STL</b></span></div>
        {(error || validateHousing(params)) && <p className="error">{error || validateHousing(params)}</p>}
        <button className="generate" disabled={busy || Boolean(validateHousing(params))} onClick={generate}>{busy ? "Generowanie zestawu…" : "Generuj korpus i pokrywę ZIP"}<span>→</span></button>
      </article>
    </section>
  </main>;
}
