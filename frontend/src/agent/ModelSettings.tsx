import { Check, Cpu, Eye, EyeOff, KeyRound, LoaderCircle, Save } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { AgentModelConfig, api } from "../api";
import { Button } from "../components/ui/button";

const defaults: Record<AgentModelConfig["provider"], string> = {
  openai: "gpt-5.2",
  anthropic: "claude-sonnet-4-5",
  google: "gemini-2.5-pro",
  "openai-compatible": "deepseek-chat",
};

export function ModelSettings({ config, onChanged }: { config: AgentModelConfig | null; onChanged: (config: AgentModelConfig) => void }) {
  const [provider, setProvider] = useState<AgentModelConfig["provider"]>(config?.provider ?? "openai");
  const [model, setModel] = useState(config?.model ?? defaults.openai);
  const [baseUrl, setBaseUrl] = useState(config?.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [thinking, setThinking] = useState<AgentModelConfig["thinking_level"]>(config?.thinking_level ?? "medium");
  const [enabled, setEnabled] = useState(config?.enabled ?? true);
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!config) return;
    setProvider(config.provider); setModel(config.model); setBaseUrl(config.base_url ?? ""); setThinking(config.thinking_level); setEnabled(config.enabled);
  }, [config]);

  const changeProvider = (next: AgentModelConfig["provider"]) => {
    setProvider(next);
    setModel(defaults[next]);
    if (next !== "openai-compatible") setBaseUrl("");
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setNotice("");
    try {
      const next = await api<AgentModelConfig>("/agent-model-config", { method: "PUT", body: JSON.stringify({ provider, model, base_url: baseUrl || null, api_key: apiKey || null, thinking_level: thinking, enabled }) });
      setApiKey(""); setNotice("配置已加密保存。新任务会立即使用此模型。"); onChanged(next);
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : "保存失败"); }
    finally { setSaving(false); }
  };

  return <div className="settings-page">
    <PageHeading kicker="PI AGENT RUNTIME" title="模型与 Runtime" description="模型凭据保存在控制面加密库中，pi runtime 仅通过内部令牌按需读取。"/>
    <div className="settings-layout">
      <form className="settings-form" onSubmit={submit}>
        <section className="form-section">
          <div className="form-section-title"><span>01</span><div><h2>模型提供商</h2><p>选择 pi agent 的主推理模型。</p></div></div>
          <div className="provider-grid">
            {(["openai", "anthropic", "google", "openai-compatible"] as const).map((item) => <button type="button" key={item} className={provider === item ? "provider-option selected" : "provider-option"} onClick={() => changeProvider(item)}><Cpu size={17}/><span>{item === "openai-compatible" ? "OpenAI 兼容" : item[0].toUpperCase() + item.slice(1)}</span>{provider === item && <Check size={15}/>}</button>)}
          </div>
        </section>
        <section className="form-section two-column">
          <label><span>模型 ID</span><input value={model} onChange={(event) => setModel(event.target.value)} placeholder="模型 ID" required/></label>
          {provider === "openai-compatible" && <label><span>API Base URL</span><input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://example.com/v1" required/></label>}
          <label className="key-field"><span>API Key</span><div><input type={showKey ? "text" : "password"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={config?.api_key_configured ? "已配置，留空保持不变" : "输入 API Key"}/><button type="button" title={showKey ? "隐藏 API Key" : "显示 API Key"} onClick={() => setShowKey(!showKey)}>{showKey ? <EyeOff size={16}/> : <Eye size={16}/>}</button></div></label>
        </section>
        <section className="form-section">
          <div className="field-label">推理强度</div>
          <div className="segmented">{(["off", "low", "medium", "high"] as const).map((level) => <button type="button" key={level} className={thinking === level ? "selected" : ""} onClick={() => setThinking(level)}>{level === "off" ? "关闭" : level === "low" ? "低" : level === "medium" ? "中" : "高"}</button>)}</div>
          <label className="toggle-row"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)}/><span><b>启用此配置</b><small>关闭后 Agent 不会发起任何模型请求。</small></span></label>
        </section>
        <div className="form-actions"><span className={notice.includes("失败") ? "save-notice error" : "save-notice"}>{notice}</span><Button type="submit" disabled={saving}>{saving ? <LoaderCircle className="spin" size={16}/> : <Save size={16}/>}保存配置</Button></div>
      </form>
      <aside className="security-note"><KeyRound size={19}/><h3>凭据边界</h3><p>浏览器永远不会重新读取 API Key。数据库只保存 Fernet 密文，Agent Runtime 使用独立内部令牌读取解密后的凭据。</p><dl><div><dt>Provider</dt><dd>{config?.provider ?? "未配置"}</dd></div><div><dt>Model</dt><dd>{config?.model ?? "-"}</dd></div><div><dt>API Key</dt><dd>{config?.api_key_configured ? "已加密" : "未配置"}</dd></div></dl></aside>
    </div>
  </div>;
}

export function PageHeading({ kicker, title, description, action }: { kicker: string; title: string; description: string; action?: React.ReactNode }) {
  return <header className="page-heading"><div><span>{kicker}</span><h1>{title}</h1><p>{description}</p></div>{action}</header>;
}
