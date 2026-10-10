#!/bin/bash
# First-boot setup for the Provok server (Amazon Linux 2023). Rendered by Terraform: only compose_version is templated.
set -euxo pipefail

dnf install -y docker
systemctl enable --now docker

# Docker Compose plugin, pinned and checksum-verified.
mkdir -p /usr/local/lib/docker/cli-plugins
cd /tmp
base="https://github.com/docker/compose/releases/download/${compose_version}"
curl -fsSL -o docker-compose "$base/docker-compose-linux-x86_64"
curl -fsSL -o docker-compose.sha256 "$base/docker-compose-linux-x86_64.sha256"
echo "$(cut -d' ' -f1 docker-compose.sha256)  docker-compose" | sha256sum -c -
install -m 0755 docker-compose /usr/local/lib/docker/cli-plugins/docker-compose

# 2 GB swap: the box has 2 GB RAM; this keeps a deploy (old + new containers) from being OOM-killed.
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

mkdir -p /opt/provok
