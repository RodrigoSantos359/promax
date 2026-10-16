"""
Rotina 14.05.05 - Lançamentos

Navega do menu principal do PromaX até a tela da rotina 14.05.05 usando o
campo de atalho, exatamente como um usuário faria manualmente, e preenche
os campos configurados na tabela `camps_map_conf` (via
`BaseRoutine.fill_configured_fields()`).

Pré-requisito: o login (usuário/senha/unidade) já deve ter sido realizado
antes de chamar `execute()` — isso é responsabilidade de quem orquestra a
execução (veja `src/automation/executor.py`, que faz login via
`PromaXLogin` antes de instanciar a rotina).
"""

import time
from typing import Dict, Any
from selenium.webdriver.common.by import By
from src.automation.base import BaseRoutine
from src.browser.waits import switch_to_default


class Routine14_05_05(BaseRoutine):
    """
    Rotina 14.05.05 - Lançamentos

    Fluxo (assumindo login já realizado):
    1. Digita "14.05.05" no campo de atalho da tela principal e pressiona Enter
    2. Fecha os alerts que aparecerem
    3. Confirma a chegada na tela alvo (frameset da rotina)
    """

    ROUTINE_ID = "14.05.05"
    ROUTINE_NAME = "Lançamentos"

    # Nomes de frame observados na captura telas/Lançamentos rotina14.05.05.html
    TARGET_FRAME_NAMES = ["rotina", "top_rotina", "bottom_rotina"]

    def execute(self) -> Dict[str, Any]:
        """
        Navega até a tela alvo da rotina 14.05.05.

        Returns:
            dict: {"status": "success", "reached_target_screen": True, ...}
                  ou {"status": "failed", "error": "..."} em caso de falha
        """
        self.log_execution_start()

        try:
            # Passo 1: usar o campo de atalho da tela principal
            self.navigate_via_shortcut(self.ROUTINE_ID)

            # Passo 2: fechar alerts que aparecerem após a navegação
            alerts = self.handle_alerts(max_retries=5)
            self.logger.info(f"Alerts fechados após navegar via atalho: {alerts}")

            self.logger.debug(
                f"Janelas abertas: {len(self.driver.window_handles)} | "
                f"URL atual: {self.driver.current_url} | Título: {self.driver.title}"
            )

            # Passo 3: confirmar chegada na tela alvo
            reached = self._wait_for_target_screen()

            if not reached:
                raise Exception(
                    "Não foi possível confirmar a chegada na tela alvo da rotina 14.05.05 "
                    f"(frames esperados: {self.TARGET_FRAME_NAMES})"
                )

            self.logger.info("Tela alvo da rotina 14.05.05 alcançada com sucesso")

            # Passo 4: preencher os campos configurados em camps_map_conf
            fill_result = self.fill_configured_fields()
            multi_option_campo = fill_result.get("multi_option_campo")

            # Passo 5: acionar "Visualizar" (workaround document.parentWindow) e
            # baixar o CSV, com retry automático em caso do relatório demorar
            # demais para gerar no servidor. Se houver um campo 'select' com
            # "lista de opções a ser gerada", gera um relatório por opção.
            if multi_option_campo:
                reports = self.run_multi_option_reports(multi_option_campo, "BotVisualizar", "GerExecl")
            else:
                report_result = self.trigger_report_and_download("BotVisualizar", "GerExecl")
                reports = None

            self.take_screenshot(f"target_screen_{self.ROUTINE_ID.replace('.', '_')}.png")

            if reports is not None:
                reports_ok = sum(1 for r in reports if r.get("downloaded_file"))
                reports_sem_dados = sum(1 for r in reports if r.get("sem_dados"))
                reports_erro = len(reports) - reports_ok - reports_sem_dados
                success = fill_result["errors"] == 0 and bool(reports) and reports_erro == 0
                result = {
                    "status": "success" if success else "failed",
                    "reached_target_screen": True,
                    "fields_filled": fill_result["filled"],
                    "fields_errors": fill_result["errors"],
                    "fields_details": fill_result["details"],
                    "reports": [
                        {**r, "downloaded_file": str(r["downloaded_file"]) if r.get("downloaded_file") else None}
                        for r in reports
                    ],
                    "message": (
                        f"Tela alvo alcançada. {fill_result['filled']} campo(s) preenchido(s), "
                        f"{fill_result['errors']} erro(s). {reports_ok}/{len(reports)} relatório(s) "
                        f"gerado(s) e baixado(s), {reports_sem_dados} sem dados no período, "
                        f"{reports_erro} erro(s) (campo '{multi_option_campo.nome_campo}')."
                    ),
                }
            else:
                report_triggered = report_result["report_triggered"]
                report_ready = report_result["report_ready"]
                downloaded_file = report_result["downloaded_file"]

                success = (
                    fill_result["errors"] == 0
                    and report_triggered
                    and report_ready
                    and downloaded_file is not None
                )

                result = {
                    "status": "success" if success else "failed",
                    "reached_target_screen": True,
                    "fields_filled": fill_result["filled"],
                    "fields_errors": fill_result["errors"],
                    "fields_details": fill_result["details"],
                    "report_triggered": report_triggered,
                    "report_ready": report_ready,
                    "downloaded_file": str(downloaded_file) if downloaded_file else None,
                    "message": (
                        f"Tela alvo alcançada. {fill_result['filled']} campo(s) preenchido(s), "
                        f"{fill_result['errors']} erro(s). "
                        f"Relatório {'gerado com sucesso' if report_ready else 'não confirmado'}. "
                        f"CSV {'baixado em ' + str(downloaded_file) if downloaded_file else 'não baixado'}"
                        + (f" ({report_result.get('alert_text')})." if report_result.get('alert_text') else ".")
                    ),
                }

            self.log_execution_end(result)
            return result

        except Exception as e:
            self.logger.error(f"Erro na rotina 14.05.05: {str(e)}")
            self.take_screenshot(f"error_{self.ROUTINE_ID.replace('.', '_')}.png")
            return {
                "status": "failed",
                "error": str(e),
                "reached_target_screen": False,
            }

    def _wait_for_target_screen(self, timeout: int = 20, poll_interval: float = 0.5) -> bool:
        """
        Confirma que a navegação chegou na tela da rotina, verificando a
        presença de um dos frames conhecidos do frameset alvo.

        Args:
            timeout: tempo máximo de espera em segundos
            poll_interval: intervalo entre tentativas

        Returns:
            bool: True se algum dos frames esperados foi encontrado
        """
        end_time = time.time() + timeout

        frame_selector = ", ".join(f"frame[name='{name}']" for name in self.TARGET_FRAME_NAMES)

        while time.time() < end_time:
            switch_to_default(self.driver)
            try:
                frames = self.driver.find_elements(By.CSS_SELECTOR, frame_selector)
                if frames:
                    found_names = [f.get_attribute("name") for f in frames]
                    self.logger.info(f"Frame(s) da tela alvo detectado(s): {found_names}")
                    return True
            except Exception as e:
                self.logger.debug(f"Erro ao verificar frames da tela alvo: {str(e)}")

            time.sleep(poll_interval)

        return False
