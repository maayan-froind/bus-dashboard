"""
Stage 4: collect the list of cities (and stop names) each route passes through,
plus an ordered list of stop coordinates per line so the dashboard can draw the
route on a map and filter routes by city / neighbourhood.
Source: open-bus-stride route_timetable (stops carry `city`, `name`, `lat`, `lon`).
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

API = "https://open-bus-stride-api.hasadna.org.il"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bus-dashboard/1.0"})

# A weekday peak window (same reference day as stage 1)
WIN_FROM = "2026-06-16T04:00:00+00:00"
WIN_TO   = "2026-06-16T06:00:00+00:00"
# fallback afternoon window for routes with no morning-peak trip
WIN_FROM2 = "2026-06-16T13:00:00+00:00"
WIN_TO2   = "2026-06-16T16:00:00+00:00"
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
            time.sleep(0.6)
    return []


def stops_for_line(line_ref):
    """Return (cities set, stop-names set, ordered stop geo list) for one line_ref."""
    for t_from, t_to in [(WIN_FROM, WIN_TO), (WIN_FROM2, WIN_TO2)]:
        stops = api_get("/route_timetable/list", {
            "line_refs": line_ref,
            "planned_start_time_date_from": t_from,
            "planned_start_time_date_to":   t_to,
            "limit": 300,
        })
        if stops:
            # keep stops from a single ride (first ride id) to avoid mixing
            first_ride = stops[0].get("gtfs_ride_id")
            ride_stops = [s for s in stops if s.get("gtfs_ride_id") == first_ride] or stops
            ride_stops.sort(key=lambda s: s.get("planned_arrival_time", ""))
            cities = {s["city"] for s in ride_stops if s.get("city")}
            names  = {s["name"]  for s in ride_stops if s.get("name")}
            geo = [[round(s["lat"], 6), round(s["lon"], 6), s.get("name", ""), s.get("city", "")]
                   for s in ride_stops if s.get("lat") and s.get("lon")]
            return cities, names, geo
    return set(), set(), []


def main():
    raw = pd.read_parquet("stage1_gtfs_raw.parquet")
    raw["line_number"] = raw["line_number"].astype(str)
    raw["makat"] = raw["makat"].astype(str)
    refs = raw[["line_ref", "makat", "line_number", "operator"]].drop_duplicates("line_ref")
    work = refs.to_dict("records")
    print(f"Fetching stops for {len(work)} line_refs …")

    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(stops_for_line, r["line_ref"]): r for r in work}
        for fut in as_completed(futs):
            done += 1
            r = futs[fut]
            try:
                cities, names, geo = fut.result()
            except Exception:
                cities, names, geo = set(), set(), []
            results[r["line_ref"]] = (cities, names, geo)
            if done % 100 == 0:
                print(f"  {done}/{len(work)}")

    refs["cities"] = refs["line_ref"].map(lambda lr: results.get(lr, (set(), set(), []))[0])
    refs["stops"]  = refs["line_ref"].map(lambda lr: results.get(lr, (set(), set(), []))[1])
    refs["geo"]    = refs["line_ref"].map(lambda lr: results.get(lr, (set(), set(), []))[2])

    # aggregate per line_number + operator (union across directions)
    def union_sets(series):
        out = set()
        for s in series:
            out |= set(s)
        return sorted(out)

    def longest_geo(series):
        # keep the most detailed direction's stop sequence
        best = max(series, key=lambda g: len(g) if g else 0, default=[])
        return json.dumps(best, ensure_ascii=False)

    agg = (refs.groupby(["makat"], as_index=False)
              .agg(line_number=("line_number", "first"),
                   operator=("operator", "first"),
                   cities=("cities", union_sets), stops=("stops", union_sets),
                   geo=("geo", longest_geo)))
    agg["makat"] = agg["makat"].astype(str)

    agg.to_parquet("stage4_stops.parquet", index=False)
    print(f"\nSaved → stage4_stops.parquet ({len(agg)} lines)")

    all_cities = sorted({c for lst in agg["cities"] for c in lst})
    print(f"Distinct cities found: {len(all_cities)}")
    print("Sample:", all_cities[:20])


if __name__ == "__main__":
    main()
