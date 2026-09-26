import {FormEvent, useCallback, useEffect, useMemo, useRef, useState} from "react";
import {useAuth} from "./Auth";
import ScadPreview from "./ScadPreview";
import "./scad.css";

type Parameter = {name: string; label: string; description: string; section: string; type: "integer"|"float"|"boolean"|"string"|"enum"; defaultValue: unknown; min?: number; max?: number; step?: number; options: string[]; hidden: boolean; advanced: boolean; unit: string};
type Version = {id: string; version_number: number; version_label: string; changelog: string; created_at: string; parameters: Parameter[]; parser_warnings: string[]; source_hash: string};
type Permissions = Record<"read"|"use"|"execute"|"update"|"publish"|"delete"|"restore"|"duplicate"|"moderate"|"permanent_delete", boolean>;
type ScadModule = {id: string; name: string; slug: string; description: string; category: string; owner_user_id: number; owner_username: string; owner_display_name: string; visibility: string; status: string; official: boolean; revision: number; working_version_id: string; published_version_id: string|null; active_version_id: string; active_version: Version; updated_at: string; preview_url?: string|null; permissions: Permissions};
type RenderJob = {id: string; status: "queued"|"running"|"completed"|"failed"|"cancelled"|"timed_out"; output_format: "stl"|"3mf"; duration_seconds?: number; metadata?: {messages?: {level: string; message: string; key?: string; value?: string}[]}; error_message?: string; stdout?: string; stderr?: string; command?: string[]; cached?: boolean};
type Preset = {id: string; name: string; parameters: Record<string, unknown>};

async function errorMessage(response: Response) {
  const body = await response.json().catch(() => ({}));
  return body.detail?.message || body.message || `Błąd HTTP ${response.status}`;
}

function ModuleCard({item, onOpen}: {item: ScadModule; onOpen: () => void}) {
  return <article className="module-card" onClick={onOpen}>
    <div className="module-thumb">{item.preview_url?<img src={item.preview_url} alt=""/>:<span>{item.name.slice(0, 1).toUpperCase()}</span>}{item.official && <b>Official</b>}</div>
    <div className="module-card-body"><small>{item.category}</small><h3>{item.name}</h3><p>{item.description || "Generator parametryczny OpenSCAD"}</p>
      <footer><span>przez {item.owner_display_name || item.owner_username}</span><span>v{item.active_version?.version_number || "—"}</span></footer>
    </div>
  </article>;
}

function ParameterControl({parameter, value, onChange}: {parameter: Parameter; value: unknown; onChange: (value: unknown) => void}) {
  if (parameter.type === "boolean") return <label className="scad-toggle"><span><b>{parameter.label}</b>{parameter.description && <small>{parameter.description}</small>}</span><input type="checkbox" checked={Boolean(value)} onChange={e => onChange(e.target.checked)}/></label>;
  if (parameter.type === "enum") return <label className="scad-field"><span>{parameter.label}</span><select value={String(value)} onChange={e => onChange(e.target.value)}>{parameter.options.map(option => <option key={option}>{option}</option>)}</select>{parameter.description && <small>{parameter.description}</small>}</label>;
  if (parameter.type === "string") return <label className="scad-field"><span>{parameter.label}</span><input value={String(value ?? "")} onChange={e => onChange(e.target.value)}/>{parameter.description && <small>{parameter.description}</small>}</label>;
  const number = Number(value);
  return <div className="scad-number"><div><b>{parameter.label}</b><output>{number}{parameter.unit && ` ${parameter.unit}`}</output></div>
    {parameter.min != null && parameter.max != null && <input type="range" min={parameter.min} max={parameter.max} step={parameter.step || (parameter.type === "integer" ? 1 : .1)} value={number} onChange={e => onChange(parameter.type === "integer" ? Number.parseInt(e.target.value) : Number(e.target.value))}/>} 
    <label><input type="number" min={parameter.min} max={parameter.max} step={parameter.step || (parameter.type === "integer" ? 1 : "any")} value={number} onChange={e => onChange(parameter.type === "integer" ? Number.parseInt(e.target.value) : Number(e.target.value))}/><span>{parameter.unit}</span></label>
    {parameter.description && <small>{parameter.description}</small>}
  </div>;
}

function ImportModule({onDone, onClose, categories}: {onDone: (module: ScadModule) => void; onClose: () => void; categories: string[]}) {
  const {apiFetch} = useAuth(); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const response = await apiFetch("/api/scad/modules", {method: "POST", body: data});
    if (!response.ok) setError(await errorMessage(response)); else onDone(await response.json()); setBusy(false);
  };
  return <div className="scad-modal" onMouseDown={e => e.target === e.currentTarget && onClose()}><form onSubmit={submit} className="scad-dialog">
    <header><div><small>NOWY GENERATOR</small><h2>Dodaj moduł SCAD</h2></div><button type="button" onClick={onClose}>×</button></header>
    <label>Nazwa<input name="name" required maxLength={120}/></label><label>Opis<textarea name="description" rows={3}/></label>
    <label>Kategoria<select name="category">{categories.map(item=><option key={item}>{item}</option>)}</select></label>
    <label>Widoczność<select name="visibility"><option value="private">Prywatny</option><option value="unlisted">Niepubliczny link</option></select></label>
    <label>Źródła<input name="source" type="file" accept=".scad,.zip" required/><small>Jeden .scad albo ZIP z module.json, bibliotekami i assets.</small></label>
    {error && <p className="error">{error}</p>}<button className="scad-primary" disabled={busy}>{busy ? "Importowanie…" : "Utwórz prywatny draft"}</button>
  </form></div>;
}

function ModuleEditor({moduleId, onBack, onOpen}: {moduleId: string; onBack: () => void; onOpen: (id: string) => void}) {
  const {apiFetch, user} = useAuth();
  const [module, setModule] = useState<ScadModule|null>(null); const [values, setValues] = useState<Record<string, unknown>>({});
  const [job, setJob] = useState<RenderJob|null>(null); const [error, setError] = useState(""); const [technical, setTechnical] = useState(false);
  const [presets, setPresets] = useState<Preset[]>([]); const [selectedPreset,setSelectedPreset]=useState(""); const [versions, setVersions] = useState<Version[]>([]); const [showVersions, setShowVersions] = useState(false);
  const [developer, setDeveloper] = useState(false); const [audit, setAudit] = useState<{id:string;action:string;timestamp:string;actor_username:string}[]>([]); const [showAudit,setShowAudit]=useState(false); const poll = useRef<number|undefined>(undefined);
  const load = useCallback(async () => {
    const response = await apiFetch(`/api/scad/modules/${moduleId}`); if (!response.ok) throw new Error(await errorMessage(response));
    const data: ScadModule = await response.json(); setModule(data);
    setValues(Object.fromEntries((data.active_version?.parameters || []).map(item => [item.name, item.defaultValue])));
    const [presetResponse, versionResponse] = await Promise.all([apiFetch(`/api/scad/modules/${moduleId}/presets`), apiFetch(`/api/scad/modules/${moduleId}/versions`)]);
    if (presetResponse.ok) setPresets((await presetResponse.json()).presets); if (versionResponse.ok) setVersions((await versionResponse.json()).versions);
  }, [apiFetch, moduleId]);
  useEffect(() => { load().catch(reason => setError(String(reason))); return () => window.clearTimeout(poll.current); }, [load]);

  const watch = useCallback(async (id: string) => {
    const response = await apiFetch(`/api/scad/renders/${id}`); if (!response.ok) {setError(await errorMessage(response)); return;}
    const next: RenderJob = await response.json(); setJob(next);
    if (["queued", "running"].includes(next.status)) poll.current = window.setTimeout(() => watch(id), 700);
  }, [apiFetch]);
  const generate = async (format: "stl"|"3mf" = "stl") => {
    setError(""); setTechnical(false); setJob(null);
    const response = await apiFetch(`/api/scad/modules/${moduleId}/renders`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({parameters: values, output_format: format})});
    if (!response.ok) {setError(await errorMessage(response)); return;} const created = await response.json(); setJob(created); watch(created.id);
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
  const uploadVersion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const response=await apiFetch(`/api/scad/modules/${moduleId}/versions`,{method:"POST",body:new FormData(event.currentTarget)});
    if(!response.ok){setError(await errorMessage(response));return} event.currentTarget.reset(); await load();
  };
  const toggleAudit = async () => {
    if(!showAudit){const response=await apiFetch(`/api/scad/modules/${moduleId}/audit`);if(response.ok)setAudit((await response.json()).audit);else setError(await errorMessage(response));}
    setShowAudit(!showAudit);
  };
  const shareModule = async () => {
    const username=prompt("Login użytkownika:"); if(!username)return; const body=new FormData(); body.set("username",username);
    const response=await apiFetch(`/api/scad/modules/${moduleId}/shares`,{method:"POST",body}); if(!response.ok)setError(await errorMessage(response));
  };
  const uploadPreview = async (file: File) => {
    const body=new FormData(); body.set("preview",file); const response=await apiFetch(`/api/scad/modules/${moduleId}/preview`,{method:"POST",body});
    if(!response.ok)setError(await errorMessage(response));else await load();
  };
  const permanentDelete = async () => {
    if(!confirm("Trwale usunąć moduł, wszystkie wersje, presety i cache? Tej operacji nie można cofnąć."))return;
    const response=await apiFetch(`/api/scad/modules/${moduleId}/permanent`,{method:"DELETE"}); if(!response.ok)setError(await errorMessage(response));else onBack();
  };
  const publishModule = async () => {
    const allowed=user.role==="admin"?"public / unlisted / system":"public / unlisted";
    const visibility=prompt(`Widoczność publikacji (${allowed}):`,module?.visibility==="unlisted"?"unlisted":"public");
    if(!visibility||!(user.role==="admin"?["public","unlisted","system"]:["public","unlisted"]).includes(visibility))return;
    await action("/publish",{visibility});
  };
  if (!module) return <main className="module-loading"><button onClick={onBack}>← Biblioteka</button><p>{error || "Ładowanie modułu…"}</p></main>;
  const visibleParameters = module.active_version.parameters.filter(item => !item.hidden || developer);
  const grouped = Object.entries(visibleParameters.reduce<Record<string, Parameter[]>>((groups, item) => {
    const section = item.advanced ? "Advanced" : item.section;
    (groups[section] ||= []).push(item);
    return groups;
  }, {}));
  const running = job && ["queued", "running"].includes(job.status);
  const previewUrl = job?.status === "completed" && job.output_format === "stl" ? `/api/scad/renders/${job.id}/download` : null;
  const owner = module.owner_user_id === user.id;
  return <main className="scad-editor-page">
    <header className="scad-editor-header"><button onClick={onBack}>← Moduły</button><div><span>{module.category}</span><h1>{module.name}</h1><p>Created by: {module.owner_display_name || module.owner_username} · v{module.active_version.version_number}</p></div>
      <div className="module-badges">{module.official && <b>Official</b>}<span>{module.visibility}</span><span>{module.status}</span></div>
    </header>
    <div className="scad-editor-grid"><aside className="scad-customize"><header><div><small>CUSTOMIZE</small><h2>Parametry</h2></div>{(owner || user.role === "admin") && <label className="dev-toggle"><input type="checkbox" checked={developer} onChange={e=>setDeveloper(e.target.checked)}/> Developer</label>}</header>
      {module.active_version.parser_warnings?.map(warning => <p className="scad-warning" key={warning}>{warning}</p>)}
      {grouped.map(([section, parameters]) => <details key={section} open={section !== "Advanced"}><summary>{section}<span>{parameters.length}</span></summary><div>{parameters.map(parameter => <ParameterControl key={parameter.name} parameter={parameter} value={values[parameter.name]} onChange={value => setValues(current => ({...current, [parameter.name]: value}))}/>)}</div></details>)}
      <div className="preset-bar"><select value={selectedPreset} onChange={e => {setSelectedPreset(e.target.value);const preset=presets.find(item=>item.id===e.target.value); if(preset)setValues(preset.parameters)}}><option value="">Wczytaj preset…</option>{presets.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}</select><button onClick={savePreset}>Zapisz preset</button><button onClick={() => setValues(Object.fromEntries(module.active_version.parameters.map(item => [item.name,item.defaultValue])))}>Reset</button>{selectedPreset&&<><button onClick={renamePreset}>Zmień nazwę</button><button onClick={deletePreset}>Usuń preset</button></>}</div>
    </aside><section className="scad-stage"><ScadPreview url={previewUrl}/>
      {job?.metadata?.messages && job.metadata.messages.length > 0 && <div className="geometry-info"><b>Obliczona geometria</b>{job.metadata.messages.filter(item=>item.level!=="DEBUG").map((item,index)=><span className={item.level.toLowerCase()} key={index}>{item.key ? `${item.key.replaceAll("_"," ")}: ${item.value}` : item.message}</span>)}</div>}
      {(error || job && ["failed","timed_out","cancelled"].includes(job.status)) && <div className="render-error"><b>Model nie mógł zostać wygenerowany</b><span>{error || job?.error_message}</span>{job && <button onClick={()=>setTechnical(!technical)}>Pokaż szczegóły techniczne</button>}{technical && <pre>{JSON.stringify({command:job?.command,stdout:job?.stdout,stderr:job?.stderr,duration:job?.duration_seconds},null,2)}</pre>}</div>}
      <div className="scad-actions"><button className="scad-primary" disabled={Boolean(running)} onClick={()=>generate("stl")}>{running ? "Generowanie…" : "Generuj podgląd STL"}</button>{running && <button onClick={()=>apiFetch(`/api/scad/renders/${job!.id}`,{method:"DELETE"})}>Anuluj</button>}{job?.status === "completed" && <><a href={`/api/scad/renders/${job.id}/download`} download>Pobierz {job.output_format.toUpperCase()}</a><button onClick={()=>generate("3mf")}>Generuj 3MF</button></>}</div>
      <div className="module-owner-actions"><button onClick={savePreset}>Zapisz preset</button><button onClick={duplicate}>Duplikuj do moich</button><a href={`/api/scad/modules/${moduleId}/source`}>Pobierz źródła</a>
        {module.permissions.update && <button onClick={editMetadata}>Edytuj dane</button>}
        {module.permissions.update && <button onClick={shareModule}>Udostępnij</button>}
        {module.permissions.update && <label className="file-action">Ustaw miniaturę<input type="file" hidden accept="image/png,image/jpeg" onChange={e=>e.target.files?.[0]&&uploadPreview(e.target.files[0])}/></label>}
        {module.permissions.publish && module.status !== "published" && <button onClick={publishModule}>Opublikuj wersję</button>}{module.permissions.publish && module.status === "published" && <button onClick={()=>action("/unpublish")}>Wycofaj publikację</button>}
        {module.permissions.update && <button onClick={()=>setShowVersions(!showVersions)}>Historia wersji</button>}{module.permissions.delete && <button className="danger" onClick={()=>confirm("Usunąć moduł?")&&action("",undefined,"DELETE")}>Usuń</button>}{module.permissions.restore&&<button onClick={()=>action("/restore")}>Przywróć</button>}
        {(owner||user.role==="admin")&&<button onClick={toggleAudit}>Audyt</button>}
        {module.permissions.moderate && <><button onClick={()=>action("/moderate",{action:module.status==="hidden"?"unhide":"hide"})}>{module.status==="hidden"?"Pokaż":"Ukryj"}</button><button onClick={()=>action("/moderate",{action:module.status==="blocked"?"unblock":"block"})}>{module.status==="blocked"?"Odblokuj":"Zablokuj"}</button><button onClick={()=>action("/moderate",{action:module.official?"unofficial":"official"})}>{module.official?"Usuń Official":"Oznacz Official"}</button></>}
        {module.permissions.permanent_delete&&<button className="danger" onClick={permanentDelete}>Usuń trwale</button>}
      </div>
      {showVersions && <div className="version-history"><h3>Historia wersji</h3>{module.permissions.update&&<form className="version-upload" onSubmit={uploadVersion}><input name="source" type="file" accept=".scad,.zip" required/><input name="version_label" placeholder="Etykieta wersji"/><input name="changelog" placeholder="Opis zmian"/><button>Zapisz nową wersję roboczą</button></form>}{versions.map(version=><article key={version.id}><div><b>v{version.version_number} · {version.version_label}</b><small>{new Date(version.created_at).toLocaleString()} · {version.source_hash.slice(0,10)}</small><p>{version.changelog}</p></div>{module.permissions.update&&<button onClick={()=>action(`/versions/${version.id}/restore`)}>{version.id===module.working_version_id?"Reload SCAD":"Przywróć jako nową"}</button>}</article>)}</div>}
      {showAudit&&<div className="audit-log"><h3>Audit log</h3>{audit.map(item=><article key={item.id}><b>{item.action}</b><span>{item.actor_username} · {new Date(item.timestamp).toLocaleString()}</span></article>)}</div>}
      {developer && <div className="developer-panel"><b>Developer mode</b><code>source {module.active_version.source_hash}</code><code>version {module.active_version.id}</code><code>render {job?.id || "—"} {job?.cached ? "(cache)" : ""}</code></div>}
    </section></div>
  </main>;
}

export default function ScadModules() {
  const {apiFetch, user} = useAuth(); const [scope,setScope]=useState("public"); const [modules,setModules]=useState<ScadModule[]>([]); const [selected,setSelected]=useState<string|null>(()=>location.hash.startsWith("#module:")?location.hash.slice(8):null);
  const [search,setSearch]=useState(""); const [author,setAuthor]=useState(""); const [category,setCategory]=useState(""); const [sort,setSort]=useState("updated"); const [categories,setCategories]=useState<string[]>(["Other"]); const [error,setError]=useState(""); const [importing,setImporting]=useState(false);
  const load=useCallback(async()=>{const query=new URLSearchParams({scope,search,author,category,sort}); const response=await apiFetch(`/api/scad/modules?${query}`); if(!response.ok)throw new Error(await errorMessage(response)); setModules((await response.json()).modules)},[apiFetch,scope,search,author,category,sort]);
  useEffect(()=>{if(!selected)load().catch(reason=>setError(String(reason)))},[load,selected]);
  useEffect(()=>{apiFetch("/api/scad/categories").then(async response=>{if(response.ok)setCategories((await response.json()).categories)})},[apiFetch]);
  const open=(id:string)=>{location.hash=`module:${id}`;setSelected(id)}; const back=()=>{history.replaceState(null,"",location.pathname);setSelected(null);load()};
  if(selected)return <ModuleEditor moduleId={selected} onBack={back} onOpen={setSelected}/>;
  return <main className="modules-page"><header className="modules-hero"><div><p className="eyebrow">PARAMETRIC MODEL MAKER</p><h1>Moduły parametryczne</h1><p>Gotowe generatory OpenSCAD oraz moduły społeczności.</p></div><button className="scad-primary" onClick={()=>setImporting(true)}>＋ Dodaj moduł</button></header>
    <nav className="module-tabs"><button className={scope==="my"?"active":""} onClick={()=>setScope("my")}>Moje moduły</button><button className={scope==="public"?"active":""} onClick={()=>setScope("public")}>Publiczne</button><button className={scope==="official"?"active":""} onClick={()=>setScope("official")}>Official</button><button className={scope==="shared"?"active":""} onClick={()=>setScope("shared")}>Udostępnione</button>{user.role==="admin"&&<button className={scope==="all"?"active":""} onClick={()=>setScope("all")}>Wszystkie / moderacja</button>}</nav>
    <div className="module-filters"><input type="search" placeholder="Szukaj nazwy lub opisu…" value={search} onChange={e=>setSearch(e.target.value)}/><input className="author-filter" placeholder="Autor" value={author} onChange={e=>setAuthor(e.target.value)}/><select value={category} onChange={e=>setCategory(e.target.value)}><option value="">Wszystkie kategorie</option>{categories.map(item=><option key={item}>{item}</option>)}</select><select value={sort} onChange={e=>setSort(e.target.value)}><option value="updated">Ostatnio aktualizowane</option><option value="newest">Najnowsze</option><option value="name">Nazwa A–Z</option></select></div>
    {error&&<p className="error">{error}</p>}<section className="module-grid">{modules.map(item=><ModuleCard item={item} key={item.id} onOpen={()=>open(item.id)}/>)}</section>{!modules.length&&!error&&<div className="module-empty"><b>Brak modułów w tej sekcji</b><span>Dodaj pierwszy plik .scad lub zmień filtry.</span></div>}
    {importing&&<ImportModule categories={categories} onClose={()=>setImporting(false)} onDone={item=>{setImporting(false);open(item.id)}}/>}
  </main>;
}
