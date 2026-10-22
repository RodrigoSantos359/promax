"""
Ponto de entrada da aplicação PromaX Automation.

Uso:
    python main.py                  # Executar teste simples
    python main.py --web            # Iniciar interface web Flask
    python main.py --help           # Mostrar ajuda
"""

import logging
import os
import sys
import argparse
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from config import logger
from config.database import init_db, seed_default_company, DatabaseService
from src.browser import DriverManager
from src.automation import AVAILABLE_ROUTINES, get_routine_class
from src.automation.executor import TaskExecutor
from src.automation.scheduler import AutomationScheduler, get_scheduler
from src.automation.execution_queue import start_queue_worker
from src.database.file_monitor import start_monitor
from src.integrations.bpo_acene_outbox import start_bpo_monitor


def test_automation():
    """Testa automação com exemplo simples."""
    logger.info("=== MODO TESTE ===")
    logger.info("Iniciando PromaX Automation Suite")

    driver = None
    try:
        if not AVAILABLE_ROUTINES:
            logger.warning("[AVISO] Nenhuma rotina registrada")
            logger.info("\nProximos passos:")
            logger.info("1. Crie uma rotina em src/automation/routines/routine_XX_XX_XX.py")
            logger.info("2. Registre em src/automation/__init__.py")
            return

        logger.info(f"[OK] Rotinas disponiveis: {len(AVAILABLE_ROUTINES)}")
        for routine_id in AVAILABLE_ROUTINES:
            logger.info(f"  - {routine_id}")

        # Executar primeira rotina
        routine_id = list(AVAILABLE_ROUTINES.keys())[0]
        logger.info(f"\n[EXECUTANDO] Rotina: {routine_id}")

        driver = DriverManager.create_driver(headless=False)
        RoutineClass = get_routine_class(routine_id)
        routine = RoutineClass(driver=driver, logger=logger)

        result = routine.execute()
        logger.info(f"\n[OK] Resultado: {result}")

    except Exception as e:
        logger.error(f"[ERRO] {str(e)}", exc_info=True)
        sys.exit(1)

    finally:
        if driver:
            DriverManager.quit_driver(driver)

    logger.info("PromaX Automation concluido")


def run_web_interface():
    """Inicia a interface web Flask."""
    logger.info("=== MODO WEB ===")

    try:
        # Inicializar banco de dados
        logger.info("Inicializando banco de dados...")
        init_db()
        seed_default_company()
        logger.info("[OK] Banco de dados ready")

        # Com o reloader do Flask (debug=True), este módulo é executado duas
        # vezes (processo pai "watcher" + processo filho que serve de fato);
        # WERKZEUG_RUN_MAIN só existe no filho, evitando iniciar a thread
        # de monitoramento duas vezes.
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            start_monitor()
            start_bpo_monitor()

            # Agendador de automações (cron) + fila de execução: antes só
            # rodava via `python main.py --scheduler` num processo separado
            # (rotina do Windows) — no container Docker (só `--web`) isso
            # nunca iniciava, então nenhuma automação disparava por horário.
            start_queue_worker(logger=logger)
            scheduler = get_scheduler()
            scheduler.schedule_all_active()
            scheduler.start()
            jobs = scheduler.list_jobs()
            logger.info(f"[OK] Scheduler iniciado com {len(jobs)} automação(ões) agendada(s)")

        # Importar app Flask
        from src.ui.app import app
        from config.settings import FLASK_PORT

        logger.info(f"[OK] Iniciando Flask em http://localhost:{FLASK_PORT}")
        logger.info("Pressione CTRL+C para parar")
        logger.info("")

        app.run(
            host="0.0.0.0",
            port=FLASK_PORT,
            debug=True,
        )

    except ImportError:
        logger.error("[ERRO] Flask nao esta instalado")
        logger.info("Instale com: pip install flask")
        sys.exit(1)

    except Exception as e:
        logger.error(f"[ERRO] Erro ao iniciar web: {str(e)}", exc_info=True)
        sys.exit(1)


def run_executor_test():
    """Testa o executor com uma automacao configurada."""
    logger.info("=== TESTE DO EXECUTOR ===")

    try:
        # Inicializar banco de dados
        init_db()
        start_monitor()
        start_bpo_monitor()

        # Criar empresa de teste
        company = DatabaseService.create_company(
            name="Teste Demo",
            promax_url="https://dibrasa.promaxcloud.com.br/",
            username="filipe",
            password="Acene003",
            unit="161.0001 - Dibrasa",
        )
        logger.info(f"[OK] Empresa criada: {company.name} (ID: {company.id})")

        # Criar automacao de teste
        from datetime import datetime, timedelta
        automation = DatabaseService.create_automation(
            company_id=company.id,
            routine_id="14.05.05",
            routine_name="Lancamentos",
            start_date=datetime.utcnow(),
            execution_time="10:00",
            interval="daily",
            max_retries=2,
            retry_delay=30,
        )
        logger.info(f"[OK] Automacao criada: {automation.routine_name} (ID: {automation.id})")

        # Executar
        logger.info(f"\n[EXECUTANDO] Automacao...")
        executor = TaskExecutor()
        result = executor.execute_automation(
            automation_id=automation.id,
            company_id=company.id,
            headless=False,
        )
        logger.info(f"[OK] Resultado: {result}")

    except Exception as e:
        logger.error(f"[ERRO] {str(e)}", exc_info=True)
        sys.exit(1)


def run_scheduler(automation_id: int = None):
    """
    Inicia o agendador (cron) de automações.

    Se `automation_id` for informado, agenda apenas essa automação;
    caso contrário, agenda todas as automações ativas.
    """
    logger.info("=== MODO SCHEDULER (CRON) ===")

    try:
        init_db()
        start_monitor()
        start_bpo_monitor()
        start_queue_worker(logger=logger)

        scheduler = AutomationScheduler(logger=logger)

        if automation_id:
            trigger = scheduler.schedule_automation(automation_id)
            if trigger is None:
                logger.warning(f"Automação {automation_id} não foi agendada (inativa ou inexistente)")
                return
        else:
            scheduler.schedule_all_active()

        scheduler.start()

        jobs = scheduler.list_jobs()
        logger.info(f"[OK] {len(jobs)} job(s) agendado(s):")
        for job in jobs:
            logger.info(f"  - {job.id}: próxima execução em {job.next_run_time}")

        logger.info("Scheduler rodando. Pressione CTRL+C para parar.")

        import time
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Interrompido pelo usuário")
        finally:
            scheduler.shutdown()

    except Exception as e:
        logger.error(f"[ERRO] {str(e)}", exc_info=True)
        sys.exit(1)


def main():
    """Função principal com argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="PromaX Automation Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py                     # Teste simples
  python main.py --web               # Interface web
  python main.py --executor          # Teste do executor
  python main.py --init-db           # Inicializar banco de dados
  python main.py --scheduler         # Agenda todas as automações ativas
  python main.py --scheduler --automation-id 1   # Agenda só a automação id=1
        """
    )

    parser.add_argument(
        "--web",
        action="store_true",
        help="Iniciar interface web Flask"
    )
    parser.add_argument(
        "--executor",
        action="store_true",
        help="Testar executor com automação"
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Inicializar banco de dados"
    )
    parser.add_argument(
        "--scheduler",
        action="store_true",
        help="Iniciar o agendador (cron) de automações"
    )
    parser.add_argument(
        "--automation-id",
        type=int,
        default=None,
        help="Usado com --scheduler: agenda apenas esta automação (padrão: todas as ativas)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="PromaX Automation 1.0.0"
    )

    args = parser.parse_args()

    # Executar baseado em argumentos
    if args.web:
        run_web_interface()

    elif args.executor:
        run_executor_test()

    elif args.scheduler:
        run_scheduler(automation_id=args.automation_id)

    elif args.init_db:
        logger.info("Inicializando banco de dados...")
        init_db()
        seed_default_company()
        logger.info("[OK] Banco de dados inicializado com sucesso")

    else:
        # Teste padrão
        test_automation()


if __name__ == "__main__":
    main()
