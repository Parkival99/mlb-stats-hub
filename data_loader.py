"""
Data loading and caching layer for MLB stats.
Uses pybaseball for Statcast data and MLB Stats API for everything else.
FanGraphs scraping is unreliable (403s), so traditional stats come from MLB API.
"""

import datetime
import requests
import pandas as pd
import streamlit as st
from pybaseball import statcast, statcast_batter, cache

# Enable pybaseball caching to avoid repeated scrapes
cache.enable()

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"


def _safe_float(val) -> float:
    """Coerce an MLB API stat to float, tolerating its placeholder strings.

    For players with no innings/at-bats in a window the API returns sentinels
    like '-.--', '.---', or '*.**' instead of a number; those (and None/blank)
    all map to 0.0 so a single empty line can't crash a whole leaderboard.
    """
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Player name lookup (Statcast only has pitcher names, not batter names)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)  # cache for 24 hours
def lookup_player_names(player_ids: list[int]) -> dict[int, str]:
    """Batch lookup player names from MLB Stats API."""
    if not player_ids:
        return {}

    names = {}
    # API accepts up to ~100 IDs at a time
    batch_size = 100
    for i in range(0, len(player_ids), batch_size):
        batch = player_ids[i:i + batch_size]
        ids_str = ",".join(str(pid) for pid in batch)
        url = f"{MLB_API_BASE}/people?personIds={ids_str}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            for person in resp.json().get("people", []):
                names[person["id"]] = person["fullName"]
        except Exception:
            pass
    return names


# ---------------------------------------------------------------------------
# Statcast data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def get_statcast_data(start_date: str, end_date: str) -> pd.DataFrame:
    """Pull Statcast pitch-level data (regular season only)."""
    try:
        df = statcast(start_dt=start_date, end_dt=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        # Filter to regular season games only — excludes spring training (S),
        # postseason (F/D/L/W), and all-star (A) data that inflates stats.
        if "game_type" in df.columns:
            df = df[df["game_type"] == "R"]
        return df
    except Exception as e:
        st.warning(f"Could not load Statcast data: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def get_statcast_batter_data(player_id: int, start_date: str, end_date: str) -> pd.DataFrame:
    """Pull Statcast pitch-level data for a SINGLE batter.

    Scoped to one player via statcast_batter, so it returns a few hundred rows
    instead of the whole league — small enough to stay reliable on Streamlit
    Cloud. This is the only Statcast pull the app still makes, and it powers the
    read-only spray chart, zone grid, and exit-velocity panel on the Player page
    (no in-page date re-query, so it can't be widened into a crash).
    """
    try:
        df = statcast_batter(start_date, end_date, player_id)
        if df is None or df.empty:
            return pd.DataFrame()
        if "game_type" in df.columns:
            df = df[df["game_type"] == "R"]
        return df
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Batting — from Statcast
# ---------------------------------------------------------------------------

def compute_batting_leaders(sc_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Statcast pitch-level data into per-batter stats.
    Filters out pitchers, deduplicates plate appearances, and resolves
    correct batter names via MLB API.
    """
    if sc_df.empty:
        return pd.DataFrame()

    # Filter to at-bat events (rows where a PA concluded)
    batted = sc_df.dropna(subset=["events"])

    if batted.empty:
        return pd.DataFrame()

    # CRITICAL: Deduplicate plate appearances.
    # Statcast can have duplicate rows or multiple pitches with the events
    # field set. Keep only one row per PA (game + at_bat_number + batter).
    dedup_cols = ["game_pk", "at_bat_number", "batter"]
    available_dedup = [c for c in dedup_cols if c in batted.columns]
    if len(available_dedup) == len(dedup_cols):
        batted = batted.drop_duplicates(subset=dedup_cols, keep="last")

    # Identify pitchers: players whose ID appears more as 'pitcher' than 'batter'
    pitcher_counts = sc_df["pitcher"].value_counts()
    batter_counts = sc_df["batter"].value_counts()
    pitcher_ids = set()
    for pid in pitcher_counts.index:
        if pitcher_counts.get(pid, 0) > batter_counts.get(pid, 0):
            pitcher_ids.add(pid)
    batted = batted[~batted["batter"].isin(pitcher_ids)]

    if batted.empty:
        return pd.DataFrame()

    hits = ["single", "double", "triple", "home_run"]

    grouped = batted.groupby("batter").agg(
        PA=("events", "count"),
        H=("events", lambda x: x.isin(hits).sum()),
        _2B=("events", lambda x: (x == "double").sum()),
        _3B=("events", lambda x: (x == "triple").sum()),
        HR=("events", lambda x: (x == "home_run").sum()),
        BB=("events", lambda x: (x == "walk").sum()),
        SO=("events", lambda x: (x == "strikeout").sum()),
        HBP=("events", lambda x: (x == "hit_by_pitch").sum()),
        SF=("events", lambda x: (x == "sac_fly").sum()),
    ).reset_index()

    # Calculate exit velocity from batted ball events only (bb_type not null)
    bbe = sc_df.dropna(subset=["launch_speed", "bb_type"])
    if not bbe.empty:
        ev_stats = bbe.groupby("batter")["launch_speed"].agg(
            AVG_EV="mean", MAX_EV="max"
        ).reset_index()
        grouped = grouped.merge(ev_stats, on="batter", how="left")
    else:
        grouped["AVG_EV"] = None
        grouped["MAX_EV"] = None

    # Lookup real batter names from MLB API
    batter_ids = grouped["batter"].tolist()
    name_map = lookup_player_names(batter_ids)
    grouped["Name"] = grouped["batter"].map(name_map).fillna("Unknown")

    # Derive team: Top inning = away team batting, Bot = home team
    if "inning_topbot" in batted.columns and "home_team" in batted.columns:
        def _get_team(sub):
            row = sub.iloc[0]
            if row.get("inning_topbot") == "Top":
                return row.get("away_team", "")
            return row.get("home_team", "")
        team_map = batted.groupby("batter").apply(_get_team, include_groups=False)
        grouped["Team"] = grouped["batter"].map(team_map).fillna("")
    else:
        grouped["Team"] = ""

    # Compute AB (PA minus BB, HBP, SF)
    grouped["AB"] = grouped["PA"] - grouped["BB"] - grouped["HBP"] - grouped["SF"]
    grouped["AB"] = grouped["AB"].clip(lower=1)

    grouped["AVG"] = (grouped["H"] / grouped["AB"]).round(3)
    grouped["HR_PA"] = (grouped["HR"] / grouped["PA"]).round(3)
    grouped["OBP"] = ((grouped["H"] + grouped["BB"] + grouped["HBP"]) / grouped["PA"]).round(3)

    # SLG = TB / AB
    grouped["TB"] = (
        (grouped["H"] - grouped["_2B"] - grouped["_3B"] - grouped["HR"])  # singles
        + grouped["_2B"] * 2 + grouped["_3B"] * 3 + grouped["HR"] * 4
    )
    grouped["SLG"] = (grouped["TB"] / grouped["AB"]).round(3)
    grouped["OPS"] = (grouped["OBP"] + grouped["SLG"]).round(3)

    return grouped.sort_values("PA", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Pitching — from Statcast
# ---------------------------------------------------------------------------

def compute_pitching_leaders(sc_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Statcast data into per-pitcher metrics."""
    if sc_df.empty:
        return pd.DataFrame()

    hits = ["single", "double", "triple", "home_run"]

    # For event-level stats (BF, H, K, etc.), deduplicate plate appearances
    # but keep all pitches for pitch-level stats (SwStr, TotalPitches)
    events_df = sc_df.dropna(subset=["events"])
    dedup_cols = ["game_pk", "at_bat_number", "batter"]
    available_dedup = [c for c in dedup_cols if c in events_df.columns]
    if len(available_dedup) == len(dedup_cols):
        events_df = events_df.drop_duplicates(subset=dedup_cols, keep="last")

    # Pitch-level aggregates (all pitches, no dedup)
    pitch_agg = sc_df.groupby("pitcher").agg(
        Name=("player_name", "first"),
        TotalPitches=("pitch_type", "count"),
        SwStr=("description", lambda x: x.isin([
            "swinging_strike", "swinging_strike_blocked"
        ]).sum()),
    ).reset_index()

    # Event-level aggregates (deduplicated PAs)
    event_agg = events_df.groupby("pitcher").agg(
        Strikeouts=("events", lambda x: (x == "strikeout").sum()),
        BF=("events", "count"),
        H=("events", lambda x: x.isin(hits).sum()),
        HR=("events", lambda x: (x == "home_run").sum()),
        BB=("events", lambda x: (x == "walk").sum()),
        HBP=("events", lambda x: (x == "hit_by_pitch").sum()),
    ).reset_index()

    grouped = pitch_agg.merge(event_agg, on="pitcher", how="left").fillna(0)

    # Derive pitcher's team: Top inning = home team pitching, Bot = away team
    if "inning_topbot" in sc_df.columns and "home_team" in sc_df.columns:
        def _get_pitcher_team(sub):
            row = sub.iloc[0]
            if row.get("inning_topbot") == "Top":
                return row.get("home_team", "")
            return row.get("away_team", "")
        p_team_map = sc_df.groupby("pitcher").apply(_get_pitcher_team, include_groups=False)
        grouped["Team"] = grouped["pitcher"].map(p_team_map).fillna("")
    else:
        grouped["Team"] = ""

    grouped["WhiffRate"] = (grouped["SwStr"] / grouped["TotalPitches"] * 100).round(1)

    # Estimate IP: ~3 batters faced per inning
    grouped["IP_est"] = (grouped["BF"] / 3).round(1).clip(lower=0.1)

    # K/9
    grouped["K9"] = (grouped["Strikeouts"] / grouped["IP_est"] * 9).round(1)

    # ERA estimate: use runs created approach
    # Approximate earned runs = 0.5*H + 0.33*BB + 0.33*HBP + 1.4*HR (rough linear weight)
    grouped["ER_est"] = (
        0.5 * grouped["H"] + 0.33 * grouped["BB"]
        + 0.33 * grouped["HBP"] + 1.4 * grouped["HR"]
    )
    grouped["ERA"] = (grouped["ER_est"] / grouped["IP_est"] * 9).round(2)

    # WHIP
    grouped["WHIP"] = ((grouped["H"] + grouped["BB"]) / grouped["IP_est"]).round(2)

    return grouped.sort_values("TotalPitches", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# MLB Stats API — traditional season stats (replaces FanGraphs)
# ---------------------------------------------------------------------------

def _parse_hitting_splits(data: dict) -> pd.DataFrame:
    """Turn an MLB Stats API hitting-stats payload into a tidy DataFrame.
    Shared by the season and date-range queries since both return the same
    split/stat shape. A player traded mid-range can appear in more than one
    split, so rows are aggregated back to one line per player.
    """
    rows = []
    for split in data.get("stats", []):
        for entry in split.get("splits", []):
            s = entry.get("stat", {})
            player = entry.get("player", {})
            team = entry.get("team", {})
            rows.append({
                "Name": player.get("fullName", ""),
                "player_id": player.get("id"),
                "Team": team.get("abbreviation", ""),
                "G": s.get("gamesPlayed", 0),
                "PA": s.get("plateAppearances", 0),
                "AB": s.get("atBats", 0),
                "H": s.get("hits", 0),
                "2B": s.get("doubles", 0),
                "3B": s.get("triples", 0),
                "HR": s.get("homeRuns", 0),
                "RBI": s.get("rbi", 0),
                "BB": s.get("baseOnBalls", 0),
                "SO": s.get("strikeOuts", 0),
                "SB": s.get("stolenBases", 0),
                "AVG": _safe_float(s.get("avg")),
                "OBP": _safe_float(s.get("obp")),
                "SLG": _safe_float(s.get("slg")),
                "OPS": _safe_float(s.get("ops")),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Collapse multi-team (traded) players into one row: counting stats sum,
    # rate stats are recomputed from the pooled totals so they stay correct.
    counting = ["G", "PA", "AB", "H", "2B", "3B", "HR", "RBI", "BB", "SO", "SB"]
    if df["player_id"].duplicated().any():
        agg = {c: "sum" for c in counting}
        agg["Name"] = "first"
        agg["Team"] = lambda x: "/".join(sorted(set(x)))
        df = df.groupby("player_id", as_index=False).agg(agg)
        ab = df["AB"].clip(lower=1)
        df["AVG"] = (df["H"] / ab).round(3)
        df["OBP"] = ((df["H"] + df["BB"]) / df["PA"].clip(lower=1)).round(3)
        tb = (df["H"] - df["2B"] - df["3B"] - df["HR"]) + df["2B"] * 2 + df["3B"] * 3 + df["HR"] * 4
        df["SLG"] = (tb / ab).round(3)
        df["OPS"] = (df["OBP"] + df["SLG"]).round(3)

    return df.sort_values("PA", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=900, show_spinner=False)
def get_mlb_batting_stats(season: int) -> pd.DataFrame:
    """Fetch full-season batting stats from MLB Stats API."""
    url = (
        f"{MLB_API_BASE}/stats"
        f"?stats=season&group=hitting&season={season}&sportId=1"
        f"&limit=1000&offset=0"
        f"&sortStat=plateAppearances&order=desc"
        f"&hydrate=team"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return _parse_hitting_splits(resp.json())
    except Exception as e:
        st.warning(f"Could not load MLB batting stats: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def get_mlb_batting_stats_range(start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch batting stats aggregated over a date range from the MLB Stats API.

    Uses the byDateRange split, which returns per-player totals for the window
    in a single fast call — unlike scraping pitch-level Statcast, this stays
    well within Streamlit Cloud's memory/time limits for any range.
    """
    url = (
        f"{MLB_API_BASE}/stats"
        f"?stats=byDateRange&group=hitting&sportId=1"
        f"&startDate={start_date}&endDate={end_date}"
        f"&limit=1000&offset=0"
        f"&sortStat=plateAppearances&order=desc"
        f"&hydrate=team"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return _parse_hitting_splits(resp.json())
    except Exception as e:
        st.warning(f"Could not load batting stats for this date range: {e}")
        return pd.DataFrame()


def _parse_pitching_splits(data: dict) -> pd.DataFrame:
    """Turn an MLB Stats API pitching-stats payload into a tidy DataFrame.
    Shared by the season and date-range queries. Multi-team (traded) pitchers
    are pooled into one row with rate stats recomputed from the totals.
    """
    rows = []
    for split in data.get("stats", []):
        for entry in split.get("splits", []):
            s = entry.get("stat", {})
            player = entry.get("player", {})
            team = entry.get("team", {})
            rows.append({
                "Name": player.get("fullName", ""),
                "player_id": player.get("id"),
                "Team": team.get("abbreviation", ""),
                "W": s.get("wins", 0),
                "L": s.get("losses", 0),
                "ERA": _safe_float(s.get("era")),
                "G": s.get("gamesPlayed", 0),
                "GS": s.get("gamesStarted", 0),
                "IP": _safe_float(s.get("inningsPitched")),
                "SO": s.get("strikeOuts", 0),
                "BB": s.get("baseOnBalls", 0),
                "H": s.get("hits", 0),
                "HR": s.get("homeRuns", 0),
                "ER": s.get("earnedRuns", 0),
                "WHIP": _safe_float(s.get("whip")),
                "K9": _safe_float(s.get("strikeoutsPer9Inn")),
                "BB9": _safe_float(s.get("walksPer9Inn")),
                "HR9": _safe_float(s.get("homeRunsPer9")),
                "AVG": _safe_float(s.get("avg")),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    counting = ["W", "L", "G", "GS", "IP", "SO", "BB", "H", "HR", "ER"]
    if df["player_id"].duplicated().any():
        agg = {c: "sum" for c in counting}
        agg["Name"] = "first"
        agg["Team"] = lambda x: "/".join(sorted(set(x)))
        df = df.groupby("player_id", as_index=False).agg(agg)
        ip = df["IP"].clip(lower=0.1)
        df["ERA"] = (df["ER"] / ip * 9).round(2)
        df["WHIP"] = ((df["H"] + df["BB"]) / ip).round(2)
        df["K9"] = (df["SO"] / ip * 9).round(2)
        df["BB9"] = (df["BB"] / ip * 9).round(2)
        df["HR9"] = (df["HR"] / ip * 9).round(2)
        df["AVG"] = 0.0  # not reconstructable from totals; hidden for traded pitchers

    return df.sort_values("IP", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=900, show_spinner=False)
def get_mlb_pitching_stats(season: int) -> pd.DataFrame:
    """Fetch full-season pitching stats from MLB Stats API."""
    url = (
        f"{MLB_API_BASE}/stats"
        f"?stats=season&group=pitching&season={season}&sportId=1"
        f"&limit=1000&offset=0"
        f"&sortStat=inningsPitched&order=desc"
        f"&hydrate=team"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return _parse_pitching_splits(resp.json())
    except Exception as e:
        st.warning(f"Could not load MLB pitching stats: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def get_mlb_pitching_stats_range(start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch pitching stats aggregated over a date range (recent-form view).

    Uses the byDateRange split — a single fast call that captures whatever
    starts/appearances a pitcher made in the window, so weekly starters show
    their recent few outings without scraping pitch-level data.
    """
    url = (
        f"{MLB_API_BASE}/stats"
        f"?stats=byDateRange&group=pitching&sportId=1"
        f"&startDate={start_date}&endDate={end_date}"
        f"&limit=1000&offset=0"
        f"&sortStat=inningsPitched&order=desc"
        f"&hydrate=team"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return _parse_pitching_splits(resp.json())
    except Exception as e:
        st.warning(f"Could not load pitching stats for this date range: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# MLB Stats API — live games, scores, matchups
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def get_todays_games() -> tuple[str, list[dict]]:
    """Fetch MLB schedule with scores.
    Before 7 AM local time, show yesterday's games so late-night final
    scores stay visible. Returns (label, games).
    """
    now = datetime.datetime.now()
    if now.hour < 7:
        target = (now - datetime.timedelta(days=1)).date()
        label = "Yesterday's Games"
    else:
        target = now.date()
        label = "Today's Games"

    date_str = target.isoformat()
    url = f"{MLB_API_BASE}/schedule?sportId=1&date={date_str}&hydrate=linescore,team,probablePitcher"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        games = []
        for date_entry in data.get("dates", []):
            for g in date_entry.get("games", []):
                # Parse game time — API gives UTC, convert to EST
                game_time_str = ""
                game_date_utc = g.get("gameDate", "")
                status_detail = g["status"]["detailedState"]
                if game_date_utc:
                    try:
                        utc_dt = datetime.datetime.fromisoformat(
                            game_date_utc.replace("Z", "+00:00")
                        )
                        est_dt = utc_dt - datetime.timedelta(hours=4)
                        game_time_str = est_dt.strftime("%I:%M %p ET").lstrip("0")
                    except Exception:
                        game_time_str = ""

                game = {
                    "game_id": g["gamePk"],
                    "status": status_detail,
                    "game_time": game_time_str,
                    "away_team": g["teams"]["away"]["team"]["name"],
                    "home_team": g["teams"]["home"]["team"]["name"],
                    "away_score": g["teams"]["away"].get("score", 0),
                    "home_score": g["teams"]["home"].get("score", 0),
                    "away_record": f'{g["teams"]["away"].get("leagueRecord", {}).get("wins", 0)}-{g["teams"]["away"].get("leagueRecord", {}).get("losses", 0)}',
                    "home_record": f'{g["teams"]["home"].get("leagueRecord", {}).get("wins", 0)}-{g["teams"]["home"].get("leagueRecord", {}).get("losses", 0)}',
                    "venue": g.get("venue", {}).get("name", ""),
                    "away_team_id": g["teams"]["away"]["team"].get("id"),
                    "home_team_id": g["teams"]["home"]["team"].get("id"),
                }
                away_pitcher = g["teams"]["away"].get("probablePitcher", {})
                home_pitcher = g["teams"]["home"].get("probablePitcher", {})
                game["away_pitcher"] = away_pitcher.get("fullName", "TBD")
                game["home_pitcher"] = home_pitcher.get("fullName", "TBD")
                game["away_pitcher_id"] = away_pitcher.get("id")
                game["home_pitcher_id"] = home_pitcher.get("id")
                games.append(game)
        return label, games
    except Exception as e:
        st.warning(f"Could not load games: {e}")
        return label, []


# ---------------------------------------------------------------------------
# Batter-vs-pitcher matchups — for the "Rivalry Matchups" section
# ---------------------------------------------------------------------------

@st.cache_data(ttl=43200, show_spinner=False)
def get_team_hitters(team_id: int) -> list[dict]:
    """Active-roster position players for a team (used as the opposing lineup
    pool — more reliable than posted lineups, which only appear ~2h pre-game)."""
    if not team_id:
        return []
    url = f"{MLB_API_BASE}/teams/{team_id}/roster?rosterType=active"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        out = []
        for p in resp.json().get("roster", []):
            if p.get("position", {}).get("type") != "Pitcher":
                out.append({
                    "id": p["person"]["id"],
                    "name": p["person"]["fullName"],
                    "pos": p["position"].get("abbreviation", ""),
                })
        return out
    except Exception:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def get_batter_vs_pitcher(batter_id: int, pitcher_id: int) -> dict:
    """Career batter-vs-pitcher totals (vsPlayerTotal split). Empty dict if the
    pair has never faced each other or the lookup fails."""
    if not batter_id or not pitcher_id:
        return {}
    url = (
        f"{MLB_API_BASE}/people/{batter_id}/stats?stats=vsPlayerTotal&group=hitting"
        f"&opposingPlayerId={pitcher_id}&sportId=1"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        for grp in resp.json().get("stats", []):
            for sp in grp.get("splits", []):
                s = sp.get("stat", {})
                return {
                    "PA": s.get("plateAppearances", 0),
                    "AB": s.get("atBats", 0),
                    "H": s.get("hits", 0),
                    "2B": s.get("doubles", 0),
                    "3B": s.get("triples", 0),
                    "HR": s.get("homeRuns", 0),
                    "RBI": s.get("rbi", 0),
                    "BB": s.get("baseOnBalls", 0),
                    "SO": s.get("strikeOuts", 0),
                    "AVG": _safe_float(s.get("avg")),
                    "OBP": _safe_float(s.get("obp")),
                    "SLG": _safe_float(s.get("slg")),
                    "OPS": _safe_float(s.get("ops")),
                }
        return {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_standings() -> pd.DataFrame:
    """Fetch current MLB standings."""
    year = datetime.date.today().year
    url = (
        f"{MLB_API_BASE}/standings"
        f"?leagueId=103,104&season={year}"
        f"&standingsTypes=regularSeason"
        f"&hydrate=division,league"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for record in data.get("records", []):
            league_name = record.get("league", {}).get("name", "")
            div_name = record.get("division", {}).get("name", "")
            if league_name and league_name not in div_name:
                division = f"{league_name} {div_name}"
            else:
                division = div_name if div_name else league_name

            for team in record.get("teamRecords", []):
                rows.append({
                    "Team": team["team"]["name"],
                    "Division": division,
                    "W": team["wins"],
                    "L": team["losses"],
                    "PCT": _safe_float(team.get("winningPercentage")),
                    "GB": team.get("gamesBack", "-"),
                    "Streak": team.get("streak", {}).get("streakCode", ""),
                })
        return pd.DataFrame(rows)
    except Exception as e:
        st.warning(f"Could not load standings: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Per-game batting stats for a single batter (used in dashboard charts)
# ---------------------------------------------------------------------------

def compute_batter_daily_stats(sc_df: pd.DataFrame, batter_id: int) -> pd.DataFrame:
    """Compute per-game-date batting stats for a specific batter from Statcast data."""
    if sc_df.empty:
        return pd.DataFrame()

    batter_data = sc_df[sc_df["batter"] == batter_id].copy()
    if batter_data.empty:
        return pd.DataFrame()

    events = batter_data.dropna(subset=["events"])
    if events.empty:
        return pd.DataFrame()

    dedup_cols = ["game_pk", "at_bat_number", "batter"]
    available = [c for c in dedup_cols if c in events.columns]
    if len(available) == len(dedup_cols):
        events = events.drop_duplicates(subset=dedup_cols, keep="last")

    hits = ["single", "double", "triple", "home_run"]

    daily = events.groupby("game_date").agg(
        PA=("events", "count"),
        H=("events", lambda x: x.isin(hits).sum()),
        _2B=("events", lambda x: (x == "double").sum()),
        _3B=("events", lambda x: (x == "triple").sum()),
        HR=("events", lambda x: (x == "home_run").sum()),
        BB=("events", lambda x: (x == "walk").sum()),
        SO=("events", lambda x: (x == "strikeout").sum()),
        HBP=("events", lambda x: (x == "hit_by_pitch").sum()),
        SF=("events", lambda x: (x == "sac_fly").sum()),
    ).reset_index()

    daily["AB"] = (daily["PA"] - daily["BB"] - daily["HBP"] - daily["SF"]).clip(lower=1)
    daily["TB"] = (
        (daily["H"] - daily["_2B"] - daily["_3B"] - daily["HR"])
        + daily["_2B"] * 2 + daily["_3B"] * 3 + daily["HR"] * 4
    )
    daily["H_AB"] = daily.apply(lambda r: f"{int(r['H'])}-{int(r['AB'])}", axis=1)

    daily["game_date"] = pd.to_datetime(daily["game_date"])
    daily = daily.sort_values("game_date")

    # Cumulative OPS — smoother than volatile per-game OPS
    cum_H = daily["H"].cumsum()
    cum_BB = daily["BB"].cumsum()
    cum_HBP = daily["HBP"].cumsum()
    cum_SF = daily["SF"].cumsum()
    cum_PA = daily["PA"].cumsum()
    cum_AB = (cum_PA - cum_BB - cum_HBP - cum_SF).clip(lower=1)
    cum_TB = daily["TB"].cumsum()
    daily["OPS"] = (
        (cum_H + cum_BB + cum_HBP) / cum_PA
        + cum_TB / cum_AB
    ).round(3)

    return daily


# ---------------------------------------------------------------------------
# Pitcher game log (season) — for dashboard ERA charts
# ---------------------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def get_pitcher_game_log(pitcher_id: int, season: int) -> pd.DataFrame:
    """Fetch pitcher game log for the season from MLB Stats API."""
    url = f"{MLB_API_BASE}/people/{pitcher_id}/stats?stats=gameLog&group=pitching&season={season}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for split_group in data.get("stats", []):
            for entry in split_group.get("splits", []):
                s = entry.get("stat", {})
                game_date = entry.get("date", "")
                opponent_obj = entry.get("opponent", {})
                opponent = opponent_obj.get("abbreviation", opponent_obj.get("name", ""))

                ip = _safe_float(s.get("inningsPitched"))

                rows.append({
                    "date": game_date,
                    "opponent": opponent,
                    "IP": ip,
                    "H": s.get("hits", 0),
                    "ER": s.get("earnedRuns", 0),
                    "BB": s.get("baseOnBalls", 0),
                    "SO": s.get("strikeOuts", 0),
                    "HR": s.get("homeRuns", 0),
                    "pitches": s.get("numberOfPitches", 0),
                })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
            df["cum_IP"] = df["IP"].cumsum()
            df["cum_ER"] = df["ER"].cumsum()
            df["ERA"] = (df["cum_ER"] / df["cum_IP"].clip(lower=0.1) * 9).round(2)
        return df
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Batter game log (season) — for dashboard hot/cold sparklines (MLB API)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def get_batter_game_log(player_id: int, season: int) -> pd.DataFrame:
    """Per-game hitting log for a batter from the MLB Stats API.

    Returns one row per game with counting stats plus a cumulative OPS line
    (smoother than volatile single-game OPS). Replaces the old Statcast-derived
    daily stats so the dashboard breakdown no longer needs a heavy scrape.
    """
    url = f"{MLB_API_BASE}/people/{player_id}/stats?stats=gameLog&group=hitting&season={season}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for split_group in data.get("stats", []):
            for entry in split_group.get("splits", []):
                s = entry.get("stat", {})
                rows.append({
                    "game_date": entry.get("date", ""),
                    "PA": s.get("plateAppearances", 0),
                    "AB": s.get("atBats", 0),
                    "H": s.get("hits", 0),
                    "HR": s.get("homeRuns", 0),
                    "BB": s.get("baseOnBalls", 0),
                    "SO": s.get("strikeOuts", 0),
                    "HBP": s.get("hitByPitch", 0),
                    "SF": s.get("sacFlies", 0),
                    "TB": s.get("totalBases", 0),
                })
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["game_date"] = pd.to_datetime(df["game_date"])
        df = df.sort_values("game_date")
        df["H_AB"] = df.apply(lambda r: f"{int(r['H'])}-{int(r['AB'])}", axis=1)

        cum_PA = df["PA"].cumsum()
        cum_AB = (cum_PA - df["BB"].cumsum() - df["HBP"].cumsum() - df["SF"].cumsum()).clip(lower=1)
        cum_OBP = (df["H"].cumsum() + df["BB"].cumsum() + df["HBP"].cumsum()) / cum_PA.clip(lower=1)
        cum_SLG = df["TB"].cumsum() / cum_AB
        df["OPS"] = (cum_OBP + cum_SLG).round(3)
        return df
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Player ID lookup by name (for clickable MLB-traditional leaderboard rows)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def lookup_player_id_by_name(name: str) -> int | None:
    """Resolve a player's MLB ID from their full name via the Stats API search."""
    if not name:
        return None
    url = f"{MLB_API_BASE}/people/search?names={requests.utils.quote(name)}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        people = resp.json().get("people", [])
        if people:
            return people[0].get("id")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Spray chart — batted-ball landing locations for one batter
# ---------------------------------------------------------------------------

# Hits used throughout for AVG / outcome coloring
_HIT_EVENTS = ["single", "double", "triple", "home_run"]


def get_batted_ball_locations(sc_df: pd.DataFrame, batter_id: int) -> pd.DataFrame:
    """Return every batted ball (ball in play) for a batter with field
    coordinates transformed so home plate sits at the origin and the
    outfield extends upward. Includes outcome category for coloring.
    """
    if sc_df.empty:
        return pd.DataFrame()

    needed = {"batter", "hc_x", "hc_y", "events"}
    if not needed.issubset(sc_df.columns):
        return pd.DataFrame()

    bb = sc_df[sc_df["batter"] == batter_id].copy()
    # Balls in play only have hit coordinates
    bb = bb.dropna(subset=["hc_x", "hc_y", "events"])
    if bb.empty:
        return pd.DataFrame()

    # Standard Statcast hit-coordinate transform (Baseball Savant pixel space).
    bb["field_x"] = bb["hc_x"] - 125.42
    bb["field_y"] = 198.27 - bb["hc_y"]

    def _outcome(ev):
        if ev == "home_run":
            return "Home Run"
        if ev in ("single", "double", "triple"):
            return "Hit"
        return "Out"

    bb["Outcome"] = bb["events"].map(_outcome)
    bb["EventLabel"] = bb["events"].str.replace("_", " ").str.title()

    keep = ["field_x", "field_y", "Outcome", "EventLabel", "events"]
    for opt in ("bb_type", "launch_speed", "launch_angle", "game_date"):
        if opt in bb.columns:
            keep.append(opt)
    return bb[keep].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 9-zone strike-zone batting-average grid for one batter
# ---------------------------------------------------------------------------

def compute_zone_avg_grid(sc_df: pd.DataFrame, batter_id: int) -> dict:
    """Build a 3x3 strike-zone grid of batting average for one batter.

    AVG is computed on balls put in play (type == 'X'): for each in-play
    pitch, the pitch location (plate_x / plate_z) assigns it to a zone, and
    AVG = hits / balls-in-play within that zone. Returns a dict with 3x3
    arrays for avg and ab (sample size), oriented catcher's view with the
    top row = high pitches.
    """
    empty = {"avg": None, "ab": None, "ready": False}
    if sc_df.empty:
        return empty

    needed = {"batter", "plate_x", "plate_z", "events", "sz_top", "sz_bot"}
    if not needed.issubset(sc_df.columns):
        return empty

    df = sc_df[sc_df["batter"] == batter_id].copy()
    # Balls in play: type 'X', with a location and an outcome
    if "type" in df.columns:
        df = df[df["type"] == "X"]
    df = df.dropna(subset=["plate_x", "plate_z", "events", "sz_top", "sz_bot"])
    if df.empty:
        return empty

    # Strike-zone vertical bounds: this batter's average top/bottom.
    sz_top = float(df["sz_top"].mean())
    sz_bot = float(df["sz_bot"].mean())
    # Horizontal bounds: standard plate half-width incl. ball (~0.83 ft).
    x_edges = [-0.83, -0.83 + 2 * 0.83 / 3, -0.83 + 4 * 0.83 / 3, 0.83]
    z_edges = [sz_bot, sz_bot + (sz_top - sz_bot) / 3,
               sz_bot + 2 * (sz_top - sz_bot) / 3, sz_top]

    df["is_hit"] = df["events"].isin(_HIT_EVENTS)

    avg = [[None, None, None] for _ in range(3)]
    ab = [[0, 0, 0] for _ in range(3)]

    for col in range(3):
        x_lo, x_hi = x_edges[col], x_edges[col + 1]
        in_col = (df["plate_x"] >= x_lo) & (df["plate_x"] < x_hi)
        for row in range(3):  # row 0 = bottom of zone
            z_lo, z_hi = z_edges[row], z_edges[row + 1]
            cell = df[in_col & (df["plate_z"] >= z_lo) & (df["plate_z"] < z_hi)]
            n = len(cell)
            # Display row 0 = top (high pitches), so invert the row index.
            disp = 2 - row
            ab[disp][col] = n
            avg[disp][col] = round(cell["is_hit"].sum() / n, 3) if n else None

    return {"avg": avg, "ab": ab, "ready": True}
