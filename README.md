# Ros2bag Fileserver Operator (k8s)

Ros2bag fileserver charm is a charm that deploys a Caddy fileserver to store ros2bag files. It can be used in conjuction with the Foxglove Studio charm and COS-lite.

## Basic Deployment

The charm is still under development and is not available yet on CharmHub.

The deployment assumes that a Juju model is deployed with microk8s. Instructions on how to set up microk8s with Juju are available [here](https://juju.is/docs/sdk/set-up-your-development-environment#heading--install-microk8s).

To deploy the local charm follow these instructions:

- Clone the source repository
  
  ```
  git clone https://github.com/ubuntu-robotics/ros2bag-fileserver-k8s-operator.git
  ```

- Access the folder

  ```
  cd ros2bag-fileserver-k8s-operator
  ```

- Build the ros2bag fileserver charm with

  ```
  charmcraft pack
  ```

- Deploy the charm with the following command:

  ```
  juju deploy ./ros2bag-fileserver_ubuntu-22.04-amd64.charm --resource caddy-fileserver-image=docker.io/caddy/caddy:2.5.2-alpine
  ```

- Test the installation by executing the following command:

  ```
  curl -v <unit_ip>:80
  ```



## COS lite deployment

The foxglove studio charm can be integrated with the [COS lite bundle](https://github.com/canonical/cos-lite-bundle)

An overlay is offered in this repository to ease up deployment.

To deploy with COS lite bundle follow these instructions:

- Clone the source repository

  ```
  git clone https://github.com/ubuntu-robotics/ros2bag-fileserver-k8s-operator.git
  ```

- Enter the folder

  ```
  cd ros2bag-fileserver-k8s-operator
  ```

- Build the ros2bag fileserver charm with

  ```
  charmcraft pack
  ```

- Deploy cos-lite bundle with the robotics overlay as follows:

  ```
  juju deploy cos-lite --trust --overlay ./robotics-overlay.yaml
  ```
  NB. this bundle is in development and attempts to deploy the foxglove-studio-k8s charm. Before deploying make sure to have the charm in the ros2bag-fileserver-k8s folder. You can create the charm by following the instructions at [foxglove-k8s-operator repository](https://github.com/ubuntu-robotics/foxglove-k8s-operator.git).


  Once deployed the ros2bag-fileserver charm will be accessible via traefik at the following link:

  ```
  http://traefik-virtual-ip/<juju-model-name>-ros2bag-fileserver/
  ```
