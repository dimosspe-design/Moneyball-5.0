"""
Moneyball 5.0 — Market HTML Structure Diagnostic

Inspects the public HTML structure of Fantasy Edge IQ.

Does not scrape authenticated pages.
Does not change Fantasy prices.
Does not execute transfers.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


URL = "https://www.fantasyedgeiq.com/euroleague/players"
OUTPUT = Path("results/market_structure_diagnostic.json")


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "source": "Fantasy Edge IQ",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "html_tables": 0,
        "table_headers": [],
        "player_name_occurrences": 0,
        "player_context_samples": [],
        "embedded_json_scripts": 0,
        "potential_player_rows": 0,
        "extraction_verified": False,
        "error": None,
    }

    try:
        response = requests.get(
            URL,
            timeout=20,
            headers={
                "User-Agent": "Moneyball5-SourceDiagnostic/1.0"
            },
        )
        report["http_status"] = response.status_code
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        tables = soup.find_all("table")
        report["html_tables"] = len(tables)

        for table in tables[:5]:
            headers = [
                th.get_text(" ", strip=True)
                for th in table.find_all("th")
            ]
            report["table_headers"].append(headers)

        scripts = soup.find_all(
            "script",
            type=re.compile(r"json", re.IGNORECASE),
        )
        report["embedded_json_scripts"] = len(scripts)

        text = soup.get_text(" ", strip=True)

        matches = list(
            re.finditer(
                r"Elijah\s+Bryant|Bryant\s+Elijah",
                text,
                flags=re.IGNORECASE,
            )
        )

        report["player_name_occurrences"] = len(matches)

        for match in matches[:3]:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 200)

            report["player_context_samples"].append(
                text[start:end]
            )

        report["potential_player_rows"] = sum(
            len(table.find_all("tr"))
            for table in tables
        )

    except requests.RequestException as exc:
        report["error"] = str(exc)

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nNO TRANSFERS EXECUTED")


if __name__ == "__main__":
    main()
