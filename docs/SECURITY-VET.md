# Third-party vet

Checked 2026-11-19 in a throwaway workspace. Source was read and scanned; nothing was run.

| Component | Source | Pin | Verdict |
|---|---|---|---|
| Agent Substrate | github.com/agent-substrate/substrate (CNCF Sandbox, Apache-2.0, govulncheck in CI) | v1.0.0 = `fd67f6204a7c287f658d080f6196ba1638744a10` | AMBER: large codebase (14k files incl. vendor/), not read line by line |
| Substrate release images (EKS) | ghcr.io/agent-substrate/substrate, published by the project's release workflow | tag v1.0.0; pin digests on first pull | AMBER |
| golang:1.23, distroless/static | official images | tags; pin digests in your registry | GREEN |

## Findings
| Check | Result |
|---|---|
| Phone-home / product telemetry endpoints in `cmd/`, `pkg/`, `internal/` | none found; "telemetry" hits are OpenTelemetry to an endpoint you configure |
| Hard-coded external URLs in Go sources | only doc links and in-cluster service names |
| Hidden Unicode in manifests, demos, hack scripts | 0 findings |
| Default credentials | the kind overlay uses static rustfs keys for a local store; never used on EKS |

## Containment
POC on throwaway kind clusters; EKS in a separate lab account with short-lived OIDC credentials and
destroy after the run. No conversation, memory or company data goes into any of it.
