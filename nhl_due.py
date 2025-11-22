"""
Daily NHL goal scoring due tracker.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SEASONS_API = "https://statsapi.web.nhl.com/api/v1/seasons"
SKATER_SUMMARY_API = "https://api.nhle.com/stats/rest/en/skater/summary"
PLAYER_GAMELOG_API = "https://api.nhle.com/stats/rest/en/player/summary"
SCHEDULE_API = "https://statsapi.web.nhl.com/api/v1/schedule"


@dataclasses.dataclass
class PlayerBaseline:
    player_id: int
    name: str
    team_id: int
    team_abbrev: str
    goals: int
    games_played: int

    @property
    def goals_per_game(self) -> float:
        if self.games_played == 0:
            return 0.0
        return self.goals / self.games_played


@dataclasses.dataclass
class PlayerDueStatus:
    player: PlayerBaseline
    last_goal_date: date
    days_since_last_goal: int
    expected_days_between_goals: float
    next_game_opponent: str
    next_game_start_time: str


class NhlApiError(RuntimeError):
    """Raised when the NHL API responds with a non-200 status."""


def _http_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


SESSION = _http_session()


def _get_json(url: str) -> Dict:
    try:
        response = SESSION.get(url, timeout=20)
    except requests.exceptions.RequestException as exc:  # pragma: no cover - network guard
        raise NhlApiError(
            "Network error while reaching NHL stats API. "
            "Check your internet connection or DNS and try again."
        ) from exc

    if not response.ok:
        raise NhlApiError(f"Failed to fetch {url}: {response.status_code}")
    return response.json()


def get_current_season_id() -> str:
    data = _get_json(f"{SEASONS_API}/current")
    return data["seasons"][0]["seasonId"]


def get_previous_season_id(current_season_id: str) -> str:
    return str(int(current_season_id) - 1)


def get_season_dates(season_id: str) -> Dict[str, str]:
    data = _get_json(f"{SEASONS_API}/{season_id}")
    season_info = data["seasons"][0]
    return {
        "regularSeasonStart": season_info["regularSeasonStartDate"],
        "regularSeasonEnd": season_info["regularSeasonEndDate"],
    }


def fetch_top_goal_scorers(season_id: str, min_goals: int = 40) -> List[PlayerBaseline]:
    params = "?isAggregate=false&isGame=false&reportName=skatersummary&cayenneExp="
    params += f"seasonId={season_id} and gameTypeId=2"
    url = f"{SKATER_SUMMARY_API}{params}"
    data = _get_json(url)
    players = []
    for entry in data.get("data", []):
        goals = int(entry.get("goals", 0))
        if goals < min_goals:
            continue
        players.append(
            PlayerBaseline(
                player_id=int(entry["playerId"]),
                name=entry["playerName"],
                team_id=int(entry["teamId"]),
                team_abbrev=entry.get("teamAbbrevs", ""),
                goals=goals,
                games_played=int(entry.get("gamesPlayed", 0)),
            )
        )
    return players


def fetch_player_gamelog(player_id: int, season_id: str) -> List[Dict]:
    params = (
        "?isAggregate=false&isGame=true&reportName=playergamelog"
        f"&cayenneExp=playerId={player_id} and seasonId={season_id}"
    )
    url = f"{PLAYER_GAMELOG_API}{params}"
    data = _get_json(url)
    return data.get("data", [])


def fetch_schedule_for_range(team_id: int, start: date, end: date) -> List[Dict]:
    url = (
        f"{SCHEDULE_API}?teamId={team_id}&startDate={start.isoformat()}"
        f"&endDate={end.isoformat()}"
    )
    data = _get_json(url)
    return data.get("dates", [])


def fetch_schedule_for_day(target_date: date) -> Dict:
    url = f"{SCHEDULE_API}?date={target_date.isoformat()}"
    return _get_json(url)


def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _extract_schedule_dates(schedule: Iterable[Dict]) -> List[date]:
    dates: List[date] = []
    for block in schedule:
        try:
            dates.append(_parse_date(block["date"]))
        except KeyError:
            continue
    return dates


def average_days_between_games(dates: List[date]) -> float:
    if len(dates) < 2:
        return 0.0
    sorted_dates = sorted(dates)
    deltas = [
        (later - earlier).days
        for earlier, later in zip(sorted_dates, sorted_dates[1:])
    ]
    return sum(deltas) / len(deltas)


def last_goal_date(game_log: List[Dict]) -> Optional[date]:
    goal_games = [
        _parse_date(entry["gameDate"])
        for entry in game_log
        if int(entry.get("goals", 0)) > 0
    ]
    return max(goal_games) if goal_games else None


def games_played_dates(game_log: List[Dict]) -> List[date]:
    return [_parse_date(entry["gameDate"]) for entry in game_log]


def _next_game_for_team(schedule_today: Dict, team_id: int) -> Optional[Dict]:
    for date_block in schedule_today.get("dates", []):
        for game in date_block.get("games", []):
            teams = game.get("teams", {})
            for side in ("home", "away"):
                team = teams.get(side, {}).get("team")
                if team and team.get("id") == team_id:
                    opponent_side = "away" if side == "home" else "home"
                    opponent_team = teams.get(opponent_side, {}).get("team", {})
                    return {
                        "opponent": opponent_team.get("name", ""),
                        "startTime": game.get("gameDate", ""),
                    }
    return None


def evaluate_due_players(today: Optional[date] = None) -> List[PlayerDueStatus]:
    today = today or date.today()
    current_season = get_current_season_id()
    previous_season = get_previous_season_id(current_season)
    season_dates = get_season_dates(current_season)
    season_start = _parse_date(season_dates["regularSeasonStart"])

    schedule_today = fetch_schedule_for_day(today)
    teams_playing_today = set()
    for date_block in schedule_today.get("dates", []):
        for game in date_block.get("games", []):
            for side in ("home", "away"):
                team = game.get("teams", {}).get(side, {}).get("team")
                if team:
                    teams_playing_today.add(team.get("id"))

    baselines = [
        player
        for player in fetch_top_goal_scorers(previous_season)
        if player.team_id in teams_playing_today
    ]

    due_players: List[PlayerDueStatus] = []
    for player in baselines:
        game_log = fetch_player_gamelog(player.player_id, current_season)
        last_goal = last_goal_date(game_log)
        if not last_goal:
            continue
        played_dates = games_played_dates(game_log)
        team_schedule = fetch_schedule_for_range(player.team_id, season_start, today)
        schedule_dates = _extract_schedule_dates(team_schedule)
        avg_days = average_days_between_games(schedule_dates or played_dates)
        if avg_days == 0:
            continue
        if player.goals_per_game == 0:
            continue
        expected_days = (1 / player.goals_per_game) * avg_days
        days_since_goal = (today - last_goal).days
        if days_since_goal <= expected_days:
            continue
        next_game = _next_game_for_team(schedule_today, player.team_id)
        if not next_game:
            continue
        due_players.append(
            PlayerDueStatus(
                player=player,
                last_goal_date=last_goal,
                days_since_last_goal=days_since_goal,
                expected_days_between_goals=expected_days,
                next_game_opponent=next_game["opponent"],
                next_game_start_time=next_game["startTime"],
            )
        )
    return due_players


def format_due_players(due_players: List[PlayerDueStatus]) -> str:
    if not due_players:
        return "No players are past due based on last season's scoring rate."
    lines = [
        "Past due goal scorers with games today:",
        "Player | Team | Days Since Last Goal | Expected Days | Opponent | Game Time",
        "------ | ---- | -------------------- | ------------- | -------- | ---------",
    ]
    for entry in due_players:
        lines.append(
            (
                f"{entry.player.name} | {entry.player.team_abbrev} | "
                f"{entry.days_since_last_goal} | "
                f"{entry.expected_days_between_goals:.1f} | "
                f"{entry.next_game_opponent} | {entry.next_game_start_time}"
            )
        )
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        due_players = evaluate_due_players()
        print(format_due_players(due_players))
    except Exception as exc:  # pragma: no cover - CLI safety
        print(f"Error: {exc}")
