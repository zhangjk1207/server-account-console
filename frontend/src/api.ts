export type Host = { id:string; name:string; address:string; port:number; ssh_user:string; tags:string[]; status:string; last_probe_error?:string|null; last_probe_latency_ms?:number|null };
export type User = { id:string; username:string; display_name:string; shell:string; home:string; enabled:boolean };
export type Script = { id:string; name:string; description:string; version:number; enabled:boolean; body:string };
export type SshKey = { id:string; managed_user_id:string; public_key:string; fingerprint:string; comment:string; enabled:boolean };
export type HostUserState = { host_id:string; host_name:string; status:string; synced_at:string|null; desired_hash:string|null };
export type JobTarget = { host_id:string; host_name:string; state:string; output:string; error:string|null; started_at:string|null; finished_at:string|null };
export type JobEvent = { id:string; job_id:string; host_id:string|null; level:string; message:string; created_at:string };
export type Job = {
  id:string; state:string; kind:string; created_at:string; started_at?:string|null; finished_at?:string|null;
  user_snapshot?:Record<string, unknown>; request_snapshot:{ host_ids?:string[]; hosts?:{id:string;name:string;address:string}[] };
  script_snapshot?:{name:string;version:number}|null; targets?:JobTarget[];
};

let csrf = "";

async function ensureCsrf(): Promise<void> {
  if (csrf) return;
  const response = await fetch("/api/auth/csrf", { credentials: "include" });
  if (!response.ok) throw new Error("登录状态已失效");
  csrf = (await response.json() as { token: string }).token;
}

export async function api<T>(path:string, init:RequestInit = {}): Promise<T> {
  const method = init.method?.toUpperCase() ?? "GET";
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && path !== "/auth/login") await ensureCsrf();
  const response = await fetch(`/api${path}`, {
    credentials:"include",
    headers:{ "Content-Type":"application/json", ...(csrf ? {"X-CSRF-Token":csrf}:{}), ...init.headers },
    ...init,
  });
  if (!response.ok) throw new Error((await response.json().catch(()=>null))?.detail || `请求失败 (${response.status})`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function login(password:string) {
  await api<void>("/auth/login", {method:"POST",body:JSON.stringify({password})});
  csrf=(await api<{token:string}>("/auth/csrf")).token;
}
