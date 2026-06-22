"""Batting Stats page — MLB Stats API leaderboards (full-season + any date range).

Both views are powered by the MLB Stats API. The date-range view uses the
byDateRange split (a single fast call) instead of scraping pitch-level
Statcast, which previously blew past Streamlit Cloud's memory/time limits and
crashed the app whenever the date range was widened.
"""

import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_loader import (
    get_mlb_batting_stats,
    get_mlb_batting_stats_range,
    lookup_player_id_by_name,
)

# Brand palette (mirrors app.py CSS)
_RED = "#E63946"
_PANEL = "rgba(26,26,46,0.6)"
_FONT = "#EAEAEA"
_RED_SCALE = ["#2A2A4A", "#7A2230", _RED, "#FF6B6B"]


def _open_player(event, src_df, id_col):
    """On a single-row leaderboard click, stash the batter and jump to the
    Player view. src_df is the unstyled frame backing the displayed table;
    selection rows are positional, so iloc lines up with the display order.
    """
    rows = event.selection["rows"] if event and event.selection else []
    if not rows:
        return
    row = src_df.iloc[rows[0]]
    name = row.get("Name", "")
    pid = row.get(id_col)
    if pid is None or pd.isna(pid):
        pid = lookup_player_id_by_name(name)
    if pid:
        st.session_state["selected_batter_id"] = int(pid)
        st.session_state["selected_batter_name"] = name
        st.session_state["main_nav"] = "Player"
        st.rerun()


def _style_plotly(fig):
    """Apply the dark brand theme to a plotly figure."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=_PANEL,
        font_color=_FONT,
        margin=dict(l=20, r=20, t=40, b=20),
        coloraxis_colorbar=dict(thickness=10),
        title_font_size=15,
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    return fig


def _leader_metrics(df: pd.DataFrame, span_label: str):
    """A row of highlight cards: batter count + category leaders."""
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Batters", f"{len(df):,}", span_label, delta_color="off")

    if not df.empty:
        hr = df.loc[df["HR"].idxmax()]
        m2.metric("Home Run Leader", f"{int(hr['HR'])} HR", hr["Name"], delta_color="off")

        # Leaders for rate stats use a light PA floor so a 1-for-1 day can't win.
        floor = df[df["PA"] >= max(5, int(df["PA"].quantile(0.5)))]
        pool = floor if not floor.empty else df
        ops = pool.loc[pool["OPS"].idxmax()]
        m3.metric("OPS Leader", f"{ops['OPS']:.3f}", ops["Name"], delta_color="off")
        avg = pool.loc[pool["AVG"].idxmax()]
        m4.metric("AVG Leader", f"{avg['AVG']:.3f}", avg["Name"], delta_color="off")


def _leaderboard_table(df: pd.DataFrame, key: str):
    """Styled, click-to-open leaderboard. Returns nothing; handles navigation."""
    display = ["Name", "Team", "G", "PA", "AB", "H", "2B", "3B", "HR", "RBI",
               "BB", "SO", "SB", "AVG", "OBP", "SLG", "OPS"]
    available = [c for c in display if c in df.columns]
    grad_cols = [c for c in ["AVG", "OBP", "SLG", "OPS"] if c in df.columns]

    styler = df[available].style.format({
        "AVG": "{:.3f}", "OBP": "{:.3f}", "SLG": "{:.3f}", "OPS": "{:.3f}",
    })
    if grad_cols:
        styler = styler.background_gradient(subset=grad_cols, cmap="RdYlGn")
    if "HR" in available:
        styler = styler.background_gradient(subset=["HR"], cmap="Reds")

    st.caption("Click any row to open that player's spray chart and zone heatmap.")
    event = st.dataframe(
        styler,
        width="stretch",
        height=460,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
        column_config={
            "Name": st.column_config.TextColumn("Player", width="medium"),
            "OPS": st.column_config.NumberColumn("OPS", format="%.3f"),
        },
    )
    _open_player(event, df, "player_id")


def _leader_charts(df: pd.DataFrame):
    c1, c2 = st.columns(2)
    top = df.nlargest(15, "OPS").sort_values("OPS")  # ascending -> best on top

    with c1:
        st.markdown("#### Top 15 by OPS")
        fig = go.Figure(go.Bar(
            x=top["OPS"], y=top["Name"], orientation="h",
            marker=dict(color=top["OPS"], colorscale=_RED_SCALE,
                        colorbar=dict(title="OPS", thickness=10)),
            text=[f"{v:.3f}" for v in top["OPS"]],
            textposition="outside", cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>OPS %{x:.3f}<extra></extra>",
        ))
        _style_plotly(fig)
        fig.update_layout(xaxis_title="OPS", yaxis_title="",
                          margin=dict(l=20, r=70, t=40, b=20))
        st.plotly_chart(fig, width="stretch")

    with c2:
        st.markdown("#### OPS Breakdown — On-Base vs. Slugging")
        fig2 = go.Figure()
        fig2.add_bar(x=top["OBP"], y=top["Name"], orientation="h", name="OBP",
                     marker_color="#4C9BE6",
                     hovertemplate="<b>%{y}</b><br>OBP %{x:.3f}<extra></extra>")
        fig2.add_bar(x=top["SLG"], y=top["Name"], orientation="h", name="SLG",
                     marker_color=_RED,
                     hovertemplate="<b>%{y}</b><br>SLG %{x:.3f}<extra></extra>")
        _style_plotly(fig2)
        fig2.update_layout(
            barmode="stack", xaxis_title="OBP + SLG = OPS", yaxis_title="",
            legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
            margin=dict(l=20, r=70, t=50, b=20),
        )
        # Label total OPS at the end of each stacked bar.
        for name, obp, slg in zip(top["Name"], top["OBP"], top["SLG"]):
            fig2.add_annotation(x=obp + slg, y=name, text=f"{obp + slg:.3f}",
                                showarrow=False, xanchor="left", xshift=4,
                                font=dict(color="#EAEAEA", size=10))
        st.plotly_chart(fig2, width="stretch")


def render():
    st.markdown('<div class="section-header">Batting Leaderboard</div>', unsafe_allow_html=True)

    today = datetime.date.today()
    season_start = datetime.date(today.year, 3, 20)
    # Before opening day, anchor to last year's season so date pickers stay valid.
    if season_start > today:
        season_start = datetime.date(today.year - 1, 3, 20)

    source = st.radio(
        "Data Source",
        ["Full Season", "Date Range"],
        horizontal=True,
    )

    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

    if source == "Full Season":
        st.caption("Full-season totals from the MLB Stats API.")
        with st.spinner("Pulling season stats..."):
            df = get_mlb_batting_stats(today.year)
        span_label = f"{today.year} season"
    else:
        # --- Date range controls ---
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            preset = st.selectbox(
                "Quick Range",
                ["Custom", "Today", "Last 3 Days", "Last 7 Days",
                 "Last 14 Days", "Last 30 Days", "Full Season"],
            )

        presets = {
            "Today": (today, today),
            "Last 3 Days": (today - datetime.timedelta(days=3), today),
            "Last 7 Days": (today - datetime.timedelta(days=7), today),
            "Last 14 Days": (today - datetime.timedelta(days=14), today),
            "Last 30 Days": (today - datetime.timedelta(days=30), today),
            "Full Season": (season_start, today),
        }
        pre_start, pre_end = presets.get(preset, (None, None))

        with col2:
            start_date = st.date_input(
                "Start Date", value=pre_start or season_start,
                min_value=season_start, max_value=today,
            )
        with col3:
            end_date = st.date_input(
                "End Date", value=pre_end or today,
                min_value=season_start, max_value=today,
            )

        if start_date > end_date:
            st.error("Start date must be on or before the end date.")
            return

        with st.spinner("Pulling stats for this date range..."):
            df = get_mlb_batting_stats_range(start_date.isoformat(), end_date.isoformat())
        span_label = f"{start_date:%b %d} – {end_date:%b %d}"

    if df.empty:
        st.warning("No batting stats available for this selection.")
        return

    # --- Shared filters ---
    f1, f2 = st.columns([1, 2])
    with f1:
        max_pa = int(df["PA"].max()) if not df.empty else 0
        cap = max(10, min(200, max_pa))
        min_pa = st.slider("Minimum Plate Appearances", 0, cap,
                           min(10, cap), step=5, key="bat_min_pa")
    with f2:
        teams = sorted(df["Team"].dropna().unique().tolist())
        team_filter = st.multiselect("Filter by Team", options=teams, default=[],
                                     key="bat_team")

    if min_pa > 0:
        df = df[df["PA"] >= min_pa]
    if team_filter:
        df = df[df["Team"].isin(team_filter)]

    if df.empty:
        st.info("No batters match the current filters.")
        return

    df = df.sort_values("PA", ascending=False).reset_index(drop=True)

    _leader_metrics(df, span_label)
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    _leaderboard_table(df, key=f"bat_table_{source}")
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    _leader_charts(df)
