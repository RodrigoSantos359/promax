"""
Client da API BPO ACENE (entrada automática dos relatórios do PromaX).

Contrato (swagger "BPO ACENE · API de integração Promax" v1.0.0):

- `POST {servidor}/api/bpo/promax/importacoes` — multipart/form-data com
  `competencia` (AAAA-MM) e `arquivo` (.csv/.txt/.inf, até 20 MB). Um
  arquivo por chamada; o BPO reconhece o tipo de relatório pelo cabeçalho.
  - 202: recebido, vai para a fila de processamento do BPO.
  - 200: o mesmo arquivo já tinha sido recebido nesta competência
    (`duplicado: true`) — reenviar é seguro.
  - 401/403/422: erro definitivo (token, permissão, competência fechada,
    layout ou filial não configurada).
  - 429: limite de 30 chamadas/minuto por token.
- Autenticação: `Authorization: Bearer <token>`, um token por empresa.

Este módulo só faz a chamada e classifica o resultado; a fila, as novas
tentativas e o controle de ritmo ficam em `bpo_acene_outbox.py`.
"""

import os
from dataclasses import dataclass
from typing import Optional

import requests
import urllib3

from config.settings import BPO_ACENE_URL, BPO_ACENE_VERIFY_SSL, logger

API_PATH = "/api/bpo/promax"
UPLOAD_TIMEOUT = 120  # segundos (arquivos de até 20 MB)
MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = (".csv", ".txt", ".inf")

# Resultados possíveis de um envio.
ENVIADO = "enviado"
DUPLICADO = "duplicado"
REJEITADO = "rejeitado"  # erro definitivo — não adianta tentar de novo
TENTAR_NOVAMENTE = "tentar_novamente"  # rede, 429 ou erro do servidor

if not BPO_ACENE_VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class ResultadoEnvio:
    """Resultado de uma chamada de envio de arquivo."""

    resultado: str
    http_status: Optional[int] = None
    lote_id: Optional[int] = None
    lote_status: Optional[str] = None
    mensagem: Optional[str] = None


def envio_configurado() -> bool:
    """True se o endereço do servidor BPO ACENE estiver configurado (BPO_ACENE_URL)."""
    return bool(BPO_ACENE_URL)


def _mensagem_erro(response: requests.Response) -> str:
    """Extrai `message` (+ `errors`) do corpo de erro da API, ou o status HTTP."""
    try:
        corpo = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    mensagem = corpo.get("message") or f"HTTP {response.status_code}"
    erros = corpo.get("errors")
    if isinstance(erros, dict) and erros:
        detalhes = "; ".join(f"{campo}: {', '.join(map(str, msgs))}" for campo, msgs in erros.items())
        mensagem = f"{mensagem} ({detalhes})"
    return mensagem


def enviar_arquivo(token: str, competencia: str, caminho_arquivo: str, nome_arquivo: str) -> ResultadoEnvio:
    """
    Envia um arquivo de relatório para a API BPO ACENE.

    Args:
        token: token de integração da empresa.
        competencia: competência AAAA-MM.
        caminho_arquivo: arquivo em disco a enviar.
        nome_arquivo: nome com que o arquivo é enviado (o nome original do download).

    Returns:
        ResultadoEnvio com `resultado` em ENVIADO, DUPLICADO, REJEITADO ou TENTAR_NOVAMENTE.
    """
    if not nome_arquivo.lower().endswith(ALLOWED_EXTENSIONS):
        return ResultadoEnvio(REJEITADO, mensagem=f"Extensão não aceita pela API: '{nome_arquivo}'")
    tamanho = os.path.getsize(caminho_arquivo)
    if tamanho > MAX_FILE_SIZE:
        return ResultadoEnvio(REJEITADO, mensagem=f"Arquivo maior que 20 MB ({tamanho} bytes)")

    url = f"{BPO_ACENE_URL}{API_PATH}/importacoes"
    try:
        with open(caminho_arquivo, "rb") as f:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                data={"competencia": competencia},
                files={"arquivo": (nome_arquivo, f, "application/octet-stream")},
                timeout=UPLOAD_TIMEOUT,
                verify=BPO_ACENE_VERIFY_SSL,
            )
    except requests.RequestException as e:
        logger.warning(f"BPO ACENE: falha de comunicação ao enviar '{nome_arquivo}': {e}")
        return ResultadoEnvio(TENTAR_NOVAMENTE, mensagem=str(e))

    status = response.status_code
    if status in (200, 202):
        try:
            corpo = response.json()
        except ValueError:
            corpo = {}
        lote = corpo.get("lote") or {}
        duplicado = bool(corpo.get("duplicado"))
        return ResultadoEnvio(
            DUPLICADO if duplicado else ENVIADO,
            http_status=status,
            lote_id=lote.get("id"),
            lote_status=lote.get("status"),
            mensagem=lote.get("aviso") or lote.get("erro"),
        )

    mensagem = _mensagem_erro(response)
    if status == 429 or status >= 500:
        return ResultadoEnvio(TENTAR_NOVAMENTE, http_status=status, mensagem=mensagem)
    return ResultadoEnvio(REJEITADO, http_status=status, mensagem=mensagem)


__all__ = [
    "ResultadoEnvio",
    "envio_configurado",
    "enviar_arquivo",
    "ENVIADO",
    "DUPLICADO",
    "REJEITADO",
    "TENTAR_NOVAMENTE",
]
