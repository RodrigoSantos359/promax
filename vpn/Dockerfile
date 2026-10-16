FROM alpine:3.19

# strongswan: pilha IKEv1/IKEv2 completa (charon), incluindo os plugins
# xauth-generic (XAuth) e resolve (grava DNS recebido via Mode Config em
# /etc/resolv.conf). iptables/iproute2: ajustes de roteamento/NAT-T.
# bind-tools: dig/nslookup para diagnóstico. iputils: ping para o healthcheck.
RUN apk add --no-cache \
        strongswan \
        iptables \
        iproute2 \
        bind-tools \
        iputils \
        bash

COPY ipsec.conf /etc/ipsec.conf
COPY strongswan.conf /etc/strongswan.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY healthcheck.sh /usr/local/bin/healthcheck.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/healthcheck.sh

# ipsec.secrets é gerado em runtime pelo entrypoint (a partir dos Docker
# secrets), nunca vem da imagem — ver entrypoint.sh e vpn/ipsec.secrets.template.

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["/usr/local/bin/healthcheck.sh"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
