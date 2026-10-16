"""
Agendador de automações (cron) baseado em APScheduler.

Lê a configuração de uma automação (tabela `automations`, incluindo o JSON
de `schedule_config` para frequências semanais/mensais) e monta o
CronTrigger correspondente, disparando `TaskExecutor.execute_with_retry()`
no horário configurado — usando `max_retries`/`retry_delay` já cadastrados
na própria automação.

Exemplo:
    scheduler = AutomationScheduler()
    scheduler.schedule_automation(1)   # agenda só a automação id=1
    scheduler.start()                  # começa a disparar nos horários certos
"""

import json
import logging
from typing import Optional

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.database import SessionLocal, Automation
from config.settings import TIMEZONE, logger as config_logger
from src.automation.execution_queue import enqueue_automation

# Mapeia nossa convenção de dia da semana (0=Domingo ... 6=Sábado, usada no
# schedule_config de automações 'weekly') para os nomes que o APScheduler
# espera no campo day_of_week do CronTrigger.
WEEKDAY_NAMES = {
    0: "sun",
    1: "mon",
    2: "tue",
    3: "wed",
    4: "thu",
    5: "fri",
    6: "sat",
}


class AutomationScheduler:
    """Agenda e dispara automações do PromaX conforme configurado no banco de dados."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or config_logger
        self.scheduler = BackgroundScheduler(timezone=TIMEZONE)

    def build_trigger(self, automation: Automation) -> CronTrigger:
        """
        Monta o CronTrigger do APScheduler a partir de `interval`,
        `schedule_config` e `execution_time` da automação.

        Regras de conversão:
            - daily:   dispara todo dia no horário configurado
            - weekly:  usa schedule_config.days (lista de 0-6, 0=Domingo)
            - monthly:
                - first_day:  dia 1 do mês
                - last_day:   último dia do mês (CronTrigger day='last')
                - specific_day: dia fixo (schedule_config.day, 2-28)
                - recurrence: a cada N dias a partir de um dia inicial,
                              usando a sintaxe start/step do cron
                              (ex: "3/5" = dias 3, 8, 13, 18, 23, 28)

        Raises:
            ValueError: se a configuração for inválida/incompleta
        """
        try:
            hour_str, minute_str = automation.execution_time.split(":")
            hour, minute = int(hour_str), int(minute_str)
        except (ValueError, AttributeError):
            raise ValueError(
                f"execution_time inválido para automação {automation.id}: "
                f"{automation.execution_time!r} (esperado 'HH:MM')"
            )

        schedule_config = {}
        if automation.schedule_config:
            try:
                schedule_config = json.loads(automation.schedule_config)
            except (TypeError, ValueError):
                self.logger.warning(
                    f"schedule_config inválido para automação {automation.id}, ignorando: "
                    f"{automation.schedule_config!r}"
                )

        interval = automation.interval

        if interval == "daily":
            return CronTrigger(hour=hour, minute=minute)

        if interval == "weekly":
            days = schedule_config.get("days") or []
            if not days:
                raise ValueError(
                    f"Automação {automation.id} é semanal mas schedule_config não tem 'days'"
                )
            day_of_week = ",".join(WEEKDAY_NAMES[d] for d in days)
            return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)

        if interval == "monthly":
            tipo = schedule_config.get("type", "first_day")

            if tipo == "first_day":
                return CronTrigger(day=1, hour=hour, minute=minute)

            if tipo == "last_day":
                return CronTrigger(day="last", hour=hour, minute=minute)

            if tipo == "specific_day":
                day = schedule_config.get("day")
                if not day:
                    raise ValueError(
                        f"Automação {automation.id}: tipo 'specific_day' sem 'day' em schedule_config"
                    )
                return CronTrigger(day=day, hour=hour, minute=minute)

            if tipo == "recurrence":
                every_n_days = schedule_config.get("every_n_days")
                start_day = schedule_config.get("start_day")
                if not every_n_days or not start_day:
                    raise ValueError(
                        f"Automação {automation.id}: 'recurrence' precisa de "
                        f"'every_n_days' e 'start_day' em schedule_config"
                    )
                return CronTrigger(day=f"{start_day}/{every_n_days}", hour=hour, minute=minute)

            raise ValueError(f"Tipo mensal desconhecido para automação {automation.id}: {tipo!r}")

        raise ValueError(f"Intervalo desconhecido para automação {automation.id}: {interval!r}")

    def schedule_automation(self, automation_id: int) -> CronTrigger:
        """
        Cria (ou substitui) o job agendado para uma automação específica,
        lendo a configuração diretamente do banco de dados.

        Args:
            automation_id: ID da automação (tabela automations)

        Returns:
            CronTrigger: o trigger montado (útil para inspeção/log)

        Raises:
            ValueError: se a automação não existir ou a configuração for inválida
        """
        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            if not automation:
                raise ValueError(f"Automação não encontrada: {automation_id}")

            if not automation.is_active:
                self.logger.info(f"Automação {automation_id} está inativa; não será agendada")
                self.unschedule_automation(automation_id)
                return None

            trigger = self.build_trigger(automation)
            job_id = f"automation_{automation_id}"

            self.scheduler.add_job(
                self._run_automation,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                args=[automation.id, automation.company_id],
                misfire_grace_time=3600,
            )

            self.logger.info(
                f"Automação {automation_id} ({automation.routine_name}) agendada: "
                f"interval={automation.interval}, horário={automation.execution_time}, "
                f"trigger={trigger}"
            )
            return trigger
        finally:
            db.close()

    def _run_automation(self, automation_id: int, company_id: int) -> None:
        """
        Callback executado pelo APScheduler exatamente no horário agendado.

        Não executa a automação diretamente — apenas enfileira (veja
        `src.automation.execution_queue`). Isso evita que várias automações
        agendadas para o mesmo horário disputem recursos/sessão do PromaX
        ao mesmo tempo: a fila garante execução uma por vez, na ordem em
        que os disparos do cron aconteceram.
        """
        self.logger.info(f"[CRON] Automação {automation_id} (company_id={company_id}) disparada, enfileirando")
        enqueue_automation(automation_id, company_id, logger=self.logger)

    def unschedule_automation(self, automation_id: int) -> None:
        """Remove o job agendado de uma automação (ex: ao desativá-la ou torná-la inativa)."""
        job_id = f"automation_{automation_id}"
        try:
            self.scheduler.remove_job(job_id)
            self.logger.info(f"Automação {automation_id} removida do agendamento")
        except JobLookupError:
            pass

    def schedule_all_active(self) -> None:
        """Agenda todas as automações ativas cadastradas no banco de dados."""
        db = SessionLocal()
        try:
            automation_ids = [
                a.id for a in db.query(Automation).filter(Automation.is_active == True).all()
            ]
        finally:
            db.close()

        for automation_id in automation_ids:
            try:
                self.schedule_automation(automation_id)
            except Exception as e:
                self.logger.error(f"Erro ao agendar automação {automation_id}: {str(e)}")

    def start(self) -> None:
        """Inicia o scheduler (não bloqueia — roda em thread de background)."""
        self.scheduler.start()
        self.logger.info("Scheduler iniciado")

    def shutdown(self, wait: bool = True) -> None:
        """Para o scheduler."""
        self.scheduler.shutdown(wait=wait)
        self.logger.info("Scheduler finalizado")

    def list_jobs(self):
        """Retorna os jobs agendados (para inspeção/log)."""
        return self.scheduler.get_jobs()


_scheduler_instance: Optional["AutomationScheduler"] = None


def get_scheduler() -> "AutomationScheduler":
    """
    Retorna a instância única (por processo) do `AutomationScheduler`,
    criando-a na primeira chamada. Usada tanto para iniciar o agendamento
    (main.py) quanto para mantê-lo sincronizado quando automações são
    criadas/editadas/ativadas pela API (src/ui/app.py), sem precisar
    reiniciar o processo.
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AutomationScheduler()
    return _scheduler_instance


__all__ = ["AutomationScheduler", "get_scheduler"]
