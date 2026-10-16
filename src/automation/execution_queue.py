"""
Fila de execução de automações agendadas.

Existem hoje 11 automações cadastradas com o mesmo horário de disparo — sem
uma fila, o `AutomationScheduler` (APScheduler) dispararia todas ao mesmo
tempo, cada uma abrindo seu próprio Chrome headless e fazendo login no
PromaX simultaneamente. Isso arrisca contenção de recursos (várias
instâncias do Chrome ao mesmo tempo) e conflitos de sessão (logins
concorrentes com o mesmo usuário no PromaX).

Este módulo resolve isso com uma fila FIFO simples + uma única thread
worker: o disparo do cron (`AutomationScheduler._run_automation`) apenas
enfileira o pedido (rápido, não bloqueia o APScheduler); a thread worker
consome a fila e executa as automações uma de cada vez, na ordem em que
foram enfileiradas.
"""

import logging
import queue
import threading
from typing import Optional, Tuple

from config.settings import logger as config_logger
from src.automation.executor import TaskExecutor

_queue: "queue.Queue[Tuple[int, int]]" = queue.Queue()
_worker_thread: Optional[threading.Thread] = None
_executor: Optional[TaskExecutor] = None


def enqueue_automation(automation_id: int, company_id: int, logger: Optional[logging.Logger] = None) -> None:
    """Enfileira uma automação para execução (consumida em ordem pela thread worker)."""
    log = logger or config_logger
    _queue.put((automation_id, company_id))
    log.info(
        f"[Fila de execução] Automação {automation_id} (company_id={company_id}) enfileirada "
        f"(tamanho atual da fila: {_queue.qsize()})"
    )


def queue_size() -> int:
    """Quantidade de automações aguardando execução na fila."""
    return _queue.qsize()


def _worker(logger: logging.Logger) -> None:
    logger.info("[Fila de execução] Worker iniciado — processando automações uma por vez")
    while True:
        automation_id, company_id = _queue.get()
        try:
            logger.info(f"[Fila de execução] Executando automação {automation_id} (company_id={company_id})")
            result = _executor.execute_with_retry(automation_id=automation_id, company_id=company_id)
            logger.info(f"[Fila de execução] Automação {automation_id} concluída: {result.get('status')}")
        except Exception as e:
            logger.error(f"[Fila de execução] Erro ao executar automação {automation_id}: {e}", exc_info=True)
        finally:
            _queue.task_done()


def start_queue_worker(logger: Optional[logging.Logger] = None) -> threading.Thread:
    """Inicia (uma única vez por processo) a thread worker que consome a fila."""
    global _worker_thread, _executor
    if _worker_thread is not None and _worker_thread.is_alive():
        return _worker_thread

    log = logger or config_logger
    _executor = TaskExecutor(logger=log)
    _worker_thread = threading.Thread(target=_worker, args=(log,), name="AutomationQueueWorker", daemon=True)
    _worker_thread.start()
    return _worker_thread


__all__ = ["enqueue_automation", "queue_size", "start_queue_worker"]
