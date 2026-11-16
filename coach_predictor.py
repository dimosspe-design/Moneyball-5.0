"""
Moneyball 5.0 - Coach Predictor v1

Uses historical EuroLeague results to estimate:
- Expected score margin
- Win probability
- Expected Fantasy coach points

Includes chronological backtesting.

IMPORTANT:
- Overtime is not identified in the source dataset.
- Exactly 20-point wins are assigned +20 by assumption.
- Probabilities are approximate and not yet calibrated.
- No transfers or lineup changes.
"""

import csv
import gzip
import io
import json
import math
import statistics
import zipfile

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


DATA_ZIP = Path("euroleague.zip")
FIXTURES = Path("fixtures.csv")

RESULTS = Path("results")

OUTPUT_CSV = RESULTS / "coach_projections_r12.csv"
BACKTEST_CSV = RESULTS / "coach_backtest.csv"
REPORT_JSON = RESULTS / "coach_predictor_report.json"

SHRINKAGE_GAMES = 8
HOME_ADVANTAGE = 2.0
MIN_MARGIN_SD = 9.0


def load_games():
    if not DATA_ZIP.exists():
        raise FileNotFoundError(DATA_ZIP)

    with zipfile.ZipFile(DATA_ZIP) as archive:
        filename = next(
            (
                name
                for name in archive.namelist()
                if name.endswith("games-2026.csv.gz")
            ),
            None,
        )

        if filename is None:
            raise ValueError("games-2026.csv.gz not found")

        compressed = archive.read(filename)

    with gzip.open(io.BytesIO(compressed), "rt") as file:
        rows = list(csv.DictReader(file))

    games = []

    for row in rows:
        home_score = row.get("home_score", "").strip()
        away_score = row.get("away_score", "").strip()

        if not home_score or not away_score:
            continue

        games.append({
            "round": int(row["round"]),
            "home": row["home"].strip().upper(),
            "away": row["away"].strip().upper(),
            "margin": int(home_score) - int(away_score),
        })

    games.sort(key=lambda game: game["round"])

    if not games:
        raise ValueError("No completed games found")

    return games


def load_fixtures():
    if not FIXTURES.exists():
        raise FileNotFoundError(FIXTURES)

    aliases = {
        "Dubai Basketball": "DUB",
        "Anadolu Efes": "EFS",
        "Maccabi Tel Aviv": "MTA",
        "Olympiacos": "OLY",
        "Zalgiris Kaunas": "ZAL",
        "Bayern Munich": "BAY",
        "Fenerbahce": "FBT",
        "ASVEL": "ASV",
        "Baskonia": "KBA",
        "Hapoel Tel Aviv": "HTA",
        "Olimpia Milano": "MIL",
        "Crvena Zvezda": "CZV",
        "Barcelona": "BAR",
        "Paris Basketball": "PAR",
        "Panathinaikos": "PAO",
        "Virtus Bologna": "VIR",
        "Real Madrid": "RMB",
        "Partizan": "PBB",
        "Valencia": "VBC",
        "Valencia Basket": "VBC",
        "Besiktas": "BJK",
    }

    fixtures = []

    with FIXTURES.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        headers = set(reader.fieldnames or [])

        required = {"home_team", "away_team"}

        if not required.issubset(headers):
            raise ValueError(
                "fixtures.csv must contain "
                "home_team and away_team columns"
            )

        for row in reader:
            home_name = row["home_team"].strip()
            away_name = row["away_team"].strip()

            if not home_name or not away_name:
                continue

            if home_name not in aliases:
                raise ValueError(
                    f"Unknown home team: {home_name}"
                )

            if away_name not in aliases:
                raise ValueError(
                    f"Unknown away team: {away_name}"
                )

            fixtures.append({
                "home": aliases[home_name],
                "away": aliases[away_name],
            })

    if len(fixtures) != 10:
        raise ValueError(
            f"Expected 10 fixtures, found {len(fixtures)}"
        )

    teams = [
        team
        for fixture in fixtures
        for team in (fixture["home"], fixture["away"])
    ]

    if len(set(teams)) != 20:
        raise ValueError(
            "Fixtures must contain 20 unique teams"
        )

    return fixtures


def calculate_team_strengths(games):
    margins = defaultdict(list)

    for game in games:
        home = game["home"]
        away = game["away"]
        margin = game["margin"]

        margins[home].append(margin)
        margins[away].append(-margin)

    strengths = {}

    for team, values in margins.items():
        count = len(values)
        average = statistics.mean(values)

        weight = count / (count + SHRINKAGE_GAMES)

        strengths[team] = average * weight

    return strengths


def estimate_margin(home, away, games):
    strengths = calculate_team_strengths(games)

    home_strength = strengths.get(home, 0.0)
    away_strength = strengths.get(away, 0.0)

    expected_margin = (
        home_strength
        - away_strength
        + HOME_ADVANTAGE
    )

    return expected_margin


def estimate_uncertainty(games):
    if len(games) < 10:
        return 13.0

    margins = [game["margin"] for game in games]

    observed_sd = statistics.stdev(margins)

    return max(MIN_MARGIN_SD, observed_sd)


def normal_cdf(value, mean, sd):
    return 0.5 * (
        1.0
        + math.erf(
            (value - mean) / (sd * math.sqrt(2.0))
        )
    )


def margin_probabilities(mean, sd):
    """
    Approximate probabilities for final score margins.

    This version does not explicitly model overtime.
    """

    def cdf(x):
        return normal_cdf(x, mean, sd)

    probabilities = {
        "win_1_10": cdf(10.5) - cdf(0.5),
        "win_11_20": cdf(20.5) - cdf(10.5),
        "win_21_plus": 1.0 - cdf(20.5),
        "loss_1_10": cdf(-0.5) - cdf(-10.5),
        "loss_11_20": cdf(-10.5) - cdf(-20.5),
        "loss_21_plus": cdf(-20.5),
    }

    total = sum(probabilities.values())

    if total <= 0:
        raise ValueError("Invalid probability distribution")

    return {
        key: value / total
        for key, value in probabilities.items()
    }


def expected_coach_score(probabilities):
    scoring = {
        "win_1_10": 10,
        "win_11_20": 20,
        "win_21_plus": 25,
        "loss_1_10": -5,
        "loss_11_20": -10,
        "loss_21_plus": -20,
    }

    return sum(
        probabilities[key] * points
        for key, points in scoring.items()
    )


def predict_game(home, away, games):
    expected_margin = estimate_margin(
        home, away, games
    )

    sd = estimate_uncertainty(games)

    home_probs = margin_probabilities(
        expected_margin, sd
    )

    away_probs = margin_probabilities(
        -expected_margin, sd
    )

    home_win_probability = (
        home_probs["win_1_10"]
        + home_probs["win_11_20"]
        + home_probs["win_21_plus"]
    )

    return {
        "home": home,
        "away": away,
        "expected_home_margin": expected_margin,
        "home_win_probability": home_win_probability,
        "home_coach_expected": expected_coach_score(
            home_probs
        ),
        "away_coach_expected": expected_coach_score(
            away_probs
        ),
    }


def chronological_backtest(games):
    rows = []

    rounds = sorted({
        game["round"]
        for game in games
    })

    for target_round in rounds:
        history = [
            game
            for game in games
            if game["round"] < target_round
        ]

        if len(history) < 20:
            continue

        targets = [
            game
            for game in games
            if game["round"] == target_round
        ]

        for game in targets:
            prediction = predict_game(
                game["home"],
                game["away"],
                history,
            )

            rows.append({
                "round": target_round,
                "home": game["home"],
                "away": game["away"],
                "actual_margin": game["margin"],
                "predicted_margin": round(
                    prediction["expected_home_margin"], 3
                ),
                "absolute_error": round(
                    abs(
                        game["margin"]
                        - prediction["expected_home_margin"]
                    ),
                    3,
                ),
            })

    return rows


def save_csv(path, rows, fields):
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(rows)


def main():
    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    games = load_games()
    fixtures = load_fixtures()

    latest_round = max(
        game["round"]
        for game in games
    )

    if latest_round >= 12:
        raise ValueError(
            "Dataset already contains R12 results. "
            "Refusing to generate pre-R12 predictions."
        )

    historical_teams = {
        team
        for game in games
        for team in (game["home"], game["away"])
    }

    fixture_teams = {
        team
        for fixture in fixtures
        for team in (fixture["home"], fixture["away"])
    }

    unknown = fixture_teams - historical_teams

    if unknown:
        raise ValueError(
            f"Unknown fixture teams: {sorted(unknown)}"
        )

    projections = []

    for fixture in fixtures:
        result = predict_game(
            fixture["home"],
            fixture["away"],
            games,
        )

        projections.append({
            "team": result["home"],
            "opponent": result["away"],
            "venue": "home",
            "expected_margin": round(
                result["expected_home_margin"], 2
            ),
            "win_probability": round(
                result["home_win_probability"], 4
            ),
            "expected_coach_fantasy": round(
                result["home_coach_expected"], 2
            ),
        })

        projections.append({
            "team": result["away"],
            "opponent": result["home"],
            "venue": "away",
            "expected_margin": round(
                -result["expected_home_margin"], 2
            ),
            "win_probability": round(
                1.0 - result["home_win_probability"], 4
            ),
            "expected_coach_fantasy": round(
                result["away_coach_expected"], 2
            ),
        })

    backtest = chronological_backtest(games)

    save_csv(
        OUTPUT_CSV,
        projections,
        [
            "team",
            "opponent",
            "venue",
            "expected_margin",
            "win_probability",
            "expected_coach_fantasy",
        ],
    )

    save_csv(
        BACKTEST_CSV,
        backtest,
        [
            "round",
            "home",
            "away",
            "actual_margin",
            "predicted_margin",
            "absolute_error",
        ],
    )

    mae = (
        statistics.mean(
            row["absolute_error"]
            for row in backtest
        )
        if backtest
        else None
    )

    baseline_mae = (
        statistics.mean(
            abs(row["actual_margin"])
            for row in backtest
        )
        if backtest
        else None
    )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "historical_games": len(games),
        "latest_historical_round": latest_round,
        "fixtures": len(fixtures),
        "coach_projections": len(projections),
        "backtest_games": len(backtest),
        "backtest_margin_mae": mae,
        "zero_margin_baseline_mae": baseline_mae,
        "probabilities_calibrated": False,
        "overtime_identified": False,
        "exact_20_point_win_assumption": 20,
        "official_coach_market_verified": False,
        "transfers_executed": False,
        "status": "INITIAL_COACH_PROJECTIONS",
    }

    REPORT_JSON.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    ))

    print("\nCOACH PROJECTIONS")

    for row in sorted(
        projections,
        key=lambda item: item[
            "expected_coach_fantasy"
        ],
        reverse=True,
    ):
        print(
            f"{row['team']:4s} "
            f"vs {row['opponent']:4s} "
            f"({row['venue']:4s}) "
            f"Win: {row['win_probability']:.1%} "
            f"Expected Fantasy: "
            f"{row['expected_coach_fantasy']:.2f}"
        )

    print("\nSUCCESS: Initial coach projections generated")
    print("WARNING: Model is not yet calibrated")
    print("NO TRANSFERS EXECUTED")


if __name__ == "__main__":
    main()
