#!/usr/bin/env python3

import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PRICE_API = (
    "http://electricinsights.co.uk/api/1/prices"
    "?date_from={date_from}"
    "&date_to={date_to}"
    "&group_by=30m"
)

EMISSIONS_API = (
    "http://electricinsights.co.uk/api/1/emissions"
    "?date_from={date_from}"
    "&date_to={date_to}"
    "&group_by=30m"
)

HISTORY_FILE = Path("history.json")
PRICE_FILE = Path("price.json")

EMISSIONS_HISTORY_FILE = Path("emissions_history.json")
EMISSIONS_FILE = Path("emissions.json")

MAX_DAYS = 30


def fetch_api(url_template, date_from, date_to):
    url = url_template.format(
        date_from=date_from,
        date_to=date_to,
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Electrical data collector"},
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def make_price_record(item, collected_at):
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


def make_emissions_record(item, collected_at):
    api_start = datetime.fromisoformat(item["start"])
    api_end = datetime.fromisoformat(item["end"])

    display_start = api_start + timedelta(minutes=30)
    display_end = api_end + timedelta(minutes=30)

    return {
        "emissions": round(
            float(item["value"]["totalInGperkWh"]),
            2,
        ),
        "unit": "gCO2/kWh",
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


def load_json(path):
    if not path.exists():
        return []

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_json(path, data):
    path.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )


def trim_history(history, now):
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

    return history


def refresh_history(now):
    start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    print(
        f"Refreshing 30 days: {start_date} to {end_date}"
    )

    prices = fetch_api(
        PRICE_API,
        start_date,
        end_date,
    )

    emissions = fetch_api(
        EMISSIONS_API,
        start_date,
        end_date,
    )

    if not prices:
        raise RuntimeError("No price records returned")

    if not emissions:
        raise RuntimeError("No emissions records returned")

    price_history = []
    emissions_history = []

    for item in prices:
        record = make_price_record(item, now)

        display_start = datetime.fromisoformat(
            record["display_period"]["start"]
        )

        if display_start <= now:
            price_history.append(record)

    for item in emissions:
        record = make_emissions_record(item, now)

        display_start = datetime.fromisoformat(
            record["display_period"]["start"]
        )

        if display_start <= now:
            emissions_history.append(record)

    price_history = trim_history(price_history, now)
    emissions_history = trim_history(emissions_history, now)

    save_json(HISTORY_FILE, price_history)
    save_json(EMISSIONS_HISTORY_FILE, emissions_history)

    if price_history:
        save_json(PRICE_FILE, price_history[-1])

    if emissions_history:
        save_json(
            EMISSIONS_FILE,
            emissions_history[-1],
        )

    print(
        f"Price history records: {len(price_history)}"
    )

    print(
        f"Emissions history records: "
        f"{len(emissions_history)}"
    )

    if price_history:
        print("\nLatest price:")
        print(json.dumps(price_history[-1], indent=2))

    if emissions_history:
        print("\nLatest emissions:")
        print(
            json.dumps(
                emissions_history[-1],
                indent=2,
            )
        )


def update_latest(now):
    date_from = now.strftime("%Y-%m-%d")
    date_to = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    prices = fetch_api(
        PRICE_API,
        date_from,
        date_to,
    )

    emissions = fetch_api(
        EMISSIONS_API,
        date_from,
        date_to,
    )

    if not prices:
        raise RuntimeError("No price records returned")

    if not emissions:
        raise RuntimeError("No emissions records returned")

    valid_prices = [
        item for item in prices
        if datetime.fromisoformat(item["start"]) + timedelta(minutes=30) <= now
    ]

    valid_emissions = [
        item for item in emissions
        if datetime.fromisoformat(item["start"]) + timedelta(minutes=30) <= now
    ]

    if not valid_prices:
        raise RuntimeError("No completed price period available")

    if not valid_emissions:
        raise RuntimeError("No completed emissions period available")

    price_output = make_price_record(
        valid_prices[-1],
        now,
    )

    emissions_output = make_emissions_record(
        valid_emissions[-1],
        now,
    )

    price_history = load_json(HISTORY_FILE)
    emissions_history = load_json(
        EMISSIONS_HISTORY_FILE
    )

    price_period = price_output["display_period"]["start"]

    price_history = [
        item for item in price_history
        if item.get("display_period", {}).get("start")
        != price_period
    ]

    price_history.append(price_output)
    price_history = trim_history(
        price_history,
        now,
    )

    emissions_period = (
        emissions_output["display_period"]["start"]
    )

    emissions_history = [
        item for item in emissions_history
        if item.get("display_period", {}).get("start")
        != emissions_period
    ]

    emissions_history.append(emissions_output)

    emissions_history = trim_history(
        emissions_history,
        now,
    )

    save_json(HISTORY_FILE, price_history)
    save_json(
        EMISSIONS_HISTORY_FILE,
        emissions_history,
    )

    save_json(PRICE_FILE, price_output)
    save_json(
        EMISSIONS_FILE,
        emissions_output,
    )

    print("\nLatest price:")
    print(json.dumps(price_output, indent=2))

    print("\nLatest emissions:")
    print(json.dumps(emissions_output, indent=2))

    print(
        f"\nPrice history records: "
        f"{len(price_history)}"
    )

    print(
        f"Emissions history records: "
        f"{len(emissions_history)}"
    )


def main():
    now = datetime.now().astimezone()

    price_history = load_json(HISTORY_FILE)
    emissions_history = load_json(
        EMISSIONS_HISTORY_FILE
    )

    if (
        "--refresh" in sys.argv
        or not price_history
        or not emissions_history
    ):
        refresh_history(now)
    else:
        update_latest(now)


if __name__ == "__main__":
    main()
