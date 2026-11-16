"""
Moneyball 5.0 — Fantasy Market Bridge

Builds a market CSV from model projections.

IMPORTANT:
- Does NOT invent Fantasy prices or positions.
- Does NOT mark availability as confirmed.
- Does NOT execute transfers.
- Requires independently verified market data
  before optimization.
"""

import argparse
import csv
import json
import math
from pathlib import Path


FIELDS = [
    "player",
    "credit",
    "position",
    "turn",
    "expected_fantasy_if_play",
    "upside_p90_approx",
    "availability",
    "verified_price",
    "verified_matchup",
]

POSITIONS = {"G", "F", "C"}
TURNS = {"T1", "T2", "T3"}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def is_valid_number(value, positive=False):
    try:
        number = float(value)
        return math.isfinite(number) and (
            not positive or number > 0
        )
    except (TypeError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--projections",
        default="results/conditional_projections.csv",
    )

    parser.add_argument(
        "--market",
        default="verified_market_template.csv",
    )

    parser.add_argument(
        "--output",
        default="results/market_candidates.csv",
    )

    parser.add_argument(
        "--report",
        default="results/market_validation.json",
    )

    args = parser.parse_args()

    projections_path = Path(args.projections)
    market_path = Path(args.market)

    if not projections_path.exists():
        raise SystemExit(
            f"Missing projections: {projections_path}"
        )

    projections = read_csv(projections_path)

    if not projections:
        raise SystemExit("Projection CSV is empty")

    required_projection_columns = {
        "player",
        "expected_fantasy_if_play",
        "upside_p90_approx",
    }

    with open(
        projections_path,
        newline="",
        encoding="utf-8-sig",
    ) as f:
        projection_headers = set(
            csv.DictReader(f).fieldnames or []
        )

    missing = required_projection_columns - projection_headers

    if missing:
        raise SystemExit(
            "Missing projection columns: "
            + ", ".join(sorted(missing))
        )

    market_rows = []

    if market_path.exists():
        market_rows = read_csv(market_path)

    market_by_player = {}

    for row in market_rows:
        name = row.get("player", "").strip().casefold()

        if not name:
            continue

        if name in market_by_player:
            raise SystemExit(
                f"Duplicate market player: {name}"
            )

        market_by_player[name] = row

    output_rows = []
    problems = []
    verified_count = 0

    for projection in projections:
        player = projection["player"].strip()

        if not player:
            problems.append("Projection with missing player name")
            continue

        market = market_by_player.get(
            player.casefold(),
            {},
        )

        credit = market.get("credit", "").strip()
        position = market.get("position", "").strip().upper()
        turn = market.get("turn", "").strip().upper()

        availability = market.get(
            "availability", "uncertain"
        ).strip().lower()

        verified_price = market.get(
            "verified_price", "false"
        ).strip().lower()

        verified_matchup = market.get(
            "verified_matchup", "false"
        ).strip().lower()

        if availability not in {"confirmed", "uncertain"}:
            availability = "uncertain"

        # A matchup in the model is not independent
        # verification of the Fantasy schedule.
        if verified_matchup != "true":
            verified_matchup = "false"

        if verified_price != "true":
            verified_price = "false"

        row = {
            "player": player,
            "credit": credit,
            "position": position,
            "turn": turn,
            "expected_fantasy_if_play": projection[
                "expected_fantasy_if_play"
            ],
            "upside_p90_approx": projection[
                "upside_p90_approx"
            ],
            "availability": availability,
            "verified_price": verified_price,
            "verified_matchup": verified_matchup,
        }

        output_rows.append(row)

        valid = (
            is_valid_number(credit, positive=True)
            and position in POSITIONS
            and turn in TURNS
            and availability == "confirmed"
            and verified_price == "true"
            and verified_matchup == "true"
            and is_valid_number(
                row["expected_fantasy_if_play"]
            )
            and is_valid_number(
                row["upside_p90_approx"]
            )
        )

        if valid:
            verified_count += 1

    if not output_rows:
        raise SystemExit("No market candidates generated")

    write_csv(args.output, output_rows)

    report = {
        "projection_players": len(projections),
        "market_rows_supplied": len(market_rows),
        "generated_candidates": len(output_rows),
        "fully_verified_candidates": verified_count,
        "unverified_candidates": (
            len(output_rows) - verified_count
        ),
        "global_market_completeness": "NOT VERIFIED",
        "coach_optimization": "NOT IMPLEMENTED",
        "availability_model": "NOT IMPLEMENTED",
        "transfers_executed": False,
        "optimization_ready": False,
        "notes": [
            "Player names must match between the two CSV files.",
            "Prices and positions require external verification.",
            "A confirmed appearance is not guaranteed.",
            "The model projections are conditional on playing.",
            "Full-market optimization remains blocked "
            "until market completeness is verified.",
        ],
        "issues": problems,
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))

    print(
        "\nSUCCESS: Market candidates generated."
        "\nNOTE: This is NOT a verified complete Fantasy market."
    )


if __name__ == "__main__":
    main()
