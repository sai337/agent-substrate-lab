# Evals

| Kind | Question | Where |
|---|---|---|
| **Platform (runtime) evals** | Does Substrate keep its promises for this agent: state, density, resume, egress, isolation? | this repo: 8 checks, `sublab run` |
| **Quality (behaviour) evals** | Is this agent version better than the last one? | the agent's eval set; see PROMOTION.md |

## The checks

Full table: [TEST-CASES.md](TEST-CASES.md). Code: [`app/sublab/checks.py`](../app/sublab/checks.py).

Scoring rules learned the hard way:
- **Idle means suspended.** With 3 workers, a 4th running actor has nowhere to go. The harness
  suspends each actor after use, the way real agents should behave; the fake driver in the unit
  tests enforces worker capacity so this cannot regress.
- **A check that got no answer is an error, not a pass** (SUB-06 requires a real self-check response).
- **Policies take about 5 s to apply.** Denied names fail at DNS (NXDOMAIN); SUB-05 polls before judging.

## Results so far (kind in GitHub Actions, 3 workers, 12 actors)

| Date | Gate | Resume p50 | Resume p95 | Suspend | New actor → first answer | Actor kernel |
|---|---|---|---|---|---|---|
| 20 Nov 2026 | 8/8 PASS | 139 ms | 168 ms | 180 ms | 1.24 s | 4.19.0-gvisor |
| 21 Nov 2026 | 8/8 PASS | 179 ms | 190 ms | 210 ms | 1.34 s | 4.19.0-gvisor |
| 22 Nov 2026 | 8/8 PASS | 134 ms | 145 ms | 151 ms | 1.23 s | 4.19.0-gvisor |
| 23 Nov 2026 | 8/8 PASS | 184 ms | 213 ms | 267 ms | 1.31 s | 4.19.0-gvisor |
| _next_ | EKS 1.34 + S3 snapshots | | | | | |

Shared CI runners are noisy; compare ranges, not single runs. The vendor's "<500 ms resume" is a
GKE figure and not directly comparable.

## Add a check

Add a block in `run_all`, a flag to `FakeDriver` that breaks the guarantee, and a parametrised
test proving the gate catches it. Push: `e2e-kind` runs it on a real cluster.
