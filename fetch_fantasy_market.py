"""
Moneyball 5.0 — Public Fantasy Market Collector

Collects player and coach prices from a public HTML table.

Outputs:
- results/public_market_snapshot.csv
- results/public_coaches_snapshot.csv
- results/public_market_report.json

No login. No transfers. No modification of verified data.
"""

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


URL = "https://www.fantasyedgeiq.com/euroleague/players"

RESULTS = Path("results")
PLAYERS_CSV = RESULTS / "public_market_snapshot.csv"
COACHES_CSV = RESULTS / "public_coaches_snapshot.csv"
REPORT_JSON = RESULTS / "public_market_report.json"

EXPECTED_HEADERS = ["Player", "Team", "Pos", "Price"]


def parse_price(value):
    cleaned = (
        value.strip()
        .replace(",", ".")
        .replace("CR", "")
        .replace("€", "")
        .strip()
    )

    number = float(cleaned)

    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"Invalid price: {value}")

    return number


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)

    response = requests.get(
        URL,
        timeout=30,
        headers={
            "User-Agent": "Moneyball5-PublicMarketCollector/1.1"
        },
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    matching_table = None

    for table in soup.find_all("table"):
        headers = [
            th.get_text(" ", strip=True)
            for th in table.find_all("th")
        ]

        if headers[:4] == EXPECTED_HEADERS:
            matching_table = table
            break

    if matching_table is None:
        raise SystemExit(
            "No table with Player/Team/Pos/Price headers found"
        )

    players = []
    coaches = []
    issues = []
    seen = set()

    for index, tr in enumerate(
        matching_table.find_all("tr")[1:],
        start=2,
    ):
        cells = [
            td.get_text(" ", strip=True)
            for td in tr.find_all("td")
        ]

        if len(cells) < 4:
            continue

        name, team, position, price_text = cells[:4]

        if not name:
            issues.append(f"Row {index}: missing name")
            continue

        key = (name.casefold(), team.casefold())

        if key in seen:
            issues.append(
                f"Row {index}: duplicate {name} ({team})"
            )
            continue

        if position not in {"G", "F", "C", "HC"}:
            issues.append(
                f"Row {index}: invalid position {position}"
            )
            continue

        try:
            price = parse_price(price_text)
        except ValueError:
            issues.append(
                f"Row {index}: invalid price {price_text}"
            )
            continue

        seen.add(key)

        row = {
            "player": name,
            "team": team,
            "position": position,
            "credit": price,
            "source": "Fantasy Edge IQ",
            "verified_price": "false",
        }

        if position == "HC":
            coaches.append(row)
        else:
            players.append(row)

    if not players:
        raise SystemExit("No valid player rows extracted")

    if not coaches:
        raise SystemExit("No coach rows extracted")

    fields = [
        "player",
        "team",
        "position",
        "credit",
        "source",
        "verified_price",
    ]

    write_csv(PLAYERS_CSV, players, fields)
    write_csv(COACHES_CSV, coaches, fields)

    report = {
        "source": URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "players_extracted": len(players),
        "coaches_extracted": len(coaches),
        "issues": issues,
        "official_fantasy_market_verified": False,
        "coach_projections_available": False,
        "transfers_executed": False,
    }

    REPORT_JSON.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))

    print("\nSUCCESS: Players and coaches extracted")
    print("NOTE: Prices are not officially verified")
    print("NO TRANSFERS EXECUTED")


if __name__ == "__main__":
    main()
