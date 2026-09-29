# jupyterhub_config.py file
c = get_config()

import os
pjoin = os.path.join

runtime_dir = os.path.join('/srv/jupyterhub')
ssl_dir = pjoin(runtime_dir, 'ssl')
if not os.path.exists(ssl_dir):
    os.makedirs(ssl_dir)

# Allows multiple single-server per user
c.JupyterHub.allow_named_servers = True

# ssl is handled by nginx so this is not needed
# https on :443
# c.JupyterHub.port = 443
# c.JupyterHub.ssl_key = pjoin(ssl_dir, 'ssl.key')
# c.JupyterHub.ssl_cert = pjoin(ssl_dir, 'ssl.cert')

# put the JupyterHub cookie secret and state db
# in /var/run/jupyterhub
c.JupyterHub.cookie_secret_file = pjoin(runtime_dir, 'cookie_secret')
c.JupyterHub.db_url = pjoin(runtime_dir, 'jupyterhub.sqlite')
# or `--db=/path/to/jupyterhub.sqlite` on the command-line

# use GitHub OAuthenticator for local users
c.JupyterHub.authenticator_class = 'oauthenticator.LocalGitHubOAuthenticator'
c.GitHubOAuthenticator.oauth_callback_url = os.environ['OAUTH_CALLBACK_URL']

# create system users that don't exist yet
c.LocalAuthenticator.create_system_users = True

# specify users and admin
c.Authenticator.whitelist = {'derekpedersen'}
c.Authenticator.admin_users = {'derekpedersen'}

# uses the default spawner
# To use a different spawner, uncomment `spawner_class` and set to desired
# spawner (e.g. SudoSpawner). Follow instructions for desired spawner
# configuration.
c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'

# kubespawner config
c.KubeSpawner.image = 'docker.io/derekpedersen/jupyter-datascience-notebook:latest'

# start single-user notebook servers in ~/assignments,
# with ~/assignments/Welcome.ipynb as the default landing page
# this config could also be put in
# /etc/jupyter/jupyter_notebook_config.py
c.Spawner.notebook_dir = '~/assignments'
c.Spawner.args = ['--NotebookApp.default_url=/notebooks/Welcome.ipynb']

# the hub should listen on all interfaces, so the proxy can access it
c.JupyterHub.hub_ip = '0.0.0.0'
c.JupyterHub.hub_connect_ip = '10.43.254.2' # IP for k8s jupyterhub-service