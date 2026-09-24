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
