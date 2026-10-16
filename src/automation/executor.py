"""
Executor de tarefas de automação.
Orquestra a execução de rotinas com retry, logging e persistência.

Exemplo:
    executor = TaskExecutor()
    result = executor.execute_automation(automation_id=1, company_id=1)
"""

import json
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from src.browser.driver import DriverManager
from src.browser.vpn_check import ensure_vpn_connected
from src.automation.login import PromaXLogin
from src.automation import get_routine_class
from config.database import SessionLocal, Automation, Company, DatabaseService
from config.settings import logger as config_logger


logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executor elegante para tarefas de automação."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Args:
            logger: Logger customizado (usa padrão se None)
        """
        self.logger = logger or config_logger

    def execute_automation(
        self,
        automation_id: int,
        company_id: int,
        headless: bool = True,
    ) -> Dict[str, Any]:
        """
        Executa uma automação com retry automático.

        Args:
            automation_id: ID da automação a executar
            company_id: ID da empresa
            headless: Executar em modo headless

        Returns:
            dict: Resultado da execução
        """
        start_time = datetime.utcnow()
        start_seconds = time.time()

        driver = None
        try:
            self.logger.info(f"Iniciando execução: automation_id={automation_id}, company_id={company_id}")

            # 1. Obter configurações
            automation, company = self._get_config(automation_id, company_id)
            if not automation or not company:
                raise ValueError(f"Configuração não encontrada: automation_id={automation_id}")

            # 2. Verificar VPN (o PromaX da Dibrasa só é acessível com a VPN
            # FortiClient conectada) — falha rápido com mensagem clara em vez
            # de abrir o Chrome e esperar ~20-30s por um timeout de rede.
            ensure_vpn_connected()

            # 3. Criar driver
            driver = DriverManager.create_driver(headless=headless)

            # 4. Fazer login
            login_result = self._login(driver, company)
            if login_result["status"] != "success":
                raise Exception(f"Login falhou: {login_result.get('error')}")

            # 5. Executar rotina
            result = self._execute_routine(
                driver=driver,
                automation=automation,
                company=company,
            )

            # 6. Fechar driver
            DriverManager.quit_driver(driver)
            driver = None

            # 6.5 Registrar, na tabela auxiliar `arquivos_baixados`, cada
            # arquivo baixado (ou tentativa) nesta execução, associado à
            # rotina e à empresa corretas.
            self._log_downloaded_files(automation, company, result, start_time)

            # 7. Registrar execução, refletindo o status que a PRÓPRIA rotina
            # retornou (ex: "failed" quando o CSV não foi baixado), e não um
            # "success" fixo — do contrário, uma falha silenciosa (sem
            # exceção) nunca apareceria no dashboard.
            routine_status = result.get("status", "success")
            error_message = result.get("error") or (
                None if routine_status == "success" else result.get("message")
            )
            duration = time.time() - start_seconds
            self._log_execution(
                automation_id=automation_id,
                company_id=company_id,
                status=routine_status,
                processed_count=result.get("fields_filled", result.get("processed", 0)),
                error_count=result.get("fields_errors", result.get("errors", 0)),
                error_message=error_message,
                duration_seconds=duration,
                result_data=result,
            )

            self.logger.info(f"Execução concluída: {result}")
            return {
                "status": routine_status,
                "automation_id": automation_id,
                "result": result,
                "duration_seconds": duration,
            }

        except Exception as e:
            self.logger.error(f"Erro na execução: {str(e)}", exc_info=True)

            duration = time.time() - start_seconds
            self._log_execution(
                automation_id=automation_id,
                company_id=company_id,
                status="failed",
                error_message=str(e),
                duration_seconds=duration,
            )

            return {
                "status": "failed",
                "automation_id": automation_id,
                "error": str(e),
                "duration_seconds": duration,
            }

        finally:
            if driver:
                DriverManager.quit_driver(driver)

    def execute_with_retry(
        self,
        automation_id: int,
        company_id: int,
        max_retries: Optional[int] = None,
        retry_delay: Optional[int] = None,
        headless: bool = True,
    ) -> Dict[str, Any]:
        """
        Executa uma automação com retry automático em caso de falha.

        Args:
            automation_id: ID da automação
            company_id: ID da empresa
            max_retries: Máximo de tentativas (usa config se None)
            retry_delay: Delay entre tentativas em segundos (usa config se None)
            headless: Executar em modo headless

        Returns:
            dict: Resultado final após retries
        """
        # Obter configurações padrão
        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            if not automation:
                raise ValueError(f"Automação não encontrada: {automation_id}")

            max_retries = max_retries or automation.max_retries
            retry_delay = retry_delay or automation.retry_delay

        finally:
            db.close()

        # Executar com retry
        last_error = None
        for attempt in range(1, max_retries + 1):
            self.logger.info(f"Tentativa {attempt}/{max_retries}")

            result = self.execute_automation(
                automation_id=automation_id,
                company_id=company_id,
                headless=headless,
            )

            if result["status"] == "success":
                return result

            last_error = result.get("error")
            if attempt < max_retries:
                self.logger.warning(f"Tentativa {attempt} falhou. Aguardando {retry_delay}s...")
                time.sleep(retry_delay)

        # Todas as tentativas falharam
        return {
            "status": "failed",
            "automation_id": automation_id,
            "error": f"Falhou após {max_retries} tentativas: {last_error}",
            "attempts": max_retries,
        }

    def _get_config(self, automation_id: int, company_id: int):
        """Obtém configurações de banco de dados."""
        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == automation_id).first()
            company = db.query(Company).filter(Company.id == company_id).first()
            return automation, company
        finally:
            db.close()

    def _login(self, driver, company: Company) -> Dict[str, Any]:
        """Realiza login no PromaX."""
        try:
            password = company.get_password()
            login = PromaXLogin(
                driver=driver,
                username=company.username,
                password=password,
                unit=company.unit,
                logger=self.logger,
            )
            return login.login()
        except Exception as e:
            self.logger.error(f"Erro ao fazer login: {str(e)}")
            return {"status": "failed", "error": str(e)}

    def _execute_routine(
        self,
        driver,
        automation: Automation,
        company: Company,
    ) -> Dict[str, Any]:
        """Executa a rotina específica."""
        try:
            RoutineClass = get_routine_class(automation.routine_id)
            routine = RoutineClass(
                driver=driver,
                logger=self.logger,
                automation_id=automation.id,
                routine_id=automation.routine_id,
                routine_name=automation.routine_name,
            )
            result = routine.execute()
            return result
        except Exception as e:
            self.logger.error(f"Erro ao executar rotina: {str(e)}")
            raise

    def _log_downloaded_files(
        self,
        automation: Automation,
        company: Company,
        result: Dict[str, Any],
        triggered_at: datetime,
    ) -> None:
        """
        Registra na tabela auxiliar `arquivos_baixados` cada arquivo baixado
        (ou tentativa de download) desta execução, para auditoria e
        associação correta com a rotina (`automation.rotina_map_id`) e a
        empresa (`company.id`).

        `data` é a data de referência dos dados do relatório: por padrão, o
        dia anterior ao disparo da automação (mesma convenção da coluna
        "data" das tabelas dinâmicas de relatório) — mas a própria rotina
        pode sobrescrever isso via `result["reference_date"]` quando essa
        convenção não se aplica (ex: 01.31.60, cujo arquivo sempre reflete o
        dia real da geração, "hoje", não "ontem").
        """
        try:
            id_rotina = automation.rotina_map_id
            if id_rotina is None:
                self.logger.warning(
                    f"Automação {automation.id} sem rotina_map_id associada — "
                    "arquivo(s) baixado(s) não puderam ser registrados em 'arquivos_baixados'"
                )
                return

            data_referencia = result.get("reference_date") or (triggered_at - timedelta(days=1)).date()
            reports = result.get("reports")
            downloaded_files = result.get("downloaded_files")

            if isinstance(reports, list) and reports:
                entries = [
                    (r.get("downloaded_file"), "sem_dados" if r.get("sem_dados") else None)
                    for r in reports
                ]
            elif isinstance(downloaded_files, list):
                entries = [(f, None) for f in downloaded_files] or [(None, None)]
            else:
                entries = [(result.get("downloaded_file"), None)]

            for downloaded_file, forced_status in entries:
                if downloaded_file:
                    # "baixado" (e não "success") é o status que a thread de
                    # monitoramento (`src.database.file_monitor`) observa para
                    # disparar a validação de cabeçalho + extração dos dados.
                    status = "baixado"
                elif forced_status:
                    status = forced_status
                else:
                    status = "failed"

                DatabaseService.create_arquivo_baixado(
                    id_rotina=id_rotina,
                    id_empresa=company.id,
                    nome_arquivo=str(downloaded_file) if downloaded_file else None,
                    data=data_referencia,
                    status=status,
                )
        except Exception as e:
            self.logger.error(f"Erro ao registrar arquivo(s) baixado(s) em 'arquivos_baixados': {str(e)}")

    def _log_execution(
        self,
        automation_id: int,
        company_id: int,
        status: str,
        processed_count: int = 0,
        error_count: int = 0,
        error_message: str = None,
        duration_seconds: float = None,
        result_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra execução no banco de dados."""
        try:
            result_data_json = None
            if result_data is not None:
                try:
                    result_data_json = json.dumps(result_data, ensure_ascii=False, default=str)
                except (TypeError, ValueError) as e:
                    self.logger.warning(f"Não foi possível serializar result_data: {str(e)}")

            DatabaseService.log_execution(
                automation_id=automation_id,
                company_id=company_id,
                status=status,
                processed_count=processed_count,
                error_count=error_count,
                error_message=error_message,
                duration_seconds=duration_seconds,
                result_data=result_data_json,
            )
        except Exception as e:
            self.logger.error(f"Erro ao registrar execução: {str(e)}")


class ExecutionResult:
    """Classe para representar resultado de execução."""

    def __init__(
        self,
        status: str,
        automation_id: int,
        duration_seconds: float,
        message: str = "",
        error: str = None,
        result_data: Dict[str, Any] = None,
    ):
        self.status = status
        self.automation_id = automation_id
        self.duration_seconds = duration_seconds
        self.message = message
        self.error = error
        self.result_data = result_data or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Converte resultado para dicionário."""
        return {
            "status": self.status,
            "automation_id": self.automation_id,
            "duration_seconds": self.duration_seconds,
            "message": self.message,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "result_data": self.result_data,
        }

    def __repr__(self):
        return f"<ExecutionResult(status={self.status}, automation_id={self.automation_id}, duration={self.duration_seconds}s)>"


__all__ = ["TaskExecutor", "ExecutionResult"]
