module "network" {
  source = "./modules/network"

  compartment_id = var.compartment_id
  project_name   = var.project_name
  region         = var.region
}

module "database" {
  source = "./modules/database"

  compartment_id   = var.compartment_id
  project_name     = var.project_name
  subnet_id        = module.network.private_subnet_id
  pg_admin_password = var.pg_admin_password
  db_shape         = var.db_shape
  db_storage_gb    = var.db_storage_gb
}

module "iam" {
  source = "./modules/iam"

  compartment_id = var.compartment_id
  tenancy_ocid   = var.tenancy_ocid
  project_name   = var.project_name
}

module "compute" {
  source = "./modules/compute"

  compartment_id    = var.compartment_id
  project_name      = var.project_name
  subnet_id         = module.network.public_subnet_id
  ssh_public_key    = var.ssh_public_key
  compute_shape     = var.compute_shape
  compute_ocpus     = var.compute_ocpus
  compute_memory_gb = var.compute_memory_gb
  pg_host           = module.database.pg_endpoint
  pg_password       = var.pg_admin_password
  tenancy_ocid      = var.tenancy_ocid
  region            = var.region
}
