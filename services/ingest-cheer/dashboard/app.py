"""
USAG Gymnastics Meet Tracker — Streamlit Dashboard
Run with: streamlit run dashboard/app.py
"""

import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Gymnastics Meet Tracker",
    page_icon="🤸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme / CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Header */
    .dash-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
        color: white;
        padding: 1.2rem 1.8rem;
        border-radius: 12px;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .dash-header h1 { margin: 0; font-size: 1.6rem; font-weight: 700; }
    .dash-header p  { margin: 0; font-size: 0.85rem; opacity: 0.75; }

    /* KPI cards */
    .kpi-card {
        background: white;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        border-left: 4px solid #e84393;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        margin-bottom: 0.5rem;
    }
    .kpi-title { font-size: 0.75rem; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    .kpi-value { font-size: 1.7rem; font-weight: 700; color: #1a1a2e; line-height: 1.2; }
    .kpi-sub   { font-size: 0.78rem; color: #666; margin-top: 2px; }

    /* Score table */
    .place-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    
    /* Medal indicators - make them stand out from scores */
    /* Note: Unicode circled numbers (④⑤⑥) are used for places 4-6 */
    /* They are visually distinct and slightly larger than regular numbers */

    /* Flip Zone spotlight */
    .fz-header {
        background: linear-gradient(135deg, #6a0dad 0%, #e84393 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
    }
    .fz-header h2 { margin: 0; font-size: 1.3rem; font-weight: 700; }
    .fz-header p  { margin: 0.2rem 0 0 0; font-size: 0.82rem; opacity: 0.85; }
    
    /* Meet and athlete search input styling - darker text */
    div[data-testid="stTextInput"]:has(input[placeholder*="Search"]) input {
        color: #1a1a2e !important;
    }
    div[data-testid="stTextInput"]:has(input[placeholder*="Search"]) input::placeholder {
        color: #666 !important;
        font-weight: 400 !important;
        opacity: 1 !important;
    }
    
    /* Match selectbox placeholder styling to text input placeholder */
    /* Style selectbox text to match placeholder - lighter gray, regular weight */
    div[data-testid="stSelectbox"]:not(:has([id*="fz_gym"])) [data-baseweb="select"] > div:first-child {
        color: #666 !important;
        font-weight: 400 !important;
    }

    /* Gym selectbox only — purple border and white bg, scoped to fz_gym key */
    div[data-testid="stSelectbox"]:has(> div > div[data-baseweb="select"] [id*="fz_gym"]) [data-baseweb="select"] > div:first-child,
    div[data-testid="stSelectbox"][aria-label="Select Gym"] [data-baseweb="select"] > div:first-child {
        background-color: white !important;
        border: 2px solid #7b52ab !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        color: #6a0dad !important;
        box-shadow: none !important;
    }
    .gold-badge   { background: #ffd700; color: #333; padding: 2px 8px; border-radius: 10px; font-weight: 700; font-size: 0.8rem; }
    .event-card   { background: white; border-radius: 8px; padding: 0.8rem 1rem; border-top: 3px solid #e84393; box-shadow: 0 2px 6px rgba(0,0,0,0.07); }
    .event-card .ev-label { font-size: 0.7rem; color: #888; text-transform: uppercase; font-weight: 600; }
    .event-card .ev-score { font-size: 1.5rem; font-weight: 700; color: #1a1a2e; }
    .event-card .ev-name  { font-size: 0.82rem; color: #555; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0 0; font-weight: 500; }

    /* The Flip Zone tab — purple gradient */
    .stTabs [data-baseweb="tab"]:last-child {
        background: linear-gradient(135deg, #6a0dad 0%, #e84393 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 8px 8px 0 0 !important;
    }
    .stTabs [data-baseweb="tab"]:last-child p {
        color: white !important;
        font-weight: 600 !important;
    }
    .stTabs [data-baseweb="tab"]:last-child[aria-selected="true"] {
        background: linear-gradient(135deg, #5a0b9d 0%, #c0306a 100%) !important;
    }
</style>
""", unsafe_allow_html=True)

# JS: Match selectbox placeholder styling to text input and clear search on focus
st.markdown("""
<script>
(function() {
    function styleSelectboxPlaceholders() {
        document.querySelectorAll('[data-testid="stSelectbox"] [data-baseweb="select"] > div:first-child').forEach(function(el) {
            const text = el.textContent || el.innerText || '';
            // If text starts with "--", it's a placeholder - style it lighter
            if (text.trim().startsWith('--')) {
                el.style.color = '#666';
                el.style.fontWeight = '400';
            } else if (text.trim() && !text.includes('Select')) {
                // Actual selected value - make it darker
                el.style.color = '#1a1a2e';
                el.style.fontWeight = '400';
            }
        });
    }
    // Run on load and after mutations
    styleSelectboxPlaceholders();
    const observer = new MutationObserver(styleSelectboxPlaceholders);
    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
""", unsafe_allow_html=True)



# ── Plotly layout defaults ─────────────────────────────────────────────────────
PLOT_LAYOUT = dict(
    paper_bgcolor="#ffffff",
    plot_bgcolor="#f9fafc",
    font=dict(color="#1a1a2e", family="Inter, sans-serif"),
    xaxis=dict(gridcolor="#e8ecf0"),
    yaxis=dict(gridcolor="#e8ecf0"),
)

# ── Level display names ────────────────────────────────────────────────────────
LEVEL_LABELS = {
    "1": "Level 1", "2": "Level 2", "3": "Level 3", "4": "Level 4",
    "5": "Level 5", "6": "Level 6", "7": "Level 7", "8": "Level 8",
    "9": "Level 9", "10": "Level 10",
    "2N": "L2 NGA", "3N": "L3 NGA", "4N": "L4 NGA",
    "2BN": "L2B NGA",
    "XB": "Xcel Bronze", "XS": "Xcel Silver", "XG": "Xcel Gold",
    "XP": "Xcel Platinum", "XD": "Xcel Diamond",
    "L9N": "L9 NGA", "L10": "Level 10", "L12": "Level 12 (HS)",
    "LXSA": "Xcel Silver A",
    "DN": "NGA Diamond", "GN": "NGA Gold", "PN": "NGA Platinum",
    "SN": "NGA Silver", "BN": "NGA Bronze",
}

def level_label(code: str) -> str:
    if not code:
        return "Unknown"
    return LEVEL_LABELS.get(str(code), f"Level {code}")

# ── DB connection ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    url = os.getenv("DATABASE_URL") or st.secrets.get("DATABASE_URL", "")
    if not url:
        st.error("DATABASE_URL not set. Add it to .env or Streamlit secrets.")
        st.stop()
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=3)


def query(sql: str, params: dict = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


# ── Cached data loaders ───────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_meets() -> pd.DataFrame:
    return query("""
        SELECT m.id, m.meet_id, m.name, m.state, m.start_date, m.location,
               COUNT(DISTINCT s.id) AS score_count
        FROM meets m
        LEFT JOIN scores s ON s.meet_id = m.id
        GROUP BY m.id
        ORDER BY m.start_date DESC NULLS LAST, m.name
    """)


@st.cache_data(ttl=300)
def load_meets_with_gyms() -> pd.DataFrame:
    """Load meets with gym information for filtering."""
    return query("""
        SELECT DISTINCT m.id, m.name, m.state, m.start_date, m.location,
               COUNT(DISTINCT s.id) AS score_count,
               STRING_AGG(DISTINCT g.canonical_name, ', ' ORDER BY g.canonical_name) AS gyms
        FROM meets m
        LEFT JOIN scores s ON s.meet_id = m.id
        LEFT JOIN athletes a ON a.id = s.athlete_id
        LEFT JOIN gyms g ON g.id = a.gym_id
        GROUP BY m.id
        ORDER BY m.start_date DESC NULLS LAST, m.name
    """)


@st.cache_data(ttl=300)
def load_meet_scores(meet_id: int) -> pd.DataFrame:
    return query("""
        SELECT a.canonical_name AS athlete, g.canonical_name AS gym,
               s.level, s.event, s.score, s.place
        FROM scores s
        JOIN athletes a ON a.id = s.athlete_id
        LEFT JOIN gyms g ON g.id = a.gym_id
        WHERE s.meet_id = :meet_id
        ORDER BY s.level, s.score DESC
    """, {"meet_id": meet_id})


@st.cache_data(ttl=300)
def load_athlete_scores(canonical_name: str) -> pd.DataFrame:
    return query("""
        SELECT m.name AS meet, m.start_date, m.location, s.level, s.event,
               s.score, s.place, g.canonical_name AS gym
        FROM scores s
        JOIN meets m ON m.id = s.meet_id
        JOIN athletes a ON a.id = s.athlete_id
        LEFT JOIN gyms g ON g.id = a.gym_id
        WHERE a.canonical_name = :name
        ORDER BY m.start_date ASC NULLS LAST
    """, {"name": canonical_name})


@st.cache_data(ttl=300)
def load_rankings(level: str) -> pd.DataFrame:
    return query("""
        SELECT a.canonical_name AS athlete, g.canonical_name AS gym,
               s.score, s.place, m.name AS meet, m.start_date,
               s.level
        FROM scores s
        JOIN athletes a ON a.id = s.athlete_id
        LEFT JOIN gyms g ON g.id = a.gym_id
        JOIN meets m ON m.id = s.meet_id
        WHERE s.level = :level AND s.event = 'AA'
        ORDER BY s.score DESC
    """, {"level": level})


@st.cache_data(ttl=300)
def load_athlete_search(query_str: str, state: str = None, gym: str = None) -> list[str]:
    """Search athletes with optional state and gym filters."""
    sql = """
        SELECT DISTINCT a.canonical_name 
        FROM athletes a
        LEFT JOIN gyms g ON g.id = a.gym_id
        WHERE LOWER(a.canonical_name) LIKE LOWER(:q)
    """
    params = {"q": f"%{query_str}%"}
    
    if state and state != "All":
        sql += " AND g.state = :state"
        params["state"] = state
    
    if gym and gym != "All":
        sql += " AND LOWER(g.canonical_name) = LOWER(:gym)"
        params["gym"] = gym
    
    sql += " ORDER BY a.canonical_name LIMIT 50"
    df = query(sql, params)
    return df["canonical_name"].tolist()


@st.cache_data(ttl=300)
def load_athlete_states() -> list[str]:
    """Get all unique states from athletes' gyms."""
    df = query("""
        SELECT DISTINCT g.state 
        FROM athletes a
        JOIN gyms g ON g.id = a.gym_id
        WHERE g.state IS NOT NULL
        ORDER BY g.state
    """)
    return df["state"].tolist()


@st.cache_data(ttl=300)
def load_athlete_gyms(state: str = None) -> list[str]:
    """Get all unique gyms from athletes, optionally filtered by state."""
    if state and state != "All":
        df = query("""
            SELECT DISTINCT g.canonical_name
            FROM athletes a
            JOIN gyms g ON g.id = a.gym_id
            WHERE g.state = :state
            ORDER BY g.canonical_name
        """, {"state": state})
    else:
        df = query("""
            SELECT DISTINCT g.canonical_name
            FROM athletes a
            JOIN gyms g ON g.id = a.gym_id
            ORDER BY g.canonical_name
        """)
    return df["canonical_name"].tolist()


@st.cache_data(ttl=300)
def load_gym_athletes(gym_name: str) -> pd.DataFrame:
    """All scores for athletes belonging to a gym (exact match on canonical name)."""
    return query("""
        SELECT a.canonical_name AS athlete,
               g.canonical_name AS gym,
               s.level, s.event, s.score, s.place, s.division,
               m.name AS meet, m.start_date, m.location
        FROM scores s
        JOIN athletes a ON a.id = s.athlete_id
        LEFT JOIN gyms g ON g.id = a.gym_id
        JOIN meets m ON m.id = s.meet_id
        WHERE g.canonical_name = :gym
        ORDER BY a.canonical_name, s.event, s.score DESC
    """, {"gym": gym_name})


@st.cache_data(ttl=300)
def load_gym_names() -> list[str]:
    df = query("SELECT canonical_name FROM gyms ORDER BY canonical_name")
    return df["canonical_name"].tolist()




# ── Header ────────────────────────────────────────────────────────────────────
# st.markdown("""
# <div class="dash-header">
#     <div>
#         <h1>🤸 Gymnastics Meet Tracker</h1>
#         <p>Meet results · Athlete profiles · Rankings · Score trends</p>
#     </div>
# </div>
# """, unsafe_allow_html=True)

# ── KPI data (loaded here, rendered at bottom) ────────────────────────────────
meets_df = load_meets()
meets_with_scores = meets_df[meets_df["score_count"] > 0]

total_scores = query("SELECT COUNT(*) AS c FROM scores").iloc[0]["c"]
total_athletes = query("SELECT COUNT(*) AS c FROM athletes").iloc[0]["c"]
total_gyms = query("SELECT COUNT(*) AS c FROM gyms").iloc[0]["c"]

# ── Main tabs ─────────────────────────────────────────────────────────────────
tab_flipzone, tab_analytics, tab_athlete, tab_meets = st.tabs([
    "🏅 Gym Spotlight", "📊 Analytics", "👤 Athlete Profile", "📋 Meet Results"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GYM SPOTLIGHT  
# ═══════════════════════════════════════════════════════════════════════════════
with tab_flipzone:
    # ── Gym selector ──────────────────────────────────────────────────────────
    all_gyms = load_gym_names()
    fz_default = next((g for g in all_gyms if g.lower() == "the flip zone"), None)
    if not fz_default:
        fz_default = next((g for g in all_gyms if "flip zone" in g.lower()), None)
    fz_default_idx = all_gyms.index(fz_default) if fz_default else 0

    # Use a separate key to store the chosen gym so the selectbox can reset to placeholder
    if "fz_selected_gym" not in st.session_state:
        st.session_state["fz_selected_gym"] = fz_default
    if "fz_gym_counter" not in st.session_state:
        st.session_state["fz_gym_counter"] = 0

    selected_gym = st.session_state["fz_selected_gym"] or fz_default
    bar_title = selected_gym or "The Flip Zone"

    # Determine header gradient based on gym
    if selected_gym and "jaycie phelps athletic center" in selected_gym.lower():
        # JPAC team colors: red to blue gradient (maintains white text contrast)
        header_gradient = "linear-gradient(135deg, #DC143C 0%, #C41E3A 30%, #0066CC 70%, #003366 100%)"
    else:
        # Default purple gradient for other gyms
        header_gradient = "linear-gradient(135deg, #6a0dad 0%, #e84393 100%)"

    # Full-width bar — title and colors update when gym is selected
    st.markdown(f"""
    <div class="fz-header" style="background: {header_gradient};">
        <div>
            <h2>🏅 {bar_title} — Season Spotlight</h2>
            <p>Personal bests · Level breakdowns · Medal summaries</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Counter-based key forces a fresh widget (back to placeholder) after each pick
    picked = st.selectbox(
        "Select Gym", all_gyms, index=None,
        key=f"fz_gym_{st.session_state['fz_gym_counter']}",
        label_visibility="collapsed",
        placeholder="Select Gym",
    )
    if picked:
        st.session_state["fz_selected_gym"] = picked
        st.session_state["fz_gym_counter"] += 1
        # Reset athlete selection when gym changes
        for key in ("fz_athlete_select", "fz_viewing_athlete", "fz_athlete_select_counter"):
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    fz_df = load_gym_athletes(selected_gym)

    if fz_df.empty:
        st.info(f"No score data found for **{selected_gym}** yet. Run ingest to populate.")
    else:
        # Sort athletes by last name (ABC order)
        def get_last_name(name):
            parts = name.split()
            return parts[-1] if len(parts) > 1 else name
        athletes_in_gym = sorted(fz_df["athlete"].unique(), key=get_last_name)
        def _level_sort_key(lv):
            s = str(lv)
            try:
                return (0, float(s))
            except ValueError:
                return (1, s)
        levels_in_gym = sorted(fz_df["level"].dropna().unique(), key=_level_sort_key)

        # ── KPIs — right under gym selector ───────────────────────────────────
        aa_df = fz_df[fz_df["event"] == "AA"]
        ev_df = fz_df[fz_df["event"] != "AA"]

        k1, k2, k3, k4 = st.columns(4)
        for col, title, val, sub, color in [
            (k1, "Gymnasts",        len(athletes_in_gym),           "On the roster",              "#e84393"),
            (k2, "Levels Competed", len(levels_in_gym),             "Across all meets",            "#7b52ab"),
            (k3, "Meets Attended",  fz_df["meet"].nunique(),        "This season",                 "#1a9e4a"),
            (k4, "Total Entries",   len(aa_df),                     "All-around score records",    "#1a7abf"),
        ]:
            col.markdown(f"""
            <div class="kpi-card" style="border-left-color:{color}">
                <div class="kpi-title">{title}</div>
                <div class="kpi-value">{val}</div>
                <div class="kpi-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)

        st.divider()

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 1 — BEST SCORES BY LEVEL & EVENT
        # ══════════════════════════════════════════════════════════════════════
        st.markdown("### 🥇 Personal Bests by Level")
        st.caption("Each gymnast's highest recorded score per event, grouped by level.")

        level_filter_opts = ["All Levels"] + [level_label(l) for l in levels_in_gym]
        level_filter_raw  = ["All Levels"] + list(levels_in_gym)
        sel_fz_level_idx = st.selectbox(
            "Filter by level", range(len(level_filter_opts)),
            format_func=lambda i: level_filter_opts[i], key="fz_level"
        )

        fz_filtered = fz_df.copy()
        if sel_fz_level_idx > 0:
            fz_filtered = fz_filtered[fz_filtered["level"] == level_filter_raw[sel_fz_level_idx]]

        EVENT_ORDER = ["AA", "VT", "UB", "BB", "FX"]
        EVENT_LABELS = {"AA": "All-Around", "VT": "Vault", "UB": "Bars", "BB": "Beam", "FX": "Floor"}

        # Best score per athlete per event
        if not fz_filtered.empty:
            best_per_event = (
                fz_filtered.groupby(["athlete", "level", "event"])["score"]
                .max().reset_index()
            )

            if not best_per_event.empty:
                # Pivot so each event is a column
                pivot = best_per_event.pivot_table(
                    index=["athlete", "level"], columns="event", values="score"
                ).reset_index()
                pivot.columns.name = None

                # Ensure all event columns exist
                for ev in EVENT_ORDER:
                    if ev not in pivot.columns:
                        pivot[ev] = None

                pivot = pivot[["athlete", "level"] + [e for e in EVENT_ORDER if e in pivot.columns]]
                pivot["_level_sort"] = pivot["level"].apply(_level_sort_key)
                pivot = pivot.sort_values(["_level_sort", "AA"], ascending=[True, False]).drop(columns=["_level_sort"]).reset_index(drop=True)
                pivot.index += 1
                pivot["level"] = pivot["level"].apply(level_label)

                rename_map = {"athlete": "Athlete", "level": "Level"}
                rename_map.update({ev: EVENT_LABELS.get(ev, ev) for ev in EVENT_ORDER})
                display_pivot = pivot.rename(columns=rename_map)

                # Keep score columns as floats so dataframe sorts numerically
                score_col_config = {
                    "Level":   st.column_config.TextColumn("Level",   width="medium"),
                    "Athlete": st.column_config.TextColumn("Athlete", width="medium"),
                }
                for col_name in EVENT_LABELS.values():
                    if col_name in display_pivot.columns:
                        display_pivot[col_name] = pd.to_numeric(display_pivot[col_name], errors="coerce")
                        score_col_config[col_name] = st.column_config.NumberColumn(col_name, format="%.3f")

                st.dataframe(display_pivot, width='stretch', height=400,
                             column_config=score_col_config)
            else:
                st.info(f"No score data found for the selected level filter.")
        else:
            st.info(f"No score data found for the selected level filter.")

        st.divider()

        # ── Level Highlights compact table ────────────────────────────────────
        st.markdown("### 🎯 Level Highlights — Top Score Each Event")
        highlight_rows = []
        
        # Always show all levels for this gym (do not filter by level dropdown)
        levels_to_show = levels_in_gym
        
        for lv in levels_to_show:
            lv_df = fz_df[fz_df["level"] == lv]
            row = {"Level": level_label(lv)}
            for ev in EVENT_ORDER:
                ev_data = lv_df[lv_df["event"] == ev]
                if not ev_data.empty:
                    max_score = ev_data["score"].max()
                    # Find all athletes with the max score (handle ties)
                    tied_athletes = ev_data[ev_data["score"] == max_score]["athlete"].unique()
                    # Get first names
                    first_names = [name.split()[0] for name in tied_athletes]
                    if len(first_names) == 1:
                        row[EVENT_LABELS[ev]] = f"{max_score:.3f} · {first_names[0]}"
                    else:
                        # Format: "9.850 · Sophie and Piper"
                        names_str = " and ".join(first_names)
                        row[EVENT_LABELS[ev]] = f"{max_score:.3f} · {names_str}"
                else:
                    row[EVENT_LABELS[ev]] = "—"
            highlight_rows.append(row)
        
        if highlight_rows:
            hl_df = pd.DataFrame(highlight_rows).set_index("Level")
            st.dataframe(hl_df, width='stretch',
                         height=35 * (len(highlight_rows) + 1) + 38,
                         column_config={"Level": st.column_config.TextColumn("Level", width="medium")})
        else:
            st.info("No highlight data available for the selected level.")
        
        st.divider()

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 2 — MEDAL & PLACEMENT SUMMARY
        # ══════════════════════════════════════════════════════════════════════
        st.markdown("### 🏆 Medal & Placement Summary")
        st.caption("Total medals and top placements across all meets and events.")

        if not fz_df.empty:
            # Count placements by category
            placements = fz_df[fz_df["place"].notna()].copy()
            
            if not placements.empty:
                medal_counts = []
                for athlete in athletes_in_gym:
                    athlete_data = placements[placements["athlete"] == athlete]
                    athlete_places = athlete_data["place"]
                    if not athlete_places.empty:
                        gold = (athlete_places == 1).sum()
                        silver = (athlete_places == 2).sum()
                        bronze = (athlete_places == 3).sum()
                        fourth_place = (athlete_places == 4).sum()
                        fifth_place = (athlete_places == 5).sum()
                        # Total counts all placements 1-5
                        total_placements = ((athlete_places >= 1) & (athlete_places <= 5)).sum()
                        
                        # Get level(s) - show most common level, or all if multiple
                        athlete_levels = athlete_data["level"].dropna().unique()
                        if len(athlete_levels) > 0:
                            # Get most common level
                            level_counts = athlete_data["level"].value_counts()
                            most_common_level = level_counts.index[0]
                            level_display = level_label(most_common_level)
                            # If athlete competed at multiple levels, show count
                            if len(athlete_levels) > 1:
                                level_display += f" (+{len(athlete_levels)-1})"
                        else:
                            level_display = "—"
                        
                        if total_placements > 0:
                            medal_counts.append({
                                "Athlete": athlete,
                                "Level": level_display,
                                "🥇": gold,
                                "🥈": silver,
                                "🥉": bronze,
                                "4th Place": fourth_place,
                                "5th Place": fifth_place,
                                "Total": total_placements,
                            })
                
                if medal_counts:
                    medal_df = pd.DataFrame(medal_counts)
                    medal_df = medal_df.sort_values(["🥇", "🥈", "🥉", "4th Place", "5th Place"], ascending=False).reset_index(drop=True)
                    medal_df.index += 1
                    
                    st.dataframe(
                        medal_df,
                        width='stretch',
                        height=min(400, 50 * (len(medal_df) + 1)),
                        column_config={
                            "Athlete": st.column_config.TextColumn("Athlete", width="large"),
                            "Level": st.column_config.TextColumn("Level", width="small"),
                            "🥇": st.column_config.TextColumn("1st 🥇", width="small"),
                            "🥈": st.column_config.TextColumn("2nd 🥈", width="small"),
                            "🥉": st.column_config.TextColumn("3rd 🥉", width="small"),
                            "4th Place": st.column_config.TextColumn("4th", width="small"),
                            "5th Place": st.column_config.TextColumn("5th", width="small"),
                            "Total": st.column_config.TextColumn("Total", width="small"),
                        }
                    )
                else:
                    st.info("No placement data available yet.")
            else:
                st.info("No placement data available yet.")

        st.divider()

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 3 — ATHLETE SEASON SUMMARY
        # ══════════════════════════════════════════════════════════════════════
        st.markdown("### 👤 Athlete Season Summary")
        st.caption("Select an athlete to view their full season across all events.")

        # Dropdown: placeholder when closed; when opened list starts with "— Recent searches —" then ABC section
        RECENT_MAX = 10
        _SENTINEL_RECENT_HEADER = "\0__RECENT_HEADER__\0"
        _SENTINEL_AZ_HEADER = "\0__AZ_HEADER__\0"
        recent_list = st.session_state.get("fz_recent_gymnasts", [])
        recent_in_gym = [a for a in recent_list if a in athletes_in_gym]
        others_abc = [a for a in athletes_in_gym if a not in recent_in_gym]
        # Options: "— Recent searches —", recent names, "— All gymnasts (A–Z) —", then ABC (no "Select a gymnast" in list)
        athlete_options = [_SENTINEL_RECENT_HEADER] + recent_in_gym + [_SENTINEL_AZ_HEADER] + others_abc

        # Who we're viewing (persists after selection). Selectbox uses a counter-based key so we can
        # "reset" it by incrementing the counter (new key = fresh widget showing placeholder).
        viewing_key = "fz_viewing_athlete"
        athlete_counter = st.session_state.get("fz_athlete_select_counter", 0)
        widget_key = f"fz_athlete_select_{athlete_counter}"
        if viewing_key not in st.session_state:
            if selected_gym and ("flip zone" in selected_gym.lower() or selected_gym.lower() == "the flip zone") and "Sophie Arnold" in athletes_in_gym:
                st.session_state[viewing_key] = "Sophie Arnold"
            else:
                st.session_state[viewing_key] = athletes_in_gym[0] if athletes_in_gym else None

        def _athlete_label(opt):
            if opt == _SENTINEL_RECENT_HEADER:
                return "— Recent searches —"
            if opt == _SENTINEL_AZ_HEADER:
                return "— All gymnasts (A–Z) —"
            return opt

        # index=None + placeholder so closed state shows "Select a gymnast"; opened list has no placeholder option
        sel_athlete = st.selectbox(
            "Gymnast",
            athlete_options,
            index=None,
            format_func=_athlete_label,
            key=widget_key,
            placeholder="Select a gymnast",
        )

        # If they picked a header, rerun to reset dropdown to placeholder; if a real gymnast, set viewing and recent
        if sel_athlete in (_SENTINEL_RECENT_HEADER, _SENTINEL_AZ_HEADER):
            st.session_state["fz_athlete_select_counter"] = athlete_counter + 1
            st.rerun()
        if sel_athlete and sel_athlete not in (_SENTINEL_RECENT_HEADER, _SENTINEL_AZ_HEADER):
            st.session_state[viewing_key] = sel_athlete
            new_recent = [sel_athlete] + [a for a in recent_list if a != sel_athlete]
            st.session_state["fz_recent_gymnasts"] = new_recent[:RECENT_MAX]
            st.session_state["fz_athlete_select_counter"] = athlete_counter + 1
            st.rerun()

        sel_athlete = st.session_state.get(viewing_key)
        if not sel_athlete:
            st.info("👆 Select a gymnast from the dropdown above to view their season summary.")
        else:
            ath_df = fz_df[fz_df["athlete"] == sel_athlete].copy()

            if not ath_df.empty:
                ath_aa = ath_df[ath_df["event"] == "AA"]
                ath_ev = ath_df[ath_df["event"] != "AA"]

                # Personal best cards
                st.markdown(f"#### {sel_athlete} — Personal Bests")
                pb_cols = st.columns(5)
                for i, ev in enumerate(EVENT_ORDER):
                    ev_scores = ath_df[ath_df["event"] == ev]["score"]
                    if ev_scores.empty:
                        pb_cols[i].markdown(f"""
                        <div class="event-card">
                            <div class="ev-label">{EVENT_LABELS[ev]}</div>
                            <div class="ev-score" style="color:#ccc;">—</div>
                            <div class="ev-name">No data</div>
                        </div>""", unsafe_allow_html=True)
                    else:
                        pb_cols[i].markdown(f"""
                        <div class="event-card">
                            <div class="ev-label">{EVENT_LABELS[ev]}</div>
                            <div class="ev-score">{ev_scores.max():.3f}</div>
                            <div class="ev-name">avg {ev_scores.mean():.3f}</div>
                        </div>""", unsafe_allow_html=True)

                # AA trend line
                if len(ath_aa) >= 2:
                    st.markdown("#### All-Around Progression")
                    trend = ath_aa.sort_values("start_date").copy()
                    trend["meet_short"] = trend["meet"].str[:28]
                    fig_trend = px.line(
                        trend, x="meet_short", y="score", markers=True,
                        labels={"meet_short": "Meet", "score": "AA Score"},
                        color_discrete_sequence=["#e84393"],
                    )
                    fig_trend.update_layout(**PLOT_LAYOUT, height=300, xaxis_tickangle=-25)
                    fig_trend.update_traces(line=dict(width=2.5), marker=dict(size=9))
                    st.plotly_chart(fig_trend, use_container_width=True)

                # Full score history
                st.markdown("#### Full Competition History")

                def medal(place) -> str:
                    """
                    Return medal/placement indicator for a given place.
                    Uses emoji medals for top 3, and circled numbers for places 4-6.
                    Note: Ties (e.g., "3T") are handled during scraping by extracting
                    the numeric part, so place values are always integers.
                    """
                    try:
                        if place is None or (isinstance(place, float) and pd.isna(place)):
                            return ""
                        p = int(place)
                        if p == 1: return " 🥇"
                        if p == 2: return " 🥈"
                        if p == 3: return " 🥉"
                        if p == 4: return " ④"  # Circled number - visually distinct
                        if p == 5: return " ⑤"
                        if p == 6: return " ⑥"
                    except Exception:
                        pass
                    return ""

                def build_history_table_fz(df: pd.DataFrame) -> pd.DataFrame:
                    rows = []
                    for (meet, start_date, location, level, division), grp in df.groupby(
                        ["meet", "start_date", "location", "level", "division"], dropna=False
                    ):
                        aa_row = grp[grp["event"] == "AA"]
                        aa_place = aa_row['place'].iloc[0] if not aa_row.empty else None
                        try:
                            aa_place_valid = aa_place is not None and not (isinstance(aa_place, float) and pd.isna(aa_place))
                        except Exception:
                            aa_place_valid = False
                        aa_score = aa_row['score'].iloc[0] if not aa_row.empty and pd.notna(aa_row['score'].iloc[0]) and aa_row['score'].iloc[0] != 0 else None
                        row = {
                            "Date":       str(start_date) if pd.notna(start_date) else "—",
                            "Meet":       meet,
                            "Location":   location if pd.notna(location) else "—",
                            "Level":      level_label(level),
                            "Division":   division if pd.notna(division) else "—",
                            "All-Around": f"{aa_score:.3f}{medal(aa_place)}" if aa_score is not None else "—",
                        }
                        for ev, col in [("VT","Vault"),("UB","Bars"),("BB","Beam"),("FX","Floor")]:
                            ev_row = grp[grp["event"] == ev]
                            if not ev_row.empty and pd.notna(ev_row['score'].iloc[0]):
                                ev_place = ev_row['place'].iloc[0] if not ev_row.empty and 'place' in ev_row.columns else None
                                ev_score = ev_row['score'].iloc[0]
                                row[col] = f"{ev_score:.3f}{medal(ev_place)}"
                            else:
                                row[col] = "—"
                        rows.append(row)
                    result = pd.DataFrame(rows)
                    if not result.empty:
                        result = result.sort_values("Date", ascending=True).reset_index(drop=True)
                        result.index += 1
                    return result

                hist_table_fz = build_history_table_fz(ath_df)
                st.dataframe(hist_table_fz, width='stretch', height=350)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_analytics:
    # Hero section with gradient
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #e84393 100%);
                padding: 3rem 2rem;
                border-radius: 16px;
                margin-bottom: 2rem;
                text-align: center;
                box-shadow: 0 8px 24px rgba(0,0,0,0.15);">
        <div style="font-size: 4rem; margin-bottom: 1rem;">📊</div>
        <h1 style="color: white; margin: 0 0 0.5rem 0; font-size: 2.5rem; font-weight: 700;">Analytics Dashboard</h1>
        <p style="color: rgba(255,255,255,0.95); font-size: 1.2rem; margin: 0;">Coming Soon</p>
        <p style="color: rgba(255,255,255,0.85); font-size: 0.95rem; margin-top: 0.5rem;">Powerful insights for coaches, gym owners, and athletes</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Main description
    st.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <p style="font-size: 1.1rem; color: #555; line-height: 1.6;">
            Transform your meet results into actionable insights. Track performance trends, identify strengths and weaknesses, 
            benchmark against competitors, and make data-driven decisions.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Feature categories grid
    st.markdown("### 🎯 Planned Analytics Features")
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Athlete Performance Analytics
        st.markdown("""
        <div style="background: white;
                    border-radius: 12px;
                    padding: 1.5rem;
                    margin-bottom: 1.5rem;
                    border-left: 4px solid #e84393;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                    transition: transform 0.2s;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;">
                <span style="font-size: 2rem;">🤸</span>
                <h3 style="margin: 0; color: #1a1a2e; font-size: 1.3rem;">Athlete Performance</h3>
            </div>
            <ul style="margin: 0; padding-left: 1.5rem; color: #666; line-height: 1.8;">
                <li>Score progression trends over time</li>
                <li>Event consistency & hit rate analysis</li>
                <li>Personal best tracking by event</li>
                <li>Momentum scoring (recent vs season avg)</li>
                <li>Event strength ranking</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # Event Analytics
        st.markdown("""
        <div style="background: white;
                    border-radius: 12px;
                    padding: 1.5rem;
                    margin-bottom: 1.5rem;
                    border-left: 4px solid #7b52ab;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08);">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;">
                <span style="font-size: 2rem;">📊</span>
                <h3 style="margin: 0; color: #1a1a2e; font-size: 1.3rem;">Event Analytics</h3>
            </div>
            <ul style="margin: 0; padding-left: 1.5rem; color: #666; line-height: 1.8;">
                <li>Event-specific weakness identification</li>
                <li>Scoring inflation analysis by meet</li>
                <li>Event difficulty gap analysis</li>
                <li>Consistency index per event</li>
                <li>Event risk scoring</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        # Competitive Benchmarking
        st.markdown("""
        <div style="background: white;
                    border-radius: 12px;
                    padding: 1.5rem;
                    margin-bottom: 1.5rem;
                    border-left: 4px solid #667eea;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08);">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;">
                <span style="font-size: 2rem;">🏆</span>
                <h3 style="margin: 0; color: #1a1a2e; font-size: 1.3rem;">Competitive Benchmarking</h3>
            </div>
            <ul style="margin: 0; padding-left: 1.5rem; color: #666; line-height: 1.8;">
                <li>Ranking trends (state/regional/national)</li>
                <li>Percentile ranking analysis</li>
                <li>Meet strength index</li>
                <li>Score needed to win/qualify</li>
                <li>Qualification tracker</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # Program Analytics
        st.markdown("""
        <div style="background: white;
                    border-radius: 12px;
                    padding: 1.5rem;
                    margin-bottom: 1.5rem;
                    border-left: 4px solid #1a9e4a;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08);">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;">
                <span style="font-size: 2rem;">🏢</span>
                <h3 style="margin: 0; color: #1a1a2e; font-size: 1.3rem;">Program Analytics</h3>
            </div>
            <ul style="margin: 0; padding-left: 1.5rem; color: #666; line-height: 1.8;">
                <li>Gym power rankings by level</li>
                <li>Podium rate analysis</li>
                <li>Athlete development pipeline</li>
                <li>Fastest improving athletes</li>
                <li>Program performance trends</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.divider()
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Advanced Features Preview
    st.markdown("### 🚀 Advanced Analytics Preview")
    
    st.markdown("""
    <div style="background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
                border-radius: 12px;
                padding: 2rem;
                margin-bottom: 1rem;
                border: 2px solid #e8ecf0;">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5rem;">
            <div style="text-align: center;">
                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📈</div>
                <h4 style="margin: 0 0 0.5rem 0; color: #1a1a2e;">Score Projection</h4>
                <p style="margin: 0; color: #666; font-size: 0.9rem;">Predict next meet scores using historical trends</p>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">⚖️</div>
                <h4 style="margin: 0 0 0.5rem 0; color: #1a1a2e;">Impact Analysis</h4>
                <p style="margin: 0; color: #666; font-size: 0.9rem;">Identify which events affect AA score most</p>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🎯</div>
                <h4 style="margin: 0 0 0.5rem 0; color: #1a1a2e;">Podium Probability</h4>
                <p style="margin: 0; color: #666; font-size: 0.9rem;">Estimate chance of placing top 3 at meets</p>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🔥</div>
                <h4 style="margin: 0 0 0.5rem 0; color: #1a1a2e;">Momentum Tracking</h4>
                <p style="margin: 0; color: #666; font-size: 0.9rem;">Compare recent performance vs season average</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.divider()
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Call to action / status
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                border-radius: 12px;
                padding: 2rem;
                text-align: center;
                color: white;">
        <h3 style="margin: 0 0 1rem 0; color: white; font-size: 1.5rem;">💡 Track Every Score. See Every Trend.</h3>
        <p style="margin: 0; color: rgba(255,255,255,0.9); font-size: 1rem; line-height: 1.6;">
            Transform your historical meet results into powerful insights that coaches, gym owners, and parents will check constantly. 
            Turn data into competitive advantages.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Status indicator
    st.markdown("""
    <div style="text-align: center; padding: 1rem;">
        <p style="color: #888; font-size: 0.9rem; margin: 0;">
            <span style="display: inline-block; width: 8px; height: 8px; background: #e84393; border-radius: 50%; margin-right: 0.5rem; animation: pulse 2s infinite;"></span>
            Analytics dashboard in development
        </p>
    </div>
    <style>
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MEET RESULTS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_meets:
    # Load meets with gym data for filtering
    meets_with_gyms_df = load_meets_with_gyms()
    
    # Initialize session state for tracking filter changes
    if "meet_state_filter_prev" not in st.session_state:
        st.session_state["meet_state_filter_prev"] = "All"
    if "meet_gym_filter_prev" not in st.session_state:
        st.session_state["meet_gym_filter_prev"] = "All"
    
    # Filters on same row
    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])

    with col_f1:
        search_meet = st.text_input("🔍 Search", placeholder="-- Search meet --", 
                                     key="meet_search_input")
    
    with col_f2:
        states_available = sorted([s for s in meets_with_gyms_df["state"].dropna().unique() if s])
        state_filter = st.selectbox("📍 State", ["All"] + states_available, key="meet_state_filter")
        
        # Clear search when state changes
        if state_filter != st.session_state["meet_state_filter_prev"]:
            st.session_state["meet_state_filter_prev"] = state_filter
            # Clear search by removing the key and rerunning (can't set widget key directly)
            if "meet_search_input" in st.session_state:
                del st.session_state["meet_search_input"]
            # Reset gym filter when state changes
            st.session_state["meet_gym_filter"] = "All"
            st.session_state["meet_gym_filter_prev"] = "All"
            st.rerun()
    
    with col_f3:
        # Get gyms based on selected state
        if state_filter != "All":
            # Filter meets by state first to get gyms for that state
            state_filtered_meets = meets_with_gyms_df[meets_with_gyms_df["state"] == state_filter]
            all_gyms_in_state = set()
            for gyms_str in state_filtered_meets["gyms"].dropna():
                if gyms_str:
                    all_gyms_in_state.update([g.strip() for g in gyms_str.split(",")])
            gyms_available = sorted(list(all_gyms_in_state))
        else:
            # Get all gyms from all meets
            all_gyms_in_meets = set()
            for gyms_str in meets_with_gyms_df["gyms"].dropna():
                if gyms_str:
                    all_gyms_in_meets.update([g.strip() for g in gyms_str.split(",")])
            gyms_available = sorted(list(all_gyms_in_meets))
        
        gym_filter = st.selectbox("🏢 Gym", ["All"] + gyms_available, key="meet_gym_filter")
        
        # Clear search when gym changes
        if gym_filter != st.session_state["meet_gym_filter_prev"]:
            st.session_state["meet_gym_filter_prev"] = gym_filter
            # Clear search by removing the key and rerunning (can't set widget key directly)
            if "meet_search_input" in st.session_state:
                del st.session_state["meet_search_input"]
            st.rerun()

    # Filter meets - dropdowns work independently and show results immediately
    filtered = meets_with_gyms_df.copy()
    
    # Apply state filter first (if selected) - shows all meets for that state
    if state_filter != "All":
        filtered = filtered[filtered["state"] == state_filter]
    
    # Apply gym filter (if selected) - works with or without state filter
    # Use exact match to avoid matching gyms with similar names (e.g., "The Flip Zone" vs "Flip Zone Gymnastics Of Southwest Fl")
    if gym_filter != "All":
        # Check if the exact gym name appears in the comma-separated gyms list
        filtered = filtered[filtered["gyms"].notna() & filtered["gyms"].apply(
            lambda gyms_str: gym_filter in [g.strip() for g in str(gyms_str).split(",")] if gyms_str else False
        )]
    
    # Apply search filter as additional refinement (only if search has text)
    # Search works on top of dropdown filters
    if search_meet:
        filtered = filtered[filtered["name"].str.contains(search_meet, case=False, na=False)]
    
    # Only show meets with scores
    filtered = filtered[filtered["score_count"] > 0]

    if filtered.empty:
        st.info("No meets match your filters.")
    else:
        # Auto-select if only one meet found, otherwise show selector with count
        if len(filtered) == 1:
            selected_meet = filtered.iloc[0]
            st.info(f"**{selected_meet['name']}** — {int(selected_meet['score_count'])} score records")
        else:
            # Meet selector with count in dropdown
            meet_options = filtered.apply(
                lambda r: f"{r['name']}", axis=1
            ).tolist()
            # Add placeholder option with count
            placeholder_text = f"-- Select meet ({len(filtered)} found) --"
            meet_options_with_placeholder = [placeholder_text] + meet_options
            
            selected_idx = st.selectbox("", range(len(meet_options_with_placeholder)),
                                         format_func=lambda i: meet_options_with_placeholder[i],
                                         key="meet_selector",
                                         label_visibility="collapsed")
            
            # If placeholder is selected (index 0), don't show meet details
            if selected_idx == 0:
                selected_meet = None
            else:
                # Adjust index since we added placeholder
                selected_meet = filtered.iloc[selected_idx - 1]
        
        # Only show meet details if a meet is selected
        if selected_meet is not None:
            # Modern meet header with styled information
            location_display = ""
            if pd.notna(selected_meet.get("location")) and selected_meet.get("location"):
                location_display = f'<span style="opacity: 0.8;">· {selected_meet["location"]}</span>'
            
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        padding: 1.5rem;
                        border-radius: 12px;
                        margin-bottom: 1.5rem;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: white; margin: 0 0 1rem 0; font-size: 1.75rem;">{selected_meet['name']}</h2>
                <div style="display: flex; gap: 2rem; flex-wrap: wrap; color: rgba(255,255,255,0.95);">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 1.2rem;">📅</span>
                        <span style="font-weight: 500;">{str(selected_meet["start_date"] or "TBD")}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 1.2rem;">📍</span>
                        <span style="font-weight: 500;">{selected_meet["state"] or "—"}</span>
                        {location_display}
                    </div>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 1.2rem;">📊</span>
                        <span style="font-weight: 500;">{int(selected_meet["score_count"])} score records</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Load scores for this meet
            scores_df = load_meet_scores(int(selected_meet["id"]))

            if scores_df.empty:
                st.info("No scores found for this meet.")
            else:
                # Level filter
                levels_in_meet = sorted(scores_df["level"].dropna().unique(),
                                        key=lambda x: str(x))
                level_opts = ["All Levels"] + [level_label(l) for l in levels_in_meet]
                level_raw = ["All Levels"] + list(levels_in_meet)
                sel_level_idx = st.selectbox("Filter by level", range(len(level_opts)),
                                              format_func=lambda i: level_opts[i],
                                              key="meet_level_filter")
                if sel_level_idx > 0:
                    scores_df = scores_df[scores_df["level"] == level_raw[sel_level_idx]]

                # Medal function
                def medal(place) -> str:
                    """Return medal/placement indicator for a given place."""
                    try:
                        if place is None or (isinstance(place, float) and pd.isna(place)):
                            return ""
                        p = int(place)
                        if p == 1: return " 🥇"
                        if p == 2: return " 🥈"
                        if p == 3: return " 🥉"
                        if p == 4: return " ④"
                        if p == 5: return " ⑤"
                        if p == 6: return " ⑥"
                    except Exception:
                        pass
                    return ""

                # Build results table grouped by athlete with events as columns
                def build_meet_results_table(df: pd.DataFrame) -> pd.DataFrame:
                    rows = []
                    # Group by athlete, gym, and level (in case same athlete competes at multiple levels)
                    for (athlete, gym, level), grp in df.groupby(["athlete", "gym", "level"], dropna=False):
                        row = {
                            "Athlete": athlete,
                            "Gym": gym if pd.notna(gym) else "—",
                            "Level": level_label(level) if pd.notna(level) else "—",
                        }
                        # Get scores for each event - format as "score medal" for display
                        # Numeric part comes first so text sorting works correctly
                        for ev, col in [("AA", "All-Around"), ("VT", "Vault"), ("UB", "Bars"), ("BB", "Beam"), ("FX", "Floor")]:
                            ev_row = grp[grp["event"] == ev]
                            if not ev_row.empty and pd.notna(ev_row['score'].iloc[0]):
                                ev_score = ev_row['score'].iloc[0]
                                ev_place = ev_row['place'].iloc[0] if 'place' in ev_row.columns and pd.notna(ev_row['place'].iloc[0]) else None
                                medal_str = medal(ev_place)
                                # Format: "9.850 🥇" - numeric first ensures proper sorting
                                row[col] = f"{ev_score:.3f}{medal_str}"
                            else:
                                row[col] = None  # Use None for proper sorting
                        rows.append(row)
                    result = pd.DataFrame(rows)
                    if not result.empty:
                        # Sort by All-Around score descending by default
                        # Convert to numeric for sorting, handling None values
                        result["_sort_aa"] = result["All-Around"].apply(
                            lambda x: float(str(x).split()[0]) if x and x != "—" and pd.notna(x) else 0
                        )
                        result = result.sort_values("_sort_aa", ascending=False).drop(columns=["_sort_aa"]).reset_index(drop=True)
                        result.index += 1
                        # Replace None with "—" for display
                        for col in ["All-Around", "Vault", "Bars", "Beam", "Floor"]:
                            result[col] = result[col].fillna("—")
                    return result

                results_table = build_meet_results_table(scores_df)
                
                # Configure columns - TextColumn allows sorting and displays medals
                column_config = {
                    "Athlete": st.column_config.TextColumn("Athlete", width="medium"),
                    "Gym": st.column_config.TextColumn("Gym", width="medium"),
                    "Level": st.column_config.TextColumn("Level", width="small"),
                }
                # Event columns as TextColumn - sorting will work on numeric prefix
                for col in ["All-Around", "Vault", "Bars", "Beam", "Floor"]:
                    column_config[col] = st.column_config.TextColumn(col, width="small")
                
                st.caption("💡 Tip: Click column headers to sort by that column")
                st.dataframe(
                    results_table,
                    width='stretch',
                    height=min(600, 50 * (len(results_table) + 1)),
                    column_config=column_config
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ATHLETE PROFILE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_athlete:
    st.subheader("👤 Athlete Profile")
    
    # Initialize session state for tracking filter changes
    if "athlete_state_filter_prev" not in st.session_state:
        st.session_state["athlete_state_filter_prev"] = "All"
    if "athlete_gym_filter_prev" not in st.session_state:
        st.session_state["athlete_gym_filter_prev"] = "All"
    
    # Filters on same row
    col_a1, col_a2, col_a3 = st.columns([2, 1, 1])
    
    with col_a1:
        search_name = st.text_input("🔍 Search", placeholder="-- Search athlete name --", key="athlete_search")
    
    with col_a2:
        states_available = load_athlete_states()
        if not states_available:
            # If no states found, use meets data as fallback
            meets_with_gyms_df = load_meets_with_gyms()
            states_available = sorted([s for s in meets_with_gyms_df["state"].dropna().unique() if s])
        
        athlete_state_filter = st.selectbox("📍 State", ["All"] + states_available, key="athlete_state_filter")
        
        # Clear search when state changes
        if athlete_state_filter != st.session_state["athlete_state_filter_prev"]:
            st.session_state["athlete_state_filter_prev"] = athlete_state_filter
            # Reset gym filter when state changes
            st.session_state["athlete_gym_filter"] = "All"
            st.session_state["athlete_gym_filter_prev"] = "All"
            # Clear search by removing the key and rerunning
            if "athlete_search" in st.session_state:
                del st.session_state["athlete_search"]
            st.rerun()
    
    with col_a3:
        # Get gyms based on selected state
        gyms_available = load_athlete_gyms(athlete_state_filter if athlete_state_filter != "All" else None)
        athlete_gym_filter = st.selectbox("🏢 Gym", ["All"] + gyms_available, key="athlete_gym_filter")
        
        # Clear search when gym changes
        if athlete_gym_filter != st.session_state["athlete_gym_filter_prev"]:
            st.session_state["athlete_gym_filter_prev"] = athlete_gym_filter
            # Clear search by removing the key and rerunning
            if "athlete_search" in st.session_state:
                del st.session_state["athlete_search"]
            st.rerun()

    if not search_name or len(search_name) < 2:
        st.info("Type at least 2 characters to search for an athlete.")
    else:
        # Apply filters to search
        state_filter_val = athlete_state_filter if athlete_state_filter != "All" else None
        gym_filter_val = athlete_gym_filter if athlete_gym_filter != "All" else None
        matches = load_athlete_search(search_name, state=state_filter_val, gym=gym_filter_val)
        if not matches:
            st.warning(f"No athletes found matching '{search_name}'.")
        else:
            selected_athlete = st.selectbox("Select athlete", matches, key="athlete_select")

            if selected_athlete:
                history = load_athlete_scores(selected_athlete)

                if history.empty:
                    st.info("No score history found.")
                else:
                    # Summary stats
                    aa_scores = history[history["event"] == "AA"]["score"]
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("Meets Competed", len(history["meet"].unique()))
                    s2.metric("Best AA Score", f"{aa_scores.max():.3f}" if not aa_scores.empty else "—")
                    s3.metric("Avg AA Score", f"{aa_scores.mean():.3f}" if not aa_scores.empty else "—")
                    s4.metric("Levels Competed", ", ".join(sorted(history["level"].dropna().unique())))

                    st.divider()

                    # Score trend chart
                    if len(aa_scores) >= 2:
                        trend_df = history[history["event"] == "AA"].copy()
                        trend_df = trend_df.sort_values("start_date")
                        trend_df["meet_short"] = trend_df["meet"].str[:30]

                        fig = px.line(
                            trend_df, x="meet_short", y="score",
                            markers=True,
                            title=f"{selected_athlete} — AA Score History",
                            labels={"meet_short": "Meet", "score": "All-Around Score"},
                            color_discrete_sequence=["#e84393"],
                        )
                        fig.update_layout(**PLOT_LAYOUT, height=350,
                                          xaxis_tickangle=-30)
                        fig.update_traces(line=dict(width=2.5), marker=dict(size=8))
                        st.plotly_chart(fig, use_container_width=True)

                    # Full history table — one row per meet
                    st.markdown("#### Competition History")

                    # Medal function
                    def medal(place) -> str:
                        """Return medal/placement indicator for a given place."""
                        try:
                            if place is None or (isinstance(place, float) and pd.isna(place)):
                                return ""
                            p = int(place)
                            if p == 1: return " 🥇"
                            if p == 2: return " 🥈"
                            if p == 3: return " 🥉"
                            if p == 4: return " ④"
                            if p == 5: return " ⑤"
                            if p == 6: return " ⑥"
                        except Exception:
                            pass
                        return ""

                    def build_history_table(df: pd.DataFrame) -> pd.DataFrame:
                        rows = []
                        for (meet, start_date, location, level), grp in df.groupby(
                            ["meet", "start_date", "location", "level"], dropna=False
                        ):
                            aa_row = grp[grp["event"] == "AA"]
                            aa_place = aa_row['place'].iloc[0] if not aa_row.empty and pd.notna(aa_row['place'].iloc[0]) else None
                            aa_score = aa_row['score'].iloc[0] if not aa_row.empty and pd.notna(aa_row['score'].iloc[0]) and aa_row['score'].iloc[0] != 0 else None
                            
                            row = {
                                "Date":       str(start_date) if pd.notna(start_date) else "—",
                                "Meet":       meet,
                                "Location":   location if pd.notna(location) else "—",
                                "Level":      level_label(level),
                                "Place":      f"#{int(aa_place)}" if aa_place is not None else "—",
                                "All-Around": f"{aa_score:.3f}{medal(aa_place)}" if aa_score is not None else "—",
                            }
                            for ev, col in [("VT","Vault"),("UB","Bars"),("BB","Beam"),("FX","Floor")]:
                                ev_row = grp[grp["event"] == ev]
                                if not ev_row.empty and pd.notna(ev_row['score'].iloc[0]):
                                    ev_score = ev_row['score'].iloc[0]
                                    ev_place = ev_row['place'].iloc[0] if 'place' in ev_row.columns and pd.notna(ev_row['place'].iloc[0]) else None
                                    row[col] = f"{ev_score:.3f}{medal(ev_place)}"
                                else:
                                    row[col] = "—"
                            rows.append(row)
                        result = pd.DataFrame(rows)
                        if not result.empty:
                            result = result.sort_values("Date", ascending=True).reset_index(drop=True)
                            result.index += 1
                        return result

                    hist_table = build_history_table(history)
                    st.caption("💡 Tip: Click column headers to sort by that column")
                    st.dataframe(hist_table, width='stretch', height=400)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — RANKINGS (HIDDEN - UNDER DEVELOPMENT)
# ═══════════════════════════════════════════════════════════════════════════════
# Rankings tab temporarily hidden while under development
# with tab_rankings:
#     st.subheader("🏆 Rankings by Level")
#     st.caption("Top all-around scores across all meets in the database.")
#
#     # Get levels that have data
#     levels_with_data = query("""
#         SELECT DISTINCT level, COUNT(*) c
#         FROM scores WHERE event='AA' AND level IS NOT NULL
#         GROUP BY level ORDER BY c DESC
#     """)
#     level_choices = levels_with_data["level"].tolist()
#     level_display = [level_label(l) for l in level_choices]
#
#     col_r1, col_r2 = st.columns([1, 3])
#     with col_r1:
#         sel_rank_level_idx = st.selectbox(
#             "Level",
#             range(len(level_choices)),
#             format_func=lambda i: level_display[i],
#             key="rankings_level"
#         )
#     selected_rank_level = level_choices[sel_rank_level_idx]
#
#     with col_r2:
#         top_n = st.slider("Show top N athletes", 10, 100, 25, key="rankings_topn")
#
#     rankings_df = load_rankings(selected_rank_level)
#
#     if rankings_df.empty:
#         st.info("No data for this level.")
#     else:
#         # Best score per athlete
#         best = (
#             rankings_df.groupby(["athlete", "gym"])
#             .agg(best_score=("score", "max"), meets_competed=("meet", "nunique"),
#                  avg_score=("score", "mean"))
#             .reset_index()
#             .sort_values("best_score", ascending=False)
#             .head(top_n)
#             .reset_index(drop=True)
#         )
#         best.index += 1
#         best["avg_score"] = best["avg_score"].round(3)
#         best["best_score"] = best["best_score"].round(3)
#
#         # Bar chart
#         fig = px.bar(
#             best.head(20), x="athlete", y="best_score",
#             color="best_score",
#             color_continuous_scale=[[0, "#fce4f0"], [1, "#e84393"]],
#             title=f"Top 20 All-Around Scores — {level_label(selected_rank_level)}",
#             labels={"athlete": "Athlete", "best_score": "Best AA Score"},
#             text="best_score",
#         )
#         fig.update_traces(textposition="outside", texttemplate="%{text:.3f}")
#         fig.update_layout(**PLOT_LAYOUT, height=400, showlegend=False,
#                           coloraxis_showscale=False, xaxis_tickangle=-35)
#         st.plotly_chart(fig, width='stretch')
#
#         # Rankings table
#         st.markdown(f"#### Full Rankings — {level_label(selected_rank_level)}")
#         display = best.rename(columns={
#             "athlete": "Athlete", "gym": "Gym",
#             "best_score": "Best AA Score", "meets_competed": "Meets",
#             "avg_score": "Avg Score"
#         })
#         st.dataframe(display, width='stretch', height=500)
#
#         # Score distribution across all athletes at this level
#         st.divider()
#         st.markdown("#### Score Distribution")
#         fig2 = px.histogram(
#             rankings_df, x="score", nbins=25,
#             title=f"All AA Scores — {level_label(selected_rank_level)}",
#             labels={"score": "All-Around Score", "count": "Count"},
#             color_discrete_sequence=["#7b52ab"],
#         )
#         fig2.update_layout(**PLOT_LAYOUT, height=300, showlegend=False)
#         st.plotly_chart(fig2, width='stretch')


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"All data is based on publicly available sources · {len(meets_df)} meets · {total_athletes:,} athletes · {total_scores:,} score records · {total_gyms:,} gyms")
