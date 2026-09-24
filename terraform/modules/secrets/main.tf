variable "compartment_id" {
  type = string
}

variable "project_name" {
  type = string
}

variable "vault_id" {
  type = string
}

variable "vault_key_id" {
  type = string
}

variable "pg_password" {
  type      = string
  sensitive = true
}

variable "grafana_admin_password" {
  type      = string
  sensitive = true
}

# --- Vault Secrets ---
# The compute instance receives only these secret OCIDs and fetches the values
# at boot with its instance principal, so no password appears in user_data.

resource "oci_vault_secret" "pg_password" {
  compartment_id = var.compartment_id
  vault_id       = var.vault_id
  key_id         = var.vault_key_id
  secret_name    = "${var.project_name}-pg-password"
  description    = "PostgreSQL password for the FinOps ETL"

  secret_content {
    content_type = "BASE64"
    content      = base64encode(var.pg_password)
  }
}

resource "oci_vault_secret" "grafana_admin_password" {
  compartment_id = var.compartment_id
  vault_id       = var.vault_id
  key_id         = var.vault_key_id
  secret_name    = "${var.project_name}-grafana-admin-password"
  description    = "Initial Grafana admin password"

  secret_content {
    content_type = "BASE64"
    content      = base64encode(var.grafana_admin_password)
  }
}

# --- Outputs ---

output "pg_password_secret_id" {
  value = oci_vault_secret.pg_password.id
}

output "grafana_admin_password_secret_id" {
  value = oci_vault_secret.grafana_admin_password.id
}
