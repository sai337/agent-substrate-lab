# Architecture

Facts from the Agent Substrate v1.0.0 README, architecture and egress guides (links at the end).

## Concepts
- **Actor**: a stateful workload (here, one agent) with an identity `actor:<atespace>:<name>`.
- **Atespace**: the isolation and naming boundary actors, templates and policies live in.
- **ActorTemplate**: what an actor runs (containers, volumes, snapshot fidelity, worker selector).
  Immutable. Its first actor is built into a *golden snapshot* that new actors start from.
- **WorkerPool**: Kubernetes custom resource; a set of warm worker pods with a sandbox class (gVisor or microVM).
- **Snapshot fidelity**: MEMORY (RAM + rootfs + volumes), ROOTFS, or VOLUMES. This lab uses MEMORY.

## Components
| Component | Role |
|---|---|
| ate-api-server | API for actors, templates, egress policies; Postgres-backed |
| ate-controller | reconciles WorkerPools into worker pods |
| atelet (DaemonSet) | per-node agent: places actors on workers, takes and restores snapshots; its objectstore sidecar moves them to the store |
| atenet-router | the only ingress; authenticates callers by SPIFFE ID; resumes suspended actors on request |
| atenet-egress | external policy enforcement point; mTLS from each actor's own certificate; per-request policy; credential injection |
| ate-idp-server / podcert controller | per-actor SPIFFE X.509 certs and JWTs |

## Request flow (call a suspended actor)
1. Client → atenet-router (mTLS; SPIFFE ID must be in the ingress allow list).
2. Router sees the actor is SUSPENDED → asks for a resume → atelet restores the snapshot onto a free worker.
3. The wakeup probe passes → the request is forwarded.
4. After idling, the actor is suspended again and the worker is free for another actor.

## Egress flow
Actor dials plain TCP → nftables redirects into atunnel → mTLS CONNECT with the actor's certificate
→ atenet-egress checks that the actor is real and RUNNING, then applies its EgressPolicy (first match
wins). `https` rules terminate TLS at the gateway (the actor trusts the gateway CA through the
`egress-mitm.ate.dev` trust bundle), which is what makes credential injection possible.
No policy means no tunnel.

## Sources
- README v1.0.0: https://github.com/agent-substrate/substrate/blob/v1.0.0/README.md
- Architecture: https://github.com/agent-substrate/substrate/blob/v1.0.0/docs/concepts/architecture.md
- Egress traffic: https://github.com/agent-substrate/substrate/blob/v1.0.0/docs/guides/egress-traffic.md
- Trust bundle: https://github.com/agent-substrate/substrate/blob/v1.0.0/docs/guides/egress-trust-bundle.md
- kubectl ate: https://github.com/agent-substrate/substrate/blob/v1.0.0/docs/reference/kubectl-ate.md
- CNCF donation: https://opensource.googleblog.com/2026/11/sandboxing-untrusted-ai-agents-at-scale.html
