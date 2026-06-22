"""Rivalry Matchups page — batter-vs-pitcher history for today's games.

For a selected game, pairs each probable starter against the opposing team's
active hitters and surfaces the matchups with the most history (career PA),
flagging whether the hitter or the pitcher has owned the battle.
"""

import streamlit as st
import pandas as pd
from data_loader import (
    get_todays_games,
    get_team_hitters,
    get_batter_vs_pitcher,
)

# OPS thresholds for who holds the edge in a matchup.
_HITTER_EDGE = 0.850
_PITCHER_EDGE = 0.550


def _edge_label(ops: float) -> str:
    if ops >= _HITTER_EDGE:
        return "🔴 Hitter"
    if ops <= _PITCHER_EDGE:
        return "🔵 Pitcher"
    return "⚪ Even"


def _build_matchup(pitcher_id, hitters, min_pa) -> pd.DataFrame:
    """Career BvP rows for every opposing hitter with >= min_pa vs the pitcher."""
    rows = []
    for h in hitters:
        s = get_batter_vs_pitcher(h["id"], pitcher_id)
        if not s or s.get("PA", 0) < min_pa:
            continue
        rows.append({
            "Hitter": h["name"], "Pos": h["pos"],
            "PA": s["PA"], "AB": s["AB"], "H": s["H"], "HR": s["HR"],
            "BB": s["BB"], "SO": s["SO"], "AVG": s["AVG"], "OPS": s["OPS"],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Edge"] = df["OPS"].apply(_edge_label)
    return df.sort_values("PA", ascending=False).reset_index(drop=True)


def _render_matchup(pitcher_name, pitcher_id, opp_team, opp_team_id, min_pa):
    st.markdown(f"### {pitcher_name} &nbsp;<span style='color:#8888AA;font-size:0.9rem;'>vs. {opp_team} hitters</span>",
                unsafe_allow_html=True)

    if not pitcher_id:
        st.info(f"No probable starter announced for {opp_team}'s opponent yet.")
        return
    hitters = get_team_hitters(opp_team_id)
    if not hitters:
        st.info(f"Could not load the {opp_team} roster.")
        return

    df = _build_matchup(pitcher_id, hitters, min_pa)
    if df.empty:
        st.info(f"No {opp_team} hitter has at least {min_pa} career plate appearances vs. {pitcher_name}.")
        return

    # Headline: the matchup with the most shared history.
    top = df.iloc[0]
    owns = "has owned" if top["OPS"] >= _HITTER_EDGE else (
        "has been dominated by" if top["OPS"] <= _PITCHER_EDGE else "is even with")
    st.caption(
        f"📊 Most history: **{top['Hitter']}** — {int(top['H'])}-for-{int(top['AB'])} "
        f"({top['AVG']:.3f}), {int(top['HR'])} HR, {int(top['SO'])} K in {int(top['PA'])} PA "
        f"· {top['Hitter']} {owns} {pitcher_name}."
    )

    st.dataframe(
        df.style.format({"AVG": "{:.3f}", "OPS": "{:.3f}"})
        .background_gradient(subset=["OPS"], cmap="RdYlGn", vmin=0.300, vmax=1.100),
        width="stretch",
        hide_index=True,
        column_config={
            "Hitter": st.column_config.TextColumn("Hitter", width="medium"),
            "Edge": st.column_config.TextColumn("Edge", help="🔴 hitter owns · 🔵 pitcher owns · ⚪ even"),
        },
    )


def render():
    st.markdown('<div class="section-header">Rivalry Matchups</div>', unsafe_allow_html=True)
    st.caption("Career batter-vs-pitcher history between each probable starter and "
               "the opposing lineup — who owns whom.")

    label, games = get_todays_games()

    # Only games with at least one probable starter are useful here.
    options, mapping = [], {}
    for g in games:
        if not g.get("away_pitcher_id") and not g.get("home_pitcher_id"):
            continue
        opt = f'{g["away_team"]} @ {g["home_team"]}'
        if g.get("game_time"):
            opt += f' · {g["game_time"]}'
        options.append(opt)
        mapping[opt] = g

    if not options:
        st.info("No probable starting pitchers have been announced for today's games yet. "
                "Check back closer to game time.")
        return

    c1, c2 = st.columns([3, 1])
    with c1:
        choice = st.selectbox("Select a game", options, key="matchup_game")
    with c2:
        min_pa = st.slider("Min. career PA", 3, 30, 6, step=1, key="matchup_min_pa")

    game = mapping[choice]
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

    with st.spinner("Loading matchup history..."):
        # Away starter faces the home lineup; home starter faces the away lineup.
        _render_matchup(game.get("away_pitcher", "TBD"), game.get("away_pitcher_id"),
                        game["home_team"], game.get("home_team_id"), min_pa)
        st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
        _render_matchup(game.get("home_pitcher", "TBD"), game.get("home_pitcher_id"),
                        game["away_team"], game.get("away_team_id"), min_pa)
