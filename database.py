"""
Lightweight JSON settings manager and in-memory stubs for Bulk Business Search & Export Pro.
SQLite database and search histories have been completely removed.
"""

import os
import json
from pathlib import Path
from logger import logger

import sys

# Directories
if getattr(sys, 'frozen', False):
    WORKSPACE_DIR = Path(sys.executable).parent
else:
    WORKSPACE_DIR = Path(__file__).parent.resolve()

DATA_DIR = WORKSPACE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

def _load_settings_file() -> dict:
    """Helper to read settings from JSON file."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read settings JSON: {e}")
    return {}

def _save_settings_file(settings_dict: dict):
    """Helper to write settings to JSON file."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings_dict, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save settings JSON: {e}")

# --- Settings Persistence ---
def save_setting(key: str, value: str):
    """Saves or updates a setting value."""
    data = _load_settings_file()
    data[key] = str(value)
    _save_settings_file(data)

def get_setting(key: str, default: str = None) -> str:
    """Gets a setting value. Returns default if key is not found."""
    data = _load_settings_file()
    return data.get(key, default)

# --- Stubs for Database Removal Compatibility ---
def initialize_database():
    """No-op since SQLite database has been removed."""
    logger.info("In-memory engine initialized (no local SQLite database is created).")

def save_business(biz_data: dict):
    """Stub function. In-memory data is managed inside the GUI."""
    pass

def get_cached_business(place_id: str) -> dict:
    """Stub function. Caching on disk is disabled."""
    return None

def get_all_businesses() -> list:
    """Stub function. Returns empty list."""
    return []

def clear_all_businesses():
    """Stub function."""
    pass

def log_api_call(api_name: str, request_url: str, response_status: str):
    """Logs API transactions directly to app.log instead of database."""
    logger.debug(f"[API Call Log] Type: {api_name} | URL: {request_url} | Status: {response_status}")

def clear_api_logs():
    """Stub function."""
    pass

def get_api_calls_count() -> int:
    """Stub function."""
    return 0

def get_dashboard_stats() -> dict:
    """Stub function. GUI calculates stats from in-memory records directly."""
    return {
        "total_businesses": 0,
        "avg_rating": 0.0,
        "businesses_with_websites": 0,
        "businesses_with_phone": 0,
        "api_calls_today": 0,
        "api_calls_total": 0,
        "top_rated_count": 0
    }
