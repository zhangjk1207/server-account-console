import { Activity, AlertTriangle, ArrowDown, ArrowUp, Bot, Check, ChevronDown, Circle, Clock3, Cpu, LoaderCircle, MessageSquareText, PanelRight, Plus, Server, ShieldCheck, TerminalSquare, Wrench } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

import type { AgentModelConfig, Host } from "../api";
import { api } from "../api";
import { Button } from "../components/ui/button";
import { AppView } from "./AppShell";
import { LiveEvent, promptAgent } from "./client";
import type { ActivityItem, AgentOverview, ConversationMessage } from "./types";

type Session = { id: string; title: string; updated: string; messages: ConversationMessage[]; activities: ActivityItem[]; events: LiveEvent[]; operationId: string | null };
const storageKey = "ops-one.sessions.v1";

function initialSessions(): Session[] {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? "[]") as Session[];
    if (Array.isArray(saved) && saved.length) return saved.map((session) => ({ ...session, events: [] }));
  } catch { /* A corrupt local cache must not block the workbench. */ }
  return [{ id: crypto.randomUUID(), title: "新运维任务", updated: "刚刚", messages: [], activities: [], events: [], operationId: null }];
}
const starterPrompts = [
  { icon: Activity, title: "巡检整组机器", prompt: "检查所有机器的连通状态，并按风险排序说明需要处理的问题。" },
  { icon: TerminalSquare, title: "定位服务异常", prompt: "列出不可连接的机器和最近失败的执行，给出排查顺序。" },
  { icon: ShieldCheck, title: "审查访问权限", prompt: "审查当前成员的 SSH 访问授权，找出缺失密钥或异常授权。" },
  { icon: Server, title: "检查机器容量", prompt: "汇总机器清单与状态，指出目前缺少哪些运维上下文。" },
];

export function AgentWorkbench({ hosts, modelConfig, onNavigate }: { hosts: Host[]; modelConfig: AgentModelConfig | null; onNavigate: (view: AppView) => void }) {
  const [sessions, setSessions] = useState<Session[]>(initialSessions);
  const [activeId, setActiveId] = useState(sessions[0].id);
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [consoleTab, setConsoleTab] = useState<"overview" | "trace" | "details">("overview");
  const [consoleOpen, setConsoleOpen] = useState(true);
  const [overview, setOverview] = useState<AgentOverview | null>(null);
  const transcriptEnd = useRef<HTMLDivElement>(null);
  const scrollContainer = useRef<HTMLDivElement>(null);
  const stuckToBottom = useRef(true);
  const [scrolledAway, setScrolledAway] = useState(false);
  const active = sessions.find((session) => session.id === activeId) ?? sessions[0];
  const activities = active.activities ?? [];
  const events = active.events ?? [];
  const operationId = active.operationId ?? null;
  const ready = Boolean(modelConfig?.enabled && modelConfig.api_key_configured && hosts.length);

  // Scrolling: stick to the newest text only while the reader is near the
  // bottom of the transcript. If the operator scrolls up to read an earlier
  // message, stop chasing the stream so their place is preserved. Show a
  // "跳回最新" affordance so the newest reply is always one click away.
  const nearBottom = () => {
    const el = scrollContainer.current;
    if (!el) return false;
    return el.scrollTop + el.clientHeight >= el.scrollHeight - 96;
  };
  const refreshStuck = () => {
    const el = scrollContainer.current;
    if (!el) return;
    if (nearBottom()) { el.scrollTop = el.scrollHeight; stuckToBottom.current = true; setScrolledAway(false); }
  };
  useEffect(() => { if (transcriptEnd.current) transcriptEnd.current.scrollIntoView({ behavior: "auto", block: "end" }); }, [activeId]);
  useEffect(() => { refreshStuck(); }, [active.messages, active.events]);
  const onTranscriptScroll = () => {
    setScrolledAway(!nearBottom());
    if (nearBottom()) { stuckToBottom.current = true; } else { stuckToBottom.current = false; }
  };
  const jumpToLatest = () => { const el = scrollContainer.current; if (!el) return; el.scrollTo({ top: el.scrollHeight, behavior: "smooth" }); stuckToBottom.current = true; setScrolledAway(false); };
  useEffect(() => { localStorage.setItem(storageKey, JSON.stringify(sessions)); }, [sessions]);
  useEffect(() => { void api<AgentOverview>("/agent-context/overview").then(setOverview).catch(() => {/* overview is decorative; failures must not block the console. */}); }, [activeId, hosts]);
  useEffect(() => {
    if (!operationId) return;
    const abort = new AbortController();
    void fetch(`/api/jobs/${operationId}/events`, { credentials: "include", signal: abort.signal })
      .then((response) => (response.ok ? response.body : null))
      .then(async (body) => {
        if (!body) return;
        const reader = body.getReader();
        const decoder = new TextDecoder();
        let raw = "";
        try {
          while (true) {
            const { done, value } = await reader.read();
            raw += decoder.decode(value, { stream: !done });
            const blocks = raw.split("\n\n");
            raw = blocks.pop() ?? "";
            for (const block of blocks) {
              const line = block.split("\n").find((part) => part.startsWith("data: "));
              if (!line) continue;
              try {
                const event = JSON.parse(line.slice(6)) as LiveEvent;
                setSessions((current) => current.map((session) => session.id === activeId ? { ...session, events: (session.events ?? []).some((item) => item.id === event.id) ? session.events : [...(session.events ?? []), event].slice(-120) } : session));
              } catch { /* one malformed event must not stop the stream. */ }
            }
            if (done) break;
          }
        } catch { /* the executor closes the stream when the run finishes. */ }
      });
    return () => abort.abort();
  }, [operationId]);

  const updateMessages = (transform: (messages: ConversationMessage[]) => ConversationMessage[]) => setSessions((current) => current.map((session) => session.id === activeId ? { ...session, messages: transform(session.messages) } : session));
  const newSession = () => { const next: Session = { id: crypto.randomUUID(), title: "新运维任务", updated: "刚刚", messages: [], activities: [], events: [], operationId: null }; setSessions((current) => [next, ...current]); setActiveId(next.id); setError(""); };
  const submit = async (value: string) => {
    const text = value.trim(); if (!text || running || !ready) return;
    const responseId = crypto.randomUUID(); setPrompt(""); setError(""); setRunning(true); setConsoleTab("trace");
    setSessions((current) => current.map((session) => session.id === activeId ? { ...session, title: session.messages.length ? session.title : text.slice(0, 24), updated: "刚刚", activities: [], events: [], messages: [...session.messages, { id: crypto.randomUUID(), role: "operator", text }, { id: responseId, role: "agent", text: "", pending: true }] } : session));
    try {
      await promptAgent(text, operationId, {
        onOperation: (nextOperationId) => setSessions((current) => current.map((session) => session.id === activeId ? { ...session, operationId: nextOperationId } : session)),
        onText: (delta) => updateMessages((messages) => messages.map((message) => message.id === responseId ? { ...message, text: message.text + delta } : message)),
        onActivity: (activity) => setSessions((current) => current.map((session) => session.id === activeId ? { ...session, activities: (session.activities ?? []).some((item) => item.id === activity.id) ? session.activities.map((item) => item.id === activity.id ? activity : item) : [...(session.activities ?? []), activity] } : session)),
      });
      updateMessages((messages) => messages.map((message) => message.id === responseId ? { ...message, pending: false } : message));
    } catch (cause) { const detail = cause instanceof Error ? cause.message : "Agent 运行失败"; setError(detail); updateMessages((messages) => messages.map((message) => message.id === responseId ? { ...message, pending: false, text: message.text || `无法完成：${detail}` } : message)); }
    finally { setRunning(false); }
  };
  const submitForm = (event: FormEvent) => { event.preventDefault(); void submit(prompt); };

  return <div className="agent-workbench">
    <aside className="session-pane">
      <Button className="new-task-button" onClick={newSession}><Plus size={16}/>新建运维任务</Button>
      <div className="session-heading"><span>任务</span><small>{sessions.length}</small></div>
      <div className="session-list">{sessions.map((session) => <button key={session.id} className={session.id === activeId ? "session-item selected" : "session-item"} onClick={() => setActiveId(session.id)}><MessageSquareText size={15}/><span><b>{session.title}</b><small>{session.updated}</small></span></button>)}</div>
      <div className="scope-block"><span>当前工作空间</span><button onClick={() => onNavigate("machines")}><Server size={15}/><div><b>{hosts.length} 台机器</b><small>{hosts.filter((host) => host.status === "reachable").length} 台可连接</small></div></button><button onClick={() => onNavigate("settings")}><Cpu size={15}/><div><b>{modelConfig?.model ?? "未配置模型"}</b><small>{modelConfig?.provider ?? "pi runtime"}</small></div></button></div>
    </aside>

    <section className="chat-workspace">
      <header className="chat-header">
        <div><b>{active.messages.length ? active.title : "新运维任务"}</b><span>{operationId ? <>运行 <em className="op-id">{operationId.slice(0, 8)}</em></> : (active.messages.length ? "本轮已结束" : "准备就绪")}</span></div>
        <button className="console-toggle" title={consoleOpen ? "收起任务控制台" : "打开任务控制台"} onClick={() => setConsoleOpen((open) => !open)}><PanelRight size={17}/></button>
      </header>
      <div className="chat-scroll" ref={scrollContainer} onScroll={onTranscriptScroll}>
        {!active.messages.length ? <Welcome ready={ready} overview={overview} hasMachines={Boolean(hosts.length)} hasModel={Boolean(modelConfig?.api_key_configured)} onNavigate={onNavigate} onPrompt={submit}/> : <div className="message-column">{active.messages.map((message) => { const isAgent = message.role === "agent"; return <article key={message.id} className={`chat-message ${message.role}`}><div className="chat-avatar">{isAgent ? <Bot size={15}/> : "你"}</div><div className="chat-bubble">{isAgent ? <div className="chat-author"><span className="dc-dot"/><span>OPS Agent</span>{active.updated && <span className="dc-time">· {new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}</span>}</div> : null}<div className="chat-text">{message.text || (message.pending ? <span className="thinking">正在思考<span className="dc-dots"><i/><i/><i/></span></span> : null)}</div></div></article>; })}<div ref={transcriptEnd}/></div>}
      </div>
      <button type="button" className={scrolledAway ? "jump-to-new visible" : "jump-to-new"} onClick={jumpToLatest}><ArrowDown size={15}/><span>回到最新</span></button>
      {error && <div className="agent-inline-error"><AlertTriangle size={15}/>{error}</div>}
      <form className="agent-composer" onSubmit={submitForm}>
        <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={ready ? "描述运维目标，Agent 会先检查再行动…" : "请先完成机器与模型配置"} rows={3} disabled={!ready}/>
        <div className="composer-toolbar"><div><button type="button" className="model-selector" onClick={() => onNavigate("settings")}><Cpu size={14}/><span>{modelConfig?.model ?? "选择模型"}</span><ChevronDown size={13}/></button><button type="button" className="scope-selector" onClick={() => onNavigate("machines")}><Server size={14}/><span>{hosts.length} 台机器</span></button></div><Button className="composer-send" type="submit" disabled={!ready || running || !prompt.trim()} title="发送"><ArrowUp size={17}/></Button></div>
      </form>
    </section>

    <aside className={consoleOpen ? "task-console" : "task-console closed"}>
      <div className="console-header"><div><b>任务控制台</b><span>{running ? <><span className="live-dot"/>运行中</> : "实时状态"}</span></div><button className="console-toggle" title="收起任务控制台" onClick={() => setConsoleOpen(false)}><PanelRight size={16}/></button></div>
      <div className="console-tabs">{(["overview", "trace", "details"] as const).map((tab) => <button key={tab} className={consoleTab === tab ? "selected" : ""} onClick={() => setConsoleTab(tab)}>{tab === "overview" ? "概览" : tab === "trace" ? "轨迹" : "详情"}</button>)}</div>
      <div className="console-body">{consoleTab === "overview" ? <OverviewConsole overview={overview} activities={activities} running={running} hosts={hosts} onNavigate={onNavigate}/> : consoleTab === "trace" ? <TraceConsole activities={activities} events={events} running={running}/> : <DetailsConsole activities={activities} events={events} running={running}/>}</div>
    </aside>
  </div>;
}

function Welcome({ ready, overview, hasMachines, hasModel, onNavigate, onPrompt }: { ready: boolean; overview: AgentOverview | null; hasMachines: boolean; hasModel: boolean; onNavigate: (view: AppView) => void; onPrompt: (prompt: string) => Promise<void> }) {
  const o = overview;
  return <div className="agent-welcome"><div className="welcome-mark"><Bot size={25}/></div><h1>今天要处理什么服务器问题？</h1><p>描述目标，Agent 会读取机器状态、拆解步骤、调用受控工具，并把每一步留在任务轨迹里。</p>{!ready ? <div className="onboarding-card"><div><span>完成工作台配置</span><small>Agent 运行前需要一个模型和至少一台机器。</small></div><button className={hasModel ? "done" : ""} onClick={() => onNavigate("settings")}><span>{hasModel ? <Check size={15}/> : "1"}</span><div><b>配置 pi agent 模型</b><small>Provider、模型 ID 与加密 API Key</small></div></button><button className={hasMachines ? "done" : ""} onClick={() => onNavigate("machines")}><span>{hasMachines ? <Check size={15}/> : "2"}</span><div><b>接入并验证机器</b><small>SSH 目标、私钥、sudo 与主机指纹</small></div></button></div> : <>
    <div className="prompt-grid">{starterPrompts.map(({ icon: Icon, title, prompt }) => <button key={title} onClick={() => void onPrompt(prompt)}><Icon size={17}/><span><b>{title}</b><small>{prompt}</small></span><ArrowUp size={14}/></button>)}</div>
    {o && <p className="quick-status">{o.machines.total > 0 ? `${o.machines.reachable} 台机器可连接，${o.machines.attention} 台需关注 · ${o.members.active} 位成员 · ${o.grants.active} 条授权` : "等待机器接入"}</p>}
  </>}</div>;
}

function OverviewConsole({ overview, activities, running, hosts, onNavigate }: { overview: AgentOverview | null; activities: ActivityItem[]; running: boolean; hosts: Host[]; onNavigate: (view: AppView) => void }) {
  const o = overview;
  const completed = activities.filter((item) => item.state === "complete").length;
  const errored = activities.filter((item) => item.state === "error").length;
  return <>
    <section className="console-card"><span className="console-label">运行状态</span><div className="run-status"><span className={running ? "status-icon active" : errored ? "status-icon error" : "status-icon"}>{running ? <LoaderCircle className="spin" size={16}/> : errored ? <AlertTriangle size={16}/> : <Check size={16}/>}</span><div><b>{running ? "Agent 正在执行" : activities.length ? (errored ? "本轮存在异常" : "本轮已完成") : "等待任务"}</b><small>{activities.length} 个工具步骤</small></div></div></section>
    <section className="metric-grid"><div><span>目标机器</span><b>{hosts.length}</b></div><div><span>工具步骤</span><b>{activities.length}</b></div><div><span>已完成</span><b>{completed}</b></div><div><span>异常</span><b>{errored}</b></div></section>
    {o && <section className="console-card"><span className="console-label">控制面快照</span><div className="stat-grid">
      <div className="stat-tile"><b>{o.machines.reachable}</b><span>可连接机器</span></div>
      <div className="stat-tile"><b>{o.machines.attention}</b><span>需关注</span></div>
      <div className="stat-tile"><b>{o.grants.active}</b><span>访问授权</span></div>
    </div><div className="attention-link">{o.machines.attention > 0 ? <button onClick={() => onNavigate("machines")}>检查 {o.machines.attention} 台异常机器 →</button> : <span className="console-alt">全部机器可连接</span>}</div></section>}
    <section className="console-card"><span className="console-label">安全边界</span><div className="guardrail"><ShieldCheck size={17}/><p>读取型检查可自动执行。任何服务、软件包、账户或文件变更都必须生成计划并等待人工批准。</p></div></section>
  </>;
}
function TraceConsole({ activities, events, running }: { activities: ActivityItem[]; events: LiveEvent[]; running: boolean }) {
  return <div className="trace-list">{[...activities].reverse().map((item, index) => <div className={`trace-item ${item.state}`} key={item.id}><span>{item.state === "running" ? <LoaderCircle className="spin" size={14}/> : item.state === "error" ? <AlertTriangle size={14}/> : <Check size={14}/>}</span><div><small>STEP {activities.length - index}</small><b>{item.label}</b><p>{item.detail}</p></div></div>)}{running && !activities.length && <div className="console-empty"><LoaderCircle className="spin" size={18}/><span>正在规划第一个步骤</span></div>}{!running && !activities.length && <div className="console-empty"><Circle size={14}/><span>开始任务后，这里会显示完整工具轨迹</span></div>}</div>;
}
function DetailsConsole({ activities, events, running }: { activities: ActivityItem[]; events: LiveEvent[]; running: boolean }) {
  const item = activities.at(-1);
  if (!item && events.length) {
    return <div className="event-list">{events.slice(-12).reverse().map((event) => <div className={`event-item ${event.level}`} key={event.id}><Wrench size={14}/><span className="ev-time">{timeOf(event.created_at)}</span><span className="ev-msg">{event.message}</span></div>)}</div>;
  }
  const output = item ? <div className="detail-panel"><span className="console-label">最近步骤</span><h3>{item.label}</h3><p style={{ marginBottom: 14, color: "var(--ops-muted)", fontSize: 10.5, lineHeight: 1.65 }}>{item.detail}</p><dl><div><dt>状态</dt><dd>{item.state}</dd></div><div><dt>证据类型</dt><dd>pi tool event</dd></div><div><dt>时间</dt><dd><Clock3 size={12}/>{running ? "运行中" : "本轮结束"}</dd></div></dl></div>
    : (events.length ? <div className="event-list">{events.slice(-12).reverse().map((event) => (<div className={`event-item ${event.level}`} key={event.id}><Wrench size={14}/><span className="ev-time">{timeOf(event.created_at)}</span><span className="ev-msg">{event.message}</span></div>))}</div>
    : <div className="console-empty"><Wrench size={17}/><span>选择一个工具步骤查看输入与结果</span></div>);
  return output;
}

function timeOf(value: string): string {
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  } catch { return "—"; }
}