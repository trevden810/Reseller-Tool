"""Cross-platform product matching, margin calculation, and opportunity scoring.

Core logic:
1. Fuzzy-match eBay listings to AliExpress suppliers
2. Calculate real margins after eBay fees, PayPal fees, shipping
3. Score with Google Trends demand velocity
4. Output ranked opportunity table
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import Levenshtein
import pandas as pd

from reseller_tool.ebay import EbayProduct
from reseller_tool.aliexpress import AliExpressProduct

# ---------------------------------------------------------------------------
# Fee constants (eBay US, 2025-2026)
# ---------------------------------------------------------------------------
EBAY_FINAL_VALUE_FEE = 0.1325  # 13.25% for most categories
EBAY_PER_ORDER_FEE = 0.30  # $0.30 per order
PAYPAL_FEE_RATE = 0.029  # 2.9%
PAYPAL_FIXED_FEE = 0.30  # $0.30 per transaction
EBAY_PROMOTED_LISTING_FEE = 0.03  # 3% avg if using promoted listings (optional)


@dataclass
class MarginResult:
    """Calculated margin for a single eBay ↔ AliExpress pair."""

    ebay_title: str
    ali_title: str
    ebay_sell_price: float
    ebay_shipping_income: float  # what buyer pays for shipping
    ali_source_cost: float  # product + shipping from supplier
    ebay_fee: float
    payment_fee: float
    promoted_fee: float
    total_cost: float
    net_profit: float
    margin_pct: float
    roi_pct: float  # profit / source_cost — how hard your dollar works

    # Metadata for scoring
    ali_orders: int = 0
    ali_rating: Optional[float] = None
    ebay_sold_count: Optional[int] = None
    trend_score: Optional[float] = None  # 0-100 from Google Trends
    composite_score: float = 0.0

    ebay_url: str = ""
    ali_url: str = ""
    ebay_thumbnail: str = ""
    ali_thumbnail: str = ""

    match_confidence: float = 0.0  # 0-1 Levenshtein similarity


def calculate_margin(
    sell_price: float,
    source_cost: float,
    shipping_income: float = 0.0,
    use_promoted: bool = False,
) -> dict:
    """Calculate net margin after all fees.

    Args:
        sell_price: What the eBay buyer pays for the item.
        source_cost: Total cost from AliExpress (product + shipping).
        shipping_income: What you charge buyer for shipping (often $0 if free shipping).
        use_promoted: Include eBay promoted listing fee.

    Returns:
        Dict with fee breakdown and net profit.
    """
    gross_revenue = sell_price + shipping_income

    # eBay final value fee on total amount
    ebay_fee = (gross_revenue * EBAY_FINAL_VALUE_FEE) + EBAY_PER_ORDER_FEE

    # Payment processing fee
    payment_fee = (gross_revenue * PAYPAL_FEE_RATE) + PAYPAL_FIXED_FEE

    # Optional promoted listing
    promoted_fee = gross_revenue * EBAY_PROMOTED_LISTING_FEE if use_promoted else 0.0

    total_cost = source_cost + ebay_fee + payment_fee + promoted_fee
    net_profit = gross_revenue - total_cost
    margin_pct = (net_profit / gross_revenue * 100) if gross_revenue > 0 else 0.0
    roi_pct = (net_profit / source_cost * 100) if source_cost > 0 else 0.0

    return {
        "ebay_fee": round(ebay_fee, 2),
        "payment_fee": round(payment_fee, 2),
        "promoted_fee": round(promoted_fee, 2),
        "total_cost": round(total_cost, 2),
        "net_profit": round(net_profit, 2),
        "margin_pct": round(margin_pct, 1),
        "roi_pct": round(roi_pct, 1),
    }


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    """Normalize product title for better matching."""
    t = title.lower()
    # Remove common noise words
    noise = [
        "free shipping", "hot sale", "new", "2024", "2025", "2026",
        "high quality", "best", "top", "wholesale", "lot", "us stock",
        "fast ship", "usa seller", "brand new", "factory", "direct",
    ]
    for word in noise:
        t = t.replace(word, "")
    # Remove special chars, collapse whitespace
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def match_products(
    ebay_products: list[EbayProduct],
    ali_products: list[AliExpressProduct],
    min_similarity: float = 0.40,
) -> list[tuple[EbayProduct, AliExpressProduct, float]]:
    """Match eBay listings to AliExpress products using fuzzy title matching.

    Args:
        ebay_products: eBay listings (sell side).
        ali_products: AliExpress listings (source side).
        min_similarity: Minimum Levenshtein ratio to consider a match (0-1).

    Returns:
        List of (ebay_product, ali_product, similarity_score) tuples,
        sorted by similarity descending.
    """
    matches: list[tuple[EbayProduct, AliExpressProduct, float]] = []
    used_ali: set[int] = set()  # prevent duplicate matching

    for ep in ebay_products:
        ep_norm = _normalize_title(ep.title)
        best_match: Optional[tuple[AliExpressProduct, float]] = None
        best_idx = -1

        for i, ap in enumerate(ali_products):
            if i in used_ali:
                continue
            ap_norm = _normalize_title(ap.title)
            sim = Levenshtein.ratio(ep_norm, ap_norm)

            if sim >= min_similarity and (best_match is None or sim > best_match[1]):
                best_match = (ap, sim)
                best_idx = i

        if best_match is not None:
            matches.append((ep, best_match[0], best_match[1]))
            used_ali.add(best_idx)

    matches.sort(key=lambda x: x[2], reverse=True)
    return matches


# ---------------------------------------------------------------------------
# Google Trends integration
# ---------------------------------------------------------------------------

def get_trend_score(keyword: str, timeframe: str = "today 3-m") -> Optional[float]:
    """Get Google Trends interest score (0-100) for a keyword.

    Returns the average interest over the timeframe, or None on failure.
    Uses pytrends (unofficial Google Trends API).

    Args:
        keyword: Search term.
        timeframe: 'today 1-m', 'today 3-m', 'today 12-m', etc.

    Returns:
        Average interest score 0-100, or None.
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360)
        pytrends.build_payload([keyword], timeframe=timeframe, geo="US")
        df = pytrends.interest_over_time()

        if df.empty:
            return None

        return round(df[keyword].mean(), 1)
    except Exception:
        return None


def get_trend_velocity(keyword: str) -> Optional[float]:
    """Calculate trend velocity: is demand growing or shrinking?

    Compares last 30 days average to prior 60 days average.
    Returns percentage change. Positive = growing.
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360)
        pytrends.build_payload([keyword], timeframe="today 3-m", geo="US")
        df = pytrends.interest_over_time()

        if df.empty or len(df) < 30:
            return None

        recent = df[keyword].tail(30).mean()
        prior = df[keyword].head(len(df) - 30).mean()

        if prior == 0:
            return None

        velocity = ((recent - prior) / prior) * 100
        return round(velocity, 1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def score_opportunity(
    margin_pct: float,
    roi_pct: float,
    ali_orders: int,
    ali_rating: Optional[float],
    trend_score: Optional[float],
    match_confidence: float,
) -> float:
    """Score a product opportunity 0-100.

    Weights:
        - Margin %:          25%  (profitability)
        - ROI %:             15%  (capital efficiency)
        - AliExpress orders: 20%  (supplier demand validation)
        - Ali rating:        10%  (supplier quality)
        - Trend score:       20%  (market demand)
        - Match confidence:  10%  (data quality)
    """
    # Normalize each factor to 0-100 scale
    margin_norm = min(max(margin_pct, 0), 60) / 60 * 100
    roi_norm = min(max(roi_pct, 0), 300) / 300 * 100
    orders_norm = min(ali_orders / 500, 1.0) * 100  # 500+ orders = max
    rating_norm = ((ali_rating or 0) / 5.0) * 100
    trend_norm = trend_score if trend_score is not None else 50  # default neutral
    match_norm = match_confidence * 100

    score = (
        margin_norm * 0.25
        + roi_norm * 0.15
        + orders_norm * 0.20
        + rating_norm * 0.10
        + trend_norm * 0.20
        + match_norm * 0.10
    )

    return round(min(score, 100), 1)


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------

def analyze_opportunities(
    ebay_products: list[EbayProduct],
    ali_products: list[AliExpressProduct],
    keyword: str = "",
    min_similarity: float = 0.40,
    use_promoted: bool = False,
    include_trends: bool = True,
) -> pd.DataFrame:
    """Full analysis pipeline: match → margin → score → rank.

    Args:
        ebay_products: eBay search results.
        ali_products: AliExpress search results.
        keyword: Search keyword for Google Trends scoring.
        min_similarity: Minimum fuzzy match threshold.
        use_promoted: Include eBay promoted listing fee.
        include_trends: Fetch Google Trends data (adds ~2s per query).

    Returns:
        DataFrame sorted by composite_score descending.
    """
    matches = match_products(ebay_products, ali_products, min_similarity)

    if not matches:
        return pd.DataFrame()

    # Google Trends (one call for the keyword)
    trend = None
    if include_trends and keyword:
        trend = get_trend_score(keyword)

    rows: list[dict] = []
    for ep, ap, similarity in matches:
        margin = calculate_margin(
            sell_price=ep.price,
            source_cost=ap.total_source_cost,
            shipping_income=ep.shipping,
            use_promoted=use_promoted,
        )

        # Skip negative margin opportunities
        if margin["net_profit"] <= 0:
            continue

        composite = score_opportunity(
            margin_pct=margin["margin_pct"],
            roi_pct=margin["roi_pct"],
            ali_orders=ap.orders,
            ali_rating=ap.rating,
            trend_score=trend,
            match_confidence=similarity,
        )

        rows.append(
            {
                "ebay_title": ep.title,
                "ali_title": ap.title,
                "ebay_price": ep.price,
                "ali_cost": ap.total_source_cost,
                "ebay_fee": margin["ebay_fee"],
                "payment_fee": margin["payment_fee"],
                "promoted_fee": margin["promoted_fee"],
                "net_profit": margin["net_profit"],
                "margin_pct": margin["margin_pct"],
                "roi_pct": margin["roi_pct"],
                "ali_orders": ap.orders,
                "ali_rating": ap.rating,
                "trend_score": trend,
                "match_confidence": round(similarity, 2),
                "composite_score": composite,
                "ebay_url": ep.url,
                "ali_url": ap.url,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    return df


def quick_margin_check(sell_price: float, source_cost: float) -> str:
    """One-liner margin check for quick CLI use."""
    m = calculate_margin(sell_price, source_cost)
    verdict = "✅ GO" if m["margin_pct"] >= 20 else "⚠️ THIN" if m["margin_pct"] >= 10 else "❌ SKIP"
    return (
        f"{verdict}  |  Sell: ${sell_price:.2f}  |  Source: ${source_cost:.2f}  |  "
        f"Profit: ${m['net_profit']:.2f}  |  Margin: {m['margin_pct']}%  |  ROI: {m['roi_pct']}%"
    )


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Standalone margin checks
    print(quick_margin_check(sell_price=24.99, source_cost=5.50))
    print(quick_margin_check(sell_price=12.99, source_cost=8.00))
    print(quick_margin_check(sell_price=9.99, source_cost=7.50))
