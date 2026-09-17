#!/usr/bin/env python3

import json
import urllib.request
from datetime import datetime, timedelta

API_URL = (
    "http://electricinsights.co.uk/api/1/prices"
    "?date_from={date_from}"
    "&date_to={date_to}"
    "&group_by=30m"
)


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
        headers={
            "User-Agent": "Electrical price collector"
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    prices = get_prices()

    if not prices:
        raise RuntimeError("No price records returned")

    latest = prices[-1]

    api_start = datetime.fromisoformat(latest["start"])
    api_end = datetime.fromisoformat(latest["end"])

    # Electric Insights API timestamps correspond to the
    # following 30-minute period shown on the website.
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
        "collected_at": datetime.now().astimezone().isoformat(),
        "source": "Electric Insights",
    }

    with open("price.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
