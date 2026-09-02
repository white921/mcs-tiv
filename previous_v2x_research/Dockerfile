FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends sumo sumo-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

ENV SUMO_HOME=/usr/share/sumo
ENV PYTHONPATH=/app:/usr/share/sumo/tools
