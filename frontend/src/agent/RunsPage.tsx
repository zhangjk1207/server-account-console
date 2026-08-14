import { Activity, CheckCircle2, Clock3, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { api, Job } from "../api";
import { PageHeading } from "./ModelSettings";

export function RunsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  useEffect(() => { void api<Job[]>("/jobs").then(setJobs); }, []);
  const pending = jobs.filter((job) => job.state === "ready_to_confirm").length;
  return <div className="runs-page"><PageHeading kicker="HUMAN IN THE LOOP" title="审批与执行" description="Agent 只能生成变更计划；影响服务器状态的操作必须在这里由管理员确认。"/><div className="run-summary"><div><ShieldAlert size={18}/><span>等待审批</span><b>{pending}</b></div><div><Activity size={18}/><span>全部执行</span><b>{jobs.length}</b></div><div><CheckCircle2 size={18}/><span>成功</span><b>{jobs.filter((job) => job.state === "succeeded").length}</b></div></div><section className="run-list"><div className="run-list-head"><span>任务</span><span>目标</span><span>状态</span><span>时间</span></div>{jobs.map((job) => <article key={job.id}><div><b>{job.kind}</b><code>{job.id.slice(0, 12)}</code></div><span>{job.targets?.map((target) => target.host_name).join(", ") || "-"}</span><span className={`run-state ${job.state}`}>{job.state}</span><time><Clock3 size={13}/>{new Date(job.created_at).toLocaleString()}</time></article>)}{!jobs.length && <div className="empty-runs">还没有执行记录</div>}</section></div>;
}
