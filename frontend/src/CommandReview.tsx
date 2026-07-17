import { AlertTriangle, CheckCircle2, Terminal } from "lucide-react";

import type { AccessGrantSnapshot, Job } from "./api";
import { Button } from "./components/ui/button";

type Props = {
  job: Job;
  confirmed: boolean;
  executeLabel: string;
  onConfirmed: (confirmed:boolean) => void;
  onExecute: () => void;
};

function targetName(job:Job, grant:AccessGrantSnapshot):string {
  return job.targets?.find((target) => target.host_id === grant.host_id)?.host_name
    || job.request_snapshot.hosts?.find((host) => host.id === grant.host_id)?.name
    || grant.host_id;
}

export function CommandReview({ job, confirmed, executeLabel, onConfirmed, onExecute }:Props) {
  const grants = job.request_snapshot.grants || [];
  const reviewable = grants.length > 0 && grants.every((grant) => grant.command_preview?.commands.length);

  return <section className="command-review" aria-label={`批次 ${job.id} 命令审阅`}>
    <header><div><Terminal size={18}/><div><strong>执行前命令审阅</strong><span>{grants.length} 台目标机器</span></div></div><span className="review-state"><CheckCircle2 size={14}/>预检已完成</span></header>
    {reviewable ? <div className="command-targets">{grants.map((grant) => {
      const preview = grant.command_preview!;
      return <details key={grant.host_id} open>
        <summary><span><b>{targetName(job, grant)}</b><small>{grant.username} · {grant.account_origin === "adopted" ? "已有账号纳管" : "创建新账号"}</small></span><code>{preview.tasks.join(" / ")}</code></summary>
        <div className="command-body">
          <p className="command-label">{preview.label}</p>
          {(preview.existing_key_fingerprints?.length || 0) > 0 && <div className="key-review-row"><span>当前已有</span><div className="fingerprints">{preview.existing_key_fingerprints!.map((fingerprint) => <code key={fingerprint}>{fingerprint}</code>)}</div></div>}
          {preview.key_fingerprints.length > 0 && <div className="key-review-row"><span>{grant.account_origin === "adopted" ? "将追加" : "将安装"}</span><div className="fingerprints">{preview.key_fingerprints.map((fingerprint) => <code key={fingerprint}>{fingerprint}</code>)}</div></div>}
          {preview.warnings.map((warning) => <p className="command-warning" key={warning}><AlertTriangle size={14}/>{warning}</p>)}
          <pre>{preview.commands.join("\n")}</pre>
        </div>
      </details>;
    })}</div> : <p className="review-missing">该历史预检没有命令快照，不能确认执行。请重新生成预检。</p>}
    <footer><label><input aria-label="我已审阅以上命令" type="checkbox" checked={confirmed} disabled={!reviewable} onChange={(event) => onConfirmed(event.target.checked)}/>我已审阅以上命令</label><Button disabled={!reviewable || !confirmed} onClick={onExecute}>{executeLabel}</Button></footer>
  </section>;
}
