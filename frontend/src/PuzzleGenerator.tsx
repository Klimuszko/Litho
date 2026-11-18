import {ChangeEvent, useEffect, useRef, useState} from "react";
import "./puzzle.css";
import {useAuth} from "./Auth";

export type PuzzleParams = {
  width_mm: number;
  height_mm: number;
  piece_count: 36 | 64 | 100 | 144 | 225;
  color_count: number;
  color_layout: "layered" | "same_layer";
  image_style: "auto" | "color" | "sepia" | "grayscale";
  available_colors: string[];
  base_thickness_mm: number;
  color_thickness_mm: number;
  piece_clearance_mm: number;
  color_pixel_mm: number;
  frame_border_mm: number;
  frame_clearance_mm: number;
  brightness: number;
  contrast: number;
  saturation: number;
  detail_strength: number;
  mirror: boolean;
  rotation_degrees: number;
  crop: {x: number; y: number; width: number; height: number};
};

type ImageSize = {width: number; height: number};

export const PUZZLE_COUNTS = [36, 64, 100, 144, 225] as const;
export const PUZZLE_FORMATS = [
  {label: "12 × 16 cm", width: 120, height: 160},
  {label: "15 × 20 cm", width: 150, height: 200},
  {label: "20 × 22 cm", width: 200, height: 220},
] as const;

export const DEFAULT_FILAMENT_COLORS = [
  "#111111", "#F5F3E8", "#8A8D91", "#D62828", "#F77F00",
  "#F4D35E", "#8AC926", "#2A9D5B", "#1B998B", "#32BDE8",
  "#277DA1", "#2541B2", "#6A4C93", "#B5179E", "#FF70A6",
  "#7F4F24", "#B08968", "#DDB892", "#E9C46A", "#6D071A",
] as const;

export const initialPuzzle: PuzzleParams = {
  width_mm: 150,
  height_mm: 200,
  piece_count: 100,
  color_count: 4,
  color_layout: "layered",
  image_style: "auto",
  available_colors: [...DEFAULT_FILAMENT_COLORS],
  base_thickness_mm: 2,
  color_thickness_mm: .2,
  piece_clearance_mm: .18,
  color_pixel_mm: .8,
  frame_border_mm: 10,
  frame_clearance_mm: .6,
  brightness: 1,
  contrast: 1.1,
  saturation: 1,
  detail_strength: 1,
  mirror: false,
  rotation_degrees: 0,
  crop: {x: 0, y: 0, width: 1, height: 1},
};

export function puzzleGridSize(count: PuzzleParams["piece_count"]) {
  return Math.sqrt(count);
}

export function puzzleFrameSize(params: PuzzleParams) {
  return {
    width: params.width_mm + 2 * params.frame_border_mm,
    height: params.height_mm + 2 * params.frame_border_mm,
    printHeight: params.height_mm + 2 * params.frame_border_mm + 7,
  };
}

export function puzzleTotalThickness(params: PuzzleParams) {
  const colorBands = params.color_layout === "same_layer" ? 1 : params.color_count - 1;
  return params.base_thickness_mm + colorBands * params.color_thickness_mm;
}

export function validatePuzzle(params: PuzzleParams): string {
  const grid = puzzleGridSize(params.piece_count);
  if (params.color_count < 3 || params.color_count > 12) return "Wybierz od 3 do 12 kolorów.";
  if (params.available_colors.length < params.color_count) return "Dodaj co najmniej tyle dostępnych filamentów, ile kolorów ma użyć projekt.";
  if (new Set(params.available_colors.map(color => color.toUpperCase())).size !== params.available_colors.length) return "Każdy dostępny filament musi mieć inny kolor.";
  if (Math.min(params.width_mm / grid, params.height_mm / grid) < 9) {
    return "Elementy byłyby mniejsze niż 9 mm. Wybierz większy format albo mniej puzzli.";
  }
  const frame = puzzleFrameSize(params);
  if (frame.width > 250 || frame.printHeight > 250) {
    return "Ramka z zawiasem nie mieści się na stole 250 × 250 mm.";
  }
  return "";
}

function automaticCrop(source: ImageSize, width: number, height: number) {
  const sourceAspect = source.width / source.height;
  const targetAspect = width / height;
  if (sourceAspect > targetAspect) {
    const cropWidth = targetAspect / sourceAspect;
    return {x: (1 - cropWidth) / 2, y: 0, width: cropWidth, height: 1};
  }
  const cropHeight = sourceAspect / targetAspect;
  return {x: 0, y: (1 - cropHeight) / 2, width: 1, height: cropHeight};
}

function Range({label, value, min, max, step, unit = "", onChange}: {
  label: string; value: number; min: number; max: number; step: number; unit?: string;
  onChange: (value: number) => void;
}) {
  return <label className="puzzle-control">
    <span>{label}<output>{value}{unit}</output></span>
    <input type="range" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))}/>
  </label>;
}

async function responseMessage(response: Response, fallback: string) {
  try {
    const problem = await response.json();
    return problem.detail?.message || problem.message || fallback;
  } catch {
    return fallback;
  }
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function PuzzleGenerator({active, onOpenLithophane, onOpenHousing}: {
  active: boolean;
  onOpenLithophane: () => void;
  onOpenHousing: () => void;
}) {
  const {apiFetch} = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const [params, setParams] = useState(initialPuzzle);
  const [file, setFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceSize, setSourceSize] = useState<ImageSize | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [palette, setPalette] = useState<string[]>([]);
  const [resolvedStyle, setResolvedStyle] = useState("");
  const sourceUrlRef = useRef("");
  const previewUrlRef = useRef("");
  const [previewBusy, setPreviewBusy] = useState(false);
  const [puzzleBusy, setPuzzleBusy] = useState(false);
  const [frameBusy, setFrameBusy] = useState(false);
  const [error, setError] = useState("");
  const frame = puzzleFrameSize(params);
  const grid = puzzleGridSize(params.piece_count);
  const pieceWidth = params.width_mm / grid;
  const pieceHeight = params.height_mm / grid;
  const printWidth = params.width_mm + (grid - 1) * 1.2 + 6;
  const printHeight = params.height_mm + (grid - 1) * 1.2 + 6;
  const portrait = params.height_mm >= params.width_mm;
  const selectedFormat = PUZZLE_FORMATS.find(format =>
    Math.min(params.width_mm, params.height_mm) === Math.min(format.width, format.height)
    && Math.max(params.width_mm, params.height_mm) === Math.max(format.width, format.height)
  );
  const styleName = (style: string) => style === "color" ? "kolor" : style === "sepia" ? "sepia" : style === "grayscale" ? "czarno-białe" : "automatycznie";
  const previewStyle = params.image_style === "auto"
    ? (resolvedStyle ? `auto: ${styleName(resolvedStyle)}` : "obróbka auto")
    : styleName(params.image_style);

  const set = <K extends keyof PuzzleParams>(key: K, value: PuzzleParams[K]) =>
    setParams(current => ({...current, [key]: value}));

  const setSize = (width: number, height: number) => setParams(current => ({
    ...current,
    width_mm: width,
    height_mm: height,
    crop: sourceSize ? automaticCrop(sourceSize, width, height) : current.crop,
  }));

  const choose = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] || null;
    if (!selected) return;
    if (!["image/jpeg", "image/png"].includes(selected.type)) {
      setError("Wybierz zdjęcie JPG lub PNG.");
      return;
    }
    if (selected.size > 20 * 1024 * 1024) {
      setError("Zdjęcie przekracza 20 MB.");
      return;
    }
    setError("");
    if (sourceUrlRef.current) URL.revokeObjectURL(sourceUrlRef.current);
    const nextUrl = URL.createObjectURL(selected);
    sourceUrlRef.current = nextUrl;
    setFile(selected);
    setSourceUrl(nextUrl);
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = "";
    setPreviewUrl("");
    setResolvedStyle("");
    const image = new Image();
    image.onload = () => {
      const size = {width: image.naturalWidth, height: image.naturalHeight};
      setSourceSize(size);
      setParams(current => ({...current, crop: automaticCrop(size, current.width_mm, current.height_mm)}));
    };
    image.src = nextUrl;
  };

  useEffect(() => {
    if (!file) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setPreviewBusy(true);
      try {
        const body = new FormData();
        body.append("image", file);
        body.append("params", JSON.stringify(params));
        const response = await apiFetch("/api/puzzle/preview", {method: "POST", body, signal: controller.signal});
        if (!response.ok) throw new Error(await responseMessage(response, "Nie udało się przygotować podglądu."));
        const nextPalette = JSON.parse(response.headers.get("X-Puzzle-Palette") || "[]") as string[];
        const nextResolvedStyle = response.headers.get("X-Puzzle-Image-Style") || params.image_style;
        const blob = await response.blob();
        const nextUrl = URL.createObjectURL(blob);
        if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = nextUrl;
        setPalette(nextPalette);
        setResolvedStyle(nextResolvedStyle);
        setPreviewUrl(nextUrl);
        setError("");
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Nie udało się przygotować podglądu.");
      } finally {
        if (!controller.signal.aborted) setPreviewBusy(false);
      }
    }, 450);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [file, params, apiFetch]);

  useEffect(() => () => {
    if (sourceUrlRef.current) URL.revokeObjectURL(sourceUrlRef.current);
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  const generatePuzzle = async () => {
    const invalid = validatePuzzle(params);
    if (!file || invalid) {
      setError(!file ? "Najpierw dodaj zdjęcie." : invalid);
      return;
    }
    setPuzzleBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("image", file);
      body.append("params", JSON.stringify(params));
      const response = await apiFetch("/api/puzzle/generate", {method: "POST", body});
      if (!response.ok) throw new Error(await responseMessage(response, "Generowanie puzzli nie powiodło się."));
      download(await response.blob(), `litho-puzzle-${params.width_mm}x${params.height_mm}-${params.piece_count}.3mf`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Generowanie puzzli nie powiodło się.");
    } finally {
      setPuzzleBusy(false);
    }
  };

  const generateFrame = async () => {
    const invalid = validatePuzzle(params);
    if (invalid) {
      setError(invalid);
      return;
    }
    setFrameBusy(true);
    setError("");
    try {
      const response = await apiFetch("/api/puzzle/frame", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(params),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "Generowanie ramki nie powiodło się."));
      download(await response.blob(), `litho-puzzle-ramka-${params.width_mm}x${params.height_mm}.zip`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Generowanie ramki nie powiodło się.");
    } finally {
      setFrameBusy(false);
    }
  };

  const zoom = sourceSize ? automaticCrop(sourceSize, params.width_mm, params.height_mm).width / params.crop.width : 1;
  const setZoom = (nextZoom: number) => {
    if (!sourceSize) return;
    const base = automaticCrop(sourceSize, params.width_mm, params.height_mm);
    setParams(current => {
      const width = base.width / nextZoom;
      const height = base.height / nextZoom;
      const centerX = current.crop.x + current.crop.width / 2;
      const centerY = current.crop.y + current.crop.height / 2;
      return {...current, crop: {
        x: Math.max(0, Math.min(1 - width, centerX - width / 2)),
        y: Math.max(0, Math.min(1 - height, centerY - height / 2)),
        width,
        height,
      }};
    });
  };

  const updateAvailableColor = (index: number, color: string) =>
    setParams(current => ({
      ...current,
      available_colors: current.available_colors.map((currentColor, currentIndex) => currentIndex === index ? color.toUpperCase() : currentColor),
    }));

  const removeAvailableColor = (index: number) => setParams(current => {
    if (current.available_colors.length <= 3) return current;
    const available_colors = current.available_colors.filter((_, currentIndex) => currentIndex !== index);
    return {...current, available_colors, color_count: Math.min(current.color_count, available_colors.length)};
  });

  const addAvailableColor = () => setParams(current => {
    if (current.available_colors.length >= 40) return current;
    const seed = (current.available_colors.length * 2654435761) & 0xFFFFFF;
    let color = `#${seed.toString(16).padStart(6, "0").toUpperCase()}`;
    while (current.available_colors.includes(color)) {
      color = `#${((parseInt(color.slice(1), 16) + 0x12345) & 0xFFFFFF).toString(16).padStart(6, "0").toUpperCase()}`;
    }
    return {...current, available_colors: [...current.available_colors, color]};
  });

  return <main className="app-shell puzzle-shell" hidden={!active}>
    <aside className="sidebar">
      <div className="sidebar-brand"><span className="mark">L</span><div><strong>Litho</strong><small>Generator puzzli 3D</small></div><span className="version">V1</span></div>
      <div className="product-switch">
        <button onClick={onOpenLithophane}>Litofania</button>
        <button onClick={onOpenHousing}>Obudowa</button>
        <button className="active">Puzzle</button>
      </div>
      <div className="sidebar-scroll">
        <h2><span>01</span> Zdjęcie</h2>
        <label className="drop"><input ref={input} type="file" accept="image/jpeg,image/png" onChange={choose}/><b>{file?.name || "Wybierz zdjęcie"}</b><small>JPG lub PNG · maks. 20 MB</small></label>
        <div className="puzzle-image-actions">
          <button disabled={!sourceSize} onClick={() => sourceSize && set("crop", automaticCrop(sourceSize, params.width_mm, params.height_mm))}>Dopasuj kadr</button>
          <button onClick={() => set("rotation_degrees", (params.rotation_degrees + 90) % 360)}>Obróć 90°</button>
        </div>
        <Range label="Powiększenie kadru" value={Number(zoom.toFixed(2))} min={1} max={3} step={.05} unit="×" onChange={setZoom}/>
        <label className="check"><input type="checkbox" checked={params.mirror} onChange={event => set("mirror", event.target.checked)}/><span>Odbij zdjęcie lustrzanie</span></label>

        <h2><span>02</span> Format</h2>
        <div className="orientation"><button className={!portrait ? "active" : ""} onClick={() => setSize(Math.max(params.width_mm, params.height_mm), Math.min(params.width_mm, params.height_mm))}>Pozioma</button><button className={portrait ? "active" : ""} onClick={() => setSize(Math.min(params.width_mm, params.height_mm), Math.max(params.width_mm, params.height_mm))}>Pionowa</button></div>
        <div className="puzzle-formats">
          {PUZZLE_FORMATS.map(format => <button key={format.label} className={selectedFormat === format ? "active" : ""} onClick={() => setSize(portrait ? format.width : format.height, portrait ? format.height : format.width)}>{format.label}</button>)}
        </div>
        <div className="dimension-grid">
          <label>Szerokość<input type="number" min="100" max="230" value={params.width_mm} onChange={event => setSize(Math.max(100, Math.min(230, Number(event.target.value) || 100)), params.height_mm)}/><span>mm</span></label>
          <label>Wysokość<input type="number" min="100" max="230" value={params.height_mm} onChange={event => setSize(params.width_mm, Math.max(100, Math.min(230, Number(event.target.value) || 100)))}/><span>mm</span></label>
        </div>

        <h2><span>03</span> Puzzle i kolory</h2>
        <h3>Liczba elementów</h3>
        <div className="puzzle-counts">{PUZZLE_COUNTS.map(count => {
          const countGrid = puzzleGridSize(count);
          const disabled = Math.min(params.width_mm / countGrid, params.height_mm / countGrid) < 9;
          return <button key={count} disabled={disabled} className={params.piece_count === count ? "active" : ""} onClick={() => set("piece_count", count)}>{count}<small>{countGrid} × {countGrid}</small></button>;
        })}</div>
        <h3>Przygotowanie zdjęcia</h3>
        <div className="puzzle-image-styles">
          <button type="button" className={params.image_style === "auto" ? "active" : ""} onClick={() => set("image_style", "auto")}>
            <b>Automatyczne</b><small>Przy 4 kolorach stawia na czytelność tonalną</small>
          </button>
          <button type="button" className={params.image_style === "color" ? "active" : ""} onClick={() => set("image_style", "color")}>
            <b>Kolor</b><small>Zachowuje charakterystyczne barwy fotografii</small>
          </button>
          <button type="button" className={params.image_style === "sepia" ? "active" : ""} onClick={() => set("image_style", "sepia")}>
            <b>Sepia</b><small>Ciepła skala tonalna, dobra przy 3–5 kolorach</small>
          </button>
          <button type="button" className={params.image_style === "grayscale" ? "active" : ""} onClick={() => set("image_style", "grayscale")}>
            <b>Czarno-białe</b><small>Neutralna skala od czerni do bieli</small>
          </button>
        </div>
        <Range label="Liczba kolorów w projekcie" value={params.color_count} min={3} max={Math.min(12, params.available_colors.length)} step={1} onChange={value => set("color_count", value)}/>
        <p className="quality-note puzzle-note">Tryb automatyczny wyrównuje światło, chroni kontury i najpierw rozpoznaje ważne role kolorów w zdjęciu. Dopiero potem dopasowuje je do filamentów, które masz.</p>
        <div className="inventory-title"><h3>Dostępne filamenty</h3><span>{params.available_colors.length}</span></div>
        <div className="filament-inventory">
          {params.available_colors.map((color, index) => <div className="filament-color" key={index}>
            <input type="color" value={color} onChange={event => updateAvailableColor(index, event.target.value)} title={`Filament ${index + 1}: ${color}`}/>
            <button type="button" disabled={params.available_colors.length <= 3} onClick={() => removeAvailableColor(index)} aria-label={`Usuń filament ${index + 1}`}>×</button>
          </div>)}
          <button type="button" className="add-filament" disabled={params.available_colors.length >= 40} onClick={addAvailableColor}>＋</button>
        </div>
        <div className="puzzle-palette" aria-label="Paleta zdjęcia">
          {palette.length ? palette.map((color, index) => <span className={index === 0 ? "base-color" : ""} key={color + index} style={{background: color}} title={index === 0 ? `Podkład: ${color}` : `Warstwa ${index + 1}: ${color}`}>{index === 0 && <i>PODKŁAD</i>}</span>) : Array.from({length: params.color_count}, (_, index) => <span key={index} className="empty-swatch"/>)}
        </div>
        <Range label="Jasność" value={params.brightness} min={.5} max={1.5} step={.05} onChange={value => set("brightness", value)}/>
        <Range label="Kontrast" value={params.contrast} min={.5} max={2} step={.05} onChange={value => set("contrast", value)}/>
        {(params.image_style === "auto" || params.image_style === "color") && <Range label="Nasycenie" value={params.saturation} min={0} max={2} step={.05} onChange={value => set("saturation", value)}/>}
        <Range label="Wyrazistość detali" value={params.detail_strength} min={0} max={2} step={.1} onChange={value => set("detail_strength", value)}/>

        <h2><span>04</span> Wydruk</h2>
        <h3>Układ kolorów</h3>
        <div className="puzzle-color-layouts">
          <button type="button" className={params.color_layout === "layered" ? "active" : ""} onClick={() => set("color_layout", "layered")}>
            <b>Warstwowo</b><small>Bez AMS · każdy kolor na innej wysokości</small>
          </button>
          <button type="button" className={params.color_layout === "same_layer" ? "active" : ""} onClick={() => set("color_layout", "same_layer")}>
            <b>Jedna wysokość</b><small>AMS · wszystkie kolory na płaskiej powierzchni</small>
          </button>
        </div>
        <Range label="Grubość podstawy" value={params.base_thickness_mm} min={1.4} max={3} step={.1} unit=" mm" onChange={value => set("base_thickness_mm", value)}/>
        <Range label={params.color_layout === "layered" ? "Wysokość jednej warstwy koloru" : "Grubość kolorowej powierzchni"} value={params.color_thickness_mm} min={.08} max={.4} step={.04} unit=" mm" onChange={value => set("color_thickness_mm", value)}/>
        <Range label="Luz elementów" value={params.piece_clearance_mm} min={.1} max={.35} step={.01} unit=" mm" onChange={value => set("piece_clearance_mm", value)}/>
        <p className="quality-note puzzle-note">{params.color_layout === "layered"
          ? "Kolor dominujący tworzy pełny podkład. Każdy następny kolor zajmuje osobny poziom, więc występuje tylko jedna zmiana filamentu na wysokość."
          : "Kolor dominujący tworzy pełny podkład, a wszystkie kolory obrazu są obok siebie w jednym płaskim pasie. Ten tryb wymaga AMS lub innego systemu wielomateriałowego."}</p>
      </div>
      <div className="sidebar-foot">Osobne obiekty · paleta 3–12 filamentów · bez zapisu zdjęcia</div>
    </aside>

    <section className="workbench puzzle-workbench">
      <article className="preview puzzle-preview">
        <div className="preview-head"><div><p className="eyebrow">PODGLĄD PUZZLI</p><h2>Zdjęcie podzielone na {params.piece_count} elementów</h2></div><span className="puzzle-badge">{params.color_count} filamenty · {previewStyle} · {params.color_layout === "layered" ? "warstwowo" : "AMS"} · {grid} × {grid}</span></div>
        <div className="puzzle-stage" style={{aspectRatio: `${params.width_mm} / ${params.height_mm}`}}>
          {file ? <img src={previewUrl || sourceUrl} alt="Podgląd puzzli"/> : <button type="button" className="puzzle-empty" onClick={() => input.current?.click()}><span>＋</span><b>Dodaj fotografię</b><small>Kliknij tutaj, aby rozpocząć</small></button>}
          {previewBusy && <div className="puzzle-loading">Przeliczanie kolorów i kształtów…</div>}
        </div>
        <div className="stats puzzle-stats">
          <span><small>OBRAZ</small><b>{params.width_mm} × {params.height_mm} mm</b></span>
          <span><small>ELEMENT</small><b>{pieceWidth.toFixed(1)} × {pieceHeight.toFixed(1)} mm</b></span>
          <span><small>PUZZLE 3MF</small><b>{printWidth.toFixed(1)} × {printHeight.toFixed(1)} × {puzzleTotalThickness(params).toFixed(2)} mm</b></span>
          <span><small>RAMKA</small><b>{frame.width} × {frame.height} mm</b></span>
        </div>
        <div className="puzzle-frame-note"><b>Jedna ramka, dwa zastosowania</b><span>Składana nóżka na śrubę M3×30 oraz dwa otwory do zawieszenia są w tym samym zestawie.</span></div>
        {(error || validatePuzzle(params)) && <p className="error">{error || validatePuzzle(params)}</p>}
        <div className="puzzle-downloads">
          <button className="generate" disabled={puzzleBusy || frameBusy || !file || Boolean(validatePuzzle(params))} onClick={generatePuzzle}>{puzzleBusy ? "Generowanie 3MF…" : "Generuj puzzle 3MF"}<span>→</span></button>
          <button className="generate secondary" disabled={puzzleBusy || frameBusy || Boolean(validatePuzzle(params))} onClick={generateFrame}>{frameBusy ? "Generowanie ramki…" : "Generuj ramkę i stojak ZIP"}<span>→</span></button>
        </div>
      </article>
      <footer>Zdjęcie jest przetwarzane w pamięci i nie jest przechowywane na serwerze.</footer>
    </section>
  </main>;
}
