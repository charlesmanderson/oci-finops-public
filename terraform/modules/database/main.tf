variable "compartment_id" {
  type = string
}

variable "project_name" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "pg_admin_password" {
  type      = string
  sensitive = true
}

variable "db_shape" {
  type    = string
  default = "PostgreSQL.VM.Standard.E5.Flex.2.32GB"
}

variable "db_storage_gb" {
  type    = number
  default = 32
}

# --- OCI PostgreSQL DB System ---

resource "oci_psql_db_system" "main" {
  compartment_id = var.compartment_id
  display_name   = "${var.project_name}-pgsql"
  db_version     = "16"
  shape          = var.db_shape

  credentials {
    username = "finops"
    password_details {
      password_type = "PLAIN_TEXT"
      password      = var.pg_admin_password
    }
  }

  storage_details {
    system_type       = "OCI_OPTIMIZED_STORAGE"
    is_regionally_durable = false
    availability_domain   = data.oci_identity_availability_domains.ads.availability_domains[0].name
  }

  network_details {
    subnet_id = var.subnet_id
  }

  instance_count       = 1
  instance_ocpu_count  = 2
  instance_memory_size_in_gbs = 32

  freeform_tags = {
    project = var.project_name
  }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

# --- Outputs ---

output "pg_endpoint" {
  description = "PostgreSQL private IP endpoint"
  value       = oci_psql_db_system.main.network_details[0].primary_db_endpoint_private_ip
}

output "db_system_id" {
  value = oci_psql_db_system.main.id
}
