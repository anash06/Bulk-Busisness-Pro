"""
Settings manager for Bulk Business Search & Export Pro.
Reads and writes settings from/to the SQLite database with default fallbacks.
"""

import os
from pathlib import Path
from database import get_setting, save_setting
from config import DEFAULT_THEME, DEFAULT_COLOR_THEME, DEFAULT_LANGUAGE, DEFAULT_SEARCH_RADIUS, DEFAULT_REQUEST_DELAY, DEFAULT_HEADLESS

class AppSettings:
    @staticmethod
    def get_api_key() -> str:
        """Retrieves the Google Places API Key."""
        return get_setting("api_key", "")

    @staticmethod
    def set_api_key(api_key: str):
        """Saves the Google Places API Key."""
        save_setting("api_key", api_key.strip())

    @staticmethod
    def get_export_folder() -> str:
        """Retrieves the default folder path for exporting search files."""
        downloads_path = str(Path(os.path.expanduser("~")) / "Downloads")
        return get_setting("export_folder", downloads_path)

    @staticmethod
    def set_export_folder(path: str):
        """Saves the default export folder path."""
        save_setting("export_folder", path.strip())

    @staticmethod
    def get_search_radius() -> int:
        """Retrieves default grid circle search radius in meters."""
        try:
            return int(get_setting("search_radius", str(DEFAULT_SEARCH_RADIUS)))
        except ValueError:
            return DEFAULT_SEARCH_RADIUS

    @staticmethod
    def set_search_radius(radius: int):
        """Saves default search radius."""
        save_setting("search_radius", str(radius))

    @staticmethod
    def get_request_delay() -> float:
        """Retrieves request delay in seconds to limit rate limits."""
        try:
            return float(get_setting("request_delay", str(DEFAULT_REQUEST_DELAY)))
        except ValueError:
            return DEFAULT_REQUEST_DELAY

    @staticmethod
    def set_request_delay(delay: float):
        """Saves request delay."""
        save_setting("request_delay", str(delay))

    @staticmethod
    def get_theme() -> str:
        """Retrieves UI light/dark theme preference (System, Light, Dark)."""
        return get_setting("theme", DEFAULT_THEME)

    @staticmethod
    def set_theme(theme: str):
        """Saves theme preference."""
        save_setting("theme", theme)

    @staticmethod
    def get_color_theme() -> str:
        """Retrieves UI color theme (blue, green, dark-blue)."""
        return get_setting("color_theme", DEFAULT_COLOR_THEME)

    @staticmethod
    def set_color_theme(color_theme: str):
        """Saves color theme preference."""
        save_setting("color_theme", color_theme)

    @staticmethod
    def get_language() -> str:
        """Retrieves interface language."""
        return get_setting("language", DEFAULT_LANGUAGE)

    @staticmethod
    def set_language(lang: str):
        """Saves interface language."""
        save_setting("language", lang)

    @staticmethod
    def get_headless() -> bool:
        """Retrieves whether the browser scraper should run in headless mode (True) or show window (False)."""
        val = get_setting("headless", str(DEFAULT_HEADLESS))
        return val.lower() == "true"

    @staticmethod
    def set_headless(headless: bool):
        """Saves browser headless preference."""
        save_setting("headless", str(headless))
