# Test cases

Source of truth: [`app/sublab/checks.py`](../app/sublab/checks.py). Workload: the memory agent
([`app/memory-agent`](../app/memory-agent)), 12 actors on a 3-worker gVisor pool.

| ID | Severity | What it checks | How | Pass rule | Threat / risk |
|---|---|---|---|---|---|
| SUB-01 | critical | RAM and disk state survive suspend and resume | remember ×3 → `suspend --mode=sync` → state SUSPENDED → recall | memory = file = 3, same boot id | State loss or silent reboot across hibernation |
| SUB-02 | high | Suspended actors resume on demand | for each of 12 suspended actors: timed GET through the router, then suspend again | all succeed; p95 ≤ budget (kind 5 s, EKS 3 s) | Slow or failed wake-ups |
| SUB-03 | critical | 12 actors share 3 workers without losing state | create → remember → suspend, one at a time; then recall each | every actor keeps its count; ≥ 3 actors per worker | Density that only works for stateless work |
| SUB-04 | critical | No egress without a policy | `/fetch https://pypi.org/simple/` | fails (no tunnel; NXDOMAIN) | Exfiltration from a fresh actor |
| SUB-05 | critical | EgressPolicy allows exactly the listed host | apply `k8s/egress-allow-pypi.yaml`, poll ≤ 30 s; fetch pypi.org and example.com | pypi ok, example.com blocked | Allow-list wider than written |
| SUB-06 | critical | No service-account token or secrets | `/selfcheck` | answered; `sa_token=false`, no secret-like env vars | Credential theft by untrusted code |
| SUB-07 | high | Runs on a sandbox kernel | `/selfcheck` kernel release vs the host | differs from host (seen: `4.19.0-gvisor`) | Running unsandboxed by mistake |
| SUB-08 | medium | New actor starts from the golden snapshot | create → first recall, timed | 200; time recorded | Slow cold start |

Unit-level cases (no cluster): `tests/unit/test_checks.py` breaks one guarantee at a time in a
fake Substrate (lost memory, open egress, leaked secrets, host kernel, slow resume, no free worker,
silent self-check) and asserts the gate fails with the right ID. Go agent: `app/memory-agent/main_test.go`.
