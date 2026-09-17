#!/usr/bin/env python3

import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

API_URL = (
    "http://electricinsights.co.uk/api/1/prices"
    "?date_from={date_from}"
    "&date_to={date_to}"
    "&group_by=30m"
)

HISTORY_FILE = Path("history.json")
PRICE_FILE = Path("price.json")
MAX_DAYS = 30


def fetch_prices(date_from, date_to):
    url = API_URL.format(
        date_from=date_from,
        date_to=date_to,
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Electrical price collector"},
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def make_record(item, collected_at):
    api_start = datetime.fromisoformat(item["start"])
    api_end = datetime.fromisoformat(item["end"])

    display_start = api_start + timedelta(minutes=30)
    display_end = api_end + timedelta(minutes=30)

    return {
        "price": round(float(item["value"]), 2),
        "currency": "GBP",
        "unit": "MWh",
        "display_period": {
            "start": display_start.isoformat(),
            "end": display_end.isoformat(),
        },
        "api_period": {
            "start": item["start"],
            "end": item["end"],
        },
        "collected_at": collected_at.isoformat(),
        "source": "Electric Insights",
    }


def load_history():
    if not HISTORY_FILE.exists():
        return []

    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_history(history):
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2) + "\n",
        encoding="utf-8",
    )


def refresh_history(now):
    start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    print(
        f"Refreshing 30 days: {start_date} to {end_date}"
    )

    prices = fetch_prices(start_date, end_date)

    if not prices:
        raise RuntimeError("No price records returned")

    history = []

    for item in prices:
        record = make_record(item, now)

        display_start = datetime.fromisoformat(
            record["display_period"]["start"]
        )

        if display_start <= now:
            history.append(record)

    cutoff = now - timedelta(days=MAX_DAYS)

    history = [
        item for item in history
        if datetime.fromisoformat(
            item["display_period"]["start"]
        ) >= cutoff
    ]

    history.sort(
        key=lambda item: item["display_period"]["start"]
    )

    save_history(history)

    if history:
        PRICE_FILE.write_text(
            json.dumps(history[-1], indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"Loaded {len(history)} history records")

    if history:
        print(json.dumps(history[-1], indent=2))


def update_latest(now):
    prices = fetch_prices(
        now.strftime("%Y-%m-%d"),
        (now + timedelta(days=1)).strftime("%Y-%m-%d"),
    )

    if not prices:
        raise RuntimeError("No price records returned")

    latest = prices[-1]
    output = make_record(latest, now)

    history = load_history()

    display_start = output["display_period"]["start"]

    history = [
        item for item in history
        if item.get("display_period", {}).get("start")
        != display_start
    ]

    history.append(output)

    cutoff = now - timedelta(days=MAX_DAYS)

    history = [
        item for item in history
        if datetime.fromisoformat(
            item["display_period"]["start"]
        ) >= cutoff
    ]

    history.sort(
        key=lambda item: item["display_period"]["start"]
    )

    save_history(history)

    PRICE_FILE.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(output, indent=2))
    print(f"History records: {len(history)}")


def main():
    now = datetime.now().astimezone()
    history = load_history()

    if "--refresh" in sys.argv or not history:
        refresh_history(now)
    else:
        update_latest(now)


if __name__ == "__main__":
    main()
