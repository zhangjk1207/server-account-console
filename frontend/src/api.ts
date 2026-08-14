export type Host = { id:string; name:string; address:string; port:number; ssh_user:string; tags:string[]; data_root:string|null; status:string; last_probe_error?:string|null; last_probe_latency_ms?:number|null };
export type HostCredentialStatus = { private_key_configured:boolean; sudo_password_configured:boolean; verified_at:string|null; ssh_verified:boolean|null; sudo_verified:boolean|null; last_error:string|null };
export type HostCredentialProbe = { fingerprint:string|null; requires_confirmation:boolean; ssh_ok:boolean|null; sudo_ok:boolean|null; error:string|null; latency_ms:number|null };
export type AgentModelConfig = { provider:"openai"|"anthropic"|"google"|"openai-compatible"; model:string; base_url:string|null; thinking_level:"off"|"minimal"|"low"|"medium"|"high"; enabled:boolean; api_key_configured:boolean };
export type HostAuthorizedKey = { public_key:string; fingerprint:string; comment:string };
export type HostUser = { username:string; uid:number; primary_group:string; groups:string[]; shell:string; home:string; locked:boolean|null; expires_at:string|null; public_keys:HostAuthorizedKey[] };
export type SshPasswordAuthentication = { enabled:boolean };
export type User = { id:string; username:string; display_name:string; shell:string; home:string; enabled:boolean };
export type Script = { id:string; name:string; description:string; version:number; enabled:boolean; body:string };
export type SshKey = { id:string; managed_user_id:string; public_key:string; fingerprint:string; comment:string; enabled:boolean };
export type PermissionTemplate = { id:string; name:string; description:string; groups:string[]; sudo_rule:string|null; enabled:boolean };
export type CommandPreview = { label:string; tasks:string[]; commands:string[]; warnings:string[]; key_fingerprints:string[]; existing_key_fingerprints?:string[] };
export type AccessGrantSnapshot = { host_id:string; username:string; account_origin:"created"|"adopted"; data_directory:string|null; remote_uid?:number|null; remote_primary_group?:string|null; remote_home?:string|null; command_preview?:CommandPreview };
export type AccessGrant = { id:string; host_id:string; host_name:string; username:string; permission_template_id:string|null; template_name:string|null; groups:string[]; sudo_rule:string|null; account_origin:"created"|"adopted"; remote_uid:number|null; remote_primary_group:string|null; remote_home:string|null; managed_key_fingerprints:string[]; data_directory:string|null; state:string; last_success_job_id:string|null; updated_at:string };
export type HostUserState = { host_id:string; host_name:string; status:string; synced_at:string|null; desired_hash:string|null };
export type JobTarget = { host_id:string; host_name:string; state:string; output:string; error:string|null; started_at:string|null; finished_at:string|null };
export type JobEvent = { id:string; job_id:string; host_id:string|null; level:string; message:string; created_at:string };
export type Job = {
  id:string; state:string; kind:string; created_at:string; started_at?:string|null; finished_at?:string|null;
  user_snapshot?:Record<string, unknown>; request_snapshot:Record<string, unknown> & { host_ids?:string[]; hosts?:{id:string;name:string;address:string}[]; grants?:AccessGrantSnapshot[] };
  script_snapshot?:{name:string;version:number}|null; targets?:JobTarget[];
};

let csrf = "";

type ApiValidationIssue = { type?: string; loc?: Array<string | number>; msg?: string };

export function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;
  const labels: Record<string, string> = { name:"机器标识", address:"地址", port:"端口", ssh_user:"SSH 用户", data_root:"数据根目录", base_url:"Base URL", api_key:"API Key" };
  const messages = detail.map((issue: ApiValidationIssue) => {
    const field = String(issue.loc?.at(-1) ?? "请求参数");
    const label = labels[field] ?? field;
    if (field === "name" && issue.type === "string_pattern_mismatch") return "机器标识只能使用英文字母、数字、点、下划线和连字符";
    if (issue.type === "string_pattern_mismatch") return `${label}格式不正确`;
    if (issue.type === "string_too_short") return `${label}不能为空`;
    return `${label}：${issue.msg ?? "输入不正确"}`;
  });
  return messages.length ? messages.join("；") : null;
}

async function ensureCsrf(): Promise<void> {
  if (csrf) return;
  const response = await fetch("/api/auth/csrf", { credentials: "include" });
  if (!response.ok) throw new Error("登录状态已失效");
  csrf = (await response.json() as { token: string }).token;
}

export async function api<T>(path:string, init:RequestInit = {}): Promise<T> {
  const method = init.method?.toUpperCase() ?? "GET";
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && path !== "/auth/login") await ensureCsrf();
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      credentials:"include",
      headers:{ ...(init.body instanceof FormData ? {} : {"Content-Type":"application/json"}), ...(csrf ? {"X-CSRF-Token":csrf}:{}), ...init.headers },
      ...init,
    });
  } catch {
    throw new Error("无法连接控制面，请确认 API 服务正在运行");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(formatApiDetail(body?.detail) ?? `请求失败 (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function login(password:string) {
  await api<void>("/auth/login", {method:"POST",body:JSON.stringify({password})});
  csrf=(await api<{token:string}>("/auth/csrf")).token;
}
