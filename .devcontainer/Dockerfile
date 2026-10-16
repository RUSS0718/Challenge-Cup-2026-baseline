FROM mcr.microsoft.com/vscode/devcontainers/python:1-3.12-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends make curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
