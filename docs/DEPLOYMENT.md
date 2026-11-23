# Deployment: EKS end to end from a laptop (or Kiro)

Creates the cluster, installs Agent Substrate v1.0.0 from the published release images with S3
snapshots, deploys the memory agent, runs the 8 checks and tears down. The `eks-e2e` workflow
runs the same steps.

**Personal lab AWS account with a budget only.** EKS is not an upstream-tested target for
Substrate (upstream tests kind and GKE): treat the first run as a pilot and expect a fix or two.

## 0. Prerequisites (10 min)

| Tool | Version | Check |
|---|---|---|
| AWS CLI v2 + lab profile | v2 | `aws sts get-caller-identity` |
| Terraform | ≥ 1.6 | `terraform version` |
| kubectl | ≥ 1.33 | `kubectl version --client` |
| Go | ≥ 1.27 (Substrate's installer and the `kubectl ate` plugin) | `go version` |
| Docker (running) | builds `linux/amd64` | `docker info` |
| Python | ≥ 3.11 | `python3 --version` |
| envsubst | gettext (macOS: `brew install gettext`) | `envsubst --version` |

```bash
export AWS_PROFILE=<lab-profile> AWS_REGION=us-west-2
export PATH="$PATH:$(go env GOPATH)/bin"          # so kubectl finds the `ate` plugin
git clone https://github.com/sai337/agent-substrate-lab && cd agent-substrate-lab
make install && make test                         # Go + harness tests, no cloud
```

## 1. Provision the infrastructure (15-20 min)

```bash
cd infra/eks/terraform
terraform init
terraform apply -var "region=$AWS_REGION" -var "budget_email=<you@example.com>"
cd ../../..
aws eks update-kubeconfig --name "$(terraform -chdir=infra/eks/terraform output -raw cluster_name)" --region "$AWS_REGION"
kubectl get nodes -L workload                     # 2 x system, 2 x substrate-worker
```

Creates: VPC, EKS 1.34 with VPC CNI NetworkPolicy on, node groups `system` and
`substrate-worker`, EBS CSI, an **S3 snapshot bucket** (KMS, public access blocked) with Pod
Identity for only `atelet` and `ate-api-server`, an ECR repo for the agent, optional budget alarm.

## 2. Install Substrate + the agent (15-25 min)

```bash
bash infra/eks/install.sh
```

In order: pinned source checkout (only for the installer and `kubectl ate`) → gp3 default
StorageClass → `ate-setup deploy ate-system --config .work/substrate-install.yaml` with
`ghcr.io/agent-substrate/substrate` v1.0.0 images → object-store sidecars switched to S3 →
memory agent built for `linux/amd64` and pushed to ECR → WorkerPool (3 workers, gVisor) →
atespace `lab-agents` → ActorTemplate → wait for the golden snapshot.

Check:
```bash
kubectl -n ate-system get pods                    # all Running
kubectl ate get workers                           # 3 ACTIVE in pool memory-agent
kubectl ate get actor-templates -a lab-agents     # golden tag set
```

## 3. Test end to end (2-4 min)

```bash
SUBLAB_RESUME_P95_MS=3000 make eks-test
cat evals/results/*-eks/summary.md
```

Pass criteria: **Gate: PASS, 8/8**. Record p50/p95 resume, suspend time and create-to-first-answer
in docs/EVALS.md. Confirm snapshots landed in S3:
```bash
aws s3 ls "s3://$(terraform -chdir=infra/eks/terraform output -raw snapshot_bucket)/" --recursive | head
```
Commit `evals/results/<date>-eks/` (author sai337).

## 4. Promotion demo (optional)

```bash
sublab policy-diff k8s/egress-allow-pypi.yaml <candidate-egress.yaml>     # G2: blocks new hosts without approval
```
See [PROMOTION.md](PROMOTION.md).

## 5. Tear down. Do not skip.

```bash
kubectl ate get actors -a lab-agents     # optional: see what is left; destroy removes everything
cd infra/eks/terraform && terraform destroy -var "region=$AWS_REGION"
```
The bucket and ECR repo are `force_destroy`/`force_delete`, so destroy removes snapshots too.

## If something fails

| Step | Symptom | Fix |
|---|---|---|
| 2 | `ate-setup` asks for GCP settings | the config file is not being read: check `.work/substrate-install.yaml` exists and is passed with `--config` |
| 2 | atelet objectstore-plugin `AccessDenied` | Pod Identity association names: service accounts `atelet`, `ate-api-server` in `ate-system` |
| 2 | worker pods CrashLoop | derived worker image name wrong: `kubectl -n lab-agents get workerpool memory-agent -o yaml`, compare with the atelet image repo |
| 2 | golden snapshot never ready | `kubectl ate get actor-template memory-agent -a lab-agents -o yaml`; usually image pull (ECR) or wakeup probe port 8080 |
| 3 | SUB-05 `no such host` | policy not yet applied (about 5 s); harness waits up to `SUBLAB_POLICY_WAIT_S` |
| 3 | SUB-02 over budget | record it; raise the budget only with a written reason |

More in [RUNBOOK.md](RUNBOOK.md).
