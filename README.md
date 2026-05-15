# Quick Cricket Scorebook

A mobile-friendly Streamlit app for quick cricket tournament scoring.

## What it does

- Add teams once
- Save match scores quickly
- Auto-detect winner or tie
- Maintain all match records
- Create an automatic points table with P, W, L, T/NR, points and NRR
- Export points table and match records as CSV
- Download and restore a full database backup
- Works well on mobile

## One-time GitHub setup

1. Create a new GitHub repository, for example `cricket-scorebook`.
2. Upload these files and folders to the repository:
   - `app.py`
   - `requirements.txt`
   - `.streamlit/config.toml`
   - `.gitignore`
   - `README.md`
3. Commit the files.

## Deploy free on Streamlit Community Cloud

1. Go to Streamlit Community Cloud.
2. Sign in with GitHub.
3. Click **New app**.
4. Select your GitHub repository.
5. Set the main file path as:

```text
app.py
```

6. Click **Deploy**.
7. Open the deployed app link on your phone and share it with scorers/captains.

## Mobile use tips

- Open the Streamlit app link in Chrome or Safari.
- Use **Add to Home Screen** so it behaves like an app.
- Use the **Backup** tab after every few matches.
- Restore the latest backup if the app is redeployed or data resets.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Important note on data

The app stores records in `scoreboard.db`. On Streamlit Community Cloud, storage can reset after redeploys or restarts. Use the **Backup** tab to download and restore your tournament data.

## Cricket overs format

Use cricket notation:

- `4.5` means 4 overs and 5 balls
- `4.6` is invalid
- If a team is all out, NRR uses the full allotted overs
