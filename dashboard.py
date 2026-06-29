"""
Gush Dan Bus Line Ranking Dashboard — Streamlit
Run: streamlit run dashboard.py
"""

import os
import io
import json
import base64
from datetime import date, timedelta
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
import folium
from streamlit_folium import st_folium
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

st.set_page_config(
    page_title="דירוג קווי אוטובוס — ישראל",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Material Design 3 + full RTL theme ────────────────────────────────────────
# NOTE: keep the <style> block free of blank lines — Streamlit's markdown ends a
# raw-HTML block at the first blank line, which would dump the CSS as visible text.
_MD_CSS = (
"<style>"
"@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700;800&display=swap');"
":root{"
"--md-primary:#1a73e8;--md-primary-dark:#1557b0;--md-on-primary:#ffffff;"
"--md-surface:#ffffff;--md-surface-variant:#f1f3f4;--md-outline:#dadce0;"
"--md-on-surface:#202124;--md-on-surface-var:#5f6368;"
"--md-elev-1:0 1px 2px rgba(60,64,67,.10),0 1px 3px rgba(60,64,67,.08);"
"--md-elev-2:0 1px 2px rgba(60,64,67,.12),0 2px 6px rgba(60,64,67,.10);"
"--md-elev-3:0 4px 8px rgba(60,64,67,.12),0 1px 3px rgba(60,64,67,.10);"
"--md-radius:16px;--md-radius-sm:10px;}"
# RTL on CONTENT containers only — NOT on the app flex layout, so Streamlit's
# native sidebar position & collapse (built for LTR) keep working.
".block-container,[data-testid='stSidebarContent']{direction:rtl;}"
"html,body,.stApp,.stApp *{font-family:'Heebo',-apple-system,BlinkMacSystemFont,sans-serif !important;}"
".stApp{background:var(--md-surface-variant);}"
"h1,h2,h3,h4,h5,h6,p,label,li{text-align:right;}"
"h1{font-weight:800 !important;letter-spacing:-.5px;color:var(--md-on-surface);}"
"h2,h3{font-weight:700 !important;color:var(--md-on-surface);}"
"h4,h5,h6{font-weight:500 !important;}"
".block-container{padding-top:0.5rem !important;max-width:1400px;}"
".sticky-bar{position:sticky;top:0;z-index:999;background:var(--md-surface);border:1px solid var(--md-outline);border-radius:var(--md-radius);box-shadow:var(--md-elev-2);padding:0.9rem 1.2rem 0.7rem 1.2rem;margin-bottom:1.4rem;}"
"[data-testid='stMetric']{background:var(--md-surface);border:1px solid var(--md-outline);border-radius:var(--md-radius);box-shadow:var(--md-elev-1);padding:1rem 1.2rem;transition:box-shadow .2s ease,transform .2s ease;}"
"[data-testid='stMetric']:hover{box-shadow:var(--md-elev-3);transform:translateY(-2px);}"
"[data-testid='stMetric'] [data-testid='stMetricLabel']{color:var(--md-on-surface-var);font-weight:500 !important;justify-content:flex-end;}"
"[data-testid='stMetric'] [data-testid='stMetricValue']{color:var(--md-primary);font-weight:700 !important;direction:rtl;}"
"[data-testid='stMetric'] *{text-align:right;direction:rtl;}"
"[data-testid='stDataFrame']{direction:rtl;border-radius:var(--md-radius);overflow:hidden;box-shadow:var(--md-elev-1);border:1px solid var(--md-outline);}"
"[data-testid='stDataFrame'] table{direction:rtl;}"
"[data-testid='stDataFrame'] th,[data-testid='stDataFrame'] td{text-align:right !important;}"
"[data-testid='stDataFrame'] thead th{background:var(--md-surface-variant) !important;font-weight:700 !important;color:var(--md-on-surface) !important;}"
"[data-testid='stPlotlyChart']{background:var(--md-surface);border:1px solid var(--md-outline);border-radius:var(--md-radius);box-shadow:var(--md-elev-1);padding:0.8rem;margin-bottom:0.5rem;}"
"[data-testid='stSidebar']{background:var(--md-surface);border-right:1px solid var(--md-outline);box-shadow:var(--md-elev-2);}"
"[data-testid='stSidebar'] label{text-align:right;font-weight:500;}"
"[data-testid='stSidebar'] h1,[data-testid='stSidebar'] h2,[data-testid='stSidebar'] h3{font-size:1.05rem !important;font-weight:700 !important;}"
# keep sidebar collapse / reopen controls LTR so the arrow & hit-area stay correct
"[data-testid='stSidebarCollapseButton'],[data-testid='stSidebarCollapsedControl'],[data-testid='collapsedControl']{direction:ltr !important;}"
"[data-testid='stSidebarCollapseButton'] button,[data-testid='collapsedControl'] button{opacity:1 !important;}"
# slider widget: track LTR for correct value/tick positioning, label RTL
"[data-testid='stSlider']{direction:ltr;}"
"[data-testid='stSlider'] label,[data-testid='stSlider'] [data-testid='stWidgetLabel']{direction:rtl !important;text-align:right !important;width:100%;}"
"[data-testid='stSliderThumbValue']{color:var(--md-primary) !important;font-weight:700 !important;}"
"[data-testid='stSliderTickBar']{direction:ltr !important;}"
".stButton > button{background:var(--md-primary) !important;color:var(--md-on-primary) !important;border:none !important;border-radius:999px !important;padding:0.5rem 1.4rem !important;font-weight:500 !important;box-shadow:var(--md-elev-1);transition:box-shadow .2s ease,background .2s ease;}"
".stButton > button:hover{background:var(--md-primary-dark) !important;box-shadow:var(--md-elev-2);}"
# Material text button (subtle) for the Excel download
".stDownloadButton > button{background:transparent !important;color:var(--md-primary) !important;border:none !important;border-radius:8px !important;padding:0.25rem 0.6rem !important;font-weight:500 !important;font-size:0.85rem !important;box-shadow:none !important;}"
".stDownloadButton > button:hover{background:rgba(26,115,232,0.08) !important;box-shadow:none !important;}"
"[data-testid='stSlider'] [role='slider']{background:var(--md-primary) !important;}"
"[data-baseweb='select'] > div,[data-baseweb='input'] > div{border-radius:var(--md-radius-sm) !important;border-color:var(--md-outline) !important;}"
"[data-baseweb='select'] > div:focus-within{border-color:var(--md-primary) !important;box-shadow:0 0 0 1px var(--md-primary) !important;}"
"[data-baseweb='tag']{background:var(--md-primary) !important;border-radius:999px !important;color:var(--md-on-primary) !important;}"
"[role='radiogroup']{flex-direction:row-reverse;justify-content:flex-end;gap:.25rem;}"
"[data-testid='stAlert']{border-radius:var(--md-radius-sm);border:none;box-shadow:var(--md-elev-1);}"
"[data-testid='stAlert'] *{text-align:right;direction:rtl;}"
"hr{margin:1rem 0 !important;border-color:var(--md-outline) !important;}"
"div[data-testid='stHorizontalBlock'] label{font-size:0.82rem;color:var(--md-on-surface-var);}"
"[data-testid='stCaptionContainer']{color:var(--md-on-surface-var);text-align:right;}"
# central search box (under the title) — taller & more prominent
".st-key-searchbox [data-baseweb='select'] > div{min-height:52px !important;border-radius:12px !important;font-size:1.05rem !important;border-color:var(--md-primary) !important;box-shadow:var(--md-elev-1);}"
".st-key-searchbox [data-baseweb='select'] input::placeholder{font-size:1.05rem;}"
".st-key-searchbox{margin-bottom:0.6rem;}"
# hide Streamlit's default top toolbar (the white 'Deploy' strip)
"[data-testid='stHeader']{display:none !important;}"
"[data-testid='stToolbar']{display:none !important;}"
# collapse the empty lang/dir helper iframe container (the white strip under the header)
"[data-testid='stElementContainer']:has(iframe[title='st.iframe']){height:0 !important;min-height:0 !important;margin:0 !important;padding:0 !important;overflow:hidden !important;}"
# ===== Last Mile branded header =====
".lm-meta{color:var(--md-on-surface-var);font-size:0.8rem;font-weight:500;white-space:nowrap;}"
".lm-meta b{color:#182443;}"
".lm-header{display:flex;align-items:center;justify-content:space-between;gap:1rem;"
"background:var(--md-surface);border-bottom:3px solid #182443;border-radius:0 0 16px 16px;"
"box-shadow:var(--md-elev-2);padding:0.55rem 1.1rem;margin:0 0 1rem 0;}"
".lm-logo{height:40px;width:auto;display:block;}"
".lm-nav{display:flex;align-items:center;gap:1.1rem;flex-wrap:wrap;}"
".lm-nav a{color:#182443;font-weight:600;font-size:0.95rem;text-decoration:none;"
"padding:.25rem .2rem;border-bottom:2px solid transparent;transition:.15s;}"
".lm-nav a:hover{color:#1a73e8;border-bottom-color:#1a73e8;}"
# ===== split layout: page content in right 50%, folium map pinned left 50% =====
".block-container,[data-testid='stMainBlockContainer']{margin-left:50vw !important;max-width:48vw !important;padding-left:1.2rem !important;padding-right:1.6rem !important;}"
# hide the unused native sidebar entirely
"[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],[data-testid='collapsedControl']{display:none !important;}"
# pin the folium map element to the left half at full viewport height
"[data-testid='stElementContainer']:has(iframe[title='streamlit_folium.st_folium']){position:fixed !important;left:0 !important;top:124px !important;width:50vw !important;height:calc(100vh - 124px) !important;z-index:500;margin:0 !important;padding:0 !important;}"
"[data-testid='stElementContainer']:has(iframe[title='streamlit_folium.st_folium'])>div,iframe[title='streamlit_folium.st_folium']{width:50vw !important;height:calc(100vh - 124px) !important;}"
# header + filter bar always span the full screen width, sitting above the map
# header + filter bar are fixed to the viewport, full width, stacked at the top
".lm-header{position:fixed !important;top:0 !important;left:0 !important;width:100vw !important;z-index:601 !important;margin:0 !important;border-radius:0 !important;box-sizing:border-box;}"
".st-key-filterbar{position:fixed !important;top:60px !important;left:0 !important;width:100vw !important;z-index:600 !important;margin:0 !important;background:var(--md-surface);box-shadow:var(--md-elev-1);padding:0.35rem 1.2rem !important;box-sizing:border-box;}"
# content + map start below the two fixed bars
".block-container,[data-testid='stMainBlockContainer']{padding-top:124px !important;}"
# ===== responsive: narrower laptops (≈1366px) — give the data side more room =====
"@media (max-width:1500px){"
".block-container,[data-testid='stMainBlockContainer']{margin-left:42vw !important;max-width:56vw !important;padding-left:0.7rem !important;padding-right:1rem !important;}"
# narrower map on small laptops (header+filter bar already full-width by default)
"[data-testid='stElementContainer']:has(iframe[title='streamlit_folium.st_folium']){width:42vw !important;}"
"[data-testid='stElementContainer']:has(iframe[title='streamlit_folium.st_folium'])>div,iframe[title='streamlit_folium.st_folium']{width:42vw !important;}"
"h1{font-size:1.5rem !important;}"
"[data-testid='stPopover'] button{padding:0.22rem 0.55rem !important;font-size:0.76rem !important;}"
"[data-testid='stMetric']{padding:0.55rem 0.7rem !important;}"
"[data-testid='stMetric'] [data-testid='stMetricValue']{font-size:1.05rem !important;}"
".lm-nav{gap:0.6rem;}.lm-nav a{font-size:0.82rem;}.lm-logo{height:32px;}.lm-meta{font-size:0.72rem;}"
"}"
# compact Material filter chips (popover trigger buttons)
"[data-testid='stPopover']{display:inline-block;}"
"[data-testid='stPopover'] button{background:var(--md-surface) !important;color:var(--md-on-surface) !important;border:1px solid var(--md-outline) !important;border-radius:999px !important;padding:0.3rem 0.9rem !important;font-weight:500 !important;font-size:0.85rem !important;box-shadow:none !important;white-space:nowrap;}"
"[data-testid='stPopover'] button:hover{background:var(--md-surface-variant) !important;border-color:var(--md-primary) !important;}"
"[data-testid='stPopoverBody']{direction:rtl;text-align:right;width:340px;max-width:92vw;}"
# RTL on popover TEXT only — never on slider internals (would break the track/handle/value)
"[data-testid='stPopoverBody'] label,[data-testid='stPopoverBody'] p,[data-testid='stPopoverBody'] .stMarkdown,[data-testid='stPopoverBody'] [data-testid='stWidgetLabel']{direction:rtl;text-align:right;}"
"[data-testid='stPopoverBody'] [data-testid='stSlider']{width:100% !important;}"
# filter bar row: keep items tight & wrap nicely
".filter-row [data-testid='stHorizontalBlock']{gap:0.4rem;align-items:flex-end;}"
# restore Material icon font (the global Heebo !important would render icon ligatures as raw text)
"[data-testid='stIconMaterial'],span[data-testid='stIconMaterial'],.material-icons,.material-symbols-rounded,.material-symbols-outlined{font-family:'Material Symbols Rounded','Material Symbols Outlined','Material Icons' !important;}"
"</style>"
)
st.markdown(_MD_CSS, unsafe_allow_html=True)

# Set the real document language + direction (Streamlit owns <html>, so use JS).
components.html(
    "<script>const d=window.parent.document;"
    "d.documentElement.lang='he';d.documentElement.dir='rtl';</script>",
    height=0,
)


@st.cache_data
def logo_data_uri():
    p = os.path.join(os.path.dirname(__file__), "assets", "lastmile-logo.svg")
    try:
        with open(p, "rb") as f:
            return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return ""


@st.cache_data(ttl=600)
def data_last_updated():
    """Latest refresh time of the underlying data (newest stage parquet)."""
    import datetime as _dt
    base = os.path.dirname(__file__)
    mtimes = [os.path.getmtime(os.path.join(base, f))
              for f in ("stage1_gtfs.parquet", "stage3_ridership.parquet",
                        "stage4_stops.parquet")
              if os.path.exists(os.path.join(base, f))]
    if not mtimes:
        return "—"
    return _dt.datetime.fromtimestamp(max(mtimes)).strftime("%d/%m/%Y %H:%M")


# ── Last Mile header (logo + nav links) ───────────────────────────────────────
_NAV_LINKS = [
    ("דשבורד", "#"),
    ("מפה", "#"),
    ("אודות", "#"),
    ("צור קשר", "#"),
]
_nav_html = "".join(f"<a href='{href}'>{txt}</a>" for txt, href in _NAV_LINKS)
st.markdown(
    f"<div class='lm-header'>"
    f"<img class='lm-logo' src='{logo_data_uri()}' alt='Last Mile'/>"
    f"<span class='lm-meta'>🕒 הנתונים עודכנו לאחרונה: <b>{data_last_updated()}</b></span>"
    f"<nav class='lm-nav'>{_nav_html}</nav>"
    f"</div>",
    unsafe_allow_html=True,
)


# ── data loading ──────────────────────────────────────────────────────────────

_STAGE_FILES = ("stage1_gtfs.parquet", "stage3_ridership.parquet",
                "stage4_stops.parquet", "stage5_shapes.parquet",
                "stage6_frequency.parquet", "stage2_siri.parquet")


def _data_version():
    """Newest mtime across all stage files. Passed into load_data() so the
    cache invalidates automatically whenever the data is refreshed (weekly
    GitHub Action commit), without needing a manual reboot / cache clear."""
    base = os.path.dirname(__file__)
    mt = [os.path.getmtime(os.path.join(base, f)) for f in _STAGE_FILES
          if os.path.exists(os.path.join(base, f))]
    return max(mt) if mt else 0.0


@st.cache_data(ttl=3600)
def load_data(data_version: float = 0.0):  # data_version keys the cache
    base = os.path.dirname(__file__)

    s1 = pd.read_parquet(os.path.join(base, "stage1_gtfs.parquet"))
    s3 = pd.read_parquet(os.path.join(base, "stage3_ridership.parquet"))
    s1["makat"] = s1["makat"].astype(str)
    s3["makat"] = s3["makat"].astype(str)

    # Join on makat (the unique route id). The same line number + operator can be
    # several distinct routes in different cities, so line_number is NOT a key.
    # inner join = only routes present in both GTFS and the ridership dataset.
    df = s1.merge(s3.drop(columns=["line_number", "operator"]), on="makat", how="inner")

    # stage 4: cities / stops each route passes through (for city filter + map)
    s4_path = os.path.join(base, "stage4_stops.parquet")
    if os.path.exists(s4_path):
        s4 = pd.read_parquet(s4_path)
        s4["makat"] = s4["makat"].astype(str)
        df = df.merge(s4.drop(columns=["line_number", "operator"]),
                      on="makat", how="left")
    # stage 5: road-following route shapes (OSRM) for accurate map polylines
    s5_path = os.path.join(base, "stage5_shapes.parquet")
    if os.path.exists(s5_path):
        s5 = pd.read_parquet(s5_path)
        s5["makat"] = s5["makat"].astype(str)
        df = df.merge(s5, on="makat", how="left")
    if "shape" not in df.columns:
        df["shape"] = "[]"
    df["shape"] = df["shape"].apply(lambda v: v if isinstance(v, str) else "[]")

    # stage 6: off-peak headway + daily trips/direction → frequency columns
    s6_path = os.path.join(base, "stage6_frequency.parquet")
    if os.path.exists(s6_path):
        s6 = pd.read_parquet(s6_path)
        s6["makat"] = s6["makat"].astype(str)
        df = df.merge(s6, on="makat", how="left")
    for _c in ("daily_trips_dir", "headway_offpeak"):
        if _c not in df.columns:
            df[_c] = np.nan
    # buses/hour = 60 / headway (NaN when no service / unknown headway)
    df["freq_peak"]    = (60.0 / df["headway_min"]).replace([np.inf, -np.inf], np.nan).round(1)
    df["freq_offpeak"] = (60.0 / df["headway_offpeak"]).replace([np.inf, -np.inf], np.nan).round(1)
    df["daily_trips"]  = df["daily_trips_dir"].round(0)

    if "cities" not in df.columns:
        df["cities"] = [[] for _ in range(len(df))]
    if "stops" not in df.columns:
        df["stops"] = [[] for _ in range(len(df))]
    if "geo" not in df.columns:
        df["geo"] = "[]"
    df["geo"] = df["geo"].apply(lambda v: v if isinstance(v, str) else "[]")
    # normalise NaN (lines missing from stage4) to empty lists
    df["cities"] = df["cities"].apply(lambda v: list(v) if isinstance(v, (list, np.ndarray)) else [])
    df["stops"]  = df["stops"].apply(lambda v: list(v) if isinstance(v, (list, np.ndarray)) else [])
    df["line_number"] = df["line_number"].astype(str)

    s2_path = os.path.join(base, "stage2_siri.parquet")
    if os.path.exists(s2_path):
        s2 = pd.read_parquet(s2_path)
        df = df.merge(s2, on=["line_number","operator"], how="left")
    else:
        df["trip_execution_rate"] = np.nan

    def norm(series, lower_is_better=False):
        s = series.copy()
        fill = s.median()
        s = s.fillna(fill)
        mn, mx = s.min(), s.max()
        if mx == mn:
            return pd.Series(50.0, index=s.index)
        n = (s - mn) / (mx - mn) * 100
        return (100 - n) if lower_is_better else n

    df["score_speed"]     = norm(df["AverageSpeed"]).values
    df["score_pkm"]       = norm(df["PKM"]).values
    df["score_adherence"] = (df["trip_execution_rate"].fillna(
                              df["trip_execution_rate"].median()) * 100)

    for col in ["score_headway","score_hw_even","score_circuity","score_length"]:
        if col not in df.columns:
            df[col] = np.nan

    return df


@st.cache_data(ttl=3600)
def load_raw_gtfs():
    """Per-direction raw GTFS rows (route names, line_ref, directions)."""
    base = os.path.dirname(__file__)
    path = os.path.join(base, "stage1_gtfs_raw.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    raw = pd.read_parquet(path)
    raw["line_number"] = raw["line_number"].astype(str)
    return raw


# ── weight defaults ───────────────────────────────────────────────────────────
DEFAULT_WEIGHTS = {
    "score_headway":   20,
    "score_hw_even":   20,
    "score_adherence": 20,
    "score_speed":     15,
    "score_circuity":  10,
    "score_length":    10,
    "score_pkm":        5,
}
PARAM_LABELS = {
    "score_headway":   "Headway ממוצע בפיק",
    "score_hw_even":   "שוויון מרווחים (evenness)",
    "score_adherence": "עמידה בלוח זמנים",
    "score_speed":     "מהירות מסחרית",
    "score_circuity":  "Circuity ratio",
    "score_length":    "אורך קו (פנדלטי)",
    "score_pkm":       "נוסעים לק״מ (PKM)",
}


def compute_score(df, weights):
    numerator   = pd.Series(0.0, index=df.index)
    denominator = pd.Series(0.0, index=df.index)
    for col, w in weights.items():
        if w == 0 or col not in df.columns:
            continue
        col_vals = df[col]
        has_val  = col_vals.notna()
        numerator   += col_vals.fillna(0) * w * has_val
        denominator += w * has_val
    return numerator / denominator.replace(0, np.nan)


# ── scoring weights + min-trips → rendered in a top-bar popover (no sidebar) ───
_d = load_data(_data_version())
_missing_cols = [col for col in DEFAULT_WEIGHTS
                 if col in _d.columns and _d[col].isna().all()]


def render_weights(container):
    """Render weight sliders + min-trips inside a popover; return (weights, min_trips)."""
    weights = {}
    with container.popover("⚖️ משקולות וסינון", use_container_width=False):
        st.caption("כל קו מקבל ציון 0–100 משוקלל. הזיזו את המחוונים לשינוי חשיבות הפרמטרים.")
        if _missing_cols:
            st.warning("⚠️ אין נתונים עבור: "
                       + "، ".join(PARAM_LABELS[c] for c in _missing_cols)
                       + " — מנוטרל בחישוב.")
        for col, default in DEFAULT_WEIGHTS.items():
            data_ok = col in _d.columns and not _d[col].isna().all()
            label = PARAM_LABELS[col] if data_ok else f"{PARAM_LABELS[col]} (אין נתונים)"
            weights[col] = st.slider(label, 0, 50, default if data_ok else 0, step=5,
                                     key=col, disabled=not data_ok)
        tw = sum(weights.values())
        if tw == 0:
            st.error("⚠️ סך המשקולות = 0 — הגדילו פרמטר אחד לפחות.")
        elif tw == 100:
            st.success(f"✓ סך המשקולות: {tw}%")
        else:
            st.info(f"סך המשקולות: {tw}% (מנורמל אוטומטית ל-100%)")
        st.divider()
        min_trips = st.slider("מינימום נסיעות בשעת שיא", 0, 50, 2, step=1, key="min_trips")
    return weights, min_trips


# ── sticky filter bar (compact Material chips) ────────────────────────────────
df_all = load_data(_data_version())


def options_for(col):
    if col not in df_all.columns:
        return []
    return sorted(df_all[col].dropna().astype(str).unique().tolist())


def filter_chip(container, label, col, key, default_only=None):
    """Compact dropdown chip; each option is a checkbox whose state lives in
    session_state under '<key>__<opt>'. 'בחר הכל'/'נקה' rewrite those keys.
    default_only: optional set of options to pre-select (others off by default).
    Returns the list of currently-checked options."""
    opts = options_for(col)
    # one-time init: default everything selected, unless default_only is given
    for opt in opts:
        ck = f"{key}__{opt}"
        if ck not in st.session_state:
            st.session_state[ck] = (default_only is None) or (opt in default_only)

    chosen = [o for o in opts if st.session_state.get(f"{key}__{o}", True)]
    n = len(chosen)
    badge = "הכל" if n == len(opts) else (chosen[0] if n == 1 else str(n))

    with container.popover(f"{label}: {badge}", use_container_width=False):
        c1, c2 = st.columns(2)
        if c1.button("בחר הכל", key=f"all_{key}", use_container_width=True):
            for opt in opts:
                st.session_state[f"{key}__{opt}"] = True
            st.rerun()
        if c2.button("נקה", key=f"clr_{key}", use_container_width=True):
            for opt in opts:
                st.session_state[f"{key}__{opt}"] = False
            st.rerun()
        for opt in opts:
            # no value= → the widget is fully controlled by its session_state key
            st.checkbox(opt, key=f"{key}__{opt}")

    return [o for o in opts if st.session_state.get(f"{key}__{o}", True)]


@st.cache_data(ttl=3600)
def all_cities():
    out = set()
    for lst in df_all["cities"]:
        out |= set(lst)
    return sorted(out)



# closed-list options for the central search (cities + line numbers from the data)
@st.cache_data(ttl=3600)
def search_options():
    cities = all_cities()
    lines = sorted(df_all["line_number"].dropna().astype(str).unique(),
                   key=lambda s: (len(s), s))
    return [f"עיר · {c}" for c in cities] + [f"קו · {ln}" for ln in lines]


# Filter bar (full-width, fixed at top): compact chips.
# (The central search lives lower, under the page title — its value is read from
#  session_state below so filtering can run before that widget is rendered.)
with st.container(key="filterbar"):
    cols = st.columns([1.4, 1.0, 1.1, 1.3, 1.1, 1.3])
    weights, min_trips = render_weights(cols[0])
    sel_ops      = filter_chip(cols[1], "מפעיל",        "operator",     "op")
    sel_district = filter_chip(cols[2], "מחוז",         "district",     "district")
    sel_service  = filter_chip(cols[3], "סוג קו שירות", "service_type", "service")
    sel_partic   = filter_chip(cols[4], "ייחודיות",     "particular",   "partic")
    sel_bustype  = filter_chip(cols[5], "סוג אוטובוס",  "bus_type",     "bustype")


# ── apply filters ─────────────────────────────────────────────────────────────
# note: date filter is UI-only (data is a fixed weekly snapshot)
df_view = df_all.copy()
for col, sel in [("operator", sel_ops), ("district", sel_district),
                 ("service_type", sel_service), ("particular", sel_partic),
                 ("bus_type", sel_bustype)]:
    if col not in df_view.columns:
        continue
    # "all selected" → skip (keep everything, incl. NaN rows); otherwise filter
    if len(sel) < len(options_for(col)):
        df_view = df_view[df_view[col].astype(str).isin(sel)]

# central search — keep routes matching any selected line number OR city.
# value comes from session_state (the widget itself is rendered under the title).
search_sel = st.session_state.get("main_search", [])
_search_cities, _search_lines = set(), set()
for _s in search_sel:
    _kind, _, _val = _s.partition(" · ")
    (_search_cities if _kind == "עיר" else _search_lines).add(_val)
if _search_cities or _search_lines:
    def _match(row):
        if _search_lines and str(row["line_number"]) in _search_lines:
            return True
        return bool(_search_cities & set(row["cities"]))
    df_view = df_view[df_view.apply(_match, axis=1)]

df_view = df_view[df_view["peak_trips"] >= min_trips]

df_view["ציון סופי"] = compute_score(df_view, weights).round(2)
df_view = df_view.sort_values("ציון סופי", ascending=False).reset_index(drop=True)
df_view.index = df_view.index + 1


# ── main content ──────────────────────────────────────────────────────────────
st.title("🚌 דירוג קווי אוטובוס — כל הארץ")
st.markdown(f"**{len(df_view)} קווים** | נתוני GTFS + SIRI + נסועה 2026")

# central search — under the title, full table width (rendered before the empty
# check so it stays editable even when a search returns no results)
with st.container(key="searchbox"):
    st.multiselect(
        "חיפוש", options=search_options(), key="main_search",
        label_visibility="collapsed",
        placeholder="🔍 חיפוש עיר / יישוב / מספר קו…",
    )

if df_view.empty:
    st.warning("🔍 אין קווים התואמים את הסינון הנוכחי. הרחיבו את הפילטרים או לחצו «בחר הכל».")
    st.stop()

# Layout: all page content lives in the right 50% (CSS pushes .block-container
# right); the folium map is CSS-pinned to the left 50% at full viewport height.

# ── ranking table ─────────────────────────────────────────────────────────────
# Kavnav-style colour per operator (the route number cell is coloured accordingly)
OP_COLORS = {
    "דן":            "#0aa0a8",   # teal
    "אגד":           "#178a3a",   # green
    "אגד תעבורה":    "#178a3a",   # green
    "מטרופולין":     "#5a3e9e",   # purple
    "אלקטרה אפיקים": "#c2185b",   # magenta
    "קווים":         "#e07b0a",   # orange
    "סופרבוס":       "#1f3a93",   # navy
    "תנופה":         "#00838f",   # dark cyan
    "אקסטרה":        "#d84315",   # deep orange
    "אקסטרה ירושלים": "#bf360c",  # deep orange (darker)
    "נתיב אקספרס":   "#2e7d32",   # green
    "דן בדרום":      "#0277bd",   # blue
    "דן באר שבע":    "#00695c",   # teal-green
    "ש.א.מ":         "#6a1b9a",   # purple
    "גלים":          "#0097a7",   # cyan
    "בית שמש אקספרס": "#ad1457",  # pink
    "נסיעות ותיירות": "#5d4037",  # brown
    "גי.בי.טורס":    "#827717",   # olive
    "מועצה אזורית גולן": "#1565c0", # blue
    "מועצה אזורית אילות": "#00838f", # cyan
    "כפיר":          "#4527a0",   # deep purple
    "כבל אקספרס":    "#283593",   # indigo
}
DEFAULT_OP_COLOR = "#455a64"


def style_line_badge(row):
    """Colour the 'קו' cell like a Kavnav badge, based on the row's operator."""
    styles = [""] * len(row)
    color = OP_COLORS.get(row.get("מפעיל"), DEFAULT_OP_COLOR)
    cols = list(row.index)
    if "קו" in cols:
        styles[cols.index("קו")] = (
            f"background-color:{color};color:#ffffff;font-weight:800;"
            "text-align:center;"
        )
    return styles


# ── KPI summary cards (above the ranking table) ───────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("ממוצע ציון", f"{df_view['ציון סופי'].mean():.2f}")
k2.metric("הטוב ביותר",
          f"{df_view.iloc[0]['line_number']} ({df_view.iloc[0]['operator']})")
k3.metric("Headway ממוצע", f"{df_view['headway_min'].mean():.2f} דק'")
k4.metric("מהירות ממוצעת", f"{df_view['AverageSpeed'].mean():.2f} קמ״ש")

_tt1, _tt2 = st.columns([3, 1])
_tt1.subheader("טבלת דירוג")
fullscreen = _tt2.toggle("🔳 מסך מלא", key="fullscreen",
                         help="הסתרת המפה והרחבת הטבלה לרוחב וגובה מלאים")
if fullscreen:
    st.markdown(
        "<style>"
        # hide the pinned map and let the content fill the whole width
        "[data-testid='stElementContainer']:has(iframe[title='streamlit_folium.st_folium'])"
        "{display:none !important;}"
        ".block-container,[data-testid='stMainBlockContainer']"
        "{margin-left:0 !important;max-width:100% !important;}"
        "</style>",
        unsafe_allow_html=True,
    )
display_cols = {
    "line_number":         "קו",
    "makat":               "מק״ט",
    "operator":            "מפעיל",
    "cluster":             "אשכול",
    "headway_min":         "Headway (דק')",
    "freq_peak":           "תדירות שיא",
    "freq_offpeak":        "תדירות שפל",
    "daily_trips":         "תדירות יומית",
    "AverageSpeed":        "מהירות (קמ״ש)",
    "length_km":           "אורך (ק״מ)",
    "circuity":            "Circuity",
    "PKM":                 "נוסעים לק״מ",
    "avg_pass_ride":       "נוסעים לנסיעה",
    "trip_execution_rate": "% ביצוע",
    "ציון סופי":           "ציון",
}
ordered = [c for c in display_cols if c in df_view.columns]
# drop columns that have no data at all (e.g. % ביצוע before stage 2 runs)
ordered = [c for c in ordered if not df_view[c].isna().all()]
show_df = df_view[ordered].rename(columns=display_cols)
show_df = show_df.round(2)
# dedicated first column for the selection checkbox (keeps the קו badge clean)
show_df.insert(0, " ", "")
# hidden helper columns for AgGrid: per-operator colour + positional index
show_df["_color"] = [OP_COLORS.get(o, DEFAULT_OP_COLOR) for o in df_view["operator"]]
show_df["_idx"] = list(range(len(df_view)))


def score_breakdown(row, weights):
    """List of (label, sub_score, weight%, contribution) for a route's score."""
    items = []
    for col, w in weights.items():
        v = row.get(col)
        if w <= 0 or v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        items.append((PARAM_LABELS[col], float(v), int(w)))
    tw = sum(w for *_, w in items)
    if tw == 0:
        return [], 0.0
    out = [(lbl, v, w, v * w / tw) for lbl, v, w in items]
    out.sort(key=lambda x: -x[3])
    return out, sum(c for *_, c in out)


def score_tip(row, weights):
    rows, final = score_breakdown(row, weights)
    if not rows:
        return "אין מספיק נתונים לחישוב הציון"
    lines = [f"• {lbl}: {v:.0f} × {w}% → {c:.1f}" for lbl, v, w, c in rows]
    return ("איך חושב הציון (0–100):\n" + "\n".join(lines)
            + f"\n──────────\nציון סופי: {final:.1f}")


# hover tooltip on the score cell — explains the weighted breakdown per route
show_df["_scoretip"] = [score_tip(df_view.iloc[i], weights) for i in range(len(df_view))]

# ── export to Excel (RTL sheet) ───────────────────────────────────────────────
def _to_excel(df):
    out = df.drop(columns=[" ", "_color", "_idx", "_scoretip"], errors="ignore").copy()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        out.to_excel(xl, index=False, sheet_name="דירוג קווים")
        ws = xl.sheets["דירוג קווים"]
        ws.sheet_view.rightToLeft = True
        for col in ws.columns:
            width = max(len(str(c.value)) for c in col) + 2
            ws.column_dimensions[col[0].column_letter].width = min(width, 28)
    return buf.getvalue()

st.caption("👆 סמנו שורה (או כמה שורות) כדי לראות נתונים ולצייר את הקווים על המפה")

# ── AgGrid ranking table (true RTL) ───────────────────────────────────────────
_badge_js = JsCode(
    "function(p){var c=(p.data&&p.data._color)||'#455a64';"
    "return {backgroundColor:c,color:'#fff',fontWeight:'800',borderRadius:'8px',"
    "textAlign:'center',display:'flex',alignItems:'center',justifyContent:'center',"
    "margin:'5px 4px',lineHeight:'1'};}"
)
_score_js = JsCode(
    "function(p){var v=p.value;if(v==null)return{};"
    "var t=Math.max(0,Math.min(100,v))/100,r,g,b,k;"
    "if(t<0.5){k=t/0.5;r=215+(255-215)*k;g=48+(235-48)*k;b=39+(110-39)*k;}"
    "else{k=(t-0.5)/0.5;r=255+(26-255)*k;g=235+(152-235)*k;b=110+(80-110)*k;}"
    "return{backgroundColor:'rgb('+(r|0)+','+(g|0)+','+(b|0)+')',color:'#000',fontWeight:'700'};}"
)
# natural column widths + horizontal scroll (no truncation). The key columns
# (rank, line, makat, cluster, score) are pinned so they're always fully visible.
_tip = JsCode("function(p){return p.value;}")
gb = GridOptionsBuilder.from_dataframe(show_df)
# sortable + filterable. Headers are shown on a single line and each column is
# min-sized to fit its full header text (st_aggrid 1.0.5 + RTL can't wrap header
# text reliably — it collapses the label — so we never risk a cut-off word).
# minWidth (not fixed width) lets columns stretch to fill the grid (no white gap)
# and fall back to a horizontal scroll on narrow screens.
gb.configure_default_column(resizable=True, sortable=True, filter="agTextColumnFilter",
                            floatingFilter=False, minWidth=74,
                            cellStyle={"textAlign": "right"}, tooltipValueGetter=_tip)
gb.configure_selection("multiple", use_checkbox=True, header_checkbox=True)
gb.configure_column("_color", hide=True)
gb.configure_column("_idx", hide=True)
gb.configure_column("_scoretip", hide=True)
# narrow fixed columns that should NOT stretch (suppressSizeToFit keeps them small)
gb.configure_column(" ", width=40, minWidth=40, maxWidth=40, pinned="right",
                    checkboxSelection=True, headerCheckboxSelection=True,
                    sortable=False, filter=False, suppressSizeToFit=True)
gb.configure_column("קו", cellStyle=_badge_js, width=56, minWidth=52, maxWidth=64,
                    pinned="right", suppressSizeToFit=True)
gb.configure_column("מק״ט", width=80, minWidth=74, pinned="right",
                    filter="agNumberColumnFilter", suppressSizeToFit=True)
gb.configure_column("אשכול", width=132, minWidth=120, pinned="right",
                    suppressSizeToFit=True)
# pinned left (always visible): score — whole number, tooltip explains it
gb.configure_column(
    "ציון", cellStyle=_score_js, width=68, minWidth=68, maxWidth=80, pinned="left",
    filter="agNumberColumnFilter", sort="desc", suppressSizeToFit=True,
    valueFormatter=JsCode("function(p){return p.value==null?'':Math.round(p.value);}"),
    tooltipValueGetter=JsCode("function(p){return p.data._scoretip;}"),
)
gb.configure_column("מפעיל", minWidth=100)
# numeric columns: number filter + per-column minWidth that fits the FULL
# single-line header (measured width + padding/sort-icon overhead) so no word
# is ever cut off. On wide screens sizeColumnsToFit stretches them further.
_num_minw = {
    "Headway (דק')": 120, "מהירות (קמ״ש)": 118, "נוסעים לנסיעה": 112,
    "תדירות יומית": 104, "נוסעים לק״מ": 102, "תדירות שפל": 102,
    "תדירות שיא": 98, "אורך (ק״מ)": 94, "Circuity": 80,
}
for _nc, _mw in _num_minw.items():
    if _nc in show_df.columns:
        gb.configure_column(_nc, filter="agNumberColumnFilter", minWidth=_mw)
# native tooltips + fill the width on load and on any resize (no leftover white gap)
gb.configure_grid_options(
    enableRtl=True, rowHeight=34,
    enableBrowserTooltips=False, tooltipShowDelay=250,
    onFirstDataRendered=JsCode("function(p){p.api.sizeColumnsToFit();}"),
    onGridSizeChanged=JsCode("function(p){p.api.sizeColumnsToFit();}"),
)
grid = AgGrid(
    show_df, gridOptions=gb.build(),
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    allow_unsafe_jscode=True, height=(820 if fullscreen else 600), theme="alpine",
    fit_columns_on_grid_load=True, key="ranking_grid",
    custom_css={
        ".ag-tooltip": {
            "white-space": "pre-line", "direction": "rtl", "text-align": "right",
            "font-size": "12px", "line-height": "1.55", "max-width": "340px",
            "background": "#202124", "color": "#fff", "border-radius": "8px",
            "padding": "8px 11px", "box-shadow": "0 2px 8px rgba(0,0,0,.4)",
        },
        # compact single-line header font (columns are sized to fit each label)
        ".ag-header-cell-text": {"font-size": "11.5px", "white-space": "nowrap"},
        # trim header padding so the full label fits without huge columns
        ".ag-header-cell": {"padding-left": "5px !important",
                            "padding-right": "5px !important"},
    },
)

# export button — below the table, aligned to its left edge (RTL → leftmost column)
_sp, _dl = st.columns([4, 1])
_dl.download_button(
    "⬇️ אקסל", data=_to_excel(show_df),
    file_name="דירוג_קווים.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="ייצוא טבלת הדירוג לקובץ Excel",
)


# Resolve selected rows (via the hidden _idx column) → drives detail + map
_sel = grid.get("selected_rows")
_idxs = []
if isinstance(_sel, pd.DataFrame):
    if "_idx" in _sel.columns:
        _idxs = [int(x) for x in _sel["_idx"].tolist()]
elif isinstance(_sel, list):
    _idxs = [int(r["_idx"]) for r in _sel if isinstance(r, dict) and r.get("_idx") is not None]
sel_indices = sorted(_idxs) if _idxs else [0]
sel_idx = sel_indices[0]
sel_row = df_view.iloc[sel_idx]
sel_rows = df_view.iloc[sel_indices]


# ── helpers for the detail panel ──────────────────────────────────────────────
def _fmt(v, nd=2, suffix=""):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" or str(v) == "nan":
        return "—"
    if isinstance(v, (int, float, np.floating, np.integer)) and not isinstance(v, bool):
        return f"{v:,.{nd}f}{suffix}"
    return f"{v}{suffix}"


def kv_table(rows):
    """rows: list of (label, value). Renders a compact RTL key-value table."""
    d = pd.DataFrame(rows, columns=["שדה", "ערך"])
    st.dataframe(
        d.style.set_properties(**{"text-align": "right", "direction": "rtl"}),
        use_container_width=True, hide_index=True,
    )


raw_gtfs = load_raw_gtfs()

st.divider()

# ── selected-line detail panel (all sources) ──────────────────────────────────
_badge_color = OP_COLORS.get(sel_row["operator"], DEFAULT_OP_COLOR)
st.markdown(
    f"<div style='direction:rtl;display:flex;align-items:center;gap:12px;margin:.2rem 0;'>"
    f"<span style='background:{_badge_color};color:#fff;font-weight:800;font-size:1.3rem;"
    f"padding:.35rem .7rem;border-radius:12px;min-width:2.4rem;text-align:center;"
    f"box-shadow:var(--md-elev-1);'>{sel_row['line_number']}</span>"
    f"<span style='font-size:1.4rem;font-weight:700;'>📋 כל הנתונים — {sel_row['operator']}</span>"
    f"</div>",
    unsafe_allow_html=True,
)
rank = sel_idx + 1
st.markdown(
    f"**דירוג #{rank} מתוך {len(df_view)}**  ·  ציון כולל: "
    f"**{_fmt(sel_row.get('ציון סופי'))}**"
)

# 1) parameter score breakdown chart
param_scores = {PARAM_LABELS[col]: sel_row.get(col, np.nan) for col in DEFAULT_WEIGHTS}
label_to_col = {v: k for k, v in PARAM_LABELS.items()}
param_df = (pd.DataFrame(list(param_scores.items()), columns=["פרמטר", "ציון"])
              .dropna(subset=["ציון"]))
if not param_df.empty:
    param_df["ציון"] = param_df["ציון"].clip(0, 100)
    fig_bar = px.bar(
        param_df, x="פרמטר", y="ציון", color="ציון",
        color_continuous_scale="RdYlGn", range_color=[0, 100],
        title="פירוק הציון לפרמטרים", text="ציון",
    )
    fig_bar.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    fig_bar.update_layout(yaxis_range=[0, 110], xaxis_tickangle=-30,
                          coloraxis_showscale=False, height=360,
                          font=dict(family="Heebo, sans-serif", size=13),
                          xaxis=dict(autorange="reversed"),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(t=50, b=40, l=20, r=20))
    st.plotly_chart(fig_bar, use_container_width=True)

# 1b) score reasoning — weighted breakdown table (why this line got its score)
_bk_rows, _bk_final = score_breakdown(sel_row, weights)
if _bk_rows:
    with st.expander("❓ איך התקבל הציון? (פירוק משוקלל)", expanded=False):
        st.caption("הציון הוא ממוצע משוקלל של ציוני-המשנה (0–100). "
                   "התרומה = ציון-משנה × משקל ÷ סך המשקלים הזמינים.")
        bk_df = pd.DataFrame(
            [(lbl, round(v, 1), f"{w}%", round(c, 1)) for lbl, v, w, c in _bk_rows],
            columns=["פרמטר", "ציון משנה", "משקל", "תרומה לציון"],
        )
        # blue gradient on the contribution column WITHOUT matplotlib
        # (Styler.background_gradient needs matplotlib, absent on Streamlit Cloud)
        _contrib = bk_df["תרומה לציון"].astype(float)
        _cmax = _contrib.max() or 1.0

        def _blue(col):
            out = []
            for v in col:
                f = max(0.0, min(1.0, float(v) / _cmax))
                r = int(232 - f * (232 - 8))
                g = int(244 - f * (244 - 81))
                b = int(255 - f * (255 - 156))
                txt = "#fff" if f > 0.55 else "#202124"
                out.append(f"background-color:rgb({r},{g},{b});color:{txt}")
            return out

        st.dataframe(
            bk_df.style.set_properties(**{"text-align": "right", "direction": "rtl"})
                 .apply(_blue, subset=["תרומה לציון"]),
            use_container_width=True, hide_index=True,
        )
        st.markdown(f"**ציון סופי = {_bk_final:.1f}**  (סכום התרומות)")

# 2) all-source data grouped into tabs
tab_gtfs, tab_ride, tab_dirs, tab_score = st.tabs(
    ["🚍 GTFS (משרד התחבורה)", "👥 נסועה (data.gov.il)", "🧭 כיוונים ומסלול", "🎯 ציונים"]
)

with tab_gtfs:
    kv_table([
        ("Headway ממוצע בפיק (דק')", _fmt(sel_row.get("headway_min"))),
        ("שונות מרווחים CV",          _fmt(sel_row.get("headway_cv"))),
        ("אורך מסלול (ק״מ)",          _fmt(sel_row.get("length_km"))),
        ("Circuity (עקלקלות)",        _fmt(sel_row.get("circuity"))),
        ("נסיעות בשעת שיא",           _fmt(sel_row.get("peak_trips"), nd=0)),
    ])

with tab_ride:
    kv_table([
        ("מק״ט",               _fmt(sel_row.get("makat"))),
        ("מחוז",               _fmt(sel_row.get("district"))),
        ("אשכול",              _fmt(sel_row.get("cluster"))),
        ("סוג קו שירות",       _fmt(sel_row.get("service_type"))),
        ("ייחודיות",           _fmt(sel_row.get("particular"))),
        ("סוג אוטובוס",        _fmt(sel_row.get("bus_type"))),
        ("גודל אוטובוס",       _fmt(sel_row.get("bus_size"))),
        ("עיר מוצא",           _fmt(sel_row.get("origin_city"))),
        ("עיר יעד",            _fmt(sel_row.get("dest_city"))),
        ("פעיל מאז",           _fmt(sel_row.get("operation_since"))),
        ("מס׳ תחנות במסלול",   _fmt(sel_row.get("stations"), nd=0)),
        ("משך נסיעה ממוצע (דק')", _fmt(sel_row.get("trip_duration"))),
        ("מהירות מסחרית (קמ״ש)", _fmt(sel_row.get("AverageSpeed"))),
        ("אורך קו רשמי (ק״מ)", _fmt(sel_row.get("RouteLength"))),
        ("נוסעים לק״מ (PKM)",  _fmt(sel_row.get("PKM"))),
        ("נוסעים ביום",        _fmt(sel_row.get("daily_pass"), nd=0)),
        ("נוסעים בשבוע",       _fmt(sel_row.get("WeeklyPassengers"), nd=0)),
        ("נסועה שבועית (ק״מ)", _fmt(sel_row.get("WeeklyKM"), nd=0)),
        ("נסיעות בשבוע",       _fmt(sel_row.get("weekly_rides"), nd=0)),
    ])

with tab_dirs:
    route_cities = list(sel_row.get("cities") or [])
    if route_cities:
        st.markdown("**ערים שהקו עובר בהן:**")
        st.markdown(
            " ".join(
                f"<span style='background:var(--md-surface-variant);border:1px solid var(--md-outline);"
                f"border-radius:999px;padding:2px 10px;margin:2px;display:inline-block;font-size:.8rem;'>{c}</span>"
                for c in route_cities
            ),
            unsafe_allow_html=True,
        )
        st.markdown("")
    if not raw_gtfs.empty:
        dirs = raw_gtfs[(raw_gtfs["line_number"] == str(sel_row["line_number"])) &
                        (raw_gtfs["operator"] == sel_row["operator"])]
        if not dirs.empty:
            show_cols = {
                "direction": "כיוון", "route_name": "שם המסלול",
                "line_ref": "line_ref", "route_id": "route_id",
                "headway_min": "Headway", "length_km": "אורך", "peak_trips": "נסיעות פיק",
            }
            d = dirs[[c for c in show_cols if c in dirs.columns]].rename(columns=show_cols)
            st.dataframe(
                d.round(2).style.set_properties(**{"text-align": "right", "direction": "rtl"}),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("אין נתוני מסלול גולמיים לקו זה.")
    else:
        st.info("קובץ ה-GTFS הגולמי לא נמצא.")

with tab_score:
    siri_txt = (_fmt(sel_row.get("trip_execution_rate"))
                if pd.notna(sel_row.get("trip_execution_rate"))
                else "— (טרם נאספו נתוני SIRI)")
    kv_table([
        ("ציון Headway",        _fmt(sel_row.get("score_headway"))),
        ("ציון שוויון מרווחים", _fmt(sel_row.get("score_hw_even"))),
        ("ציון עמידה בלו״ז",    _fmt(sel_row.get("score_adherence"))),
        ("ציון מהירות",         _fmt(sel_row.get("score_speed"))),
        ("ציון Circuity",       _fmt(sel_row.get("score_circuity"))),
        ("ציון אורך",           _fmt(sel_row.get("score_length"))),
        ("ציון PKM",            _fmt(sel_row.get("score_pkm"))),
        ("— ציון כולל —",        _fmt(sel_row.get("ציון סופי"))),
        ("SIRI: שיעור ביצוע נסיעות", siri_txt),
    ])

st.divider()

# ── map view (CSS-pinned to the left 50%, full viewport height) ───────────────
st.subheader("🗺️ מפה")


def parse_geo(s):
    try:
        return json.loads(s) if isinstance(s, str) else []
    except Exception:
        return []


# distinct colour palette so several selected routes are easy to tell apart
ROUTE_PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
                 "#008080", "#9a6324", "#800000", "#000075", "#e07b0a",
                 "#46c2c2", "#bc3f8e"]

mopt1, mopt2, mopt3 = st.columns(3)
show_all = mopt1.checkbox("כל המסוננים", value=False,
                          help="ציור קל של מסלולי כל הקווים שעברו את הסינון (עד 80)")
show_stops = mopt2.checkbox("תחנות", value=(len(sel_indices) == 1))
use_op_colors = mopt3.checkbox("צבע מפעיל", value=False,
                               help="כבוי = צבע ייחודי לכל קו; דלוק = צבע המפעיל (Kavnav)")

fmap = folium.Map(location=[32.08, 34.80], zoom_start=11, tiles="CartoDB positron",
                  control_scale=True)

# Neutralise Leaflet's default div-icon box so route-number badges keep their
# coloured background and never wrap to multiple lines.
fmap.get_root().header.add_child(folium.Element(
    "<style>"
    ".routebadge{background:transparent !important;border:none !important;"
    "width:auto !important;height:auto !important;overflow:visible !important;}"
    ".routebadge .rb{display:inline-block;white-space:nowrap;color:#fff;"
    "font-weight:800;font-size:12px;line-height:1.2;padding:3px 8px;"
    "border-radius:9px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.55);"
    "transform:translate(-50%,-50%);}"
    "</style>"
))

# light overlay of all filtered routes
if show_all:
    for _, r in df_view.head(80).iterrows():
        g = parse_geo(r.get("geo"))
        if len(g) >= 2:
            folium.PolyLine([[p[0], p[1]] for p in g],
                            color=OP_COLORS.get(r["operator"], DEFAULT_OP_COLOR),
                            weight=2, opacity=0.2).add_to(fmap)


def number_badge(latlon, num, color):
    folium.Marker(
        latlon,
        icon=folium.DivIcon(
            class_name="routebadge",
            icon_size=(0, 0), icon_anchor=(0, 0),
            html=f"<span class='rb' style='background:{color};'>{num}</span>",
        ),
    ).add_to(fmap)


def route_tooltip(r, color):
    """Rich HTML tooltip shown when hovering a route line."""
    def row(lbl, val):
        return (f"<tr><td style='color:#5f6368;padding:1px 6px;text-align:right'>{lbl}</td>"
                f"<td style='font-weight:600;padding:1px 6px;text-align:left'>{val}</td></tr>")
    rt = ""
    o, d = r.get("origin_city"), r.get("dest_city")
    if pd.notna(o) and pd.notna(d):
        rt = f"<div style='color:#5f6368;font-size:11px;margin-bottom:4px'>{o} ⟵ {d}</div>"
    return folium.Tooltip(
        f"<div style='direction:rtl;font-family:Heebo,sans-serif;min-width:170px'>"
        f"<div style='display:flex;align-items:center;gap:6px;margin-bottom:3px'>"
        f"<span style='background:{color};color:#fff;font-weight:800;padding:1px 8px;"
        f"border-radius:7px'>{r['line_number']}</span>"
        f"<span style='font-weight:700'>{r['operator']}</span></div>"
        f"{rt}"
        f"<table style='border-collapse:collapse;font-size:12px'>"
        + row("ציון", _fmt(r.get('ציון סופי')))
        + row("מק״ט", _fmt(r.get('makat')))
        + row("Headway (דק')", _fmt(r.get('headway_min')))
        + row("מהירות (קמ״ש)", _fmt(r.get('AverageSpeed')))
        + row("אורך (ק״מ)", _fmt(r.get('length_km')))
        + row("נוסעים/ק״מ", _fmt(r.get('PKM')))
        + row("סוג שירות", _fmt(r.get('service_type')))
        + "</table></div>",
        sticky=True,
    )


all_pts = []
drawn = 0
for order, (_, r) in enumerate(sel_rows.iterrows()):
    geo = parse_geo(r.get("geo"))
    if len(geo) < 2:
        continue
    color = (OP_COLORS.get(r["operator"], DEFAULT_OP_COLOR) if use_op_colors
             else ROUTE_PALETTE[order % len(ROUTE_PALETTE)])
    # road-following shape (OSRM); fall back to straight stop line if missing
    road = parse_geo(r.get("shape"))
    line_pts = [[p[0], p[1]] for p in road] if len(road) >= 2 \
        else [[p[0], p[1]] for p in geo]
    all_pts += line_pts
    folium.PolyLine(line_pts, color=color, weight=5, opacity=0.9,
                    tooltip=route_tooltip(r, color)).add_to(fmap)
    if show_stops:
        for i, p in enumerate(geo):
            edge = i == 0 or i == len(geo) - 1
            folium.CircleMarker(
                [p[0], p[1]], radius=6 if edge else 4,
                color=color, fill=True,
                fill_color=color if edge else "#ffffff",
                fill_opacity=1, weight=2, tooltip=f"{p[2]} · {p[3]}",
            ).add_to(fmap)
    # route-number badges: endpoints at the terminal stops, one at the path midpoint
    number_badge([geo[0][0], geo[0][1]],   r["line_number"], color)
    number_badge([geo[-1][0], geo[-1][1]], r["line_number"], color)
    number_badge(line_pts[len(line_pts) // 2], r["line_number"], color)
    drawn += 1

if all_pts:
    lat_s = [p[0] for p in all_pts]; lon_s = [p[1] for p in all_pts]
    fmap.fit_bounds([[min(lat_s), min(lon_s)], [max(lat_s), max(lon_s)]])

if drawn:
    nums = "، ".join(str(r["line_number"]) for _, r in sel_rows.iterrows())
    st.caption(f"מציג **{drawn}** קווים: {nums} · סמנו עוד שורות בטבלה")
else:
    st.caption("אין נתוני מסלול לקווים שנבחרו.")
# Render the map only when NOT in full-screen mode — a Leaflet map built inside a
# hidden (display:none) container can't compute size/bounds and ends up zoomed out.
# Keying the widget on the current selection forces a fresh fit on every change, so
# the map always re-focuses on the selected route (incl. when leaving full screen).
if not fullscreen:
    _map_key = "route_map_" + "_".join(str(i) for i in sel_indices)
    st_folium(fmap, use_container_width=True, height=1400, returned_objects=[],
              key=_map_key)

st.caption("מקורות: GTFS (משרד התחבורה) · Open Bus Stride API · data.gov.il נסועה Q1-2026")
