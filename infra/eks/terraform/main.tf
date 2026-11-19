# EKS for the Agent Substrate pilot: private nodes, a system node group and a
# worker node group for Substrate WorkerPools, VPC CNI with NetworkPolicy
# enforcement (Substrate relies on NetworkPolicies for default deny), EBS CSI,
# an S3 bucket for actor snapshots with Pod Identity access, ECR for images,
# and a monthly budget alarm. EKS is NOT an upstream-tested target (upstream
# tests kind and GKE); see docs/ENTERPRISE.md for what is verified.

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs  = slice(data.aws_availability_zones.available.names, 0, 3)
  tags = { project = "agent-substrate-lab", managed_by = "terraform", owner = var.owner }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name               = var.name
  cidr               = "10.40.0.0/16"
  azs                = local.azs
  private_subnets    = ["10.40.0.0/19", "10.40.32.0/19", "10.40.64.0/19"]
  public_subnets     = ["10.40.96.0/22", "10.40.100.0/22", "10.40.104.0/22"]
  enable_nat_gateway = true
  single_nat_gateway = true # lab cost; use one per AZ in production

  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  tags                = local.tags
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name                             = var.name
  cluster_version                          = var.kubernetes_version
  vpc_id                                   = module.vpc.vpc_id
  subnet_ids                               = module.vpc.private_subnets
  cluster_endpoint_public_access           = true # CI runner reaches the API; restrict with cidrs below
  cluster_endpoint_public_access_cidrs     = var.api_allowed_cidrs
  enable_cluster_creator_admin_permissions = true
  authentication_mode                      = "API"

  cluster_addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
      # OpenShell's hard requirement: egress NetworkPolicy must be enforced.
      configuration_values = jsonencode({ enableNetworkPolicy = "true" })
    }
    eks-pod-identity-agent = {}
    aws-ebs-csi-driver = {
      pod_identity_association = [{
        role_arn        = aws_iam_role.ebs_csi.arn
        service_account = "ebs-csi-controller-sa"
      }]
    }
  }

  eks_managed_node_groups = {
    system = {
      instance_types = ["m7i.large"]
      min_size       = 2
      max_size       = 3
      desired_size   = 2
      labels         = { workload = "system" }
    }
    substrate_workers = {
      instance_types = [var.sandbox_instance_type]
      min_size       = 1
      max_size       = 4
      desired_size   = 2
      labels         = { workload = "substrate-worker" }
      metadata_options = {
        http_tokens                 = "required"
        http_put_response_hop_limit = 1 # pods cannot reach node IMDS credentials
      }
    }
  }

  tags = local.tags
}

data "aws_iam_policy_document" "pod_identity_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi" {
  name               = "${var.name}-ebs-csi"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# Actor snapshots (RAM + rootfs + volumes) leave the node through this bucket.
resource "aws_s3_bucket" "snapshots" {
  bucket_prefix = "${var.name}-snapshots-"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "snapshots" {
  bucket                  = aws_s3_bucket.snapshots.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_iam_role" "snapshots" {
  name               = "${var.name}-snapshots"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "snapshots" {
  role   = aws_iam_role.snapshots.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.snapshots.arn },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.snapshots.arn}/*" }
    ]
  })
}

# Only the two Substrate components that move snapshots get the bucket role.
resource "aws_eks_pod_identity_association" "snapshots" {
  for_each        = toset(["atelet", "ate-api-server"])
  cluster_name    = module.eks.cluster_name
  namespace       = "ate-system"
  service_account = each.key
  role_arn        = aws_iam_role.snapshots.arn
}

resource "aws_ecr_repository" "agent" {
  name                 = "${var.name}/memory-agent"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}

resource "aws_budgets_budget" "lab" {
  count        = var.budget_email == "" ? 0 : 1
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }
}
