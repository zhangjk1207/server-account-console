export type Host = { id:string; name:string; address:string; port:number; ssh_user:string; tags:string[]; status:string };
export type User = { id:string; username:string; display_name:string; shell:string; home:string; enabled:boolean };
export type Script = { id:string; name:string; description:string; version:number; enabled:boolean; body:string };
export type Job = { id:string; state:string; kind:string; created_at:string; request_snapshot: { host_ids:string[] } };
let csrf = "";

async function ensureCsrf(): Promise<void> {
  if (csrf) return;
  const response = await fetch("/api/auth/csrf", { credentials: "include" });
  if (!response.ok) throw new Error("登录状态已失效");
  csrf = (await response.json() as { token: string }).token;
}

export async function api<T>(path:string, init:RequestInit = {}): Promise<T> {
  const method = init.method?.toUpperCase() ?? "GET";
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && path !== "/auth/login") await ensureCsrf();
  const response = await fetch(`/api${path}`, { credentials:"include", headers:{ "Content-Type":"application/json", ...(csrf ? {"X-CSRF-Token":csrf}:{}), ...init.headers }, ...init });
  if (!response.ok) throw new Error((await response.json().catch(()=>null))?.detail || `请求失败 (${response.status})`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export async function login(password:string) { await api<void>("/auth/login", {method:"POST",body:JSON.stringify({password})}); csrf=(await api<{token:string}>("/auth/csrf")).token; }
