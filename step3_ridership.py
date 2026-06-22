"""
Stage 3: Download ridership data from data.gov.il, compute PKM per Gush Dan line.
Also extracts AverageSpeed as cross-reference for commercial speed.
"""

import requests
import pandas as pd
import numpy as np

CKAN_SEARCH  = "https://data.gov.il/api/3/action/datastore_search"
RESOURCE_ID  = "7b126b6d-3411-4438-89c3-8eceea61c2db"   # 2026 ridership
PAGE_SIZE    = 1000

def fetch_ridership():
    """Fetch ALL ridership records nationwide (every metropolitan area / operator)."""
    records = []
    offset = 0
    while True:
        r = requests.get(CKAN_SEARCH, params={
            "resource_id": RESOURCE_ID,
            "limit":    PAGE_SIZE,
            "offset":   offset,
        }, timeout=40)
        r.raise_for_status()
        batch = r.json()["result"]["records"]
        if not batch:
            break
        records.extend(batch)
        print(f"  {len(records)} records fetched …")
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return records


def main():
    print("Fetching ridership data (nationwide) …")
    records = fetch_ridership()
    df = pd.DataFrame(records)
    print(f"Total records: {len(df)}")

    # Keep ONLY regular routes (סדיר) — excludes student/night/feeder variants
    if "RouteParticular" in df.columns:
        before = len(df)
        df = df[df["RouteParticular"] == "סדיר"].copy()
        print(f"Regular-only filter: kept {len(df)} of {before} rows")

    # Ensure numeric
    for col in ["WeeklyKM", "WeeklyPassengers", "RouteLength", "AverageSpeed"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # PKM = passengers per km
    df["PKM"] = df["WeeklyPassengers"] / df["WeeklyKM"]

    # Aggregate per RouteName (line number) + AgencyName, average across directions
    # numeric extras
    for col in ["StationsInRoute", "AverageTripDuration", "DailyPassengers",
                "WeekyRides", "UniqueStations", "AVGCommutersPerRide(Weekly)"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    def first_valid(s):
        v = s.dropna()
        return v.iloc[0] if len(v) else None

    # group by RouteID (makat) — the unique route identifier. The same line
    # number + operator can be several distinct routes in different cities.
    agg = (df.groupby(["RouteID"], as_index=False)
             .agg(
                 line_number  =("RouteName",      "first"),
                 operator     =("AgencyName",     "first"),
                 district     =("Metropolin",     "first"),
                 cluster      =("ClusterName",     first_valid),
                 service_type =("ServiceType",    "first"),
                 particular   =("RouteParticular","first"),
                 bus_type     =("BusType",        "first"),
                 bus_size     =("BusSize",         first_valid),
                 origin_city  =("OriginCityName",  first_valid),
                 dest_city    =("DestinationCityName", first_valid),
                 operation_since=("OperationSince", first_valid),
                 stations     =("StationsInRoute", "mean"),
                 trip_duration=("AverageTripDuration", "mean"),
                 daily_pass   =("DailyPassengers", "mean"),
                 avg_pass_ride=("AVGCommutersPerRide(Weekly)", "mean"),
                 weekly_rides =("WeekyRides",      "sum"),
                 PKM          =("PKM",           "mean"),
                 AverageSpeed =("AverageSpeed",   "mean"),
                 RouteLength  =("RouteLength",    "mean"),
                 WeeklyKM     =("WeeklyKM",       "sum"),
                 WeeklyPassengers=("WeeklyPassengers","sum"),
             )
             .rename(columns={"RouteID": "makat"}))

    # Normalise operator names to match stage 1
    name_map = {
        "דן":         "דן",
        "מטרופולין":  "מטרופולין",
        "אגד תעבורה": "אגד תעבורה",
    }
    agg["operator"] = agg["operator"].map(name_map).fillna(agg["operator"])
    agg["line_number"] = agg["line_number"].astype(str)
    agg["makat"] = agg["makat"].astype(str)

    agg.to_parquet("stage3_ridership.parquet", index=False)
    print("\nSaved → stage3_ridership.parquet")

    # Preview
    pd.set_option("display.float_format", "{:.2f}".format)
    pd.set_option("display.width", 130)
    sample = (agg.dropna(subset=["PKM"])
                 .sort_values("PKM", ascending=False)
                 .head(10)
                 .reset_index(drop=True))
    print("\n=== Top 10 by PKM ===")
    print(sample[["line_number","operator","PKM","AverageSpeed","RouteLength"]].to_string())
    return agg


if __name__ == "__main__":
    main()
