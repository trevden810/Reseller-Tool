"""eBay product search via SerpApi.

Returns structured product data including title, price, condition,
shipping cost, seller info, and listing URL.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from serpapi import EbaySearch

load_dotenv()

from functools import lru_cache

@lru_cache(maxsize=1)
def get_api_key() -> str:
    """Load API key from Streamlit secrets (cloud) or .env (local)."""
    # 1. Try Streamlit secrets (cloud)
    try:
        import streamlit as st
        if "SERPAPI_API_KEY" in st.secrets:
            return st.secrets["SERPAPI_API_KEY"]
    except Exception:
        pass

    # 2. Fallback to env var (local)
    return os.getenv("SERPAPI_API_KEY", "")


@dataclass
class EbayProduct:
    """Single eBay listing."""

    title: str
    price: float
    currency: str = "USD"
    condition: str = "Unknown"
    shipping: float = 0.0
    total_cost: float = 0.0
    seller: str = ""
    seller_rating: Optional[float] = None
    sold_count: Optional[int] = None
    url: str = ""
    thumbnail: str = ""
    extensions: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.total_cost = round(self.price + self.shipping, 2)


def search_ebay(
    query: str,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    condition: Optional[str] = None,
    sort: str = "best_match",
    limit: int = 20,
) -> list[EbayProduct]:
    """Search eBay via SerpApi and return structured product list.

    Args:
        query: Search keywords.
        min_price: Floor price filter.
        max_price: Ceiling price filter.
        condition: 'new', 'used', or None for all.
        sort: 'best_match', 'price_asc', 'price_desc', 'ending_soonest', 'newly_listed'.
        limit: Max results to return (capped at 60 per page).

    Returns:
        List of EbayProduct dataclasses.
    """
    if not get_api_key():
        raise ValueError(
            "SERPAPI_API_KEY not set. Get a free key at https://serpapi.com"
        )

    sort_map = {
        "best_match": "12",
        "price_asc": "15",
        "price_desc": "16",
        "ending_soonest": "1",
        "newly_listed": "10",
    }

    condition_map = {
        "new": "3",
        "used": "4",
    }

    params: dict = {
        "api_key": get_api_key(),
        "engine": "ebay",
        "_nkw": query,
        "ebay_domain": "ebay.com",
        "_sop": sort_map.get(sort, "BestMatch"),
    }

    if min_price is not None:
        params["_udlo"] = str(min_price)
    if max_price is not None:
        params["_udhi"] = str(max_price)
    if condition and condition.lower() in condition_map:
        params["LH_ItemCondition"] = condition_map[condition.lower()]

    search = EbaySearch(params)
    results = search.get_dict()
    organic = results.get("organic_results", [])

    products: list[EbayProduct] = []
    for i, item in enumerate(organic[:limit]):
        price_raw = item.get("price", {})
        if isinstance(price_raw, dict):
            price_val = price_raw.get("raw", "0")
            currency = price_raw.get("currency", "USD")
        else:
            price_val = str(price_raw)
            currency = "USD"

        # robust price extraction
        # removes currency symbols and text, keeps digits and decimals
        try:
            # Match the first occurence of a number like 12.99 or 1,200.50
            # We remove commas first to simplify float parsing
            price_str_clean = str(price_val).replace(",", "")
            match = re.search(r"(\d+\.?\d*)", price_str_clean)
            if match:
                price_num = float(match.group(1))
            else:
                continue
        except (ValueError, TypeError):
            continue

        # Shipping
        shipping_raw = item.get("shipping", "")
        shipping_cost = 0.0
        if isinstance(shipping_raw, str):
            if "free" in shipping_raw.lower():
                shipping_cost = 0.0
            else:
                # Extract first number found
                match_ship = re.search(r"(\d+\.?\d*)", str(shipping_raw).replace(",", ""))
                if match_ship:
                    shipping_cost = float(match_ship.group(1))

        # Seller info
        seller_info = item.get("seller_info", {})
        if isinstance(seller_info, dict):
            seller_name = seller_info.get("name", "")
            seller_pct = seller_info.get("positive_feedback_percent")
        else:
            seller_name = str(seller_info)
            seller_pct = None

        # Sold count from extensions
        extensions = item.get("extensions", [])
        sold = None
        for ext in extensions:
            if "sold" in str(ext).lower():
                digits = "".join(c for c in str(ext) if c.isdigit())
                if digits:
                    sold = int(digits)
                break

        products.append(
            EbayProduct(
                title=item.get("title", ""),
                price=price_num,
                currency=currency,
                condition=item.get("condition", "Unknown"),
                shipping=shipping_cost,
                seller=seller_name,
                seller_rating=seller_pct,
                sold_count=sold,
                url=item.get("link", ""),
                thumbnail=item.get("thumbnail", ""),
                extensions=extensions,
            )
        )

    return products


def search_ebay_sold(query: str, limit: int = 20) -> list[EbayProduct]:
    """Search eBay SOLD/completed listings to validate actual demand.

    This is critical for dropshipping — it shows what people actually
    bought, not just what's listed.
    """
    if not get_api_key():
        raise ValueError("SERPAPI_API_KEY not set.")

    params = {
        "api_key": get_api_key(),
        "engine": "ebay",
        "_nkw": query,
        "ebay_domain": "ebay.com",
        "LH_Complete": "1",
        "LH_Sold": "1",
        "_sop": "EndTimeSoonest",
    }

    search = EbaySearch(params)
    results = search.get_dict()
    organic = results.get("organic_results", [])

    products: list[EbayProduct] = []
    for item in organic[:limit]:
        price_raw = item.get("price", {})
        if isinstance(price_raw, dict):
            price_val = price_raw.get("raw", "0")
        else:
            price_val = str(price_raw)

        price_clean = (
            str(price_val).replace("$", "").replace(",", "").strip()
        )
        try:
            price_num = float(price_clean)
        except (ValueError, TypeError):
            continue

        products.append(
            EbayProduct(
                title=item.get("title", ""),
                price=price_num,
                condition=item.get("condition", "Unknown"),
                url=item.get("link", ""),
                thumbnail=item.get("thumbnail", ""),
            )
        )

    return products


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    results = search_ebay("pet bandana dog", limit=5)
    for p in results:
        print(f"${p.total_cost:>7.2f}  |  {p.title[:60]}")
