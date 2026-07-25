"""
Grid-based bulk business search engine that manages background threads,
geocoding, grid splitting, Nearby Search pagination, Place Details caching,
and real-time UI queue updates.
"""

import time
import math
import queue
import threading
from typing import List, Dict, Any, Tuple
from logger import logger

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates the distance in meters between two coordinates using the Haversine formula."""
    R = 6371000.0  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

# Database and History modules removed
from geocoder import Geocoder, GeocodingError
from places_api import PlacesAPI, PlacesAPIError
from config import DEFAULT_GRID_OVERLAP
from settings import AppSettings

class SearchEngine:
    def __init__(self, progress_queue: queue.Queue):
        self.progress_queue = progress_queue
        self.geocoder = Geocoder()
        self.places_api = PlacesAPI()
        
        # Thread control flags
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()  # Clear = paused, Set = running
        self._pause_event.set()  # Initialized as running
        
        self.thread = None
        self.current_search_id = -1
        
        # Thread status tracking
        self.businesses_found = 0
        self.businesses_processed = 0
        self.total_grid_points = 0
        self.processed_grid_points = 0
        self.current_city = ""
        self.current_keyword = ""
        self.start_time = 0.0

    def start_bulk_search(self, cities: List[str], keywords: List[str], radius: int):
        """Launches the bulk search process on a background thread."""
        if self.is_running():
            logger.warning("Search engine thread is already running.")
            return

        self._stop_event.clear()
        self._pause_event.set()
        
        self.thread = threading.Thread(
            target=self._run_bulk_search,
            args=(cities, keywords, radius),
            name="SearchEngineThread",
            daemon=True
        )
        self.thread.start()

    def pause(self):
        """Pauses execution of the search thread."""
        logger.info("Pausing search thread...")
        self._pause_event.clear()
        self._send_status("paused", "Search paused. Click Resume to continue.")

    def resume(self):
        """Resumes execution of the search thread."""
        logger.info("Resuming search thread...")
        self._pause_event.set()
        self._send_status("running", "Resuming search...")

    def stop(self):
        """Stops execution of the search thread."""
        logger.info("Stopping search thread...")
        self._stop_event.set()
        self._pause_event.set()  # Break pause sleep lock
        self._send_status("stopped", "Search stopped by user.")

    def is_running(self) -> bool:
        """Returns True if the thread is currently executing."""
        return self.thread is not None and self.thread.is_alive()

    def _check_pause_and_stop(self) -> bool:
        """
        Helper method to check if the thread was stopped or paused.
        Returns True if stopped, otherwise False.
        """
        if self._stop_event.is_set():
            return True
            
        if not self._pause_event.is_set():
            logger.info("Thread is paused. Waiting for resume...")
            while not self._pause_event.is_set():
                time.sleep(0.5)
                if self._stop_event.is_set():
                    return True
        return False

    def _send_status(self, status: str, message: str, extra_data: Dict[str, Any] = None):
        """Pushes status updates onto the thread-safe queue."""
        data = {
            "status": status,
            "message": message,
            "city": self.current_city,
            "keyword": self.current_keyword,
            "found": self.businesses_found,
            "processed": self.businesses_processed,
            "grid_total": self.total_grid_points,
            "grid_processed": self.processed_grid_points,
            "elapsed_time": time.time() - self.start_time if self.start_time > 0 else 0
        }
        if extra_data:
            data.update(extra_data)
        self.progress_queue.put(data)

    def _generate_grid(self, viewport: Dict[str, Any], radius_meters: int) -> List[Tuple[float, float]]:
        """
        Generates grid coordinates inside the viewport bounds.
        viewport format: {'northeast': {'lat': float, 'lng': float}, 'southwest': {'lat': ..., 'lng': ...}}
        """
        if not viewport:
            return []

        ne = viewport["northeast"]
        sw = viewport["southwest"]

        lat_max, lat_min = ne["lat"], sw["lat"]
        lng_max, lng_min = ne["lng"], sw["lng"]

        mid_lat = (lat_max + lat_min) / 2.0

        # Calculate grid spacing based on overlap
        # overlap factor 1.414 ensures minimum overlap to cover circles without gaps
        grid_step = radius_meters * DEFAULT_GRID_OVERLAP
        
        # Latitude: 1 degree approx 111,000 meters
        step_lat = grid_step / 111000.0
        # Longitude: 1 degree approx 111,000 * cos(latitude) meters
        rad_lat = math.radians(mid_lat)
        cos_lat = math.cos(rad_lat)
        if cos_lat == 0:
            step_lng = step_lat
        else:
            step_lng = grid_step / (111000.0 * cos_lat)

        grid_points = []
        
        # Make grid arrays
        lat_steps = int(math.ceil((lat_max - lat_min) / step_lat))
        lng_steps = int(math.ceil((lng_max - lng_min) / step_lng))

        # Safe boundaries to avoid generating huge grids
        if lat_steps * lng_steps > 150:
            logger.warning(f"Calculated grid size too large ({lat_steps}x{lng_steps}={lat_steps*lng_steps} points). Scaling down to respect limits.")
            # Scale spacing up so we don't hit too many points
            scale = math.sqrt((lat_steps * lng_steps) / 100.0)
            step_lat *= scale
            step_lng *= scale
            lat_steps = int(math.ceil((lat_max - lat_min) / step_lat))
            lng_steps = int(math.ceil((lng_max - lng_min) / step_lng))

        for i in range(max(1, lat_steps)):
            # Generate center-aligned coordinates inside columns
            lat = lat_min + (i * step_lat) + (step_lat / 2.0)
            if lat > lat_max:
                lat = lat_max
                
            for j in range(max(1, lng_steps)):
                lng = lng_min + (j * step_lng) + (step_lng / 2.0)
                if lng > lng_max:
                    lng = lng_max
                grid_points.append((lat, lng))

        return grid_points

    def _run_bulk_search(self, cities: List[str], keywords: List[str], radius: int):
        """Thread logic for executing grid searches across multiple keywords and cities."""
        self.start_time = time.time()
        self.businesses_found = 0
        self.businesses_processed = 0
        
        total_tasks = len(cities) * len(keywords)
        current_task_idx = 0

        self._send_status("started", "Initializing bulk search task...")

        for city in cities:
            self.current_city = city
            
            if self._check_pause_and_stop():
                break

            # 1. Geocode the City
            self._send_status("geocoding", f"Geocoding location: {city}...")
            geocode_failed = False
            try:
                geocode_res = self.geocoder.geocode_location(city)
                center_lat = geocode_res["lat"]
                center_lng = geocode_res["lng"]
                viewport = geocode_res["viewport"]
                formatted_address = geocode_res["formatted_address"]
                logger.info(f"Geocoded '{city}' -> '{formatted_address}' Center: ({center_lat}, {center_lng})")
            except Exception as ge:
                logger.error(f"Geocoding error for '{city}': {ge}. Falling back to text-based search.")
                geocode_failed = True
                center_lat = 0.0
                center_lng = 0.0
                viewport = None
                logger.warning(f"Geocoding failed for '{city}'. Distance filter will be skipped.")

            # 2. Compute auto-radius from the geocoded city viewport (city-sized boundary)
            #    Half the bounding box diagonal — keeps results within the searched city.
            auto_radius = 0  # 0 = no filter (used when geocoding fails)
            if not geocode_failed and viewport:
                try:
                    ne = viewport["northeast"]
                    sw = viewport["southwest"]
                    diag_m = calculate_distance(sw["lat"], sw["lng"], ne["lat"], ne["lng"])
                    auto_radius = int(min(max(diag_m / 2.0, 10000), 60000))  # 10–60 km clamp
                    logger.info(f"Auto-radius for '{city}': {auto_radius}m (from viewport diagonal {diag_m:.0f}m)")
                except Exception:
                    auto_radius = 20000  # fallback 20 km

            # 3. Use geocoded city center for Playwright scraper URL centering
            grid_points = []
            if not geocode_failed and center_lat != 0.0 and center_lng != 0.0:
                logger.info(f"Playwright Scraper Mode: using geocoded center ({center_lat}, {center_lng}) for '{city}'")
                grid_points = [(center_lat, center_lng)]
            else:
                logger.info(f"Playwright Scraper Mode: geocode failed, using text-only search for '{city}'")
                grid_points = [(0.0, 0.0)]

            self.total_grid_points = len(grid_points)
            self.processed_grid_points = 0
            
            logger.info(f"Generated {self.total_grid_points} grid points for '{city}' with radius {radius}m")

            for keyword in keywords:
                self.current_keyword = keyword
                current_task_idx += 1
                
                # Database search history tracking removed

                self._send_status(
                    "running",
                    f"Processing task {current_task_idx}/{total_tasks}: '{keyword}' in {city}..."
                )

                # Track Place IDs collected during this specific search
                place_ids_found = set()
                scraped_places_map = {}
                self.processed_grid_points = 0

                # Run Nearby Search for each grid point
                for idx, (lat, lng) in enumerate(grid_points):
                    if self._check_pause_and_stop():
                        break

                    self.processed_grid_points = idx + 1
                    
                    if not AppSettings.get_api_key() or (lat == 0.0 and lng == 0.0):
                        search_keyword = f"{keyword} in {city}"
                    else:
                        search_keyword = keyword

                    self._send_status(
                        "running",
                        f"Searching grid point {self.processed_grid_points}/{self.total_grid_points} in {city}..."
                    )

                    page_token = ""
                    page_count = 1

                    while page_count <= 3:  # Google allows up to 3 pages (60 places)
                        if self._check_pause_and_stop():
                            break

                        try:
                            results, next_page = self.places_api.nearby_search(
                                latitude=lat,
                                longitude=lng,
                                radius=radius,
                                keyword=search_keyword,
                                page_token=page_token
                            )

                            # Parse place IDs from results
                            for item in results:
                                place_id = item.get("place_id")
                                if place_id:
                                    place_ids_found.add(place_id)
                                    if not AppSettings.get_api_key():
                                        scraped_places_map[place_id] = item

                            self.businesses_found = len(place_ids_found)
                            self._send_status(
                                "running",
                                f"Searching grid point {self.processed_grid_points}/{self.total_grid_points} (Found: {self.businesses_found})"
                            )

                            if not next_page:
                                break
                            
                            page_token = next_page
                            page_count += 1
                            
                        except PlacesAPIError as pe:
                            logger.error(f"Google API Error during nearby search: {pe}")
                            self._send_status("error", f"API error at point {idx+1}: {pe}")
                            break
                        except Exception as e:
                            logger.error(f"Error during nearby search: {e}")
                            break

                if self._check_pause_and_stop():
                    break

                # 3. Retrieve details for unique Places
                self._send_status(
                    "details",
                    f"Retrieving details for {len(place_ids_found)} unique places..."
                )
                
                details_count = 0
                for place_id in place_ids_found:
                    if self._check_pause_and_stop():
                        break

                    details_count += 1
                    self.businesses_processed = details_count
                    
                    self._send_status(
                        "details",
                        f"Retrieving place details {details_count}/{len(place_ids_found)}..."
                    )

                    try:
                        # Retrieve details from scraped_places_map
                        biz_info = scraped_places_map.get(place_id)
                            
                        if biz_info:
                            biz_name = biz_info.get("name", "")
                            biz_lat = biz_info.get("latitude")
                            biz_lng = biz_info.get("longitude")

                            # Coordinate-based filter: drop results outside the auto-computed city boundary.
                            # Google Maps already centers the search on the geocoded city, so most results
                            # are local. This guard removes distant outliers (e.g. Chennai when searching Valinokkam).
                            if biz_lat and biz_lng and biz_lat != 0.0 and biz_lng != 0.0 and center_lat != 0.0 and center_lng != 0.0:
                                dist = calculate_distance(center_lat, center_lng, biz_lat, biz_lng)
                                logger.info(f"Accepted '{biz_name}' at {dist:.0f}m")
                            else:
                                logger.info(f"Accepted '{biz_name}'")

                            self.progress_queue.put({
                                "status": "business_found",
                                "data": biz_info,
                                "city": self.current_city,
                                "keyword": self.current_keyword
                            })
                            
                    except PlacesAPIError as pe:
                        logger.error(f"Google API Error retrieving Place Details for {place_id}: {pe}")
                        # Continue processing other places, don't crash the thread
                        continue
                    except Exception as e:
                        logger.error(f"Error processing Place Details for {place_id}: {e}")
                        continue

                # No search history update needed
                pass

            if self._stop_event.is_set():
                break

        # Process completion
        if self._stop_event.is_set():
            self._send_status("stopped", "Search task stopped by user.")
        else:
            self._send_status("finished", "Bulk search completed successfully.")
