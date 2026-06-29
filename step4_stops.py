"""
Stage 4: collect the list of cities (and stop names) each route passes through,
plus an ordered list of stop coordinates per line so the dashboard can draw the
route on a map and filter routes by city / neighbourhood.
Source: open-bus-stride route_timetable (stops carry `city`, `name`, `lat`, `lon`).

Also builds Stage 7 (stage7_stops_index.parquet): a reverse index of public
stop code → the bus lines (makats) that serve it (+ the stop's name / city /
lat / lon), so the dashboard can search by stop number and show the serving
lines on a map. The public `code` lives in gtfs_stops, joined to the
route_timetable stops by stop `id` (verified identical id space, same date).
"""

import json
import time
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

API = "https://open-bus-stride-api.hasadna.org.il"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bus-dashboard/1.0"})

# Reference weekday: this matches step1/step6 (steps back a week, past the
# API's ~3-day ride ingestion lag, then snaps to that week's Monday).
_ref_base = date.today() - timedelta(days=7)
REF = (_ref_base - timedelta(days=_ref_base.weekday())).isoformat()
WIN_FROM  = f"{REF}T04:00:00+00:00"      # morning peak 07:00–09:00 local
WIN_TO    = f"{REF}T06:00:00+00:00"
WIN_FROM2 = f"{REF}T13:00:00+00:00"      # fallback afternoon peak
WIN_TO2   = f"{REF}T16:00:00+00:00"
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
    """Return (cities set, stop-names set, ordered geo list, stop-id set)."""
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
            ids = {s["id"] for s in ride_stops if s.get("id")}
            return cities, names, geo, ids
    return set(), set(), [], set()


def fetch_stop_code_map(ref_date):
    """All stops for ref_date → {stop_id: {code, lat, lon, name, city}}."""
    out, offset, page = {}, 0, 5000
    while True:
        batch = api_get("/gtfs_stops/list", {
            "date_from": ref_date, "date_to": ref_date,
            "limit": page, "offset": offset,
        })
        if not batch:
            break
        for s in batch:
            if s.get("id") is not None and s.get("code") is not None:
                out[s["id"]] = {
                    "code": s["code"], "lat": s.get("lat"), "lon": s.get("lon"),
                    "name": s.get("name", ""), "city": s.get("city", ""),
                }
        offset += len(batch)
        print(f"  gtfs_stops fetched {offset} …")
        if len(batch) < page:
            break
    return out


def build_stop_index(makat_stop_ids, code_map):
    """makat→{stop_ids} + id→stop info  →  one row per public stop code."""
    by_code = {}
    for makat, sids in makat_stop_ids.items():
        for sid in sids:
            info = code_map.get(sid)
            if not info:
                continue
            code = info["code"]
            rec = by_code.get(code)
            if rec is None:
                rec = by_code[code] = {
                    "code": code, "name": info["name"], "city": info["city"],
                    "lat": info["lat"], "lon": info["lon"], "makats": set(),
                }
            rec["makats"].add(makat)
    rows = [{**r, "makats": sorted(r["makats"])} for r in by_code.values()]
    return pd.DataFrame(rows, columns=["code", "name", "city", "lat", "lon", "makats"])


def main():
    raw = pd.read_parquet("stage1_gtfs_raw.parquet")
    raw["line_number"] = raw["line_number"].astype(str)
    raw["makat"] = raw["makat"].astype(str)
    refs = raw[["line_ref", "makat", "line_number", "operator"]].drop_duplicates("line_ref")
    work = refs.to_dict("records")
    print(f"Fetching stops for {len(work)} line_refs (ref date {REF}) …")

    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(stops_for_line, r["line_ref"]): r for r in work}
        for fut in as_completed(futs):
            done += 1
            r = futs[fut]
            try:
                cities, names, geo, ids = fut.result()
            except Exception:
                cities, names, geo, ids = set(), set(), [], set()
            results[r["line_ref"]] = (cities, names, geo, ids)
            if done % 100 == 0:
                print(f"  {done}/{len(work)}")

    refs["cities"] = refs["line_ref"].map(lambda lr: results.get(lr, (set(), set(), [], set()))[0])
    refs["stops"]  = refs["line_ref"].map(lambda lr: results.get(lr, (set(), set(), [], set()))[1])
    refs["geo"]    = refs["line_ref"].map(lambda lr: results.get(lr, (set(), set(), [], set()))[2])
    refs["sids"]   = refs["line_ref"].map(lambda lr: results.get(lr, (set(), set(), [], set()))[3])

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

    # ── Stage 7: stop-code → serving lines index ──────────────────────────────
    makat_stop_ids = {}
    for rec in refs.to_dict("records"):
        makat_stop_ids.setdefault(rec["makat"], set()).update(rec["sids"])
    print(f"\nFetching gtfs_stops code map for {REF} …")
    code_map = fetch_stop_code_map(REF)
    print(f"  {len(code_map)} stops with codes")
    idx = build_stop_index(makat_stop_ids, code_map)
    idx.to_parquet("stage7_stops_index.parquet", index=False)
    print(f"Saved → stage7_stops_index.parquet ({len(idx)} stops on our lines)")


if __name__ == "__main__":
    main()
