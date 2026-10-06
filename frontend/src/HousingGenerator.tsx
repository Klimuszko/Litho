import { useState } from "react";
import "./housing.css";
import {useAuth} from "./Auth";

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
  usb_side: "left" | "right";
  electronics_position: "bottom" | "top";
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
  back_thickness_mm: 2.4, usb_side: "right", electronics_position: "bottom",
};

export function housingOuterSize(params: HousingParams) {
  const margin = params.kind === "frame" ? params.frame_border_mm : params.wall_mm + params.clearance_mm;
  return {width: params.panel_width_mm + 2 * margin, height: params.panel_height_mm + 2 * margin};
}

export function housingClipCount(params: HousingParams) {
  // Frames with wedge sockets carry three clips per edge, halfway between the sockets.
  const wedgeSockets = params.kind === "frame" && params.frame_border_mm - params.clearance_mm / 2 - params.wall_mm >= 4;
  const edgeCount = (length: number) => wedgeSockets && length / 6 >= 10.51 ? 3 : length >= 175 ? 4 : length >= 125 ? 3 : 2;
  return 2 * (edgeCount(params.panel_width_mm) + edgeCount(params.panel_height_mm));
}

export function housingBackSnapCount(params: HousingParams) {
  const edgeCount = (length: number) => length >= 175 ? 4 : length >= 125 ? 3 : 2;
  const outer = housingOuterSize(params);
  return 2 * (edgeCount(outer.width) + edgeCount(outer.height));
}

export function housingPreviewSize(params: HousingParams, maxWidth = 520, maxHeight = 390) {
  const outer = housingOuterSize(params);
  const scale = Math.min(maxWidth / outer.width, maxHeight / outer.height);
  return {width: outer.width * scale, height: outer.height * scale};
}

export function validateHousing(params: HousingParams): string {
  if (params.panel_width_mm < 20 || params.panel_height_mm < 20) return "Panel musi mieć co najmniej 20 × 20 mm.";
  const outer = housingOuterSize(params);
  if (outer.width > 256 || outer.height > 256) return "Obudowa nie mieści się na stole 256 × 256 mm.";
  if (params.depth_mm < 27) return "Mocowanie USB-C wymaga co najmniej 27 mm głębokości obudowy.";
  if (outer.height < 59) return "Obudowa jest za niska na pionowe mocowanie ściemniacza.";
  return "";
}

function Range({label, value, min, max, step, onChange}: {label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void}) {
  return <label className="control"><span>{label}<output>{value} mm</output></span><input type="range" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))}/></label>;
}

export default function HousingGenerator({active, onOpenLithophane}: {active: boolean; onOpenLithophane: () => void}) {
  const {apiFetch} = useAuth();
  const [params, setParams] = useState(initialHousing);
  const [custom, setCustom] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const outer = housingOuterSize(params);
  const previewSize = housingPreviewSize(params);
  const clipCount = housingClipCount(params);
  const backSnapCount = housingBackSnapCount(params);
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
  const setElectronicsPlacement = (usb_side: HousingParams["usb_side"], electronics_position: HousingParams["electronics_position"]) =>
    setParams(current => ({...current, usb_side, electronics_position}));
  const setDimension = (key: "panel_width_mm" | "panel_height_mm", raw: string) => {
    const value = Math.max(20, Math.min(250, Number(raw) || 20));
    setCustom(true); set(key, value);
  };
  const generate = async () => {
    const invalid = validateHousing(params);
    if (invalid) { setError(invalid); return; }
    setBusy(true); setError("");
    try {
      const response = await apiFetch("/api/housing/generate", {
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

  return <main className="app-shell housing-shell" hidden={!active}>
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
        <p className="quality-note flange-note">Wymagany panel z opcją „Kołnierz montażowy Litho Mount V1”. Panel wkłada się od tyłu i dociska pod sprężyste zatrzaski — bez kleju. W ramce panel dodatkowo blokują drukowane kliny wsuwane w gniazda obok panelu.</p>
        <h2><span>03</span> Głębokość</h2>
        <Range label="Głębokość obudowy" value={params.depth_mm} min={20} max={80} step={1} onChange={value => set("depth_mm", value)}/>
        <h2><span>04</span> Zasilanie i sterowanie</h2>
        <div className="housing-toggle"><span><b>Stały zestaw elektroniki</b><small>USB-C oraz sterownik zbliżeniowy 37,04 × 10,08 mm</small></span><strong>WYMAGANY</strong></div>
        <h3>Położenie USB-C i sterownika</h3>
        <div className="electronics-placement">
          <button className={params.usb_side === "left" && params.electronics_position === "top" ? "active" : ""} onClick={() => setElectronicsPlacement("left", "top")}>Lewy górny bok</button>
          <button className={params.usb_side === "right" && params.electronics_position === "top" ? "active" : ""} onClick={() => setElectronicsPlacement("right", "top")}>Prawy górny bok</button>
          <button className={params.usb_side === "left" && params.electronics_position === "bottom" ? "active" : ""} onClick={() => setElectronicsPlacement("left", "bottom")}>Lewy dolny bok</button>
          <button className={params.usb_side === "right" && params.electronics_position === "bottom" ? "active" : ""} onClick={() => setElectronicsPlacement("right", "bottom")}>Prawy dolny bok</button>
        </div>
        <p className="quality-note housing-note">USB-C: 8,85 × 3,12 mm, płytka 14,02 mm. Oba elementy wsuwa się od tyłu w masywne kieszenie drukowane bez podpór i blokuje drukowanymi klinami (osobny plik STL). Antena sprężynowa dotyka ścianki z lekkim dociskiem 0,4 mm.</p>
        <div className="housing-spec">
          <span><small>KIESZEŃ PANELU</small><b>{(params.panel_thickness_mm + params.clearance_mm).toFixed(1)} mm</b></span>
          <span><small>KLIPSY PANELU</small><b>{clipCount} × 0.4 mm</b></span>
          <span><small>PRZYŁĄCZE</small><b>{`USB-C · ${params.usb_side === "left" ? "lewy" : "prawy"} ${params.electronics_position === "bottom" ? "dół" : "góra"}`}</b></span>
        </div>
      </div>
      <div className="sidebar-foot">Zintegrowane zatrzaski · bez kleju · pokrywa serwisowa</div>
    </aside>
    <section className="workbench housing-workbench">
      <article className="preview housing-preview">
        <div className="preview-head"><div><p className="eyebrow">PODGLĄD KONSTRUKCJI</p><h2>{params.kind === "box" ? "Podświetlany Box" : "Podświetlana ramka"}</h2></div><span className="housing-badge">{clipCount} klipsów panelu · {backSnapCount} zatrzasków pokrywy</span></div>
        <div className="housing-stage">
          <div className={`housing-model ${params.kind}`} style={{width: `${previewSize.width}px`, height: `${previewSize.height}px`, padding: `${visualBorder}px`}}>
            <div className="housing-panel"><span>LITHO</span><small>{params.panel_width_mm} × {params.panel_height_mm} mm</small></div>
            <div className={`electronics-marker ${params.usb_side} ${params.electronics_position}`}><i>USB-C</i><i>DOTYK</i></div>
          </div>
          <div className="depth-preview"><div style={{width: `${Math.max(70, params.depth_mm * 2)}px`}}/><span>{params.depth_mm} mm</span></div>
        </div>
        <div className="stats"><span><small>PANEL LITHO</small><b>{params.panel_width_mm} × {params.panel_height_mm} mm</b></span><span><small>OBUDOWA</small><b>{outer.width.toFixed(1)} × {outer.height.toFixed(1)} × {params.depth_mm} mm</b></span><span><small>ZESTAW</small><b>{params.kind === "frame" && params.frame_border_mm - params.clearance_mm / 2 - params.wall_mm >= 4 ? "4 pliki STL" : "3 pliki STL"}</b></span></div>
        {(error || validateHousing(params)) && <p className="error">{error || validateHousing(params)}</p>}
        <button className="generate" disabled={busy || Boolean(validateHousing(params))} onClick={generate}>{busy ? "Generowanie zestawu…" : "Generuj korpus i pokrywę ZIP"}<span>→</span></button>
      </article>
    </section>
  </main>;
}
