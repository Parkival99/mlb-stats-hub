"""
MLB Stats Dashboard — Main Entry Point
Run with: streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="MLB Stats Hub",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS for sleek dark UI
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* ---- Global ---- */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* ---- Hide sidebar completely ---- */
    section[data-testid="stSidebar"] {
        display: none !important;
    }

    /* ---- Top nav bar ---- */
    .top-nav {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 0;
        margin-bottom: 1rem;
        border-bottom: 1px solid #2A2A4A;
        flex-wrap: wrap;
        gap: 8px;
    }
    .top-nav .brand {
        font-size: 1.3rem;
        font-weight: 700;
        color: #EAEAEA;
        white-space: nowrap;
    }

    /* Restyle the segmented control (radio) as pill nav */
    div[data-testid="stHorizontalBlock"] .stRadio > div {
        display: flex !important;
        flex-direction: row !important;
        gap: 6px !important;
        flex-wrap: wrap !important;
    }
    div[data-testid="stHorizontalBlock"] .stRadio > div > label {
        background: #1A1A2E !important;
        border: 1px solid #2A2A4A !important;
        border-radius: 10px !important;
        padding: 10px 28px !important;
        color: #EAEAEA !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        cursor: pointer !important;
        transition: all 0.2s ease !important;
        white-space: nowrap !important;
    }
    div[data-testid="stHorizontalBlock"] .stRadio > div > label:hover {
        background: rgba(230, 57, 70, 0.15) !important;
        border-color: #E63946 !important;
    }
    div[data-testid="stHorizontalBlock"] .stRadio > div > label[data-checked="true"],
    div[data-testid="stHorizontalBlock"] .stRadio > div > label:has(input:checked) {
        background: #E63946 !important;
        border-color: #E63946 !important;
        color: white !important;
    }

    /* ---- Mobile tweaks ---- */
    @media (max-width: 768px) {
        .player-row { flex-wrap: wrap !important; gap: 6px !important; }
        .game-score { font-size: 1.1rem !important; }
        div[data-testid="stHorizontalBlock"] .stRadio > div > label {
            padding: 8px 16px !important;
            font-size: 0.9rem !important;
        }
    }

    /* ---- Cards / Metric containers ---- */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
        border: 1px solid #2A2A4A;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }

    div[data-testid="stMetric"] label {
        color: #8888AA;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #FFFFFF;
        font-weight: 700;
    }

    /* ---- Dataframes ---- */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #2A2A4A;
    }

    /* ---- Buttons ---- */
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #E63946;
        color: #E63946;
        background: transparent;
        font-weight: 600;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        background: #E63946;
        color: white;
    }

    /* ---- Tab styling ---- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 20px;
        font-weight: 500;
    }

    /* ---- Section headers ---- */
    .section-header {
        font-size: 1.4rem;
        font-weight: 700;
        color: #EAEAEA;
        margin-bottom: 0.5rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #E63946;
        display: inline-block;
    }

    /* ---- Game cards ---- */
    .game-card {
        background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
        border: 1px solid #2A2A4A;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }

    .game-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.4);
    }

    .game-card .teams {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }

    .game-card .team-name {
        font-weight: 600;
        font-size: 1.1rem;
        color: #EAEAEA;
    }

    .game-card .score {
        font-size: 1.8rem;
        font-weight: 700;
        color: #E63946;
        text-align: center;
    }

    .game-card .record {
        font-size: 0.8rem;
        color: #8888AA;
    }

    .game-card .status {
        text-align: center;
        font-size: 0.75rem;
        color: #8888AA;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .game-card .pitcher {
        font-size: 0.85rem;
        color: #AAAACC;
    }

    /* ---- Hot / Cold badges ---- */
    .hot-badge {
        background: linear-gradient(135deg, #E63946 0%, #FF6B6B 100%);
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }

    .cold-badge {
        background: linear-gradient(135deg, #1E90FF 0%, #63B3ED 100%);
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }

    /* ---- Player row ---- */
    .player-row {
        background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
        border: 1px solid #2A2A4A;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
    }

    .player-row .name {
        font-weight: 600;
        color: #EAEAEA;
        font-size: 1rem;
    }

    .player-row .stat {
        color: #E63946;
        font-weight: 700;
        font-size: 1.1rem;
    }

    .player-row .detail {
        color: #8888AA;
        font-size: 0.8rem;
    }

    /* ---- Divider ---- */
    .custom-divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, #2A2A4A, transparent);
        margin: 1.5rem 0;
    }

    /* Auto-refresh indicator */
    .refresh-badge {
        background: rgba(230, 57, 70, 0.15);
        color: #E63946;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.7rem;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Top navigation bar
# ---------------------------------------------------------------------------
nav_left, nav_right = st.columns([5, 1])

with nav_left:
    st.markdown('<span style="font-size:2rem;font-weight:700;color:#EAEAEA;letter-spacing:-0.5px;">⚾ MLB Stats Hub</span>'
                '&nbsp;&nbsp;<span class="refresh-badge">Auto-refreshes</span>',
                unsafe_allow_html=True)

with nav_right:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

page = st.radio(
    "Navigate",
    ["Dashboard", "Matchups", "Batting Stats", "Pitching Stats", "Standings", "Player"],
    horizontal=True,
    label_visibility="collapsed",
    key="main_nav",
)

st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------
if page == "Dashboard":
    from views import dashboard
    dashboard.render()
elif page == "Matchups":
    from views import matchups
    matchups.render()
elif page == "Batting Stats":
    from views import batting
    batting.render()
elif page == "Pitching Stats":
    from views import pitching
    pitching.render()
elif page == "Standings":
    from views import standings
    standings.render()
elif page == "Player":
    from views import player
    player.render()
