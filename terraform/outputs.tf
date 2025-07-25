output "app_name" {
  value       = juju_application.ros2bag_fileserver.name
  description = "The name of the deployed application"
}

output "requires" {
  value = {
    catalogue         = "catalogue"
    ingress_tcp       = "ingress-tcp"
    ingress_http      = "ingress"
    auth-devices-keys = "auth_devices_keys"
  }
  description = "Map of the integration endpoints required by the application"
}

output "provides" {
  value = {
    blackbox_probes = "blackbox-probes"
  }
  description = "Map of the integration endpoints provided by the application"
}
