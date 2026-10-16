"""PromaX Automation - Source code module."""

__version__ = "1.0.0"
__author__ = "Rodrigo"

from src.browser import DriverManager
from src.automation import AVAILABLE_ROUTINES, get_routine_class

__all__ = [
    "DriverManager",
    "AVAILABLE_ROUTINES",
    "get_routine_class",
]
