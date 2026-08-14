import { CheckCircle2, KeyRound, LoaderCircle, Plus, Server, TestTube2, Upload } from "lucide-react";
import { FormEvent, useState } from "react";

import { api, Host, HostCredentialProbe } from "../api";
import { Button } from "../components/ui/button";
import { PageHeading } from "./ModelSettings";

export function MachinesPage({ hosts, onChanged }: { hosts: Host[]; onChanged: () => Promise<void> }) {
  const [selected, setSelected] = useState<string | null>(hosts[0]?.id ?? null);
  const [adding, setAdding] = useState(hosts.length === 0);
  const [error, setError] = useState("");
  const host = hosts.find((item) => item.id === selected) ?? hosts[0] ?? null;
  return <div className="machines-page">
    <PageHeading kicker="MANAGED INFRASTRUCTURE" title="机器" description="Agent 只能操作这里显式接入并验证过的服务器。" action={<Button onClick={() => setAdding(true)}><Plus size={16}/>接入机器</Button>}/>
    {error && <div className="inline-alert">{error}</div>}
    <div className="machine-layout">
      <aside className="machine-list">
        <div className="list-caption"><span>已接入</span><b>{hosts.length}</b></div>
        {hosts.map((item) => <button key={item.id} className={(host?.id === item.id && !adding) ? "machine-list-item selected" : "machine-list-item"} onClick={() => { setSelected(item.id); setAdding(false); }}><span className={`machine-status ${item.status}`}/><div><b>{item.name}</b><small>{item.ssh_user}@{item.address}:{item.port}</small></div></button>)}
        {!hosts.length && <div className="empty-list"><Server size={22}/><span>还没有机器</span></div>}
      </aside>
      <section className="machine-canvas">
        {adding ? <AddMachine onCancel={() => setAdding(false)} onAdded={async (next) => { await onChanged(); setSelected(next.id); setAdding(false); }} onError={setError}/> : host ? <MachineDetail host={host} onChanged={onChanged} onError={setError}/> : null}
      </section>
    </div>
  </div>;
}

function AddMachine({ onCancel, onAdded, onError }: { onCancel: () => void; onAdded: (host: Host) => Promise<void>; onError: (error: string) => void }) {
  const [form, setForm] = useState({ name: "", address: "", port: 22, ssh_user: "root", data_root: "", tags: "" });
  const submit = async (event: FormEvent) => { event.preventDefault(); try { const host = await api<Host>("/hosts", { method: "POST", body: JSON.stringify({ ...form, data_root: form.data_root || null, tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean) }) }); await onAdded(host); } catch (cause) { onError(cause instanceof Error ? cause.message : "接入失败"); } };
  return <form className="machine-editor" onSubmit={submit}><div className="canvas-title"><span><Plus size={18}/></span><div><h2>接入新机器</h2><p>先登记连接目标，再上传管理凭据并验证主机指纹。</p></div></div><div className="field-grid"><label><span>机器标识</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="server-71" pattern="[A-Za-z0-9][A-Za-z0-9._-]*" title="只能使用英文字母、数字、点、下划线和连字符" required/><small className="field-hint">用于 Ansible inventory，例如 server-71</small></label><label><span>地址</span><input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="10.0.0.21 或 FQDN" required/></label><label><span>SSH 用户</span><input value={form.ssh_user} onChange={(e) => setForm({ ...form, ssh_user: e.target.value })} required/></label><label><span>SSH 端口</span><input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}/></label><label><span>数据根目录</span><input value={form.data_root} onChange={(e) => setForm({ ...form, data_root: e.target.value })} placeholder="/mnt/data"/></label><label><span>标签</span><input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="gpu, production"/></label></div><div className="editor-actions"><Button type="button" className="text-button" onClick={onCancel}>取消</Button><Button type="submit">保存并继续</Button></div></form>;
}

function MachineDetail({ host, onChanged, onError }: { host: Host; onChanged: () => Promise<void>; onError: (error: string) => void }) {
  const [privateKey, setPrivateKey] = useState<File | null>(null); const [sudo, setSudo] = useState(""); const [busy, setBusy] = useState(false); const [probe, setProbe] = useState<HostCredentialProbe | null>(null);
  const save = async () => { if (!privateKey || !sudo) { onError("请选择 SSH 私钥并填写 sudo 密码"); return; } const body = new FormData(); body.set("private_key_file", privateKey); body.set("sudo_password", sudo); setBusy(true); try { await api(`/hosts/${host.id}/credentials`, { method: "PUT", body }); setPrivateKey(null); setSudo(""); } catch (cause) { onError(cause instanceof Error ? cause.message : "凭据保存失败"); } finally { setBusy(false); } };
  const test = async () => { setBusy(true); try { const next = await api<HostCredentialProbe>(`/hosts/${host.id}/credentials/test`, { method: "POST" }); setProbe(next); await onChanged(); } catch (cause) { onError(cause instanceof Error ? cause.message : "连接测试失败"); } finally { setBusy(false); } };
  const confirmFingerprint = async () => { if (!probe?.fingerprint) return; setBusy(true); try { await api<Host>(`/hosts/${host.id}/confirm-fingerprint`, { method:"POST", body:JSON.stringify({ fingerprint:probe.fingerprint }) }); setProbe(null); await onChanged(); } catch (cause) { onError(cause instanceof Error ? cause.message : "主机指纹确认失败"); } finally { setBusy(false); } };
  return <div className="machine-editor"><div className="machine-detail-head"><div className="canvas-title"><span><Server size={18}/></span><div><h2>{host.name}</h2><p>{host.ssh_user}@{host.address}:{host.port}</p></div></div><span className={`host-state ${host.status}`}>{host.status}</span></div><section className="connection-panel"><div className="section-number">01</div><div><h3>管理连接</h3><p>凭据加密保存，Agent 和浏览器都无法读取原文。</p><div className="credential-grid"><label className="file-field"><span>SSH 私钥</span><div><Upload size={16}/>{privateKey?.name ?? "选择 PEM / OpenSSH 私钥"}</div><input type="file" onChange={(event) => setPrivateKey(event.target.files?.[0] ?? null)}/></label><label><span>sudo 密码</span><input type="password" value={sudo} onChange={(event) => setSudo(event.target.value)} placeholder="用于受控提权"/></label></div><div className="connection-actions"><Button onClick={() => void save()} disabled={busy}><KeyRound size={16}/>保存凭据</Button><Button className="secondary-button" onClick={() => void test()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16}/> : <TestTube2 size={16}/>}验证连接</Button></div>{probe?.requires_confirmation && probe.fingerprint ? <div className="fingerprint-review"><ShieldFingerprint/><div><b>确认主机指纹</b><code>{probe.fingerprint}</code><small>请与服务器管理员提供的指纹核对，确认后才会尝试登录。</small></div><Button onClick={() => void confirmFingerprint()} disabled={busy}>确认指纹</Button></div> : probe && <div className={probe.ssh_ok ? "probe-result ok" : "probe-result"}>{probe.ssh_ok ? <CheckCircle2 size={16}/> : null}<span>{probe.ssh_ok ? `SSH 已连接，sudo ${probe.sudo_ok ? "可用" : "不可用"}` : probe.error}</span>{probe.latency_ms != null && <small>{probe.latency_ms} ms</small>}</div>}</div></section><section className="connection-panel"><div className="section-number">02</div><div><h3>Agent 作用域</h3><p>数据根目录：{host.data_root || "未配置"}</p><div className="tag-row">{host.tags.length ? host.tags.map((tag) => <span key={tag}>{tag}</span>) : <span>无标签</span>}</div></div></section></div>;
}

function ShieldFingerprint() { return <KeyRound size={17}/>; }
