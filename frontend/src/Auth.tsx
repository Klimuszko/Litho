import { createContext, FormEvent, ReactNode, useCallback, useContext, useEffect, useState } from "react";

type User = {id: number; username: string; display_name: string; role: "admin" | "operator"; active: boolean; created_at: string};
type AuthContextValue = {user: User; apiFetch: typeof fetch; logout: () => Promise<void>; changePassword: () => Promise<void>};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

function Login({onLogin}: {onLogin: (username: string, password: string) => Promise<void>}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { await onLogin(username, password); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Logowanie nie powiodło się."); }
    finally { setBusy(false); }
  };
  return <main className="login-page">
    <form className="login-card" onSubmit={submit}>
      <div className="login-logo">L</div>
      <p className="eyebrow">PRYWATNY PANEL PRODUKCYJNY</p>
      <h1>Zaloguj się do Litho</h1>
      <p className="login-copy">Generator i projekty klientów są dostępne wyłącznie dla zespołu.</p>
      <label>Login<input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required autoFocus/></label>
      <label>Hasło<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required/></label>
      {error && <p className="error">{error}</p>}
      <button className="generate" disabled={busy}>{busy ? "Logowanie…" : "Zaloguj się"}<span>→</span></button>
    </form>
  </main>;
}

function UserManager({apiFetch}: {apiFetch: typeof fetch}) {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({username: "", display_name: "", password: "", role: "operator" as "admin" | "operator"});
  const load = useCallback(async () => {
    const response = await apiFetch("/api/auth/users");
    if (!response.ok) throw new Error("Nie udało się pobrać kont.");
    setUsers((await response.json()).users);
  }, [apiFetch]);
  useEffect(() => { load().catch(reason => setError(String(reason))); }, [load]);
  const create = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    const response = await apiFetch("/api/auth/users", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(form)});
    if (!response.ok) { const problem = await response.json(); setError(problem.detail?.message || problem.message || "Nie udało się utworzyć konta."); return; }
    setForm({username: "", display_name: "", password: "", role: "operator"}); await load();
  };
  const save = async (user: User) => {
    const response = await apiFetch(`/api/auth/users/${user.id}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({display_name: user.display_name, role: user.role, active: user.active})});
    if (!response.ok) { const problem = await response.json(); setError(problem.detail?.message || "Nie udało się zapisać konta."); return; }
    await load();
  };
  const resetPassword = async (user: User) => {
    const password = window.prompt(`Nowe hasło dla ${user.username} (minimum 12 znaków):`);
    if (!password) return;
    const response = await apiFetch(`/api/auth/users/${user.id}/password`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({new_password: password})});
    if (!response.ok) { const problem = await response.json(); setError(problem.detail?.message || "Nie udało się zmienić hasła."); }
  };
  return <main className="admin-page">
    <section className="admin-panel">
      <header><div><p className="eyebrow">ADMINISTRACJA</p><h1>Konta zespołu</h1><p>Zarządzaj dostępem administratorów i operatorów do aplikacji.</p></div></header>
      {error && <p className="error">{error}</p>}
      <div className="user-list">{users.map((user, index) => <div className="user-row" key={user.id}>
        <input aria-label="Nazwa" value={user.display_name} onChange={event => setUsers(current => current.map((item, i) => i === index ? {...item, display_name: event.target.value} : item))}/>
        <strong>{user.username}</strong>
        <select value={user.role} onChange={event => setUsers(current => current.map((item, i) => i === index ? {...item, role: event.target.value as User["role"]} : item))}><option value="operator">Operator</option><option value="admin">Administrator</option></select>
        <label className="user-active"><input type="checkbox" checked={user.active} onChange={event => setUsers(current => current.map((item, i) => i === index ? {...item, active: event.target.checked} : item))}/> Aktywne</label>
        <button onClick={() => save(user)}>Zapisz</button><button onClick={() => resetPassword(user)}>Nowe hasło</button>
      </div>)}</div>
      <form className="new-user" onSubmit={create}>
        <h3>Dodaj konto</h3>
        <input placeholder="Login" value={form.username} onChange={event => setForm({...form, username: event.target.value})} required minLength={3}/>
        <input placeholder="Imię / nazwa" value={form.display_name} onChange={event => setForm({...form, display_name: event.target.value})} required/>
        <input type="password" placeholder="Hasło — min. 12 znaków" value={form.password} onChange={event => setForm({...form, password: event.target.value})} required minLength={12}/>
        <select value={form.role} onChange={event => setForm({...form, role: event.target.value as User["role"]})}><option value="operator">Operator</option><option value="admin">Administrator</option></select>
        <button className="generate">Dodaj konto</button>
      </form>
    </section>
  </main>;
}

export default function AuthProvider({children}: {children: ReactNode}) {
  const [user, setUser] = useState<User | null>(null);
  const [csrf, setCsrf] = useState("");
  const [loading, setLoading] = useState(true);
  const [manageUsers, setManageUsers] = useState(false);
  useEffect(() => {
    if (user?.role !== "admin") setManageUsers(false);
  }, [user]);
  useEffect(() => {
    fetch("/api/auth/me", {credentials: "include"}).then(async response => {
      if (!response.ok) return;
      const data = await response.json(); setUser(data.user); setCsrf(data.csrf_token);
    }).finally(() => setLoading(false));
  }, []);
  const apiFetch = useCallback(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const headers = new Headers(init.headers);
    const method = (init.method || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", csrf);
    const response = await fetch(input, {...init, headers, credentials: "include"});
    if (response.status === 401) setUser(null);
    return response;
  }, [csrf]);
  const login = async (username: string, password: string) => {
    const response = await fetch("/api/auth/login", {method: "POST", credentials: "include", headers: {"Content-Type": "application/json"}, body: JSON.stringify({username, password})});
    if (!response.ok) { const problem = await response.json(); throw new Error(problem.detail?.message || problem.message || "Nieprawidłowy login lub hasło."); }
    const data = await response.json(); setUser(data.user); setCsrf(data.csrf_token);
  };
  const logout = async () => { await apiFetch("/api/auth/logout", {method: "POST"}); setUser(null); setCsrf(""); };
  const changePassword = async () => {
    const current_password = window.prompt("Obecne hasło:"); if (!current_password) return;
    const new_password = window.prompt("Nowe hasło (minimum 12 znaków):"); if (!new_password) return;
    const response = await apiFetch("/api/auth/password", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({current_password, new_password})});
    if (!response.ok) { const problem = await response.json(); window.alert(problem.detail?.message || "Nie udało się zmienić hasła."); return; }
    setUser(null); setCsrf("");
  };
  if (loading) return <main className="login-page"><div className="login-loader">Litho</div></main>;
  if (!user) return <Login onLogin={login}/>;
  return <AuthContext.Provider value={{user, apiFetch, logout, changePassword}}>
    <div className="authenticated-app">
      <header className="topbar">
        <div className="topbar-brand"><span>L</span><strong>Litho</strong></div>
        <nav aria-label="Główna nawigacja">
          <button className={!manageUsers ? "active" : ""} aria-current={!manageUsers ? "page" : undefined} onClick={() => setManageUsers(false)}>Generator</button>
          {user.role === "admin" && <button className={manageUsers ? "active" : ""} aria-current={manageUsers ? "page" : undefined} onClick={() => setManageUsers(true)}>Administracja</button>}
        </nav>
        <div className="topbar-account"><span><b>{user.display_name}</b><small>{user.role === "admin" ? "Administrator" : "Operator"}</small></span><button onClick={changePassword}>Hasło</button><button onClick={logout}>Wyloguj</button></div>
      </header>
      <div className="app-content" hidden={manageUsers}>{children}</div>
      {user.role === "admin" && <div hidden={!manageUsers}><UserManager apiFetch={apiFetch}/></div>}
    </div>
  </AuthContext.Provider>;
}
