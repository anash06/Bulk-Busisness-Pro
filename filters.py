"""
Filtering logic for retrieved businesses.
Applies criteria like rating, review counts, status, presence of phone/website, price, type, and keyword matching.
"""

from typing import List, Dict, Any

def apply_filters(businesses: List[Dict[str, Any]], criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filters a list of business dictionaries based on specified criteria.
    
    criteria dict structure:
      - 'min_rating': float or None
      - 'max_rating': float or None
      - 'min_reviews': int or None
      - 'business_status': str or None (e.g. 'OPERATIONAL', 'CLOSED_TEMPORARILY', 'CLOSED_PERMANENTLY', 'All')
      - 'open_now': bool or None
      - 'has_phone': bool or None
      - 'has_website': bool or None
      - 'price_levels': List[int] or None (e.g., [1, 2] out of 0,1,2,3,4)
      - 'business_type': str or None (e.g., 'restaurant', 'All')
      - 'include_keyword': str or None (matches name, address, or types)
      - 'exclude_keyword': str or None (excludes match in name, address, or types)
    """
    filtered = []

    for biz in businesses:
        # 1. Rating
        rating = biz.get("rating")
        min_rating = criteria.get("min_rating")
        max_rating = criteria.get("max_rating")
        
        if min_rating is not None:
            if rating is None or rating < min_rating:
                continue
        if max_rating is not None:
            if rating is None or rating > max_rating:
                continue

        # 2. Reviews Count
        reviews = biz.get("total_reviews") or 0
        min_reviews = criteria.get("min_reviews")
        if min_reviews is not None:
            if reviews < min_reviews:
                continue

        # 3. Business Status
        status = biz.get("business_status")
        target_status = criteria.get("business_status", "All")
        if target_status and target_status != "All":
            if not status or status.upper() != target_status.upper():
                continue

        # 4. Open Now
        open_now_val = criteria.get("open_now")
        if open_now_val:
            opening_hours = biz.get("opening_hours")
            if not opening_hours or not opening_hours.get("open_now"):
                continue

        # 5. Has Phone Number
        if criteria.get("has_phone"):
            phone = biz.get("phone_number")
            if not phone or phone.strip() == "":
                continue

        # 6. Has Website
        if criteria.get("has_website"):
            website = biz.get("website")
            if not website or website.strip() == "":
                continue

        # 7. Price Levels
        price_levels = criteria.get("price_levels")
        if price_levels is not None and len(price_levels) > 0:
            price = biz.get("price_level")
            # If price level is None, it means unspecified. We skip it if specific price levels are requested.
            if price is None or price not in price_levels:
                continue

        # 8. Business Type
        target_type = criteria.get("business_type", "All")
        if target_type and target_type != "All":
            types = biz.get("business_types") or []
            if target_type.lower() not in [t.lower() for t in types]:
                continue

        # 9. Include Keyword
        include_kw = criteria.get("include_keyword")
        if include_kw:
            kw = include_kw.lower().strip()
            name = (biz.get("name") or "").lower()
            addr = (biz.get("full_address") or "").lower()
            types = [t.lower() for t in (biz.get("business_types") or [])]
            
            # Check if keyword matches name, address, or any of its types
            matches_name = kw in name
            matches_addr = kw in addr
            matches_types = any(kw in t for t in types)

            if not (matches_name or matches_addr or matches_types):
                continue

        # 10. Exclude Keyword
        exclude_kw = criteria.get("exclude_keyword")
        if exclude_kw:
            kw = exclude_kw.lower().strip()
            name = (biz.get("name") or "").lower()
            addr = (biz.get("full_address") or "").lower()
            types = [t.lower() for t in (biz.get("business_types") or [])]
            
            matches_name = kw in name
            matches_addr = kw in addr
            matches_types = any(kw in t for t in types)

            if matches_name or matches_addr or matches_types:
                continue

        filtered.append(biz)

    return filtered
