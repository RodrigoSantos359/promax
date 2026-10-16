"""
Script avulso de backfill: reprocessa retroativamente a automação da rotina
14.05.05 (automation_id=1) para um intervalo de datas passadas, inserindo os
dados extraídos na tabela dinâmica já existente ('rel_1_140505_v1' no
Postgres, por padrão).

Não faz parte do fluxo normal do sistema (agendador ou tela de execução) e
NÃO altera nenhum arquivo do projeto: usa monkeypatch em tempo de execução,
com escopo restrito a este processo, para forçar a data dos campos
'date'/'data' da rotina a cada rodada (em vez do padrão "ontem"). O download
de cada dia é enfileirado em `arquivos_baixados` exatamente como um download
normal — quem de fato valida o cabeçalho e insere os dados na tabela
dinâmica é o `ArquivoBaixadoMonitor` já rodando no processo web (nenhuma
lógica de importação é duplicada aqui).

Datas que já existem na tabela de destino são automaticamente puladas.

Uso (dentro do container, a partir de /app):
    python3 -m src.scripts.backfill_14_05_05 --start 2026-09-01 --end 2026-09-22
    python3 -m src.scripts.backfill_14_05_05 --start 2026-09-01 --end 2026-09-22 --table rel_1_140505_v1
"""

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text as sql_text

from config import logger
from config.database import Automation, CampoMapConf, Company, DatabaseService, SessionLocal
from src.automation import get_routine_class
from src.automation.login import PromaXLogin
from src.browser.driver import DriverManager
from src.browser.vpn_check import ensure_vpn_connected
from src.database.dynamic_tables import postgres_engine

AUTOMATION_ID = 1


def _get_existing_dates(table_name: str) -> set:
    with postgres_engine.begin() as conn:
        rows = conn.execute(sql_text(f'SELECT DISTINCT "data" FROM "{table_name}"')).fetchall()
    return {r[0] for r in rows}


def _daterange(start: date, end: date):
    dia = start
    while dia <= end:
        yield dia
        dia += timedelta(days=1)


def run_backfill(start: date, end: date, table_name: str = "rel_1_140505_v1", poll_after: int = 20) -> None:
    db = SessionLocal()
    try:
        automation = db.query(Automation).filter(Automation.id == AUTOMATION_ID).first()
        if not automation:
            raise SystemExit(f"Automação {AUTOMATION_ID} não encontrada")
        company = db.query(Company).filter(Company.id == automation.company_id).first()
        if not company:
            raise SystemExit(f"Empresa {automation.company_id} não encontrada")
        id_rotina = automation.rotina_map_id
        id_empresa = company.id
        routine_id = automation.routine_id
        routine_name = automation.routine_name
        username = company.username
        password = company.get_password()
        unit = company.unit
    finally:
        db.close()

    if id_rotina is None:
        raise SystemExit(f"Automação {AUTOMATION_ID} não tem rotina_map_id associada")

    ja_existentes = _get_existing_dates(table_name)
    logger.info(f"[Backfill 14.05.05] Datas já existentes em '{table_name}': {sorted(ja_existentes)}")

    dias_pendentes = [d for d in _daterange(start, end) if d not in ja_existentes]
    logger.info(f"[Backfill 14.05.05] {len(dias_pendentes)} dia(s) a processar: {dias_pendentes}")

    # Monkeypatch de CampoMapConf.resolve_value, restrito a este processo:
    # força os campos 'date'/'data' da rotina para a data-alvo da iteração
    # atual, em vez do padrão de produção (execução - 1 dia).
    original_resolve_value = CampoMapConf.resolve_value
    target_date = {"value": None}

    def resolve_value_patched(self, execution_date=None):
        if self.tipo in ("date", "data"):
            return target_date["value"].strftime("%d/%m/%Y")
        return original_resolve_value(self, execution_date)

    CampoMapConf.resolve_value = resolve_value_patched

    enfileirados = 0
    try:
        for dia in dias_pendentes:
            logger.info(f"[Backfill 14.05.05] Processando {dia.strftime('%d/%m/%Y')}...")
            target_date["value"] = dia

            try:
                ensure_vpn_connected()
            except Exception as e:
                logger.error(f"[Backfill 14.05.05] VPN indisponível, abortando: {e}")
                break

            driver = DriverManager.create_driver(headless=True)
            try:
                login = PromaXLogin(driver=driver, username=username, password=password, unit=unit, logger=logger)
                login_result = login.login()
                if login_result.get("status") != "success":
                    logger.error(f"[Backfill 14.05.05] Login falhou em {dia}: {login_result.get('error')}")
                    continue

                RoutineClass = get_routine_class(routine_id)
                routine = RoutineClass(
                    driver=driver,
                    logger=logger,
                    automation_id=AUTOMATION_ID,
                    routine_id=routine_id,
                    routine_name=routine_name,
                )
                result = routine.execute()
            except Exception as e:
                logger.error(f"[Backfill 14.05.05] Erro ao executar rotina em {dia}: {e}")
                continue
            finally:
                DriverManager.quit_driver(driver)

            downloaded_file = result.get("downloaded_file")
            if not downloaded_file:
                logger.warning(
                    f"[Backfill 14.05.05] Nenhum arquivo baixado para {dia} "
                    f"(status={result.get('status')}, msg={result.get('message')})"
                )
                continue

            # Entra na fila normal de importação — o ArquivoBaixadoMonitor
            # (já rodando no processo web) valida o cabeçalho e insere os
            # dados na tabela dinâmica, exatamente como um download do dia.
            DatabaseService.create_arquivo_baixado(
                id_rotina=id_rotina,
                id_empresa=id_empresa,
                nome_arquivo=str(downloaded_file),
                data=dia,
                status="baixado",
            )
            enfileirados += 1
            logger.info(f"[Backfill 14.05.05] {dia}: baixado e enfileirado para importação ({downloaded_file})")
    finally:
        CampoMapConf.resolve_value = original_resolve_value

    logger.info(
        f"[Backfill 14.05.05] Concluído: {enfileirados} dia(s) enfileirado(s) para importação. "
        f"Aguardando {poll_after}s pelo ArquivoBaixadoMonitor processar a fila..."
    )
    time.sleep(poll_after)
    logger.info(f"[Backfill 14.05.05] Datas em '{table_name}' agora: {sorted(_get_existing_dates(table_name))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill retroativo da rotina 14.05.05")
    parser.add_argument("--start", required=True, help="Data inicial (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Data final (YYYY-MM-DD)")
    parser.add_argument("--table", default="rel_1_140505_v1", help="Tabela dinâmica de destino")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    run_backfill(start_date, end_date, table_name=args.table)
