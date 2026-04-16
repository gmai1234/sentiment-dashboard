#!/usr/bin/env python3
"""
Sentiment Dashboard Data Collector
- CNN Fear & Greed Index (current + historical comparisons)
- CNN Fear & Greed Sub-indicators (7 components)
- AAII Investor Sentiment Survey (latest + 52-week history)

Outputs: sentiment_data.js (window.SENTIMENT_DATA = {...})
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone


def fetch_url(url, headers=None, timeout=15):
    """Fetch URL with optional headers."""
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def collect_fear_greed():
    """Collect CNN Fear & Greed Index data."""
    print("[1/2] Fetching CNN Fear & Greed Index...")

    # Current score + comparisons
    current_url = "https://production.dataviz.cnn.io/index/fearandgreed/current"
    raw = fetch_url(current_url, headers={"User-Agent": "Mozilla/5.0"})
    current = json.loads(raw)

    # Full data with sub-indicators
    graph_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    raw2 = fetch_url(graph_url, headers={"User-Agent": "Mozilla/5.0"})
    graph = json.loads(raw2)

    # Extract sub-indicators
    sub_keys = [
        ("market_momentum_sp500", "Market Momentum (S&P 500)"),
        ("stock_price_strength", "Stock Price Strength"),
        ("stock_price_breadth", "Stock Price Breadth"),
        ("put_call_options", "Put/Call Options"),
        ("market_volatility_vix", "Market Volatility (VIX)"),
        ("junk_bond_demand", "Junk Bond Demand"),
        ("safe_haven_demand", "Safe Haven Demand"),
    ]
    sub_indicators = []
    for key, label in sub_keys:
        if key in graph:
            item = graph[key]
            sub_indicators.append({
                "name": label,
                "score": round(item.get("score", 0), 2),
                "rating": item.get("rating", ""),
            })

    # Extract historical time series (last 90 days for chart)
    history = []
    fg_hist = graph.get("fear_and_greed_historical", {})
    if "data" in fg_hist:
        for point in fg_hist["data"][-90:]:
            history.append({
                "date": datetime.fromtimestamp(
                    point["x"] / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d"),
                "score": round(point["y"], 1),
                "rating": point.get("rating", ""),
            })

    result = {
        "score": round(current.get("score", 0), 1),
        "rating": current.get("rating", ""),
        "timestamp": current.get("timestamp", ""),
        "previous_close": round(current.get("previous_close", 0), 1),
        "previous_1_week": round(current.get("previous_1_week", 0), 1),
        "previous_1_month": round(current.get("previous_1_month", 0), 1),
        "previous_1_year": round(current.get("previous_1_year", 0), 1),
        "sub_indicators": sub_indicators,
        "history": history,
    }
    print(f"  -> Score: {result['score']} ({result['rating']})")
    return result


def collect_aaii():
    """Collect AAII Investor Sentiment Survey data."""
    print("[2/2] Fetching AAII Sentiment Survey...")

    url = "https://www.aaii.com/sentimentsurvey"
    html = fetch_url(url, headers={"User-Agent": "Mozilla/5.0"})

    # Extract dataChart5 array (52-week history)
    match = re.search(r"var\s+dataChart5\s*=\s*(\[[\s\S]*?\]);", html)
    if not match:
        raise ValueError("Could not find dataChart5 in AAII page")

    raw_json = match.group(1)
    # Fix unquoted 'spread:' key
    raw_json = re.sub(r"(?<!\")spread:", '"spread":', raw_json)
    history = json.loads(raw_json)

    # Get latest entry
    latest = history[-1] if history else {}

    # Also try to get more precise values from the results table
    precise_latest = None
    try:
        results_url = "https://www.aaii.com/sentimentsurvey/sent_results"
        results_html = fetch_url(results_url, headers={"User-Agent": "Mozilla/5.0"})
        # Parse first data row from results table
        row_match = re.search(
            r'<tr[^>]*align="center"[^>]*>\s*<td[^>]*>([^<]+)</td>\s*'
            r"<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>",
            results_html,
        )
        if row_match:
            precise_latest = {
                "date": row_match.group(1).strip(),
                "bullish": float(row_match.group(2).strip()),
                "neutral": float(row_match.group(3).strip()),
                "bearish": float(row_match.group(4).strip()),
            }
    except Exception as e:
        print(f"  -> Precise table fetch failed (using chart data): {e}")

    # Build latest data (prefer precise if available)
    if precise_latest:
        bull = precise_latest["bullish"]
        neut = precise_latest["neutral"]
        bear = precise_latest["bearish"]
        date_str = precise_latest["date"]
    else:
        bull = float(latest.get("bullish", 0))
        neut = float(latest.get("neutral", 0))
        bear = float(latest.get("bearish", 0))
        date_str = latest.get("date_", "")

    # Build history array
    hist_arr = []
    for item in history:
        hist_arr.append({
            "date": item.get("date_", ""),
            "bullish": float(item.get("bullish", 0)),
            "neutral": float(item.get("neutral", 0)),
            "bearish": float(item.get("bearish", 0)),
            "spread": float(item.get("spread", 0)),
            "bull_avg": float(item.get("bullAvg", 0)),
            "bear_avg": float(item.get("bearAvg", 0)),
        })

    result = {
        "latest": {
            "date": date_str,
            "bullish": round(bull, 1),
            "neutral": round(neut, 1),
            "bearish": round(bear, 1),
            "spread": round(bull - bear, 1),
        },
        "history": hist_arr,
    }
    print(f"  -> Bull: {bull}%, Neutral: {neut}%, Bear: {bear}%")
    return result


def main():
    data = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fear_greed": None,
        "aaii": None,
        "errors": [],
    }

    # Collect Fear & Greed
    try:
        data["fear_greed"] = collect_fear_greed()
    except Exception as e:
        err = f"Fear & Greed collection failed: {e}"
        print(f"  !! {err}")
        data["errors"].append(err)

    # Collect AAII
    try:
        data["aaii"] = collect_aaii()
    except Exception as e:
        err = f"AAII collection failed: {e}"
        print(f"  !! {err}")
        data["errors"].append(err)

    # Check if we got at least one source
    if data["fear_greed"] is None and data["aaii"] is None:
        print("ERROR: Both sources failed. Not overwriting existing data.")
        sys.exit(1)

    # Write output
    js_content = "window.SENTIMENT_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    with open("sentiment_data.js", "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"\nDone! sentiment_data.js written ({len(js_content)} bytes)")
    if data["errors"]:
        print(f"Warnings: {data['errors']}")


if __name__ == "__main__":
    main()
