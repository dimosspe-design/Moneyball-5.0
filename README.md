# Moneyball 5.0 v6 — integration preparation, not live deployment

## What works
- Reusable baseline training/backtest via `python weekly.py --data euroleague-2026-2.zip --out weekly_output`.
- Guarded lineup optimizer **only** after verified full-market CSV and complete roster are supplied.
- Conditional team-level Monte Carlo diagnostic from empirical out-of-sample residuals:
  `python team_simulator.py --lineups weekly_output/candidate_lineups.json --backtest weekly_output/chronological_backtest.csv --out weekly_output/team_scenarios.json`
- GitHub Actions *manual* research workflow template at `.github/workflows/weekly.yml`, requiring an authorized updated `data/euroleague.zip` committed to a private repository.

## What is NOT complete
1. **Live Fantasy market connector:** No authenticated/licensed source or verified full-market export supplied. Never scrape private endpoints, request credentials, or fabricate market data. Supply an authorized current CSV.
2. **Calibrated team upside / T1-T2:** Monte Carlo estimates conditional distributions only, using independent residuals. It is not a calibrated probability of final team score, and turn_planner.py is still a simple conditional decision aid. Requires official fantasy score targets, coach outcomes, injury/participation observations and retrospective turn-state histories for validation.
3. **Autonomous weekly runner:** GitHub workflow is provided but NOT installed or running. Requires user to connect GitHub, select a private repo, and approve repository setup. No scheduled execution until authorized, deployed and tested. Existing ChatGPT monitor is separate.

## Safety
No trades or account actions are executed. Every candidate requires user approval. The official Fantasy scoring target and matchup data remain subject to independent verification (see v5 README).
