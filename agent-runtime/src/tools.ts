import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

import { ControlPlaneClient, type Overview } from "./control-plane.js";

type Machine = { id: string; name: string; address: string; status: string; tags: string[]; data_root: string | null };
type Member = { id: string; username: string; display_name: string; enabled: boolean };
type Grant = { host_name: string; username: string; template_name: string | null; state: string; account_origin: string };
type Run = { id: string; kind: string; state: string; created_at: string; request_snapshot: { hosts?: { name: string }[] } };

function result(data: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(data) }], details: data };
}

export function createControlPlaneTools(client: ControlPlaneClient) {
  return [
    defineTool({
      name: "get_control_plane_overview",
      label: "Read fleet overview",
      description: "Get aggregate machine, member, grant, and recent run health without secrets.",
      parameters: Type.Object({}),
      execute: async () => result(await client.get<Overview>("/agent-context/overview")),
    }),
    defineTool({
      name: "list_machines",
      label: "Inspect machines",
      description: "List registered machines and their current connectivity state.",
      parameters: Type.Object({ status: Type.Optional(Type.String()) }),
      execute: async (_id, params) => {
        const machines = await client.get<Machine[]>("/hosts");
        return result(params.status ? machines.filter((machine) => machine.status === params.status) : machines);
      },
    }),
    defineTool({
      name: "list_members",
      label: "Inspect members",
      description: "List managed members. Disabled members are included only when requested.",
      parameters: Type.Object({ include_disabled: Type.Optional(Type.Boolean()) }),
      execute: async (_id, params) => {
        const members = await client.get<Member[]>("/users");
        return result(params.include_disabled ? members : members.filter((member) => member.enabled));
      },
    }),
    defineTool({
      name: "get_member_access",
      label: "Inspect member access",
      description: "Get active and historical access grants for one member ID.",
      parameters: Type.Object({ member_id: Type.String() }),
      execute: async (_id, params) => result(await client.get<Grant[]>(`/users/${encodeURIComponent(params.member_id)}/access-grants`)),
    }),
    defineTool({
      name: "list_recent_runs",
      label: "Inspect recent runs",
      description: "List recent preview and execution runs with sanitized state and targets.",
      parameters: Type.Object({ limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })) }),
      execute: async (_id, params) => {
        const runs = await client.get<Run[]>("/jobs");
        return result(runs.slice(0, params.limit ?? 8));
      },
    }),
  ];
}
