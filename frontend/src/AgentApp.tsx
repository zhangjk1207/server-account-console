import { KeyRound, LoaderCircle } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { AgentModelConfig, api, Host, login } from "./api";
import { AgentWorkbench } from "./agent/AgentWorkbench";
import { AppShell, AppView } from "./agent/AppShell";
import { MachinesPage } from "./agent/MachinesPage";
import { ModelSettings } from "./agent/ModelSettings";
import { RunsPage } from "./agent/RunsPage";
import { Button } from "./components/ui/button";

export function AgentApp() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [view, setView] = useState<AppView>("operations");
  const [hosts, setHosts] = useState<Host[]>([]);
  const [modelConfig, setModelConfig] = useState<AgentModelConfig | null>(null);

  const loadWorkspace = async () => {
    const [nextHosts, nextConfig] = await Promise.all([api<Host[]>("/hosts"), api<AgentModelConfig | null>("/agent-model-config")]);
    setHosts(nextHosts); setModelConfig(nextConfig);
  };
  useEffect(() => { void fetch("/api/auth/me", { credentials: "include" }).then(async (response) => { if (response.ok) { setAuthenticated(true); await loadWorkspace(); } }).catch(() => setError("无法连接控制面")).finally(() => setChecking(false)); }, []);

  const submitLogin = async (event: FormEvent) => { event.preventDefault(); try { await login(password); setAuthenticated(true); setError(""); await loadWorkspace(); } catch (cause) { setError(cause instanceof Error ? cause.message : "登录失败"); } };
  if (checking) return <div className="app-loading"><LoaderCircle className="spin" size={22}/><span>正在连接控制面</span></div>;
  if (!authenticated) return <main className="ops-login"><section><div className="login-symbol"><KeyRound size={20}/></div><span>OPS/ONE · PRIVATE CONTROL PLANE</span><h1>服务器运维 Agent</h1><p>登录后管理机器、模型、任务与受控执行。</p><form onSubmit={submitLogin}><label><span>管理员密码</span><input autoFocus type="password" value={password} onChange={(event) => setPassword(event.target.value)}/></label>{error && <div className="inline-alert">{error}</div>}<Button type="submit">进入工作台</Button></form></section></main>;

  const ready = Boolean(modelConfig?.enabled && modelConfig.api_key_configured && hosts.length);
  return <AppShell view={view} onView={setView} runtimeReady={ready}>
    {view === "operations" ? <AgentWorkbench hosts={hosts} modelConfig={modelConfig} onNavigate={setView}/>
      : view === "machines" ? <MachinesPage hosts={hosts} onChanged={loadWorkspace}/>
      : view === "runs" ? <RunsPage/>
      : <ModelSettings config={modelConfig} onChanged={setModelConfig}/ >}
  </AppShell>;
}
