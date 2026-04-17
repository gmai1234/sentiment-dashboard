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


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


def fetch_url(url, headers=None, timeout=20):
    """Fetch URL with browser-like headers to avoid bot detection."""
    req = urllib.request.Request(url)
    # Always set browser-like headers
    for k, v in BROWSER_HEADERS.items():
        req.add_header(k, v)
    # Override with any custom headers
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def collect_fear_greed():
    """Collect CNN Fear & Greed Index data."""
    print("[1/2] Fetching CNN Fear & Greed Index...")

    # Current score + comparisons
    cnn_headers = {
        "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        "Origin": "https://edition.cnn.com",
    }
    current_url = "https://production.dataviz.cnn.io/index/fearandgreed/current"
    raw = fetch_url(current_url, headers=cnn_headers)
    current = json.loads(raw)

    # Full data with sub-indicators
    graph_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    raw2 = fetch_url(graph_url, headers=cnn_headers)
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
    """Collect AAII Investor Sentiment Survey data.

    Strategy:
    1. Try main survey page for dataChart5 (52-week JS variable)
    2. Try results table page for precise latest values
    3. If both fail, try to preserve existing AAII data from sentiment_data.js
    """
    print("[2/2] Fetching AAII Sentiment Survey...")

    history = []
    precise_latest = None

    # Strategy 1: Main survey page (has 52-week history in JS variable)
    try:
        url = "https://www.aaii.com/sentimentsurvey"
        html = fetch_url(url, headers={"Referer": "https://www.aaii.com/"})
        match = re.search(r"var\s+dataChart5\s*=\s*(\[[\s\S]*?\]);", html)
        if match:
            raw_json = match.group(1)
            raw_json = re.sub(r"(?<!\")spread:", '"spread":', raw_json)
            history = json.loads(raw_json)
            print(f"  -> Got {len(history)} weeks of history from survey page")
        else:
            print("  -> dataChart5 not found in HTML (may require JS rendering)")
    except Exception as e:
        print(f"  -> Survey page fetch failed: {e}")

    # Strategy 2: Results table (simpler HTML, more likely to work)
    try:
        results_url = "https://www.aaii.com/sentimentsurvey/sent_results"
        results_html = fetch_url(
            results_url,
            headers={"Referer": "https://www.aaii.com/sentimentsurvey"},
        )
        rows = re.findall(
            r'<tr[^>]*align="center"[^>]*>\s*'
            r"<td[^>]*>([^<]+)</td>\s*"
            r"<td[^>]*>([^<]+)</td>\s*"
            r"<td[^>]*>([^<]+)</td>\s*"
            r"<td[^>]*>([^<]+)</td>",
            results_html,
        )
        if rows:
            # First row is the latest
            r = rows[0]
            precise_latest = {
                "date": r[0].strip(),
                "bullish": float(r[1].strip()),
                "neutral": float(r[2].strip()),
                "bearish": float(r[3].strip()),
            }
            print(f"  -> Got precise latest from results table: {precise_latest}")

            # If we don't have history from Strategy 1, build partial history from table
            if not history and len(rows) >= 2:
                for row in rows:
                    bull = float(row[1].strip())
                    bear = float(row[3].strip())
                    history.append({
                        "date_": row[0].strip(),
                        "bullish": str(round(bull)),
                        "neutral": str(round(float(row[2].strip()))),
                        "bearish": str(round(bear)),
                        "spread": str(round(bull - bear)),
                        "bullAvg": str(round(bull)),
                        "bearAvg": str(round(bear)),
                    })
                history.reverse()  # oldest first
                print(f"  -> Built {len(history)} rows of history from results table")
    except Exception as e:
        print(f"  -> Results table fetch failed: {e}")

    # Strategy 3: Preserve existing data if we got nothing new
    if not history and not precise_latest:
        try:
            with open("sentiment_data.js", "r", encoding="utf-8") as f:
                existing = f.read()
            match = re.search(r"window\.SENTIMENT_DATA\s*=\s*(\{[\s\S]*\});", existing)
            if match:
                old_data = json.loads(match.group(1))
                if old_data.get("aaii"):
                    print("  -> Preserving existing AAII data (fresh fetch failed)")
                    return old_data["aaii"]
        except Exception:
            pass
        raise ValueError("All AAII collection methods failed and no existing data")

    # Build latest data
    if precise_latest:
        bull = precise_latest["bullish"]
        neut = precise_latest["neutral"]
        bear = precise_latest["bearish"]
        date_str = precise_latest["date"]
    elif history:
        latest = history[-1]
        bull = float(latest.get("bullish", 0))
        neut = float(latest.get("neutral", 0))
        bear = float(latest.get("bearish", 0))
        date_str = latest.get("date_", "")
    else:
        raise ValueError("No AAII data available")

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

    # Check if we got at least one source with new data
    if data["fear_greed"] is None and data["aaii"] is None:
        print("ERROR: Both sources failed. Not overwriting existing data.")
        sys.exit(1)

    # If only one source failed, try to preserve existing data for the other
    if data["fear_greed"] is None or data["aaii"] is None:
        try:
            with open("sentiment_data.js", "r", encoding="utf-8") as f:
                existing = f.read()
            match = re.search(r"window\.SENTIMENT_DATA\s*=\s*(\{[\s\S]*\});", existing)
            if match:
                old = json.loads(match.group(1))
                if data["fear_greed"] is None and old.get("fear_greed"):
                    data["fear_greed"] = old["fear_greed"]
                    print("  -> Preserved existing Fear & Greed data")
                if data["aaii"] is None and old.get("aaii"):
                    data["aaii"] = old["aaii"]
                    print("  -> Preserved existing AAII data")
        except Exception:
            pass

    # Write output
    js_content = "window.SENTIMENT_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    with open("sentiment_data.js", "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"\nDone! sentiment_data.js written ({len(js_content)} bytes)")
    if data["errors"]:
        print(f"Warnings: {data['errors']}")


if __name__ == "__main__":
    main()
