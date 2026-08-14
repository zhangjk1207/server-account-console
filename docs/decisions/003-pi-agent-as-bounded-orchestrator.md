# ADR-003: Use pi as a bounded orchestration runtime

**Status:** Accepted

The control plane keeps FastAPI, SQLite, and Ansible as the authority for credentials, validation, previews, approvals, and execution. A separate TypeScript service embeds `@earendil-works/pi-coding-agent` for model sessions and streaming, but exposes only domain-specific tools backed by authenticated control-plane APIs; pi receives no shell, filesystem, SSH credential, or direct Ansible access. This split preserves the existing security boundary, allows the agent runtime to evolve independently, and prevents probabilistic model output from becoming an execution contract.

## Consequences

- Every mutating tool produces a reviewable Plan or preview; execution remains an explicit administrator action.
- Agent and control-plane events are correlated, but control-plane Runs are the authoritative audit record.
- The deployment gains one Node.js service and a private service-to-service URL.
