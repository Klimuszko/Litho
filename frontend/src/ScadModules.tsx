import {FormEvent, useCallback, useEffect, useMemo, useRef, useState} from "react";
import {MODULES_HOME_EVENT, useAuth} from "./Auth";
import ScadPreview from "./ScadPreview";
import "./scad.css";

type Parameter = {name: string; label: string; description: string; section: string; type: "integer"|"float"|"boolean"|"string"|"enum"; defaultValue: unknown; min?: number; max?: number; step?: number; options: (string|number|boolean)[]; optionLabels?: string[]; hidden: boolean; advanced: boolean; unit: string};
type Version = {id: string; version_number: number; version_label: string; changelog: string; created_at: string; parameters: Parameter[]; parser_warnings: string[]; source_hash: string; entry_file: string};
type Permissions = Record<"read"|"use"|"execute"|"update"|"publish"|"delete"|"restore"|"duplicate"|"moderate"|"permanent_delete", boolean>;
type ScadModule = {id: string; name: string; slug: string; description: string; category: string; owner_user_id: number; owner_username: string; owner_display_name: string; visibility: string; status: string; official: boolean; revision: number; working_version_id: string; published_version_id: string|null; active_version_id: string; active_version: Version; updated_at: string; preview_url?: string|null; permissions: Permissions};
type RenderJob = {id: string; status: "queued"|"running"|"completed"|"failed"|"cancelled"|"timed_out"; output_format: "stl"|"3mf"; duration_seconds?: number; metadata?: {messages?: {level: string; message: string; key?: string; value?: string}[]}; error_message?: string; stdout?: string; stderr?: string; command?: string[]; cached?: boolean};
type Preset = {id: string; name: string; parameters: Record<string, unknown>};
type LocalOutput = {url: string; format: "stl"|"3mf"; name: string};
type ModuleSession = {userId: number; activeVersionId: string; values: Record<string, unknown>; job: RenderJob|null; localOutput: LocalOutput|null};

const moduleSessions = new Map<string, ModuleSession>();

function discardModuleSession(moduleId: string) {
  const session = moduleSessions.get(moduleId);
  if (session?.localOutput) URL.revokeObjectURL(session.localOutput.url);
  moduleSessions.delete(moduleId);
}

const STATUS_LABELS: Record<string, string> = {
  draft: "Szkic",
  published: "Opublikowany",
  hidden: "Ukryty",
  blocked: "Zablokowany",
  deleted: "Usunięty",
};

const DEFAULT_SOURCE = `/* [Main] */
width = 50; // [10:1:100] @unit:mm
height = 20; // [5:1:50] @unit:mm
rounded = true;

if (rounded) {
  minkowski() {
    cube([width - 4, height - 4, 2]);
    cylinder(r = 2, h = 1, $fn = 32);
  }
} else {
  cube([width, height, 3]);
}
`;

function parseLocalMetadata(stdout = "", stderr = "") {
  const messages: {level: string; message: string; key?: string; value?: string}[] = [];
  for (const line of `${stdout}\n${stderr}`.split("\n")) {
    const match = line.match(/(?:ECHO:\s*)?["']?(INFO|WARNING|ERROR|DEBUG):\s*([^"']*)/i);
    if (!match) continue;
    const message = match[2].trim(); const separator = message.indexOf("=");
    messages.push({level: match[1].toUpperCase(), message, ...(separator >= 0 ? {key: message.slice(0, separator).trim(), value: message.slice(separator + 1).trim()} : {})});
  }
  return messages;
}

async function errorMessage(response: Response) {
  const body = await response.json().catch(() => ({}));
  return body.detail?.message || body.message || `Błąd HTTP ${response.status}`;
}

function ModuleCard({item, onOpen}: {item: ScadModule; onOpen: () => void}) {
  return <article className="module-card" onClick={onOpen}>
    <div className="module-thumb">{item.preview_url?<img src={item.preview_url} alt=""/>:<span>{item.name.slice(0, 1).toUpperCase()}</span>}<div className="card-badges">{item.official && <b>Oficjalny</b>}<b className={`status-${item.status}`}>{STATUS_LABELS[item.status] || item.status}</b></div></div>
    <div className="module-card-body"><small>{item.category}</small><h3>{item.name}</h3><p>{item.description || "Generator parametryczny OpenSCAD"}</p>
      <footer><span>przez {item.owner_display_name || item.owner_username}</span><span>v{item.active_version?.version_number || "—"}</span></footer>
    </div>
  </article>;
}

function ParameterControl({parameter, value, onChange}: {parameter: Parameter; value: unknown; onChange: (value: unknown) => void}) {
  if (parameter.type === "boolean") return <label className="scad-toggle"><span><b>{parameter.label}</b>{parameter.description && <small>{parameter.description}</small>}</span><input type="checkbox" checked={Boolean(value)} onChange={e => onChange(e.target.checked)}/></label>;
  if (parameter.options.length) return <label className="scad-field"><span>{parameter.label}</span><select value={String(value)} onChange={e => {const selected=parameter.options.find(option=>String(option)===e.target.value);onChange(selected)}}>{parameter.options.map((option,index) => <option value={String(option)} key={String(option)}>{parameter.optionLabels?.[index] || String(option)}</option>)}</select>{parameter.description && <small>{parameter.description}</small>}</label>;
  if (parameter.type === "string") return <label className="scad-field"><span>{parameter.label}</span><input value={String(value ?? "")} onChange={e => onChange(e.target.value)}/>{parameter.description && <small>{parameter.description}</small>}</label>;
  const number = Number(value);
  return <div className="scad-number"><div><b>{parameter.label}</b><output>{number}{parameter.unit && ` ${parameter.unit}`}</output></div>
    {parameter.min != null && parameter.max != null && <input type="range" min={parameter.min} max={parameter.max} step={parameter.step || (parameter.type === "integer" ? 1 : .1)} value={number} onChange={e => onChange(parameter.type === "integer" ? Number.parseInt(e.target.value) : Number(e.target.value))}/>} 
    <label><input type="number" min={parameter.min} max={parameter.max} step={parameter.step || (parameter.type === "integer" ? 1 : "any")} value={number} onChange={e => onChange(parameter.type === "integer" ? Number.parseInt(e.target.value) : Number(e.target.value))}/><span>{parameter.unit}</span></label>
    {parameter.description && <small>{parameter.description}</small>}
  </div>;
}

function CreateModule({onDone, onClose, categories}: {onDone: (module: ScadModule) => void; onClose: () => void; categories: string[]}) {
  const {apiFetch} = useAuth(); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [mode,setMode]=useState<"code"|"file">("code"); const [source,setSource]=useState(DEFAULT_SOURCE);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const response = mode === "code"
      ? await apiFetch("/api/scad/modules/code", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:data.get("name"),description:data.get("description"),category:data.get("category"),source})})
      : await apiFetch("/api/scad/modules", {method: "POST", body: data});
    if (!response.ok) setError(await errorMessage(response)); else onDone(await response.json()); setBusy(false);
  };
  return <div className="scad-modal" onMouseDown={e => e.target === e.currentTarget && onClose()}><form onSubmit={submit} className="scad-dialog">
    <header><div><small>NOWY GENERATOR</small><h2>Utwórz moduł SCAD</h2></div><button type="button" onClick={onClose}>×</button></header>
    <label>Nazwa<input name="name" required maxLength={120}/></label><label>Opis<textarea name="description" rows={3}/></label>
    <label>Kategoria<select name="category">{categories.map(item=><option key={item}>{item}</option>)}</select></label>
    <div className="source-mode"><button type="button" className={mode==="code"?"active":""} onClick={()=>setMode("code")}>Napisz kod</button><button type="button" className={mode==="file"?"active":""} onClick={()=>setMode("file")}>Wgraj plik</button></div>
    {mode==="code"?<label>Kod OpenSCAD<textarea className="source-editor small" value={source} onChange={e=>setSource(e.target.value)} spellCheck={false}/></label>:<label>Źródła<input name="source" type="file" accept=".scad,.zip" required/><small>Jeden .scad albo ZIP z bibliotekami i assets.</small></label>}
    {error && <p className="error">{error}</p>}<button className="scad-primary" disabled={busy}>{busy ? "Tworzenie…" : "Utwórz draft"}</button>
  </form></div>;
}

function ModuleEditor({moduleId, onBack, onOpen}: {moduleId: string; onBack: () => void; onOpen: (id: string) => void}) {
  const {apiFetch, user} = useAuth();
  const initialSession = moduleSessions.get(moduleId);
  const [module, setModule] = useState<ScadModule|null>(null); const [values, setValues] = useState<Record<string, unknown>>(() => initialSession?.userId === user.id ? initialSession.values : {});
  const [job, setJob] = useState<RenderJob|null>(() => initialSession?.userId === user.id ? initialSession.job : null); const [error, setError] = useState(""); const [technical, setTechnical] = useState(false);
  const [presets, setPresets] = useState<Preset[]>([]); const [selectedPreset,setSelectedPreset]=useState(""); const [versions, setVersions] = useState<Version[]>([]); const [showVersions, setShowVersions] = useState(false);
  const [developer, setDeveloper] = useState(false); const [audit, setAudit] = useState<{id:string;action:string;timestamp:string;actor_username:string}[]>([]); const [showAudit,setShowAudit]=useState(false);
  const [localOutput, setLocalOutput] = useState<LocalOutput|null>(() => initialSession?.userId === user.id ? initialSession.localOutput : null);
  const [codeEditor,setCodeEditor]=useState<{source:string;versionId:string}|null>(null); const [codeBusy,setCodeBusy]=useState(false);
  const wasmWorker = useRef<Worker|null>(null);
  const load = useCallback(async () => {
    const response = await apiFetch(`/api/scad/modules/${moduleId}`); if (!response.ok) throw new Error(await errorMessage(response));
    const data: ScadModule = await response.json(); setModule(data);
    const cached = moduleSessions.get(moduleId);
    if (cached?.userId === user.id && cached.activeVersionId === data.active_version_id) {
      setValues(cached.values); setJob(cached.job); setLocalOutput(cached.localOutput);
    } else {
      if (cached) discardModuleSession(moduleId);
      setValues(Object.fromEntries((data.active_version?.parameters || []).map(item => [item.name, item.defaultValue])));
      setJob(null); setLocalOutput(null);
    }
    const [presetResponse, versionResponse] = await Promise.all([apiFetch(`/api/scad/modules/${moduleId}/presets`), apiFetch(`/api/scad/modules/${moduleId}/versions`)]);
    if (presetResponse.ok) setPresets((await presetResponse.json()).presets); if (versionResponse.ok) setVersions((await versionResponse.json()).versions);
  }, [apiFetch, moduleId, user.id]);
  useEffect(() => { load().catch(reason => setError(String(reason))); return () => wasmWorker.current?.terminate(); }, [load]);
  useEffect(() => {
    if (!module) return;
    moduleSessions.set(moduleId, {userId: user.id, activeVersionId: module.active_version_id, values, job, localOutput});
  }, [job, localOutput, module, moduleId, user.id, values]);

  const generate = async (format: "stl"|"3mf" = "stl") => {
    if (!module) return;
    setError(""); setTechnical(false); setLocalOutput(current => {if(current) URL.revokeObjectURL(current.url); return null;});
    setJob({id: `wasm-${Date.now()}`, status: "running", output_format: format, stdout: "Pobieranie źródeł modułu…", metadata: {messages: []}});
    const source = await apiFetch(`/api/scad/modules/${moduleId}/source?version_id=${encodeURIComponent(module.active_version_id)}`);
    if (!source.ok) {setError(await errorMessage(source)); setJob(null); return;}
    const archive = await source.arrayBuffer();
    const worker = new Worker(new URL("./scadWasm.worker.ts", import.meta.url), {type: "module"});
    wasmWorker.current?.terminate(); wasmWorker.current = worker;
    worker.onmessage = event => {
      const result = event.data;
      if (result.type === "progress") {
        setJob(current => current ? {...current, status: "running", stdout: result.stage === "engine" ? "Ładowanie silnika WebAssembly…" : "Generowanie modelu na tym komputerze…"} : current);
        return;
      }
      worker.terminate(); wasmWorker.current = null;
      if (result.type === "complete") {
        const blob = new Blob([result.output], {type: format === "stl" ? "model/stl" : "model/3mf"});
        const url = URL.createObjectURL(blob);
        setLocalOutput({url, format, name: `${module.slug}.${format}`});
        setJob({id: `wasm-${Date.now()}`, status: "completed", output_format: format, duration_seconds: result.durationSeconds, stdout: result.stdout, stderr: result.stderr, command: result.command, metadata: {messages: parseLocalMetadata(result.stdout, result.stderr)}});
      } else {
        setJob({id: `wasm-${Date.now()}`, status: "failed", output_format: format, duration_seconds: result.durationSeconds, stdout: result.stdout, stderr: result.stderr, error_message: result.message});
      }
    };
    worker.onerror = event => {
      worker.terminate(); wasmWorker.current = null;
      setJob({id: `wasm-${Date.now()}`, status: "failed", output_format: format, error_message: event.message || "Nie udało się uruchomić OpenSCAD WebAssembly."});
    };
    worker.postMessage({archive, entryFile: module.active_version.entry_file, outputFormat: format, parameters: module.active_version.parameters, values}, [archive]);
  };
  const cancelRender = () => {
    wasmWorker.current?.terminate(); wasmWorker.current = null;
    setJob(current => current ? {...current, status: "cancelled", error_message: "Render anulowany."} : current);
  };
  const action = async (path: string, body?: object, method = "POST") => {
    const response = await apiFetch(`/api/scad/modules/${moduleId}${path}`, {method, headers: body ? {"Content-Type": "application/json"} : undefined, body: body ? JSON.stringify(body) : undefined});
    if (!response.ok) {setError(await errorMessage(response)); return null;} const result = response.status === 204 ? null : await response.json(); await load(); return result;
  };
  const savePreset = async () => {
    const name = prompt("Nazwa presetu:"); if (!name) return;
    const response = await apiFetch(`/api/scad/modules/${moduleId}/presets`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name, parameters:values})});
    if (!response.ok) setError(await errorMessage(response)); else setPresets([...presets, await response.json()]);
  };
  const renamePreset = async () => {
    const preset=presets.find(item=>item.id===selectedPreset); if(!preset)return; const name=prompt("Nowa nazwa presetu:",preset.name); if(!name)return;
    const response=await apiFetch(`/api/scad/modules/${moduleId}/presets/${preset.id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,parameters:preset.parameters})});
    if(!response.ok)setError(await errorMessage(response));else setPresets(presets.map(item=>item.id===preset.id?{...item,name}:item));
  };
  const deletePreset = async () => {
    if(!selectedPreset||!confirm("Usunąć preset?"))return; const response=await apiFetch(`/api/scad/modules/${moduleId}/presets/${selectedPreset}`,{method:"DELETE"});
    if(!response.ok)setError(await errorMessage(response));else{setPresets(presets.filter(item=>item.id!==selectedPreset));setSelectedPreset("")}
  };
  const duplicate = async () => { const result = await action("/duplicate"); if (result) {location.hash = `module:${result.id}`; onOpen(result.id);} };
  const editMetadata = async () => {
    const name=prompt("Nazwa modułu:",module?.name); if(!name||!module)return;
    const description=prompt("Opis:",module.description); if(description===null)return;
    const category=prompt("Kategoria:",module.category); if(!category)return;
    await action("",{name,description,category,visibility:module.visibility,revision:module.revision},"PUT");
  };
  const openCodeEditor = async () => {
    setError("");
    const response=await apiFetch(`/api/scad/modules/${moduleId}/code`); if(!response.ok){setError(await errorMessage(response));return}
    const data=await response.json(); setCodeEditor({source:data.source,versionId:data.version_id});
  };
  const saveCode = async () => {
    if(!codeEditor)return; setCodeBusy(true); setError("");
    const response=await apiFetch(`/api/scad/modules/${moduleId}/code`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({source:codeEditor.source,version_label:"Edycja w przeglądarce",changelog:"Kod zmieniony w edytorze Litho"})});
    if(!response.ok)setError(await errorMessage(response));else{setCodeEditor(null);await load()} setCodeBusy(false);
  };
  const toggleAudit = async () => {
    if(!showAudit){const response=await apiFetch(`/api/scad/modules/${moduleId}/audit`);if(response.ok)setAudit((await response.json()).audit);else setError(await errorMessage(response));}
    setShowAudit(!showAudit);
  };
  const uploadPreview = async (file: File) => {
    const body=new FormData(); body.set("preview",file); const response=await apiFetch(`/api/scad/modules/${moduleId}/preview`,{method:"POST",body});
    if(!response.ok)setError(await errorMessage(response));else await load();
  };
  const permanentDelete = async () => {
    if(!confirm("Trwale usunąć moduł, wszystkie wersje, presety i cache? Tej operacji nie można cofnąć."))return;
    const response=await apiFetch(`/api/scad/modules/${moduleId}/permanent`,{method:"DELETE"}); if(!response.ok)setError(await errorMessage(response));else{discardModuleSession(moduleId);onBack();}
  };
  const publishModule = async () => {
    await action("/publish",{visibility:module?.official&&user.role==="admin"?"system":"public"});
  };
  if (!module) return <main className="module-loading"><button onClick={onBack}>← Biblioteka</button><p>{error || "Ładowanie modułu…"}</p></main>;
  const visibleParameters = module.active_version.parameters.filter(item => !item.hidden || developer);
  const grouped = Object.entries(visibleParameters.reduce<Record<string, Parameter[]>>((groups, item) => {
    const section = item.advanced ? "Zaawansowane" : item.section;
    (groups[section] ||= []).push(item);
    return groups;
  }, {}));
  const running = job && ["queued", "running"].includes(job.status);
  const previewUrl = job?.status === "completed" && job.output_format === "stl" ? localOutput?.url || null : null;
  const owner = module.owner_user_id === user.id;
  return <><main className="scad-editor-page">
    <header className="scad-editor-header"><button onClick={onBack}>← Moduły</button><div><span>{module.category}</span><h1>{module.name}</h1><p>Autor: {module.owner_display_name || module.owner_username} · v{module.active_version.version_number}</p></div>
      <div className="module-badges">{module.official && <b>Oficjalny</b>}<span className={`status-${module.status}`}>{STATUS_LABELS[module.status] || module.status}</span></div>
    </header>
    <div className="scad-editor-grid"><aside className="scad-customize"><header><div><small>DOSTOSUJ</small><h2>Parametry</h2></div>{(owner || user.role === "admin") && <label className="dev-toggle"><input type="checkbox" checked={developer} onChange={e=>setDeveloper(e.target.checked)}/> Tryb techniczny</label>}</header>
      {module.active_version.parser_warnings?.map(warning => <p className="scad-warning" key={warning}>{warning}</p>)}
      {grouped.map(([section, parameters]) => <details key={section} open={section !== "Zaawansowane"}><summary>{section}<span>{parameters.length}</span></summary><div>{parameters.map(parameter => <ParameterControl key={parameter.name} parameter={parameter} value={values[parameter.name]} onChange={value => setValues(current => ({...current, [parameter.name]: value}))}/>)}</div></details>)}
      <div className="preset-bar"><select value={selectedPreset} onChange={e => {setSelectedPreset(e.target.value);const preset=presets.find(item=>item.id===e.target.value); if(preset)setValues(preset.parameters)}}><option value="">Wczytaj preset…</option>{presets.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}</select><button onClick={savePreset}>Zapisz preset</button><button onClick={() => setValues(Object.fromEntries(module.active_version.parameters.map(item => [item.name,item.defaultValue])))}>Reset</button>{selectedPreset&&<><button onClick={renamePreset}>Zmień nazwę</button><button onClick={deletePreset}>Usuń preset</button></>}</div>
    </aside><section className="scad-stage"><ScadPreview url={previewUrl}/>
      {job?.metadata?.messages && job.metadata.messages.length > 0 && <div className="geometry-info"><b>Obliczona geometria</b>{job.metadata.messages.filter(item=>item.level!=="DEBUG").map((item,index)=><span className={item.level.toLowerCase()} key={index}>{item.key ? `${item.key.replaceAll("_"," ")}: ${item.value}` : item.message}</span>)}</div>}
      {(error || job && ["failed","timed_out","cancelled"].includes(job.status)) && <div className="render-error"><b>Model nie mógł zostać wygenerowany</b><span>{error || job?.error_message}</span>{job && <button onClick={()=>setTechnical(!technical)}>Pokaż szczegóły techniczne</button>}{technical && <pre>{JSON.stringify({command:job?.command,stdout:job?.stdout,stderr:job?.stderr,duration:job?.duration_seconds},null,2)}</pre>}</div>}
      <div className="scad-actions"><button className="scad-primary" disabled={Boolean(running)||!module.permissions.execute} onClick={()=>generate("stl")}>{!module.permissions.execute?"Generowanie zablokowane":running?"Generowanie na tym komputerze…":"Generuj podgląd STL"}</button>{running && <button onClick={cancelRender}>Anuluj</button>}{job?.status === "completed" && localOutput && <><a href={localOutput.url} download={localOutput.name}>Pobierz {job.output_format.toUpperCase()}</a><button onClick={()=>generate("3mf")}>Generuj 3MF</button></>}</div>
      <div className="module-owner-actions">
        {module.permissions.update&&<button className="scad-primary" onClick={openCodeEditor}>Edytuj kod</button>}
        {module.permissions.update&&<button onClick={editMetadata}>Edytuj dane</button>}
        {module.permissions.publish&&module.status!=="published"&&<button onClick={publishModule}>Opublikuj</button>}
        {module.permissions.publish&&module.status==="published"&&<button onClick={()=>action("/unpublish")}>Zmień na szkic</button>}
        {module.permissions.update&&<button onClick={()=>setShowVersions(!showVersions)}>Historia</button>}
        <details className="module-more"><summary>Więcej</summary><div><button onClick={duplicate}>Duplikuj do moich</button><a href={`/api/scad/modules/${moduleId}/source`}>Pobierz źródła</a>
          {module.permissions.update&&<label className="file-action">Ustaw miniaturę<input type="file" hidden accept="image/png,image/jpeg" onChange={e=>e.target.files?.[0]&&uploadPreview(e.target.files[0])}/></label>}
          {(owner||user.role==="admin")&&<button onClick={toggleAudit}>Audyt</button>}
          {module.permissions.moderate&&<><button onClick={()=>action("/moderate",{action:module.status==="hidden"?"unhide":"hide"})}>{module.status==="hidden"?"Pokaż":"Ukryj"}</button><button onClick={()=>action("/moderate",{action:module.status==="blocked"?"unblock":"block"})}>{module.status==="blocked"?"Odblokuj":"Zablokuj"}</button><button onClick={()=>action("/moderate",{action:module.official?"unofficial":"official"})}>{module.official?"Usuń oznaczenie oficjalne":"Oznacz jako oficjalny"}</button></>}
          {module.permissions.delete&&<button className="danger" onClick={()=>confirm("Usunąć moduł?")&&action("",undefined,"DELETE")}>Usuń</button>}{module.permissions.permanent_delete&&<button className="danger" onClick={permanentDelete}>Usuń trwale</button>}
        </div></details>
      </div>
      {showVersions && <div className="version-history"><h3>Historia wersji</h3>{versions.map(version=><article key={version.id}><div><b>v{version.version_number} · {version.version_label}</b><small>{new Date(version.created_at).toLocaleString()} · {version.source_hash.slice(0,10)}</small><p>{version.changelog}</p></div>{module.permissions.update&&version.id!==module.working_version_id&&<button onClick={()=>action(`/versions/${version.id}/restore`)}>Przywróć jako nową</button>}</article>)}</div>}
      {showAudit&&<div className="audit-log"><h3>Audit log</h3>{audit.map(item=><article key={item.id}><b>{item.action}</b><span>{item.actor_username} · {new Date(item.timestamp).toLocaleString()}</span></article>)}</div>}
      {developer && <div className="developer-panel"><b>Tryb techniczny</b><code>źródło {module.active_version.source_hash}</code><code>wersja {module.active_version.id}</code><code>generowanie {job?.id || "—"} {job?.cached ? "(pamięć podręczna)" : ""}</code></div>}
    </section></div>
  </main>{codeEditor&&<div className="code-modal"><section><header><div><small>EDYTOR OPENSCAD</small><h2>{module.name}</h2></div><button onClick={()=>setCodeEditor(null)}>×</button></header><textarea className="source-editor" value={codeEditor.source} onChange={e=>setCodeEditor({...codeEditor,source:e.target.value})} spellCheck={false}/><footer><span className={error?"error":""}>{error||"Zapis utworzy nową wersję roboczą."}</span><div><button onClick={()=>setCodeEditor(null)}>Anuluj</button><button className="scad-primary" disabled={codeBusy} onClick={saveCode}>{codeBusy?"Zapisywanie…":"Zapisz nową wersję"}</button></div></footer></section></div>}</>;
}

export default function ScadModules() {
  const {apiFetch,user} = useAuth(); const [scope,setScope]=useState("all"); const [modules,setModules]=useState<ScadModule[]>([]); const [selected,setSelected]=useState<string|null>(()=>location.hash.startsWith("#module:")?location.hash.slice(8):null);
  const [search,setSearch]=useState(""); const [status,setStatus]=useState(""); const [sort,setSort]=useState("updated"); const [categories,setCategories]=useState<string[]>(["Other"]); const [error,setError]=useState(""); const [importing,setImporting]=useState(false);
  const load=useCallback(async()=>{const query=new URLSearchParams({scope,search,status,sort}); const response=await apiFetch(`/api/scad/modules?${query}`); if(!response.ok)throw new Error(await errorMessage(response)); setModules((await response.json()).modules)},[apiFetch,scope,search,status,sort]);
  useEffect(()=>{if(!selected)load().catch(reason=>setError(String(reason)))},[load,selected]);
  useEffect(()=>{apiFetch("/api/scad/categories").then(async response=>{if(response.ok)setCategories((await response.json()).categories)})},[apiFetch]);
  useEffect(() => {
    for (const [moduleId, session] of moduleSessions) if (session.userId !== user.id) discardModuleSession(moduleId);
  }, [user.id]);
  useEffect(() => {
    const showHome = () => {setSelected(null); setImporting(false); setError("");};
    const syncHash = () => setSelected(location.hash.startsWith("#module:") ? location.hash.slice(8) : null);
    window.addEventListener(MODULES_HOME_EVENT, showHome);
    window.addEventListener("hashchange", syncHash);
    return () => {window.removeEventListener(MODULES_HOME_EVENT, showHome); window.removeEventListener("hashchange", syncHash);};
  }, []);
  const open=(id:string)=>{location.hash=`module:${id}`;setSelected(id)}; const back=()=>{history.replaceState(null,"",`${location.pathname}${location.search}`);setSelected(null);load()};
  if(selected)return <ModuleEditor moduleId={selected} onBack={back} onOpen={setSelected}/>;
  return <main className="modules-page"><header className="modules-hero"><div><p className="eyebrow">OPENSCAD W PRZEGLĄDARCE</p><h1>Moduły</h1><p>Twórz, edytuj i generuj modele bez obciążania serwera.</p></div><button className="scad-primary" onClick={()=>setImporting(true)}>＋ Nowy moduł</button></header>
    <nav className="module-tabs"><button className={scope==="my"?"active":""} onClick={()=>setScope("my")}>Moje moduły</button><button className={scope==="all"?"active":""} onClick={()=>setScope("all")}>Wszystkie moduły</button></nav>
    <div className="module-filters"><input type="search" placeholder="Szukaj nazwy, opisu lub autora…" value={search} onChange={e=>setSearch(e.target.value)}/><select value={status} onChange={e=>setStatus(e.target.value)}><option value="">Wszystkie statusy</option><option value="draft">Tylko szkice</option><option value="published">Tylko opublikowane</option><option value="blocked">Zablokowane</option></select><select value={sort} onChange={e=>setSort(e.target.value)}><option value="updated">Ostatnio aktualizowane</option><option value="newest">Najnowsze</option><option value="name">Nazwa A–Z</option></select></div>
    {error&&<p className="error">{error}</p>}<section className="module-grid">{modules.map(item=><ModuleCard item={item} key={item.id} onOpen={()=>open(item.id)}/>)}</section>{!modules.length&&!error&&<div className="module-empty"><b>Brak modułów</b><span>Utwórz pierwszy moduł albo zmień filtr.</span></div>}
    {importing&&<CreateModule categories={categories} onClose={()=>setImporting(false)} onDone={item=>{setImporting(false);open(item.id)}}/>}
  </main>;
}
