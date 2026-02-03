data "juju_model" "model" {
  name = "testing"
}

variable "channel" {
  description = "The channel to use when deploying a charm"
  type        = string
  default     = "latest/edge"
}

terraform {
  required_providers {
    juju = {
      version = "~> 0.19.0"
      source  = "juju/juju"
    }
  }
}

provider "juju" {}

module "ros2bag_fileserver_k8s" {
  app_name = "ros2bag-fileserver"
  source   = "./.."
  channel  = var.channel
  model    = data.juju_model.model.uuid
  units    = 1
}
