import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ATHENS = ZoneInfo("Europe/Athens")


def load_schedule(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        required = {
            "round",
            "first_game_utc",
            "fantasy_deadline_utc",
        }

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f"Required columns: {sorted(required)}"
            )

        rounds = []

        for row in reader:
            first_game = datetime.fromisoformat(
                row["first_game_utc"].replace("Z", "+00:00")
            )

            deadline = datetime.fromisoformat(
                row["fantasy_deadline_utc"].replace(
                    "Z", "+00:00"
                )
            )

            if first_game.tzinfo is None:
                raise ValueError("Timezone required")

            if deadline.tzinfo is None:
                raise ValueError("Timezone required")

            rounds.append({
                "round": row["round"],
                "first_game": first_game,
                "deadline": deadline,
            })

    return sorted(rounds, key=lambda x: x["deadline"])


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--schedule",
        default="schedule.csv",
    )

    parser.add_argument(
        "--hours-before",
        type=int,
        default=24,
    )

    parser.add_argument(
        "--out",
        default="results/matchday_status.json",
    )

    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    rounds = load_schedule(args.schedule)

    upcoming = [
        r for r in rounds
        if r["deadline"] > now
    ]

    if not upcoming:
        status = {
            "status": "NO_UPCOMING_ROUND",
            "checked_at_utc": now.isoformat(),
        }

    else:
        next_round = upcoming[0]

        hours_left = (
            next_round["deadline"] - now
        ).total_seconds() / 3600

        should_prepare = (
            0 < hours_left <= args.hours_before
        )

        status = {
            "status": (
                "PREPARE_PROJECTIONS"
                if should_prepare
                else "WAITING"
            ),
            "round": next_round["round"],
            "hours_until_deadline": round(
                hours_left, 2
            ),
            "deadline_athens": (
                next_round["deadline"]
                .astimezone(ATHENS)
                .isoformat()
            ),
            "first_game_athens": (
                next_round["first_game"]
                .astimezone(ATHENS)
                .isoformat()
            ),
        }

    output = Path(args.out)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            status,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(
        status,
        indent=2,
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
