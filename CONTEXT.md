# Server Access Control

This context describes how an administrator delegates and governs Linux server access through an agent-assisted control plane.

## Language

**Task Console**:
The synchronized Overview, Trace, Details, Approval, and Output views for one Operation.

**Workspace Resource**:
A model profile, Machine, Access Policy, skill, or tool that may be attached to an Operation.

**Tool Step**:
One typed control-plane call with sanitized inputs, status, and result evidence.

**Member**:
A person whose Linux identities and SSH public keys are managed by the control plane.
_Avoid_: User, account

**Machine**:
A Linux host registered with verified administrator credentials and a pinned host fingerprint.
_Avoid_: Server, node, target

**Access Grant**:
The managed relationship that allows one Member to use one Linux account on one Machine.
_Avoid_: Permission, binding

**Access Policy**:
A reusable declaration of supplementary groups and sudo rules applied to an Access Grant.
_Avoid_: Permission template, role

**Operation**:
A user goal being investigated or carried out by the Agent, including its conversation and evidence trail.
_Avoid_: Chat, task, job

**Plan**:
The Agent's structured, reviewable proposal for changing control-plane state.
_Avoid_: Answer, command list

**Approval**:
An administrator's explicit authorization for one immutable Plan to cross a risk boundary.
_Avoid_: Confirmation, consent

**Execution**:
The deterministic application of an approved Plan through the control plane and Ansible executor.
_Avoid_: Tool call, Agent action

**Run**:
The durable record of a preview or Execution, including per-Machine outcomes and sanitized events.
_Avoid_: Operation, task
