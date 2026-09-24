variable "compartment_id" {
  type = string
}

variable "tenancy_ocid" {
  type = string
}

variable "project_name" {
  type = string
}

# --- Dynamic Group ---
# Matches compute instances tagged with the project name

resource "oci_identity_dynamic_group" "finops_etl" {
  compartment_id = var.tenancy_ocid
  name           = "${var.project_name}-etl-dynamic-group"
  description    = "Dynamic group for OCI FinOps ETL compute instances"
  matching_rule  = "All {tag.freeformTags.project.value = '${var.project_name}', tag.freeformTags.role.value = 'etl-grafana'}"
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
