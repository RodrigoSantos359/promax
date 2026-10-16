"""
Helpers de espera e navegação entre frames.

O PromaX é uma aplicação clássica baseada em framesets (várias telas usam
<frameset>/<frame> em vez de <iframe> moderno). Para interagir com um campo
é preciso primeiro trocar o contexto do WebDriver para o frame correto.
"""

import logging
import time
from pathlib import Path
from typing import Optional, Set
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

logger = logging.getLogger(__name__)


def switch_to_default(driver: WebDriver) -> None:
    """Volta o contexto do driver para o documento principal (fora de qualquer frame)."""
    driver.switch_to.default_content()


def find_element_across_frames(
    driver: WebDriver,
    by: str,
    value: str,
    max_depth: int = 4,
) -> Optional[WebElement]:
    """
    Procura um elemento no documento atual e, recursivamente, dentro de
    frames/iframes aninhados (busca em largura).

    Se o elemento for encontrado dentro de um frame, o driver permanece com
    o contexto trocado para esse frame (para permitir interação imediata).
    Se não encontrar em nenhum lugar, o contexto volta para o default_content.

    Args:
        driver: WebDriver Selenium
        by: estratégia de localização (By.CSS_SELECTOR, By.XPATH, ...)
        value: seletor
        max_depth: profundidade máxima de recursão em frames aninhados

    Returns:
        WebElement encontrado, ou None se não encontrado em nenhum frame
    """
    switch_to_default(driver)
    element = _search_frame_recursive(driver, by, value, max_depth)

    if element is None:
        logger.debug(f"Elemento não encontrado em nenhum frame: ({by}, {value})")
        switch_to_default(driver)

    return element


def _search_frame_recursive(
    driver: WebDriver,
    by: str,
    value: str,
    max_depth: int,
) -> Optional[WebElement]:
    """Busca o elemento no contexto atual; se não achar, desce nos frames filhos."""
    try:
        elements = driver.find_elements(by, value)
        if elements:
            return elements[0]
    except Exception as e:
        logger.debug(f"Erro ao buscar elemento no frame atual: {str(e)}")

    if max_depth <= 0:
        return None

    frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")

    for index in range(len(frames)):
        try:
            # Re-busca os frames a cada iteração: o DOM pode ter sido re-obtido
            # após o switch_to, invalidando referências antigas (stale element).
            current_frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
            if index >= len(current_frames):
                break

            driver.switch_to.frame(current_frames[index])
            found = _search_frame_recursive(driver, by, value, max_depth - 1)
            if found is not None:
                return found

            driver.switch_to.parent_frame()
        except Exception as e:
            logger.debug(f"Erro ao entrar no frame {index}: {str(e)}")
            try:
                driver.switch_to.parent_frame()
            except Exception:
                pass

    return None


def wait_for_element_across_frames(
    driver: WebDriver,
    by: str,
    value: str,
    timeout: int = 10,
    poll_interval: float = 0.5,
    max_depth: int = 4,
) -> Optional[WebElement]:
    """
    Tenta repetidamente localizar um elemento em qualquer frame até o timeout.

    Útil quando a página ainda está carregando os frames/conteúdo dinamicamente.
    """
    import time

    end_time = time.time() + timeout

    while time.time() < end_time:
        element = find_element_across_frames(driver, by, value, max_depth)
        if element is not None:
            return element
        time.sleep(poll_interval)

    return None


def list_files(directory: Path) -> Set[str]:
    """Lista os nomes de arquivo (não diretórios) de um diretório, se ele existir."""
    if not directory.exists():
        return set()
    return {p.name for p in directory.iterdir() if p.is_file()}


def _is_bogus_download(path: Path) -> bool:
    """
    Detecta arquivos que apareceram na pasta de downloads mas NÃO são o
    relatório esperado — artefatos do próprio Chrome, não do PromaX:

    - Página HTML salva (ex: "downloads.html"/"downloads.htm") — acontece
      quando o clique no botão de exportar cai numa página de erro/aviso em
      vez do CSV real (ex: sessão expirada, relatório falhou silenciosamente),
      e o Chrome, sem um Content-Disposition claro, ainda assim "baixa" o
      HTML renderizado.
    - Dump de crash do Chromium (magic bytes "Cr24", formato Crashpad) —
      observado ocasionalmente ao rodar várias instâncias headless em
      sequência rápida.

    Sem esse filtro, `wait_for_new_download` aceitaria esses arquivos como
    se fossem o relatório baixado (são "novos" e "completos"), corrompendo
    silenciosamente o pipeline de importação.
    """
    if path.suffix.lower() in (".html", ".htm"):
        return True

    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return False

    if head.startswith(b"Cr24"):
        return True
    if head.lstrip().lower().startswith((b"<!doctype", b"<html")):
        return True

    return False


def wait_for_new_download(
    directory: Path,
    files_before: Set[str],
    timeout: int = 30,
    poll_interval: float = 0.5,
) -> Optional[Path]:
    """
    Aguarda o aparecimento de um novo arquivo completo (não `.crdownload`)
    em `directory`, comparando com o snapshot `files_before` (capturado
    antes da ação que dispara o download).

    Arquivos "bogus" (páginas HTML salvas por engano, dumps de crash do
    Chromium — veja `_is_bogus_download`) são ignorados: continuam sendo
    monitorados, mas não são aceitos como o download real, para que um
    arquivo genuíno que apareça depois ainda seja capturado dentro do
    mesmo timeout.

    Args:
        directory: pasta onde os downloads do navegador são salvos
        files_before: nomes de arquivo existentes antes do download começar
        timeout: tempo máximo de espera em segundos
        poll_interval: intervalo entre verificações

    Returns:
        Path do arquivo baixado, ou None se nenhum novo arquivo completo
        (e válido) apareceu dentro do timeout
    """
    end_time = time.time() + timeout
    warned_bogus: Set[str] = set()

    while time.time() < end_time:
        current_files = list_files(directory)
        new_files = current_files - files_before

        # Ignora arquivos parciais do Chrome (ainda baixando)
        complete_new_files = [f for f in new_files if not f.endswith((".crdownload", ".tmp"))]

        valid_new_files = []
        for name in complete_new_files:
            candidate = directory / name
            if _is_bogus_download(candidate):
                if name not in warned_bogus:
                    logger.warning(f"Ignorando arquivo bogus na pasta de downloads (não é o relatório): {candidate}")
                    warned_bogus.add(name)
                continue
            valid_new_files.append(candidate)

        if valid_new_files:
            # Se houver mais de um, pega o mais recente
            newest = max(valid_new_files, key=lambda p: p.stat().st_mtime)
            logger.info(f"Download concluído: {newest}")
            return newest

        time.sleep(poll_interval)

    logger.warning(f"Timeout aguardando novo download em {directory}")
    return None


__all__ = [
    "switch_to_default",
    "find_element_across_frames",
    "wait_for_element_across_frames",
    "list_files",
    "wait_for_new_download",
]
