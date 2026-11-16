"""
Moneyball 5.0 — Public Market Source Diagnostic

Checks whether Fantasy Edge IQ exposes player data
in its public HTML response.

No login.
No transfers.
No changes to verified market data.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests


URL = "https://www.fantasyedgeiq.com/euroleague/players"

OUTPUT = Path("results/market_source_diagnostic.json")


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "source": "Fantasy Edge IQ",
        "url": URL,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "html_length": 0,
        "player_name_found": False,
        "credit_value_found": False,
        "automatic_extraction_ready": False,
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
        report["html_length"] = len(response.text)

        response.raise_for_status()

        html = response.text

        report["player_name_found"] = bool(
            re.search(
                r"Elijah\s+Bryant|Bryant\s+Elijah",
                html,
                flags=re.IGNORECASE,
            )
        )

        report["credit_value_found"] = bool(
            re.search(r"17[.,]6", html)
        )

        report["automatic_extraction_ready"] = (
            report["player_name_found"]
            and report["credit_value_found"]
        )

    except requests.RequestException as exc:
        report["error"] = str(exc)

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if report["automatic_extraction_ready"]:
        print(
            "\nSUCCESS: Player name and reference price "
            "are visible in the HTML response."
        )
        print(
            "NOTE: This does not yet prove that a complete "
            "market table can be extracted."
        )
    else:
        print(
            "\nCHECK REQUIRED: Reference player/price "
            "not found together in the HTML response."
        )
        print(
            "The page may use JavaScript or another "
            "data-loading mechanism."
        )

    print("\nNO TRANSFERS EXECUTED")


if __name__ == "__main__":
    main()
