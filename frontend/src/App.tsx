import { FormEvent, useEffect, useMemo, useState } from "react";
import { Activity, ChevronRight, CircleCheck, KeyRound, LayoutDashboard, MonitorCog, Play, RotateCcw, TerminalSquare, Users } from "lucide-react";

import { api, Host, HostCredentialProbe, HostCredentialStatus, HostUser, HostUserState, Job, JobEvent, login, Script, SshKey, SshPasswordAuthentication, User } from "./api";
import { Button } from "./components/ui/button";

type View = "overview" | "hosts" | "users" | "scripts" | "jobs";
const nav: {id:View; label:string; icon:typeof Activity}[] = [
  {id:"overview",label:"概览",icon:LayoutDashboard}, {id:"hosts",label:"机器",icon:MonitorCog},
  {id:"users",label:"用户与公钥",icon:Users}, {id:"scripts",label:"脚本模板",icon:TerminalSquare}, {id:"jobs",label:"执行记录",icon:Activity},
];
const runningStates = new Set(["pending", "preview_running", "running"]);
const stateLabel: Record<string, string> = { pending:"等待中", preview_running:"预检中", ready_to_confirm:"预检完成", preview_failed:"预检失败", running:"执行中", succeeded:"已完成", partial_failed:"部分失败", expired:"已过期", failed:"失败", synced:"已同步", enabled:"已启用", disabled:"已停用", reachable:"可连接", unreachable:"不可连接", unconfirmed:"待确认指纹", fingerprint_changed:"指纹已变化" };

export function App() {
  const [view,setView] = useState<View>("overview");
  const [authed,setAuthed] = useState(false);
  const [password,setPassword] = useState("");
  const [error,setError] = useState("");
  const [hosts,setHosts] = useState<Host[]>([]);
  const [users,setUsers] = useState<User[]>([]);
  const [scripts,setScripts] = useState<Script[]>([]);
  const [jobs,setJobs] = useState<Job[]>([]);
  const [syncUser,setSyncUser] = useState<User|null>(null);
  const [selectedHosts,setSelectedHosts] = useState<string[]>([]);
  const [selectedScript,setSelectedScript] = useState("");
  const [activeJob,setActiveJob] = useState<Job|null>(null);
  const [events,setEvents] = useState<JobEvent[]>([]);
  const [confirmed,setConfirmed] = useState(false);

  const load = async () => {
    try {
      const [nextHosts,nextUsers,nextScripts,nextJobs] = await Promise.all([
        api<Host[]>("/hosts"), api<User[]>("/users"), api<Script[]>("/script-templates"), api<Job[]>("/jobs"),
      ]);
      setHosts(nextHosts); setUsers(nextUsers); setScripts(nextScripts); setJobs(nextJobs); setError("");
      if (activeJob) setActiveJob(nextJobs.find((job) => job.id === activeJob.id) ?? activeJob);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "加载失败"); }
  };

  useEffect(() => { fetch("/api/auth/me", {credentials:"include"}).then((response) => { if (response.ok) { setAuthed(true); void load(); } }); }, []);
  useEffect(() => {
    if (!authed || !jobs.some((job) => runningStates.has(job.state))) return;
    const timer = window.setInterval(() => void load(), 1200);
    return () => window.clearInterval(timer);
  }, [authed, jobs]);
  useEffect(() => {
    if (!activeJob || !runningStates.has(activeJob.state) || typeof EventSource === "undefined") return;
    const source = new EventSource(`/api/jobs/${activeJob.id}/events`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as JobEvent;
      setEvents((current) => current.some((item) => item.id === event.id) ? current : [...current, event]);
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [activeJob?.id, activeJob?.state]);

  const activeEvents = useMemo(() => events.filter((event) => event.job_id === activeJob?.id), [activeJob?.id, events]);
  const openJob = async (job: Job) => {
    const detail = await api<Job>(`/jobs/${job.id}`);
    setActiveJob(detail); setEvents([]); setConfirmed(false);
  };
  const preview = async () => {
    if (!syncUser || !selectedHosts.length) { setError("请至少勾选一台可连接机器"); return; }
    const job = await api<Job>("/jobs/preview", { method:"POST", body:JSON.stringify({ user_id:syncUser.id, host_ids:selectedHosts, script_template_id:selectedScript || null }) });
    setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]); setActiveJob(job); setEvents([]); setConfirmed(false); setSyncUser(null); setView("jobs");
  };
  const execute = async (job: Job, newPassword = "") => {
    const isHostOperation = ["host_user_operation", "ssh_password_authentication"].includes(job.kind);
    const operation = job.request_snapshot.operation as { action?: string } | undefined;
    const body = isHostOperation ? JSON.stringify(operation?.action === "reset_password" ? {new_password:newPassword} : {}) : undefined;
    const next = await api<Job>(`${isHostOperation ? "/host-operations" : "/jobs"}/${job.id}/execute`, {method:"POST", ...(body ? {body} : {})});
    setActiveJob(next); setJobs((current) => current.map((item) => item.id === next.id ? next : item)); setConfirmed(false);
  };
  const rerun = async (job: Job) => {
    const next = await api<Job>(`/jobs/${job.id}/rerun`, {method:"POST"});
    setJobs((current) => [next, ...current]); setActiveJob(next); setEvents([]); setConfirmed(false);
  };

  if (!authed) return <Login password={password} error={error} onPassword={setPassword} onLogin={async () => { try { await login(password); setAuthed(true); await load(); } catch (cause) { setError(cause instanceof Error ? cause.message : "登录失败"); } }} />;

  const content = view === "overview" ? <Overview hosts={hosts} users={users} jobs={jobs} onOpen={openJob} />
    : view === "hosts" ? <Hosts hosts={hosts} users={users} onAdd={async (form) => { await api<Host>("/hosts", {method:"POST",body:JSON.stringify(form)}); await load(); }} onArchive={async (host) => { if (!window.confirm(`归档机器 ${host.name}？`)) return; await api(`/hosts/${host.id}`, {method:"DELETE"}); await load(); }} onTest={async (host) => { const result = await api<{requires_confirmation:boolean;fingerprint:string|null;error:string|null}>(`/hosts/${host.id}/test`, {method:"POST"}); if (result.requires_confirmation && result.fingerprint && window.confirm(`确认主机指纹？\n${result.fingerprint}`)) await api(`/hosts/${host.id}/confirm-fingerprint`, {method:"POST",body:JSON.stringify({fingerprint:result.fingerprint})}); if (result.error) setError(result.error); await load(); }} onError={setError} onPreview={(job) => { setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]); setActiveJob(job); setEvents([]); setConfirmed(false); setView("jobs"); }} />
    : view === "users" ? <UsersView users={users} onAdd={async (form) => { await api<User>("/users", {method:"POST",body:JSON.stringify(form)}); await load(); }} onAddKey={(user, key) => api<SshKey>(`/users/${user.id}/keys`, {method:"POST",body:JSON.stringify({public_key:key})})} onDisable={async (user) => { if (!window.confirm(`停用用户 ${user.username}？`)) return; await api(`/users/${user.id}`, {method:"DELETE"}); await load(); }} onSync={(user) => { setSyncUser(user); setSelectedHosts([]); setSelectedScript(""); }} />
    : view === "scripts" ? <ScriptsView scripts={scripts} onAdd={async (form) => { await api<Script>("/script-templates", {method:"POST",body:JSON.stringify(form)}); await load(); }} onDisable={async (script) => { if (!window.confirm(`停用模板 ${script.name}？`)) return; await api(`/script-templates/${script.id}`, {method:"DELETE"}); await load(); }} />
    : <JobsView jobs={jobs} activeJob={activeJob} events={activeEvents} confirmed={confirmed} onOpen={openJob} onConfirmed={setConfirmed} onExecute={execute} onRerun={rerun} />;

  return <div className="layout"><aside><div className="brand"><KeyRound size={20}/><span>ACC/CTL</span></div>{nav.map((item) => { const Icon = item.icon; return <button key={item.id} className={view === item.id ? "nav active" : "nav"} onClick={() => setView(item.id)}><Icon size={17}/>{item.label}</button>; })}</aside><main className="workspace"><header><div><p className="eyebrow">单管理员 · 内网控制面</p><h1>{nav.find((item) => item.id === view)?.label}</h1></div><Button className="quiet" onClick={() => void load()}>刷新</Button></header>{error && <p className="error">{error}</p>}{content}{syncUser && <SyncPanel user={syncUser} hosts={hosts} scripts={scripts} selectedHosts={selectedHosts} selectedScript={selectedScript} onToggle={(id, checked) => setSelectedHosts((current) => checked ? [...current, id] : current.filter((value) => value !== id))} onScript={setSelectedScript} onPreview={preview} onCancel={() => setSyncUser(null)} />}</main></div>;
}

function Login({password,error,onPassword,onLogin}:{password:string;error:string;onPassword:(value:string)=>void;onLogin:()=>Promise<void>}) { return <main className="login"><section><p className="eyebrow">INTERNAL CONTROL PLANE</p><h1>账户管理控制台</h1><p>在确认前不改变任何机器。</p><form onSubmit={(event) => { event.preventDefault(); void onLogin(); }}><label>管理员密码<input autoFocus type="password" value={password} onChange={(event) => onPassword(event.target.value)}/></label><Button type="submit">进入控制台 <ChevronRight size={16}/></Button>{error && <small className="error">{error}</small>}</form></section></main>; }
function Overview({hosts,users,jobs,onOpen}:{hosts:Host[];users:User[];jobs:Job[];onOpen:(job:Job)=>Promise<void>}) { return <><div className="metrics"><Metric label="机器" value={hosts.length}/><Metric label="可连接" value={hosts.filter((host) => host.status === "reachable").length}/><Metric label="用户" value={users.length}/><Metric label="任务" value={jobs.length}/></div><section className="panel"><h2>最近任务</h2><JobTable jobs={jobs.slice(0,6)} onOpen={onOpen}/></section></>; }
function Metric({label,value}:{label:string;value:number}) { return <section className="metric"><span>{label}</span><strong>{value}</strong></section>; }
function Hosts({hosts,users,onAdd,onArchive,onTest,onError,onPreview}:{hosts:Host[];users:User[];onAdd:(value:Record<string,unknown>)=>Promise<void>;onArchive:(host:Host)=>Promise<void>;onTest:(host:Host)=>Promise<void>;onError:(message:string)=>void;onPreview:(job:Job)=>void}) {
  const [selected,setSelected] = useState<Host|null>(null);
  return <><InlineForm title="接入机器" fields={["name:名称","address:IP 或 FQDN","port:端口","ssh_user:SSH 用户","tags:标签，逗号分隔"]} onSubmit={async (form) => onAdd({name:form.name,address:form.address,port:Number(form.port || 22),ssh_user:form.ssh_user || "root",tags:(form.tags || "").split(",").map((tag) => tag.trim()).filter(Boolean)})}/><Table rows={hosts} columns={["name","address","ssh_user","tags"]} render={(host) => <><State state={host.status}/>{host.last_probe_error && <small className="muted">{host.last_probe_error}</small>}</>} action={(host) => <><Button className="quiet" onClick={() => setSelected(host)}>详情</Button><Button onClick={() => void onTest(host)}>测试连接</Button><Button className="quiet" onClick={() => void onArchive(host)}>归档</Button></>}/>{selected && <HostDetail key={selected.id} host={selected} users={users} onClose={() => setSelected(null)} onError={onError} onPreview={onPreview}/>}</>;
}

function HostDetail({host,users,onClose,onError,onPreview}:{host:Host;users:User[];onClose:()=>void;onError:(message:string)=>void;onPreview:(job:Job)=>void}) {
  const [credential,setCredential] = useState<HostCredentialStatus|null>(null);
  const [privateKey,setPrivateKey] = useState<File|null>(null);
  const [sudoPassword,setSudoPassword] = useState("");
  const [probe,setProbe] = useState<HostCredentialProbe|null>(null);
  const [hostUsers,setHostUsers] = useState<HostUser[]>([]);
  const [listed,setListed] = useState(false);
  const [openKeys,setOpenKeys] = useState<{username:string;keys:{fingerprint:string;comment:string;public_key:string}[]}|null>(null);
  const [passwordAuthentication,setPasswordAuthentication] = useState<SshPasswordAuthentication|null>(null);
  const [action,setAction] = useState("upsert");
  const [username,setUsername] = useState("");
  const [managedUserId,setManagedUserId] = useState("");
  const [groups,setGroups] = useState("");
  const [shell,setShell] = useState("/bin/bash");
  const [home,setHome] = useState("");
  const [sudoRule,setSudoRule] = useState("");
  const [keys,setKeys] = useState("");
  const [keyMode,setKeyMode] = useState("append");
  const [removeHome,setRemoveHome] = useState(false);

  useEffect(() => { void api<HostCredentialStatus>(`/hosts/${host.id}/credentials`).then(setCredential).catch((cause) => onError(cause instanceof Error ? cause.message : "无法读取凭证状态")); }, [host.id, onError]);

  const message = (cause:unknown, fallback:string) => cause instanceof Error ? cause.message : fallback;
  const saveCredentials = async (event:FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!privateKey || !sudoPassword) { onError("请选择 SSH 私钥文件并输入 sudo 密码"); return; }
    const form = new FormData(); form.set("private_key_file", privateKey); form.set("sudo_password", sudoPassword);
    try { setCredential(await api<HostCredentialStatus>(`/hosts/${host.id}/credentials`, {method:"PUT",body:form})); setPrivateKey(null); setSudoPassword(""); setProbe(null); } catch (cause) { onError(message(cause,"保存凭证失败")); }
  };
  const testCredentials = async () => {
    try {
      let result = await api<HostCredentialProbe>(`/hosts/${host.id}/credentials/test`, {method:"POST"});
      if (result.requires_confirmation && result.fingerprint && window.confirm(`确认主机指纹？\n${result.fingerprint}`)) {
        await api(`/hosts/${host.id}/confirm-fingerprint`, {method:"POST",body:JSON.stringify({fingerprint:result.fingerprint})});
        result = await api<HostCredentialProbe>(`/hosts/${host.id}/credentials/test`, {method:"POST"});
      }
      setProbe(result); setCredential(await api<HostCredentialStatus>(`/hosts/${host.id}/credentials`));
      if (result.error) onError(result.error);
    } catch (cause) { onError(message(cause,"凭证测试失败")); }
  };
  const listUsers = async () => { try { setHostUsers(await api<HostUser[]>(`/hosts/${host.id}/users`)); setListed(true); } catch (cause) { onError(message(cause,"用户盘点失败")); } };
  const listKeys = async (user:HostUser) => { try { setOpenKeys({username:user.username,keys:await api(`/hosts/${host.id}/users/${user.username}/keys`)}); } catch (cause) { onError(message(cause,"公钥读取失败")); } };
  const inspectPasswordAuthentication = async () => { try { setPasswordAuthentication(await api<SshPasswordAuthentication>(`/hosts/${host.id}/ssh-password-authentication`)); } catch (cause) { onError(message(cause,"SSH 配置读取失败")); } };
  const previewPasswordAuthentication = async (enabled:boolean) => { try { onPreview(await api<Job>(`/hosts/${host.id}/ssh-password-authentication/preview`, {method:"POST",body:JSON.stringify({enabled})})); } catch (cause) { onError(message(cause,"SSH 设置预检失败")); } };
  const chooseManagedUser = (id:string) => { setManagedUserId(id); const user = users.find((item) => item.id === id); if (user) { setUsername(user.username); setShell(user.shell); setHome(user.home); } };
  const previewUserOperation = async (event:FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload:Record<string,unknown> = {action,username};
    if (managedUserId) payload.managed_user_id = managedUserId;
    if (action === "upsert") { if (groups.trim()) payload.groups = groups.split(",").map((value) => value.trim()).filter(Boolean); if (shell.trim()) payload.shell = shell.trim(); if (home.trim()) payload.home = home.trim(); payload.sudo_rule = sudoRule.trim(); }
    if (action === "delete") payload.remove_home = removeHome;
    if (action === "keys") { const existing = hostUsers.find((item) => item.username === username); if (existing) payload.home = existing.home; payload.key_mode = keyMode; payload.public_keys = keys.split("\n").map((value) => value.trim()).filter(Boolean); }
    try { onPreview(await api<Job>(`/hosts/${host.id}/user-operations/preview`, {method:"POST",body:JSON.stringify(payload)})); } catch (cause) { onError(message(cause,"用户操作预检失败")); }
  };
  const credentialReady = Boolean(credential?.ssh_verified && credential?.sudo_verified);
  const verificationLabel = (value:boolean|null|undefined) => value === true ? "通过" : value === false ? "未通过" : "未验证";
  const sshVerification = probe?.ssh_ok ?? credential?.ssh_verified;
  const sudoVerification = probe?.sudo_ok ?? credential?.sudo_verified;

  return <section className="host-detail" aria-label={`${host.name} 机器工作台`}><div className="host-detail-heading"><div><p className="eyebrow">机器工作台 · {host.address}:{host.port}</p><h2>{host.name}</h2></div><div><State state={host.status}/><Button className="quiet" onClick={onClose}>关闭详情</Button></div></div><div className="host-grid"><section className="panel credential-panel"><div className="section-heading"><h3>连接凭证</h3><State state={credentialReady ? "enabled" : "pending"}/></div><p className="muted">私钥与 sudo 密码以加密形式保存，页面和任务日志不会回显。</p><form className="operation-form" onSubmit={(event) => void saveCredentials(event)}><label>SSH 私钥文件<input type="file" accept=".key,.pem,*/*" onChange={(event) => setPrivateKey(event.target.files?.[0] ?? null)}/></label><label>sudo 密码<input type="password" autoComplete="new-password" value={sudoPassword} onChange={(event) => setSudoPassword(event.target.value)}/></label><div className="form-actions"><Button type="submit">保存凭证</Button><Button type="button" className="quiet" disabled={!credential?.private_key_configured} onClick={() => void testCredentials()}>测试 SSH 与 sudo</Button></div></form>{credential?.verified_at && <p className="muted">最近验证：{new Date(credential.verified_at).toLocaleString()}</p>}{credential?.last_error && <p className="error">{credential.last_error}</p>}{credential && <div className="probe-result"><span>SSH：{verificationLabel(sshVerification)}</span><span>sudo：{verificationLabel(sudoVerification)}</span>{probe?.latency_ms != null && <span>{probe.latency_ms} ms</span>}</div>}</section><section className="panel ssh-panel"><div className="section-heading"><h3>SSH 密码登录</h3><Button className="quiet" onClick={() => void inspectPasswordAuthentication()}>读取当前状态</Button></div>{passwordAuthentication ? <><p className={passwordAuthentication.enabled ? "error" : "muted"}>当前：{passwordAuthentication.enabled ? "已允许密码登录" : "已关闭密码登录"}</p><div className="form-actions"><Button className="quiet" onClick={() => void previewPasswordAuthentication(true)}>预检开启</Button><Button disabled={!credentialReady} onClick={() => void previewPasswordAuthentication(false)}>预检关闭</Button></div></> : <p className="muted">按需读取目标机 `sshd` 的实际生效配置。</p>}</section></div><section className="panel inventory-panel"><div className="section-heading"><div><h3>已有系统用户</h3><p className="muted">盘点 UID 大于等于 1000 的本地用户；仅在已验证凭证后可用。</p></div><Button disabled={!credentialReady} onClick={() => void listUsers()}>盘点已有用户</Button></div>{listed && <Table rows={hostUsers} columns={["username","uid","primary_group","groups","shell","home"]} render={(item) => <State state={item.locked === true ? "disabled" : item.locked === false ? "enabled" : "pending"}/>} action={(item) => <Button className="quiet" onClick={() => void listKeys(item)}>查看公钥</Button>}/>} {openKeys && <div className="key-list"><h3>{openKeys.username} 的公钥</h3><Table rows={openKeys.keys} columns={["fingerprint","comment","public_key"]}/></div>}</section><section className="panel operation-panel"><div className="section-heading"><div><h3>用户运维</h3><p className="muted">创建、锁定、解锁、密码重置、删除和公钥变更均先预检，再到执行记录确认。</p></div><State state={credentialReady ? "enabled" : "pending"}/></div><form className="operation-form" onSubmit={(event) => void previewUserOperation(event)}><label>常用用户<select value={managedUserId} onChange={(event) => chooseManagedUser(event.target.value)}><option value="">不关联控制台用户</option>{users.filter((item) => item.enabled).map((user) => <option key={user.id} value={user.id}>{user.username} · {user.display_name || "未命名"}</option>)}</select></label><label>运维动作<select value={action} onChange={(event) => setAction(event.target.value)}><option value="upsert">创建或更新用户</option><option value="lock">锁定账户</option><option value="unlock">解锁账户</option><option value="reset_password">重置密码</option><option value="keys">管理 SSH 公钥</option><option value="delete">删除账户</option></select></label><label>目标用户名<input required value={username} onChange={(event) => setUsername(event.target.value)}/></label>{action === "upsert" && <><label>附加组<input value={groups} placeholder="docker,video" onChange={(event) => setGroups(event.target.value)}/></label><label>登录 Shell<input value={shell} onChange={(event) => setShell(event.target.value)}/></label><label>家目录<input value={home} placeholder="/home/username" onChange={(event) => setHome(event.target.value)}/></label><label className="wide">sudo 规则<textarea rows={2} value={sudoRule} onChange={(event) => setSudoRule(event.target.value)}/></label></>}{action === "keys" && <><label>公钥动作<select value={keyMode} onChange={(event) => setKeyMode(event.target.value)}><option value="append">追加</option><option value="remove">移除</option><option value="replace">完全替换</option></select></label><label className="wide">SSH 公钥<textarea required rows={4} value={keys} onChange={(event) => setKeys(event.target.value)} placeholder="每行一条公钥"/></label></>}{action === "delete" && <label className="check-option"><input type="checkbox" checked={removeHome} onChange={(event) => setRemoveHome(event.target.checked)}/>同时删除家目录</label>}<div className="form-actions"><Button type="submit" disabled={!credentialReady}>预检用户操作</Button></div></form></section></section>;
}
function UsersView({users,onAdd,onAddKey,onDisable,onSync}:{users:User[];onAdd:(value:Record<string,unknown>)=>Promise<void>;onAddKey:(user:User,key:string)=>Promise<SshKey>;onDisable:(user:User)=>Promise<void>;onSync:(user:User)=>void}) { const [keyUser,setKeyUser] = useState<User|null>(null); const [keys,setKeys] = useState<SshKey[]>([]); const [hostStates,setHostStates] = useState<HostUserState[]>([]); const [key,setKey] = useState(""); const openKeys = async (user:User) => { setKeyUser(user); setKey(""); const [nextKeys,nextStates] = await Promise.all([api<SshKey[]>(`/users/${user.id}/keys`),api<HostUserState[]>(`/users/${user.id}/host-states`)]); setKeys(nextKeys); setHostStates(nextStates); }; return <><UserForm onSubmit={onAdd}/><Table rows={users} columns={["username","display_name","shell","home"]} render={(user) => <State state={user.enabled ? "enabled" : "disabled"}/>} action={(user) => <><Button className="quiet" onClick={() => void openKeys(user)}><KeyRound size={14}/>公钥</Button><Button disabled={!user.enabled} onClick={() => onSync(user)}><Play size={14}/>同步</Button>{user.enabled && <Button className="quiet" onClick={() => void onDisable(user)}>停用用户</Button>}</>}/>{keyUser && <section className="panel key-panel"><h2>{keyUser.username} 的 SSH 公钥</h2><Table rows={keys} columns={["fingerprint","comment"]} render={(item) => <State state={item.enabled ? "enabled" : "disabled"}/>} action={(item) => item.enabled ? <Button className="quiet" onClick={async () => { await api(`/users/${keyUser.id}/keys/${item.id}`, {method:"DELETE"}); setKeys((current) => current.map((value) => value.id === item.id ? {...value,enabled:false} : value)); }}>停用</Button> : null}/><h3>机器同步状态</h3><Table rows={hostStates} columns={["host_name","synced_at"]} render={(item) => <State state={item.status}/>} /><label>SSH 公钥<textarea value={key} onChange={(event) => setKey(event.target.value)} rows={3}/></label><div><Button disabled={!key.trim()} onClick={async () => { const added = await onAddKey(keyUser, key); setKeys((current) => [...current, added]); setKey(""); }}>添加公钥</Button><Button className="quiet" onClick={() => setKeyUser(null)}>关闭</Button></div></section>}</>; }
function UserForm({onSubmit}:{onSubmit:(value:Record<string,unknown>)=>Promise<void>}) { const [formError,setFormError] = useState(""); return <form className="panel inline" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { const parseList = (name:string) => { const value = String(data.get(name) || "[]"); const parsed = JSON.parse(value); if (!Array.isArray(parsed)) throw new Error(`${name} 必须是 JSON 数组`); return parsed; }; const payload = { username:data.get("username"), display_name:data.get("display_name"), primary_group:data.get("primary_group") || undefined, groups:String(data.get("groups") || "").split(",").map((value) => value.trim()).filter(Boolean), shell:data.get("shell") || "/bin/bash", home:data.get("home") || undefined, sudo_rule:data.get("sudo_rule") || undefined, directories:parseList("directories"), symlinks:parseList("symlinks") }; void onSubmit(payload).then(() => { event.currentTarget.reset(); setFormError(""); }).catch((cause) => setFormError(cause instanceof Error ? cause.message : "保存失败")); } catch (cause) { setFormError(cause instanceof Error ? cause.message : "配置格式无效"); } }}><h2>创建 Linux 用户</h2><div><label>用户名<input name="username" required/></label><label>显示名<input name="display_name"/></label><label>主组<input name="primary_group"/></label><label>附加组<input name="groups" placeholder="docker,video"/></label><label>登录 Shell<input name="shell" placeholder="/bin/bash"/></label><label>家目录<input name="home" placeholder="/home/username"/></label><label className="wide">sudo 规则<textarea name="sudo_rule" rows={2}/></label><label className="wide">目录配置<textarea name="directories" defaultValue="[]" rows={2}/></label><label className="wide">软链接配置<textarea name="symlinks" defaultValue="[]" rows={2}/></label><Button type="submit">保存</Button>{formError && <small className="error">{formError}</small>}</div></form>; }
function ScriptsView({scripts,onAdd,onDisable}:{scripts:Script[];onAdd:(value:Record<string,unknown>)=>Promise<void>;onDisable:(script:Script)=>Promise<void>}) { return <><ScriptForm onSubmit={onAdd}/><Table rows={scripts} columns={["name","description","version"]} render={(script) => <State state={script.enabled ? "enabled" : "disabled"}/>} action={(script) => script.enabled ? <Button className="quiet" onClick={() => void onDisable(script)}>停用模板</Button> : null}/></>; }
function SyncPanel({user,hosts,scripts,selectedHosts,selectedScript,onToggle,onScript,onPreview,onCancel}:{user:User;hosts:Host[];scripts:Script[];selectedHosts:string[];selectedScript:string;onToggle:(id:string,checked:boolean)=>void;onScript:(id:string)=>void;onPreview:()=>Promise<void>;onCancel:()=>void}) { return <section className="panel sync"><h2>同步 {user.username}</h2><p>仅勾选本次需要变更的机器。预检不会变更目标机器，完成后仍需确认。</p>{hosts.map((host) => <label className={`check ${host.status === "reachable" ? "" : "blocked"}`} key={host.id}><input type="checkbox" disabled={host.status !== "reachable"} checked={selectedHosts.includes(host.id)} onChange={(event) => onToggle(host.id,event.target.checked)}/><span>{host.name} <small>{host.address}</small></span><State state={host.status}/>{host.status !== "reachable" && <small>{host.last_probe_error || "未通过 SSH 指纹或连通性检查"}</small>}</label>)}<label className="script-choice">后置脚本<select value={selectedScript} onChange={(event) => onScript(event.target.value)}><option value="">不执行后置脚本</option>{scripts.filter((script) => script.enabled).map((script) => <option key={script.id} value={script.id}>{script.name} · v{script.version}</option>)}</select></label><div><Button onClick={() => void onPreview()}>执行预检</Button><Button className="quiet" onClick={onCancel}>取消</Button></div></section>; }
function JobsView({jobs,activeJob,events,confirmed,onOpen,onConfirmed,onExecute,onRerun}:{jobs:Job[];activeJob:Job|null;events:JobEvent[];confirmed:boolean;onOpen:(job:Job)=>Promise<void>;onConfirmed:(value:boolean)=>void;onExecute:(job:Job,newPassword?:string)=>Promise<void>;onRerun:(job:Job)=>Promise<void>}) { return <><JobTable jobs={jobs} onOpen={onOpen}/>{activeJob && <JobDetail job={activeJob} events={events} confirmed={confirmed} onConfirmed={onConfirmed} onExecute={onExecute} onRerun={onRerun}/>}</>; }
function JobTable({jobs,onOpen}:{jobs:Job[];onOpen:(job:Job)=>Promise<void>}) { return <Table rows={jobs} columns={["id","created_at"]} render={(job) => <State state={job.state}/>} action={(job) => <Button className="quiet" onClick={() => void onOpen(job)}>查看</Button>}/>; }
function JobDetail({job,events,confirmed,onConfirmed,onExecute,onRerun}:{job:Job;events:JobEvent[];confirmed:boolean;onConfirmed:(value:boolean)=>void;onExecute:(job:Job,newPassword?:string)=>Promise<void>;onRerun:(job:Job)=>Promise<void>}) { const targets = job.targets ?? []; const [newPassword,setNewPassword] = useState(""); const operation = job.request_snapshot.operation as {action?:string;username?:string}|undefined; const needsPassword = job.kind === "host_user_operation" && operation?.action === "reset_password"; return <section className="panel job-detail"><div className="section-heading"><h2>任务详情</h2><State state={job.state}/></div>{job.script_snapshot && <p className="muted">后置脚本：{job.script_snapshot.name} · v{job.script_snapshot.version}</p>}{operation?.action && <p className="muted">受控操作：{operation.action}{operation.username ? ` · ${operation.username}` : ""}</p>}<Table rows={targets} columns={["host_name","state","output","error"]}/>{job.state === "ready_to_confirm" && <div className="confirm">{needsPassword && <label>新的系统密码<input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)}/></label>}<label><input type="checkbox" checked={confirmed} onChange={(event) => onConfirmed(event.target.checked)}/>我已确认以上变更</label><Button disabled={!confirmed || (needsPassword && !newPassword)} onClick={() => void onExecute(job,newPassword)}><CircleCheck size={14}/>确认并执行</Button></div>}{job.kind === "sync" && ["preview_failed","expired","succeeded","partial_failed"].includes(job.state) && <Button className="quiet" onClick={() => void onRerun(job)}><RotateCcw size={14}/>以相同输入重新预检</Button>}{events.length > 0 && <div className="log"><h3>实时日志</h3>{events.map((event) => <pre key={event.id} className={event.level === "error" ? "log-error" : ""}>{event.message}</pre>)}</div>}</section>; }
function InlineForm({title,fields,onSubmit}:{title:string;fields:string[];onSubmit:(values:Record<string,string>)=>Promise<void>}) { return <form className="panel inline" onSubmit={(event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget).entries()) as Record<string,string>; void onSubmit(data).then(() => event.currentTarget.reset()); }}><h2>{title}</h2><div>{fields.map((field) => { const [name,label] = field.split(":"); return <label key={name}>{label}<input name={name} required={!['tags','port','shell','home'].includes(name)}/></label>; })}<Button type="submit">保存</Button></div></form>; }
function ScriptForm({onSubmit}:{onSubmit:(values:Record<string,unknown>)=>Promise<void>}) { return <form className="panel inline" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); void onSubmit({name:data.get("name"),description:data.get("description"),body:data.get("body")}).then(() => event.currentTarget.reset()); }}><h2>新增后置脚本</h2><div><label>名称<input name="name" required/></label><label>说明<input name="description"/></label><label className="wide">脚本正文<textarea name="body" required rows={4}/></label><Button type="submit">保存模板</Button></div></form>; }
function Table({rows,columns,action,render}:{rows:any[];columns:string[];action?:(row:any)=>React.ReactNode;render?:(row:any)=>React.ReactNode}) { return <section className="table"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}{render && <th>状态</th>}{action && <th/>}</tr></thead><tbody>{rows.map((row,index) => <tr key={row.id || row.host_id || index}>{columns.map((column) => <td key={column}>{Array.isArray(row[column]) ? row[column].join(", ") : String(row[column] ?? "-")}</td>)}{render && <td>{render(row)}</td>}{action && <td>{action(row)}</td>}</tr>)}</tbody></table>{!rows.length && <p className="empty">暂无记录</p>}</section>; }
function State({state}:{state:string}) { return <span className={`badge state-${state}`}>{stateLabel[state] ?? state}</span>; }
