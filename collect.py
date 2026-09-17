#!/usr/bin/env python3

import json
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
MAX_DAYS = 30


def get_prices():
    now = datetime.now().astimezone()

    date_from = now.strftime("%Y-%m-%d")
    date_to = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    url = API_URL.format(
        date_from=date_from,
        date_to=date_to,
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Electrical price collector"},
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    now = datetime.now().astimezone()
    prices = get_prices()

    if not prices:
        raise RuntimeError("No price records returned")

    latest = prices[-1]

    api_start = datetime.fromisoformat(latest["start"])
    api_end = datetime.fromisoformat(latest["end"])

    display_start = api_start + timedelta(minutes=30)
    display_end = api_end + timedelta(minutes=30)

    output = {
        "price": round(float(latest["value"]), 2),
        "currency": "GBP",
        "unit": "MWh",
        "display_period": {
            "start": display_start.isoformat(),
            "end": display_end.isoformat(),
        },
        "api_period": {
            "start": latest["start"],
            "end": latest["end"],
        },
        "collected_at": now.isoformat(),
        "source": "Electric Insights",
    }

    # Latest price
    Path("price.json").write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )

    # Load existing history
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = []
    else:
        history = []

    # Replace an existing entry for the same display period,
    # otherwise add a new one.
    history = [
        item for item in history
        if item.get("display_period", {}).get("start")
        != output["display_period"]["start"]
    ]

    history.append(output)

    # Keep only the most recent 30 days
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

    HISTORY_FILE.write_text(
        json.dumps(history, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(output, indent=2))
    print(f"History records: {len(history)}")


if __name__ == "__main__":
    main()
