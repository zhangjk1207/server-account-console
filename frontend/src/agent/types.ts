export type AgentOverview = {
  machines: { total: number; reachable: number; attention: number };
  members: { active: number; with_keys: number };
  grants: { active: number };
  runs: { active: number; failed_recently: number };
};

export type ConversationMessage = {
  id: string;
  role: "operator" | "agent";
  text: string;
  pending?: boolean;
};

export type ActivityItem = {
  id: string;
  label: string;
  detail: string;
  state: "running" | "complete" | "error";
};
