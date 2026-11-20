# Runbook

| Symptom | Check | Fix |
|---|---|---|
| `ate-setup` fails building images | buildx config has `[registry."localhost:5001"] http = true` | in CI it is in the workflow; locally use `hack/create-kind-cluster.sh` first |
| template stays `building` | `kubectl ate get actor-template memory-agent -a lab-agents -o yaml` | image not pullable (digest from localhost:5001), or the wakeup probe port is not 8080 |
| actors never RUNNING | `kubectl ate get workers` | WorkerPool has no ACTIVE workers; check the copied worker image |
| SUB-01 fails with memory reset | template `snapshotConfig.preferredFidelity` | must be `SNAPSHOT_FIDELITY_MEMORY` for RAM to survive |
| SUB-05 allowed host fails with `no such host` | wait: a new policy reaches the actor's DNS relay in about 5 s; denied names get NXDOMAIN | the harness polls up to `SUBLAB_POLICY_WAIT_S` (30 s) |
| SUB-05 allowed host fails with a TLS error | `kubectl -n ate-system logs deployment/atenet-egress` | TLS trust: the actor needs `SSL_CERT_FILE=/run/ate/trust-bundle.pem` (already in the template) |
| SUB-02 over budget on kind | p95 in results.json | kind on a 4-vCPU runner is slow; raise `SUBLAB_RESUME_P95_MS` for kind, keep it tight on EKS |
| EKS snapshots fail | objectstore-plugin logs in atelet | Pod Identity association, `ATE_STORAGE_BACKEND=s3` and `AWS_REGION` on the sidecars |

Useful: `kubectl ate get actors -a lab-agents`, `kubectl ate logs actor <name> -a lab-agents`,
`kubectl ate suspend actor <name> -a lab-agents --mode=sync`.
