"""
TEMPLATE: Use este arquivo como base para criar novas rotinas.

Para criar uma nova rotina:
1. Copie este arquivo para routine_XX_XX_XX.py
2. Atualize ROUTINE_ID, ROUTINE_NAME, ROUTINE_URL
3. Implemente o método execute()
4. Registre em src/automation/__init__.py
"""

from typing import Dict, Any
from selenium.webdriver.common.by import By
from src.automation.base import BaseRoutine


class RoutineTemplate(BaseRoutine):
    """
    Rotina Template - Descrição breve do que faz.

    Responsável por:
    - Tarefa 1
    - Tarefa 2
    - Tarefa 3
    """

    ROUTINE_ID = "XX.XX.XX"
    ROUTINE_NAME = "Nome da Rotina"
    ROUTINE_URL = "/pw/cgi-bin/PPXXXXX.exe?SessionID={session}&ppopcao=7&call=XXXXXXXXX&SubSessionID={subsession}"

    def execute(self) -> Dict[str, Any]:
        """
        Executa a rotina principal.

        Returns:
            dict: Status e dados da execução
                {
                    "status": "success" | "failed",
                    "processed": 10,
                    "errors": 0,
                    "message": "Descrição do resultado"
                }
        """
        self.log_execution_start()

        try:
            # Passo 1: Navegar até a rotina
            self.navigate_to_routine()

            # Passo 2: Fechar alerts iniciais
            alerts = self.handle_alerts()
            self.logger.info(f"Alerts fechados: {alerts}")

            # Passo 3: Aguardar carregamento
            self._wait_for_page_load()

            # Passo 4: Processar dados
            result = self._process_data()

            # Log de sucesso
            self.log_execution_end(result)
            return result

        except Exception as e:
            self.logger.error(f"Erro na execução: {str(e)}")
            self.take_screenshot("error_screenshot.png")
            return {
                "status": "failed",
                "error": str(e)
            }

    def _wait_for_page_load(self, timeout: int = 10) -> None:
        """
        Aguarda o carregamento completo da página.

        Args:
            timeout: Tempo máximo de espera
        """
        # Aguardar pelo elemento principal da página
        locator = (By.CSS_SELECTOR, ".TableTop")  # Exemplo
        self.wait_for_element(locator, timeout=timeout)
        self.logger.info("Página carregada")

    def _process_data(self) -> Dict[str, Any]:
        """
        Processa os dados da rotina.

        Returns:
            dict: Resultado do processamento
        """
        processed = 0
        errors = 0

        try:
            # Exemplo: contar linhas da tabela
            table_rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            self.logger.info(f"Encontradas {len(table_rows)} linhas")

            for index, row in enumerate(table_rows):
                try:
                    # Processar cada linha
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if cells:
                        value = cells[0].text
                        self.logger.debug(f"Processando linha {index + 1}: {value}")
                        processed += 1
                except Exception as e:
                    self.logger.warning(f"Erro na linha {index + 1}: {str(e)}")
                    errors += 1

            return {
                "status": "success",
                "processed": processed,
                "errors": errors,
                "message": f"Processadas {processed} linhas com {errors} erros"
            }

        except Exception as e:
            self.logger.error(f"Erro ao processar dados: {str(e)}")
            raise

    def _example_fill_form(self) -> None:
        """
        Exemplo: Preencher formulário.

        Este é um método auxiliar para demonstrar o padrão de uso.
        """
        # Preencher campo de texto
        username_locator = (By.CSS_SELECTOR, "input[name='username']")
        self.send_keys(username_locator, "seu_usuario")

        # Preencher senha
        password_locator = (By.CSS_SELECTOR, "input[name='password']")
        self.send_keys(password_locator, "sua_senha")

        # Clicar botão
        submit_locator = (By.CSS_SELECTOR, "input[type='submit']")
        self.click_element(submit_locator)

        # Aguardar resultado
        result_locator = (By.CSS_SELECTOR, ".success-message")
        result = self.wait_for_element(result_locator)
        message = result.text
        self.logger.info(f"Resultado: {message}")

    def _example_extract_table_data(self) -> list:
        """
        Exemplo: Extrair dados de tabela.

        Returns:
            list: Lista de dicionários com dados das linhas
        """
        data = []

        # Aguardar tabela carregar
        table_locator = (By.CSS_SELECTOR, "table.data-table")
        self.wait_for_element(table_locator)

        # Extrair dados
        rows = self.driver.find_elements(By.CSS_SELECTOR, "table.data-table tbody tr")

        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 3:
                record = {
                    "col1": cells[0].text,
                    "col2": cells[1].text,
                    "col3": cells[2].text,
                }
                data.append(record)
                self.logger.debug(f"Linha extraída: {record}")

        self.logger.info(f"Total de linhas extraídas: {len(data)}")
        return data
