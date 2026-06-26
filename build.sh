#!/bin/sh
set -e
# Build z brama strażnika. Dla maksimum: uruchom z read-only rootfs:
#   podman run -it --rm --read-only --tmpfs /home/magos karmazynos
podman build -t karmazynos . 2>/dev/null || docker build -t karmazynos .
echo "OK. Boot:  podman run -it --rm karmazynos"
