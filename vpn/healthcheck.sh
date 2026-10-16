#!/bin/bash
# Usado pelo HEALTHCHECK do Dockerfile / docker-compose. "Saudável" = a SA
# da conexão "dibrasa" está ESTABLISHED. Dá pra evoluir depois para também
# testar um TCP connect real a um host interno conhecido do ProMAX.
set -euo pipefail

if ipsec statusall dibrasa 2>/dev/null | grep -q "ESTABLISHED"; then
    exit 0
fi

echo "[healthcheck] túnel 'dibrasa' não está ESTABLISHED" >&2
exit 1
