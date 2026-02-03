run "basic_deploy" {

  assert {
    condition     = module.ros2bag_fileserver_k8s.app_name == "ros2bag-fileserver"
    error_message = "app_name did not match expected default value"
  }

  # Test requires integration endpoints - check count
  assert {
    condition     = length(module.ros2bag_fileserver_k8s.requires) == 4
    error_message = "Expected 4 required integration endpoints"
  }

  # Test requires integration endpoints - check specific keys
  assert {
    condition     = contains(keys(module.ros2bag_fileserver_k8s.requires), "catalogue")
    error_message = "requires output is missing 'catalogue' endpoint"
  }

  assert {
    condition     = contains(keys(module.ros2bag_fileserver_k8s.requires), "ingress_http")
    error_message = "requires output is missing 'ingress_http' endpoint"
  }

  assert {
    condition     = contains(keys(module.ros2bag_fileserver_k8s.requires), "ingress_tcp")
    error_message = "requires output is missing 'ingress_tcp' endpoint"
  }

  assert {
    condition     = contains(keys(module.ros2bag_fileserver_k8s.requires), "auth-devices-keys")
    error_message = "requires output is missing 'auth-devices-keys' endpoint"
  }

  # Test requires integration endpoints - check exact values
  assert {
    condition     = module.ros2bag_fileserver_k8s.requires["catalogue"] == "catalogue"
    error_message = "requires.catalogue endpoint did not match expected value"
  }

  assert {
    condition     = module.ros2bag_fileserver_k8s.requires["ingress_http"] == "ingress"
    error_message = "requires.ingress_http endpoint did not match expected value"
  }

  assert {
    condition     = module.ros2bag_fileserver_k8s.requires["ingress_tcp"] == "ingress-tcp"
    error_message = "requires.ingress_tcp endpoint did not match expected value"
  }

  assert {
    condition     = module.ros2bag_fileserver_k8s.requires["auth-devices-keys"] == "auth_devices_keys"
    error_message = "requires.auth-devices-keys endpoint did not match expected value"
  }

  # Test provides integration endpoints - check count
  assert {
    condition     = length(module.ros2bag_fileserver_k8s.provides) == 1
    error_message = "Expected 1 provided integration endpoints"
  }

  # Test provides integration endpoints - check specific keys
  assert {
    condition     = contains(keys(module.ros2bag_fileserver_k8s.provides), "blackbox_probes")
    error_message = "provides output is missing 'blackbox_probes' endpoint"
  }

  # Test provides integration endpoints - check exact values
  assert {
    condition     = module.ros2bag_fileserver_k8s.provides["blackbox_probes"] == "blackbox-probes"
    error_message = "provides.blackbox_probes endpoint did not match expected value"
  }

}
