FROM jupyterhub/jupyterhub

RUN mkdir -p /etc/jupyter-hub
RUN pip3 install oauthenticator && \
    pip3 install jupyter && \
    pip3 install jupyterhub-kubespawner

COPY ./jupyter-hub_config.py /etc/jupyter-hub

CMD ["jupyterhub", "-f", "/etc/jupyter-hub/jupyter-hub_config.py"]
