import type { ActivityItem } from "./types";

export type LiveEvent = {
  id: string;
  job_id: string;
  host_id: string | null;
  level: string;
  message: string;
  created_at: string;
};

type StreamCallbacks = {
  onOperation: (operationId: string) => void;
  onText: (delta: string) => void;
  onActivity: (activity: ActivityItem) => void;
};

type AgentEnvelope = { type?: string; operation_id?: string; message?: string; event?: Record<string, unknown> };

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function consumeAgentEvent(envelope: AgentEnvelope, callbacks: StreamCallbacks): void {
  if (envelope.type === "operation" && envelope.operation_id) {
    callbacks.onOperation(envelope.operation_id);
    return;
  }
  if (envelope.type === "error") throw new Error(envelope.message || "Agent 运行失败");
  if (envelope.type !== "agent_event" || !envelope.event) return;

  const event = envelope.event;
  const eventType = stringValue(event.type);
  const assistantEvent = event.assistantMessageEvent as Record<string, unknown> | undefined;
  if (eventType === "message_update" && assistantEvent?.type === "text_delta") {
    callbacks.onText(stringValue(assistantEvent.delta));
    return;
  }

  const toolCall = (event.toolCall ?? event.tool) as Record<string, unknown> | undefined;
  const toolName = stringValue(toolCall?.name ?? event.toolName ?? event.tool_name);
  const toolCallId = stringValue(toolCall?.id ?? event.toolCallId ?? event.tool_call_id) || crypto.randomUUID();
  if (eventType.includes("tool") && toolName) {
    const failed = eventType.includes("error");
    const complete = eventType.includes("end") || eventType.includes("result");
    callbacks.onActivity({
      id: toolCallId,
      label: toolName.replaceAll("_", " "),
      detail: failed ? "工具调用失败" : complete ? "证据已返回" : "正在读取控制面",
      state: failed ? "error" : complete ? "complete" : "running",
    });
  }
}

export async function promptAgent(
  prompt: string,
  operationId: string | null,
  callbacks: StreamCallbacks,
): Promise<void> {
  const response = await fetch("/agent/operations/prompt", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, operation_id: operationId }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail || `Agent 服务不可用 (${response.status})`);
  }
  if (!response.body) throw new Error("Agent 响应不支持流式读取");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) consumeAgentEvent(JSON.parse(line) as AgentEnvelope, callbacks);
    }
    if (done) break;
  }
  if (buffer.trim()) consumeAgentEvent(JSON.parse(buffer) as AgentEnvelope, callbacks);
}
