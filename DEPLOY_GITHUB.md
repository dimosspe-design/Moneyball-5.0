# Deploy Moneyball 5.0 to GitHub

Repository: https://github.com/dimosspe-design/Moneyball-5.0 (user-provided; private repository not accessible to assistant)

1. Download this package and extract it locally.
2. In your **private** GitHub repository, select **Add file → Upload files**. Upload the *contents* of `Moneyball_5_0_v6/` to the repository root, including the `.github/workflows/weekly.yml` path. GitHub's browser upload may not preserve hidden nested folders; if `.github/workflows/weekly.yml` is missing, create it using **Add file → Create new file** and paste the workflow contents, or use GitHub Desktop/git.
3. Confirm `model.py`, `weekly.py`, `readiness.py`, `requirements.txt` and `data/euroleague.zip` are at the repository root or specified paths. The ZIP included here is the **historical R11 snapshot**, not automatically fresh data.
4. Open **Actions → Moneyball 5.0 weekly research → Run workflow**. Inspect logs and download artifact `moneyball-research-*`.
5. GitHub Actions will then schedule a run each Monday at 07:00 UTC, subject to GitHub's scheduling behavior and repository settings. It **does not fetch new data automatically**; you must update `data/euroleague.zip` from an authorized source. Running on stale data will repeat old projections.
6. The workflow does **not** read your Fantasy account, fetch market prices, place trades, or validate availability. Those remain separate prerequisites.

Security: Keep the repository private. Do not upload credentials, TOTP seeds, recovery codes, personal account screenshots, or private tokens. Do not commit unauthorized third-party data.
