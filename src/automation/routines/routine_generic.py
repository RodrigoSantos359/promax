"""
Rotina genérica — funciona para QUALQUER routine_id, sem lógica de tela
específica escrita em Python.

Usada como fallback por `get_routine_class()` (src/automation/__init__.py)
quando não existe uma classe dedicada para o `routine_id` de uma automação:
em vez de falhar com "rotina não encontrada", a automação roda usando
apenas o que estiver configurado em `camps_map_conf` via `RotinaMap`
(editor de rotinas na interface web) — inclusive campos do tipo 'botao',
que permitem clicar em botões de ação (ex: gerar relatório) sem precisar
escrever uma rotina Python específica.

Se uma tela exigir lógica especial (ex: o workaround de
`document.parentWindow` usado em `Routine14_05_05`), crie uma classe
dedicada em vez de depender da rotina genérica.
"""

from typing import Dict, Any
from src.automation.base import BaseRoutine


class GenericRoutine(BaseRoutine):
    """
    Navega até a tela da rotina via atalho e preenche os campos
    configurados em `camps_map_conf` — sem nenhuma etapa específica de
    tela. `self.routine_id`/`self.routine_name` vêm da automação (passados
    pelo executor), não de atributos fixos de classe.
    """

    ROUTINE_NAME = "Rotina Genérica"

    def execute(self) -> Dict[str, Any]:
        """
        Navega via atalho, aguarda a página carregar e preenche os campos
        mapeados.

        Returns:
            dict: {"status": "success"|"failed", "fields_filled": int,
                   "fields_errors": int, "fields_details": [...], ...}
        """
        self.log_execution_start()

        try:
            if not self.routine_id:
                raise NotImplementedError(
                    "GenericRoutine precisa de um routine_id (via automação ou routine_code)"
                )

            self.navigate_via_shortcut(self.routine_id)

            alerts = self.handle_alerts(max_retries=5)
            self.logger.info(f"Alerts fechados após navegar via atalho: {alerts}")

            ready = self.wait_for_page_ready(timeout=15)
            if not ready:
                self.logger.warning("Timeout aguardando document.readyState == 'complete'; prosseguindo mesmo assim")

            fill_result = self.fill_configured_fields()
            multi_option_campo = fill_result.get("multi_option_campo")

            # Tenta acionar "Visualizar" (workaround document.parentWindow) e
            # baixar o CSV, igual à Routine14_05_05 — best-effort, já que nem
            # toda tela genérica tem esses botões. Com retry automático em
            # caso do relatório demorar demais para gerar no servidor.
            #
            # Se houver um campo 'select' marcado com "lista de opções a ser
            # gerada", gera UM relatório por opção em vez de um único.
            reports = None
            report_triggered = False
            report_ready = False
            downloaded_file = None
            report_alert_text = None
            csv_button_name = self.get_csv_button_name()
            report_ready_timeout = self.get_report_ready_timeout()
            try:
                if multi_option_campo:
                    reports = self.run_multi_option_reports(
                        multi_option_campo, "BotVisualizar", csv_button_name, report_ready_timeout=report_ready_timeout
                    )
                else:
                    report_result = self.trigger_report_and_download(
                        "BotVisualizar", csv_button_name, report_ready_timeout=report_ready_timeout
                    )
                    report_triggered = report_result["report_triggered"]
                    report_ready = report_result["report_ready"]
                    downloaded_file = report_result["downloaded_file"]
                    report_alert_text = report_result.get("alert_text")
            except Exception as e:
                self.logger.info(
                    f"Tela '{self.routine_id}' sem botão de relatório/CSV (ou falhou ao acioná-lo): {str(e)}"
                )

            self.take_screenshot(f"target_screen_{self.routine_id.replace('.', '_')}.png")

            if reports is not None:
                reports_ok = sum(1 for r in reports if r.get("downloaded_file"))
                reports_sem_dados = sum(1 for r in reports if r.get("sem_dados"))
                reports_erro = len(reports) - reports_ok - reports_sem_dados
                result = {
                    "status": "success" if fill_result["errors"] == 0 and reports_erro == 0 and reports else "failed",
                    "fields_filled": fill_result["filled"],
                    "fields_errors": fill_result["errors"],
                    "fields_details": fill_result["details"],
                    "reports": [
                        {**r, "downloaded_file": str(r["downloaded_file"]) if r.get("downloaded_file") else None}
                        for r in reports
                    ],
                    "message": (
                        f"{fill_result['filled']} campo(s) preenchido(s), {fill_result['errors']} erro(s). "
                        f"{reports_ok}/{len(reports)} relatório(s) gerado(s) e baixado(s), "
                        f"{reports_sem_dados} sem dados no período, {reports_erro} erro(s) "
                        f"(campo '{multi_option_campo.nome_campo}')."
                    ),
                }
            else:
                result = {
                    "status": "success" if fill_result["errors"] == 0 else "failed",
                    "fields_filled": fill_result["filled"],
                    "fields_errors": fill_result["errors"],
                    "fields_details": fill_result["details"],
                    "report_triggered": report_triggered,
                    "report_ready": report_ready,
                    "downloaded_file": str(downloaded_file) if downloaded_file else None,
                    "message": (
                        f"{fill_result['filled']} campo(s) preenchido(s), "
                        f"{fill_result['errors']} erro(s). "
                        f"Relatório {'gerado com sucesso' if report_ready else 'não confirmado'}. "
                        f"CSV {'baixado em ' + str(downloaded_file) if downloaded_file else 'não baixado'}"
                        + (f" ({report_alert_text})." if report_alert_text else ".")
                    ),
                }

            self.log_execution_end(result)
            return result

        except Exception as e:
            self.logger.error(f"Erro na rotina genérica '{self.routine_id}': {str(e)}")
            safe_id = (self.routine_id or "desconhecida").replace(".", "_")
            self.take_screenshot(f"error_{safe_id}.png")
            return {
                "status": "failed",
                "error": str(e),
            }


__all__ = ["GenericRoutine"]
