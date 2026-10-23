"""
Classe base para automações de rotinas no PromaX.
Fornece funcionalidades comuns para todas as rotinas.
"""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, UnexpectedAlertPresentException

from pathlib import Path

from config.settings import SELENIUM_WAIT_TIMEOUT, PROMAX_URL, SELECTORS, DOWNLOAD_DIR, LOGS_DIR
from src.browser.waits import (
    switch_to_default,
    wait_for_element_across_frames,
    list_files,
    wait_for_new_download,
)


class BaseRoutine(ABC):
    """
    Classe base para todas as automações de rotinas PromaX.

    Fornece métodos comuns para navegação, esperas, tratamento de erros, etc.

    Exemplo:
        class Routine14_05_05(BaseRoutine):
            ROUTINE_ID = "14.05.05"

            def execute(self) -> dict:
                self.navigate_to_routine()
                self._process_data()
                return {"status": "success"}
    """

    ROUTINE_ID: str = None
    ROUTINE_NAME: str = None
    ROUTINE_URL: str = None

    def __init__(
        self,
        driver: WebDriver,
        logger: Optional[logging.Logger] = None,
        timeout: int = SELENIUM_WAIT_TIMEOUT,
        automation_id: Optional[int] = None,
        routine_id: Optional[str] = None,
        routine_name: Optional[str] = None,
    ):
        """
        Args:
            driver: Instância do WebDriver Selenium
            logger: Logger para registrar operações
            timeout: Timeout padrão para esperas explícitas (segundos)
            automation_id: ID da automação (tabela automations), usado para
                           buscar os mapeamentos de campo em camps_map_conf
            routine_id: código da rotina (ex: "14.05.05"). Sobrescreve
                        `self.ROUTINE_ID` — usado por rotinas genéricas que
                        não têm um código fixo definido na classe.
            routine_name: nome da rotina, para logs. Sobrescreve `self.ROUTINE_NAME`.
        """
        self.driver = driver
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.timeout = timeout
        self.wait = WebDriverWait(driver, timeout)
        self.automation_id = automation_id
        self.routine_id = routine_id or self.ROUTINE_ID
        self.routine_name = routine_name or self.ROUTINE_NAME

    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """
        Executa a rotina principal.

        Returns:
            dict: Resultado da execução com status, dados processados, etc.
                  Exemplo: {"status": "success", "processed": 10, "errors": 0}
        """
        pass

    def navigate_to_routine(self, url_override: Optional[str] = None) -> None:
        """
        Navega até a rotina.

        Args:
            url_override: URL customizada (sobrescreve ROUTINE_URL)
        """
        url = url_override or self.ROUTINE_URL
        if not url:
            raise NotImplementedError(f"{self.__class__.__name__} deve definir ROUTINE_URL")

        full_url = PROMAX_URL.rstrip("/") + url
        self.logger.info(f"Navegando para: {full_url}")
        self.driver.get(full_url)

    def navigate_via_shortcut(self, routine_code: Optional[str] = None, timeout: Optional[int] = None) -> bool:
        """
        Usa o campo de atalho da tela principal do PromaX para chegar na tela
        da rotina, como um usuário faria manualmente: digita o código
        (ex: "14.05.05") no campo <input name="atalho"> e pressiona Enter,
        que dispara VerificaTeclaPress('13','AtalhoMenu()') no PromaX.

        Args:
            routine_code: código da rotina (usa self.routine_id se None)
            timeout: timeout customizado para localizar o campo de atalho

        Returns:
            bool: True se o campo de atalho foi encontrado e preenchido

        Raises:
            Exception: se o campo de atalho não for encontrado em nenhum frame
        """
        code = routine_code or self.routine_id
        if not code:
            raise NotImplementedError(f"{self.__class__.__name__} deve definir ROUTINE_ID ou informar routine_code")

        timeout = timeout or self.timeout

        switch_to_default(self.driver)
        atalho_input = wait_for_element_across_frames(
            self.driver,
            By.CSS_SELECTOR,
            SELECTORS.get("shortcut_input", "input[name='atalho']"),
            timeout=timeout,
        )

        if atalho_input is None:
            raise Exception("Campo de atalho não encontrado em nenhum frame da tela principal")

        atalho_input.clear()
        atalho_input.send_keys(code)
        self.logger.info(f"Atalho digitado: {code}")

        handles_before = self.driver.window_handles

        # Envia Enter (keyCode 13), que dispara VerificaTeclaPress('13','AtalhoMenu()')
        atalho_input.send_keys(Keys.ENTER)
        self.logger.info("Enter enviado no campo de atalho (AtalhoMenu())")

        # A rotina pode abrir em uma nova janela/aba (popup) em vez de navegar
        # na mesma janela — se isso ocorrer, troca o contexto do driver para ela.
        self._switch_to_new_window_if_opened(handles_before, wait_seconds=3)

        return True

    def _switch_to_new_window_if_opened(self, handles_before: list, wait_seconds: float = 3) -> bool:
        """
        Aguarda até `wait_seconds` por uma nova janela/aba do navegador e,
        se aparecer, troca o contexto do driver para ela.

        Args:
            handles_before: lista de window handles antes da ação que pode abrir a nova janela
            wait_seconds: tempo máximo de espera

        Returns:
            bool: True se trocou para uma nova janela
        """
        end_time = time.time() + wait_seconds

        while time.time() < end_time:
            current_handles = self.driver.window_handles
            new_handles = [h for h in current_handles if h not in handles_before]

            if new_handles:
                self.driver.switch_to.window(new_handles[0])
                self.logger.info(f"Nova janela/aba detectada e trocada (total de janelas: {len(current_handles)})")
                return True

            time.sleep(0.2)

        return False

    def click_report_button(self, button_name: str = "BotVisualizar", timeout: int = 10) -> Dict[str, Any]:
        """
        Aciona um botão de relatório do PromaX (ex: "Visualizar") contornando
        o uso de `document.parentWindow` (API proprietária do Internet
        Explorer, ausente no Chromium) presente no `onclick` original.

        Muitas telas de relatório do PromaX seguem este padrão:
            function Visualizar(){
                if( !ValidaParRel() ){ return false; }
                document.parentWindow.parent.top_rotina.document.all.unidade.disabled = true;
                AbreProgressBar(btnCancelar);
                document.form1.opcao.value = 1;
                document.form1.submit();
            }
        `document.parentWindow` não existe no Chromium (retorna undefined),
        o que quebra a função antes de chegar no submit. Este método
        reproduz a mesma lógica substituindo `document.parentWindow` por
        `window` — equivalentes na prática, já que ambos referenciam a
        window que possui o document atual.

        Args:
            button_name: atributo `name` do botão (padrão: "BotVisualizar")
            timeout: tempo máximo para localizar o botão

        Returns:
            dict: {"ok": True} em caso de sucesso, ou
                  {"ok": False, "reason": "validacao_falhou"} se a validação
                  do formulário (ValidaParRel) rejeitar os dados preenchidos

        Raises:
            Exception: se o botão não for encontrado em nenhum frame
        """
        switch_to_default(self.driver)
        btn = wait_for_element_across_frames(self.driver, By.NAME, button_name, timeout=timeout)

        if btn is None:
            raise Exception(f"Botão '{button_name}' não encontrado em nenhum frame")

        script = """
            // ValidaParRel() chama FormataCampo() nos campos de data, que por
            // sua vez chama VB_FormataCampo() — função só de VBScript
            // (<script language="VbScript">, silenciosamente ignorado pelo
            // Chromium), ausente em JS e por isso lançando ReferenceError
            // antes de ValidaParRel() concluir. Como os campos de data já são
            // preenchidos por nós no formato correto (DD/MM/AAAA), um stub
            // que devolve o valor sem alteração é seguro.
            if (typeof window.VB_FormataCampo === 'undefined') {
                window.VB_FormataCampo = function(valor, mascara, xMasc) { return valor; };
            }
            if (!window.ValidaParRel()) { return {ok: false, reason: 'validacao_falhou'}; }
            try {
                window.parent.top_rotina.document.all.unidade.disabled = true;
            } catch (e) {
                // Campo 'unidade' pode não existir em todas as telas; não é crítico.
            }
            window.AbreProgressBar(window.btnCancelar);
            window.document.form1.opcao.value = 1;
            window.document.form1.submit();
            return {ok: true};
        """

        try:
            result = self.driver.execute_script(script)
        except UnexpectedAlertPresentException as e:
            # O ChromeDriver já descarta o alert automaticamente ao levantar
            # essa exceção (unexpected alert behaviour = "dismiss and
            # notify") — o texto só pode ser recuperado de `e.alert_text`,
            # NUNCA tentando reabrir `driver.switch_to.alert` depois (já não
            # existe mais nesse ponto).
            alert_text = getattr(e, "alert_text", None) or self._accept_pending_alert()
            self.logger.warning(
                f"Alert nativo bloqueou o clique em '{button_name}' (dados provavelmente inválidos "
                f"para esta opção): '{alert_text}'"
            )
            return {"ok": False, "reason": "alerta_bloqueado", "alert_text": alert_text}

        if not isinstance(result, dict):
            # `ValidaParRel()`/o próprio submit podem disparar um alert()
            # nativo de forma assíncrona (aparece só no comando seguinte,
            # não durante o execute_script) — nesse caso o script retorna
            # algo inesperado (None/undefined) em vez do dict esperado.
            alert_text = self._accept_pending_alert()
            if alert_text:
                self.logger.warning(f"Alert nativo detectado após clicar em '{button_name}': '{alert_text}'")
                return {"ok": False, "reason": "alerta_bloqueado", "alert_text": alert_text}
            self.logger.warning(f"Clique em '{button_name}' retornou resultado inesperado: {result!r}")
            return {"ok": False, "reason": "resultado_inesperado"}

        self.logger.info(f"Botão '{button_name}' acionado via workaround JS: {result}")
        return result

    def _accept_pending_alert(self) -> Optional[str]:
        """Se houver um alert nativo aberto, aceita e retorna seu texto (senão None)."""
        try:
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            alert.accept()
            return alert_text
        except Exception:
            return None

    def trigger_report_and_download(
        self,
        report_button_name: str = "BotVisualizar",
        csv_button_name: str = "GerExecl",
        max_attempts: int = 2,
        click_timeout: int = 10,
        report_ready_timeout: int = 30,
        download_timeout: int = 30,
        rename_suffix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Aciona "Visualizar" e baixa o CSV, com retry automático quando o
        clique estoura o timeout fixo de 300s do ChromeDriver
        ("Timed out receiving message from renderer").

        Esse timeout acontece quando o relatório do PromaX demora demais
        para ser gerado no servidor (observado em produção: ~4-5 minutos
        em relatórios pesados, como "Situação dos Títulos" - 12.06.07) e
        não indica que o clique falhou — o formulário provavelmente já foi
        submetido, só a resposta do script não chegou a tempo. Por isso,
        antes de tentar clicar de novo, primeiro verificamos se o relatório
        já ficou pronto (pode ter terminado bem depois do nosso timeout).

        Args:
            report_button_name: nome do botão "Visualizar" (padrão: "BotVisualizar")
            csv_button_name: nome do botão de exportação CSV (padrão: "GerExecl")
            max_attempts: máximo de tentativas de clique em "Visualizar"
            click_timeout: timeout para localizar o botão "Visualizar"
            report_ready_timeout: timeout para aguardar o relatório ficar pronto
                após um clique bem-sucedido
            download_timeout: timeout para aguardar o download do CSV
            rename_suffix: se informado, prefixa o nome do arquivo baixado com
                esse valor (sanitizado) — usado para identificar de qual opção
                da lista o relatório veio, quando há geração em lote

        Returns:
            dict: {"report_triggered": bool, "report_ready": bool,
                   "downloaded_file": Optional[Path], "attempts": int}
        """
        report_ready = False
        report_triggered = False
        downloaded_file = None
        click_reason = None
        alert_text = None
        # Uma vez que o clique tenha "pegado" (sucesso confirmado, ou timeout
        # do ChromeDriver que provavelmente já submeteu o formulário mesmo
        # assim), NUNCA clicamos de novo — a página já mudou de estado após
        # o primeiro submit (campos desabilitados, formulário trocado por um
        # painel de progresso, etc.), e um segundo clique em Visualizar()
        # tende a quebrar com erros de JS (ex: "Cannot read properties of
        # null"), já visto em produção. As tentativas restantes servem só
        # para dar mais tempo ao `wait_for_report_ready`, não para re-clicar.
        click_done = False

        for attempt in range(1, max_attempts + 1):
            if not click_done:
                try:
                    click_result = self.click_report_button(report_button_name, timeout=click_timeout)
                    report_triggered = bool(click_result.get("ok"))
                    if not report_triggered:
                        click_reason = click_result.get("reason")
                        alert_text = click_result.get("alert_text")
                        self.logger.warning(
                            f"Validação do formulário rejeitou os dados (tentativa {attempt}/{max_attempts}): {click_result}"
                        )
                        break
                    click_done = True
                except TimeoutException as e:
                    self.logger.warning(
                        f"Timeout ao clicar em '{report_button_name}' (tentativa {attempt}/{max_attempts}): {str(e)}. "
                        "Verificando se o relatório terminou de gerar mesmo assim..."
                    )
                    report_triggered = True
                    click_done = True

            try:
                report_ready = self.wait_for_report_ready(timeout=report_ready_timeout)
            except UnexpectedAlertPresentException as e:
                # Alert nativo enquanto aguarda o relatório: geralmente é uma
                # validação de negócio real (ex: "Não há notas para
                # listar"), não uma falha da automação — o ChromeDriver já
                # descarta o alert ao levantar essa exceção, então o texto
                # só existe em `e.alert_text`.
                alert_text = getattr(e, "alert_text", None)
                self.logger.info(f"Alert nativo ao aguardar o relatório: '{alert_text}'")
                break

            if report_ready:
                break

            if attempt < max_attempts:
                self.logger.warning(
                    f"Relatório não ficou pronto na tentativa {attempt}/{max_attempts}; aguardando mais um pouco "
                    "(sem clicar de novo, já que o clique anterior foi confirmado)."
                )

        if report_ready:
            downloaded_file = self.download_report_file(
                csv_button_name, timeout=download_timeout, rename_suffix=rename_suffix
            )

        return {
            "report_triggered": report_triggered,
            "report_ready": report_ready,
            "downloaded_file": downloaded_file,
            "click_reason": click_reason,
            "alert_text": alert_text,
        }

    def run_multi_option_reports(
        self,
        campo,
        report_button_name: str = "BotVisualizar",
        csv_button_name: str = "GerExecl",
        report_ready_timeout: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Gera um relatório por opção de um campo 'select' marcado com
        `gerar_lista_opcoes=True` (configurado no editor de rotinas, seção
        "Lista de opções a ser gerada" ao lado de "Informação a Inserir").

        Para cada opção: seleciona o valor no <select>, aciona "Visualizar"
        + baixa o CSV (via `trigger_report_and_download`), com o nome do
        arquivo prefixado pelo texto da opção (facilita achar/debugar qual
        arquivo é de qual opção). Depois de cada relatório (exceto o
        último), volta para a tela de filtros (`driver.back()`) para poder
        selecionar a próxima opção.

        `opcoes_modo`:
            - 'todas': varre em tempo de execução TODAS as opções que
              existirem no <select> da página (via Selenium `Select.options`)
            - 'manual': usa apenas a lista de opções em `campo.opcoes_lista`
              (JSON de strings, cada uma tentada por texto visível e, se não
              encontrar, pelo `value` da opção)

        Args:
            campo: CampoMapConf com gerar_lista_opcoes=True
            report_button_name: nome do botão "Visualizar"
            csv_button_name: nome do botão de exportação CSV

        Returns:
            list[dict]: um item por opção processada, cada um com
                {"opcao": str, "report_triggered": bool, "report_ready": bool,
                 "downloaded_file": Optional[Path], "error": Optional[str]}
        """
        by, value_locator = self._extract_locator_from_html(campo.select)

        if campo.opcoes_modo == "todas":
            element = wait_for_element_across_frames(self.driver, by, value_locator, timeout=10)
            if element is None:
                raise Exception(f"Campo '{campo.nome_campo}' não encontrado para listar opções: ({by}, {value_locator})")
            opcoes = [
                opt.text.strip()
                for opt in Select(element).options
                if opt.text.strip() and (opt.get_attribute("value") or "").strip()
                and not opt.text.strip().lstrip("-").strip().lower().startswith("selecionar")
            ]
        else:
            try:
                opcoes = json.loads(campo.opcoes_lista) if campo.opcoes_lista else []
            except (TypeError, ValueError):
                opcoes = []

        if not opcoes:
            self.logger.warning(f"Campo '{campo.nome_campo}' marcado para lista de opções, mas nenhuma opção disponível")
            return []

        self.logger.info(f"Gerando {len(opcoes)} relatório(s) para o campo '{campo.nome_campo}': {opcoes}")

        results: List[Dict[str, Any]] = []
        # Janela da tela de filtros: o relatório abre em outra janela, e é
        # para cá que o robô deve voltar entre uma opção e outra.
        self._filter_window = self.driver.current_window_handle
        self._filter_url = self.driver.current_url
        self.logger.info(f"Janelas abertas antes das opções: {len(self.driver.window_handles)}")

        for index, opcao in enumerate(opcoes):
            entry: Dict[str, Any] = {"opcao": opcao}
            try:
                element = wait_for_element_across_frames(self.driver, by, value_locator, timeout=10)
                if element is None:
                    raise Exception(f"Campo '{campo.nome_campo}' não encontrado no frameset: ({by}, {value_locator})")

                # Garante o período antes de cada portador: depois de um
                # alerta ("Nenhuma informação" / "Data inválida") o PromaX pode
                # limpar as datas mesmo com a tela de filtros já de volta.
                if index:
                    self.fill_configured_fields()
                self._apply_field_value(element, "select", opcao, campo.select)
                self.logger.info(f"Opção selecionada em '{campo.nome_campo}': {opcao!r} ({index + 1}/{len(opcoes)})")

                # Relatórios de portadores grandes (ex: 237) levam mais que o
                # padrão de 30s para exportar o CSV.
                report_result = self.trigger_report_and_download(
                    report_button_name,
                    csv_button_name,
                    report_ready_timeout=report_ready_timeout,
                    download_timeout=120,
                    rename_suffix=opcao,
                )
                entry.update(report_result)

                # Mesmo padrão do except abaixo, mas para quando o alert sem
                # texto aparece DENTRO do execute_script do clique (síncrono)
                # em vez de aparecer depois, ao aguardar o relatório
                # (assíncrono) — ambos os casos indicam a mesma coisa: esta
                # opção provavelmente não tem lançamentos no período.
                if report_result.get("click_reason") == "alerta_bloqueado" and not report_result.get("alert_text"):
                    entry["sem_dados"] = True
                # "Nenhuma informação encontrada" é o alerta do PromaX para
                # portador sem movimento no período: não é erro.
                alerta = (report_result.get("alert_text") or "").lower()
                if not report_result.get("downloaded_file") and "nenhuma informação" in alerta:
                    entry["sem_dados"] = True

            except UnexpectedAlertPresentException as e:
                # O ChromeDriver já descarta o alert ao levantar essa
                # exceção; o texto só existe em `e.alert_text` (tentar
                # `driver.switch_to.alert` depois disso não acha nada).
                #
                # Um alert SEM texto, nesse ponto do fluxo (logo após o
                # submit do relatório), é o padrão observado quando o
                # PromaX não tem lançamentos para a opção/período — não é
                # um erro da automação, então não conta como falha.
                alert_text = getattr(e, "alert_text", None)
                if alert_text:
                    entry.update({
                        "report_triggered": False, "report_ready": False, "downloaded_file": None,
                        "error": f"alerta_bloqueado: {alert_text}",
                    })
                    self.logger.warning(f"Alert nativo bloqueou a opção '{opcao}' de '{campo.nome_campo}': '{alert_text}'")
                else:
                    entry.update({
                        "report_triggered": True, "report_ready": False, "downloaded_file": None,
                        "sem_dados": True,
                    })
                    self.logger.info(
                        f"Opção '{opcao}' de '{campo.nome_campo}' sem relatório (provavelmente sem lançamentos no período)"
                    )
            except Exception as e:
                entry.update({"report_triggered": False, "report_ready": False, "downloaded_file": None, "error": str(e)})
                self.logger.error(f"Erro ao gerar relatório para a opção '{opcao}' de '{campo.nome_campo}': {str(e)}")

            # O relatório da opção abre em outra janela: fecha essa janela
            # antes de qualquer outro comando, para não ficar preso nela.
            self._fechar_janelas_de_relatorio()

            # Garante que nenhum alert nativo (ex: validação que rejeitou a
            # opção) fique pendente — um alert aberto bloqueia TODOS os
            # comandos WebDriver seguintes (inclusive o retorno à tela de
            # filtros abaixo), abortando o restante do lote inteiro.
            self._accept_pending_alert()

            results.append(entry)

            is_last = index == len(opcoes) - 1
            if not is_last:
                self._return_to_filter_screen(by, value_locator)

        return results

    def _describe_window_current(self) -> str:
        """Título e URL (curta) da janela atual, para diagnóstico."""
        try:
            return f"title={self.driver.title!r} url={self.driver.current_url[:140]!r}"
        except Exception as e:
            return f"(sem detalhes: {e})"

    def _describe_windows(self) -> str:
        """Lista as janelas abertas (título e URL), para diagnóstico. Volta para a janela atual."""
        atual = self.driver.current_window_handle
        partes = []
        try:
            for i, handle in enumerate(self.driver.window_handles):
                self.driver.switch_to.window(handle)
                marca = " (filtro)" if handle == getattr(self, "_filter_window", None) else ""
                partes.append(f"[{i}]{marca} {self._describe_window_current()}")
            self.driver.switch_to.window(atual)
        except Exception as e:
            return f"(falha ao listar: {e})"
        return " | ".join(partes)

    def _fechar_janelas_de_relatorio(self) -> None:
        """
        Fecha as janelas abertas pelo relatório (todas exceto a da tela de
        filtros, guardada em `self._filter_window`) e volta para a tela de
        filtros. Não faz novo login: é a mesma sessão.
        """
        filtro = getattr(self, "_filter_window", None)
        if not filtro:
            return
        try:
            for handle in list(self.driver.window_handles):
                if handle == filtro:
                    continue
                self.driver.switch_to.window(handle)
                self.driver.close()
                self.logger.info("Janela do relatório fechada")
            if filtro in self.driver.window_handles:
                self.driver.switch_to.window(filtro)
        except Exception as e:
            self.logger.warning(f"Falha ao fechar janelas de relatório: {str(e)}")

    def _return_to_filter_screen(self, by, value_locator) -> bool:
        """
        Volta para a tela de filtros entre uma opção e outra da geração em
        lote (`run_multi_option_reports`).

        Primeiro tenta `history.back()` (rápido); como essa navegação nem
        sempre restaura corretamente TODOS os frames do frameset (observado
        em produção: `driver.back()` às vezes deixa o campo do select
        inacessível — "não encontrado no frameset" — mesmo a tela parecendo
        ter voltado), confirma se o campo do select reapareceu. Se não
        reaparecer, refaz a navegação do zero pelo atalho e repreenche os
        outros campos configurados (mais lento, mas confiável).

        Returns:
            bool: True se a tela de filtros foi restaurada (por um dos dois
                  caminhos), False se ambos falharem
        """
        # O relatório abre em outra janela: fecha essas janelas e volta para a
        # da tela de filtros. Se o select já estiver ali, não há nada a
        # "voltar" (um history.back nessa janela tiraria a tela de filtros).
        self._fechar_janelas_de_relatorio()

        # Recarrega a URL da tela de filtros guardada no início, a cada
        # portador (mesma sessão, sem novo login): começa de uma tela limpa,
        # sem o estado deixado pelo alerta do portador anterior.
        url_filtro = getattr(self, "_filter_url", None)
        if url_filtro:
            try:
                self.driver.get(url_filtro)
                self.wait_for_page_ready(timeout=15)
                self._accept_pending_alert()
                if wait_for_element_across_frames(self.driver, by, value_locator, timeout=10) is not None:
                    # Recarregar a tela zera o período: preenche de novo.
                    self.fill_configured_fields()
                    return True
            except Exception as e:
                self.logger.warning(f"Falha ao recarregar a tela de filtros: {str(e)}")

        if wait_for_element_across_frames(self.driver, by, value_locator, timeout=5) is not None:
            return True

        try:
            switch_to_default(self.driver)
            self.driver.execute_script("window.history.back();")
            self.wait_for_page_ready(timeout=10)
            self._accept_pending_alert()
        except Exception as e:
            self.logger.warning(f"Falha ao executar history.back(): {str(e)}")

        if wait_for_element_across_frames(self.driver, by, value_locator, timeout=5) is not None:
            return True

        self.logger.warning(
            "history.back() não restaurou a tela de filtros (select não encontrado); "
            "renavegando do zero pelo atalho e repreenchendo os campos."
        )
        try:
            if not self.routine_id:
                return False
            try:
                self.navigate_via_shortcut(self.routine_id)
            except Exception:
                # Depois do alerta "Nenhuma informação encontrada" (portador
                # sem movimento no período), a página sai da tela principal e
                # o campo de atalho some: reabre a página inicial do PromaX
                # (mesma sessão) e tenta o atalho de novo.
                self.logger.warning("Campo de atalho ausente; reabrindo a página inicial do PromaX")
                self.driver.get(PROMAX_URL)
                self.wait_for_page_ready(timeout=15)
                self._accept_pending_alert()
                self.navigate_via_shortcut(self.routine_id)
            self.handle_alerts(max_retries=5)
            self.wait_for_page_ready(timeout=15)
            self.fill_configured_fields()
            return True
        except Exception as e:
            self.logger.error(f"Falha ao renavegar do zero para a tela de filtros: {str(e)}")
            return False

    def wait_for_report_ready(
        self,
        timeout: int = 30,
        poll_interval: float = 1.0,
        marker_text: str = "Imprimir",
    ) -> bool:
        """
        Aguarda o relatório terminar de processar, procurando por um
        elemento característico da barra de ferramentas do relatório
        (ex: o link/botão "Imprimir").

        Args:
            timeout: tempo máximo de espera em segundos
            poll_interval: intervalo entre tentativas
            marker_text: texto característico da tela de relatório pronta

        Returns:
            bool: True se o relatório terminou de carregar
        """
        end_time = time.time() + timeout
        xpath = f"//*[contains(text(), '{marker_text}')]"

        while time.time() < end_time:
            element = wait_for_element_across_frames(self.driver, By.XPATH, xpath, timeout=1)
            if element is not None:
                self.logger.info(f"Relatório pronto (marcador '{marker_text}' encontrado)")
                return True
            time.sleep(poll_interval)

        return False

    def download_report_file(
        self,
        button_name: str = "GerExecl",
        timeout: int = 30,
        download_dir: Optional[Path] = None,
        rename_suffix: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Clica em um botão de exportação de relatório (ex: "CSV", cujo botão
        real é `<button name="GerExecl" onclick="Excel()">`) e aguarda o
        arquivo ser baixado para `download_dir` (padrão: settings.DOWNLOAD_DIR,
        já configurado como pasta de downloads do Chrome em `DriverManager`).

        Diferente de `click_report_button()`, os botões de exportação
        (CSV/PDF/Salvar) usam apenas `document.all.form1.submit()` — sem
        `document.parentWindow` — então um clique normal do Selenium já
        funciona no Chromium, sem necessidade de workaround via JS.

        Args:
            button_name: atributo `name` do botão (padrão: "GerExecl", botão "CSV")
            timeout: tempo máximo de espera pelo download, em segundos
            download_dir: pasta onde o arquivo deve aparecer (usa DOWNLOAD_DIR se None)
            rename_suffix: se informado, o arquivo baixado é renomeado com
                esse valor (sanitizado) como prefixo, para facilitar
                identificar/debugar qual opção gerou qual arquivo em uma
                geração em lote (ex: "999_Todas__14.05.05_PW04234R_...csv.inf")

        Returns:
            Path do arquivo baixado, ou None se o download não foi confirmado
            dentro do timeout

        Raises:
            Exception: se o botão não for encontrado em nenhum frame
        """
        download_dir = download_dir or DOWNLOAD_DIR
        download_dir.mkdir(parents=True, exist_ok=True)

        switch_to_default(self.driver)
        btn = wait_for_element_across_frames(self.driver, By.NAME, button_name, timeout=timeout)

        if btn is None:
            raise Exception(f"Botão '{button_name}' não encontrado em nenhum frame")

        files_before = list_files(download_dir)

        btn.click()
        self.logger.info(f"Botão '{button_name}' clicado; aguardando download em {download_dir}")

        downloaded_file = wait_for_new_download(download_dir, files_before, timeout=timeout)

        if downloaded_file is None:
            self.logger.error(f"Download não confirmado após clicar em '{button_name}'")
            return None

        self.logger.info(f"Arquivo baixado com sucesso: {downloaded_file}")

        if rename_suffix:
            safe_suffix = re.sub(r"[^A-Za-z0-9_-]+", "_", rename_suffix).strip("_") or "opcao"
            new_path = downloaded_file.with_name(f"{safe_suffix}__{downloaded_file.name}")
            try:
                downloaded_file = downloaded_file.rename(new_path)
                self.logger.info(f"Arquivo renomeado para identificar a opção: {downloaded_file}")
            except OSError as e:
                self.logger.warning(f"Não foi possível renomear o arquivo com o sufixo da opção: {str(e)}")

        return downloaded_file

    def wait_for_page_ready(self, timeout: int = 10, poll_interval: float = 0.3) -> bool:
        """
        Aguarda o documento atual terminar de carregar (`document.readyState
        == 'complete'`). Usado como sinal genérico de "a navegação
        terminou", útil para rotinas sem uma tela alvo conhecida com
        antecedência (ex: `GenericRoutine`).

        Args:
            timeout: tempo máximo de espera em segundos
            poll_interval: intervalo entre verificações

        Returns:
            bool: True se o documento chegou ao estado 'complete' a tempo
        """
        end_time = time.time() + timeout

        while time.time() < end_time:
            try:
                if self.driver.execute_script("return document.readyState") == "complete":
                    return True
            except Exception:
                pass
            time.sleep(poll_interval)

        return False

    def get_csv_button_name(self, default: str = "GerExecl") -> str:
        """
        Nome do botão usado para exportar/baixar o arquivo do relatório
        desta rotina — normalmente "GerExecl" (CSV), mas configurável por
        RotinaMap (`RotinaMap.csv_button_name`) para telas que desabilitam
        "GerExecl" em certos relatórios e exigem outro botão (ex: "salvar",
        rotina 01.20.12: "Permitido apenas Salvar ou Gerar CSV").

        Returns:
            str: `RotinaMap.csv_button_name` da automação atual, ou `default`
                 se não houver automação/RotinaMap ou o campo estiver vazio.
        """
        if not self.automation_id:
            return default

        from config.database import SessionLocal, Automation, RotinaMap

        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == self.automation_id).first()
            if not automation or not automation.rotina_map_id:
                return default
            rotina_map = db.query(RotinaMap).filter(RotinaMap.id == automation.rotina_map_id).first()
            return (rotina_map.csv_button_name if rotina_map and rotina_map.csv_button_name else default)
        finally:
            db.close()

    def get_report_ready_timeout(self, default: int = 30) -> int:
        """
        Segundos a esperar pelo relatório ficar pronto após clicar em
        "Visualizar" — normalmente 30s, mas configurável por RotinaMap
        (`RotinaMap.report_ready_timeout`) para telas que geram o relatório
        de forma muito mais lenta no servidor (ex: rotina 12.06.07
        "Situação dos Títulos", observado levando 5-8 minutos).

        Returns:
            int: `RotinaMap.report_ready_timeout` da automação atual, ou
                 `default` se não houver automação/RotinaMap ou o campo
                 estiver vazio.
        """
        if not self.automation_id:
            return default

        from config.database import SessionLocal, Automation, RotinaMap

        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == self.automation_id).first()
            if not automation or not automation.rotina_map_id:
                return default
            rotina_map = db.query(RotinaMap).filter(RotinaMap.id == automation.rotina_map_id).first()
            return (rotina_map.report_ready_timeout if rotina_map and rotina_map.report_ready_timeout else default)
        finally:
            db.close()

    def login_file_manager(self) -> bool:
        """
        Faz login no "Gerenciador de Arquivos" (app separado na porta 8080,
        mesmas credenciais do PromaX) — usado por rotinas que geram
        arquivos diretamente no servidor (ex: 01.31.60), sem oferecer
        download direto no navegador da tela da rotina.

        Abre uma aba nova (não perde a sessão/aba da rotina no PromaX).

        Returns:
            bool: True se o login foi bem-sucedido
        """
        from config.database import SessionLocal, Automation, Company
        from config.settings import FILE_MANAGER_URL

        db = SessionLocal()
        try:
            automation = db.query(Automation).filter(Automation.id == self.automation_id).first()
            company = db.query(Company).filter(Company.id == automation.company_id).first() if automation else None
        finally:
            db.close()

        if not company:
            self.logger.error("Não foi possível obter a empresa para logar no Gerenciador de Arquivos")
            return False

        self.driver.execute_script("window.open('about:blank', '_file_manager');")
        self.driver.switch_to.window(self.driver.window_handles[-1])

        self.driver.get(f"{FILE_MANAGER_URL}/")
        try:
            user_input = self.driver.find_element(By.ID, "username")
            pass_input = self.driver.find_element(By.ID, "password")
        except NoSuchElementException:
            self.logger.error("Campos de login do Gerenciador de Arquivos não encontrados")
            return False

        user_input.send_keys(company.username)
        pass_input.send_keys(company.get_password())
        pass_input.send_keys(Keys.ENTER)
        time.sleep(2)

        ok = "login" not in self.driver.current_url.lower() and "Gerenciador de Arquivos" in self.driver.title
        if not ok:
            self.logger.error(f"Falha ao logar no Gerenciador de Arquivos: url={self.driver.current_url}")
        return ok

    def list_file_manager_files(self, folder: str, filename_pattern: str) -> List[str]:
        """
        Lista, no Gerenciador de Arquivos (já logado via `login_file_manager`),
        os nomes de arquivo em `folder` que combinam com `filename_pattern`.

        Args:
            folder: pasta a listar (ex: "dvs")
            filename_pattern: regex do nome do arquivo (sem grupos de
                captura — usa `re.findall` sobre o HTML da listagem)

        Returns:
            list[str]: nomes de arquivo encontrados (ordenados, sem duplicatas)
        """
        from config.settings import FILE_MANAGER_URL

        self.driver.get(f"{FILE_MANAGER_URL}/arquivos/browse/{folder}")
        return sorted(set(re.findall(filename_pattern, self.driver.page_source)))

    def download_file_manager_file(self, folder: str, filename: str, timeout: int = 30) -> Optional[Path]:
        """
        Baixa um arquivo específico do Gerenciador de Arquivos.

        Args:
            folder: pasta onde o arquivo está (ex: "dvs")
            filename: nome exato do arquivo
            timeout: tempo máximo de espera pelo download, em segundos

        Returns:
            Path do arquivo baixado, ou None se o download não foi confirmado
        """
        from config.settings import FILE_MANAGER_URL, DOWNLOAD_DIR

        files_before = list_files(DOWNLOAD_DIR)
        self.driver.get(f"{FILE_MANAGER_URL}/arquivos/download/file/{folder}/{filename}")
        downloaded = wait_for_new_download(DOWNLOAD_DIR, files_before, timeout=timeout)

        if downloaded:
            self.logger.info(f"Arquivo baixado do Gerenciador de Arquivos: {downloaded}")
        else:
            self.logger.error(f"Falha ao baixar '{filename}' do Gerenciador de Arquivos")
        return downloaded

    def wait_for_element(
        self,
        locator: tuple,
        timeout: Optional[int] = None,
        message: str = None
    ):
        """
        Aguarda um elemento aparecer na página.

        Args:
            locator: Tupla (By.CSS_SELECTOR, "selector") ou (By.XPATH, "xpath")
            timeout: Timeout customizado (usa self.timeout se None)
            message: Mensagem de erro customizada

        Returns:
            WebElement: Elemento encontrado

        Raises:
            TimeoutException: Se elemento não encontrado no tempo limite
        """
        timeout = timeout or self.timeout
        try:
            element = self.wait.until(
                EC.presence_of_element_located(locator),
                message=message or f"Elemento não encontrado: {locator}"
            )
            self.logger.debug(f"Elemento encontrado: {locator}")
            return element
        except TimeoutException as e:
            self.logger.error(f"Timeout aguardando elemento: {locator}")
            raise

    def click_element(self, locator: tuple, timeout: Optional[int] = None) -> None:
        """
        Aguarda e clica em um elemento.

        Args:
            locator: Tupla com seletor
            timeout: Timeout customizado
        """
        element = self.wait_for_element(locator, timeout)
        try:
            element.click()
            self.logger.debug(f"Clicado: {locator}")
        except Exception as e:
            self.logger.error(f"Erro ao clicar em {locator}: {str(e)}")
            raise

    def send_keys(self, locator: tuple, text: str, timeout: Optional[int] = None) -> None:
        """
        Aguarda e preenche um campo de texto.

        Args:
            locator: Tupla com seletor
            text: Texto a inserir
            timeout: Timeout customizado
        """
        element = self.wait_for_element(locator, timeout)
        try:
            element.clear()
            element.send_keys(text)
            self.logger.debug(f"Texto inserido em {locator}: {text[:20]}...")
        except Exception as e:
            self.logger.error(f"Erro ao preencher {locator}: {str(e)}")
            raise

    def get_text(self, locator: tuple, timeout: Optional[int] = None) -> str:
        """
        Obtém o texto de um elemento.

        Args:
            locator: Tupla com seletor
            timeout: Timeout customizado

        Returns:
            str: Texto do elemento
        """
        element = self.wait_for_element(locator, timeout)
        return element.text

    def is_element_visible(self, locator: tuple, timeout: int = 2) -> bool:
        """
        Verifica se um elemento está visível na página.

        Args:
            locator: Tupla com seletor
            timeout: Timeout para busca rápida

        Returns:
            bool: True se elemento está visível
        """
        try:
            self.wait.until(
                EC.visibility_of_element_located(locator),
                timeout=timeout
            )
            return True
        except TimeoutException:
            return False

    def handle_alerts(self, max_retries: int = 5) -> int:
        """
        Fecha todos os alertas (alert dialogs) na página.

        Args:
            max_retries: Número máximo de alertas a fechar

        Returns:
            int: Número de alertas fechados
        """
        alerts_closed = 0
        for _ in range(max_retries):
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
                alerts_closed += 1
                self.logger.debug(f"Alert fechado ({alerts_closed})")
            except:
                break
        return alerts_closed

    def fill_configured_fields(self, automation_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Preenche os campos da tela alvo com base nos mapeamentos configurados
        na tabela `camps_map_conf` para a automação.

        Cada mapeamento guarda o HTML do campo em `select` (não um seletor
        CSS puro) — o elemento é localizado extraindo o atributo `name`
        (ou `id`, como fallback) desse HTML. Para `radio`, `name`+`value`
        juntos identificam a opção exata dentro do grupo.

        Tipos suportados: 'select', 'text', 'checkbox', 'radio',
        'botao'/'button', 'date'/'data'.

        Campos do tipo 'date'/'data' são preenchidos via JavaScript
        (`element.value = ...`), sem disparar o evento `blur` real — isso
        evita acionar `FormataCampo()` -> `VB_FormataCampo()`, função que só
        existe em VBScript e não está disponível no Chromium.

        Ordem de preenchimento: definida explicitamente pela coluna `ordem`
        de cada campo (crescente), configurável no editor de rotinas — NÃO
        é adivinhada pelo tipo do campo. Telas diferentes reagem de forma
        diferente a cada ação: um botão "Adicionar" pode resetar outros
        campos da tela ao ser clicado (deve vir ANTES desses campos), já um
        botão "Gerar Relatório" deve vir DEPOIS de todos os outros. Ajuste
        `ordem` conforme o comportamento observado na tela real.

        Se houver um campo 'select' com `gerar_lista_opcoes=True` (configurado
        no editor de rotinas), ele é IGNORADO aqui — não recebe um valor
        único, pois será preenchido repetidamente (uma vez por opção) por
        `run_multi_option_reports()`. Esse campo vem identificado na chave
        `"multi_option_campo"` do retorno.

        Args:
            automation_id: ID da automação (usa self.automation_id se None)

        Returns:
            dict: {"filled": int, "errors": int, "details": [...],
                   "multi_option_campo": CampoMapConf | None}
        """
        from config.database import DatabaseService

        automation_id = automation_id or self.automation_id
        if not automation_id:
            self.logger.warning(
                "Nenhum automation_id disponível; pulando preenchimento de campos configurados"
            )
            return {"filled": 0, "errors": 0, "details": [], "multi_option_campo": None}

        # Já retorna ordenado por (ordem, id) — ver DatabaseService.get_campos_map_conf_by_automation
        campos = DatabaseService.get_campos_map_conf_by_automation(automation_id)
        if not campos:
            self.logger.info("Nenhum campo mapeado configurado para esta automação")
            return {"filled": 0, "errors": 0, "details": [], "multi_option_campo": None}

        multi_option_campo = next(
            (c for c in campos if c.tipo == "select" and c.gerar_lista_opcoes), None
        )
        if multi_option_campo:
            self.logger.info(
                f"Campo '{multi_option_campo.nome_campo}' configurado para gerar "
                f"lista de opções (modo='{multi_option_campo.opcoes_modo}'); será "
                "preenchido/relatado por opção, não no preenchimento único."
            )

        filled = 0
        errors = 0
        details: List[Dict[str, Any]] = []
        patched_ie_collections = False

        for campo in campos:
            if campo is multi_option_campo:
                continue
            try:
                by, value_locator = self._extract_locator_from_html(campo.select)

                element = wait_for_element_across_frames(
                    self.driver, by, value_locator, timeout=5
                )
                if element is None:
                    raise Exception(f"Elemento não encontrado no frameset: ({by}, {value_locator})")

                if not patched_ie_collections:
                    # Já estamos no frame certo (wait_for_element_across_frames
                    # deixa o driver posicionado nele) — corrige de uma vez
                    # qualquer função da tela com a sintaxe document.all.NOME(N)
                    # só-do-IE antes de preencher qualquer campo 'select' cujo
                    # onchange dependa dela (ex: Carrega() de telas com
                    # "quebra1/2/3"). Só precisa rodar uma vez por tela.
                    self._patch_ie_collection_call_syntax()
                    patched_ie_collections = True

                resolved_value = campo.resolve_value()
                self._apply_field_value(element, campo.tipo, resolved_value, campo.select)

                filled += 1
                details.append({
                    "nome_campo": campo.nome_campo,
                    "status": "ok",
                    "value": resolved_value,
                })
                self.logger.info(f"Campo preenchido: {campo.nome_campo} = {resolved_value!r}")

            except Exception as e:
                errors += 1
                details.append({
                    "nome_campo": campo.nome_campo,
                    "status": "erro",
                    "error": str(e),
                })
                self.logger.error(f"Erro ao preencher campo '{campo.nome_campo}': {str(e)}")

        self.logger.info(f"Preenchimento de campos concluído: {filled} ok, {errors} erro(s)")
        return {
            "filled": filled,
            "errors": errors,
            "details": details,
            "multi_option_campo": multi_option_campo,
        }

    def _extract_locator_from_html(self, html_fragment: str) -> tuple:
        """
        Extrai um locator Selenium a partir do HTML bruto de um campo
        (armazenado em CampoMapConf.select).

        Radio buttons são um caso especial: vários <input type="radio">
        compartilham o mesmo `name` (um por grupo), diferenciados apenas
        pelo `value`. Por isso, quando o HTML é de um radio, o locator
        combina `name` + `value` (CSS) em vez de usar só o `name` — senão
        `find_elements` sempre pegaria a primeira opção do grupo.

        Args:
            html_fragment: string HTML do campo, ex: '<input name="iniDat" ...>'

        Returns:
            tuple: (By.CSS_SELECTOR, "input[name='x'][value='y']") para radio,
                   (By.NAME, "iniDat") ou (By.ID, "algumId") para os demais

        Raises:
            ValueError: se não for possível extrair name/id (e value, se radio) do HTML

        Nota: os regex exigem espaço (ou início da tag) antes do atributo,
        para não confundir `name=` com o final de atributos compostos como
        `data-name=` ou `aria-name=` (que contêm "name=" como substring).
        """
        name_match = re.search(r'(?:\s|^)name=["\']([^"\']+)["\']', html_fragment)
        is_radio = bool(re.search(r'(?:\s|^)type=["\']radio["\']', html_fragment, re.IGNORECASE))

        if is_radio and name_match:
            value_match = re.search(r'(?:\s|^)value=["\']([^"\']*)["\']', html_fragment)
            if not value_match:
                raise ValueError(f"Radio button sem atributo 'value' no HTML: {html_fragment}")
            css = f"input[name='{name_match.group(1)}'][value='{value_match.group(1)}']"
            return (By.CSS_SELECTOR, css)

        if name_match:
            return (By.NAME, name_match.group(1))

        id_match = re.search(r'(?:\s|^)id=["\']([^"\']+)["\']', html_fragment)
        if id_match:
            return (By.ID, id_match.group(1))

        raise ValueError(f"Não foi possível extrair name/id do HTML do campo: {html_fragment}")

    def _patch_ie_collection_call_syntax(self) -> int:
        """
        Corrige, em TODAS as funções globais da página/frame atual, a
        sintaxe `document.all.NOME(N)` — API só do IE para "chamar" como
        função uma coleção de elementos que compartilham o mesmo `name`
        (equivalente a indexar o N-ésimo elemento do grupo). No Chromium,
        `document.all.NOME` é uma `RadioNodeList`/`HTMLCollection` comum,
        que não é chamável — `document.all.NOME(N)` lança
        `TypeError: ... is not a function`.

        Encontrado em telas que usam múltiplas quebras/eixos (padrão
        "quebra1/2/3" com uma função `Carrega()` compartilhada) — o erro
        acontece DENTRO de um `onchange` disparado por um clique real (via
        `Select.select_by_visible_text`), então o navegador só registra o
        erro no console em vez de propagá-lo para o Selenium: o preenchimento
        do campo "funciona" sem erro visível, mas a função quebra antes de
        terminar, deixando outros campos que ela deveria configurar (ex:
        `quebra1Inicial`/`quebra1Final`) desabilitados/vazios — o que pode
        fazer o relatório final vir sem nenhum resultado, sem nenhum erro
        aparente na automação.

        Não é possível corrigir isso sobrescrevendo `document.all`
        diretamente (é uma propriedade "unforgeable" do navegador —
        atribuições são silenciosamente ignoradas). A correção reescreve o
        CÓDIGO-FONTE de cada função afetada (troca `document.all.NOME(N)`
        por `document.all.NOME[N]`, equivalente e válido no Chromium) e a
        redefine em `window`, preservando o resto da lógica original.

        Returns:
            int: quantidade de funções corrigidas (0 se nenhuma precisava)
        """
        script = r"""
            var pattern = /document\.all\.(\w+)\((\d+)\)/g;
            var fixedCount = 0;
            for (var key in window) {
                var fn;
                try { fn = window[key]; } catch (e) { continue; }
                if (typeof fn !== 'function') { continue; }
                var src;
                try { src = fn.toString(); } catch (e) { continue; }
                if (!pattern.test(src)) { continue; }
                pattern.lastIndex = 0;
                var fixedSrc = src.replace(pattern, 'document.all.$1[$2]');
                try {
                    window[key] = eval('(' + fixedSrc.replace(/^function[^(]*/, 'function') + ')');
                    fixedCount++;
                } catch (e) {
                    // Alguma função pode não ser reescrevível; ignora e segue.
                }
            }
            return fixedCount;
        """
        try:
            count = self.driver.execute_script(script) or 0
            if count:
                self.logger.info(
                    f"Corrigida sintaxe document.all(N) só-do-IE em {count} função(ões) da tela atual"
                )
            return count
        except Exception as e:
            self.logger.debug(f"Falha ao tentar corrigir sintaxe document.all(N): {str(e)}")
            return 0

    @staticmethod
    def _extract_onclick_from_html(html_fragment: str) -> Optional[str]:
        """
        Extrai o código JS do atributo `onclick` de um HTML de botão
        (ex: 'AdicionaNatureza();' de `<button onclick="AdicionaNatureza();">`).

        Returns:
            str: código JS do onclick, ou None se o atributo não existir
        """
        match = re.search(r'onclick=(["\'])(.*?)\1', html_fragment, re.DOTALL)
        return match.group(2) if match else None

    def _apply_field_value(self, element, tipo: str, value: Any, html_fragment: Optional[str] = None) -> None:
        """
        Aplica o valor resolvido no elemento, de acordo com o tipo do campo.

        Args:
            element: WebElement já localizado (no frame correto)
            tipo: 'select', 'text', 'checkbox', 'radio', 'botao'/'button', 'date'/'data'
            value: valor já resolvido por CampoMapConf.resolve_value()
            html_fragment: HTML original do campo (CampoMapConf.select) — usado
                            por 'botao'/'button' para extrair o `onclick`
        """
        if tipo in ("date", "data"):
            # Define o valor via JS para NÃO disparar o evento blur real
            # (FormataCampo -> VB_FormataCampo, que não existe em VBScript no Chromium)
            self.driver.execute_script("arguments[0].value = arguments[1];", element, value)
            return

        if tipo in ("botao", "button"):
            # Botão auxiliar da tela: não usa `value`, sempre aciona a ação.
            #
            # Preferimos executar o JS do `onclick` diretamente (via
            # execute_script) em vez de um clique real (`element.click()`):
            # alguns botões têm a função do próprio `onclick` correta, mas um
            # clique REAL não produz efeito — o evento é interceptado por
            # outro listener da página (que pode ter o mesmo tipo de bug do
            # `document.parentWindow` já visto em `click_report_button`).
            # Executar o onclick diretamente contorna esse listener, pois não
            # dispara um evento de clique de fato (sem bubbling).
            onclick_js = self._extract_onclick_from_html(html_fragment) if html_fragment else None
            if onclick_js:
                self.driver.execute_script(onclick_js)
            else:
                element.click()
            return

        if tipo in ("checkbox", "radio"):
            is_checked = element.is_selected()
            if bool(value) != is_checked:
                element.click()
                # Alguns checkboxes/radios têm onclick que recalcula outros
                # campos da tela (ex: "Lista NFs de Compra" -> AlteraData(),
                # que reajusta os campos de data). Preenchimento automático é
                # rápido o bastante para rodar antes desse efeito colateral
                # terminar — uma pequena pausa evita que o campo de data,
                # preenchido em seguida (conforme `ordem`), seja sobrescrito
                # ou fique inconsistente com o que esse onclick calculou.
                time.sleep(0.3)
            return

        tag_name = (element.tag_name or "").lower()
        if tipo == "select" or tag_name == "select":
            select_element = Select(element)
            try:
                select_element.select_by_visible_text(str(value))
            except Exception:
                select_element.select_by_value(str(value))
            return

        # 'text' e demais tipos: preenchimento normal de texto
        element.clear()
        element.send_keys(str(value))

    def take_screenshot(self, filename: str) -> None:
        """
        Captura uma screenshot da página, salva em `logs/screenshots/` (não
        na raiz do projeto — antes era salva com um caminho relativo, o que
        acumulava PNGs soltos no diretório de trabalho atual a cada execução).

        Args:
            filename: Nome do arquivo para salvar
        """
        try:
            screenshots_dir = LOGS_DIR / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            path = screenshots_dir / filename
            self.driver.save_screenshot(str(path))
            self.logger.info(f"Screenshot salva: {path}")
        except Exception as e:
            self.logger.error(f"Erro ao salvar screenshot: {str(e)}")

    def get_page_source(self) -> str:
        """Retorna o HTML da página atual."""
        return self.driver.page_source

    def log_execution_start(self) -> None:
        """Log no início da execução."""
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Iniciando {self.routine_name} ({self.routine_id})")
        self.logger.info(f"{'='*60}")

    def log_execution_end(self, result: dict) -> None:
        """Log no final da execução."""
        self.logger.info(f"Resultado: {result}")
        self.logger.info(f"{'='*60}")
