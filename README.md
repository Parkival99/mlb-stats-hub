# ⚾ MLB Stats Hub

A sleek, auto-updating MLB statistics dashboard built with Streamlit.

## Features

- **Live Dashboard** — Today's games with scores, probable pitchers, and venue info
- **Who's Hot / Cold** — Rolling 7-day performance highlights
- **Batting Stats** — Full leaderboard with custom date ranges, Statcast + FanGraphs data
- **Pitching Stats** — K/9, whiff rate, strikeouts with advanced Statcast metrics
- **Standings** — Current division standings with records and streaks
- **Auto-refresh** — Data caches with TTL so stats update throughout the day

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app will open at `http://localhost:8501`.

## Deploy (Free) on Streamlit Community Cloud

1. Push this project to a GitHub repo
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub account
4. Select the repo and set `app.py` as the main file
5. Click **Deploy** — you'll get a public URL to share with friends

## Data Sources

- **[pybaseball](https://github.com/jldbc/pybaseball)** — Statcast & FanGraphs data
- **MLB Stats API** — Live scores, schedules, standings (free, no API key needed)

## Project Structure

```
MLB project/
├── app.py              # Main entry point & navigation
├── data_loader.py      # All data fetching & caching logic
├── requirements.txt    # Python dependencies
├── .streamlit/
│   └── config.toml     # Theme & server config
└── pages/
    ├── dashboard.py    # Today's games, hot/cold players
    ├── batting.py      # Batting leaderboard with date filters
    ├── pitching.py     # Pitching leaderboard (K/9, whiff rate)
    └── standings.py    # Division standings
```
