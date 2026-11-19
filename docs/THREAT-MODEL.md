# Threat model

Assumption, as upstream states it: every actor is untrusted and the actors are mutually hostile.

| # | Threat | Substrate control | Check |
|---|---|---|---|
| T1 | Exfiltrate to any host | no policy = no egress tunnel | SUB-04 |
| T2 | Exfiltrate while some hosts are allowed | per-actor EgressPolicy, first match wins | SUB-05 |
| T3 | Steal credentials from the sandbox | credentials injected at the egress gateway, never in the actor | SUB-06 |
| T4 | Use a Kubernetes token | no SA token in actors | SUB-06 |
| T5 | Kernel escape to the host | gVisor (or microVM) per actor | SUB-07 |
| T6 | State tampering or loss across hibernation | snapshots handled by atelet + sidecar, not the actor | SUB-01, SUB-03 |
| T7 | Denial of service by holding workers | oversubscription + suspend of idle actors | SUB-03 |
| T8 | Snapshot theft from the store | S3 KMS, public access block, Pod Identity scoped to two SAs | EKS Terraform |
| T9 | Impersonating another actor at egress | gateway checks the cert UID is a real RUNNING actor | upstream egress demo |

Not covered here: snapshot contents contain process memory (secrets an agent fetched would be in the
snapshot), cross-actor side channels on a shared worker, and DNS-based exfiltration beyond the
policy's hostnames.
