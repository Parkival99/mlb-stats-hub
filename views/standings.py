"""Standings page — division standings from MLB Stats API with team colors."""

import streamlit as st
import pandas as pd
from data_loader import get_standings

# Primary team colors (hex) for row background
TEAM_COLORS = {
    "Arizona Diamondbacks": "#A71930",
    "Atlanta Braves": "#CE1141",
    "Baltimore Orioles": "#DF4601",
    "Boston Red Sox": "#BD3039",
    "Chicago Cubs": "#0E3386",
    "Chicago White Sox": "#27251F",
    "Cincinnati Reds": "#C6011F",
    "Cleveland Guardians": "#00385D",
    "Colorado Rockies": "#333366",
    "Detroit Tigers": "#0C2340",
    "Houston Astros": "#002D62",
    "Kansas City Royals": "#004687",
    "Los Angeles Angels": "#BA0021",
    "Los Angeles Dodgers": "#005A9C",
    "Miami Marlins": "#00A3E0",
    "Milwaukee Brewers": "#12284B",
    "Minnesota Twins": "#002B5C",
    "New York Mets": "#002D72",
    "New York Yankees": "#003087",
    "Oakland Athletics": "#003831",
    "Philadelphia Phillies": "#E81828",
    "Pittsburgh Pirates": "#27251F",
    "San Diego Padres": "#2F241D",
    "San Francisco Giants": "#FD5A1E",
    "Seattle Mariners": "#0C2C56",
    "St. Louis Cardinals": "#C41E3A",
    "Tampa Bay Rays": "#092C5C",
    "Texas Rangers": "#003278",
    "Toronto Blue Jays": "#134A8E",
    "Washington Nationals": "#AB0003",
    "Athletics": "#003831",
}


def _get_team_color(team_name: str) -> str:
    """Get team's primary color, with fuzzy matching for short names."""
    if team_name in TEAM_COLORS:
        return TEAM_COLORS[team_name]
    # Try partial match (API sometimes returns just "Guardians" etc.)
    for full_name, color in TEAM_COLORS.items():
        if team_name in full_name or full_name.endswith(team_name):
            return color
    return "#2A2A4A"


def render():
    st.markdown('<div class="section-header">MLB Standings</div>', unsafe_allow_html=True)

    standings = get_standings()

    if standings.empty:
        st.warning("Could not load standings data.")
        return

    all_divisions = standings["Division"].unique().tolist()
    al_divisions = sorted([d for d in all_divisions if "American" in d])
    nl_divisions = sorted([d for d in all_divisions if "National" in d])

    if not al_divisions and not nl_divisions:
        al_divisions = all_divisions[:len(all_divisions) // 2]
        nl_divisions = all_divisions[len(all_divisions) // 2:]

    al_col, nl_col = st.columns(2)

    with al_col:
        st.markdown("### American League")
        for div in al_divisions:
            div_df = standings[standings["Division"] == div].copy()
            if div_df.empty:
                continue
            short_name = div.replace("American League", "AL")
            st.markdown(f"**{short_name}**")
            _render_standings_table(div_df)

    with nl_col:
        st.markdown("### National League")
        for div in nl_divisions:
            div_df = standings[standings["Division"] == div].copy()
            if div_df.empty:
                continue
            short_name = div.replace("National League", "NL")
            st.markdown(f"**{short_name}**")
            _render_standings_table(div_df)


def _render_standings_table(div_df: pd.DataFrame):
    """Render a division standings table with team-colored row backgrounds and white text."""
    rows_html = ""
    for _, row in div_df.iterrows():
        bg = _get_team_color(row["Team"])
        cell_style = f'padding:8px 12px; color:#FFFFFF; font-weight:500;'
        rows_html += (
            f'<tr style="background-color:{bg};">'
            f'<td style="{cell_style} font-weight:600;">{row["Team"]}</td>'
            f'<td style="{cell_style} text-align:center;">{row["W"]}</td>'
            f'<td style="{cell_style} text-align:center;">{row["L"]}</td>'
            f'<td style="{cell_style} text-align:center;">{row["PCT"]:.3f}</td>'
            f'<td style="{cell_style} text-align:center;">{row["GB"]}</td>'
            f'<td style="{cell_style} text-align:center;">{row["Streak"]}</td>'
            f'</tr>'
        )

    header_style = 'padding:8px 12px; text-align:center; color:#8888AA; font-size:0.75rem; text-transform:uppercase; letter-spacing:1px; background:#0F0F23;'
    header = (
        f'<th style="{header_style} text-align:left;">Team</th>'
        f'<th style="{header_style}">W</th>'
        f'<th style="{header_style}">L</th>'
        f'<th style="{header_style}">PCT</th>'
        f'<th style="{header_style}">GB</th>'
        f'<th style="{header_style}">Streak</th>'
    )

    html = (
        f'<table style="width:100%; border-collapse:collapse; margin-bottom:20px; '
        f'border-radius:10px; overflow:hidden; border:1px solid #2A2A4A;">'
        f'<thead><tr>{header}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
    )

    st.markdown(html, unsafe_allow_html=True)
