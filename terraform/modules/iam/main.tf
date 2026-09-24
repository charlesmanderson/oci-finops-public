variable "compartment_id" {
  type = string
}

variable "tenancy_ocid" {
  type = string
}

variable "project_name" {
  type = string
}

variable "instance_id" {
  description = "OCID of the ETL compute instance; the dynamic group matches only this instance"
  type        = string
}

variable "secret_ids" {
  description = "OCIDs of the Vault secrets the ETL instance may read"
  type        = list(string)
}

# --- Dynamic Group ---
# Matches the ETL instance by OCID. Freeform tags are not access-controlled in
# OCI, so a tag-based rule would let anyone who can tag an instance join the
# group and inherit its permissions.

resource "oci_identity_dynamic_group" "finops_etl" {
  compartment_id = var.tenancy_ocid
  name           = "${var.project_name}-etl-dynamic-group"
  description    = "Dynamic group for OCI FinOps ETL compute instances"
  matching_rule  = "All {instance.id = '${var.instance_id}'}"
}

# --- IAM Policies ---

resource "oci_identity_policy" "finops_object_storage" {
  compartment_id = var.tenancy_ocid
  name           = "${var.project_name}-object-storage-policy"
  description    = "Allow FinOps ETL to read FOCUS reports from Object Storage"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.finops_etl.name} to read objects in tenancy where target.namespace = 'bling'",
    "Allow dynamic-group ${oci_identity_dynamic_group.finops_etl.name} to read buckets in tenancy where target.namespace = 'bling'",
  ]
}

resource "oci_identity_policy" "finops_notifications" {
  compartment_id = var.compartment_id
  name           = "${var.project_name}-notifications-policy"
  description    = "Allow FinOps ETL to publish anomaly alerts via ONS"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.finops_etl.name} to use ons-topics in compartment id ${var.compartment_id}",
  ]
}

resource "oci_identity_policy" "finops_secrets" {
  compartment_id = var.compartment_id
  name           = "${var.project_name}-secrets-policy"
  description    = "Allow FinOps ETL to read its own Vault secrets at boot"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.finops_etl.name} to read secret-bundles in compartment id ${var.compartment_id} where any {${join(", ", [for id in var.secret_ids : "target.secret.id = '${id}'"])}}",
  ]
}

# --- OCI Notifications Topic ---

resource "oci_ons_notification_topic" "anomaly_alerts" {
  compartment_id = var.compartment_id
  name           = "${var.project_name}-anomaly-alerts"
  description    = "Cost anomaly alert notifications"
}

# --- Outputs ---

output "dynamic_group_id" {
  value = oci_identity_dynamic_group.finops_etl.id
}

output "ons_topic_ocid" {
  value = oci_ons_notification_topic.anomaly_alerts.id
}
