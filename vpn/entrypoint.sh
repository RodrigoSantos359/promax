#!/bin/bash
# Entrypoint do container vpn:
#   1. Gera /etc/ipsec.secrets a partir dos Docker secrets (nunca de arquivo
#      versionado) e preenche o selector do túnel em /etc/ipsec.conf.
#   2. Sobe o strongSwan e a conexão "dibrasa".
#   3. Mantém um monitor em loop: reconecta se a SA cair (além do
#      dpdaction=restart do próprio strongSwan) e publica o DNS a ser usado
#      pelo container promax em /vpn-runtime/resolv.conf — necessário porque
#      `network_mode: service:vpn` compartilha rede, mas NÃO compartilha
#      filesystem entre os containers.
set -euo pipefail

SECRETS_DIR="/run/secrets"
PSK_FILE="$SECRETS_DIR/vpn_psk"
XAUTH_USER_FILE="$SECRETS_DIR/vpn_xauth_user"
XAUTH_PASS_FILE="$SECRETS_DIR/vpn_xauth_password"

for f in "$PSK_FILE" "$XAUTH_USER_FILE" "$XAUTH_PASS_FILE"; do
    if [ ! -s "$f" ]; then
        echo "[entrypoint] ERRO: secret ausente/vazio: $f — configure os arquivos em ./secrets/ (ver secrets/README.md) antes de subir o container." >&2
        exit 1
    fi
done

PSK=$(cat "$PSK_FILE")
XAUTH_USER=$(cat "$XAUTH_USER_FILE")
XAUTH_PASS=$(cat "$XAUTH_PASS_FILE")

cat > /etc/ipsec.secrets <<EOF
%any : PSK "${PSK}"
${XAUTH_USER} : XAUTH "${XAUTH_PASS}"
EOF
chmod 600 /etc/ipsec.secrets

# Full-tunnel (0.0.0.0/0, igual ao FortiClient) por padrão. Defina
# VPN_REMOTE_SUBNETS no .env (ex: "10.50.0.0/16") para restringir, uma vez
# que se saiba exatamente quais redes o ProMAX interno usa.
RIGHTSUBNET="${VPN_REMOTE_SUBNETS:-0.0.0.0/0}"
sed -i "s|{{RIGHTSUBNET}}|${RIGHTSUBNET}|g" /etc/ipsec.conf
echo "[entrypoint] rightsubnet=${RIGHTSUBNET}"

# Identidade usada na troca XAuth (ver comentário em ipsec.conf) — sem isso,
# o strongSwan tenta buscar a credencial pelo IP local em vez do usuário real.
sed -i "s|{{XAUTH_IDENTITY}}|${XAUTH_USER}|g" /etc/ipsec.conf

mkdir -p /vpn-runtime

monitor_tunnel() {
    # Subshell (por causa do '&' que chama esta função) — set +e aqui não
    # afeta o processo principal, só este loop de monitoramento.
    set +e

    # Backoff exponencial entre tentativas de reconexão (20s, 40s, 80s... até
    # um teto de 30min) — sem isso, dias sem conseguir conectar viram dezenas
    # de milhares de pacotes IKE repetidos, o suficiente para o FortiGate
    # bloquear nosso IP por proteção anti-flood (já aconteceu uma vez).
    local backoff=20
    local backoff_max=1800

    while true; do
        sleep "$backoff"

        if ipsec statusall dibrasa 2>/dev/null | grep -q "ESTABLISHED"; then
            backoff=20
        else
            echo "[monitor] túnel 'dibrasa' não está ESTABLISHED — tentando reconectar (próxima tentativa em ${backoff}s se falhar)..."
            if ipsec up dibrasa; then
                backoff=20
            else
                backoff=$((backoff * 2))
                [ "$backoff" -gt "$backoff_max" ] && backoff=$backoff_max
            fi
        fi

        {
            if [ -n "${VPN_INTERNAL_DNS:-}" ]; then
                echo "nameserver ${VPN_INTERNAL_DNS}"
            fi
            echo "nameserver 127.0.0.11"   # DNS embutido do Docker (resolve 'postgres' etc. na rede do compose)
            echo "nameserver 8.8.8.8"      # fallback público
        } > /vpn-runtime/resolv.conf.tmp
        mv /vpn-runtime/resolv.conf.tmp /vpn-runtime/resolv.conf
    done
}

echo "[entrypoint] iniciando strongSwan..."
ipsec start --nofork &
STRONGSWAN_PID=$!

sleep 3
ipsec up dibrasa || echo "[entrypoint] primeira tentativa de 'ipsec up' falhou — o monitor (a cada 20s) vai retentar"

monitor_tunnel &

wait "$STRONGSWAN_PID"
