"""
Verificação de conectividade com o PromaX (via VPN FortiClient) antes de
executar automações.

O PromaX da Dibrasa só é acessível com a VPN FortiClient conectada. Sem essa
verificação, uma VPN caída aparece só como um erro genérico e confuso do
Selenium (`net::ERR_CONNECTION_TIMED_OUT`), depois de ~20-30s tentando
carregar a página de login. Checar antes evita essa espera e dá um erro
claro e acionável ("conecte a VPN") em vez de uma stacktrace do ChromeDriver.

Checar o status do adaptador de rede virtual do FortiClient (abordagem
tentada antes) se mostrou pouco confiável: o adaptador "Fortinet SSL VPN
Virtual Ethernet Adapter" fica "Disconnected" mesmo com a VPN ativa nesse
ambiente (FortiClient usa outro adaptador/modo), e o outro adaptador virtual
("Fortinet Virtual Ethernet Adapter") fica "Up" tanto com a VPN conectada
quanto desconectada — o nome/status do adaptador não reflete o túnel real.

Por isso a verificação aqui é direta: tenta abrir uma conexão TCP na porta
443 do host configurado em `PROMAX_URL`. Isso responde exatamente a
pergunta que importa ("dá para alcançar o PromaX agora?"), sem depender de
detalhes de implementação do FortiClient que podem variar por ambiente/versão.
"""

import logging
import socket
from urllib.parse import urlparse

from config.settings import PROMAX_URL, VPN_CHECK_ENABLED

logger = logging.getLogger(__name__)


def is_vpn_connected(timeout: float = 5.0) -> bool:
    """
    Verifica se o host do PromaX (extraído de `PROMAX_URL`) está alcançável
    na porta 443, tentando uma conexão TCP direta.

    Args:
        timeout: tempo máximo, em segundos, para a tentativa de conexão

    Returns:
        bool: True se conseguiu conectar (VPN/rede ok), False se não
    """
    host = urlparse(PROMAX_URL).hostname
    if not host:
        logger.warning(f"Não foi possível extrair o host de PROMAX_URL='{PROMAX_URL}'; pulando verificação de VPN")
        return True

    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return True
    except OSError as e:
        logger.debug(f"Falha ao conectar em {host}:443 (VPN provavelmente desconectada): {str(e)}")
        return False


def ensure_vpn_connected() -> None:
    """
    Levanta uma exceção clara e imediata se o PromaX não estiver alcançável
    (VPN desconectada), quando a verificação estiver habilitada
    (`VPN_CHECK_ENABLED`).

    Chamada no início de `TaskExecutor.execute_automation()`, antes de criar
    o WebDriver — evita abrir um Chrome e esperar ~20-30s por um timeout de
    rede só para descobrir que a VPN está caída.

    Raises:
        Exception: se VPN_CHECK_ENABLED=True e o PromaX não estiver alcançável
    """
    if not VPN_CHECK_ENABLED:
        return

    if not is_vpn_connected():
        raise Exception(
            "Não foi possível alcançar o PromaX (VPN FortiClient provavelmente "
            "desconectada). Conecte a VPN da Dibrasa (ícone do FortiClient na "
            "bandeja do Windows) antes de executar esta automação."
        )


__all__ = ["is_vpn_connected", "ensure_vpn_connected"]
