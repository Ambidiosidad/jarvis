#!/bin/bash
echo "J.A.R.V.I.S. — Deteniendo servicios..."
cd /opt/jarvis/extensions
docker compose down
echo "Jarvis detenido."
