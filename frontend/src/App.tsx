import { Fragment, useEffect, useState } from "react";
import { Activity, CheckCircle2, ChevronRight, Database, KeyRound, MonitorCog, Plus, RefreshCw, Settings2, ShieldCheck, Users } from "lucide-react";

import { AccessGrant, api, Host, HostUser, Job, login, PermissionTemplate, SshKey, User } from "./api";
import { CommandReview } from "./CommandReview";
import { Button } from "./components/ui/button";

type View = "members" | "machines" | "templates" | "jobs";
type GrantRow = { selected:boolean; username:string; accountOrigin:"created"|"adopted"; permissionTemplateId:string; groupsOverride:string; sudoRuleOverride:string; advanced:boolean; inventory:HostUser[]; inventoryLoading:boolean; inventoryLoaded:boolean };
type ProvisionRow =
  | { host_id:string; username:string; account_origin:"created"; permission_template_id:string|null; groups_override:string[]|null; sudo_rule_override:string|null }
  | { host_id:string; username:string; account_origin:"adopted"; existing_account:{ uid:number; primary_group:string; home:string; public_key_fingerprints:string[] } };

const stateLabel: Record<string, string> = {
  reachable: "可连接", unreachable: "不可连接", unconfirmed: "待确认", fingerprint_changed: "指纹变化",
  pending: "未检测", preview_running: "预检中", ready_to_confirm: "等待确认", preview_failed: "预检失败",
  running: "执行中", succeeded: "已完成", partial_failed: "部分失败", active: "已开通", revoked: "已回收",
};

const nav: { id:View; label:string; icon:typeof Users }[] = [
  { id:"members", label:"成员与开通", icon:Users }, { id:"machines", label:"机器", icon:MonitorCog },
  { id:"templates", label:"权限模板", icon:ShieldCheck }, { id:"jobs", label:"执行记录", icon:Activity },
];

export function App() {
  const [authed, setAuthed] = useState(false);
  const [password, setPassword] = useState("");
  const [view, setView] = useState<View>("members");
  const [error, setError] = useState("");
  const [hosts, setHosts] = useState<Host[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [templates, setTemplates] = useState<PermissionTemplate[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedUserId, setSelectedUserId] = useState("");

  const load = async () => {
    try {
      const [nextHosts, nextUsers, nextTemplates, nextJobs] = await Promise.all([
        api<Host[]>("/hosts"), api<User[]>("/users"), api<PermissionTemplate[]>("/permission-templates"), api<Job[]>("/jobs"),
      ]);
      setHosts(nextHosts); setUsers(nextUsers); setTemplates(nextTemplates); setJobs(nextJobs); setError("");
      setSelectedUserId((current) => current || nextUsers.find((user) => user.enabled)?.id || "");
    } catch (cause) { setError(message(cause, "加载控制台失败")); }
  };

  useEffect(() => { void fetch("/api/auth/me", { credentials:"include" }).then((response) => { if (response.ok) { setAuthed(true); void load(); } }); }, []);
  useEffect(() => {
    if (!authed || !jobs.some((job) => ["preview_running", "running"].includes(job.state))) return;
    const timer = window.setInterval(() => void load(), 1300);
    return () => window.clearInterval(timer);
  }, [authed, jobs]);

  if (!authed) return <Login password={password} error={error} onPassword={setPassword} onLogin={async () => { try { await login(password); setAuthed(true); await load(); } catch (cause) { setError(message(cause, "登录失败")); } }} />;

  const selectedUser = users.find((user) => user.id === selectedUserId) ?? null;
  const executeReadyJob = async (job: Job) => {
    const endpoint = job.kind.startsWith("access_grant_") ? `/access-grant-jobs/${job.id}/execute` : `/jobs/${job.id}/execute`;
    try {
      const next = await api<Job>(endpoint, { method:"POST" });
      setJobs((current) => current.map((item) => item.id === next.id ? next : item));
    } catch (cause) { setError(message(cause, "执行任务失败")); }
  };
  const content = view === "members" ? <MembersView users={users} selectedUser={selectedUser} hosts={hosts} templates={templates} onSelect={setSelectedUserId} onCreated={async (payload) => { const user = await api<User>("/users", { method:"POST", body:JSON.stringify(payload) }); await load(); setSelectedUserId(user.id); }} onError={setError} onJob={(job) => { setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]); }} />
    : view === "machines" ? <MachinesView hosts={hosts} onError={setError} onChanged={load} />
    : view === "templates" ? <TemplatesView templates={templates} onChanged={load} onError={setError} />
    : <JobsView jobs={jobs} onExecute={executeReadyJob} />;

  return <div className="shell"><aside className="sidebar"><div className="brand"><KeyRound size={19}/><span>TRAIN/ACCESS</span></div><nav>{nav.map((item) => { const Icon = item.icon; return <button key={item.id} className={view === item.id ? "nav-item current" : "nav-item"} onClick={() => setView(item.id)}><Icon size={17}/>{item.label}</button>; })}</nav><div className="sidebar-foot"><span className="pulse"/>内网控制面</div></aside><main className="workspace"><header className="topbar"><div><p className="eyebrow">ACCESS CONTROL / INTERNAL</p><h1>{nav.find((item) => item.id === view)?.label}</h1></div><Button className="icon-button" title="刷新数据" onClick={() => void load()}><RefreshCw size={17}/></Button></header>{error && <p className="notice error">{error}</p>}{content}</main></div>;
}

function MembersView({ users, selectedUser, hosts, templates, onSelect, onCreated, onError, onJob }:{ users:User[]; selectedUser:User|null; hosts:Host[]; templates:PermissionTemplate[]; onSelect:(id:string)=>void; onCreated:(payload:Record<string,string>)=>Promise<void>; onError:(value:string)=>void; onJob:(job:Job)=>void }) {
  const [createOpen, setCreateOpen] = useState(false);
  return <div className="member-layout"><section className="roster"><div className="roster-head"><div><span className="section-kicker">团队成员</span><strong>{users.filter((user) => user.enabled).length}</strong></div><Button className="icon-button" title="新建成员" onClick={() => setCreateOpen(true)}><Plus size={17}/></Button></div>{createOpen && <MemberCreate onCancel={() => setCreateOpen(false)} onSubmit={async (payload) => { await onCreated(payload); setCreateOpen(false); }}/>}<div className="member-list">{users.filter((user) => user.enabled).map((user) => <button key={user.id} className={selectedUser?.id === user.id ? "member-row selected" : "member-row"} onClick={() => onSelect(user.id)}><span className="avatar">{(user.display_name || user.username).slice(0, 1).toUpperCase()}</span><span><b>{user.display_name || user.username}</b><small>{user.username}</small></span><ChevronRight size={15}/></button>)}</div></section><section className="member-canvas">{selectedUser ? <MemberWorkbench key={selectedUser.id} user={selectedUser} hosts={hosts} templates={templates} onError={onError} onJob={onJob}/> : <EmptyState/>}</section></div>;
}

function MemberCreate({ onCancel, onSubmit }:{ onCancel:()=>void; onSubmit:(payload:Record<string,string>)=>Promise<void> }) {
  const [username, setUsername] = useState(""); const [displayName, setDisplayName] = useState("");
  return <form className="mini-form" onSubmit={(event) => { event.preventDefault(); void onSubmit({ username, display_name:displayName }); }}><input aria-label="新成员用户名" placeholder="Linux 默认用户名" value={username} onChange={(event) => setUsername(event.target.value)}/><input aria-label="新成员姓名" placeholder="姓名" value={displayName} onChange={(event) => setDisplayName(event.target.value)}/><div><Button type="submit">创建</Button><Button type="button" className="text-button" onClick={onCancel}>取消</Button></div></form>;
}

function MemberWorkbench({ user, hosts, templates, onError, onJob }:{ user:User; hosts:Host[]; templates:PermissionTemplate[]; onError:(value:string)=>void; onJob:(job:Job)=>void }) {
  const [keys, setKeys] = useState<SshKey[]>([]);
  const [grants, setGrants] = useState<AccessGrant[]>([]);
  const [keyText, setKeyText] = useState("");
  const [rows, setRows] = useState<Record<string, GrantRow>>({});
  const [preparedJob, setPreparedJob] = useState<Job|null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const defaultTemplate = templates.find((template) => template.enabled)?.id || "";
  const loadDetail = async () => {
    try {
      const [nextKeys, nextGrants] = await Promise.all([api<SshKey[]>(`/users/${user.id}/keys`), api<AccessGrant[]>(`/users/${user.id}/access-grants`)]);
      setKeys(nextKeys);
      setGrants(nextGrants);
      setRows((current) => Object.fromEntries(hosts.map((host) => [host.id, current[host.id] || {
        selected:false, username:user.username, accountOrigin:"created", permissionTemplateId:defaultTemplate,
        groupsOverride:"", sudoRuleOverride:"", advanced:false, inventory:[], inventoryLoading:false, inventoryLoaded:false,
      }])));
    } catch (cause) { onError(message(cause, "无法读取成员授权信息")); }
  };
  useEffect(() => { void loadDetail(); }, [user.id, hosts.length, templates.length]);
  useEffect(() => {
    if (preparedJob?.state !== "preview_running") return;
    let disposed = false;
    const refresh = () => void api<Job>(`/jobs/${preparedJob.id}`).then((job) => {
      if (!disposed) { setPreparedJob(job); onJob(job); }
    }).catch((cause) => !disposed && onError(message(cause, "无法读取预检状态")));
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [preparedJob?.id, preparedJob?.state, onError, onJob]);
  const changeRow = (hostId:string, update:Partial<GrantRow>) => setRows((current) => ({ ...current, [hostId]:{ ...current[hostId], ...update } }));
  const chooseOrigin = async (host:Host, accountOrigin:"created"|"adopted") => {
    changeRow(host.id, { accountOrigin, selected:false, advanced:false, username:accountOrigin === "created" ? user.username : rows[host.id].username });
    if (accountOrigin === "created" || rows[host.id].inventoryLoaded || rows[host.id].inventoryLoading) return;
    changeRow(host.id, { inventoryLoading:true });
    try {
      const inventory = await api<HostUser[]>(`/hosts/${host.id}/users`);
      const first = inventory[0];
      const firstKeys = first ? await api<HostUser["public_keys"]>(`/hosts/${host.id}/users/${first.username}/keys`) : [];
      const inventoryWithKeys = first ? inventory.map((account) => account.username === first.username ? { ...account, public_keys:firstKeys } : account) : inventory;
      changeRow(host.id, { inventory:inventoryWithKeys, inventoryLoaded:true, inventoryLoading:false, username:first?.username || "" });
    } catch (cause) {
      changeRow(host.id, { inventoryLoading:false });
      onError(message(cause, `无法盘点 ${host.name} 的已有账号`));
    }
  };
  const chooseExistingAccount = async (host:Host, username:string) => {
    changeRow(host.id, { username });
    if (!username) return;
    try {
      const publicKeys = await api<HostUser["public_keys"]>(`/hosts/${host.id}/users/${username}/keys`);
      setRows((current) => ({
        ...current,
        [host.id]:{
          ...current[host.id],
          inventory:current[host.id].inventory.map((account) => account.username === username ? { ...account, public_keys:publicKeys } : account),
        },
      }));
    } catch (cause) { onError(message(cause, `无法读取 ${host.name} 上 ${username} 的公钥`)); }
  };
  const provisionRows = hosts.filter((host) => rows[host.id]?.selected).map((host):ProvisionRow|null => {
    const row = rows[host.id];
    if (row.accountOrigin === "adopted") {
      const existing = row.inventory.find((account) => account.username === row.username);
      return existing ? { host_id:host.id, username:existing.username, account_origin:"adopted", existing_account:{ uid:existing.uid, primary_group:existing.primary_group, home:existing.home, public_key_fingerprints:existing.public_keys.map((key) => key.fingerprint) } } : null;
    }
    return {
      host_id:host.id, username:row.username, account_origin:"created",
      permission_template_id:row.permissionTemplateId || null,
      groups_override:row.groupsOverride ? row.groupsOverride.split(",").map((value) => value.trim()).filter(Boolean) : null,
      sudo_rule_override:row.sudoRuleOverride || null,
    };
  }).filter((row):row is ProvisionRow => row !== null);
  const preview = async () => {
    const selectedRows = hosts.filter((host) => rows[host.id]?.selected);
    if (!selectedRows.length) { onError("请至少勾选一台机器"); return; }
    if (selectedRows.some((host) => rows[host.id].accountOrigin === "adopted" && !rows[host.id].inventory.some((account) => account.username === rows[host.id].username))) { onError("请为纳管机器选择已有账号"); return; }
    try {
      const job = await api<Job>(`/users/${user.id}/access-grants/preview`, { method:"POST", body:JSON.stringify({ grants:provisionRows }) });
      setPreparedJob(job); setConfirmed(false); onJob(job);
    } catch (cause) { onError(message(cause, "开通预检失败")); }
  };
  const execute = async () => { if (!preparedJob) return; try { const job = await api<Job>(`/access-grant-jobs/${preparedJob.id}/execute`, { method:"POST" }); setPreparedJob(job); setConfirmed(false); onJob(job); } catch (cause) { onError(message(cause, "执行开通失败")); } };
  const activeGrants = grants.filter((grant) => grant.state === "active");
  return <>
    <section className="member-summary"><div><span className="section-kicker">成员档案</span><h2>{user.display_name || user.username}</h2><p>{user.username} · 密钥登录</p></div><div className="summary-count"><b>{activeGrants.length}</b><span>已开通机器</span></div></section>
    <section className="key-strip"><div><h3>SSH 公钥</h3><p>{keys.length ? `${keys.length} 把启用公钥` : "还没有启用公钥，不能开通"}</p></div><details><summary>管理公钥</summary><div className="key-management">{keys.map((key) => <code key={key.id}>{key.fingerprint} {key.comment}</code>)}<form onSubmit={(event) => { event.preventDefault(); void api<SshKey>(`/users/${user.id}/keys`, { method:"POST", body:JSON.stringify({ public_key:keyText }) }).then(() => { setKeyText(""); void loadDetail(); }).catch((cause) => onError(message(cause, "保存公钥失败"))); }}><textarea aria-label="SSH 公钥内容" placeholder="ssh-ed25519 AAAA..." value={keyText} onChange={(event) => setKeyText(event.target.value)}/><Button type="submit" disabled={!keyText.trim()}>添加公钥</Button></form></div></details></section>
    <section className="workbench">
      <div className="workbench-heading"><div><span className="section-kicker">批量开通</span><h3>选择机器与账号方式</h3></div><Button disabled={!keys.length} onClick={() => void preview()}>预检开通 <ChevronRight size={16}/></Button></div>
      <div className="grant-table"><table><thead><tr><th>机器</th><th>账号</th><th>权限与位置</th></tr></thead><tbody>{hosts.map((host) => {
        const row = rows[host.id]; if (!row) return null;
        const reachable = host.status === "reachable";
        const eligible = reachable && (row.accountOrigin === "adopted" || Boolean(host.data_root));
        const template = templates.find((item) => item.id === row.permissionTemplateId);
        const existing = row.inventory.find((account) => account.username === row.username);
        return <Fragment key={host.id}>
          <tr className={!eligible ? "blocked" : ""}>
            <td><div className="host-machine"><label className="host-select"><input aria-label={`选择 ${host.name}`} type="checkbox" checked={row.selected} disabled={!eligible || (row.accountOrigin === "adopted" && !existing)} onChange={(event) => changeRow(host.id, { selected:event.target.checked })}/><span><b>{host.name}</b><small>{host.address} · {host.tags.join(" / ") || "未标记"}</small></span></label><State state={eligible ? host.status : "unconfigured"}/></div></td>
            <td><div className="account-cell"><div className="mode-switch"><button className={row.accountOrigin === "created" ? "active" : ""} aria-pressed={row.accountOrigin === "created"} onClick={() => void chooseOrigin(host, "created")}>创建新账号</button><button className={row.accountOrigin === "adopted" ? "active" : ""} aria-pressed={row.accountOrigin === "adopted"} disabled={!reachable} onClick={() => void chooseOrigin(host, "adopted")}>纳管已有账号</button></div>{row.accountOrigin === "created" ? <input aria-label={`${host.name} 用户名`} value={row.username} disabled={!eligible} onChange={(event) => changeRow(host.id, { username:event.target.value })}/> : <div className="existing-account"><select aria-label={`${host.name} 已有账号`} value={row.username} disabled={row.inventoryLoading} onChange={(event) => void chooseExistingAccount(host, event.target.value)}><option value="">{row.inventoryLoading ? "正在盘点..." : "选择已有账号"}</option>{row.inventory.map((account) => <option key={account.username} value={account.username}>{account.username}</option>)}</select>{existing && <small>UID {existing.uid} · {existing.primary_group} · {existing.home} · {existing.public_keys.length} 把现有密钥</small>}</div>}</div></td>
            <td>{row.accountOrigin === "created" ? <><select aria-label={`${host.name} 权限模板`} value={row.permissionTemplateId} disabled={!eligible} onChange={(event) => changeRow(host.id, { permissionTemplateId:event.target.value })}><option value="">自定义最小权限</option>{templates.filter((item) => item.enabled).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className="row-link" onClick={() => changeRow(host.id, { advanced:!row.advanced })}>覆盖</button><code className="path-preview">{host.data_root ? `${host.data_root}/${row.username || "用户名"}` : "先配置数据根目录"}</code></> : <><b>保留现有权限</b><small>不迁移 home，不修改组和 sudo</small></>}</td>
          </tr>
          {row.accountOrigin === "created" && row.advanced && <tr className="advanced-row"><td colSpan={3}><label>附加组<input placeholder={template?.groups.join(",") || "例如 docker"} value={row.groupsOverride} onChange={(event) => changeRow(host.id, { groupsOverride:event.target.value })}/></label><label>sudo 规则<input placeholder={template?.sudo_rule || "留空表示不授予 sudo"} value={row.sudoRuleOverride} onChange={(event) => changeRow(host.id, { sudoRuleOverride:event.target.value })}/></label></td></tr>}
        </Fragment>;
      })}</tbody></table></div>
      {preparedJob && preparedJob.state !== "ready_to_confirm" && <section className="prepared"><div><State state={preparedJob.state}/><strong>正在生成预检</strong><span>完成后将在这里展示逐机命令。</span></div></section>}
      {preparedJob?.state === "ready_to_confirm" && (
        <CommandReview job={preparedJob} confirmed={confirmed} executeLabel="确认并开通" onConfirmed={setConfirmed} onExecute={() => void execute()}/>
      )}
    </section>
    <GrantList userId={user.id} grants={activeGrants} onError={onError} onJob={onJob}/>
  </>;
}

function GrantList({ userId, grants, onError, onJob }:{ userId:string; grants:AccessGrant[]; onError:(value:string)=>void; onJob:(job:Job)=>void }) {
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [deleteData, setDeleteData] = useState<Record<string, boolean>>({});
  const [prepared, setPrepared] = useState<Job|null>(null);
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => {
    if (prepared?.state !== "preview_running") return;
    let disposed = false;
    const refresh = () => void api<Job>(`/jobs/${prepared.id}`).then((job) => {
      if (!disposed) { setPrepared(job); onJob(job); }
    }).catch((cause) => !disposed && onError(message(cause, "无法读取回收预检状态")));
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [prepared?.id, prepared?.state, onError, onJob]);
  const preview = async () => {
    const rows = grants.filter((grant) => selected[grant.id]).map((grant) => ({ grant_id:grant.id, delete_data:grant.account_origin === "created" && Boolean(deleteData[grant.id]) }));
    if (!rows.length) { onError("请先勾选要回收的机器权限"); return; }
    try { const job = await api<Job>(`/users/${userId}/access-grants/revoke/preview`, { method:"POST", body:JSON.stringify({ grants:rows }) }); setPrepared(job); setConfirmed(false); onJob(job); } catch (cause) { onError(message(cause, "回收预检失败")); }
  };
  const execute = async () => { if (!prepared) return; try { const job = await api<Job>(`/access-grant-jobs/${prepared.id}/execute`, { method:"POST" }); setPrepared(job); setConfirmed(false); onJob(job); } catch (cause) { onError(message(cause, "执行回收失败")); } };
  return <section className="existing-grants">
    <div className="workbench-heading"><div><span className="section-kicker">已开通</span><h3>机器权限</h3></div>{grants.length > 0 && <Button className="text-button" onClick={() => void preview()}>预检回收</Button>}</div>
    {grants.length ? <div className="grant-chips">{grants.map((grant) => <div key={grant.id} className={selected[grant.id] ? "revoke-selected" : ""}>
      <label><input aria-label={`回收 ${grant.host_name}`} type="checkbox" checked={Boolean(selected[grant.id])} onChange={(event) => setSelected({ ...selected, [grant.id]:event.target.checked })}/><b>{grant.host_name}</b></label>
      <span>{grant.username} · {grant.account_origin === "adopted" ? "已有账号纳管" : "平台创建"}</span>
      <code>{grant.account_origin === "adopted" ? grant.remote_home : grant.data_directory}</code>
      {grant.account_origin === "created" ? <label className="delete-data"><input aria-label={`删除 ${grant.host_name} 数据目录`} type="checkbox" checked={Boolean(deleteData[grant.id])} onChange={(event) => setDeleteData({ ...deleteData, [grant.id]:event.target.checked })}/>删除数据目录</label> : <small>回收时移除平台密钥并锁定账号</small>}
      <State state={grant.state}/>
    </div>)}</div> : <p className="empty-inline">还没有机器权限。</p>}
    {prepared && prepared.state !== "ready_to_confirm" && <section className="prepared"><div><State state={prepared.state}/><strong>正在生成回收预检</strong></div></section>}
    {prepared?.state === "ready_to_confirm" && (
      <CommandReview job={prepared} confirmed={confirmed} executeLabel="确认并回收" onConfirmed={setConfirmed} onExecute={() => void execute()}/>
    )}
  </section>;
}

function MachinesView({ hosts, onChanged, onError }:{ hosts:Host[]; onChanged:()=>Promise<void>; onError:(value:string)=>void }) { const [form, setForm] = useState({ name:"", address:"", ssh_user:"root", data_root:"" }); return <><section className="machine-intro"><Database size={22}/><div><span className="section-kicker">基础设施配置</span><h2>机器只需配置一次连接与数据根目录</h2><p>开通时将自动使用此机器自己的根目录，创建成员专属数据目录和 `/home` 软链接。</p></div></section><section className="machine-table"><table><thead><tr><th>机器</th><th>管理连接</th><th>数据根目录</th><th>状态</th><th/></tr></thead><tbody>{hosts.map((host) => <MachineRow key={host.id} host={host} onChanged={onChanged} onError={onError}/>)}</tbody></table></section><form className="add-machine" onSubmit={(event) => { event.preventDefault(); void api<Host>("/hosts", { method:"POST", body:JSON.stringify({ ...form, port:22, tags:[] }) }).then(onChanged).catch((cause) => onError(message(cause, "添加机器失败"))); }}><span className="section-kicker">接入机器</span><input placeholder="名称" value={form.name} onChange={(event) => setForm({ ...form, name:event.target.value })}/><input placeholder="IP 或 FQDN" value={form.address} onChange={(event) => setForm({ ...form, address:event.target.value })}/><input placeholder="管理 SSH 用户" value={form.ssh_user} onChange={(event) => setForm({ ...form, ssh_user:event.target.value })}/><input placeholder="数据根目录，例如 /mnt/train" value={form.data_root} onChange={(event) => setForm({ ...form, data_root:event.target.value })}/><Button type="submit">添加机器</Button></form></>; }

function MachineRow({ host, onChanged, onError }:{ host:Host; onChanged:()=>Promise<void>; onError:(value:string)=>void }) {
  const [dataRoot, setDataRoot] = useState(host.data_root || ""); const [privateKey, setPrivateKey] = useState<File|null>(null); const [sudoPassword, setSudoPassword] = useState("");
  const saveCredential = async () => { if (!privateKey || !sudoPassword) { onError("请选择管理私钥并填写 sudo 密码"); return; } const form = new FormData(); form.set("private_key_file", privateKey); form.set("sudo_password", sudoPassword); try { await api(`/hosts/${host.id}/credentials`, { method:"PUT", body:form }); setPrivateKey(null); setSudoPassword(""); } catch (cause) { onError(message(cause, "保存连接凭据失败")); } };
  return <tr><td><b>{host.name}</b><small>{host.tags.join(" / ") || "未标记"}</small></td><td>{host.ssh_user}@{host.address}:{host.port}<details className="connection-settings"><summary>连接设置</summary><div><label>管理私钥<input aria-label={`${host.name} 管理私钥`} type="file" onChange={(event) => setPrivateKey(event.target.files?.[0] || null)}/></label><label>sudo 密码<input aria-label={`${host.name} sudo 密码`} type="password" value={sudoPassword} onChange={(event) => setSudoPassword(event.target.value)}/></label><Button type="button" onClick={() => void saveCredential()}>保存连接凭据</Button></div></details></td><td><div className="root-editor"><input aria-label={`${host.name} 数据根目录`} placeholder="未配置" value={dataRoot} onChange={(event) => setDataRoot(event.target.value)}/><Button className="icon-button" title="保存数据根目录" onClick={() => void api<Host>(`/hosts/${host.id}`, { method:"PATCH", body:JSON.stringify({ data_root:dataRoot || null }) }).then(onChanged).catch((cause) => onError(message(cause, "保存机器配置失败")))}><Settings2 size={15}/></Button></div></td><td><State state={host.status}/></td><td><span className={host.data_root ? "machine-ready" : "machine-missing"}>{host.data_root ? "可开通" : "缺少数据根目录"}</span></td></tr>;
}

function TemplatesView({ templates, onChanged, onError }:{ templates:PermissionTemplate[]; onChanged:()=>Promise<void>; onError:(value:string)=>void }) { const [name, setName] = useState(""); const [groups, setGroups] = useState(""); const [sudo, setSudo] = useState(""); return <><section className="template-grid">{templates.map((template) => <article key={template.id}><span className="section-kicker">{template.enabled ? "启用" : "停用"}</span><h2>{template.name}</h2><p>{template.description || "无说明"}</p><div>{template.groups.map((group) => <code key={group}>{group}</code>) || <span>无附加组</span>}</div><small>{template.sudo_rule || "不授予 sudo"}</small></article>)}</section><form className="template-create" onSubmit={(event) => { event.preventDefault(); void api<PermissionTemplate>("/permission-templates", { method:"POST", body:JSON.stringify({ name, groups:groups.split(",").map((value) => value.trim()).filter(Boolean), sudo_rule:sudo || null }) }).then(() => { setName(""); setGroups(""); setSudo(""); return onChanged(); }).catch((cause) => onError(message(cause, "创建权限模板失败"))); }}><span className="section-kicker">新权限模板</span><input placeholder="名称" value={name} onChange={(event) => setName(event.target.value)}/><input placeholder="附加组，以逗号分隔" value={groups} onChange={(event) => setGroups(event.target.value)}/><input placeholder="sudo 规则（可选）" value={sudo} onChange={(event) => setSudo(event.target.value)}/><Button type="submit">创建模板</Button></form></>; }

function JobsView({ jobs, onExecute }:{ jobs:Job[]; onExecute:(job:Job)=>Promise<void> }) {
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const command = (job:Job) => job.kind === "access_grant_provision" ? "确认并开通" : job.kind === "access_grant_revoke" ? "确认并回收" : "确认并执行";
  const readyJobs = jobs.filter((job) => job.state === "ready_to_confirm" && job.kind.startsWith("access_grant_"));
  return <>
    <section className="jobs-table"><table><thead><tr><th>批次</th><th>创建时间</th><th>目标机器</th><th>状态</th><th>操作</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td><b>{job.kind === "access_grant_provision" ? "批量开通" : job.kind === "access_grant_revoke" ? "批量回收" : job.kind}</b><small>{job.id}</small></td><td>{new Date(job.created_at).toLocaleString()}</td><td>{job.targets?.map((target) => target.host_name).join(" / ") || "-"}</td><td><State state={job.state}/></td><td>{job.state === "ready_to_confirm" ? "查看下方命令" : "-"}</td></tr>)}</tbody></table>{!jobs.length && <EmptyState/>}</section>
    <div className="job-reviews">{readyJobs.map((job) => <CommandReview key={job.id} job={job} confirmed={Boolean(confirmed[job.id])} executeLabel={command(job)} onConfirmed={(value) => setConfirmed({ ...confirmed, [job.id]:value })} onExecute={() => void onExecute(job)}/>)}</div>
  </>;
}

function State({ state }:{ state:string }) { return <span className={`state state-${state}`}>{stateLabel[state] || (state === "unconfigured" ? "未配置" : state)}</span>; }
function EmptyState() { return <div className="empty-state"><CheckCircle2 size={20}/><p>选择成员后即可管理 SSH 公钥和机器权限。</p></div>; }
function Login({ password, error, onPassword, onLogin }:{ password:string; error:string; onPassword:(value:string)=>void; onLogin:()=>Promise<void> }) { return <main className="login"><section><span className="section-kicker">TRAIN/ACCESS</span><h1>服务器访问控制台</h1><p>成员密钥、机器权限和数据盘目录在同一处确认。</p><form onSubmit={(event) => { event.preventDefault(); void onLogin(); }}><input autoFocus aria-label="管理员密码" type="password" value={password} onChange={(event) => onPassword(event.target.value)} placeholder="管理员密码"/><Button type="submit">进入控制台 <ChevronRight size={16}/></Button>{error && <span className="notice error">{error}</span>}</form></section></main>; }
function message(cause:unknown, fallback:string) { return cause instanceof Error ? cause.message : fallback; }
