"""
Stage 9: historical ridership (נסועה) for trend analysis. Pulls the previous
years' files from the SAME data.gov.il "נסועה בקווי אוטובוס" dataset (we already
use 2026 as stage3) and aggregates per route (RouteID = makat) per year, so the
line page can show how a line's demand changed over time.

Output: stage9_ridership_history.parquet
  makat, year, daily_pass, pkm, avg_speed   (one row per line per year)

The 2026 point comes live from stage3 in the dashboard; this fills 2023-2025.
"""
import time
from pull_meta import record

import pandas as pd
import requests

CKAN = "https://data.gov.il/api/3/action/datastore_search"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bus-dashboard/1.0"})

# Yearly resources from the ridership dataset (2026 is stage3; these are history).
RESOURCES = {
    2025: "a52b0f0a-0785-48ff-a2d8-70a4a8e63fd8",
    2024: "e6cfac2f-979a-44fd-b439-ecb116ec0b16",
    2023: "9cf3237f-80cd-4646-836f-f1370088430a",
}


def fetch_resource(resource_id):
    out, offset, page = [], 0, 5000
    while True:
        for attempt in range(3):
            try:
                r = SESSION.get(CKAN, params={"resource_id": resource_id,
                                              "limit": page, "offset": offset}, timeout=40)
                r.raise_for_status()
                res = r.json()["result"]
                break
            except Exception:
                if attempt == 2:
                    return out
                time.sleep(1.0)
        recs = res.get("records", [])
        out += recs
        offset += len(recs)
        if not recs or offset >= res.get("total", 0):
            break
    return out


def main():
    frames = []
    for year, rid in RESOURCES.items():
        recs = fetch_resource(rid)
        df = pd.DataFrame(recs)
        if df.empty:
            print(f"{year}: no records, skipping")
            continue
        # match stage3: regular routes only (if the column exists in this file)
        if "RouteParticular" in df.columns:
            df = df[df["RouteParticular"] == "סדיר"].copy()
        for c in ["DailyPassengers", "WeeklyPassengers", "WeeklyKM", "AverageSpeed"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["makat"] = df["RouteID"].astype(str)
        df["year"] = int(year)
        g = (df.groupby(["makat", "year"], as_index=False)
               .agg(daily_pass=("DailyPassengers", "mean"),
                    _wp=("WeeklyPassengers", "sum"),
                    _wk=("WeeklyKM", "sum"),
                    avg_speed=("AverageSpeed", "mean")))
        g["pkm"] = g["_wp"] / g["_wk"]
        frames.append(g[["makat", "year", "daily_pass", "pkm", "avg_speed"]])
        print(f"{year}: {len(g)} lines")

    if not frames:
        print("No history pulled; nothing written.")
        return
    hist = pd.concat(frames, ignore_index=True)
    hist.to_parquet("stage9_ridership_history.parquet", index=False)
    record("ridership_history", {"years": sorted(RESOURCES)})
    print(f"\nSaved → stage9_ridership_history.parquet "
          f"({len(hist)} rows, {hist['makat'].nunique()} lines, years {sorted(hist['year'].unique())})")


if __name__ == "__main__":
    main()
