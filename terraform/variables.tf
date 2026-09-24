variable "tenancy_ocid" {
  description = "OCID of the OCI tenancy"
  type        = string
}

variable "compartment_id" {
  description = "OCID of the compartment for all resources"
  type        = string
}

variable "region" {
  description = "OCI region (e.g., us-ashburn-1)"
  type        = string
  default     = "us-ashburn-1"
}

variable "ssh_public_key" {
  description = "SSH public key for compute instance access"
  type        = string
}

variable "pg_admin_password" {
  description = "Password for the PostgreSQL admin user"
  type        = string
  sensitive   = true
}

variable "grafana_admin_password" {
  description = "Initial Grafana admin password. Stored in OCI Vault and fetched at boot; never placed in instance metadata."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.grafana_admin_password) >= 12
    error_message = "grafana_admin_password must be at least 12 characters."
  }
}

variable "grafana_allowed_cidrs" {
  description = "CIDR blocks allowed to reach Grafana on port 3000. Empty (the default) keeps Grafana private; reach it through an SSH tunnel."
  type        = list(string)
  default     = []
}

variable "vault_id" {
  description = "OCID of an existing OCI Vault that will hold the PostgreSQL and Grafana passwords"
  type        = string
}

variable "vault_key_id" {
  description = "OCID of a master encryption key in vault_id, used to encrypt the secrets"
  type        = string
}

variable "compute_shape" {
  description = "Shape for the compute instance"
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "compute_ocpus" {
  description = "Number of OCPUs for the compute instance"
  type        = number
  default     = 1
}

variable "compute_memory_gb" {
  description = "Memory in GB for the compute instance"
  type        = number
  default     = 8
}

variable "db_shape" {
  description = "Shape for the PostgreSQL DB system"
  type        = string
  default     = "PostgreSQL.VM.Standard.E5.Flex.2.32GB"
}

variable "db_storage_gb" {
  description = "Storage in GB for the PostgreSQL DB system"
  type        = number
  default     = 32
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "oci-finops"
}
