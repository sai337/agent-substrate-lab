# Plan

## Goal
Measure, on our own clusters, whether CNCF Agent Substrate gives stateful untrusted agents
density (many actors per worker), continuity (state across hibernation) and containment
(default-deny egress, no credentials, sandbox kernel).

## Scope
In: Substrate v1.0.0 on kind, memory agent, 8 checks, CI gates, EKS pilot with S3 snapshots.
Out (next): microVM sandbox class, credential injection with a real secret store, 1,000+ actor
scale runs, kagent / Agent Executor on top.

## POC vs enterprise
| | POC (kind) | Enterprise pilot (EKS) |
|---|---|---|
| Install | `ate-setup --kind` from pinned source | `ate-setup --config` with release images |
| Snapshots | local S3-compatible store | S3 + KMS + Pod Identity |
| Gate | `SUBLAB_RESUME_P95_MS=5000` | 3000 |

## Acceptance
| # | Done when | Proven by |
|---|---|---|
| A1 | agent keeps memory + disk counts, restarts reset only memory | Go tests |
| A2 | healthy model passes; each broken guarantee fails the gate with its ID | `tests/unit` |
| A3 | all 8 checks pass on kind | `e2e-kind` |
| A4 | all 8 checks pass on EKS, then destroy | `eks-e2e` |

## Milestones
1. M1 repo, agent, harness, unit tests (done)
2. M2 green `e2e-kind` with results
3. M3 EKS pilot green
4. M4 scale run (100+ actors) and the blog post
