"""Quick diagnostic for SerpApi eBay search."""

import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("SERPAPI_API_KEY", "")
print(f"API key loaded: {'YES (' + key[:8] + '...)' if key else 'NO — key is empty'}")

if not key:
    print("\nFix: Make sure .env contains SERPAPI_API_KEY=your_actual_key")
    exit(1)

# Test 1: Raw serpapi call
print("\n--- Test 1: Basic eBay search via serpapi ---")
try:
    from serpapi import EbaySearch

    params = {
        "api_key": key,
        "engine": "ebay",
        "_nkw": "pet bandana",
        "ebay_domain": "ebay.com",
        "_sop": "12",  # Best Match
    }
    search = EbaySearch(params)
    results = search.get_dict()

    if "error" in results:
        print(f"API ERROR: {results['error']}")
    else:
        organic = results.get("organic_results", [])
        print(f"Results found: {len(organic)}")
        for item in organic[:3]:
            title = item.get("title", "?")
            price = item.get("price", "?")
            try:
                print(f"  - {title[:60]} | {price}")
            except UnicodeEncodeError:
                print(f"  - {title[:60].encode('ascii', 'replace').decode()} | {price}")

    # Dump full response keys for debugging
    print(f"\nResponse keys: {list(results.keys())}")

except Exception as e:
    print(f"Exception: {e}")

# Test AliExpress via Google Shopping
print("\n--- Test 2: AliExpress search via Google Shopping ---")
try:
    from serpapi import GoogleSearch
    params_shopping = {
        "api_key": key,
        "engine": "google_shopping",
        "q": "aliexpress pet bandana",
        "direct_link": "true"
    }
    search_shopping = GoogleSearch(params_shopping)
    results_shopping = search_shopping.get_dict()
    shopping_results = results_shopping.get("shopping_results", [])
    
    ali_matches = [r for r in shopping_results if "aliexpress" in r.get("source", "").lower()]
    print(f"AliExpress matches found: {len(ali_matches)}")
    for item in ali_matches[:3]:
        print(f"  - {item.get('title', '?')[:60]} | {item.get('price', '?')}")

except Exception as e:
    print(f"Exception: {e}")
