import os

c = get_config()

runtime_dir = "/srv/jupyterhub"

# Store Hub state on a mounted volume so restarts keep state.
c.JupyterHub.cookie_secret_file = os.path.join(runtime_dir, "cookie_secret")
c.JupyterHub.db_url = "sqlite:///" + os.path.join(runtime_dir, "jupyterhub.sqlite")

c.JupyterHub.bind_url = "http://:8000"
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.hub_connect_ip = "hub"

c.JupyterHub.authenticator_class = "dummy"
c.DummyAuthenticator.password = os.environ.get("JUPYTERHUB_PASSWORD", "jupyter")
c.Authenticator.allow_all = True
c.Authenticator.admin_users = {"admin"}

c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"
c.DockerSpawner.image = os.environ.get(
    "DOCKER_NOTEBOOK_IMAGE", "local/jupyter-datascience-notebook:latest"
)
c.DockerSpawner.network_name = os.environ.get("DOCKER_NETWORK_NAME", "jupyterhub-local")
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.remove = True

c.Spawner.default_url = "/lab"
c.Spawner.notebook_dir = "/home/jovyan/work"
c.DockerSpawner.volumes = {"jupyterhub-user-{username}": "/home/jovyan/work"}