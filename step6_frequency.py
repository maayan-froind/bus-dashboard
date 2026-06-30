"""
Stage 6: off-peak frequency + daily trip count per direction.
For each direction we fetch the full day's planned departures (one query) and derive:
  - daily trips per direction (count)
  - off-peak headway (10:00–15:00 IST) → off-peak buses/hour in the dashboard
Peak headway already comes from stage 1.
Output: stage6_frequency.parquet → makat, daily_trips_dir, headway_offpeak
"""

import time
from pull_meta import record
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta

import numpy as np
import pandas as pd
import requests

API = "https://open-bus-stride-api.hasadna.org.il"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bus-dashboard/1.0"})

# Representative service day: step back a week (past the API's ~3-day ride
# ingestion lag) then snap to that week's Monday. Must match step1's REF_DATE.
_ref_base = date.today() - timedelta(days=7)
REF = (_ref_base - timedelta(days=_ref_base.weekday())).isoformat()
# full service day in UTC (≈ 04:00–24:00 IST, IST = UTC+3)
DAY_FROM = f"{REF}T01:00:00+00:00"
DAY_TO   = f"{REF}T21:00:00+00:00"
# off-peak midday band in UTC minutes-since-midnight (10:00–15:00 IST = 07:00–12:00 UTC)
OFFPEAK_FROM_MIN, OFFPEAK_TO_MIN = 7 * 60, 12 * 60
MAX_WORKERS = 10


def api_get(endpoint, params, timeout=20, retries=2):
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(f"{API}{endpoint}", params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries:
                return []
            time.sleep(0.5)
    return []


def to_min(s):
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.hour * 60 + dt.minute + dt.second / 60


def headway_of(mins):
    mins = sorted(mins)
    gaps = [mins[i + 1] - mins[i] for i in range(len(mins) - 1)
            if 0 < mins[i + 1] - mins[i] <= 90]
    return float(np.mean(gaps)) if gaps else np.nan


def per_direction(route_id):
    """Return (daily_trip_count, off-peak headway) for one direction."""
    trips = api_get("/gtfs_rides/list", {
        "gtfs_route_id": route_id,
        "start_time_from": DAY_FROM, "start_time_to": DAY_TO, "limit": 500,
    })
    starts = [t["start_time"] for t in trips if t.get("start_time")]
    daily = len(starts)
    mins = [to_min(s) for s in starts]
    off = [m for m in mins if OFFPEAK_FROM_MIN <= m < OFFPEAK_TO_MIN]
    return daily, headway_of(off)


def main():
    raw = pd.read_parquet("stage1_gtfs_raw.parquet")
    raw["makat"] = raw["makat"].astype(str)
    try:
        keep = set(pd.read_parquet("stage3_ridership.parquet")["makat"].astype(str))
        raw = raw[raw["makat"].isin(keep)]
    except Exception:
        pass
    dirs = raw[["makat", "route_id"]].dropna().drop_duplicates("route_id").to_dict("records")
    print(f"Fetching daily timetable for {len(dirs)} directions …")

    rows, done = [], 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(per_direction, d["route_id"]): d for d in dirs}
        for fut in as_completed(futs):
            d = futs[fut]
            done += 1
            try:
                daily, hw_off = fut.result()
            except Exception:
                daily, hw_off = 0, np.nan
            rows.append({"makat": d["makat"], "daily": daily, "hw_off": hw_off})
            if done % 100 == 0:
                print(f"  {done}/{len(dirs)}")

    df = pd.DataFrame(rows)
    agg = (df.groupby("makat", as_index=False)
             .agg(daily_trips_dir=("daily", "mean"),       # avg trips/day per direction
                  headway_offpeak=("hw_off", "mean")))
    agg["makat"] = agg["makat"].astype(str)
    agg.to_parquet("stage6_frequency.parquet", index=False)
    record("frequency", {"service_date": REF})
    print(f"\nSaved → stage6_frequency.parquet ({len(agg)} routes)")
    print(agg.head(8).to_string())


if __name__ == "__main__":
    main()
