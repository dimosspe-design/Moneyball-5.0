import csv
import gzip
import io
import json
import zipfile
from pathlib import Path

DATA = Path("euroleague.zip")
FIXTURES = Path("fixtures.csv")
OUT = Path("results/fixtures_validation.json")

ALIASES = {
    "Dubai Basketball": ["Dubai"],
    "Anadolu Efes": ["Efes", "Anadolu"],
    "Maccabi Tel Aviv": ["Maccabi"],
    "Olympiacos": ["Olympiacos"],
    "Zalgiris Kaunas": ["Zalgiris"],
    "Bayern Munich": ["Bayern"],
    "Fenerbahce": ["Fenerbahce"],
    "ASVEL": ["ASVEL"],
    "Baskonia": ["Baskonia"],
    "Hapoel Tel Aviv": ["Hapoel"],
    "Olimpia Milano": ["Milano", "Milan"],
    "Crvena Zvezda": ["Crvena", "Zvezda"],
    "Barcelona": ["Barcelona"],
    "Paris Basketball": ["Paris"],
    "Partizan": ["Partizan"],
    "Valencia Basket": ["Valencia"],
    "Virtus Bologna": ["Virtus"],
    "Panathinaikos": ["Panathinaikos"],
    "Besiktas": ["Besiktas"],
    "Real Madrid": ["Real Madrid"],
}

def normalize(value):
    return "".join(
        c for c in str(value).casefold()
        if c.isalnum()
    )

def main():
    with open(FIXTURES, newline="", encoding="utf-8-sig") as f:
        fixtures = list(csv.DictReader(f))

    if not fixtures:
        raise ValueError("fixtures.csv is empty")

    with zipfile.ZipFile(DATA) as z:
        with gzip.open(
            io.BytesIO(z.read("team_games-2026.csv.gz")),
            "rt",
            encoding="utf-8-sig",
        ) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    columns = rows[0].keys()
    print("Available columns:", list(columns))

    team_columns = [
        c for c in columns
        if "team" in c.lower()
    ]

    print("Candidate team columns:", team_columns)

    if not team_columns:
        raise ValueError(
            "No team-related column found. "
            "Inspect dataset schema."
        )

    values = set()

    for row in rows:
        for col in team_columns:
            value = row.get(col, "")
            if value:
                values.add(value)

    matched = {}
    unmatched = []

    for team, aliases in ALIASES.items():
        candidates = [team] + aliases

        found = sorted(
            v for v in values
            if any(
                normalize(alias) in normalize(v)
                for alias in candidates
            )
        )

        if found:
            matched[team] = found
        else:
            unmatched.append(team)

    report = {
        "fixture_games": len(fixtures),
        "teams_expected": len(ALIASES),
        "teams_matched": len(matched),
        "matched": matched,
        "unmatched": unmatched,
        "candidate_columns": team_columns,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if unmatched:
        raise SystemExit(
            f"Unmatched teams: {', '.join(unmatched)}"
        )

if __name__ == "__main__":
    main()
