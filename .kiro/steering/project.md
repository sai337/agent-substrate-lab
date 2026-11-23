---
inclusion: always
---
# agent-substrate-lab: working rules

Goal: deploy CNCF Agent Substrate v1.0.0 on EKS (pilot: EKS is not upstream-tested), run the
memory agent and the 8 checks, record results, tear down. docs/DEPLOYMENT.md is the source of truth.

Rules
- AWS: only `$AWS_PROFILE` (personal lab account). Region default `us-west-2`. Always end with `terraform destroy` unless told to keep it.
- Never commit secrets, keys or account IDs. `.work/` stays untracked.
- Commits: author `sai337 <sai.devop@gmail.com>`, no co-author or tool attribution lines.
- Pins live in `versions.env` (commit SHA, not the tag object). Do not bump without re-reading docs/SECURITY-VET.md.
- Never copy actor snapshots between environments (they contain process memory).

Definition of done
1. `make test` passes.
2. `evals/results/<date>-eks/summary.md` shows `Gate: PASS` 8/8; snapshot objects exist in the S3 bucket.
3. docs/EVALS.md results table has an EKS row (p50, p95, suspend, cold start, kernel).
4. Any fix needed for EKS is recorded in docs/RUNBOOK.md and committed.
5. `terraform destroy` completed.
