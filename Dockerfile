FROM python:3.10.13-bookworm AS pyrobot

WORKDIR /app/

COPY ./requirements.txt /tmp/requirements.txt

RUN apt-get update && apt-get upgrade -y

RUN apt-get install -y python3-dev

RUN python3 -m venv /app/venv1/

RUN /app/venv1/bin/pip3 install --upgrade pip

RUN /app/venv1/bin/pip3 install -r /tmp/requirements.txt

COPY ./pyrobot /app/pyrobot

WORKDIR /app/