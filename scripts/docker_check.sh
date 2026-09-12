#!/bin/sh
# Run from any directory in Ubuntu/WSL. Existing data volumes are preserved.
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
    cp .env.example .env
fi
docker compose version >/dev/null
docker compose build web
docker compose up -d --wait web
docker compose run --rm --no-deps -e DJANGO_DEBUG=True web python manage.py test
docker compose run --rm --no-deps -e DJANGO_DEBUG=True web python manage.py makemigrations --check --dry-run
docker compose exec -T web python scripts/docker_smoke.py
docker compose ps
