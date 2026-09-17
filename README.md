# Electrical

Automatic electricity price data from Electric Insights.

## Website

[View the live electricity price website](https://boothy91.github.io/Electrical/)

## What it does

This project retrieves the latest UK electricity price from the Electric Insights API and stores it in JSON format.

The collector runs automatically through GitHub Actions every 30 minutes.

## Files

- `price.json` — latest electricity price
- `history.json` — rolling 30-day price history
- `collect.py` — API collector and history manager
- `.github/workflows/update-price.yml` — automatic updater

## 30-day history

`history.json` stores the collected 30-minute electricity prices.

The collector automatically removes entries older than 30 days.

## API timestamp

Electric Insights' API timestamp is one 30-minute period earlier than the corresponding period displayed on the website.

For example:

```text
API:     06:00–06:30 → £96.00/MWh
Website: 06:30–07:00 → £96.00/MWh




