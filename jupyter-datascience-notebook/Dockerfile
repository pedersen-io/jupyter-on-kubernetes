FROM jupyter/datascience-notebook

# install pinned jupyterhub and ensure notebook is installed
RUN python3 -m pip install jupyter && \
    python3 -m pip install jupyterhub && \
    python3 -m pip install notebook

USER root

COPY templates/MLB_Data_Starter.ipynb /opt/jupyter-templates/MLB_Data_Starter.ipynb
COPY start-notebook.d/10-copy-mlb-template.sh /usr/local/bin/start-notebook.d/10-copy-mlb-template.sh

RUN chmod +x /usr/local/bin/start-notebook.d/10-copy-mlb-template.sh

USER ${NB_UID}