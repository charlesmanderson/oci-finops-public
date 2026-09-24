output "vcn_id" {
  description = "OCID of the VCN"
  value       = module.network.vcn_id
}

output "compute_public_ip" {
  description = "Public IP of the compute instance"
  value       = module.compute.public_ip
}

output "pg_endpoint" {
  description = "PostgreSQL private endpoint"
  value       = module.database.pg_endpoint
}

output "grafana_url" {
  description = "Grafana dashboard URL (via an SSH tunnel unless grafana_allowed_cidrs is set)"
  value       = length(var.grafana_allowed_cidrs) > 0 ? "http://${module.compute.public_ip}:3000" : "http://localhost:3000 via ssh -L 3000:localhost:3000 opc@${module.compute.public_ip}"
}

output "dynamic_group_id" {
  description = "OCID of the dynamic group for instance principal auth"
  value       = module.iam.dynamic_group_id
}
