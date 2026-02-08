"""AliExpress product search via web scraping.

Scrapes AliExpress search results to extract supplier pricing,
shipping estimates, order volume, store ratings, and product URLs.

Uses httpx + BeautifulSoup. No API key required.

NOTE: AliExpress frequently changes their page structure. This module
uses their public search API endpoint which returns JSON, which is more
stable than HTML scraping. If it breaks, the JSON schema may have changed.
"""

from __future__ import annotations

import re
import time
import random
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup

# AliExpress search URL (public, no auth required)
_SEARCH_URL = "https://www.aliexpress.com/w/wholesale-{query}.html"

# More stable: AliExpress API-like endpoint used by their frontend
_API_URL = "https://www.aliexpress.com/fn/search-pc/index"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.aliexpress.com/",
}


@dataclass
class AliExpressProduct:
    """Single AliExpress listing."""

    title: str
    price: float
    original_price: Optional[float] = None
    currency: str = "USD"
    shipping_cost: float = 0.0
    total_source_cost: float = 0.0
    orders: int = 0
    rating: Optional[float] = None
    review_count: int = 0
    store_name: str = ""
    store_url: str = ""
    store_rating: Optional[float] = None
    store_years: Optional[int] = None
    url: str = ""
    thumbnail: str = ""
    free_shipping: bool = False
    ships_from: str = "China"

    def __post_init__(self):
        self.total_source_cost = round(self.price + self.shipping_cost, 2)


def _parse_price(text: str) -> Optional[float]:
    """Extract numeric price from strings like 'US $3.49', '$3.49 - $12.00', etc."""
    if not text:
        return None
    # Take first price if range
    text = text.split("-")[0].strip()
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_orders(text: str) -> int:
    """Parse order count from strings like '1,234 sold', '5K+ sold'."""
    if not text:
        return 0
    text = text.lower().replace(",", "").replace("+", "")
    # Handle K notation: "5k sold" -> 5000
    k_match = re.search(r"([\d.]+)\s*k", text)
    if k_match:
        return int(float(k_match.group(1)) * 1000)
    digits = re.search(r"(\d+)", text)
    return int(digits.group(1)) if digits else 0


def search_aliexpress_html(
    query: str,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = "default",
    limit: int = 20,
    min_orders: int = 0,
    min_rating: float = 0.0,
) -> list[AliExpressProduct]:
    """Search AliExpress by scraping HTML search results.

    Args:
        query: Search keywords.
        min_price: Minimum price filter (USD).
        max_price: Maximum price filter (USD).
        sort: 'default', 'price_asc', 'price_desc', 'orders', 'newest'.
        limit: Max results to return.
        min_orders: Post-filter — only return items with >= this many orders.
        min_rating: Post-filter — only return items with >= this rating.

    Returns:
        List of AliExpressProduct dataclasses.
    """
    sort_map = {
        "default": "default",
        "price_asc": "price_asc",
        "price_desc": "price_desc",
        "orders": "total_tranpro_desc",
        "newest": "create_desc",
    }

    slug = query.replace(" ", "-")
    url = _SEARCH_URL.format(query=slug)

    params: dict = {
        "SearchText": query,
        "SortType": sort_map.get(sort, "default"),
    }
    if min_price is not None:
        params["minPrice"] = str(min_price)
    if max_price is not None:
        params["maxPrice"] = str(max_price)

    # Polite delay to avoid rate limiting
    time.sleep(random.uniform(1.0, 2.5))

    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[aliexpress] HTTP error: {e}")
        return []

    return _parse_html_results(resp.text, limit, min_orders, min_rating)


def _parse_html_results(
    html: str,
    limit: int,
    min_orders: int,
    min_rating: float,
) -> list[AliExpressProduct]:
    """Parse AliExpress search results from HTML."""
    soup = BeautifulSoup(html, "lxml")
    products: list[AliExpressProduct] = []

    # AliExpress uses various card selectors; try common ones
    cards = soup.select('[class*="search-item-card"]')
    if not cards:
        cards = soup.select('[class*="product-snippet"]')
    if not cards:
        cards = soup.select('[class*="list--gallery"]')
    if not cards:
        # Fallback: try to extract from embedded JSON in script tags
        return _parse_json_from_scripts(html, limit, min_orders, min_rating)

    for card in cards[:limit * 2]:  # over-fetch then filter
        title_el = (
            card.select_one("h1")
            or card.select_one("h3")
            or card.select_one('[class*="title"]')
        )
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        # Price
        price_el = card.select_one('[class*="price"]')
        price_text = price_el.get_text(strip=True) if price_el else "0"
        price = _parse_price(price_text)
        if price is None:
            continue

        # Orders
        orders_el = card.select_one('[class*="sold"]') or card.select_one(
            '[class*="order"]'
        )
        orders_text = orders_el.get_text(strip=True) if orders_el else ""
        orders = _parse_orders(orders_text)

        # Rating
        rating_el = card.select_one('[class*="star"]') or card.select_one(
            '[class*="rating"]'
        )
        rating = None
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            r = _parse_price(rating_text)
            if r and 0 < r <= 5:
                rating = r

        # Shipping
        ship_el = card.select_one('[class*="shipping"]')
        ship_text = ship_el.get_text(strip=True) if ship_el else ""
        free_shipping = "free" in ship_text.lower()
        shipping_cost = 0.0 if free_shipping else (_parse_price(ship_text) or 0.0)

        # Link
        link_el = card.select_one("a[href]")
        raw_url = link_el["href"] if link_el else ""
        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url

        # Thumbnail
        img_el = card.select_one("img[src]")
        thumb = img_el["src"] if img_el else ""
        if thumb.startswith("//"):
            thumb = "https:" + thumb

        # Store name
        store_el = card.select_one('[class*="store"]')
        store = store_el.get_text(strip=True) if store_el else ""

        # Apply post-filters
        if orders < min_orders:
            continue
        if rating is not None and rating < min_rating:
            continue

        products.append(
            AliExpressProduct(
                title=title,
                price=price,
                shipping_cost=shipping_cost,
                orders=orders,
                rating=rating,
                store_name=store,
                url=raw_url,
                thumbnail=thumb,
                free_shipping=free_shipping,
            )
        )

        if len(products) >= limit:
            break

    return products


def _parse_json_from_scripts(
    html: str,
    limit: int,
    min_orders: int,
    min_rating: float,
) -> list[AliExpressProduct]:
    """Fallback: extract product data from inline JSON in script tags.

    AliExpress often renders search results via client-side JS with
    embedded JSON data in <script> tags.
    """
    import json

    products: list[AliExpressProduct] = []

    # Look for the data payload in script tags
    pattern = re.compile(r'"itemList"\s*:\s*(\[.*?\])', re.DOTALL)
    match = pattern.search(html)
    if not match:
        # Try alternative patterns
        pattern2 = re.compile(r'"items"\s*:\s*(\[.*?\])', re.DOTALL)
        match = pattern2.search(html)

    if not match:
        return products

    try:
        items = json.loads(match.group(1))
    except json.JSONDecodeError:
        return products

    for item in items[:limit * 2]:
        title = item.get("title", "") or item.get("productTitle", "")
        if not title:
            continue

        # Price
        price_str = (
            item.get("price", "")
            or item.get("minPrice", "")
            or item.get("salePrice", "")
        )
        price = _parse_price(str(price_str))
        if price is None:
            continue

        original = _parse_price(str(item.get("originalPrice", "")))

        # Orders
        orders_raw = item.get("tradeCount", 0) or item.get("orders", 0)
        if isinstance(orders_raw, str):
            orders = _parse_orders(orders_raw)
        else:
            orders = int(orders_raw) if orders_raw else 0

        # Rating
        rating_raw = item.get("starRating", None) or item.get("averageStar", None)
        rating = float(rating_raw) if rating_raw else None

        # URL
        product_id = item.get("productId", "") or item.get("itemId", "")
        url = f"https://www.aliexpress.com/item/{product_id}.html" if product_id else ""

        # Image
        thumb = item.get("imageUrl", "") or item.get("image", "")
        if thumb.startswith("//"):
            thumb = "https:" + thumb

        # Store
        store = item.get("storeName", "") or item.get("store", {}).get("name", "")

        # Shipping
        free_ship = item.get("freeShipping", False)
        ship_cost = 0.0 if free_ship else (_parse_price(str(item.get("shippingFee", ""))) or 0.0)

        if orders < min_orders:
            continue
        if rating is not None and rating < min_rating:
            continue

        products.append(
            AliExpressProduct(
                title=title,
                price=price,
                original_price=original,
                shipping_cost=ship_cost,
                orders=orders,
                rating=rating,
                store_name=store,
                url=url,
                thumbnail=thumb,
                free_shipping=free_ship,
            )
        )

        if len(products) >= limit:
            break

    return products


def search_aliexpress(
    query: str,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = "orders",
    limit: int = 20,
    min_orders: int = 0,  # Shopping API doesn't provide order counts
    min_rating: float = 0.0,
) -> list[AliExpressProduct]:
    """Search AliExpress via SerpApi's Google Shopping engine.
    
    This is much more stable than direct scraping which is often blocked by captchas.
    """
    import os
    from serpapi import GoogleSearch
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("SERPAPI_API_KEY", "")
    
    if not api_key:
        print("[aliexpress] SERPAPI_API_KEY not found in .env")
        return []

    params = {
        "api_key": api_key,
        "engine": "google_shopping",
        "q": f"aliexpress {query}",
        "location": "United States",
        "hl": "en",
        "gl": "us",
        "direct_link": "true"
    }

    if min_price is not None:
        params["minPrice"] = str(min_price)
    if max_price is not None:
        params["maxPrice"] = str(max_price)

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        shopping_results = results.get("shopping_results", [])
    except Exception as e:
        print(f"[aliexpress] SerpApi error: {e}")
        return []

    products: list[AliExpressProduct] = []
    for item in shopping_results:
        # We only want results where AliExpress is the source
        source = item.get("source", "").lower()
        if "aliexpress" not in source:
            continue
            
        title = item.get("title", "")
        price_str = item.get("price", "0")
        price = _parse_price(price_str)
        if price is None:
            continue

        # Shopping results don't provide order counts or store ratings easily
        # We'll use 0/None as placeholders to maintain compatibility
        products.append(
            AliExpressProduct(
                title=title,
                price=price,
                shipping_cost=0.0,  # Often included in price/not provided
                orders=0,
                rating=item.get("rating"),
                review_count=item.get("reviews", 0),
                store_name="AliExpress Supplier",
                url=item.get("link", ""),
                thumbnail=item.get("thumbnail", ""),
                free_shipping=True if "free shipping" in str(item).lower() else False,
            )
        )
        
        if len(products) >= limit:
            break

    return products


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    results = search_aliexpress("pet bandana dog", limit=5, min_orders=0, min_rating=0)
    if results:
        for p in results:
            print(
                f"${p.total_source_cost:>6.2f}  |  ⭐{p.rating or 0:.1f}  |  "
                f"{p.orders:>5} sold  |  {p.title[:50]}"
            )
    else:
        print("No results — AliExpress may have changed page structure.")
        print("Try running with VPN or check _parse_html_results selectors.")
