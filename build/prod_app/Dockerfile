FROM registry_path/technology/python/3.11:latest
MAINTAINER ZoomRx


# Install dependent linux packages
RUN sudo apt-get --allow-releaseinfo-change update;
RUN sudo apt-get -y install pkg-config libldap2-dev libsasl2-dev ldap-utils libjpeg-dev zlib1g-dev default-libmysqlclient-dev build-essential
RUN pip install poetry

# Create Directory Structure and copy
RUN mkdir -p /app/ferma-medical-information
COPY . /app/ferma-medical-information

RUN sudo chown -R ferma:ferma /app
WORKDIR /app/ferma-medical-information

RUN python -m pip install pattern
RUN python -m poetry install --no-root

# port to be exposed
EXPOSE 8000

CMD python -m poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

