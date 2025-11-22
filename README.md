# morgoals

A lightweight Python script that checks for NHL players who were 40+ goal scorers last season, estimates how often they typically score based on last year's goals-per-game rate, and lists anyone who looks “past due” but has a game today.

## How it works

1. Fetch the current season ID and the previous season (to use as the baseline).
2. Pull last season's skater summary and filter to players with at least 40 regular-season goals.
3. Grab each player's game log for the current season to find their most recent goal date.
4. Compute an expected days-between-goals value using last season's goals-per-game rate and the average spacing between games on the player's current schedule.
5. Mark players as past due when their days since last goal exceed that expected interval and they have a game scheduled today.

## Running the check

### macOS quickstart

```bash
# 1) Make sure you have Python 3 installed (macOS 12+ ships with it, or use Homebrew: brew install python)
# 2) From the repo root, create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3) Install dependencies and run the script
pip install -r requirements.txt
python nhl_due.py
```

The script prints a formatted table of “past due” scorers with games today, or a message if no players meet the criteria. You can schedule the command to run daily with `cron`, macOS Calendar alerts that run scripts, or a GitHub Action if you prefer to offload execution from your Mac.

### Troubleshooting network errors

If you see a message like `Network error while reaching NHL stats API` or `Failed to resolve 'statsapi.web.nhl.com'`, double-check that you have an active internet connection and that your DNS resolver can reach `statsapi.web.nhl.com` and `api.nhle.com`. Corporate or hotel networks sometimes block these hosts; connecting to a different network or VPN can clear it up. The script now retries transient failures automatically, so running it again after connectivity returns should succeed.
