import { Activity, Bot, Cpu, Server, Settings2, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

export type AppView = "operations" | "machines" | "runs" | "settings";

const navigation = [
  { id: "operations" as const, label: "运维任务", icon: Bot },
  { id: "machines" as const, label: "机器", icon: Server },
  { id: "runs" as const, label: "审批与执行", icon: Activity },
];

export function AppShell({ view, onView, children, runtimeReady }: { view: AppView; onView: (view: AppView) => void; children: ReactNode; runtimeReady: boolean }) {
  return <div className="ops-shell">
    <aside className="ops-sidebar">
      <button className="ops-brand" onClick={() => onView("operations")} aria-label="打开运维任务">
        <span><Cpu size={20}/></span><div><b>OPS/ONE</b><small>SERVER AGENT</small></div>
      </button>
      <nav aria-label="主导航">
        {navigation.map(({ id, label, icon: Icon }) => <button key={id} className={view === id ? "ops-nav current" : "ops-nav"} onClick={() => onView(id)}><Icon size={18}/><span>{label}</span></button>)}
      </nav>
      <div className="ops-sidebar-bottom">
        <button className={view === "settings" ? "ops-nav current" : "ops-nav"} onClick={() => onView("settings")}><Settings2 size={18}/><span>模型与 Runtime</span></button>
        <div className={runtimeReady ? "runtime-pill ready" : "runtime-pill"}><ShieldCheck size={15}/><span>{runtimeReady ? "pi runtime 已就绪" : "需要完成配置"}</span></div>
      </div>
    </aside>
    <main className="ops-content">{children}</main>
  </div>;
}
