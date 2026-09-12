#!/bin/sh
# Probe production settings over a private container connection, without TLS issuance.
set -eu
cd "$(dirname "$0")/.."
DJANGO_SECRET_KEY=$(docker compose run --rm --no-deps web python -c 'import secrets; print(secrets.token_urlsafe(64))')
export DJANGO_SECRET_KEY
docker compose run --rm --no-deps \
  -e DJANGO_DEBUG=False -e DJANGO_SECRET_KEY \
  -e PRIMARY_DOMAIN=example.test -e ADDITIONAL_DOMAINS=www.example.test \
  -e TRUST_PROXY=True -e SMOKE_HTTPS_PROXY=True \
  web sh -c '
    set -eu
    python manage.py check --deploy
    gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 1 --access-logfile - &
    server_pid=$!
    trap "kill $server_pid 2>/dev/null || true" EXIT
    python -c "import socket,time; deadline=time.monotonic()+20
while True:
    try:
        socket.create_connection((\"127.0.0.1\",8000),timeout=1).close(); break
    except OSError:
        if time.monotonic()>deadline: raise
        time.sleep(.2)"
    python scripts/docker_smoke.py
  '
