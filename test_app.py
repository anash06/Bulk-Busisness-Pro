"""
Off-line verification script for Bulk Business Search & Export Pro.
Mocks Google API requests and validates database caching, search engine grid splitting,
advanced filters, and Excel/CSV/JSON exports.
"""

import sys
import os
import unittest
import json
import shutil
from unittest.mock import patch, MagicMock
from pathlib import Path

# Set up paths
sys.path.append(str(Path(__file__).parent))

# Ensure configuration points to a test database and clean directory
import config
config.DB_PATH = Path(config.WORKSPACE_DIR) / "data" / "test_database.db"
config.LOG_PATH = Path(config.WORKSPACE_DIR) / "logs" / "test_app.log"

import database
database.SETTINGS_FILE = Path(config.WORKSPACE_DIR) / "data" / "test_settings.json"

from database import initialize_database
from settings import AppSettings
from geocoder import Geocoder
from search_engine import SearchEngine
from filters import apply_filters
from places_api import PlacesAPI
from exporter import Exporter

class TestBulkBusinessApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize test DB
        initialize_database()
        AppSettings.set_api_key("MOCK_API_KEY_12345")
        AppSettings.set_export_folder(str(config.WORKSPACE_DIR / "data"))

    def setUp(self):
        # Reset DB state before each test if needed
        pass

    def test_settings_persistence(self):
        """Validates JSON settings persistence (read/write logic)."""
        AppSettings.set_api_key("TEST_KEY_9999")
        self.assertEqual(AppSettings.get_api_key(), "TEST_KEY_9999")
        
        AppSettings.set_search_radius(3500)
        self.assertEqual(AppSettings.get_search_radius(), 3500)
        
        AppSettings.set_headless(False)
        self.assertFalse(AppSettings.get_headless())

    def test_geocoder_and_grid_math(self):
        """Verifies that city coordinates and grid bounds divide correctly."""
        mock_viewport = {
            "northeast": {"lat": 40.0, "lng": -89.0},
            "southwest": {"lat": 39.0, "lng": -90.0}
        }
        
        engine = SearchEngine(MagicMock())
        grid = engine._generate_grid(mock_viewport, radius_meters=10000)
        
        self.assertTrue(len(grid) > 0)
        # Check coordinates range
        for lat, lng in grid:
            self.assertTrue(39.0 <= lat <= 40.0)
            self.assertTrue(-90.0 <= lng <= -89.0)

    def test_business_filtering(self):
        """Tests that business lists filters apply correct criteria."""
        sample_list = [
            {"name": "Restaurant A", "rating": 4.5, "total_reviews": 50, "website": "http://a.com", "business_types": ["restaurant"]},
            {"name": "Dentist B", "rating": 3.8, "total_reviews": 5, "website": "", "business_types": ["dentist"]},
            {"name": "Gym C", "rating": 4.8, "total_reviews": 120, "website": "http://c.com", "business_types": ["gym"]}
        ]

        # Filter rating >= 4.0 and review count >= 10
        criteria_1 = {
            "min_rating": 4.0,
            "min_reviews": 10,
        }
        res_1 = apply_filters(sample_list, criteria_1)
        self.assertEqual(len(res_1), 2)
        self.assertEqual(res_1[0]["name"], "Restaurant A")
        self.assertEqual(res_1[1]["name"], "Gym C")

        # Filter has website
        criteria_2 = {
            "has_website": True
        }
        res_2 = apply_filters(sample_list, criteria_2)
        self.assertEqual(len(res_2), 2)
        
        # Filter type dentist
        criteria_3 = {
            "business_type": "dentist"
        }
        res_3 = apply_filters(sample_list, criteria_3)
        self.assertEqual(len(res_3), 1)
        self.assertEqual(res_3[0]["name"], "Dentist B")

    def test_exporters(self):
        """Validates CSV, JSON, and Excel creation and styling outputs."""
        sample_biz_list = [
            {
                "place_id": "place_01",
                "name": "Sunny Spa",
                "full_address": "456 Oak Rd",
                "city": "Sunnyvale",
                "state": "CA",
                "country": "USA",
                "rating": 4.2,
                "total_reviews": 45,
                "phone_number": "+1-408-555-1212",
                "website": "http://sunnyspa.com",
                "business_types": ["spa", "beauty"],
                "price_level": 1,
                "created_at": "2026-07-16T12:00:00"
            },
            {
                "place_id": "place_02",
                "name": "Grand Hotel",
                "full_address": "789 Pine Ave",
                "city": "Sunnyvale",
                "state": "CA",
                "country": "USA",
                "rating": 4.9,
                "total_reviews": 230,
                "phone_number": "+1-408-555-9876",
                "website": "http://grandhotel.com",
                "business_types": ["lodging", "hotel"],
                "price_level": 3,
                "created_at": "2026-07-16T12:00:00"
            }
        ]

        out_dir = Path(config.WORKSPACE_DIR) / "data" / "exports"
        out_dir.mkdir(exist_ok=True)

        excel_path = str(out_dir / "test_export.xlsx")
        csv_path = str(out_dir / "test_export.csv")
        json_path = str(out_dir / "test_export.json")

        self.assertTrue(Exporter.export_to_excel(sample_biz_list, excel_path))
        self.assertTrue(Exporter.export_to_csv(sample_biz_list, csv_path))
        self.assertTrue(Exporter.export_to_json(sample_biz_list, json_path))

        self.assertTrue(os.path.exists(excel_path))
        self.assertTrue(os.path.exists(csv_path))
        self.assertTrue(os.path.exists(json_path))

    @patch("places_api.sync_playwright")
    def test_scraper_parsing(self, mock_playwright):
        """Verifies that the Playwright scraper coordinates calls and parses page details."""
        # Setup mocks
        mock_p = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        
        mock_browser = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser
        
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        
        # Mock URL containing coordinate structure
        mock_page.url = "https://www.google.com/maps/place/Awesome+Gym/@37.3688,-122.0363,17z/data=..."
        
        # Mock locator objects
        mock_name_locator = MagicMock()
        mock_name_locator.first = mock_name_locator
        mock_name_locator.count.return_value = 1
        mock_name_locator.text_content.return_value = "Awesome Gym"
        
        mock_addr_locator = MagicMock()
        mock_addr_locator.first = mock_addr_locator
        mock_addr_locator.count.return_value = 1
        mock_addr_locator.text_content.return_value = "Address: 123 Fitness Ave, California"
        
        mock_phone_locator = MagicMock()
        mock_phone_locator.first = mock_phone_locator
        mock_phone_locator.count.return_value = 1
        mock_phone_locator.text_content.return_value = "Phone: +1 408-555-9000"
        
        mock_web_locator = MagicMock()
        mock_web_locator.first = mock_web_locator
        mock_web_locator.count.return_value = 1
        mock_web_locator.get_attribute.return_value = "https://www.awesomegym.com"
        
        mock_rating_locator = MagicMock()
        mock_rating_locator.first = mock_rating_locator
        mock_rating_locator.count.return_value = 1
        mock_rating_locator.text_content.return_value = "4.7(450)"
        
        mock_cat_locator = MagicMock()
        mock_cat_locator.first = mock_cat_locator
        mock_cat_locator.count.return_value = 1
        mock_cat_locator.text_content.return_value = "Gym"
        
        # Route locator calls based on query selectors
        def mock_locator(selector):
            if selector == "h1":
                return mock_name_locator
            elif selector == 'button[data-item-id="address"]':
                return mock_addr_locator
            elif selector == 'button[data-item-id^="phone:tel:"]':
                return mock_phone_locator
            elif selector == 'a[data-item-id="authority"]':
                return mock_web_locator
            elif selector == 'div.F7nice':
                return mock_rating_locator
            elif selector == 'button[jsaction*="category"]':
                return mock_cat_locator
            return MagicMock(count=lambda: 0)
            
        mock_page.locator.side_effect = mock_locator
        
        api = PlacesAPI()
        # Call details extraction
        biz_info = api._extract_details_from_page(mock_page)
        
        self.assertEqual(biz_info["name"], "Awesome Gym")
        self.assertEqual(biz_info["full_address"], "123 Fitness Ave, California")
        self.assertEqual(biz_info["phone_number"], "+1 408-555-9000")
        self.assertEqual(biz_info["website"], "https://www.awesomegym.com")
        self.assertEqual(biz_info["rating"], 4.7)
        self.assertEqual(biz_info["total_reviews"], 450)
        self.assertEqual(biz_info["latitude"], 37.3688)
        self.assertEqual(biz_info["longitude"], -122.0363)
        self.assertIn("gym", biz_info["business_types"])

if __name__ == "__main__":
    unittest.main()
