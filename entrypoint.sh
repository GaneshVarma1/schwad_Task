#!/bin/sh
# Mounted volumes arrive owned by root. Hand the database directory to the
# service account, then drop to it before serving any traffic.
set -eu
directory="$(dirname "${SHORTENER_DATABASE:-/data/shortener.db}")"
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$directory"
    chown -R shortener:shortener "$directory"
    exec setpriv --reuid=shortener --regid=shortener --init-groups "$@"
fi
exec "$@"
