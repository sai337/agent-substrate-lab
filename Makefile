.PHONY: install test poc e2e poc-down eks-up eks-test eks-down

install:
	pip install -e '.[test]'

test:
	cd app/memory-agent && go vet ./... && go test ./...
	pytest -q

poc:        ## kind + Agent Substrate v1.0.0 (from pinned source) + memory agent
	bash e2e/up.sh

e2e:        ## 8 checks -> evals/results/<date>-kind/summary.md
	bash e2e/run.sh

poc-down:
	bash e2e/down.sh

eks-up:     ## experimental; personal lab account only
	cd infra/eks/terraform && terraform init && terraform apply
	aws eks update-kubeconfig --name $$(terraform -chdir=infra/eks/terraform output -raw cluster_name) --region $$(terraform -chdir=infra/eks/terraform output -raw region)
	bash infra/eks/install.sh

eks-test:
	TARGET=eks bash e2e/run.sh

eks-down:
	cd infra/eks/terraform && terraform destroy
