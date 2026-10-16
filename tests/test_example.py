"""
Testes de exemplo para o framework de automação.

Para executar:
    pytest tests/test_example.py -v
"""

import pytest
from src.automation import AVAILABLE_ROUTINES, get_routine_class


def test_available_routines():
    """Verifica se há rotinas registradas."""
    assert len(AVAILABLE_ROUTINES) > 0, "Nenhuma rotina registrada"


def test_get_routine_class():
    """Testa obtenção de classe de rotina."""
    routine_id = "14.05.05"
    RoutineClass = get_routine_class(routine_id)
    assert RoutineClass is not None


def test_get_routine_class_not_found():
    """Testa erro ao obter rotina inexistente."""
    with pytest.raises(ValueError):
        get_routine_class("99.99.99")


def test_routine_attributes():
    """Verifica atributos obrigatórios de rotinas."""
    for routine_id, RoutineClass in AVAILABLE_ROUTINES.items():
        assert hasattr(RoutineClass, "ROUTINE_ID")
        assert hasattr(RoutineClass, "ROUTINE_NAME")
        assert hasattr(RoutineClass, "execute")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
