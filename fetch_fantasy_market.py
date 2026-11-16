"""
Moneyball 5.0 — Public Fantasy Market Collector

Reads the public player table from Fantasy Edge IQ.

Outputs an unverified market snapshot.
Does not modify verified market data.
Does not log in or execute transfers.
"""

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


URL = "https://www.fantasyedgeiq.com/euroleague/players"

OUTPUT_CSV = Path("results/public_market_snapshot.csv")
OUTPUT_REPORT = Path("results/public_market_report.json")

EXPECTED_HEADERS = [
    "Player",
    "Team",
    "Pos",
    "Price",
    "MIN/G",
    "PIR/G",
    "Proj PIR",
]


def parse_price(value):
    value = value.strip().replace(",", ".")
    value = value.replace("CR", "").replace("€", "").strip()

    number = float(value)

    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"Invalid price: {value}")

    return number


def main():
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(
        URL,
        timeout=30,
        headers={
            "User-Agent": "Moneyball5-PublicMarketCollector/1.0"
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

        if headers[:4] == EXPECTED_HEADERS[:4]:
            matching_table = table
            break

    if matching_table is None:
        raise SystemExit(
            "No table with Player/Team/Pos/Price headers found"
        )

    rows = []
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

        player, team, position, price_text = cells[:4]

        if not player:
            issues.append(f"Row {index}: missing player")
            continue

        if player.casefold() in seen:
            issues.append(f"Row {index}: duplicate {player}")
            continue

        if position not in {"G", "F", "C"}:
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

        seen.add(player.casefold())

        rows.append({
            "player": player,
            "team": team,
            "position": position,
            "credit": price,
            "source": "Fantasy Edge IQ",
            "verified_price": "false",
        })

    if not rows:
        raise SystemExit("No valid player rows extracted")

    with OUTPUT_CSV.open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "player",
                "team",
                "position",
                "credit",
                "source",
                "verified_price",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "source": URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "players_extracted": len(rows),
        "issues": issues,
        "official_fantasy_market_verified": False,
        "transfers_executed": False,
    }

    OUTPUT_REPORT.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nSUCCESS: Public market snapshot created")
    print("NO TRANSFERS EXECUTED")


if __name__ == "__main__":
    main()
