output "cluster_name" {
  value = module.eks.cluster_name
}

output "region" {
  value = var.region
}

output "ecr_repository_url" {
  value = aws_ecr_repository.agent.repository_url
}

output "ecr_registry" {
  value = split("/", aws_ecr_repository.agent.repository_url)[0]
}

output "snapshot_bucket" {
  value = aws_s3_bucket.snapshots.bucket
}
