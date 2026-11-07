#!/usr/bin/env python3

import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = "http://electricinsights.co.uk/api/1/{kind}?date_from={{date_from}}&date_to={{date_to}}&group_by=30m"

PRICE_API = BASE.format(kind="prices")
EMISSIONS_API = BASE.format(kind="emissions")
GENERATION_API = BASE.format(kind="generation")

HISTORY_FILE = Path("history.json")
PRICE_FILE = Path("price.json")

EMISSIONS_HISTORY_FILE = Path("emissions_history.json")
EMISSIONS_FILE = Path("emissions.json")

GENERATION_HISTORY_FILE = Path("generation_history.json")
GENERATION_FILE = Path("generation.json")

MAX_DAYS = 30


def fetch_api(url_template, date_from, date_to):
    url = url_template.format(date_from=date_from, date_to=date_to)
    request = urllib.request.Request(
        url, headers={"User-Agent": "Electrical data collector"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def periods(item):
    """API periods are shifted by 30 minutes for display (as before)."""
    start = datetime.fromisoformat(item["start"]) + timedelta(minutes=30)
    end = datetime.fromisoformat(item["end"]) + timedelta(minutes=30)
    return {
        "display_period": {"start": start.isoformat(), "end": end.isoformat()},
        "api_period": {"start": item["start"], "end": item["end"]},
    }


def make_price_record(item, collected_at):
    return {
        "price": round(float(item["value"]), 2),
        "currency": "GBP",
        "unit": "MWh",
        **periods(item),
        "collected_at": collected_at.isoformat(),
        "source": "Electric Insights",
    }


def make_emissions_record(item, collected_at):
    return {
        "emissions": round(float(item["value"]["totalInGperkWh"]), 2),
        "unit": "gCO2/kWh",
        **periods(item),
        "collected_at": collected_at.isoformat(),
        "source": "Electric Insights",
    }


# Generation comes from Elexon's open API (no key). Times are true period
# times. If the mix looks one step out of line with price/emissions on the
# page, change this to 30 (or -30).
GEN_SHIFT_MINUTES = 0

ELEXON_FUELHH = (
    "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH"
    "?settlementDateFrom={d1}&settlementDateTo={d2}&format=json"
)

FUEL_NAMES = {
    "BIOMASS": "Biomass",
    "CCGT": "Gas",
    "OCGT": "Gas",
    "COAL": "Coal",
    "NUCLEAR": "Nuclear",
    "NPSHYD": "Hydro",
    "WIND": "Wind",
    "PS": "Pumped Storage",
    "OIL": "Oil",
    "OTHER": "Biomass",  # matches Electric Insights (07:00: 3248+217 = 3.47 GW)
}


def fuel_name(code):
    if code.startswith("INT"):
        return "Imports & Exports"
    return FUEL_NAMES.get(code, code.title())


def make_generation_record(item, collected_at):
    shift = timedelta(minutes=GEN_SHIFT_MINUTES)
    start = datetime.fromisoformat(item["start"]) + shift
    end = datetime.fromisoformat(item["end"]) + shift
    return {
        "generation": item["value"],
        "unit": "MW",
        "display_period": {"start": start.isoformat(), "end": end.isoformat()},
        "api_period": {"start": item["start"], "end": item["end"]},
        "collected_at": collected_at.isoformat(),
        "source": "Elexon BMRS (FUELHH)",
    }


def load_json(path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def trim_history(history, now):
    cutoff = now - timedelta(days=MAX_DAYS)
    history = [
        item for item in history
        if datetime.fromisoformat(item["display_period"]["start"]) >= cutoff
    ]
    history.sort(key=lambda item: item["display_period"]["start"])
    return history


def build_history(items, maker, now):
    records = []
    for item in items:
        record = maker(item, now)
        start = datetime.fromisoformat(record["display_period"]["start"])
        if start <= now:
            records.append(record)
    return trim_history(records, now)


def merge_latest(history_file, latest_file, record, now):
    history = load_json(history_file)
    period = record["display_period"]["start"]
    history = [
        item for item in history
        if item.get("display_period", {}).get("start") != period
    ]
    history.append(record)
    history = trim_history(history, now)
    save_json(history_file, history)
    save_json(latest_file, record)
    return history


def last_completed(items, now):
    done = [
        item for item in items
        if datetime.fromisoformat(item["start"]) + timedelta(minutes=30) <= now
    ]
    return done[-1] if done else None


def fetch_generation(date_from, date_to):
    """Optional: a failure here must not stop price/emissions."""
    try:
        d1 = datetime.fromisoformat(date_from).date()
        d2 = datetime.fromisoformat(date_to).date()
        rows = {}
        cur = d1
        while cur <= d2:  # fetch in 7-day chunks
            end = min(cur + timedelta(days=6), d2)
            url = ELEXON_FUELHH.format(d1=cur.isoformat(), d2=end.isoformat())
            req = urllib.request.Request(
                url, headers={"User-Agent": "Electrical data collector"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8")).get("data", [])
            for r in data:
                rows[(r["startTime"], r["fuelType"])] = r
            cur = end + timedelta(days=1)

        by_start = {}
        for (start, code), r in rows.items():
            mix = by_start.setdefault(start, {})
            name = fuel_name(code)
            mix[name] = mix.get(name, 0) + (r.get("generation") or 0)

        items = []
        for start in sorted(by_start):
            s0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
            items.append({
                "start": s0.isoformat(),
                "end": (s0 + timedelta(minutes=30)).isoformat(),
                "value": by_start[start],
            })
        if not items:
            print("Warning: no generation records returned")
        return items
    except Exception as err:
        print(f"Warning: generation fetch failed: {err}")
        return []


def refresh_history(now):
    start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Refreshing 30 days: {start_date} to {end_date}")

    prices = fetch_api(PRICE_API, start_date, end_date)
    emissions = fetch_api(EMISSIONS_API, start_date, end_date)
    generation = fetch_generation(start_date, end_date)

    if not prices:
        raise RuntimeError("No price records returned")
    if not emissions:
        raise RuntimeError("No emissions records returned")

    price_history = build_history(prices, make_price_record, now)
    emissions_history = build_history(emissions, make_emissions_record, now)
    generation_history = build_history(generation, make_generation_record, now)

    save_json(HISTORY_FILE, price_history)
    save_json(EMISSIONS_HISTORY_FILE, emissions_history)

    if price_history:
        save_json(PRICE_FILE, price_history[-1])
    if emissions_history:
        save_json(EMISSIONS_FILE, emissions_history[-1])

    if generation_history:
        save_json(GENERATION_HISTORY_FILE, generation_history)
        save_json(GENERATION_FILE, generation_history[-1])

    print(f"Price history records: {len(price_history)}")
    print(f"Emissions history records: {len(emissions_history)}")
    print(f"Generation history records: {len(generation_history)}")

    if generation_history:
        print("\nLatest generation:")
        print(json.dumps(generation_history[-1], indent=2))


def update_latest(now):
    date_from = now.strftime("%Y-%m-%d")
    date_to = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    prices = fetch_api(PRICE_API, date_from, date_to)
    emissions = fetch_api(EMISSIONS_API, date_from, date_to)
    generation = fetch_generation(date_from, date_to)

    if not prices:
        raise RuntimeError("No price records returned")
    if not emissions:
        raise RuntimeError("No emissions records returned")

    price_item = last_completed(prices, now)
    emissions_item = last_completed(emissions, now)

    if not price_item:
        raise RuntimeError("No completed price period available")
    if not emissions_item:
        raise RuntimeError("No completed emissions period available")

    price_output = make_price_record(price_item, now)
    emissions_output = make_emissions_record(emissions_item, now)

    price_history = merge_latest(HISTORY_FILE, PRICE_FILE, price_output, now)
    emissions_history = merge_latest(
        EMISSIONS_HISTORY_FILE, EMISSIONS_FILE, emissions_output, now
    )

    generation_history = []
    generation_item = last_completed(generation, now) if generation else None
    if generation_item:
        generation_output = make_generation_record(generation_item, now)
        generation_history = merge_latest(
            GENERATION_HISTORY_FILE, GENERATION_FILE, generation_output, now
        )
        print("\nLatest generation:")
        print(json.dumps(generation_output, indent=2))

    print("\nLatest price:")
    print(json.dumps(price_output, indent=2))
    print("\nLatest emissions:")
    print(json.dumps(emissions_output, indent=2))

    print(f"\nPrice history records: {len(price_history)}")
    print(f"Emissions history records: {len(emissions_history)}")
    print(f"Generation history records: {len(generation_history)}")


def main():
    now = datetime.now().astimezone()

    price_history = load_json(HISTORY_FILE)
    emissions_history = load_json(EMISSIONS_HISTORY_FILE)
    generation_history = load_json(GENERATION_HISTORY_FILE)

    if (
        "--refresh" in sys.argv
        or not price_history
        or not emissions_history
        or not generation_history
    ):
        refresh_history(now)
    else:
        update_latest(now)


if __name__ == "__main__":
    main()
