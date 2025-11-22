# morgoals

A lightweight Python script that checks for NHL players who were 40+ goal scorers last season, estimates how often they typically score based on last year's goals-per-game rate, and lists anyone who looks “past due” but has a game today.

## How it works

1. Fetch the current season ID and the previous season (to use as the baseline).
2. Pull last season's skater summary and filter to players with at least 40 regular-season goals.
3. Grab each player's game log for the current season to find their most recent goal date.
4. Compute an expected days-between-goals value using last season's goals-per-game rate and the average spacing between games on the player's current schedule.
5. Mark players as past due when their days since last goal exceed that expected interval and they have a game scheduled today.

## Running the check

```bash
pip install -r requirements.txt
python nhl_due.py
```

The script prints a formatted table of “past due” scorers with games today, or a message if no players meet the criteria.

You can schedule this command to run daily (e.g., with `cron`) to keep the list up to date.
