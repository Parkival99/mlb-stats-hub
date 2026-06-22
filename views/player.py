"""Player page — season spray chart and 9-zone batting-average heatmap.

Reached by clicking a batter on the Batting Stats leaderboard, which stores
the selected batter's ID + name in session_state.
"""

import datetime
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from data_loader import (
    get_statcast_batter_data,
    get_batted_ball_locations,
    compute_zone_avg_grid,
)

_OUTCOME_COLORS = {
    "Home Run": "#E63946",
    "Hit": "#FFB703",
    "Out": "#5A6B8C",
}


def _spray_chart(locs):
    """Scatter of batted-ball landing spots, colored by outcome."""
    fig = go.Figure()

    # Foul lines + a simple outfield arc for spatial reference.
    fig.add_trace(go.Scatter(
        x=[0, 90], y=[0, 90], mode="lines",
        line=dict(color="#2A2A4A", width=1), hoverinfo="skip", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[0, -90], y=[0, 90], mode="lines",
        line=dict(color="#2A2A4A", width=1), hoverinfo="skip", showlegend=False,
    ))
    arc_t = np.linspace(np.pi / 4, 3 * np.pi / 4, 60)
    fig.add_trace(go.Scatter(
        x=125 * np.cos(arc_t), y=125 * np.sin(arc_t), mode="lines",
        line=dict(color="#2A2A4A", width=1, dash="dot"),
        hoverinfo="skip", showlegend=False,
    ))

    for outcome, color in _OUTCOME_COLORS.items():
        sub = locs[locs["Outcome"] == outcome]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["field_x"], y=sub["field_y"], mode="markers",
            name=f"{outcome} ({len(sub)})",
            marker=dict(color=color, size=8, opacity=0.75,
                        line=dict(width=0.5, color="#0E1117")),
            customdata=sub["EventLabel"],
            hovertemplate="%{customdata}<extra></extra>",
        ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(26,26,46,0.6)",
        font_color="#EAEAEA",
        margin=dict(l=10, r=10, t=10, b=10),
        height=480,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1,
                   range=[-160, 160]),
        yaxis=dict(visible=False, range=[-25, 190]),
    )
    return fig


def _zone_heatmap(grid):
    """3x3 strike-zone heatmap colored by batting average."""
    avg = grid["avg"]
    ab = grid["ab"]
    z = [[(v if v is not None else np.nan) for v in row] for row in avg]
    text = []
    for r in range(3):
        text_row = []
        for c in range(3):
            if avg[r][c] is None:
                text_row.append("—")
            else:
                text_row.append(f"{avg[r][c]:.3f}<br><span style='font-size:0.7em'>{ab[r][c]} BIP</span>")
        text.append(text_row)

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=["Inside/Left", "Middle", "Outside/Right"],
        y=["Up", "Middle", "Down"],
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=15, color="#0E1117"),
        colorscale="RdYlGn",
        zmin=0.0, zmax=0.5,
        hovertemplate="AVG %{z:.3f}<extra></extra>",
        colorbar=dict(title="AVG"),
        xgap=3, ygap=3,
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#EAEAEA",
        margin=dict(l=10, r=10, t=10, b=10),
        height=420,
        xaxis=dict(side="top", showgrid=False),
        yaxis=dict(showgrid=False),
    )
    return fig


def _exit_velocity_panel(sc):
    """Highlight cards for batted-ball quality (exit velocity / launch angle)."""
    if "launch_speed" not in sc.columns:
        return
    bbe = sc.dropna(subset=["launch_speed"])
    if "bb_type" in bbe.columns:
        bbe = bbe.dropna(subset=["bb_type"])
    if bbe.empty:
        return

    avg_ev = bbe["launch_speed"].mean()
    max_ev = bbe["launch_speed"].max()
    hard_hit = (bbe["launch_speed"] >= 95).mean() * 100  # MLB "hard-hit" threshold
    if "launch_angle" in bbe.columns and bbe["launch_angle"].notna().any():
        # Barrel-ish proxy: 95+ mph and a 8–50° launch window.
        la = bbe["launch_angle"]
        sweet = ((bbe["launch_speed"] >= 95) & la.between(8, 50)).mean() * 100
    else:
        sweet = None

    st.markdown("##### Batted-Ball Quality")
    cols = st.columns(4)
    cols[0].metric("Avg Exit Velo", f"{avg_ev:.1f} mph")
    cols[1].metric("Max Exit Velo", f"{max_ev:.1f} mph")
    cols[2].metric("Hard-Hit %", f"{hard_hit:.0f}%", f"{len(bbe)} batted balls", delta_color="off")
    cols[3].metric("Sweet-Spot %", f"{sweet:.0f}%" if sweet is not None else "—")
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)


def render():
    st.markdown('<div class="section-header">Player Spray & Zone Profile</div>',
                unsafe_allow_html=True)

    batter_id = st.session_state.get("selected_batter_id")
    batter_name = st.session_state.get("selected_batter_name", "")

    if not batter_id:
        st.info("Click a player's row on the **Batting Stats** leaderboard to "
                "load their season spray chart and strike-zone heatmap.")
        return

    today = datetime.date.today()
    season_start = datetime.date(today.year, 3, 20)

    st.markdown(f"#### {batter_name}")
    st.caption(f"Full {today.year} season · batted-ball locations, exit velocity, "
               f"and batting average by strike-zone region.")

    # Single-batter Statcast pull — small and cached, so the page loads once
    # and isn't re-queried from a widget (no way to widen it into a crash).
    with st.spinner("Pulling season Statcast data..."):
        sc = get_statcast_batter_data(int(batter_id), season_start.isoformat(), today.isoformat())

    if sc.empty:
        st.warning("No Statcast data available for this player yet this season.")
        return

    _exit_velocity_panel(sc)

    locs = get_batted_ball_locations(sc, int(batter_id))
    grid = compute_zone_avg_grid(sc, int(batter_id))

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("##### Spray Chart")
        if locs.empty:
            st.info("No batted balls on record for this player this season.")
        else:
            st.caption(f"{len(locs)} batted balls (catcher's view, outs included).")
            st.plotly_chart(_spray_chart(locs), width="stretch")

    with col2:
        st.markdown("##### Batting Avg by Zone")
        if not grid["ready"] or all(v is None for row in grid["avg"] for v in row):
            st.info("Not enough balls in play to build a zone map.")
        else:
            st.caption("AVG on balls in play, by pitch location (catcher's view).")
            st.plotly_chart(_zone_heatmap(grid), width="stretch")
