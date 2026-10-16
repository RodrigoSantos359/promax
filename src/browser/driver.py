"""
Gerenciador do WebDriver Selenium.
Fornece factory method para criar instâncias do navegador (Chrome ou Edge).

Suporte a "edge_ie": algumas telas do PromaX usam VBScript (ex:
telas/*/funcoes.vbs.download), que só funciona em Internet Explorer ou no
modo de Compatibilidade com IE do Microsoft Edge ("IE mode"). Nesse modo, o
Selenium usa o driver do IE (IEDriverServer) com a opção
`attach_to_edge_chrome`, que instrui o IEDriverServer a abrir o Edge
Chromium renderizando a página com o motor do IE.
"""

import logging
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.ie.service import Service as IeService
from selenium.webdriver.ie.options import Options as IeOptions

from config.settings import (
    BROWSER,
    CHROMEDRIVER_PATH,
    IEDRIVER_PATH,
    EDGE_EXECUTABLE_PATH,
    HEADLESS,
    WINDOW_SIZE,
    USER_AGENT,
    DOWNLOAD_DIR,
)


logger = logging.getLogger(__name__)


class DriverManager:
    """Gerencia criação e limpeza do WebDriver (Chrome ou Edge em modo IE)."""

    @staticmethod
    def create_driver(
        browser: Optional[str] = None,
        headless: Optional[bool] = None,
        window_size: Optional[str] = None,
        driver_path: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """
        Cria uma instância do WebDriver, de acordo com `browser` (ou a
        variável de ambiente BROWSER, se não informado).

        Args:
            browser: "chrome" ou "edge_ie" (usa settings.BROWSER se None)
            headless: Se True, executa em modo headless (ignorado para edge_ie,
                       que não suporta headless)
            window_size: Tamanho da janela "LARGURA,ALTURA"
            driver_path: Caminho customizado para o driver (chromedriver ou IEDriverServer)
            user_agent: User-Agent customizado (ex: settings.IE7_USER_AGENT).
                        Só troca o cabeçalho HTTP enviado — o motor de renderização
                        continua sendo o Chromium (V8/Blink), não o Trident do IE.
                        Útil apenas se a tela faz sniffing de UA sem depender de
                        VBScript/ActiveX de fato.

        Returns:
            WebDriver: Instância do Chrome ou Edge (via IEDriverServer)

        Exemplo:
            driver = DriverManager.create_driver(headless=False)
            driver.get("https://example.com")
            driver.quit()
        """
        browser = (browser or BROWSER).lower()
        window_size = window_size or WINDOW_SIZE
        user_agent = user_agent or USER_AGENT

        if browser == "edge_ie":
            driver = DriverManager._create_edge_ie_driver(driver_path)
        else:
            driver = DriverManager._create_chrome_driver(headless, window_size, driver_path, user_agent)

            # Em modo headless, o Chrome bloqueia downloads por padrão a menos
            # que isso seja habilitado explicitamente via CDP.
            try:
                driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                    "behavior": "allow",
                    "downloadPath": str(DOWNLOAD_DIR.resolve()),
                })
            except Exception as e:
                logger.debug(f"Não foi possível configurar downloadBehavior via CDP: {str(e)}")

        # Define o tamanho da janela de forma independente do navegador
        # (IE/Edge IE mode não aceita --window-size como argumento de linha de comando)
        try:
            width, height = (int(v) for v in window_size.split(","))
            driver.set_window_size(width, height)
        except Exception as e:
            logger.debug(f"Não foi possível definir o tamanho da janela: {str(e)}")

        logger.info(f"WebDriver criado com sucesso (browser={browser})")
        return driver

    @staticmethod
    def _create_chrome_driver(
        headless: Optional[bool],
        window_size: str,
        driver_path: Optional[str],
        user_agent: Optional[str] = None,
    ) -> webdriver.Chrome:
        """Cria uma instância do Chrome WebDriver."""
        headless = headless if headless is not None else HEADLESS
        driver_path = driver_path or CHROMEDRIVER_PATH

        logger.info(
            f"Criando WebDriver Chrome (headless={headless}, size={window_size}, "
            f"user_agent={'customizado' if user_agent else 'padrão'})"
        )

        options = ChromeOptions()

        if headless:
            options.add_argument("--headless")
            logger.debug("Modo headless ativado")

        options.add_argument(f"--window-size={window_size}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--lang=pt-BR")

        # Evita que o próprio Chrome baixe, em segundo plano, componentes
        # internos (ex: modelo on-device do "Optimization Guide", pacotes
        # CRX3 - magic bytes "Cr24") para dentro de DOWNLOAD_DIR: como
        # download.default_directory é aplicado globalmente, esses downloads
        # internos do navegador (não relacionados a nenhum relatório)
        # apareciam na pasta e eram confundidos com o CSV real (ex:
        # "downloads.html", ~30MB), fazendo `wait_for_new_download` "vencer
        # a corrida" com um arquivo errado antes do CSV verdadeiro chegar.
        options.add_argument("--disable-component-update")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-features=OptimizationGuideModelDownloading,OptimizationHints,OptimizationHintsFetching,Translate")

        # Habilita captura de logs do console via driver.get_log("browser") — útil
        # para diagnosticar erros de script (ex: VBScript não suportado pelo Chromium)
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

        # Downloads (ex: CSV/PDF de relatórios) vão direto para DOWNLOAD_DIR,
        # sem diálogo de "Salvar como"
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        options.add_experimental_option("prefs", {
            "download.default_directory": str(DOWNLOAD_DIR.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        })

        if user_agent:
            options.add_argument(f"--user-agent={user_agent}")
            logger.debug(f"User-Agent customizado: {user_agent}")

        if driver_path:
            logger.debug(f"Usando ChromeDriver em: {driver_path}")
            service = ChromeService(driver_path)
            return webdriver.Chrome(service=service, options=options)

        logger.debug("Usando Selenium Manager para resolver o ChromeDriver")
        return webdriver.Chrome(options=options)

    @staticmethod
    def _create_edge_ie_driver(driver_path: Optional[str]) -> webdriver.Ie:
        """
        Cria uma instância do Edge em modo de Compatibilidade com Internet
        Explorer, via IEDriverServer + `attach_to_edge_chrome`.

        Requer:
            - IEDriverServer.exe (informe o caminho em IEDRIVER_PATH no .env,
              ou deixe o Selenium Manager tentar resolver automaticamente)
            - msedge.exe instalado (caminho em EDGE_EXECUTABLE_PATH no .env)
            - "Internet Explorer mode" habilitado no Edge
              (edge://settings/defaultbrowser -> "Permitir que sites sejam
              recarregados no modo Internet Explorer")
        """
        driver_path = driver_path or IEDRIVER_PATH

        logger.info(f"Criando WebDriver Edge em modo IE (edge_executable_path={EDGE_EXECUTABLE_PATH})")

        options = IeOptions()
        options.attach_to_edge_chrome = True
        options.edge_executable_path = EDGE_EXECUTABLE_PATH

        # Evita bloqueios comuns do IE relacionados a "Protected Mode" e
        # zonas de segurança diferentes entre as zonas do navegador.
        options.ignore_protected_mode_settings = True
        options.ignore_zoom_level = True
        options.native_events = True

        if driver_path:
            logger.debug(f"Usando IEDriverServer em: {driver_path}")
            service = IeService(driver_path)
            return webdriver.Ie(service=service, options=options)

        logger.debug("Usando Selenium Manager para resolver o IEDriverServer")
        return webdriver.Ie(options=options)

    @staticmethod
    def quit_driver(driver) -> None:
        """
        Fecha o WebDriver e libera recursos.

        Args:
            driver: Instância do WebDriver a fechar
        """
        if driver:
            try:
                driver.quit()
                logger.info("WebDriver fechado com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao fechar WebDriver: {str(e)}")

    @staticmethod
    def create_context_driver(browser: str = None, headless: bool = None):
        """
        Context manager para uso com 'with' statement.

        Exemplo:
            with DriverManager.create_context_driver() as driver:
                driver.get("https://example.com")
                # Driver é fechado automaticamente
        """
        from contextlib import contextmanager

        @contextmanager
        def _driver_context():
            driver = DriverManager.create_driver(browser=browser, headless=headless)
            try:
                yield driver
            finally:
                DriverManager.quit_driver(driver)

        return _driver_context()


__all__ = ["DriverManager"]
