"""
Google Places API wrapper that dynamically supports:
1. Official Google Places API (Nearby Search and Place Details) if an API key is set.
2. Playwright Chromium web browser automation scraper if no API key is configured.
"""

import time
import json
import re
import urllib.parse
import requests
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
from config import GOOGLE_NEARBY_SEARCH_URL, GOOGLE_PLACE_DETAILS_URL, PLACE_TYPES
from logger import logger
from database import log_api_call
from settings import AppSettings

# Configure Playwright to look for and install browsers locally next to the executable
if getattr(sys, 'frozen', False):
    app_dir = Path(sys.executable).parent
else:
    app_dir = Path(__file__).parent.resolve()

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(app_dir / "playwright-browsers")

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

class PlacesAPIError(Exception):
    """Custom exception class for Google Places API errors."""
    pass

class PlacesAPIQuotaError(PlacesAPIError):
    """Quota limit exceeded."""
    pass

class PlacesAPIKeyError(PlacesAPIError):
    """Invalid API key."""
    pass

class PlacesAPI:
    def __init__(self):
        # A list of realistic User Agents to rotate and avoid bot detection
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]
        self.ua_index = 0

    def _get_headers(self) -> Dict[str, str]:
        """Returns standard browser headers with rotated user agents."""
        ua = self.user_agents[self.ua_index]
        self.ua_index = (self.ua_index + 1) % len(self.user_agents)
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/"
        }

    def _apply_delay(self):
        """Applies configured request delay to respect rate limits."""
        delay = AppSettings.get_request_delay()
        if delay > 0:
            time.sleep(delay)

    def nearby_search(self, latitude: float, longitude: float, radius: int, keyword: str = "", page_token: str = "") -> Tuple[List[Dict[str, Any]], str]:
        """
        Main Nearby Search router using Playwright Web Scraper.
        """
        if page_token:
            return [], ""
        return self._nearby_search_scraper(latitude, longitude, radius, keyword)

    def get_place_details(self, place_id: str) -> Dict[str, Any]:
        """
        Main Details router.
        If API key is present, calls the API. Otherwise returns placeholder or scrapes.
        """
        api_key = AppSettings.get_api_key()
        if api_key:
            return self._get_place_details_api(place_id)
        else:
            return {}

    # ==========================================
    # OFFICIAL API IMPLEMENTATION
    # ==========================================
    def _make_api_request(self, url: str, params: Dict[str, Any], api_name: str) -> Dict[str, Any]:
        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            self._apply_delay()
            logger.debug(f"Making API request to {api_name} (Attempt {attempt+1}/{max_retries})")
            
            try:
                log_api_call(api_name, url, "pending")
                response = requests.get(url, params=params, timeout=15)
                log_api_call(api_name, url, str(response.status_code))

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")
                    
                    if status == "OK" or status == "ZERO_RESULTS":
                        return data
                    elif status == "OVER_QUERY_LIMIT":
                        logger.warning(f"Google API OVER_QUERY_LIMIT. Retrying in {backoff}s...")
                        time.sleep(backoff)
                        backoff *= 2.0
                        continue
                    elif status == "REQUEST_DENIED":
                        error_msg = data.get("error_message", "Request Denied.")
                        raise PlacesAPIKeyError(f"API Request Denied: {error_msg}")
                    else:
                        raise PlacesAPIError(f"API Error {status}: {data.get('error_message')}")
                elif response.status_code in [500, 503]:
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    raise PlacesAPIError(f"HTTP Error {response.status_code}")
            except requests.exceptions.RequestException as e:
                time.sleep(backoff)
                backoff *= 2.0

        raise PlacesAPIQuotaError("Failed to receive response from Google API.")

    def _nearby_search_api(self, latitude: float, longitude: float, radius: int, keyword: str = "", page_token: str = "") -> Tuple[List[Dict[str, Any]], str]:
        api_key = AppSettings.get_api_key()
        params = {"key": api_key}

        if page_token:
            params["pagetoken"] = page_token
            time.sleep(2.0)
        else:
            params["location"] = f"{latitude},{longitude}"
            params["radius"] = radius
            if keyword:
                params["keyword"] = keyword

        data = self._make_api_request(GOOGLE_NEARBY_SEARCH_URL, params, "nearby_search")
        return data.get("results", []), data.get("next_page_token", "")

    def _get_place_details_api(self, place_id: str) -> Dict[str, Any]:
        api_key = AppSettings.get_api_key()
        fields = (
            "name,place_id,formatted_address,address_components,geometry,"
            "formatted_phone_number,international_phone_number,website,url,"
            "rating,user_ratings_total,business_status,opening_hours,price_level,"
            "plus_code,types,wheelchair_accessible_entrance"
        )
        params = {
            "place_id": place_id,
            "fields": fields,
            "key": api_key
        }

        data = self._make_api_request(GOOGLE_PLACE_DETAILS_URL, params, "details")
        result = data.get("result", {})
        if not result:
            return {}

        city = state = country = postal_code = ""
        for comp in result.get("address_components", []):
            types = comp.get("types", [])
            if "locality" in types:
                city = comp.get("long_name", "")
            elif "administrative_area_level_1" in types:
                state = comp.get("short_name", "")
            elif "country" in types:
                country = comp.get("long_name", "")
            elif "postal_code" in types:
                postal_code = comp.get("long_name", "")

        opening_hours = None
        raw_hours = result.get("opening_hours")
        if raw_hours:
            opening_hours = {
                "open_now": raw_hours.get("open_now"),
                "weekday_text": raw_hours.get("weekday_text", [])
            }

        return {
            "place_id": result.get("place_id"),
            "name": result.get("name"),
            "full_address": result.get("formatted_address"),
            "city": city,
            "state": state,
            "country": country,
            "postal_code": postal_code,
            "latitude": result.get("geometry", {}).get("location", {}).get("lat"),
            "longitude": result.get("geometry", {}).get("location", {}).get("lng"),
            "phone_number": result.get("formatted_phone_number"),
            "international_phone_number": result.get("international_phone_number"),
            "website": result.get("website"),
            "maps_url": result.get("url"),
            "rating": result.get("rating"),
            "total_reviews": result.get("user_ratings_total"),
            "business_status": result.get("business_status"),
            "opening_hours": opening_hours,
            "business_types": result.get("types", []),
            "price_level": result.get("price_level"),
            "plus_code": result.get("plus_code", {}).get("global_code"),
            "accessibility": {"wheelchair_accessible_entrance": result.get("wheelchair_accessible_entrance")},
        }

    # ==========================================
    # PLAYWRIGHT SCRAPER IMPLEMENTATION
    # ==========================================
    def _nearby_search_scraper(self, latitude: float, longitude: float, radius: int, keyword: str) -> Tuple[List[Dict[str, Any]], str]:
        """
        Uses Playwright Chromium browser automation to navigate Google Maps,
        infinite scroll the feed container, and scrape listing coordinates/detail panes.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright library is not installed. Scraper mode cannot run.")
            raise PlacesAPIError("Playwright library is missing. Please run: pip install playwright && playwright install chromium")

        # Determine zoom level based on search radius
        zoom = 15
        if radius > 10000:
            zoom = 12
        elif radius > 5000:
            zoom = 13
        elif radius < 1000:
            zoom = 16

        # Encode query
        encoded_query = urllib.parse.quote(keyword)
        if latitude == 0.0 and longitude == 0.0:
            # Fallback text query mode: no centering coordinates
            url = f"https://www.google.com/maps/search/{encoded_query}"
        else:
            # Construct Google Maps search URL centered at coordinates
            url = f"https://www.google.com/maps/search/{encoded_query}/@{latitude},{longitude},{zoom}z"

        self._apply_delay()
        logger.info(f"Playwright Scraper: Opening browser to URL -> {url}")
        
        parsed_places = []
        
        try:
            log_api_call("playwright_search", url, "pending")
            
            with sync_playwright() as p:
                headless_pref = AppSettings.get_headless()
                
                # Auto-detect Chromium executable path in Linux / Docker environments
                import glob
                possible_execs = (
                    glob.glob("/ms-playwright/chromium-*/chrome-linux/chrome") +
                    glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome") +
                    glob.glob("/home/*/.cache/ms-playwright/chromium-*/chrome-linux/chrome") +
                    glob.glob("/app/playwright-browsers/chromium-*/chrome-linux/chrome")
                )
                
                launch_kwargs = {
                    "headless": headless_pref,
                    "args": [
                        "--disable-gpu",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-service-autorun"
                    ]
                }
                
                if possible_execs and os.path.exists(possible_execs[0]):
                    logger.info(f"Playwright Scraper: Found Chromium binary at -> {possible_execs[0]}")
                    launch_kwargs["executable_path"] = possible_execs[0]
                
                try:
                    browser = p.chromium.launch(**launch_kwargs)
                except Exception as le:
                    logger.warning(f"Playwright custom path launch notice: {le}. Retrying standard launch...")
                    if "executable_path" in launch_kwargs:
                        del launch_kwargs["executable_path"]
                    browser = p.chromium.launch(**launch_kwargs)
                
                context = browser.new_context(
                    user_agent=self.user_agents[0],
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()
                page.goto(url, timeout=30000)
                
                # Bypassing Cookie Consent wall if visible
                try:
                    consent_btn = page.locator('form[action*="consent"] button, button[aria-label*="Accept"], button[aria-label*="Agree"], button[aria-label*="Reject"]').first
                    if consent_btn.count() > 0:
                        logger.info("Playwright Scraper: Agreeing to cookies consent.")
                        consent_btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

                # Check if search redirected directly to a single business detail view
                if "/maps/place/" in page.url:
                    logger.info("Playwright Scraper: Direct redirect to a single place page.")
                    biz_info = self._extract_details_from_page(page, page.url)
                    if biz_info and biz_info["name"] != "Unknown Business":
                        parsed_places.append(biz_info)
                        
                else:
                    # Multi-listings results pane feed container
                    feed_selectors = [
                        'div[role="feed"]',
                        'div[aria-label*="Results for"]',
                        'div.m6QE3c[tabindex="-1"]',
                        'div.m6QE3c'
                    ]
                    feed_selector = None
                    feed_found = False
                    for selector in feed_selectors:
                        try:
                            if page.locator(selector).first.count() > 0:
                                feed_selector = selector
                                feed_found = True
                                break
                        except Exception:
                            continue

                    if not feed_found:
                        try:
                            page.wait_for_selector('div[role="feed"]', timeout=6000)
                            feed_selector = 'div[role="feed"]'
                            feed_found = True
                        except Exception:
                            logger.warning("Feed selector not found. Retrying link extraction from page body...")
                            feed_selector = 'body'
                            feed_found = True

                    if feed_found and feed_selector:
                        feed = page.locator(feed_selector).first
                        last_height = feed.evaluate("el => el.scrollHeight")
                        scroll_attempts = 0
                        max_scrolls = 15  # Fast 15 scrolls for instant responsiveness
                        
                        while scroll_attempts < max_scrolls:
                            # Check if Google Maps displays the end of list message
                            end_of_list_visible = False
                            try:
                                end_of_list_el = page.locator('span:has-text("You\'ve reached the end of the list")').first
                                if end_of_list_el.count() > 0 and end_of_list_el.is_visible():
                                    end_of_list_visible = True
                            except Exception:
                                pass
                            
                            if end_of_list_visible:
                                logger.info("Playwright Scraper: Reached the end of the Google Maps list.")
                                break

                            feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                            page.wait_for_timeout(300)
                            
                            new_height = feed.evaluate("el => el.scrollHeight")
                            if new_height == last_height:
                                page.wait_for_timeout(300)
                                feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                                new_height2 = feed.evaluate("el => el.scrollHeight")
                                if new_height2 == last_height:
                                    break
                                last_height = new_height2
                            else:
                                last_height = new_height
                            scroll_attempts += 1
                        
                        # Extract all listings directly from the sidebar feed DOM in 1 fast pass (2 seconds)
                        feed_items_data = page.evaluate("""() => {
                            const items = [];
                            const cards = document.querySelectorAll('div.Nv2pk, div[role="article"], a[href*="/maps/place/"]');
                            const seenNames = new Set();
                            
                            cards.forEach((card, idx) => {
                                try {
                                    let linkEl = card.tagName === 'A' ? card : card.querySelector('a[href*="/maps/place/"]');
                                    let href = linkEl ? linkEl.getAttribute('href') : '';
                                    
                                    let name = '';
                                    if (linkEl && linkEl.getAttribute('aria-label')) {
                                        name = linkEl.getAttribute('aria-label').trim();
                                    }
                                    if (!name && card.querySelector('div.fontHeadlineSmall')) {
                                        name = card.querySelector('div.fontHeadlineSmall').textContent.trim();
                                    }
                                    if (!name && linkEl) {
                                        name = linkEl.textContent.trim();
                                    }
                                    
                                    if (!name || name === 'Directions' || name === 'Website' || name === 'Reviews' || seenNames.has(name)) return;
                                    seenNames.add(name);

                                    let cardText = card.textContent || '';
                                    
                                    // Extract Rating & Reviews
                                    let rating = 0.0;
                                    let reviews = 0;
                                    let ratingEl = card.querySelector('span.MW4etd, div.F7nice');
                                    if (ratingEl) {
                                        let rText = ratingEl.textContent.trim();
                                        let m = rText.match(/([1-5]\\.\\d)/);
                                        if (m) rating = parseFloat(m[1]);
                                    }
                                    let revEl = card.querySelector('span.UY7F9');
                                    if (revEl) {
                                        let rvText = revEl.textContent.replace(/[^0-9]/g, '');
                                        if (rvText) reviews = parseInt(rvText);
                                    }

                                    // Extract phone number from card text
                                    let phone = '';
                                    let phoneMatch = cardText.match(/(\\+?\\d{1,4}[-.\\s]?\\(?\\d{2,4}\\)?[-.\\s]?\\d{3,4}[-.\\s]?\\d{3,4})/);
                                    if (phoneMatch && phoneMatch[1].length >= 8 && !phoneMatch[1].includes('0000')) {
                                        phone = phoneMatch[1].trim();
                                    }

                                    // Extract website link
                                    let web = '';
                                    let webEl = card.querySelector('a[href*="http"]:not([href*="google.com"])');
                                    if (webEl) web = webEl.getAttribute('href');

                                    // Coordinates from URL
                                    let lat = 0.0, lng = 0.0;
                                    if (href) {
                                        let coordMatch = href.match(/!3d(-?\\d+\\.\\d+)!4d(-?\\d+\\.\\d+)/);
                                        if (coordMatch) {
                                            lat = parseFloat(coordMatch[1]);
                                            lng = parseFloat(coordMatch[2]);
                                        }
                                    }

                                    // Hash place_id
                                    let hashVal = 0;
                                    let strToHash = name + (href || idx);
                                    for (let i = 0; i < strToHash.length; i++) {
                                        hashVal = ((hashVal << 5) - hashVal) + strToHash.charCodeAt(i);
                                        hashVal |= 0;
                                    }

                                    items.push({
                                        place_id: 'scrape_' + Math.abs(hashVal),
                                        name: name,
                                        full_address: cardText.slice(0, 120),
                                        city: '',
                                        state: '',
                                        country: 'India',
                                        postal_code: '',
                                        latitude: lat,
                                        longitude: lng,
                                        phone_number: phone,
                                        international_phone_number: phone,
                                        website: web,
                                        maps_url: href ? (href.startsWith('http') ? href : ('https://www.google.com' + href)) : page.url,
                                        rating: rating,
                                        total_reviews: reviews,
                                        business_status: 'OPERATIONAL',
                                        business_types: ['Business']
                                    });
                                } catch(e) {}
                            });
                            return items;
                        }""")

                        if feed_items_data and isinstance(feed_items_data, list):
                            logger.info(f"Playwright Scraper: Extracted {len(feed_items_data)} items directly from feed DOM in 1 pass.")
                            parsed_places.extend(feed_items_data)

                        # If 1-pass extraction yielded fewer than 5 items, fallback to fast detail loads for top 5
                        if len(parsed_places) < 5:
                            links_loc = page.locator('a[href*="/maps/place/"]')
                            links_count = links_loc.count()
                            place_urls = []
                            for i in range(links_count):
                                href = links_loc.nth(i).get_attribute('href')
                                if href and href not in place_urls:
                                    place_urls.append(href)

                            target_urls = place_urls[:8]
                            for idx, href in enumerate(target_urls):
                                try:
                                    logger.info(f"Playwright Scraper: Fallback detail load ({idx+1}/{len(target_urls)}) -> {href}")
                                    page.goto(href, wait_until="domcontentloaded", timeout=6000)
                                    biz_info = self._extract_details_from_page(page, href)
                                    if biz_info and biz_info["name"] != "Unknown Business":
                                        # Deduplicate by name
                                        if not any(p.get("name") == biz_info["name"] for p in parsed_places):
                                            parsed_places.append(biz_info)
                                except Exception as ex:
                                    logger.error(f"Error scraping detail page {href}: {ex}")
                                    continue

                browser.close()
                log_api_call("playwright_search", url, "200")
                
            return parsed_places, ""
            
        except Exception as e:
            logger.error(f"Playwright Scraper Exception: {e}", exc_info=True)
            return [], ""

    def _extract_details_from_page(self, page, place_url: str = "") -> Dict[str, Any]:
        """Scrapes text fields from detail panel elements."""
        # Allow panel animations to settle fast
        page.wait_for_timeout(150)
        
        current_url = place_url or page.url
        latitude = 0.0
        longitude = 0.0
        
        # 1. Try parsing exact coordinates from !3d...!4d URL parameters (extremely reliable)
        url_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', current_url)
        if url_match:
            latitude = float(url_match.group(1))
            longitude = float(url_match.group(2))
            logger.debug(f"Coordinates parsed from URL parameters: ({latitude}, {longitude})")
            
        # 2. Try parsing coordinates from /@lat,lng in the URL path
        if latitude == 0.0 or longitude == 0.0:
            coord_match = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', current_url)
            if coord_match:
                latitude = float(coord_match.group(1))
                longitude = float(coord_match.group(2))
                logger.debug(f"Coordinates parsed from URL path: ({latitude}, {longitude})")
        
        # 3. Fallback: Parse coordinates from meta staticmap image tag (exact location pin marker only)
        if latitude == 0.0 or longitude == 0.0:
            try:
                meta_img = page.locator('meta[itemprop="image"]').first
                if meta_img.count() > 0:
                    img_url = meta_img.get_attribute("content") or ""
                    # Check markers first (the exact red pin location on maps)
                    marker_match = re.search(r'markers=(-?\d+\.\d+)%2C(-?\d+\.\d+)', img_url)
                    if not marker_match:
                        marker_match = re.search(r'markers=(-?\d+\.\d+),(-?\d+\.\d+)', img_url)
                    
                    if marker_match:
                        latitude = float(marker_match.group(1))
                        longitude = float(marker_match.group(2))
            except Exception:
                pass

        # 4. Fallback: Poll and parse from dynamic page URL
        # Once Google Maps fully loads and pans to the destination, the URL updates
        if latitude == 0.0 or longitude == 0.0:
            for _ in range(20):  # Poll up to 4 seconds
                current_url = page.url
                coord_match = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', current_url)
                if coord_match:
                    lat_val = float(coord_match.group(1))
                    lng_val = float(coord_match.group(2))
                    # Avoid grabbing default Chennai map center coordinates
                    if abs(lat_val - 13.0826802) > 0.01 or abs(lng_val - 80.2707184) > 0.01:
                        latitude = lat_val
                        longitude = lng_val
                        break
                page.wait_for_timeout(200)

        # Name
        name = "Unknown Business"
        try:
            name_elem = page.locator('h1').first
            if name_elem.count() > 0:
                name = name_elem.text_content().strip()
        except Exception:
            pass

        # Address
        address = ""
        try:
            addr_elem = page.locator('button[data-item-id="address"]').first
            if addr_elem.count() > 0:
                address = addr_elem.text_content().strip()
                # Clean prefix label "Address: " if present
                if address.lower().startswith("address:"):
                    address = address[8:].strip()
        except Exception:
            pass

        # Phone
        phone = ""
        try:
            phone_elem = page.locator('button[data-item-id^="phone:tel:"]').first
            if phone_elem.count() > 0:
                phone = phone_elem.text_content().strip()
                if phone.lower().startswith("phone:"):
                    phone = phone[6:].strip()
        except Exception:
            pass

        # Website
        website = ""
        try:
            web_elem = page.locator('a[data-item-id="authority"]').first
            if web_elem.count() > 0:
                website = web_elem.get_attribute('href')
        except Exception:
            pass

        # Rating & Review Count
        rating = 0.0
        reviews = 0
        try:
            rating_block = page.locator('div.F7nice').first
            if rating_block.count() > 0:
                text = rating_block.text_content().strip()
                # Match e.g. "4.5(120)" or "4.5120 reviews"
                match = re.search(r'([1-5]\.\d)\s*\(?([\d,]+)\)?', text)
                if match:
                    rating = float(match.group(1))
                    reviews = int(match.group(2).replace(",", ""))
                else:
                    match_r = re.search(r'([1-5]\.\d)', text)
                    if match_r:
                        rating = float(match_r.group(1))
        except Exception:
            pass

        # Category/Types
        business_types = []
        try:
            # Use multiple robust selectors to find the category button next to ratings
            cat_selectors = [
                'button[jsaction*="category"]',
                'button[class*="D755Mc"]',
                'span.fontBodyMedium button',
                'button[jsaction*="pane.rating.category"]'
            ]
            for selector in cat_selectors:
                cat_elem = page.locator(selector).first
                if cat_elem.count() > 0:
                    cat = cat_elem.text_content().strip()
                    if cat:
                        business_types.append(cat.lower())
                        break
        except Exception:
            pass

        # Business Status (Active Status)
        business_status = "OPERATIONAL"
        try:
            main_pane = page.locator('div[role="main"]').first
            panel_text = main_pane.text_content() if main_pane.count() > 0 else ""
            if not panel_text:
                panel_text = page.locator('body').text_content() or ""
            
            panel_text_lower = panel_text.lower()
            if "permanently closed" in panel_text_lower:
                business_status = "CLOSED_PERMANENTLY"
            elif "temporarily closed" in panel_text_lower:
                business_status = "CLOSED_TEMPORARILY"
        except Exception:
            pass

        # Place ID Hash
        # Attempt to capture Google Place ID from current URL
        place_id = ""
        ftid_match = re.search(r'ftid:(0x[0-9a-fA-F]+)', current_url)
        if ftid_match:
            place_id = f"osm_{ftid_match.group(1)}"
        else:
            place_id = f"scrape_{abs(hash(name + str(latitude) + str(longitude)))}"

        # Parse city/state/country from physical address string
        city = state = country = postal_code = ""
        if address:
            parts = [p.strip() for p in address.split(",")]
            # Filter out empty parts
            parts = [p for p in parts if p]
            
            if parts:
                # 1. Identify country (if last part is India or doesn't have digit/state info)
                if parts[-1].lower() in ["india", "ind"]:
                    country = parts.pop()
                else:
                    country = "India" # default fallback for this app's context
                
                # 2. Find the state/postal code part (usually the last or second-to-last part now)
                # Let's look for a 6-digit zip code
                state_idx = -1
                for idx in range(len(parts) - 1, -1, -1):
                    part = parts[idx]
                    zip_match = re.search(r'\b(\d{5,6})\b', part)
                    if zip_match:
                        postal_code = zip_match.group(1)
                        # State is this part minus the zip code
                        state = part.replace(postal_code, "").strip()
                        state_idx = idx
                        break
                
                # If no postal code found, try to identify state by common names
                if not state and parts:
                    state_names = ["tamil nadu", "tamilnadu", "kerala", "karnataka", "andhra pradesh", "telangana", "maharashtra", "pondicherry", "puducherry"]
                    for idx in range(len(parts) - 1, -1, -1):
                        part_lower = parts[idx].lower()
                        if any(s in part_lower for s in state_names):
                            state = parts[idx]
                            state_idx = idx
                            break
                
                # Default state index if still not found
                if state_idx == -1:
                    state_idx = len(parts) - 1
                    if parts:
                        state = parts[state_idx]

                # Clean state name (remove any trailing/leading symbols)
                if state:
                    state = re.sub(r'[^a-zA-Z\s]', '', state).strip()

                # 3. Identify City (the part immediately to the left of the state)
                city_idx = state_idx - 1
                if city_idx >= 0:
                    city = parts[city_idx]
                elif parts:
                    city = parts[0]
                
                # Clean city name (remove zip codes if any leaked in)
                if city:
                    city = re.sub(r'[^a-zA-Z\s-]', '', city).strip()

        return {
            "place_id": place_id,
            "name": name,
            "full_address": address,
            "city": city,
            "state": state,
            "country": country,
            "postal_code": postal_code,
            "latitude": latitude,
            "longitude": longitude,
            "phone_number": phone,
            "international_phone_number": phone,
            "website": website,
            "maps_url": page.url,
            "rating": rating,
            "total_reviews": reviews,
            "business_status": business_status,
            "opening_hours": None,
            "business_types": business_types,
            "price_level": None,
            "plus_code": None,
            "accessibility": None,
        }
