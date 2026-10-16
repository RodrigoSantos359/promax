"""
Script avulso de backfill genérico: reprocessa retroativamente QUALQUER
automação (identificada por --automation-id) para um intervalo de datas
passadas, deixando o reconhecimento automático de cabeçalho
(`src/database/file_processor.py`) criar/atualizar o layout
(`map_col_rel_rotina`) e a tabela dinâmica correspondente no Postgres a
partir do próprio arquivo real baixado — nunca de outra rotina.

Generalização de `backfill_14_05_05.py` (mesma técnica: monkeypatch de
`CampoMapConf.resolve_value`, restrito a este processo, para forçar a data
de cada rodada; o download de cada dia entra na fila normal de
`arquivos_baixados`, processada pelo `ArquivoBaixadoMonitor` já rodando no
processo web). Não altera nenhum arquivo do projeto.

Se a rotina não tiver nenhum campo do tipo 'date'/'data' (ex: relatórios que
não são filtrados por período, como "Plano de Contas"), o conceito de
"backfill por dia" não se aplica — o script detecta isso e executa a
automação UMA única vez, taggeando o download com a data final informada.

Uso (dentro do container, a partir de /app):
    python3 -m src.scripts.backfill_routine --automation-id 6 --start 2026-09-01 --end 2026-09-22
    python3 -m src.scripts.backfill_routine --automation-id 7 --end 2026-09-22
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
from src.database.dynamic_tables import build_table_name, postgres_engine


def _get_existing_dates(id_rotina: int) -> set:
    """Datas já presentes na tabela dinâmica desta rotina, se ela já existir."""
    base_table_name = build_table_name(id_rotina)
    version_record = DatabaseService.get_map_col_rel_rotina_version(id_rotina, base_table_name)
    if version_record is None:
        return set()
    with postgres_engine.begin() as conn:
        rows = conn.execute(sql_text(f'SELECT DISTINCT "data" FROM "{version_record.nome_tabela_atual}"')).fetchall()
    return {r[0] for r in rows}


def _daterange(start: date, end: date):
    dia = start
    while dia <= end:
        yield dia
        dia += timedelta(days=1)


def _run_once(automation, company, target_date: date) -> dict:
    """Executa a rotina uma vez (login + navegação + download), sem enqueue."""
    driver = DriverManager.create_driver(headless=True)
    try:
        login = PromaXLogin(
            driver=driver, username=company.username, password=company.get_password(),
            unit=company.unit, logger=logger,
        )
        login_result = login.login()
        if login_result.get("status") != "success":
            return {"status": "failed", "message": f"Login falhou: {login_result.get('error')}"}

        RoutineClass = get_routine_class(automation.routine_id)
        routine = RoutineClass(
            driver=driver, logger=logger, automation_id=automation.id,
            routine_id=automation.routine_id, routine_name=automation.routine_name,
        )
        return routine.execute()
    finally:
        DriverManager.quit_driver(driver)


def _extract_downloaded_files(result: dict) -> list:
    """
    Extrai os arquivos baixados de um resultado de `routine.execute()`,
    cobrindo os formatos possíveis:
    - relatório único: `result["downloaded_file"]`
    - relatório multi-opção (campo com `gerar_lista_opcoes=True`, ex: um
      relatório por banco/portador): `result["reports"]`, uma entrada por
      opção, cada uma com seu próprio `downloaded_file`
    - rotinas com formato próprio (ex: 01.31.60): `result["downloaded_files"]`
    """
    files = []

    reports = result.get("reports")
    if isinstance(reports, list):
        files.extend(r.get("downloaded_file") for r in reports if r.get("downloaded_file"))

    if result.get("downloaded_file"):
        files.append(result["downloaded_file"])

    downloaded_files = result.get("downloaded_files")
    if isinstance(downloaded_files, list):
        files.extend(f for f in downloaded_files if f)

    return files


def _enqueue(id_rotina: int, id_empresa: int, downloaded_file, dia: date) -> None:
    DatabaseService.create_arquivo_baixado(
        id_rotina=id_rotina, id_empresa=id_empresa,
        nome_arquivo=str(downloaded_file), data=dia, status="baixado",
    )


def run_backfill(automation_id: int, start: date = None, end: date = None, poll_after: int = 20) -> None:
    db = SessionLocal()
    try:
        automation = db.query(Automation).filter(Automation.id == automation_id).first()
        if not automation:
            raise SystemExit(f"Automação {automation_id} não encontrada")
        company = db.query(Company).filter(Company.id == automation.company_id).first()
        if not company:
            raise SystemExit(f"Empresa {automation.company_id} não encontrada")
        id_rotina = automation.rotina_map_id
        if id_rotina is None:
            raise SystemExit(f"Automação {automation_id} não tem rotina_map_id associada")

        tem_campo_data = (
            db.query(CampoMapConf)
            .filter(CampoMapConf.rotina_map_id == id_rotina, CampoMapConf.tipo.in_(("date", "data")))
            .count()
            > 0
        )
    finally:
        db.close()

    id_empresa = company.id
    logger.info(
        f"[Backfill automation={automation_id}] rotina={automation.routine_id} "
        f"(id_rotina={id_rotina}) — {'com' if tem_campo_data else 'sem'} campo de data"
    )

    if not tem_campo_data:
        if end is None:
            raise SystemExit("Rotina sem campo de data: informe --end (data de referência para o snapshot único)")
        logger.info(
            f"[Backfill automation={automation_id}] rotina sem campo de data — "
            f"executando uma única vez (snapshot referenciado como {end})"
        )
        try:
            ensure_vpn_connected()
        except Exception as e:
            logger.error(f"[Backfill automation={automation_id}] VPN indisponível, abortando: {e}")
            return

        result = _run_once(automation, company, end)
        downloaded_files = _extract_downloaded_files(result)
        if not downloaded_files:
            logger.warning(
                f"[Backfill automation={automation_id}] nenhum arquivo baixado "
                f"(status={result.get('status')}, msg={result.get('message')})"
            )
            return
        for downloaded_file in downloaded_files:
            _enqueue(id_rotina, id_empresa, downloaded_file, end)
        logger.info(f"[Backfill automation={automation_id}] {len(downloaded_files)} arquivo(s) baixado(s) e enfileirado(s): {downloaded_files}")
        time.sleep(poll_after)
        logger.info(f"[Backfill automation={automation_id}] datas na tabela agora: {sorted(_get_existing_dates(id_rotina))}")
        return

    if start is None or end is None:
        raise SystemExit("Rotina com campo de data: informe --start e --end")

    ja_existentes = _get_existing_dates(id_rotina)
    logger.info(f"[Backfill automation={automation_id}] datas já existentes: {sorted(ja_existentes)}")

    dias_pendentes = [d for d in _daterange(start, end) if d not in ja_existentes]
    logger.info(f"[Backfill automation={automation_id}] {len(dias_pendentes)} dia(s) a processar: {dias_pendentes}")

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
            logger.info(f"[Backfill automation={automation_id}] Processando {dia.strftime('%d/%m/%Y')}...")
            target_date["value"] = dia

            try:
                ensure_vpn_connected()
            except Exception as e:
                logger.error(f"[Backfill automation={automation_id}] VPN indisponível, abortando: {e}")
                break

            try:
                result = _run_once(automation, company, dia)
            except Exception as e:
                logger.error(f"[Backfill automation={automation_id}] Erro ao executar rotina em {dia}: {e}")
                continue

            downloaded_files = _extract_downloaded_files(result)
            if not downloaded_files:
                logger.warning(
                    f"[Backfill automation={automation_id}] Nenhum arquivo baixado para {dia} "
                    f"(status={result.get('status')}, msg={result.get('message')})"
                )
                continue

            for downloaded_file in downloaded_files:
                _enqueue(id_rotina, id_empresa, downloaded_file, dia)
            enfileirados += 1
            logger.info(
                f"[Backfill automation={automation_id}] {dia}: {len(downloaded_files)} arquivo(s) "
                f"baixado(s) e enfileirado(s): {downloaded_files}"
            )
    finally:
        CampoMapConf.resolve_value = original_resolve_value

    logger.info(
        f"[Backfill automation={automation_id}] Concluído: {enfileirados} dia(s) enfileirado(s). "
        f"Aguardando {poll_after}s pelo ArquivoBaixadoMonitor..."
    )
    time.sleep(poll_after)
    logger.info(f"[Backfill automation={automation_id}] Datas na tabela agora: {sorted(_get_existing_dates(id_rotina))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill retroativo genérico de uma automação")
    parser.add_argument("--automation-id", type=int, required=True)
    parser.add_argument("--start", help="Data inicial (YYYY-MM-DD) — obrigatório se a rotina tiver campo de data")
    parser.add_argument("--end", required=True, help="Data final (YYYY-MM-DD)")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else None
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    run_backfill(args.automation_id, start_date, end_date)
