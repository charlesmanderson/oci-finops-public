variable "compartment_id" {
  type = string
}

variable "project_name" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "ssh_public_key" {
  type = string
}

variable "compute_shape" {
  type    = string
  default = "VM.Standard.E4.Flex"
}

variable "compute_ocpus" {
  type    = number
  default = 1
}

variable "compute_memory_gb" {
  type    = number
  default = 8
}

variable "pg_host" {
  type = string
}

variable "pg_password" {
  type      = string
  sensitive = true
}

variable "tenancy_ocid" {
  type = string
}

variable "region" {
  type = string
}

# Get the latest Oracle Linux 9 image
data "oci_core_images" "ol9" {
  compartment_id           = var.compartment_id
  operating_system         = "Oracle Linux"
  operating_system_version = "9"
  shape                    = var.compute_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

resource "oci_core_instance" "etl" {
  compartment_id      = var.compartment_id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "${var.project_name}-etl"
  shape               = var.compute_shape

  shape_config {
    ocpus         = var.compute_ocpus
    memory_in_gbs = var.compute_memory_gb
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ol9.images[0].id
  }

  create_vnic_details {
    subnet_id        = var.subnet_id
    assign_public_ip = true
    display_name     = "${var.project_name}-etl-vnic"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
      pg_host        = var.pg_host
      pg_password    = var.pg_password
      tenancy_ocid   = var.tenancy_ocid
      region         = var.region
    }))
  }

  freeform_tags = {
    project = var.project_name
    role    = "etl-grafana"
  }
}

output "public_ip" {
  value = oci_core_instance.etl.public_ip
}

output "instance_id" {
  value = oci_core_instance.etl.id
}
