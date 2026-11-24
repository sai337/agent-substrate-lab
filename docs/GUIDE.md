# Agent Substrate lab: the plain-language guide

Everything about this project in simple words, from what it is to every component, flow, command and signal. The same content, with diagrams, is the bible page at `site/index.html` and the matching tab in the Study Bible.

## Start here: the whole idea in plain words

**The problem.** An AI agent spends most of its life waiting for someone to talk to it. Give every agent its own Kubernetes pod and you pay for 1,000 pods that mostly sit idle. Delete the pods to save money and the agents lose their memory.

**What Substrate does.** It saves a sleeping agent (RAM, files, running process) as a *snapshot*, frees the pod, and wakes the agent on any free pod in about 150 ms when someone talks to it again, with its memory intact. That is how 12 agents share 3 pods in this lab.

### Think of it as a hotel

| Substrate word               | Plain meaning                                                       | Hotel version                                               |
|------------------------------|---------------------------------------------------------------------|-------------------------------------------------------------|
| Actor                        | One agent instance, with its own memory and files                   | A guest                                                     |
| Worker (WorkerPool)          | A warm pod that hosts one awake agent at a time                     | A room                                                      |
| Suspend / snapshot           | Freeze the agent's RAM and disk and save it                         | Guest checks out, luggage goes to storage                   |
| Resume                       | Load the snapshot into any free worker                              | Guest returns, gets any free room, luggage already unpacked |
| ActorTemplate                | The starting image every new agent is cloned from (golden snapshot) | The standard room setup                                     |
| atenet-router                | Receives each request and wakes the right agent                     | Front desk                                                  |
| ate-api-server + Postgres    | Records where every agent is and whether it is awake                | The hotel register                                          |
| atelet                       | Per-node helper that moves snapshots and restores agents            | Housekeeping on each floor                                  |
| atenet-egress + EgressPolicy | The only way out to the internet, allowlist only                    | The guarded exit with a guest list                          |
| gVisor                       | A fake kernel, so the agent never touches the real one              | A locked room inside a locked building                      |
| Atespace                     | A tenant folder: names, permissions and policies live inside it     | A floor reserved for one company                            |

## One request, every component

Numbers follow the steps below. Grey arrows are the request path; the green arrow is the only allowed way out.

*Diagram: open `site/index.html` (the bible page) for the drawing.*

**1. Name the actor**

Your app sends the HTTP request to the router with header `ate-target-actor: <atespace>/<actor>`. That header, not the Host, picks the agent.

**2. Router asks to resume**

Envoy pauses the request; its ext_proc calls `ResumeActor` on the API server. If the actor is already RUNNING it is a no-op that returns the worker IP.

**3. Pick a room**

The scheduler claims a worker with room in the actor's WorkerPool (an atomic assignment in Postgres, no Kubernetes scheduling) and tells that node's atelet to restore.

**4. Unpack the snapshot**

atelet uses the node-local copy if it has one, else the objectstore-plugin downloads it from S3. ateworker restores it with gVisor (`runsc restore`). State becomes RUNNING.

**5. Deliver the request**

The router opens an mTLS CONNECT tunnel to atunnel on worker port 8443, which hands the request to the actor. The response goes back the same way.

**6. Only the guest list gets out**

Every outbound connection is redirected into atunnel and carried to atenet-egress. No EgressPolicy means no tunnel; unlisted names get NXDOMAIN.

**7. Check out**

Someone calls `SuspendActor`. ateworker checkpoints, atelet keeps a local copy and uploads to S3, and the worker is wiped and returned to the pool.

### If every room is full

The router "parks" the request and keeps retrying the resume with backoff for up to 5 s (`--parked-request-budget`), because another actor usually frees a worker within milliseconds. After that the client gets `503 no worker has room for the actor`.

## Nodes, pods and who creates what

*Diagram: open `site/index.html` (the bible page) for the drawing.*

### Node

The machine: an EC2 instance in the `substrate-worker` node group (Terraform), or a Docker container in kind.

### atelet

A DaemonSet pod, one per node: housekeeping for that node's workers. It does not create worker pods; it supervises the ones Kubernetes put on its node.

### Worker pods

You declare a `WorkerPool` (3 here). atecontroller turns it into a normal Deployment, and the Kubernetes scheduler places the pods on nodes. They stay up; actors move in and out of them, so a wake-up never waits for a new pod.

### Inside a worker

`ateworker` takes run / checkpoint / restore orders from atelet, `atunnel` is the door for traffic in and out, and the gVisor sandbox is where the actor runs. A worker has a capacity; it hosts as many awake actors as fit.

### "Your app / gateway picks the actor name"

Substrate knows actor names, not people. Something you own sits in front of it and, for every request: (1) authenticates the user, (2) looks up `(user, session) → actor name` in its own table, (3) calls `CreateActor` from the template if the session is new, (4) forwards to atenet-router with `ate-target-actor: <atespace>/<actor>`. In this lab the `sublab` harness plays that role. In production it is one small service plus one table, and it is also where an idle-suspender belongs.

## gVisor vs NVIDIA OpenShell vs Substrate

Not competitors: different layers. gVisor is the walls, OpenShell is a guard at each door, Substrate is the hotel.

|                     | gVisor                                                                                                                                                                                                                                      | NVIDIA OpenShell                                                                                                     | Agent Substrate                                                                               |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| What it is          | A sandbox runtime: a Linux kernel re-written in Go, running in user space                                                                                                                                                                   | An agent sandbox platform: gateway, per-sandbox policy proxy, CLI                                                    | An actor runtime: many sleeping agents, few warm pods                                         |
| Question it answers | If the agent is hijacked, can it break out onto the machine?                                                                                                                                                                                | What is this agent allowed to do and talk to?                                                                        | How do I run thousands of mostly idle agents cheaply without losing their memory?             |
| How                 | Intercepts every system call, so the agent never touches the host kernel                                                                                                                                                                    | Every outbound call passes a proxy that checks host, program (binary), HTTP method and path, read-only or read-write | Snapshots idle actors to S3, resumes on any warm worker in about 150 ms, routes by actor name |
| Network rules       | None of its own                                                                                                                                                                                                                             | Fine-grained, per sandbox (L7)                                                                                       | Per actor, by hostname and port at a shared egress gateway                                    |
| Secrets             | n/a                                                                                                                                                                                                                                         | Providers inject them; the agent never holds them                                                                    | The egress gateway injects them; the agent never holds them                                   |
| Sleep / wake        | Can checkpoint and restore a process (Substrate uses this)                                                                                                                                                                                  | No: one always-on pod per sandbox                                                                                    | Yes: that is the product                                                                      |
| Together            | OpenShell can run its sandboxes on a gVisor runtime class (strong walls + strict guard). Substrate already uses gVisor but its exit rules are coarser. The promotion repo uses OpenShell for tight per-agent rules and Substrate for scale. |                                                                                                                      |                                                                                               |

## Every component and what it can do

Everything an install of Substrate v1.0.0 runs, top to bottom. Sources: upstream docs/concepts/architecture.md and cmd/ in the v1.0.0 tag.

| Component                     | Runs as                                                          | Capabilities                                                                                                                                                                                                                                                                                                                                                    |
|-------------------------------|------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **kubectl ate**               | CLI plugin on your laptop / CI                                   | Create, get, suspend, resume, revert, delete actors; create templates, egress policies, tags; `kubectl ate logs actor`; `kubectl ate proxy` to an actor. Talks gRPC to the API server.                                                                                                                                                                          |
| **atenet-router**             | Deployment (Envoy + ext_proc)                                    | Ingress for every actor. Reads `ate-target-actor`, calls ResumeActor, resolves the worker, opens an mTLS CONNECT tunnel to that worker. Parks requests during saturation (5 s). Supports other actor ports via HTTP CONNECT. Re-routes each request if the actor moved workers. Emits `atenet.router.route.duration` and traces (1% sampled).                   |
| **ate-api-server**            | Deployment, gRPC                                                 | The brain. State store (Postgres), scheduler (picks a worker), workflow engine (multi-step resume/suspend: lock, download, restore), authentication (mTLS, OIDC) and per-atespace authorization (embedded OpenFGA). Mints short-lived actor JWTs. Owns every Actor, Worker, ActorTemplate, Tag, EgressPolicy and access policy record.                          |
| **Postgres**                  | In-cluster (upstream manifests); a managed database is an option | Holds the high-churn records so millions of actors never touch the Kubernetes API server.                                                                                                                                                                                                                                                                       |
| **atecontroller**             | Deployment                                                       | Turns each `WorkerPool` CRD into a Kubernetes Deployment of worker pods; reports desired/ready workers.                                                                                                                                                                                                                                                         |
| **WorkerPool, SandboxConfig** | Kubernetes CRDs                                                  | WorkerPool: how many warm rooms, which sandbox class (gvisor or microvm), node selector, tolerations. SandboxConfig: which runtime binaries and versions a class uses.                                                                                                                                                                                          |
| **atelet**                    | DaemonSet (one per node)                                         | Supervises the worker pods on its node: run, checkpoint, restore. Keeps a node-local copy of the latest snapshot so the next resume on that node skips S3 (until `--snapshot-detach-delay`). Uploads in the background after an async suspend. Content-addressed cache of sandbox binaries. OTLP relay for worker telemetry. Has no storage credentials itself. |
| **objectstore-plugin**        | Sidecar in atelet and in ate-api-server                          | The only thing that talks to S3 or GCS. In atelet: upload and fetch snapshot files, fetch sandbox assets (sha256-checked). In the API server: copy and delete whole snapshots (tags, garbage collection).                                                                                                                                                       |
| **S3 snapshot bucket**        | AWS S3 (EKS) / local (kind)                                      | Durable home of every suspended actor: memory, rootfs changes and DurableDir volumes. KMS-encrypted in our Terraform. Reached only through the plugin, with EKS Pod Identity.                                                                                                                                                                                   |
| **Worker pod: ateworker**     | Pod from the WorkerPool                                          | gRPC `RunWorkload`, `CheckpointWorkload`, `RestoreWorkload` for atelet. Runs the actor under gVisor `runsc` (or a Kata microVM). Samples per-actor CPU and memory usage. Hosts atunnel.                                                                                                                                                                         |
| **atunnel**                   | Inside ateworker                                                 | Inbound: accepts the router's mTLS tunnel on 8443 and forwards to the actor's private veth. Outbound: catches every actor TCP connection and carries it to atenet-egress.                                                                                                                                                                                       |
| **gVisor (runsc)**            | Inside the worker pod                                            | A user-space kernel for each actor (our check shows `4.19.0-gvisor`). Does the actual checkpoint and restore of the process tree.                                                                                                                                                                                                                               |
| **atenet-egress**             | Deployment                                                       | Enforces each actor's EgressPolicy (hostnames, ports, http or https). Denied names get NXDOMAIN. For https rules it terminates TLS with its own CA (trust bundle mounted in the actor at `/run/ate`) so it can inject credentials or an actor JWT into headers. Policy changes apply in about 5 s.                                                              |
| **Credential provider**       | Deployment                                                       | Hands real secrets to the egress gateway for header replacement. Its NetworkPolicy admits only the gateway, so the actor never holds a secret.                                                                                                                                                                                                                  |
| **ate-idp-server**            | Deployment                                                       | Publishes the OIDC discovery document and keys so outside services can verify actor JWTs (for example a cloud token exchange).                                                                                                                                                                                                                                  |
| **podcertcontroller**         | Deployment                                                       | Issues pod certificates from a local CA: workload identity for mTLS between components, and Postgres login certificates for the API server.                                                                                                                                                                                                                     |
| **Actor (our memory-agent)**  | A process inside gVisor in a worker pod                          | Whatever your agent does. Ours is a small Go test probe: see "The memory agent" below.                                                                                                                                                                                                                                                                          |
| **OTel collector**            | Optional, you install it                                         | Receives OTLP logs, metrics and traces from every component. Not installed by our lab scripts today.                                                                                                                                                                                                                                                            |

## What the API server remembers, and what it does not

### Actor record

`atespace`, `name`, `uid` (unique for the actor's lifetime), `version`, create/update/delete times, template reference, worker selector, source tag, and status: state (SUSPENDED, RESUMING, RUNNING, SUSPENDING, CRASHED), worker assignment (IP), assigned node, volumes, crash info, and the list of snapshots.

### Other records

Worker: id, ACTIVE / UNAVAILABLE / DRAINING, capacity, which actors it hosts. ActorTemplate: image, resources, snapshot fidelity, golden snapshot (immutable). Tag: a pinned, named copy of a snapshot. EgressPolicy per actor. Access policies per atespace.

### Not stored at all

No user, no session, no conversation history, no request IDs, no free-form labels on actors. Substrate knows actors, not people. Mapping a user or session to an actor is your app's job (next section).

### Who triggers suspend?

In v1.0.0 a suspend happens when something calls `SuspendActor`: your app, a controller you write, or our test harness (it suspends each actor after use). Async (the default) returns once the local checkpoint is written and uploads later; `--mode=sync` waits for the S3 upload. The code has plumbing for a worker to ask for a suspend when an actor goes idle, but we found no idle timer wired to it in v1.0.0, so plan an idle-suspender in your layer.

| Snapshot fidelity (ActorTemplate) | What comes back after resume                                                                   |
|-----------------------------------|------------------------------------------------------------------------------------------------|
| VOLUMES                           | Only the DurableDir folders. The process cold-boots.                                           |
| ROOTFS                            | Volumes plus files written anywhere in the container. Cold-boots.                              |
| MEMORY (default, this lab)        | All of the above plus the running process and its RAM: the same process continues mid-thought. |

## The memory agent: every path

app/memory-agent/main.go, 172 lines of Go, listening on :8080. It is a test probe built to make the platform's promises visible from outside, not a real AI agent.

| Path       | Method / input         | Returns                                   | Proves                                                                                                            |
|------------|------------------------|-------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| /readyz    | GET                    | 200, empty                                | The actor is up and routable (readiness).                                                                         |
| /remember  | POST `?note=<text>`    | state JSON                                | Adds the note to a list in RAM and appends a line to `/home/agent/notes.txt` (the DurableDir).                    |
| /recall    | GET                    | state JSON                                | Reads back what survived a suspend/resume.                                                                        |
| /fetch     | GET `?url=https://...` | url, ok, status, ms, error                | Tries one outbound GET (body discarded). Used for SUB-04 (blocked) and SUB-05 (only pypi.org allowed).            |
| /selfcheck | GET                    | kernel_release, uid, sa_token, secret_env | What a hijacked agent would see: gVisor kernel, no Kubernetes token, no secret-looking env vars (SUB-06, SUB-07). |

**State JSON** = `memory_count` (notes in RAM), `file_count` (lines in notes.txt), `boot_id` (process id + start time, set once per real start), `started_at`, `hostname`. If both counters keep counting and `boot_id` does not change after a resume, Substrate restored the same process: that is SUB-01.

### How it "remembers"

Two copies of each note. RAM: survives only a MEMORY-fidelity snapshot. Disk (notes.txt in the DurableDir): survives every fidelity. That split is what lets one check tell a true restore from a reboot.

### What it does not do

No LLM calls, no context window, no conversation history, no users or sessions, no knowledge graph, no metrics endpoint. Its only log line is `memory-agent listening on :8080`. Those belong to your real agent; the next section shows how they map onto Substrate.

## Users, sessions, context and request IDs: how to build them on Substrate

Substrate gives you one thing: an actor whose whole memory survives sleep. Everything about people lives in a thin layer you own (your app or the gateway) plus inside the agent.

**1. Tenant = atespace**

One atespace per team or customer. Permissions (OpenFGA), templates, egress policies and tags are scoped to it.

**2. Session = actor**

Your layer maps `(user, session)` to an actor name such as `u-<hash>-s-<n>`, creates it from the template on first use, and sets `ate-target-actor` on every request. One actor per session means each snapshot is that session's memory, nothing else.

**3. Context lives in the actor**

Conversation history, the running context window and any knowledge graph sit in the agent's RAM and in its DurableDir (for example `history.jsonl` or a SQLite graph). MEMORY snapshots carry all of it, so the agent wakes mid-conversation.

**4. Long-term memory outside**

Facts that must outlive a session, or be shared across sessions, go to an external store (vector DB, graph DB) the agent reaches through an EgressPolicy rule, with credentials injected by the gateway.

**5. Request IDs**

Snapshots are taken per suspend, not per request. Track requests with W3C `traceparent` through the router and with the agent's own log lines; tie them to the actor by `ate.actor.uid`.

**6. Checkpoints you can go back to**

`CreateTag` pins a named copy of a snapshot ("before-risky-step"). `RevertActor` discards unsaved state and returns to the last durable snapshot.

### A snapshot is everything the agent saw

It holds the session's raw RAM: prompts, PII, tokens the agent read. Keep one session per actor, encrypt the bucket (KMS), delete actors when sessions end (that garbage-collects their snapshots), and never copy snapshots between environments.

## Logs, metrics and traces: what exists and how to export them

| Signal                         | What Substrate gives you                                                                                                                                                                                                                                                                                                                                                       | How to get it out                                                                                                                                                                                                                                                   |
|--------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Actor logs**                 | The actor's stdout/stderr, wrapped as JSON with `ate.actor.name`, `ate.actor.uid`, `ate.atespace`, `ate.template.name`, container name. Lifecycle lines too ("Actor restored").                                                                                                                                                                                                | Live: `kubectl ate logs actor <name> -a <atespace> -f` (current worker only). History across workers and suspends: ship container logs with Fluent Bit to CloudWatch Logs, OpenSearch or Loki, and query by `ate.actor.uid`.                                        |
| **Usage events**               | "Actor usage sampled" log records per actor: initial, periodic, final; CPU time, memory usage, working set, peak.                                                                                                                                                                                                                                                              | Same log pipeline. This is your per-actor cost record (identity lives in logs, not in metrics, to keep cardinality low).                                                                                                                                            |
| **Platform metrics**           | OpenTelemetry instruments, for example `ate.actor.lifecycle.operation.duration` (create/resume/suspend), `ate.actor.restore.duration`, `ate.actor.checkpoint.duration`, `ate.scheduler.assignment.duration`, `ate.workerpool.workers` (idle / partial / at_capacity), `ate.actor.crashes`, `atelet.snapshot.size`, `atenet.router.route.duration`, `rpc.server.call.duration`. | Push: set `OTEL_EXPORTER_OTLP_ENDPOINT` in the `ate-otel-config` ConfigMap and restart; on EKS point it at an ADOT collector that writes to Amazon Managed Prometheus or CloudWatch. Pull: Prometheus scrapes `/metrics` on :9090 of ateapi, atelet and the router. |
| **Traces**                     | Head-sampled request traces: 10% by default, 1% at the router.                                                                                                                                                                                                                                                                                                                 | Same OTLP endpoint into Jaeger, Tempo or X-Ray (through ADOT).                                                                                                                                                                                                      |
| **Worker telemetry**           | ateworker sends its logs, metrics and traces over a unix socket to atelet's relay, which forwards them.                                                                                                                                                                                                                                                                        | Nothing extra: follows atelet's endpoint.                                                                                                                                                                                                                           |
| **Your agent's own telemetry** | Nothing automatic: the actor's OTel SDK is just another outbound connection.                                                                                                                                                                                                                                                                                                   | Add an `http` EgressPolicy rule for the collector's Service on ports 4317/4318, or the export fails with NXDOMAIN.                                                                                                                                                  |

In this lab today: the harness measures resume, suspend and cold start itself and writes `evals/results/<date>-<target>/`. No collector is installed by our scripts, so the OTLP push has nowhere to go until you add one.
