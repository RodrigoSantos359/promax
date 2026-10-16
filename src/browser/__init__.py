"""Browser automation module."""

from src.browser.driver import DriverManager
from src.browser.waits import (
    switch_to_default,
    find_element_across_frames,
    wait_for_element_across_frames,
    list_files,
    wait_for_new_download,
)

__all__ = [
    "DriverManager",
    "switch_to_default",
    "find_element_across_frames",
    "wait_for_element_across_frames",
    "list_files",
    "wait_for_new_download",
]
