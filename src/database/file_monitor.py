"""
Thread de monitoramento em background: observa a tabela auxiliar
`arquivos_baixados` por registros com status "baixado" e dispara o
processamento de cada um (validação de cabeçalho + extração/inserção na
tabela dinâmica correspondente — veja `src/database/file_processor.py`).

Implementado como polling simples (sem fila/broker externo) porque a
gravação em `arquivos_baixados` já é feita via SQLAlchemy/SQLite pelo
próprio `TaskExecutor`; um polling curto é suficiente e mantém a
infraestrutura do projeto simples.
"""

import threading

from config.settings import logger

DEFAULT_POLL_INTERVAL = 15  # segundos

_monitor_instance = None


class ArquivoBaixadoMonitor(threading.Thread):
    """Thread daemon que faz polling de `arquivos_baixados` (status == 'baixado')."""

    def __init__(self, poll_interval: int = DEFAULT_POLL_INTERVAL):
        super().__init__(name="ArquivoBaixadoMonitor", daemon=True)
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info(f"ArquivoBaixadoMonitor iniciado (polling a cada {self.poll_interval}s)")
        while not self._stop_event.is_set():
            try:
                self._process_pending()
            except Exception as e:
                logger.error(f"ArquivoBaixadoMonitor: erro inesperado no ciclo de polling: {e}")
            self._stop_event.wait(self.poll_interval)

    def _process_pending(self) -> None:
        from config.database import DatabaseService
        from src.database.file_processor import process_arquivo_baixado

        pendentes = DatabaseService.get_arquivos_baixados(status="baixado")
        if not pendentes:
            return

        logger.info(f"ArquivoBaixadoMonitor: {len(pendentes)} arquivo(s) pendente(s) de processamento")
        for arquivo in pendentes:
            try:
                novo_status = process_arquivo_baixado(arquivo)
            except Exception as e:
                logger.error(f"ArquivoBaixadoMonitor: falha ao processar ArquivoBaixado {arquivo.id}: {e}")
                novo_status = "erro_processamento"

            # "removido": em caso de sucesso, `process_arquivo_baixado` já
            # apagou o arquivo e o próprio registro — nada mais a atualizar.
            if novo_status == "removido":
                continue

            try:
                DatabaseService.update_arquivo_baixado_status(arquivo.id, novo_status)
            except Exception as e:
                logger.error(f"ArquivoBaixadoMonitor: falha ao atualizar status do ArquivoBaixado {arquivo.id}: {e}")


def start_monitor(poll_interval: int = DEFAULT_POLL_INTERVAL) -> ArquivoBaixadoMonitor:
    """Inicia (uma única vez por processo) a thread de monitoramento e a retorna."""
    global _monitor_instance
    if _monitor_instance is not None and _monitor_instance.is_alive():
        return _monitor_instance

    _monitor_instance = ArquivoBaixadoMonitor(poll_interval=poll_interval)
    _monitor_instance.start()
    return _monitor_instance
