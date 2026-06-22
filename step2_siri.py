"""
Stage 2: SIRI execution data — trip execution rate as schedule adherence proxy.
Headway evenness (CV) is computed in stage 1 from GTFS planned times.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

API     = "https://open-bus-stride-api.hasadna.org.il"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bus-dashboard/1.0"})

PEAK_WINDOWS = [
    ("2026-06-16T04:00:00+00:00", "2026-06-16T06:00:00+00:00"),
    ("2026-06-16T13:00:00+00:00", "2026-06-16T16:00:00+00:00"),
]
MAX_WORKERS = 8


def api_get(endpoint, params, timeout=15, retries=3):
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(f"{API}{endpoint}", params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries:
                return []
            time.sleep(0.5 * (attempt + 1))
    return []


def get_siri_route_id(line_ref):
    data = api_get("/siri_routes/list", {"line_refs": line_ref, "limit": 1})
    return data[0]["id"] if data else None


def compute_execution_rate(line_ref, gtfs_peak_trips):
    srid = get_siri_route_id(line_ref)
    if not srid:
        return {"line_ref": line_ref, "trip_execution_rate": np.nan, "siri_rides": 0}

    all_rides = []
    for t_from, t_to in PEAK_WINDOWS:
        batch = api_get("/siri_rides/list", {
            "siri_route_ids":            srid,
            "scheduled_start_time_from": t_from,
            "scheduled_start_time_to":   t_to,
            "limit": 100,
        })
        all_rides.extend(batch)

    exec_rate = np.nan
    if gtfs_peak_trips and gtfs_peak_trips > 0:
        exec_rate = min(len(all_rides) / gtfs_peak_trips, 1.0)

    return {
        "line_ref":            line_ref,
        "trip_execution_rate": exec_rate,
        "siri_rides":          len(all_rides),
    }


def main():
    stage1_raw = pd.read_parquet("stage1_gtfs_raw.parquet")
    print(f"Loaded {len(stage1_raw)} raw routes")

    work = (stage1_raw
            .groupby("line_ref")
            .agg(peak_trips=("peak_trips","sum"))
            .reset_index()
            .to_dict("records"))
    print(f"Processing {len(work)} unique line_refs …")

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(compute_execution_rate, r["line_ref"], r["peak_trips"]): r
                   for r in work}
        for fut in as_completed(futures):
            done += 1
            try:
                res = fut.result()
            except Exception as e:
                row = futures[fut]
                res = {"line_ref": row["line_ref"], "trip_execution_rate": np.nan}
            results.append(res)
            if done % 50 == 0:
                print(f"  {done}/{len(work)} done")

    siri_df = pd.DataFrame(results)

    # Map to line_number + operator
    raw_line = (stage1_raw[["line_ref","line_number","operator"]]
                .drop_duplicates("line_ref"))
    siri_df = siri_df.merge(raw_line, on="line_ref", how="left")

    stage2 = (siri_df.groupby(["line_number","operator"], as_index=False)
              .agg(trip_execution_rate=("trip_execution_rate","mean")))

    stage2.to_parquet("stage2_siri.parquet", index=False)
    print("\nSaved → stage2_siri.parquet")

    sample = (stage2.dropna(subset=["trip_execution_rate"])
              .sort_values("trip_execution_rate", ascending=False)
              .head(10)
              .reset_index(drop=True))
    pd.set_option("display.float_format", "{:.3f}".format)
    print("\n=== Top 10 by execution rate ===")
    print(sample.to_string())
    return stage2


if __name__ == "__main__":
    main()
