import { FormEvent, useEffect, useMemo, useState } from "react";
import { Activity, ChevronRight, CircleCheck, KeyRound, LayoutDashboard, MonitorCog, Play, RotateCcw, TerminalSquare, Users } from "lucide-react";

import { api, Host, Job, JobEvent, login, Script, User } from "./api";
import { Button } from "./components/ui/button";

type View = "overview" | "hosts" | "users" | "scripts" | "jobs";
const nav: {id:View; label:string; icon:typeof Activity}[] = [
  {id:"overview",label:"概览",icon:LayoutDashboard}, {id:"hosts",label:"机器",icon:MonitorCog},
  {id:"users",label:"用户与公钥",icon:Users}, {id:"scripts",label:"脚本模板",icon:TerminalSquare}, {id:"jobs",label:"执行记录",icon:Activity},
];
const runningStates = new Set(["pending", "preview_running", "running"]);
const stateLabel: Record<string, string> = { pending:"等待中", preview_running:"预检中", ready_to_confirm:"预检完成", preview_failed:"预检失败", running:"执行中", succeeded:"已完成", partial_failed:"部分失败", expired:"已过期", failed:"失败" };

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
  const execute = async (job: Job) => {
    const next = await api<Job>(`/jobs/${job.id}/execute`, {method:"POST"});
    setActiveJob(next); setJobs((current) => current.map((item) => item.id === next.id ? next : item)); setConfirmed(false);
  };
  const rerun = async (job: Job) => {
    const next = await api<Job>(`/jobs/${job.id}/rerun`, {method:"POST"});
    setJobs((current) => [next, ...current]); setActiveJob(next); setEvents([]); setConfirmed(false);
  };

  if (!authed) return <Login password={password} error={error} onPassword={setPassword} onLogin={async () => { try { await login(password); setAuthed(true); await load(); } catch (cause) { setError(cause instanceof Error ? cause.message : "登录失败"); } }} />;

  const content = view === "overview" ? <Overview hosts={hosts} users={users} jobs={jobs} onOpen={openJob} />
    : view === "hosts" ? <Hosts hosts={hosts} onAdd={async (form) => { await api<Host>("/hosts", {method:"POST",body:JSON.stringify(form)}); await load(); }} onTest={async (host) => { const result = await api<{requires_confirmation:boolean;fingerprint:string|null;error:string|null}>(`/hosts/${host.id}/test`, {method:"POST"}); if (result.requires_confirmation && result.fingerprint && window.confirm(`确认主机指纹？\n${result.fingerprint}`)) await api(`/hosts/${host.id}/confirm-fingerprint`, {method:"POST",body:JSON.stringify({fingerprint:result.fingerprint})}); if (result.error) setError(result.error); await load(); }} />
    : view === "users" ? <UsersView users={users} onAdd={async (form) => { await api<User>("/users", {method:"POST",body:JSON.stringify(form)}); await load(); }} onAddKey={async (user, key) => { await api(`/users/${user.id}/keys`, {method:"POST",body:JSON.stringify({public_key:key})}); }} onSync={(user) => { setSyncUser(user); setSelectedHosts([]); setSelectedScript(""); }} />
    : view === "scripts" ? <ScriptsView scripts={scripts} onAdd={async (form) => { await api<Script>("/script-templates", {method:"POST",body:JSON.stringify(form)}); await load(); }} />
    : <JobsView jobs={jobs} activeJob={activeJob} events={activeEvents} confirmed={confirmed} onOpen={openJob} onConfirmed={setConfirmed} onExecute={execute} onRerun={rerun} />;

  return <div className="layout"><aside><div className="brand"><KeyRound size={20}/><span>ACC/CTL</span></div>{nav.map((item) => { const Icon = item.icon; return <button key={item.id} className={view === item.id ? "nav active" : "nav"} onClick={() => setView(item.id)}><Icon size={17}/>{item.label}</button>; })}</aside><main className="workspace"><header><div><p className="eyebrow">单管理员 · 内网控制面</p><h1>{nav.find((item) => item.id === view)?.label}</h1></div><Button className="quiet" onClick={() => void load()}>刷新</Button></header>{error && <p className="error">{error}</p>}{content}{syncUser && <SyncPanel user={syncUser} hosts={hosts} scripts={scripts} selectedHosts={selectedHosts} selectedScript={selectedScript} onToggle={(id, checked) => setSelectedHosts((current) => checked ? [...current, id] : current.filter((value) => value !== id))} onScript={setSelectedScript} onPreview={preview} onCancel={() => setSyncUser(null)} />}</main></div>;
}

function Login({password,error,onPassword,onLogin}:{password:string;error:string;onPassword:(value:string)=>void;onLogin:()=>Promise<void>}) { return <main className="login"><section><p className="eyebrow">INTERNAL CONTROL PLANE</p><h1>账户管理控制台</h1><p>在确认前不改变任何机器。</p><form onSubmit={(event) => { event.preventDefault(); void onLogin(); }}><label>管理员密码<input autoFocus type="password" value={password} onChange={(event) => onPassword(event.target.value)}/></label><Button type="submit">进入控制台 <ChevronRight size={16}/></Button>{error && <small className="error">{error}</small>}</form></section></main>; }
function Overview({hosts,users,jobs,onOpen}:{hosts:Host[];users:User[];jobs:Job[];onOpen:(job:Job)=>Promise<void>}) { return <><div className="metrics"><Metric label="机器" value={hosts.length}/><Metric label="可连接" value={hosts.filter((host) => host.status === "reachable").length}/><Metric label="用户" value={users.length}/><Metric label="任务" value={jobs.length}/></div><section className="panel"><h2>最近任务</h2><JobTable jobs={jobs.slice(0,6)} onOpen={onOpen}/></section></>; }
function Metric({label,value}:{label:string;value:number}) { return <section className="metric"><span>{label}</span><strong>{value}</strong></section>; }
function Hosts({hosts,onAdd,onTest}:{hosts:Host[];onAdd:(value:Record<string,unknown>)=>Promise<void>;onTest:(host:Host)=>Promise<void>}) { return <><InlineForm title="接入机器" fields={["name:名称","address:IP 或 FQDN","port:端口","ssh_user:SSH 用户","tags:标签，逗号分隔"]} onSubmit={async (form) => onAdd({name:form.name,address:form.address,port:Number(form.port || 22),ssh_user:form.ssh_user || "root",tags:(form.tags || "").split(",")})}/><Table rows={hosts} columns={["name","address","ssh_user","tags"]} render={(host) => <><State state={host.status}/>{host.last_probe_error && <small className="muted">{host.last_probe_error}</small>}</>} action={(host) => <Button onClick={() => void onTest(host)}>测试连接</Button>}/></>; }
function UsersView({users,onAdd,onAddKey,onSync}:{users:User[];onAdd:(value:Record<string,unknown>)=>Promise<void>;onAddKey:(user:User,key:string)=>Promise<void>;onSync:(user:User)=>void}) { const [keyUser,setKeyUser] = useState<User|null>(null); const [key,setKey] = useState(""); return <><InlineForm title="创建 Linux 用户" fields={["username:用户名","display_name:显示名","shell:登录 Shell","home:家目录"]} onSubmit={async (form) => onAdd({username:form.username,display_name:form.display_name,shell:form.shell || "/bin/bash",home:form.home || undefined})}/><Table rows={users} columns={["username","display_name","shell","home"]} render={(user) => <State state={user.enabled ? "enabled" : "disabled"}/>} action={(user) => <><Button className="quiet" onClick={() => { setKeyUser(user); setKey(""); }}><KeyRound size={14}/>公钥</Button><Button disabled={!user.enabled} onClick={() => onSync(user)}><Play size={14}/>同步</Button></>}/>{keyUser && <section className="panel key-panel"><h2>{keyUser.username} 的 SSH 公钥</h2><label>SSH 公钥<textarea value={key} onChange={(event) => setKey(event.target.value)} rows={3}/></label><div><Button disabled={!key.trim()} onClick={async () => { await onAddKey(keyUser, key); setKey(""); }}>添加公钥</Button><Button className="quiet" onClick={() => setKeyUser(null)}>关闭</Button></div></section>}</>; }
function ScriptsView({scripts,onAdd}:{scripts:Script[];onAdd:(value:Record<string,unknown>)=>Promise<void>}) { return <><ScriptForm onSubmit={onAdd}/><Table rows={scripts} columns={["name","description","version"]} render={(script) => <State state={script.enabled ? "enabled" : "disabled"}/>}/></>; }
function SyncPanel({user,hosts,scripts,selectedHosts,selectedScript,onToggle,onScript,onPreview,onCancel}:{user:User;hosts:Host[];scripts:Script[];selectedHosts:string[];selectedScript:string;onToggle:(id:string,checked:boolean)=>void;onScript:(id:string)=>void;onPreview:()=>Promise<void>;onCancel:()=>void}) { return <section className="panel sync"><h2>同步 {user.username}</h2><p>仅勾选本次需要变更的机器。预检不会变更目标机器，完成后仍需确认。</p>{hosts.map((host) => <label className={`check ${host.status === "reachable" ? "" : "blocked"}`} key={host.id}><input type="checkbox" disabled={host.status !== "reachable"} checked={selectedHosts.includes(host.id)} onChange={(event) => onToggle(host.id,event.target.checked)}/><span>{host.name} <small>{host.address}</small></span><State state={host.status}/>{host.status !== "reachable" && <small>{host.last_probe_error || "未通过 SSH 指纹或连通性检查"}</small>}</label>)}<label className="script-choice">后置脚本<select value={selectedScript} onChange={(event) => onScript(event.target.value)}><option value="">不执行后置脚本</option>{scripts.filter((script) => script.enabled).map((script) => <option key={script.id} value={script.id}>{script.name} · v{script.version}</option>)}</select></label><div><Button onClick={() => void onPreview()}>执行预检</Button><Button className="quiet" onClick={onCancel}>取消</Button></div></section>; }
function JobsView({jobs,activeJob,events,confirmed,onOpen,onConfirmed,onExecute,onRerun}:{jobs:Job[];activeJob:Job|null;events:JobEvent[];confirmed:boolean;onOpen:(job:Job)=>Promise<void>;onConfirmed:(value:boolean)=>void;onExecute:(job:Job)=>Promise<void>;onRerun:(job:Job)=>Promise<void>}) { return <><JobTable jobs={jobs} onOpen={onOpen}/>{activeJob && <JobDetail job={activeJob} events={events} confirmed={confirmed} onConfirmed={onConfirmed} onExecute={onExecute} onRerun={onRerun}/>}</>; }
function JobTable({jobs,onOpen}:{jobs:Job[];onOpen:(job:Job)=>Promise<void>}) { return <Table rows={jobs} columns={["id","created_at"]} render={(job) => <State state={job.state}/>} action={(job) => <Button className="quiet" onClick={() => void onOpen(job)}>查看</Button>}/>; }
function JobDetail({job,events,confirmed,onConfirmed,onExecute,onRerun}:{job:Job;events:JobEvent[];confirmed:boolean;onConfirmed:(value:boolean)=>void;onExecute:(job:Job)=>Promise<void>;onRerun:(job:Job)=>Promise<void>}) { const targets = job.targets ?? []; return <section className="panel job-detail"><div className="section-heading"><h2>任务详情</h2><State state={job.state}/></div>{job.script_snapshot && <p className="muted">后置脚本：{job.script_snapshot.name} · v{job.script_snapshot.version}</p>}<Table rows={targets} columns={["host_name","state","output","error"]}/>{job.state === "ready_to_confirm" && <div className="confirm"><label><input type="checkbox" checked={confirmed} onChange={(event) => onConfirmed(event.target.checked)}/>我已确认以上变更</label><Button disabled={!confirmed} onClick={() => void onExecute(job)}><CircleCheck size={14}/>确认并执行</Button></div>}{["preview_failed","expired","succeeded","partial_failed"].includes(job.state) && <Button className="quiet" onClick={() => void onRerun(job)}><RotateCcw size={14}/>以相同输入重新预检</Button>}{events.length > 0 && <div className="log"><h3>实时日志</h3>{events.map((event) => <pre key={event.id} className={event.level === "error" ? "log-error" : ""}>{event.message}</pre>)}</div>}</section>; }
function InlineForm({title,fields,onSubmit}:{title:string;fields:string[];onSubmit:(values:Record<string,string>)=>Promise<void>}) { return <form className="panel inline" onSubmit={(event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget).entries()) as Record<string,string>; void onSubmit(data).then(() => event.currentTarget.reset()); }}><h2>{title}</h2><div>{fields.map((field) => { const [name,label] = field.split(":"); return <label key={name}>{label}<input name={name} required={!['tags','port','shell','home'].includes(name)}/></label>; })}<Button type="submit">保存</Button></div></form>; }
function ScriptForm({onSubmit}:{onSubmit:(values:Record<string,unknown>)=>Promise<void>}) { return <form className="panel inline" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); void onSubmit({name:data.get("name"),description:data.get("description"),body:data.get("body")}).then(() => event.currentTarget.reset()); }}><h2>新增后置脚本</h2><div><label>名称<input name="name" required/></label><label>说明<input name="description"/></label><label className="wide">脚本正文<textarea name="body" required rows={4}/></label><Button type="submit">保存模板</Button></div></form>; }
function Table({rows,columns,action,render}:{rows:any[];columns:string[];action?:(row:any)=>React.ReactNode;render?:(row:any)=>React.ReactNode}) { return <section className="table"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}{render && <th>状态</th>}{action && <th/>}</tr></thead><tbody>{rows.map((row,index) => <tr key={row.id || row.host_id || index}>{columns.map((column) => <td key={column}>{Array.isArray(row[column]) ? row[column].join(", ") : String(row[column] ?? "-")}</td>)}{render && <td>{render(row)}</td>}{action && <td>{action(row)}</td>}</tr>)}</tbody></table>{!rows.length && <p className="empty">暂无记录</p>}</section>; }
function State({state}:{state:string}) { return <span className={`badge state-${state}`}>{stateLabel[state] ?? state}</span>; }
