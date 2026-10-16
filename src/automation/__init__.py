"""
Módulo de automação com registro de todas as rotinas disponíveis.
"""

import logging

# Importe as rotinas aqui conforme forem criadas
from src.automation.routines.routine_14_05_05 import Routine14_05_05
from src.automation.routines.routine_generic import GenericRoutine

logger = logging.getLogger(__name__)

# Dicionário de rotinas com classe Python dedicada (lógica específica de tela)
AVAILABLE_ROUTINES = {
    "14.05.05": Routine14_05_05,
}


def get_routine_class(routine_id: str):
    """
    Obtém a classe de uma rotina pelo ID.

    Se `routine_id` não tiver uma classe Python dedicada registrada em
    `AVAILABLE_ROUTINES`, retorna `GenericRoutine` como fallback — ela
    navega via atalho e preenche os campos configurados em
    `camps_map_conf` (editor de rotinas), sem precisar de código Python
    específico para a tela.

    Args:
        routine_id: ID da rotina (ex: "14.05.05")

    Returns:
        Classe da rotina (dedicada ou GenericRoutine)
    """
    if routine_id in AVAILABLE_ROUTINES:
        return AVAILABLE_ROUTINES[routine_id]

    logger.info(
        f"Rotina '{routine_id}' não tem classe dedicada; usando GenericRoutine "
        f"(navegação via atalho + preenchimento de camps_map_conf)"
    )
    return GenericRoutine


__all__ = [
    "AVAILABLE_ROUTINES",
    "get_routine_class",
    "GenericRoutine",
]
