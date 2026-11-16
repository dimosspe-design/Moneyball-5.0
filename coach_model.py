"""
Moneyball 5.0 - Coach Scoring Engine
Tests official Fantasy coach scoring rules.
No transfers or lineup changes.
"""

import json
import math
from pathlib import Path


OUTPUT = Path("results/coach_model_test.json")


def coach_fantasy_points(margin, overtime=False):
    if margin == 0:
        raise ValueError("Invalid final margin: zero")

    if overtime:
        return 10 if margin > 0 else -5

    if margin > 0:
        if margin <= 10:
            return 10
        if margin <= 20:
            return 20
        return 25

    if margin >= -10:
        return -5
    if margin >= -20:
        return -10
    return -20


def expected_coach_points(outcomes):
    total_probability = 0.0
    expected_points = 0.0

    for outcome in outcomes:
        probability = float(outcome["probability"])
        margin = int(outcome["margin"])
        overtime = bool(outcome.get("overtime", False))

        if not math.isfinite(probability):
            raise ValueError("Invalid probability")

        if probability < 0 or probability > 1:
            raise ValueError("Probability outside [0,1]")

        points = coach_fantasy_points(margin, overtime)

        expected_points += probability * points
        total_probability += probability

    if not math.isclose(
        total_probability, 1.0, abs_tol=1e-9
    ):
        raise ValueError("Probabilities must sum to 1")

    return expected_points


def run_tests():
    tests = [
        (1, False, 10),
        (10, False, 10),
        (11, False, 20),
        (20, False, 20),
        (21, False, 25),
        (-1, False, -5),
        (-10, False, -5),
        (-11, False, -10),
        (-20, False, -10),
        (-21, False, -20),
        (3, True, 10),
        (-3, True, -5),
    ]

    for margin, overtime, expected in tests:
        actual = coach_fantasy_points(margin, overtime)
        assert actual == expected, (
            f"Failed margin={margin}, overtime={overtime}"
        )

    outcomes = [
        {"probability": 0.40, "margin": 5},
        {"probability": 0.20, "margin": 15},
        {"probability": 0.10, "margin": 25},
        {"probability": 0.20, "margin": -5},
        {"probability": 0.07, "margin": -15},
        {"probability": 0.03, "margin": -25},
    ]

    expected_points = expected_coach_points(outcomes)

    assert math.isclose(
        expected_points, 8.2, abs_tol=1e-9
    )

    return {
        "scoring_tests_passed": len(tests),
        "example_expected_points": expected_points,
        "exact_20_point_win_assumption": 20,
        "historical_probabilities_trained": False,
        "coach_market_connected": False,
        "transfers_executed": False,
        "status": "SCORING_ENGINE_TESTED",
    }


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    report = run_tests()

    OUTPUT.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))
    print("SUCCESS: Coach scoring engine tests passed")
    print("NO TRANSFERS EXECUTED")


if __name__ == "__main__":
    main()
