"""
Stage 1: Fetch Gush Dan bus routes via open-bus-stride API.
Compute per-route: headway (peak), length_km, circuity.
Saves stage1_gtfs.parquet for downstream stages.
"""

import math, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import pandas as pd
import numpy as np
import requests

API = "https://open-bus-stride-api.hasadna.org.il"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bus-dashboard/1.0"})

# All bus operators nationwide (operator_ref → name)
GUSH_DAN_OPERATORS = {
    3:  "אגד",            4:  "אגד תעבורה",   5:  "דן",
    6:  "ש.א.מ",          7:  "נסיעות ותיירות", 8: "גי.בי.טורס",
    10: "מועצה אזורית אילות", 14: "נתיב אקספרס", 15: "מטרופולין",
    16: "סופרבוס",        18: "קווים",         20: "כרמלית",
    21: "כפיר",           23: "גלים",          24: "מועצה אזורית גולן",
    25: "אלקטרה אפיקים",  31: "דן בדרום",      32: "דן באר שבע",
    33: "כבל אקספרס",     34: "תנופה",         35: "בית שמש אקספרס",
    37: "אקסטרה",         38: "אקסטרה ירושלים",
    42: "ירושלים-רמאללה איחוד", 44: "ירושלים-אבו-תור-ענאתא איחוד",
    45: "ירושלים-אלווסט איחוד", 47: "ירושלים-הר הזיתים",
    49: "ירושלים - עיסאוויה מחנה שעפאט איחוד", 50: "ירושלים-דרום איחוד",
    51: "ירושלים-צור באהר איחוד",
}

# Reference weekday = Monday of the current week (so re-runs always pull a
# fresh, representative service day instead of a frozen 2026 date).
from datetime import date as _date

try:
    from zoneinfo import ZoneInfo
    _IL_TZ = ZoneInfo("Asia/Jerusalem")          # handles IST/IDT (UTC+2/+3)
except Exception:                                # pragma: no cover
    _IL_TZ = timezone(timedelta(hours=3))        # fallback: assume summer time


def _recent_monday():
    # The open-bus-stride API ingests actual ride instances with a ~3-day lag,
    # so "today" / this week's Monday can return zero rides. Step back a full
    # week first, then snap to that week's Monday → always a representative
    # weekday that is safely behind the ingestion frontier (7–13 days old).
    t = _date.today() - timedelta(days=7)
    return t - timedelta(days=t.weekday())       # weekday(): Mon=0 … Sun=6


def _utc_window(d, h_from, h_to):
    """Local (IST/IDT) hour range on date d → (utc_from_iso, utc_to_iso)."""
    a = datetime(d.year, d.month, d.day, h_from, tzinfo=_IL_TZ).astimezone(timezone.utc)
    b = datetime(d.year, d.month, d.day, h_to, tzinfo=_IL_TZ).astimezone(timezone.utc)
    return (a.isoformat(), b.isoformat())


_REF = _recent_monday()
REF_DATE = _REF.isoformat()

# Peak windows, converted from local Israel time → UTC for the API.
PEAK_WINDOWS_UTC = [
    _utc_window(_REF, 7, 9),    # morning peak 07:00–09:00 local
    _utc_window(_REF, 16, 19),  # evening peak 16:00–19:00 local
]
LONG_ROUTE_KM = 10.0
MAX_WORKERS   = 8


# ── geometry ──────────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def geometry_from_stops(stops):
    """[(lat, lon), ...] → (path_km, circuity)"""
    coords = [(s["lat"], s["lon"]) for s in stops
              if s.get("lat") and s.get("lon")]
    if len(coords) < 2:
        return np.nan, np.nan
    path_km = sum(haversine_km(coords[i][0], coords[i][1],
                               coords[i+1][0], coords[i+1][1])
                  for i in range(len(coords)-1))
    air_km = haversine_km(coords[0][0], coords[0][1],
                          coords[-1][0], coords[-1][1])
    circuity = path_km / air_km if air_km > 1e-3 else np.nan
    return path_km, circuity


# ── API calls ─────────────────────────────────────────────────────────────────

def api_get(endpoint, params, timeout=25, retries=2):
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(f"{API}{endpoint}", params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries:
                return []
            time.sleep(1)
    return []


def get_peak_trips(route_id):
    """Return all start_times (UTC str) in peak windows for this route."""
    trips = []
    for t_from, t_to in PEAK_WINDOWS_UTC:
        batch = api_get("/gtfs_rides/list", {
            "gtfs_route_id": route_id,
            "start_time_from": t_from,
            "start_time_to":   t_to,
            "limit": 100,
        })
        trips.extend(batch)
    return trips


def get_geometry_for_route(line_ref, sample_start_time):
    """
    Fetch stops for one trip (narrow window around its start_time)
    and return (length_km, circuity).
    """
    # narrow 2-minute window around the trip's start
    dt = datetime.fromisoformat(sample_start_time.replace("Z", "+00:00"))
    t_from = (dt - timedelta(seconds=30)).isoformat()
    t_to   = (dt + timedelta(seconds=90)).isoformat()

    stops = api_get("/route_timetable/list", {
        "line_refs": line_ref,
        "planned_start_time_date_from": t_from,
        "planned_start_time_date_to":   t_to,
        "limit": 200,
    })
    if not stops:
        return np.nan, np.nan
    stops.sort(key=lambda x: x.get("planned_arrival_time", ""))
    return geometry_from_stops(stops)


# ── per-route computation ─────────────────────────────────────────────────────

def compute_route(route_row):
    """
    route_row: dict with keys id, line_ref, route_short_name, route_direction, ...
    Returns dict with computed metrics.
    """
    rid      = route_row["id"]
    line_ref = route_row["line_ref"]

    # 1. Peak trips → headway
    trips = get_peak_trips(rid)
    headway_min = np.nan
    sample_start = None

    if trips:
        start_times = sorted(t["start_time"] for t in trips if t.get("start_time"))
        if start_times:
            sample_start = start_times[0]

        # Convert to minutes-since-midnight (UTC) for gap calc
        def to_min(s):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return (dt.hour * 60 + dt.minute + dt.second / 60) % (24 * 60)

        mins = sorted(to_min(s) for s in start_times if s)

        # Split across peak windows to avoid cross-window gaps
        gaps = []
        for i in range(len(mins) - 1):
            g = mins[i+1] - mins[i]
            if 0 < g <= 90:
                gaps.append(g)
        headway_cv = np.nan
        if gaps:
            headway_min = float(np.mean(gaps))
            if len(gaps) >= 2:
                headway_cv = float(np.std(gaps, ddof=1) / np.mean(gaps))
    else:
        headway_cv = np.nan

    # 2. Geometry
    length_km, circuity = np.nan, np.nan
    if sample_start:
        length_km, circuity = get_geometry_for_route(line_ref, sample_start)

    return {
        "route_id":       rid,
        "line_ref":       line_ref,
        "makat":          route_row.get("route_mkt", ""),
        "line_number":    route_row.get("route_short_name", ""),
        "direction":      route_row.get("route_direction", ""),
        "operator_ref":   route_row.get("operator_ref"),
        "operator":       GUSH_DAN_OPERATORS.get(route_row.get("operator_ref"), "?"),
        "route_name":     route_row.get("route_long_name", ""),
        "headway_min":    headway_min,
        "headway_cv":     headway_cv,
        "length_km":      length_km,
        "circuity":       circuity,
        "peak_trips":     len(trips),
    }


# ── normalise ────────────────────────────────────────────────────────────────

def minmax_score(series, lower_is_better=False):
    """Scale to 0-100; NaN rows remain NaN (no imputation here)."""
    s    = series.copy()
    valid = s.dropna()
    if len(valid) < 2:
        return pd.Series(np.nan, index=s.index)
    mn, mx = valid.min(), valid.max()
    if mx == mn:
        return pd.Series(np.where(s.notna(), 50.0, np.nan), index=s.index)
    norm = (s - mn) / (mx - mn) * 100
    return (100 - norm) if lower_is_better else norm


def length_penalty_score(km):
    if pd.isna(km) or km <= LONG_ROUTE_KM:
        return 100.0
    return max(0.0, 100.0 - (km - LONG_ROUTE_KM) * (100.0 / 30.0))


# ── main ──────────────────────────────────────────────────────────────────────

def fetch_routes():
    all_routes = []
    for op_ref, op_name in GUSH_DAN_OPERATORS.items():
        offset = 0
        while True:
            batch = api_get("/gtfs_routes/list", {
                "operator_refs": op_ref,
                "date_from": REF_DATE,
                "date_to":   REF_DATE,
                "route_type": "3",
                "limit":  500,
                "offset": offset,
            })
            if not batch:
                break
            for r in batch:
                r["operator_ref"] = op_ref
            all_routes.extend(batch)
            if len(batch) < 500:
                break
            offset += 500
        print(f"  {op_name}: {len([r for r in all_routes if r['operator_ref']==op_ref])} routes")
    return all_routes


def main():
    print("Fetching Gush Dan routes …")
    routes = fetch_routes()
    print(f"Total routes: {len(routes)}")

    # Deduplicate by makat + direction (keep latest route_id).
    # NOTE: the same line number can exist as several distinct routes (different
    # makat) in different cities — so we must key on route_mkt, not line number.
    df_routes = (pd.DataFrame(routes)
                 .sort_values("id", ascending=False)
                 .drop_duplicates(subset=["route_mkt", "route_direction"]))

    # Only compute routes that exist in the (regular-only) ridership dataset —
    # huge speedup vs. computing every GTFS route nationwide.
    try:
        s3 = pd.read_parquet("stage3_ridership.parquet")
        keep = set(s3["makat"].astype(str))
        df_routes = df_routes[df_routes["route_mkt"].astype(str).isin(keep)]
        print(f"Restricted to {len(keep)} regular makats from ridership")
    except Exception as e:
        print(f"(no ridership filter: {e})")

    df_routes = df_routes.to_dict("records")
    print(f"After dedup + filter (per makat+direction): {len(df_routes)} routes")

    # Parallel processing
    results = []
    done = 0
    print(f"Computing metrics with {MAX_WORKERS} workers …")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(compute_route, r): r for r in df_routes}
        for fut in as_completed(futures):
            done += 1
            row = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"route_id": row["id"], "line_number": row.get("route_short_name","?"),
                       "error": str(e)}
            results.append(res)
            if done % 20 == 0:
                print(f"  {done}/{len(df_routes)} done")

    df = pd.DataFrame(results)
    df["makat"] = df["makat"].astype(str)

    # Filter student routes
    STUDENT_KEYWORDS = r"תלמיד|ילדי|בית ספר|גני ילד|ביה''ס|ביה\"ס|בי''ס|בי\"ס"
    keyword_mask = df["route_name"].str.contains(STUDENT_KEYWORDS, na=False)
    dan_9xx_mask = (df["operator"] == "דן") & df["line_number"].str.match(r"^9\d\d$")
    student_mask = keyword_mask | dan_9xx_mask
    removed = student_mask.sum()
    df = df[~student_mask].copy()
    print(f"Student filter: removed {removed} rows ({student_mask.sum() if False else removed})")
    df.to_parquet("stage1_gtfs_raw.parquet", index=False)

    # Aggregate directions → one row per makat (the unique route identifier)
    df_agg = (df.groupby(["makat"], as_index=False)
                .agg(
                    line_number=("line_number", "first"),
                    operator   =("operator",    "first"),
                    headway_min=("headway_min", "mean"),
                    headway_cv =("headway_cv",  "mean"),
                    length_km  =("length_km",   "mean"),
                    circuity   =("circuity",     "mean"),
                    peak_trips =("peak_trips",   "sum"),
                ))

    # Scores
    df_agg["score_headway"]   = minmax_score(df_agg["headway_min"], lower_is_better=True).values
    df_agg["score_hw_even"]   = minmax_score(df_agg["headway_cv"],  lower_is_better=True).values
    df_agg["score_circuity"]  = minmax_score(df_agg["circuity"],    lower_is_better=True).values
    df_agg["score_length"]    = df_agg["length_km"].apply(length_penalty_score)
    df_agg["makat"] = df_agg["makat"].astype(str)

    df_agg.to_parquet("stage1_gtfs.parquet", index=False)
    df.to_parquet("stage1_gtfs_raw.parquet", index=False)
    print("\nSaved → stage1_gtfs.parquet")

    # Preview
    preview_cols = ["line_number", "operator", "headway_min", "length_km", "circuity",
                    "score_headway", "score_circuity", "score_length"]
    sample = (df_agg[preview_cols]
              .dropna(subset=["headway_min"])
              .sort_values("score_headway", ascending=False)
              .head(10)
              .reset_index(drop=True))
    pd.set_option("display.float_format", "{:.2f}".format)
    pd.set_option("display.width", 130)
    print("\n=== Top 10 Gush Dan lines — Stage 1 ===")
    print(sample.to_string())

    print(f"\nTotal lines with headway data: {df_agg['headway_min'].notna().sum()}/{len(df_agg)}")
    return df_agg


if __name__ == "__main__":
    main()
