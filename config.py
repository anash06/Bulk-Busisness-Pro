"""
Configuration settings and constants for Bulk Business Search & Export Pro.
"""

import os
from pathlib import Path

# App Information
APP_NAME = "Bulk Business Search & Export Pro"
APP_VERSION = "1.0.0"

import sys

# Directories
if getattr(sys, 'frozen', False):
    WORKSPACE_DIR = Path(sys.executable).parent
else:
    WORKSPACE_DIR = Path(__file__).parent.resolve()

DB_DIR = WORKSPACE_DIR / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "app_database.db"

# Logs
LOG_DIR = WORKSPACE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "app.log"

# Default Preferences
DEFAULT_THEME = "System"  # System, Light, Dark
DEFAULT_COLOR_THEME = "blue"  # blue, green, dark-blue
DEFAULT_LANGUAGE = "English"
DEFAULT_EXPORT_FORMAT = "Excel"
DEFAULT_SEARCH_RADIUS = 2000  # meters
DEFAULT_GRID_OVERLAP = 1.414  # spacing factor (sqrt(2)) for minimal circle grid gaps
DEFAULT_REQUEST_DELAY = 0.5  # seconds between API requests
DEFAULT_CACHE_TTL_DAYS = 30  # SQLite Cache TTL for Place Details
DEFAULT_HEADLESS = True  # Playwright browser running headless by default

# Google API endpoints
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
GOOGLE_PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# UI Colors & Fonts
SIDEBAR_WIDTH = 220
WINDOW_MIN_WIDTH = 360
WINDOW_MIN_HEIGHT = 500

# Web Server Preferences
DEFAULT_WEB_HOST = "0.0.0.0"
DEFAULT_WEB_PORT = 5000

# Common Business Categories/Types for reference
PLACE_TYPES = [
    "accounting", "airport", "amusement_park", "aquarium", "art_gallery", "atm", "bakery", "bank", "bar",
    "beauty_salon", "bicycle_store", "book_store", "bowling_alley", "bus_station", "cafe", "campground",
    "car_dealer", "car_rental", "car_repair", "car_wash", "casino", "cemetery", "church", "city_hall",
    "clothing_store", "convenience_store", "courthouse", "dentist", "department_store", "doctor",
    "drugstore", "electrician", "electronics_store", "embassy", "fire_station", "florist", "funeral_home",
    "furniture_store", "gas_station", "gym", "hair_care", "hardware_store", "hindu_template",
    "home_goods_store", "hospital", "insurance_agency", "jewelry_store", "laundry", "lawyer", "library",
    "light_rail_station", "liquor_store", "local_government_office", "locksmith", "lodging", "meal_delivery",
    "meal_takeaway", "mosque", "movie_rental", "movie_theater", "moving_company", "museum", "night_club",
    "painter", "park", "parking", "pet_store", "pharmacy", "physiotherapist", "plumber", "police",
    "post_office", "primary_school", "real_estate_agency", "restaurant", "roofing_contractor", "rv_park",
    "school", "secondary_school", "shoe_store", "shopping_mall", "spa", "stadium", "storage", "store",
    "subway_station", "supermarket", "synagogue", "taxi_stand", "tourist_attraction", "train_station",
    "transit_station", "travel_agency", "university", "veterinary_care", "zoo"
]
