# Enterprise path (EKS, experimental)

Upstream tests kind and GKE. EKS is not an upstream target, so this path is a pilot: expect the
first run to need fixes, and treat every result as ours, not the vendor's.

## What is different from kind
| Area | kind POC | EKS pilot |
|---|---|---|
| Images | built from source with ko into localhost:5001 | published release images under `ghcr.io/agent-substrate/substrate` (tag v1.0.0) |
| Snapshots | local S3-compatible store (rustfs) from the kind overlay | S3 bucket, KMS-encrypted, public access blocked |
| Snapshot credentials | static lab keys | EKS Pod Identity for `atelet` and `ate-api-server` only |
| NetworkPolicy | kind CNI | VPC CNI with `enableNetworkPolicy=true` |
| Agent image | localhost:5001 | ECR, immutable tags, scan on push |

## One-time setup
1. `aws cloudformation deploy --template-file infra/eks/bootstrap/github-oidc.yaml --stack-name sublab-github-oidc --capabilities CAPABILITY_NAMED_IAM --parameter-overrides Repo=sai337/agent-substrate-lab`
2. Repo environment `eks` with you as required reviewer; variables `AWS_ROLE_ARN`, `AWS_REGION`; optional secret `BUDGET_EMAIL`.
3. Actions → `eks-e2e` → Run.

## Production gaps (before anyone depends on it)
- External Postgres for ate-api-server (`ateapi.postgres.*`), backups, HA.
- Your IdP federated with actor JWTs (`docs/guides/actor-jwt-federation.md` upstream).
- Credential injection with a real secret store instead of the default-deny `k8s.io` provider.
- SLOs and alerts from the upstream `slos-and-alerts` guide; OTel to your tracing backend.
- Least-privilege deploy role; S3 lifecycle rules for old snapshots.
