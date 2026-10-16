"""
Handler de login para PromaX.
Automação do processo de login na plataforma PromaX Cloud.

O PromaX é uma aplicação clássica baseada em framesets: a tela de login
carregada em PROMAX_URL é, na verdade, um <frameset> com um <frame name="top">
que carrega o formulário real (tabela com class="TableTop"). Por isso toda
busca de elemento aqui usa `find_element_across_frames`, que localiza o
elemento em qualquer frame/iframe aninhado e troca o contexto do driver
automaticamente para onde ele foi encontrado.
"""

import logging
import time
from typing import Optional, Dict, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from src.browser.waits import (
    switch_to_default,
    find_element_across_frames,
    wait_for_element_across_frames,
)
from config.settings import (
    PROMAX_URL,
    PROMAX_DEFAULT_USER,
    PROMAX_DEFAULT_PASSWORD,
    SELENIUM_WAIT_TIMEOUT,
    SELECTORS,
)


class PromaXLogin:
    """
    Gerencia o login no PromaX Cloud.

    Exemplo:
        login = PromaXLogin(driver, username="filipe", password="senha123", unit="161.0001 - Dibrasa")
        login.login()
    """

    def __init__(
        self,
        driver: WebDriver,
        username: Optional[str] = None,
        password: Optional[str] = None,
        unit: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        timeout: int = SELENIUM_WAIT_TIMEOUT,
    ):
        """
        Args:
            driver: WebDriver Selenium
            username: Usuário (usa padrão se None)
            password: Senha (usa padrão se None)
            unit: Unidade PromaX (ex: "161.0001 - Dibrasa")
            logger: Logger
            timeout: Timeout para esperas
        """
        self.driver = driver
        self.username = username or PROMAX_DEFAULT_USER
        self.password = password or PROMAX_DEFAULT_PASSWORD
        self.unit = unit
        self.logger = logger or logging.getLogger(__name__)
        self.timeout = timeout
        self.wait = WebDriverWait(driver, timeout)
        self._last_failure_alert: Optional[str] = None

    # Textos de alert() que indicam rejeição do login pelo PromaX — se
    # algum desses aparecer, o form foi submetido mas a sessão NÃO foi
    # aberta (ex: "Senha Expirada. Altere sua senha para prosseguir.").
    # `_handle_alerts()` fechava qualquer alert sem olhar o conteúdo, então
    # esses casos silenciosamente viravam um falso "login com sucesso" —
    # só se descobria depois, numa rotina qualquer, com "Campo de atalho
    # não encontrado" (sintoma genérico, nada a ver com a causa real).
    LOGIN_FAILURE_ALERT_SNIPPETS = (
        "senha expirada",
        "usuário ou senha inválido",
        "usuario ou senha invalido",
        "usuário inválido",
        "usuario invalido",
        "senha inválida",
        "senha invalida",
        "conta bloqueada",
        "usuário bloqueado",
        "usuario bloqueado",
    )

    def login(self) -> Dict[str, Any]:
        """
        Realiza o login completo no PromaX: credenciais -> alerts -> unidade -> confirmação.

        Returns:
            dict: {"status": "success" | "failed", "message"/"error": "..."}
        """
        try:
            self.logger.info("Iniciando processo de login")

            self._navigate_to_login()
            self._fill_login_form()
            self._submit_login_form()
            self._handle_alerts()

            if self.unit:
                self._select_unit()
                self._handle_alerts()

            self._confirm_login()
            self._handle_alerts()

            if not self.is_logged_in():
                reason = self._last_failure_alert or (
                    "campo de atalho não encontrado após o fluxo de login "
                    "(credenciais podem ter sido rejeitadas sem um alert reconhecido)"
                )
                self.logger.error(f"Login não confirmado: {reason}")
                return {"status": "failed", "error": reason}

            self.logger.info("Login realizado com sucesso")
            return {
                "status": "success",
                "message": "Login realizado com sucesso",
            }

        except TimeoutException as e:
            self.logger.error(f"Timeout no login: {str(e)}")
            return {"status": "failed", "error": "Timeout ao fazer login"}
        except Exception as e:
            self.logger.error(f"Erro no login: {str(e)}")
            return {"status": "failed", "error": str(e)}

    def _navigate_to_login(self) -> None:
        """Navega até a página de login."""
        login_url = PROMAX_URL.rstrip("/")
        self.logger.debug(f"Navegando para: {login_url}")
        self.driver.get(login_url)

    def _fill_login_form(self) -> None:
        """Preenche usuário e senha no formulário de login (dentro de .TableTop)."""
        username_input = wait_for_element_across_frames(
            self.driver,
            By.CSS_SELECTOR,
            SELECTORS["username_input"],
            timeout=self.timeout,
        )
        if username_input is None:
            raise Exception("Campo de usuário não encontrado (nenhum frame)")

        username_input.clear()
        username_input.send_keys(self.username)
        self.logger.debug(f"Usuário preenchido: {self.username}")

        # O campo de senha fica no mesmo frame que o de usuário
        password_input = self.driver.find_element(By.CSS_SELECTOR, SELECTORS["password_input"])
        password_input.clear()
        password_input.send_keys(self.password)
        self.logger.debug("Senha preenchida")

    def _submit_login_form(self) -> None:
        """Clica no botão de confirmar login (input[name='cmdConfirma'])."""
        # O driver já está no frame do formulário após _fill_login_form
        submit_button = self.driver.find_element(By.CSS_SELECTOR, SELECTORS["login_button"])
        submit_button.click()
        self.logger.debug("Formulário de login submetido")

    def _handle_alerts(self, max_retries: int = 10, wait_between: float = 0.3) -> int:
        """
        Fecha todos os window.alert() que aparecerem na tela, um a um.

        O PromaX costuma abrir vários alerts em sequência após o login;
        cada `alert.accept()` pode revelar o próximo, por isso o loop com
        pequena espera entre tentativas.
        """
        alerts_closed = 0
        for _ in range(max_retries):
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text
                self.logger.debug(f"Fechando alert: {alert_text}")
                if any(snippet in alert_text.lower() for snippet in self.LOGIN_FAILURE_ALERT_SNIPPETS):
                    self._last_failure_alert = alert_text
                    self.logger.warning(f"Alert indica falha de login: {alert_text!r}")
                alert.accept()
                alerts_closed += 1
                time.sleep(wait_between)
            except Exception:
                break

        if alerts_closed:
            self.logger.info(f"Alerts fechados: {alerts_closed}")

        return alerts_closed

    def _select_unit(self) -> None:
        """
        Seleciona a Unidade PromaX, se uma tela/seletor de unidade aparecer.

        Melhor esforço: a tela de seleção de unidade não pôde ser inspecionada
        antecipadamente, então tentamos primeiro um <select>, depois um link/
        elemento clicável contendo o texto da unidade. Falhas aqui são
        logadas como aviso e não interrompem o login (algumas contas podem
        não ter etapa de seleção de unidade).
        """
        switch_to_default(self.driver)

        select_element = wait_for_element_across_frames(
            self.driver,
            By.CSS_SELECTOR,
            SELECTORS.get("unit_selector", "select"),
            timeout=3,
        )

        if select_element is not None:
            try:
                options = select_element.find_elements(By.TAG_NAME, "option")
                for option in options:
                    if self.unit in option.text:
                        option.click()
                        self.logger.info(f"Unidade selecionada via <select>: {self.unit}")
                        return
                self.logger.warning(f"Unidade '{self.unit}' não encontrada nas opções do select")
            except Exception as e:
                self.logger.warning(f"Erro ao selecionar unidade via <select>: {str(e)}")

        # Fallback: procurar um elemento clicável (link/div/td) com o texto da unidade
        switch_to_default(self.driver)
        xpath = SELECTORS.get("unit_link_xpath", "//*[contains(text(), '{unit}')]").format(unit=self.unit)
        unit_link = wait_for_element_across_frames(self.driver, By.XPATH, xpath, timeout=3)

        if unit_link is not None:
            unit_link.click()
            self.logger.info(f"Unidade selecionada via clique: {self.unit}")
            return

        self.logger.warning(
            f"Nenhum elemento de seleção de unidade encontrado para '{self.unit}' "
            "(pode não haver etapa de seleção de unidade para esta conta)"
        )

    def _confirm_login(self) -> None:
        """Clica em um botão de confirmação, se houver (ex: após escolher a unidade)."""
        switch_to_default(self.driver)
        confirm_button = wait_for_element_across_frames(
            self.driver,
            By.CSS_SELECTOR,
            SELECTORS.get("confirm_button", "input[type='submit']"),
            timeout=3,
        )

        if confirm_button is not None:
            try:
                confirm_button.click()
                self.logger.debug("Botão de confirmação clicado")
            except Exception as e:
                self.logger.warning(f"Erro ao clicar em confirmar: {str(e)}")
        else:
            self.logger.debug("Nenhum botão de confirmação adicional encontrado")

    def is_logged_in(self) -> bool:
        """Verifica se o usuário está logado (procura o campo de atalho em qualquer frame)."""
        switch_to_default(self.driver)
        element = find_element_across_frames(
            self.driver,
            By.CSS_SELECTOR,
            SELECTORS.get("shortcut_input", "input[name='atalho']"),
        )
        logged_in = element is not None
        self.logger.debug(f"Usuário {'está' if logged_in else 'não está'} logado")
        switch_to_default(self.driver)
        return logged_in

    def logout(self) -> bool:
        """Faz logout do PromaX, se um link/botão de saída for encontrado."""
        switch_to_default(self.driver)
        logout_element = find_element_across_frames(
            self.driver,
            By.XPATH,
            "//*[contains(text(), 'Sair') or contains(text(), 'Logout')]",
        )

        if logout_element is not None:
            logout_element.click()
            self.logger.info("Logout realizado")
            return True

        self.logger.warning("Botão de logout não encontrado")
        return False


__all__ = ["PromaXLogin"]
