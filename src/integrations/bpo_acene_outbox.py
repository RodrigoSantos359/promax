"""
Fila de envio dos relatórios do PromaX para a API BPO ACENE.

Fluxo:
1. `enfileirar_arquivo()` é chamado pelo `file_processor` logo depois que um
   arquivo baixado foi importado com sucesso no Postgres (e antes de o
   original ser apagado). Se a rotina estiver em `BPO_ACENE_ROTINAS`, o
   servidor estiver configurado (`BPO_ACENE_URL`) e a empresa tiver token,
   uma cópia do arquivo vai para `BPO_ACENE_OUTBOX_DIR` e é registrada em
   `envios_bpo` com status 'pendente'. Qualquer falha aqui só é logada —
   nunca interrompe a importação.
2. `EnvioBpoMonitor` (thread em background) envia os pendentes, um por vez,
   respeitando o limite da API (30 chamadas/minuto por token). Falha de
   rede, 429 ou erro 5xx agenda nova tentativa (espera crescente); erros
   definitivos (401/403/422...) ficam como 'rejeitado' com a mensagem da
   API. Depois de 'enviado'/'duplicado', a cópia local é apagada.

A competência (AAAA-MM) é o mês da data de referência do arquivo
(`ArquivoBaixado.data`, a mesma usada na coluna `data` das tabelas).
"""

import os
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config.settings import BPO_ACENE_OUTBOX_DIR, BPO_ACENE_ROTINAS, logger
from src.integrations import bpo_acene_client as client

POLL_INTERVAL = 30  # segundos entre ciclos de verificação da fila
INTERVALO_ENTRE_ENVIOS = 2.5  # segundos — mantém abaixo de 30 chamadas/minuto
MAX_TENTATIVAS = 10
# Espera antes de cada nova tentativa (minutos), pelo número da tentativa que falhou.
ESPERAS_MINUTOS = [1, 2, 5, 10, 30, 60, 120, 240, 480]

_monitor_instance = None


def _codigo_rotina(id_rotina: Optional[int]) -> Optional[str]:
    from config.database import DatabaseService

    if id_rotina is None:
        return None
    rotina = DatabaseService.get_rotina_map(id_rotina)
    return rotina.routine_id if rotina else None


def enfileirar_arquivo(arquivo) -> Optional[int]:
    """
    Coloca na fila de envio uma cópia do arquivo baixado, se aplicável.

    Args:
        arquivo: `config.database.ArquivoBaixado` já importado com sucesso
            (o arquivo ainda precisa existir em disco).

    Returns:
        ID do registro em `envios_bpo`, ou None se o arquivo não se aplica
        (rotina fora da lista, envio desligado, empresa sem token) ou se
        houve falha ao enfileirar.
    """
    from config.database import DatabaseService

    try:
        if not client.envio_configurado():
            return None

        codigo = _codigo_rotina(arquivo.id_rotina)
        if codigo not in BPO_ACENE_ROTINAS:
            return None

        if not DatabaseService.get_company_bpo_acene_token(arquivo.id_empresa):
            logger.info(
                f"ArquivoBaixado {arquivo.id}: empresa {arquivo.id_empresa} sem token BPO ACENE — "
                f"arquivo da rotina {codigo} não será enviado"
            )
            return None

        origem = Path(arquivo.nome_arquivo)
        destino = BPO_ACENE_OUTBOX_DIR / f"{datetime.now():%Y%m%d%H%M%S}_{arquivo.id}_{origem.name}"
        shutil.copy2(origem, destino)

        envio = DatabaseService.create_envio_bpo(
            id_empresa=arquivo.id_empresa,
            id_rotina=arquivo.id_rotina,
            competencia=arquivo.data.strftime("%Y-%m"),
            caminho_arquivo=str(destino),
            nome_arquivo=origem.name,
        )
        return envio.id
    except Exception as e:
        logger.error(f"ArquivoBaixado {arquivo.id}: falha ao enfileirar envio para o BPO ACENE: {e}")
        return None


def _remover_copia(envio) -> None:
    try:
        if os.path.isfile(envio.caminho_arquivo):
            os.remove(envio.caminho_arquivo)
    except OSError as e:
        logger.warning(f"EnvioBpo {envio.id}: falha ao remover cópia '{envio.caminho_arquivo}': {e}")


def processar_envio(envio) -> str:
    """
    Faz uma tentativa de envio de um registro pendente e grava o resultado.

    Returns:
        Novo status do envio ('enviado', 'duplicado', 'rejeitado', 'erro' ou
        'pendente' quando foi reagendado).
    """
    from config.database import DatabaseService

    agora = datetime.utcnow()
    tentativas = envio.tentativas + 1

    if not os.path.isfile(envio.caminho_arquivo):
        DatabaseService.update_envio_bpo(
            envio.id, status="erro", tentativas=tentativas, mensagem="Cópia do arquivo não encontrada em disco"
        )
        logger.error(f"EnvioBpo {envio.id}: cópia não encontrada em '{envio.caminho_arquivo}'")
        return "erro"

    token = DatabaseService.get_company_bpo_acene_token(envio.id_empresa)
    if not token:
        DatabaseService.update_envio_bpo(
            envio.id, status="rejeitado", tentativas=tentativas, mensagem="Empresa sem token BPO ACENE configurado"
        )
        return "rejeitado"

    resultado = client.enviar_arquivo(token, envio.competencia, envio.caminho_arquivo, envio.nome_arquivo)
    campos = {
        "tentativas": tentativas,
        "http_status": resultado.http_status,
        "mensagem": resultado.mensagem,
    }

    if resultado.resultado in (client.ENVIADO, client.DUPLICADO):
        campos.update(
            status=resultado.resultado,
            lote_id=resultado.lote_id,
            lote_status=resultado.lote_status,
            enviado_em=agora,
            proxima_tentativa=None,
        )
        DatabaseService.update_envio_bpo(envio.id, **campos)
        _remover_copia(envio)
        logger.info(
            f"EnvioBpo {envio.id}: '{envio.nome_arquivo}' ({envio.competencia}) {resultado.resultado} — "
            f"lote {resultado.lote_id} ({resultado.lote_status})"
        )
        return resultado.resultado

    if resultado.resultado == client.REJEITADO:
        campos.update(status="rejeitado", proxima_tentativa=None)
        DatabaseService.update_envio_bpo(envio.id, **campos)
        logger.error(
            f"EnvioBpo {envio.id}: '{envio.nome_arquivo}' rejeitado pela API "
            f"(HTTP {resultado.http_status}): {resultado.mensagem}"
        )
        return "rejeitado"

    # TENTAR_NOVAMENTE
    if tentativas >= MAX_TENTATIVAS:
        campos.update(status="erro", proxima_tentativa=None)
        DatabaseService.update_envio_bpo(envio.id, **campos)
        logger.error(f"EnvioBpo {envio.id}: desistindo após {tentativas} tentativas: {resultado.mensagem}")
        return "erro"

    espera = ESPERAS_MINUTOS[min(tentativas - 1, len(ESPERAS_MINUTOS) - 1)]
    campos.update(status="pendente", proxima_tentativa=agora + timedelta(minutes=espera))
    DatabaseService.update_envio_bpo(envio.id, **campos)
    logger.warning(
        f"EnvioBpo {envio.id}: falha temporária (tentativa {tentativas}/{MAX_TENTATIVAS}), "
        f"nova tentativa em {espera} min: {resultado.mensagem}"
    )
    return "pendente"


def reenviar(envio_id: int) -> None:
    """Volta um envio 'rejeitado'/'erro' para a fila (ex: depois de corrigir o token)."""
    from config.database import DatabaseService

    DatabaseService.update_envio_bpo(envio_id, status="pendente", tentativas=0, proxima_tentativa=None)


class EnvioBpoMonitor(threading.Thread):
    """Thread daemon que envia os registros pendentes de `envios_bpo`."""

    def __init__(self, poll_interval: int = POLL_INTERVAL):
        super().__init__(name="EnvioBpoMonitor", daemon=True)
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info(f"EnvioBpoMonitor iniciado (polling a cada {self.poll_interval}s)")
        while not self._stop_event.is_set():
            try:
                self._processar_fila()
            except Exception as e:
                logger.error(f"EnvioBpoMonitor: erro inesperado no ciclo: {e}")
            self._stop_event.wait(self.poll_interval)

    def _processar_fila(self) -> None:
        from config.database import DatabaseService

        if not client.envio_configurado():
            return
        prontos = DatabaseService.get_envios_bpo_prontos(datetime.utcnow())
        for i, envio in enumerate(prontos):
            if self._stop_event.is_set():
                return
            if i:
                self._stop_event.wait(INTERVALO_ENTRE_ENVIOS)
            try:
                processar_envio(envio)
            except Exception as e:
                logger.error(f"EnvioBpoMonitor: falha ao processar EnvioBpo {envio.id}: {e}")


def start_bpo_monitor(poll_interval: int = POLL_INTERVAL) -> EnvioBpoMonitor:
    """Inicia (uma única vez por processo) a thread de envio e a retorna."""
    global _monitor_instance
    if _monitor_instance is not None and _monitor_instance.is_alive():
        return _monitor_instance

    _monitor_instance = EnvioBpoMonitor(poll_interval=poll_interval)
    _monitor_instance.start()
    return _monitor_instance


__all__ = ["enfileirar_arquivo", "processar_envio", "reenviar", "start_bpo_monitor", "EnvioBpoMonitor"]
