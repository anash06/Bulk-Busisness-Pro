"""
Geocoder that supports official Google Geocoding API (when an API Key is set)
and fallback OpenStreetMap Nominatim API (when no API Key is set) for free, keyless city searches.
"""

import time
import requests
from typing import Dict, Any
from config import GOOGLE_GEOCODE_URL
from logger import logger
from database import log_api_call
from settings import AppSettings

class GeocodingError(Exception):
    """Custom exception for Geocoding failures."""
    pass

class Geocoder:
    def __init__(self):
        pass

    def geocode_location(self, address_str: str) -> Dict[str, Any]:
        """
        Geocodes a location string using Google Geocoder or OSM Nominatim.
        """
        api_key = AppSettings.get_api_key()

        if api_key:
            return self._geocode_google(address_str, api_key)
        else:
            return self._geocode_nominatim(address_str)

    def _geocode_google(self, address_str: str, api_key: str) -> Dict[str, Any]:
        """Geocodes using the official Google Geocoding API."""
        params = {
            "address": address_str,
            "key": api_key
        }

        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            # Apply request delay
            delay = AppSettings.get_request_delay()
            if delay > 0:
                time.sleep(delay)
                
            logger.debug(f"Making Google Geocoding request for '{address_str}' (Attempt {attempt+1}/{max_retries})")
            
            try:
                log_api_call("geocode", GOOGLE_GEOCODE_URL, "pending")
                response = requests.get(GOOGLE_GEOCODE_URL, params=params, timeout=15)
                log_api_call("geocode", GOOGLE_GEOCODE_URL, str(response.status_code))

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")

                    if status == "OK" and data.get("results"):
                        result = data["results"][0]
                        geometry = result.get("geometry", {})
                        location = geometry.get("location", {})
                        viewport = geometry.get("bounds") or geometry.get("viewport")

                        return {
                            "lat": location.get("lat"),
                            "lng": location.get("lng"),
                            "viewport": viewport,
                            "formatted_address": result.get("formatted_address")
                        }
                    elif status == "ZERO_RESULTS":
                        logger.warning(f"Google Geocoding returned ZERO_RESULTS for '{address_str}'")
                        raise GeocodingError(f"Could not locate '{address_str}' on Google. Check the spelling.")
                    elif status == "OVER_QUERY_LIMIT":
                        logger.warning(f"Google Geocoding API rate limit hit. Retrying in {backoff}s...")
                        time.sleep(backoff)
                        backoff *= 2.0
                        continue
                    elif status == "REQUEST_DENIED":
                        raise GeocodingError(f"API Request Denied: {data.get('error_message', 'Request Denied')}")
                    else:
                        raise GeocodingError(f"Geocoding failed with status {status}: {data.get('error_message')}")
                else:
                    raise GeocodingError(f"HTTP Error {response.status_code} during Google Geocoding.")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Network error during Google Geocoding: {e}. Retrying...")
                time.sleep(backoff)
                backoff *= 2.0

        raise GeocodingError(f"Failed to geocode location '{address_str}' with Google Geocoder.")

    def _geocode_nominatim(self, address_str: str) -> Dict[str, Any]:
        """Geocodes using free OpenStreetMap Nominatim API (no API key required).
        
        Tries to return the actual city/town rather than district or administrative boundary,
        to ensure the geocoded center and bounding box are city-sized (not district-sized).
        """
        url = "https://nominatim.openstreetmap.org/search"
        headers = {
            "User-Agent": "BusinessDirectoryExporterUtility/2.5 (contact-exporter@geodatasearch.org)",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }

        delay = AppSettings.get_request_delay()
        if delay > 0:
            time.sleep(delay)

        logger.debug(f"Making OSM Nominatim Geocoding request for '{address_str}'")

        def _do_request(extra_params: dict) -> dict | None:
            params = {
                "q": address_str,
                "format": "json",
                "limit": 5,          # fetch several candidates so we can pick the best
                "addressdetails": 1,
            }
            params.update(extra_params)
            try:
                log_api_call("geocode_osm", url, "pending")
                response = requests.get(url, params=params, headers=headers, timeout=15)
                log_api_call("geocode_osm", url, str(response.status_code))
                if response.status_code == 200:
                    return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error during Nominatim Geocoding: {e}")
            return None

        def _pick_best(results: list) -> dict | None:
            """
            Prefer settlement-level results (city, town, village, suburb, hamlet)
            over administrative boundaries (district, county, state, country).
            """
            if not results:
                return None
            preferred_types = {"city", "town", "village", "suburb", "hamlet", "municipality",
                               "borough", "quarter", "neighbourhood", "administrative"}
            # Rank: exact city/town types first, then anything else
            for r in results:
                rtype = (r.get("type") or "").lower()
                rclass = (r.get("class") or "").lower()
                # Skip pure district/county/state-level hits that span huge areas
                if rtype in {"district", "county", "state", "country", "region"}:
                    continue
                if rclass == "boundary" and rtype not in {"city", "town", "village"}:
                    continue
                return r
            # Fallback: just return the first result
            return results[0]

        try:
            # First attempt: restrict to place features (cities/towns/villages)
            data = _do_request({"featuretype": "settlement"})
            result = _pick_best(data) if data else None

            # Second attempt (fallback): unrestricted search
            if not result:
                logger.debug(f"Settlement search returned nothing for '{address_str}', trying unrestricted...")
                data = _do_request({})
                result = _pick_best(data) if data else None

            # Third attempt (fallback): append ', India' for single-word locations
            if not result and "," not in address_str:
                logger.debug(f"Unrestricted search returned nothing for '{address_str}', trying with country context...")
                try:
                    params_fallback = {"q": f"{address_str}, India", "format": "json", "addressdetails": 1, "limit": 5}
                    resp_fallback = requests.get(NOMINATIM_GEOCODE_URL, params=params_fallback, headers=headers, timeout=5)
                    if resp_fallback.status_code == 200:
                        data_fb = resp_fallback.json()
                        result = _pick_best(data_fb) if data_fb else None
                except Exception:
                    pass

            if not result:
                logger.warning(f"Nominatim returned no results for '{address_str}'")
                raise GeocodingError(f"Could not locate '{address_str}' on OpenStreetMap.")

            lat = float(result["lat"])
            lng = float(result["lon"])
            display_name = result.get("display_name", "")

            # Bounding Box: OSM returns list [lat_min, lat_max, lon_min, lon_max]
            bbox = result.get("boundingbox")
            viewport = None
            if bbox and len(bbox) == 4:
                viewport = {
                    "southwest": {"lat": float(bbox[0]), "lng": float(bbox[2])},
                    "northeast": {"lat": float(bbox[1]), "lng": float(bbox[3])}
                }

            logger.debug(f"Nominatim chose: '{display_name}' type={result.get('type')} class={result.get('class')}")
            return {
                "lat": lat,
                "lng": lng,
                "viewport": viewport,
                "formatted_address": display_name
            }

        except GeocodingError:
            raise
        except Exception as e:
            logger.error(f"Nominatim Geocoding unexpected error: {e}")
            raise GeocodingError(f"Nominatim failure: {e}")

