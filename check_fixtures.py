import csv
import gzip
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

DATA = Path("euroleague.zip")
FIXTURES = Path("fixtures.csv")
OUT = Path("results/fixtures_validation.json")

# Verified team codes from the EuroLeague 2026 dataset.
TEAM_CODES = {
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
    "Partizan": "PBB",
    "Valencia Basket": "VBC",
    "Virtus Bologna": "VIR",
    "Panathinaikos": "PAO",
    "Besiktas": "BJK",
    "Real Madrid": "RMB",
}


def normalize(value):
    return "".join(
        char
        for char in str(value).casefold()
        if char.isalnum()
    )


def read_fixtures():
    if not FIXTURES.exists():
        raise FileNotFoundError(
            f"Missing fixtures file: {FIXTURES}"
        )

    with FIXTURES.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)
        fixtures = list(reader)
        columns = reader.fieldnames or []

    if not fixtures:
        raise ValueError("fixtures.csv is empty")

    return fixtures, columns


def read_dataset_teams():
    if not DATA.exists():
        raise FileNotFoundError(
            f"Missing dataset: {DATA}"
        )

    with zipfile.ZipFile(DATA) as archive:
        filename = "team_games-2026.csv.gz"

        if filename not in archive.namelist():
            raise ValueError(
                f"Missing {filename} inside {DATA}"
            )

        compressed = archive.read(filename)

    with gzip.open(
        io.BytesIO(compressed),
        "rt",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        if "team" not in (reader.fieldnames or []):
            raise ValueError(
                "Dataset has no 'team' column"
            )

        teams = {
            row["team"].strip()
            for row in reader
            if row.get("team", "").strip()
        }

    return teams


def find_fixture_team_columns(columns):
    normalized = {
        normalize(column): column
        for column in columns
    }

    # Supported common CSV formats:
    # home_team, away_team
    # home, away
    # team1, team2
    # team, opponent

    possible_pairs = [
        ("hometeam", "awayteam"),
        ("home", "away"),
        ("team1", "team2"),
        ("team", "opponent"),
    ]

    for first, second in possible_pairs:
        if first in normalized and second in normalized:
            return normalized[first], normalized[second]

    return None


def main():
    fixtures, fixture_columns = read_fixtures()
    dataset_teams = read_dataset_teams()

    print("Dataset team codes:")
    print(sorted(dataset_teams))

    print("Fixture columns:")
    print(fixture_columns)

    # Match every configured team to an actual dataset code.
    matched = {
        team: code
        for team, code in TEAM_CODES.items()
        if code in dataset_teams
    }

    unmatched = [
        team
        for team, code in TEAM_CODES.items()
        if code not in dataset_teams
    ]

    # Check that two Fantasy teams do not share a code.
    code_counts = Counter(TEAM_CODES.values())

    duplicate_codes = sorted(
        code
        for code, count in code_counts.items()
        if count > 1
    )

    # Identify fixture teams using supported column formats.
    team_columns = find_fixture_team_columns(
        fixture_columns
    )

    fixture_team_names = []
    unknown_fixture_teams = []
    duplicate_fixture_teams = []
    fixture_codes = []

    if team_columns:
        first_column, second_column = team_columns

        for row in fixtures:
            for column in team_columns:
                name = row.get(column, "").strip()

                if not name:
                    continue

                fixture_team_names.append(name)

                if name in TEAM_CODES:
                    fixture_codes.append(
                        TEAM_CODES[name]
                    )
                else:
                    unknown_fixture_teams.append(name)

        fixture_code_counts = Counter(
            fixture_codes
        )

        duplicate_fixture_teams = sorted(
            code
            for code, count
            in fixture_code_counts.items()
            if count > 1
        )

    report = {
        "status": "PASS",
        "fixture_games": len(fixtures),
        "teams_expected": len(TEAM_CODES),
        "teams_matched": len(matched),
        "matched": matched,
        "unmatched": unmatched,
        "dataset_team_codes": sorted(
            dataset_teams
        ),
        "duplicate_codes": duplicate_codes,
        "fixture_columns": fixture_columns,
        "fixture_team_columns": (
            list(team_columns)
            if team_columns
            else None
        ),
        "fixture_teams_found": len(
            fixture_team_names
        ),
        "unknown_fixture_teams": sorted(
            set(unknown_fixture_teams)
        ),
        "duplicate_fixture_teams": (
            duplicate_fixture_teams
        ),
    }

    errors = []

    if unmatched:
        errors.append(
            "Some team codes are missing "
            "from the dataset"
        )

    if duplicate_codes:
        errors.append(
            "Duplicate dataset team codes"
        )

    if len(fixtures) != 10:
        errors.append(
            f"Expected 10 fixtures, "
            f"found {len(fixtures)}"
        )

    if team_columns is None:
        errors.append(
            "Could not identify fixture "
            "team columns"
        )
    else:
        if unknown_fixture_teams:
            errors.append(
                "Unknown team names "
                "in fixtures.csv"
            )

        if duplicate_fixture_teams:
            errors.append(
                "Teams appear more than once "
                "in fixtures.csv"
            )

        if len(fixture_team_names) != 20:
            errors.append(
                "Expected 20 fixture team entries, "
                f"found {len(fixture_team_names)}"
            )

        if set(fixture_codes) != set(
            TEAM_CODES.values()
        ):
            errors.append(
                "Fixture teams do not cover "
                "all 20 EuroLeague teams"
            )

    if errors:
        report["status"] = "FAIL"

    report["errors"] = errors

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUT.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )

    if errors:
        raise SystemExit(
            "Fixture validation failed: "
            + "; ".join(errors)
        )

    print(
        "SUCCESS: All 20 teams validated."
    )


if __name__ == "__main__":
    main()
