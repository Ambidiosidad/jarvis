#!/bin/bash
echo "J.A.R.V.I.S. — Parando entorno de desarrollo..."
cd "$(dirname "$0")/../../extensions"
docker compose -f docker-compose.dev.yml down
echo "Servicios detenidos."
