data "juju_model" "model" {
  name = var.model
}

resource "juju_application" "ros2bag_fileserver" {
  name  = var.app_name
  model = data.juju_model.model.name
  # We always need this variable to be true in order
  # to be able to apply resources limits.
  trust = true
  charm {
    name     = "ros2bag-fileserver-k8s"
    channel  = var.channel
    revision = var.revision
  }
  units     = var.units
  config    = var.config
  resources = var.resources
}
