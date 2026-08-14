# Agent-native architecture

## Product interaction model

The web workbench follows the governed task pattern used by mature agent products such as DataFoundry: a persistent Operation pane, a centered conversation with visible tool steps, and a synchronized task console for overview, trace, details, approvals, and outputs. Machines and model profiles are workspace resources; the selected model and Machine scope are visible next to the prompt.

An empty workspace is blocked by onboarding until both a model profile and a managed Machine exist. Model keys and SSH credentials are never returned by public read APIs.

The product is an access control plane with an agent interface, not a chat box attached to CRUD screens. The Agent turns an administrator's goal into evidence and a structured Plan. The deterministic control plane validates and executes that Plan.

```text
Administrator
    |
    v
Agent Workbench (React)
    |  prompt + SSE events
    v
pi Agent Runtime (TypeScript)
    |  allowlisted domain tools
    v
Control Plane (FastAPI) ---> SQLite
    |  immutable preview / approval gate
    v
Ansible Runner ---> Managed machines
```

## Trust boundaries

1. The Agent may inspect machine, member, grant, policy, and run metadata through authenticated APIs.
2. The Agent may prepare a preview only through typed domain tools. It cannot construct arbitrary shell commands.
3. A preview is an immutable Plan candidate. Any relevant state drift invalidates it.
4. Only an administrator can approve execution. Approval is scoped to the preview identifier and snapshot.
5. FastAPI revalidates credentials, fingerprints, grant state, and snapshots immediately before execution.
6. Secrets never enter prompts, Agent messages, tool results, plan snapshots, or event streams.

## Runtime contract

The Agent Runtime owns conversational Operations and pi session lifecycle. FastAPI owns domain state and Runs. Initial integration uses HTTP and SSE because execution feedback is server-to-client and does not require bidirectional WebSocket semantics.

The first tool set is deliberately small:

- `get_control_plane_overview`
- `list_machines`
- `list_members`
- `get_member_access`
- `list_recent_runs`

Mutation tools will be added one workflow at a time only after their typed Plan schema and approval behavior are covered by contract tests.

## Product model

The primary screen is an Operation workspace with three synchronized areas: the conversation, the Agent activity trail, and the current Plan or evidence. Inventory screens remain available for deliberate manual maintenance and incident recovery.
