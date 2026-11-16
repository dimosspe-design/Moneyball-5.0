"""
Moneyball 5.0 - Guarded Optimizer v5

Read-only EuroLeague Fantasy roster optimizer.

Features:
- 4 Guards, 4 Forwards, 2 Centers, 1 Coach
- Legal starting-five formations
- Captain, sixth player and bench weights
- Maximum 6 players from one team
- Budget and maximum transfer constraints
- Coach projections handled separately
- Unverified or uncertain NEW candidates excluded
- Current roster retained as a baseline
- User-confirmed incumbents overlaid with explicit audit; missing projections block execution
- Expected and upside-proxy scenarios
- Sparse MILP constraints

Limitations:
- Conditional projections, not availability-adjusted
- No live T1/T2 substitution optimization
- No automatic transfers
- No claim of global optimality without a complete market
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix


FORMATIONS = [
    (2, 2, 1),
    (1, 2, 2),
    (2, 1, 2),
    (1, 3, 1),
    (3, 1, 1),
]

SLOTS = [
    "captain",
    "starter2",
    "starter3",
    "starter4",
    "starter5",
    "sixth",
    "bench1",
    "bench2",
    "bench3",
    "bench4",
    "coach",
]

WEIGHTS = np.array([
    2.0, 1.0, 1.0, 1.0, 1.0,
    1.0,
    0.5, 0.5, 0.5, 0.5,
    1.0,
])

REQUIRED_MARKET = {
    "player",
    "team",
    "position",
    "credit",
    "turn",
    "expected_fantasy_if_play",
    "upside_p90_approx",
    "availability",
    "verified_price",
    "verified_matchup",
}

POSITIONS = {
    "G": 4,
    "F": 4,
    "C": 2,
    "HC": 1,
}

VALID_TURNS = {"T1", "T2", "T3", "T4"}


def truthy(value):
    return str(value).strip().lower() in {
        "true", "1", "yes"
    }


def clean_name(value):
    return str(value).strip()


def validate_market(market):
    missing = REQUIRED_MARKET - set(market.columns)

    if missing:
        raise ValueError(
            f"Missing market columns: {sorted(missing)}"
        )

    market = market.copy()

    for column in ["player", "team", "position", "turn"]:
        market[column] = (
            market[column].astype(str).str.strip()
        )

    if market["player"].eq("").any():
        raise ValueError("Empty player identity")

    if market["player"].duplicated().any():
        raise ValueError("Duplicate player identity")

    if not market["position"].isin(POSITIONS).all():
        raise ValueError("Invalid position")

    if not market["turn"].isin(VALID_TURNS).all():
        raise ValueError("Invalid turn")

    if market["team"].eq("").any():
        raise ValueError("Missing team")

    numeric = [
        "credit",
        "expected_fantasy_if_play",
        "upside_p90_approx",
    ]

    for column in numeric:
        market[column] = pd.to_numeric(
            market[column],
            errors="coerce",
        )

        if not np.isfinite(
            market[column].to_numpy(dtype=float)
        ).all():
            raise ValueError(
                f"Invalid numeric values in {column}"
            )

    if (market["credit"] <= 0).any():
        raise ValueError("Credits must be positive")

    if not market["availability"].isin(
        ["confirmed", "uncertain"]
    ).all():
        raise ValueError("Invalid availability status")

    return market


def validate_roster(market, roster, budget):
    if "player" not in roster.columns:
        raise ValueError("Roster requires player column")

    names = roster["player"].map(clean_name)

    if len(names) != 11 or names.duplicated().any():
        raise ValueError(
            "Roster must contain 11 distinct entries"
        )

    market_names = set(market["player"])

    missing = set(names) - market_names

    if missing:
        raise ValueError(
            f"Roster entries missing from market: "
            f"{sorted(missing)}"
        )

    current = market.set_index("player").loc[
        names.tolist()
    ].reset_index()

    counts = current["position"].value_counts()

    for position, required in POSITIONS.items():
        if counts.get(position, 0) != required:
            raise ValueError(
                f"Current roster has invalid {position} count"
            )

    team_counts = (
        current[current["position"] != "HC"]
        ["team"].value_counts()
    )

    if (team_counts > 6).any():
        raise ValueError(
            "Current roster exceeds team cap"
        )

    spent = float(current["credit"].sum())

    if spent > budget + 1e-6:
        raise ValueError(
            f"Current roster exceeds budget: {spent:.2f}"
        )

    return current


def candidate_is_safe(row, incumbent):
    if incumbent:
        return True

    return (
        truthy(row["verified_price"])
        and truthy(row["verified_matchup"])
        and row["availability"] == "confirmed"
    )


def prepare_pool(market, roster):
    originals = set(roster["player"].map(clean_name))

    mask = market.apply(
        lambda row: candidate_is_safe(
            row,
            row["player"] in originals,
        ),
        axis=1,
    )

    pool = market.loc[mask].reset_index(drop=True)

    excluded = market.loc[~mask, [
        "player", "team", "position",
        "availability", "verified_price",
        "verified_matchup",
    ]].to_dict("records")

    return pool, excluded


def score_column(market, metric):
    values = market[metric].to_numpy(
        dtype=float
    ).copy()

    # Coach rows must have a separate coach projection
    # supplied in the chosen metric column.
    return values


def optimize(
    market,
    roster,
    budget,
    max_trades,
    metric,
    time_limit=60,
):
    original = set(roster["player"])

    m, excluded = prepare_pool(market, roster)

    n = len(m)
    k = len(SLOTS)
    variable_count = n * k

    if n < 11:
        raise RuntimeError(
            "Not enough eligible market entries"
        )

    def index(i, j):
        return i * k + j

    lower_bounds = np.zeros(variable_count)
    upper_bounds = np.ones(variable_count)

    # Disallow players in coach slot and vice versa.
    for i in range(n):
        for j in range(k):
            is_coach_slot = j == 10
            is_coach = m.loc[i, "position"] == "HC"

            if is_coach_slot != is_coach:
                upper_bounds[index(i, j)] = 0

    constraints = []

    def add_constraint(terms, minimum, maximum):
        constraints.append(
            (terms, minimum, maximum)
        )

    # Exactly one entry per slot.
    for j in range(k):
        add_constraint(
            [(index(i, j), 1) for i in range(n)],
            1, 1,
        )

    # Each entry used at most once.
    for i in range(n):
        add_constraint(
            [(index(i, j), 1) for j in range(k)],
            0, 1,
        )

    # Complete roster composition.
    for position, required in POSITIONS.items():
        terms = [
            (index(i, j), 1)
            for i in range(n)
            if m.loc[i, "position"] == position
            for j in range(k)
        ]

        add_constraint(terms, required, required)

    # Budget.
    add_constraint(
        [
            (index(i, j), float(m.loc[i, "credit"]))
            for i in range(n)
            for j in range(k)
        ],
        0, budget,
    )

    # Transfer count, including coach.
    add_constraint(
        [
            (
                index(i, j),
                int(m.loc[i, "player"] not in original),
            )
            for i in range(n)
            for j in range(k)
        ],
        0, max_trades,
    )

    # Team cap applies to players, not coach.
    for team in m["team"].unique():
        terms = [
            (index(i, j), 1)
            for i in range(n)
            if m.loc[i, "team"] == team
            for j in range(10)
        ]

        add_constraint(terms, 0, 6)

    # The objective is conditional on participation.
    projections = score_column(m, metric)

    objective = np.zeros(variable_count)

    for i in range(n):
        for j in range(k):
            objective[index(i, j)] = (
                -projections[i] * WEIGHTS[j]
            )

    solutions = []

    for formation in FORMATIONS:
        g, f, c = formation

        current_constraints = list(constraints)

        for position, required in [
            ("G", g),
            ("F", f),
            ("C", c),
        ]:
            terms = [
                (index(i, j), 1)
                for i in range(n)
                if m.loc[i, "position"] == position
                for j in range(5)
            ]

            current_constraints.append(
                (terms, required, required)
            )

        matrix = lil_matrix(
            (len(current_constraints), variable_count),
            dtype=float,
        )

        lows = []
        highs = []

        for row_number, (terms, lo, hi) in enumerate(
            current_constraints
        ):
            for variable, coefficient in terms:
                matrix[row_number, variable] += coefficient

            lows.append(lo)
            highs.append(hi)

        result = milp(
            c=objective,
            integrality=np.ones(variable_count),
            bounds=Bounds(
                lower_bounds,
                upper_bounds,
            ),
            constraints=LinearConstraint(
                matrix.tocsr(),
                np.array(lows),
                np.array(highs),
            ),
            options={
                "time_limit": time_limit,
                "mip_rel_gap": 0.005,
            },
        )

        # Only accept a solver-confirmed successful result.
        if not result.success or result.x is None:
            continue

        selected = result.x.reshape(n, k)

        lineup = []

        for j, slot in enumerate(SLOTS):
            indices = np.flatnonzero(
                selected[:, j] > 0.5
            )

            if len(indices) != 1:
                raise RuntimeError(
                    f"Invalid solution for {slot}"
                )

            i = int(indices[0])

            lineup.append({
                "slot": slot,
                "player": str(m.loc[i, "player"]),
                "team": str(m.loc[i, "team"]),
                "position": str(m.loc[i, "position"]),
                "turn": str(m.loc[i, "turn"]),
                "credit": float(m.loc[i, "credit"]),
                "projection": float(projections[i]),
                "availability": str(
                    m.loc[i, "availability"]
                ),
                "is_transfer": (
                    m.loc[i, "player"] not in original
                ),
            })

        solutions.append({
            "formation": f"{g}-{f}-{c}",
            "conditional_weighted_score": round(
                -float(result.fun), 3
            ),
            "credits": round(
                sum(row["credit"] for row in lineup), 2
            ),
            "trades": sum(
                row["is_transfer"] for row in lineup
            ),
            "lineup": lineup,
        })

    if not solutions:
        raise RuntimeError(
            "No verified feasible solution found"
        )

    best = max(
        solutions,
        key=lambda row: row[
            "conditional_weighted_score"
        ],
    )

    return best, excluded



def reconcile_roster_market(market, roster, audit_path=None):
    """Overlay independently user-confirmed incumbent identities only.

    Roster credits/teams are user-reported, not independently verified.
    Never manufacture missing projections or mark availability confirmed.
    """
    required_roster = {"player", "team", "position", "credit", "turn"}
    absent = required_roster - set(roster.columns)
    if absent:
        raise ValueError(f"Roster lacks overlay fields: {sorted(absent)}")
    market = market.copy()
    names = roster["player"].astype(str).str.strip()
    if len(names) != 11 or names.duplicated().any():
        raise ValueError("Roster must contain 11 distinct entries")
    audit = {"added_from_roster": [], "roster_market_discrepancies": [],
             "excluded_incomplete_market_rows": [], "blocking_issues": [],
             "transfers_executed": False}
    for _, r in roster.iterrows():
        name = str(r["player"]).strip()
        matching = market.index[market["player"].astype(str).str.strip() == name]
        if len(matching) > 1:
            audit["blocking_issues"].append(f"Duplicate market name: {name}")
            continue
        if len(matching) == 0:
            # The roster is the evidence for identity, team, position and price;
            # no projections or verification flags are invented.
            row = {col: "" for col in market.columns}
            for col in required_roster:
                row[col] = r[col]
            row.update({"availability": "uncertain", "verified_price": "false",
                        "verified_matchup": "false", "source": "user_confirmed_roster",
                        "match_status": "missing_public_market"})
            market = pd.concat([market, pd.DataFrame([row])], ignore_index=True)
            audit["added_from_roster"].append(name)
        else:
            idx = matching[0]
            for col in ("team", "position", "turn", "credit"):
                a, b = str(market.at[idx, col]).strip(), str(r[col]).strip()
                if col == "credit":
                    try:
                        equal = abs(float(a) - float(b)) < 0.001
                    except (TypeError, ValueError):
                        equal = False
                else:
                    equal = a == b
                if not equal:
                    audit["roster_market_discrepancies"].append(
                        {"player": name, "field": col, "market": a, "roster": b})
                    # Preserve incumbent details as reported by user, but not verified.
                    market.at[idx, col] = r[col]
                    if col == "credit":
                        market.at[idx, "verified_price"] = "false"
                    if col in ("team", "turn"):
                        market.at[idx, "verified_matchup"] = "false"

    # Missing projection for an incumbent is a BLOCKER, never filled with zero.
    incumbents = set(names)
    for _, r in market[market["player"].isin(incumbents)].iterrows():
        for col in ("expected_fantasy_if_play", "upside_p90_approx"):
            value = pd.to_numeric(r.get(col), errors="coerce")
            if not np.isfinite(value):
                audit["blocking_issues"].append(
                    f"Missing {col} for incumbent {r['player']}")
        if r["position"] == "HC":
            value = pd.to_numeric(r.get("coach_expected_fantasy"), errors="coerce")
            if not np.isfinite(value):
                audit["blocking_issues"].append(
                    f"Missing coach_expected_fantasy for {r['player']}")

    # Unverified new candidates cannot be transferred in; rows with no
    # projection should not invalidate the entire market during validation.
    good = pd.Series(True, index=market.index)
    for col in ("credit", "expected_fantasy_if_play", "upside_p90_approx"):
        good &= pd.to_numeric(market[col], errors="coerce").map(np.isfinite)
    good &= market["turn"].isin(VALID_TURNS)
    good &= market["position"].isin(POSITIONS)
    good &= market["team"].astype(str).str.strip().ne("")
    good &= market["player"].astype(str).str.strip().ne("")
    incomplete = market.loc[~good]
    audit["excluded_incomplete_market_rows"] = [
        str(x) for x in incomplete.loc[~incomplete["player"].isin(incumbents), "player"]
    ]
    if audit_path:
        dest = Path(audit_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    if audit["blocking_issues"]:
        raise ValueError("Roster reconciliation blocked: " +
                         "; ".join(audit["blocking_issues"]) +
                         (f". Audit: {audit_path}" if audit_path else ""))
    return market.loc[good].reset_index(drop=True), audit

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--market", required=True
    )
    parser.add_argument(
        "--roster", required=True
    )
    parser.add_argument(
        "--out", required=True
    )
    parser.add_argument(
        "--budget", type=float, default=103.7
    )
    parser.add_argument(
        "--trades", type=int, default=4
    )
    parser.add_argument(
        "--complete-market-confirmed",
        action="store_true",
    )

    args = parser.parse_args()

    if not math.isfinite(args.budget) or args.budget <= 0:
        raise ValueError("Invalid budget")

    if not 0 <= args.trades <= 4:
        raise ValueError("Invalid transfer limit")

    roster = pd.read_csv(args.roster)
    raw_market = pd.read_csv(args.market)
    # Read-only audit saved alongside the requested output.
    audit_path = str(Path(args.out).with_suffix(".reconciliation.json"))
    reconciled, audit = reconcile_roster_market(
        raw_market, roster, audit_path
    )
    market = validate_market(reconciled)

    current = validate_roster(
        market, roster, args.budget
    )

    # Do not silently use player projections as
    # coach projections. Require an explicit column.
    if "coach_expected_fantasy" not in market.columns:
        raise ValueError(
            "Missing coach_expected_fantasy column. "
            "Merge verified coach projections first."
        )

    market["coach_expected_fantasy"] = pd.to_numeric(
        market["coach_expected_fantasy"],
        errors="coerce",
    )

    coach_mask = market["position"] == "HC"

    if market.loc[
        coach_mask, "coach_expected_fantasy"
    ].isna().any():
        raise ValueError(
            "Missing coach projections"
        )

    # Use the separate coach model for HC entries.
    market.loc[
        coach_mask, "expected_fantasy_if_play"
    ] = market.loc[
        coach_mask, "coach_expected_fantasy"
    ]

    # Coach upside is not calibrated.
    # Use expected value in the proxy scenario.
    market.loc[
        coach_mask, "upside_p90_approx"
    ] = market.loc[
        coach_mask, "coach_expected_fantasy"
    ]

    results = {}

    for metric in [
        "expected_fantasy_if_play",
        "upside_p90_approx",
    ]:
        best, excluded = optimize(
            market,
            current,
            args.budget,
            args.trades,
            metric,
        )

        results[metric] = best

    results["excluded_candidates"] = excluded
    results["roster_market_reconciliation"] = audit

    results["market_complete_verified_by_user"] = (
        args.complete_market_confirmed
    )

    results["current_roster"] = (
        current["player"].tolist()
    )

    results["caveats"] = [
        "No transfers executed",
        "Market completeness not independently established",
        "Incumbent prices and matchups require verification",
        "Conditional projections ignore non-participation risk",
        "Uncertain incumbents remain selectable",
        "No live T1/T2 substitution optimization",
        "Upside proxy is not a calibrated team percentile",
        "Coach upside uses coach expected value",
        "Solver solutions are conditional on supplied inputs",
    ]

    results["transfers_executed"] = False

    output = Path(args.out)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("SUCCESS: Guarded optimizer completed")
    print("Output:", output)
    print("No transfers executed")


if __name__ == "__main__":
    main()