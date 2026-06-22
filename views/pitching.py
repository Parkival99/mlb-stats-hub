"""Pitching Stats page — MLB Stats API leaderboards (full-season + recent form).

The old Statcast whiff-rate view scraped pitch-level data and crashed Streamlit
Cloud on wider ranges. Both views now come from the MLB Stats API. "Recent Form"
uses a date window (default ~3 weeks) so weekly starters show their last few
outings without any scraping.
"""

import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
from data_loader import get_mlb_pitching_stats, get_mlb_pitching_stats_range

_RED = "#E63946"
_PANEL = "rgba(26,26,46,0.6)"
_FONT = "#EAEAEA"
# Low ERA = good, so run cool->hot reversed for "lower is better" coloring.
_ERA_SCALE = ["#2E7D32", "#9ACD32", "#FFD166", _RED]


def _style_plotly(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=_PANEL,
        font_color=_FONT,
        margin=dict(l=20, r=20, t=40, b=20),
        coloraxis_colorbar=dict(thickness=10),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    return fig


def _leader_metrics(df: pd.DataFrame, span_label: str, ip_floor: float):
    qual = df[df["IP"] >= ip_floor]
    pool = qual if not qual.empty else df
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pitchers", f"{len(df):,}", span_label, delta_color="off")
    if not pool.empty:
        era = pool.loc[pool["ERA"].idxmin()]
        m2.metric("ERA Leader", f"{era['ERA']:.2f}", era["Name"], delta_color="off")
        k = df.loc[df["SO"].idxmax()]
        m3.metric("Strikeout Leader", f"{int(k['SO'])} K", k["Name"], delta_color="off")
        whip = pool.loc[pool["WHIP"].idxmin()]
        m4.metric("WHIP Leader", f"{whip['WHIP']:.2f}", whip["Name"], delta_color="off")


def _leaderboard_table(df: pd.DataFrame, key: str):
    display = ["Name", "Team", "W", "L", "ERA", "G", "GS", "IP", "SO", "BB",
               "H", "HR", "WHIP", "K9", "BB9", "HR9", "AVG"]
    available = [c for c in display if c in df.columns]
    styler = df[available].style.format({
        "ERA": "{:.2f}", "WHIP": "{:.2f}", "K9": "{:.2f}",
        "BB9": "{:.2f}", "HR9": "{:.2f}", "AVG": "{:.3f}", "IP": "{:.1f}",
    })
    for col, cmap in (("ERA", "RdYlGn_r"), ("WHIP", "RdYlGn_r"), ("K9", "RdYlGn")):
        if col in available:
            styler = styler.background_gradient(subset=[col], cmap=cmap)
    st.dataframe(
        styler, width="stretch", height=460, hide_index=True, key=key,
        column_config={"Name": st.column_config.TextColumn("Pitcher", width="medium")},
    )


def _leader_charts(df: pd.DataFrame, ip_floor: float):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Strikeout Leaders")
        top = df.nlargest(15, "SO").sort_values("SO")
        fig = px.bar(
            top, x="SO", y="Name", orientation="h",
            color="ERA", color_continuous_scale=_ERA_SCALE,
            text="SO", labels={"SO": "Strikeouts"},
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        _style_plotly(fig)
        fig.update_layout(yaxis_title=None)
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown("#### K/9 vs. ERA")
        qual = df[df["IP"] >= ip_floor]
        plot_df = qual if not qual.empty else df
        fig2 = px.scatter(
            plot_df, x="K9", y="ERA", size="IP", hover_name="Name",
            color="WHIP", color_continuous_scale=_ERA_SCALE, size_max=24,
            labels={"K9": "K/9", "ERA": "ERA"},
        )
        # Lower ERA is better — put the best arms at the top.
        fig2.update_yaxes(autorange="reversed")
        _style_plotly(fig2)
        st.plotly_chart(fig2, width="stretch")


def render():
    st.markdown('<div class="section-header">Pitching Leaderboard</div>', unsafe_allow_html=True)

    today = datetime.date.today()
    season_start = datetime.date(today.year, 3, 20)
    if season_start > today:
        season_start = datetime.date(today.year - 1, 3, 20)

    source = st.radio(
        "Data Source",
        ["Full Season", "Recent Form"],
        horizontal=True,
        key="pitch_source",
    )
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

    if source == "Full Season":
        st.caption("Full-season totals from the MLB Stats API.")
        with st.spinner("Pulling season pitching stats..."):
            df = get_mlb_pitching_stats(today.year)
        span_label = f"{today.year} season"
    else:
        st.caption("Each pitcher's recent outings over the selected window — "
                   "a few weeks captures a weekly starter's last few starts.")
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            preset = st.selectbox(
                "Quick Range",
                ["Last 21 Days", "Last 7 Days", "Last 14 Days", "Last 30 Days", "Custom"],
                key="pitch_preset",
            )
        windows = {"Last 7 Days": 7, "Last 14 Days": 14, "Last 21 Days": 21, "Last 30 Days": 30}
        if preset in windows:
            pre_start, pre_end = today - datetime.timedelta(days=windows[preset]), today
        else:
            pre_start, pre_end = None, None
        with col2:
            start_date = st.date_input("Start Date", value=pre_start or (today - datetime.timedelta(days=21)),
                                       min_value=season_start, max_value=today, key="pitch_start")
        with col3:
            end_date = st.date_input("End Date", value=pre_end or today,
                                     min_value=season_start, max_value=today, key="pitch_end")
        if start_date > end_date:
            st.error("Start date must be on or before the end date.")
            return
        with st.spinner("Pulling recent pitching stats..."):
            df = get_mlb_pitching_stats_range(start_date.isoformat(), end_date.isoformat())
        span_label = f"{start_date:%b %d} – {end_date:%b %d}"

    if df.empty:
        st.warning("No pitching stats available for this selection.")
        return

    # --- Filters ---
    f1, f2 = st.columns([1, 2])
    with f1:
        max_ip = int(df["IP"].max()) if not df.empty else 0
        cap = max(5, min(100, max_ip))
        default_ip = min(10 if source == "Full Season" else 3, cap)
        min_ip = st.slider("Minimum IP", 0, cap, default_ip, step=1, key="pitch_min_ip")
    with f2:
        teams = sorted(df["Team"].dropna().unique().tolist())
        team_filter = st.multiselect("Filter by Team", options=teams, default=[], key="pitch_team")

    ip_floor = max(1.0, float(min_ip))
    if min_ip > 0:
        df = df[df["IP"] >= min_ip]
    if team_filter:
        df = df[df["Team"].isin(team_filter)]
    if df.empty:
        st.info("No pitchers match the current filters.")
        return

    df = df.sort_values("IP", ascending=False).reset_index(drop=True)

    _leader_metrics(df, span_label, ip_floor)
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    _leaderboard_table(df, key=f"pitch_table_{source}")
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    _leader_charts(df, ip_floor)
