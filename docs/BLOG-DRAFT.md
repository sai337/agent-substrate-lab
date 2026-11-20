# Draft: "Agents are idle 95% of the time. Stop paying for a pod each."

**Problem.** One pod per agent works for ten agents, not ten thousand. Agents mostly wait on models,
tools and people, but a pod per agent holds memory and a scheduler slot the whole time.

**What Agent Substrate changes.** Actors on warm workers; idle actors snapshotted out; resume on
request; gVisor per actor; identity and egress outside the sandbox.

**What I built.** A stateful Go agent and a harness that checks 8 promises on my own cluster,
on kind every night and on EKS on demand.

**Results (kind, first green run).** 12 actors on 3 workers (4:1), no state lost; resume p50 139 ms, p95 168 ms; suspend 180 ms;
new actor to first answer 1.2 s from the golden snapshot; default egress denied, the allow-list opened exactly pypi.org;
the actor saw `4.19.0-gvisor`, no service-account token and no secrets. EKS numbers: next.

**Lessons so far.**
1. A snapshot holds process memory. Any secret the agent fetched is in it: encrypt the store and scope access to two service accounts.
2. `https` egress rules terminate TLS. The actor must trust the gateway CA, or allowed hosts look blocked.
3. Vendor resume numbers are GKE numbers. Measure on your own nodes.
5. Denied names fail at DNS (NXDOMAIN), and a new policy takes about 5 s to reach the actor. My first run failed on exactly that.
6. Idle means suspended: with 3 workers, the 4th running actor has nowhere to go. Design agents to suspend when done.
4. EKS is not an upstream target yet; say "pilot" until it runs green twice.

**Compare with OpenShell** (openshell-eks-lab): OpenShell is a per-sandbox policy proxy with strong L7
rules; Substrate is a density and lifecycle runtime with egress at a shared gateway. They solve
different halves of the same problem.
