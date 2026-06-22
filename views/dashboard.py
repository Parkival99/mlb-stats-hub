"""Dashboard page — today's games, who's hot, who's cold, top matchups."""

import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_loader import (
    get_todays_games,
    get_mlb_batting_stats_range,
    get_mlb_pitching_stats_range,
    get_batter_game_log,
    get_pitcher_game_log,
)

# Team colors: (primary for gradient, text color for name visibility)
# Text color uses secondary/accent so names pop against the dark card background
TEAM_COLORS = {
    "Arizona Diamondbacks": ("#A71930", "#E3D4AD"),
    "Atlanta Braves": ("#CE1141", "#CE1141"),
    "Baltimore Orioles": ("#DF4601", "#DF4601"),
    "Boston Red Sox": ("#BD3039", "#BD3039"),
    "Chicago Cubs": ("#0E3386", "#CC3433"),
    "Chicago White Sox": ("#27251F", "#C4CED4"),
    "Cincinnati Reds": ("#C6011F", "#C6011F"),
    "Cleveland Guardians": ("#00385D", "#E31937"),
    "Colorado Rockies": ("#333366", "#C4CED4"),
    "Detroit Tigers": ("#0C2340", "#FA4616"),
    "Houston Astros": ("#002D62", "#EB6E1F"),
    "Kansas City Royals": ("#004687", "#7BB2DD"),
    "Los Angeles Angels": ("#BA0021", "#BA0021"),
    "Los Angeles Dodgers": ("#005A9C", "#5A8FBE"),
    "Miami Marlins": ("#00A3E0", "#00A3E0"),
    "Milwaukee Brewers": ("#12284B", "#FFC52F"),
    "Minnesota Twins": ("#002B5C", "#D31145"),
    "New York Mets": ("#002D72", "#FF5910"),
    "New York Yankees": ("#003087", "#C4CED4"),
    "Oakland Athletics": ("#003831", "#EFB21E"),
    "Philadelphia Phillies": ("#E81828", "#E81828"),
    "Pittsburgh Pirates": ("#27251F", "#FDB827"),
    "San Diego Padres": ("#2F241D", "#FFC425"),
    "San Francisco Giants": ("#FD5A1E", "#FD5A1E"),
    "Seattle Mariners": ("#0C2C56", "#00C2B3"),
    "St. Louis Cardinals": ("#C41E3A", "#C41E3A"),
    "Tampa Bay Rays": ("#092C5C", "#8FBCE6"),
    "Texas Rangers": ("#003278", "#C0111F"),
    "Toronto Blue Jays": ("#134A8E", "#5BA5E1"),
    "Washington Nationals": ("#AB0003", "#AB0003"),
    "Athletics": ("#003831", "#EFB21E"),
}


def _get_color(team: str) -> str:
    """Get primary (gradient) color."""
    if team in TEAM_COLORS:
        return TEAM_COLORS[team][0]
    for full, colors in TEAM_COLORS.items():
        if team in full or full.endswith(team):
            return colors[0]
    return "#1A1A2E"


def _get_text_color(team: str) -> str:
    """Get text color for team name (bright/contrasting)."""
    if team in TEAM_COLORS:
        return TEAM_COLORS[team][1]
    for full, colors in TEAM_COLORS.items():
        if team in full or full.endswith(team):
            return colors[1]
    return "#EAEAEA"


# Team name/abbreviation -> MLB team ID for logo URLs
TEAM_IDS = {
    "Arizona Diamondbacks": 109, "Atlanta Braves": 144, "Baltimore Orioles": 110,
    "Boston Red Sox": 111, "Chicago Cubs": 112, "Chicago White Sox": 145,
    "Cincinnati Reds": 113, "Cleveland Guardians": 114, "Colorado Rockies": 115,
    "Detroit Tigers": 116, "Houston Astros": 117, "Kansas City Royals": 118,
    "Los Angeles Angels": 108, "Los Angeles Dodgers": 119, "Miami Marlins": 146,
    "Milwaukee Brewers": 158, "Minnesota Twins": 142, "New York Mets": 121,
    "New York Yankees": 147, "Athletics": 133, "Oakland Athletics": 133,
    "Philadelphia Phillies": 143, "Pittsburgh Pirates": 134, "San Diego Padres": 135,
    "San Francisco Giants": 137, "Seattle Mariners": 136, "St. Louis Cardinals": 138,
    "Tampa Bay Rays": 139, "Texas Rangers": 140, "Toronto Blue Jays": 141,
    "Washington Nationals": 120,
    # Abbreviations (from Statcast)
    "AZ": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112, "CWS": 145,
    "CIN": 113, "CLE": 114, "COL": 115, "DET": 116, "HOU": 117, "KC": 118,
    "LAA": 108, "LAD": 119, "MIA": 146, "MIL": 158, "MIN": 142, "NYM": 121,
    "NYY": 147, "ATH": 133, "OAK": 133, "PHI": 143, "PIT": 134, "SD": 135,
    "SF": 137, "SEA": 136, "STL": 138, "TB": 139, "TEX": 140, "TOR": 141,
    "WSH": 120,
}


def _team_logo_img(team_name: str) -> str:
    """Return an <img> tag for a team logo."""
    team_id = TEAM_IDS.get(team_name)
    if not team_id:
        # Fuzzy match
        for name, tid in TEAM_IDS.items():
            if team_name in name or name.endswith(team_name):
                team_id = tid
                break
    if not team_id:
        return ''
    url = f"https://www.mlbstatic.com/team-logos/{team_id}.svg"
    return (
        f'<img src="{url}" '
        f'style="width:40px;height:40px;margin-right:12px;object-fit:contain;">'
    )


def _render_game_card(game: dict):
    """Render a single game as a styled card with team color gradient."""
    away_color = _get_color(game["away_team"])
    home_color = _get_color(game["home_team"])
    away_text = _get_text_color(game["away_team"])
    home_text = _get_text_color(game["home_team"])
    is_live = "Progress" in game["status"]
    is_final = "Final" in game["status"]

    live_dot = '<span style="color:#FF4444;font-size:0.6rem;">&#9679;</span> ' if is_live else ''

    # Show time for scheduled games, status for live/final
    if is_live or is_final:
        status_text = f'{live_dot}{game["status"]}'
    else:
        time_str = game.get("game_time", "")
        status_text = time_str if time_str else game["status"]

    st.markdown(
        f'<div style="background:linear-gradient(135deg, {away_color}55 0%, #1A1A2E 35%, #1A1A2E 65%, {home_color}55 100%);'
        f'border:1px solid #2A2A4A;border-radius:12px;padding:20px;margin-bottom:12px;'
        f'box-shadow:0 4px 15px rgba(0,0,0,0.3);">'
        f'<div style="text-align:center;font-size:0.75rem;color:#8888AA;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">'
        f'{status_text}</div>'
        f'<div style="display:flex;align-items:center;margin-bottom:8px;">'
        f'<div style="flex:1;min-width:0;">'
        f'<div style="font-weight:600;font-size:1.1rem;color:{away_text};">{game["away_team"]}</div>'
        f'<div style="font-size:0.8rem;color:#8888AA;">{game["away_record"]}</div>'
        f'<div style="font-size:0.85rem;color:#AAAACC;">SP: {game["away_pitcher"]}</div>'
        f'</div>'
        f'<div class="game-score" style="padding:0 10px;font-size:1.6rem;font-weight:700;color:#EAEAEA;text-align:center;white-space:nowrap;">'
        f'{game["away_score"]} - {game["home_score"]}</div>'
        f'<div style="flex:1;min-width:0;text-align:right;">'
        f'<div style="font-weight:600;font-size:1.1rem;color:{home_text};">{game["home_team"]}</div>'
        f'<div style="font-size:0.8rem;color:#8888AA;">{game["home_record"]}</div>'
        f'<div style="font-size:0.85rem;color:#AAAACC;">SP: {game["home_pitcher"]}</div>'
        f'</div></div>'
        f'<div style="text-align:center;font-size:0.75rem;color:#8888AA;margin-top:4px;">'
        f'{game["venue"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _hot_cold_list(rows, start, end, kind):
    """Render a hot- or cold-hitter list with an expandable 7-day OPS trend."""
    is_hot = kind == "hot"
    badge = "hot-badge" if is_hot else "cold-badge"
    label = "HOT" if is_hot else "COLD"
    line_color = "#E63946" if is_hot else "#1E90FF"
    third_stat = "HR" if is_hot else "SO"

    for _, row in rows.iterrows():
        img = _team_logo_img(row.get("Team", ""))
        ops_val = row.get("OPS", 0)
        third_val = int(row.get(third_stat, 0))
        st.markdown(
            f'<div class="player-row">'
            f'{img}'
            f'<div style="flex:1;">'
            f'<div class="name">{row["Name"]}</div>'
            f'<div class="detail">{int(row["PA"])} PA &middot; {row["AVG"]:.3f} AVG '
            f'&middot; {third_val} {third_stat}</div>'
            f'</div>'
            f'<div><span class="stat">{ops_val:.3f} OPS</span> '
            f'<span class="{badge}">{label}</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        pid = row.get("player_id")
        if pid is None or pd.isna(pid):
            continue
        with st.expander(f"📊 {row['Name']} — 7-Day Breakdown"):
            log = get_batter_game_log(int(pid), end.year)
            window = log[log["game_date"] >= pd.Timestamp(start)] if not log.empty else log
            if window.empty:
                st.caption("No game-by-game data available.")
                continue
            # Cumulative OPS within the 7-day window (smoother than per-game).
            cum_pa = window["PA"].cumsum()
            cum_ab = (cum_pa - window["BB"].cumsum() - window["HBP"].cumsum()
                      - window["SF"].cumsum()).clip(lower=1)
            obp = (window["H"].cumsum() + window["BB"].cumsum()
                   + window["HBP"].cumsum()) / cum_pa.clip(lower=1)
            slg = window["TB"].cumsum() / cum_ab
            window = window.assign(OPS=(obp + slg).round(3))

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=window["game_date"], y=window["OPS"],
                mode="lines+markers",
                line=dict(color=line_color, width=2),
                marker=dict(size=8, color=line_color),
                customdata=window[["TB", "H_AB", "SO", "HR"]].values,
                hovertemplate=(
                    "<b>%{x|%a %m/%d}</b><br>"
                    "OPS: %{y:.3f}<br>"
                    "Total Bases: %{customdata[0]}<br>"
                    "H-AB: %{customdata[1]}<br>"
                    "Strikeouts: %{customdata[2]}<br>"
                    "Home Runs: %{customdata[3]}"
                    "<extra></extra>"
                ),
            ))
            fig.update_layout(
                height=220,
                margin=dict(l=40, r=20, t=10, b=40),
                xaxis_title="Date", yaxis_title="OPS",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8888AA"),
                xaxis=dict(gridcolor="#2A2A4A"), yaxis=dict(gridcolor="#2A2A4A"),
            )
            st.plotly_chart(fig, width="stretch", key=f"{kind}_chart_{int(pid)}")


def _pitcher_list(rows, season, headline):
    """Render a recent-pitching list with an expandable season ERA trend."""
    for _, row in rows.iterrows():
        img = _team_logo_img(row.get("Team", ""))
        st.markdown(
            f'<div class="player-row">'
            f'{img}'
            f'<div style="flex:1;">'
            f'<div class="name">{row["Name"]}</div>'
            f'<div class="detail">{row["IP"]:.1f} IP &middot; {int(row["SO"])} K '
            f'&middot; {row["WHIP"]:.2f} WHIP</div>'
            f'</div>'
            f'<div><span class="stat">{headline(row)}</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        pid = row.get("player_id")
        if pid is None or pd.isna(pid):
            continue
        with st.expander(f"📊 {row['Name']} — Season ERA Trend"):
            game_log = get_pitcher_game_log(int(pid), season)
            if game_log.empty:
                st.caption("No season game log available.")
                continue
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=game_log["date"], y=game_log["ERA"],
                mode="lines+markers",
                line=dict(color="#E63946", width=2),
                marker=dict(size=8, color="#E63946"),
                customdata=game_log[["IP", "SO", "ER", "opponent"]].values,
                hovertemplate=(
                    "<b>%{x|%m/%d}</b><br>"
                    "ERA: %{y:.2f}<br>"
                    "IP: %{customdata[0]}<br>"
                    "K: %{customdata[1]}<br>"
                    "ER: %{customdata[2]}<br>"
                    "vs %{customdata[3]}"
                    "<extra></extra>"
                ),
            ))
            fig.update_layout(
                height=220,
                margin=dict(l=40, r=20, t=10, b=40),
                xaxis_title="Date", yaxis_title="Cumulative ERA",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8888AA"),
                xaxis=dict(gridcolor="#2A2A4A"), yaxis=dict(gridcolor="#2A2A4A"),
            )
            st.plotly_chart(fig, width="stretch", key=f"era_trend_{int(pid)}")


def render():
    games_label, games = get_todays_games()
    st.markdown(f'<div class="section-header">{games_label}</div>', unsafe_allow_html=True)

    if not games:
        st.info("No games scheduled or data unavailable.")
    else:
        cols_per_row = 3
        for i in range(0, len(games), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                if i + j < len(games):
                    with col:
                        _render_game_card(games[i + j])

    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

    # --- Who's Hot / Who's Cold (last 7 days) ---
    st.markdown('<div class="section-header">Who\'s Hot & Who\'s Cold</div>', unsafe_allow_html=True)
    st.caption("Based on the last 7 days, minimum 15 plate appearances")

    end = datetime.date.today()
    start = end - datetime.timedelta(days=7)

    with st.spinner("Loading recent performance data..."):
        leaders = get_mlb_batting_stats_range(start.isoformat(), end.isoformat())

    if leaders.empty:
        st.info("No batting data available for the last 7 days.")
        return

    qualified = leaders[leaders["PA"] >= 15].copy()
    if qualified.empty:
        st.info("Not enough qualified plate appearances in the last 7 days.")
        return

    hot_col, cold_col = st.columns(2)
    with hot_col:
        st.markdown("### 🔥 Hottest Hitters")
        _hot_cold_list(qualified.nlargest(5, "OPS"), start, end, "hot")
    with cold_col:
        st.markdown("### 🥶 Coldest Hitters")
        _hot_cold_list(qualified.nsmallest(5, "OPS"), start, end, "cold")

    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

    # --- Top Pitchers (last 14 days) ---
    # Pitchers work sporadically, so a 2-week window captures a couple of
    # starts / several relief appearances.
    st.markdown('<div class="section-header">Pitching Highlights — Last 14 Days</div>', unsafe_allow_html=True)
    p_start = end - datetime.timedelta(days=14)

    with st.spinner("Loading recent pitching data..."):
        p_leaders = get_mlb_pitching_stats_range(p_start.isoformat(), end.isoformat())

    if p_leaders.empty:
        st.info("No pitching data available for the last 14 days.")
        return

    qual_p = p_leaders[p_leaders["IP"] >= 5].copy()
    if qual_p.empty:
        st.info("Not enough innings pitched in the last 14 days.")
        return

    era_col, k_col = st.columns(2)
    with era_col:
        st.markdown("### 🎯 Best ERA")
        _pitcher_list(qual_p.nsmallest(5, "ERA"), end.year,
                      lambda r: f"{r['ERA']:.2f} ERA")
    with k_col:
        st.markdown("### 🔥 Most Strikeouts")
        _pitcher_list(qual_p.nlargest(5, "SO"), end.year,
                      lambda r: f"{int(r['SO'])} K")
