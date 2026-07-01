"""
Stage 3: Download ridership data from data.gov.il, compute PKM per Gush Dan line.
Also extracts AverageSpeed as cross-reference for commercial speed.
"""

import json
from pull_meta import record
import requests
import pandas as pd
import numpy as np

# passenger-per-ride profile: day-type × time band (data.gov.il column names)
_DAYS  = ["ימי חול", "שישי", "שבת"]
_SLOTS = ["00:00-03:59", "04:00-05:59", "06:00-08:59", "09:00-11:59",
          "12:00-14:59", "15:00-18:59", "19:00-23:59"]

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

    # Ensure numeric (core + extras + the hourly passenger-profile bands)
    _band_cols = [f"{d} - {s}" for d in _DAYS for s in _SLOTS
                  if f"{d} - {s}" in df.columns]
    for col in ["WeeklyKM", "WeeklyPassengers", "RouteLength", "AverageSpeed",
                "StationsInRoute", "AverageTripDuration", "DailyPassengers",
                "WeekyRides", "UniqueStations", "AVGCommutersPerRide(Weekly)",
                "AVGPassengersPerWeek", "OperatingCostPerPassenger",
                "NumOfAlternatives", "DailyRides(Tuesday)", "ערך מקסימום בתקופת יום",
                "דרוג הפחתה", "דרוג הוספה",
                # MOT recommendation-engine low-load flags (1.0 when triggered)
                "ערך מקסימום בתקופת יום קטן מ 3", "ערך מקסימום בתקופת יום קטן מ 7",
                "ערך מקסימום בתקופת יום קטן מ 10", "ערך מקסימום בתקופת יום קטן מ 15",
                "ממוצע נוסעים לקמ נמוך", "year"] + _band_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # PKM = passengers per km
    df["PKM"] = df["WeeklyPassengers"] / df["WeeklyKM"]

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
                 route_type   =("RouteType",       first_valid),
                 particular   =("RouteParticular","first"),
                 bus_type     =("BusType",        "first"),
                 bus_size     =("BusSize",         first_valid),
                 origin_city  =("OriginCityName",  first_valid),
                 dest_city    =("DestinationCityName", first_valid),
                 operation_since=("OperationSince", first_valid),
                 stations     =("StationsInRoute", "mean"),
                 unique_stations=("UniqueStations", "mean"),
                 num_alternatives=("NumOfAlternatives", "mean"),
                 trip_duration=("AverageTripDuration", "mean"),
                 daily_pass   =("DailyPassengers", "mean"),
                 avg_pass_ride=("AVGCommutersPerRide(Weekly)", "mean"),
                 avg_pass_week=("AVGPassengersPerWeek", "mean"),
                 daily_rides_tue=("DailyRides(Tuesday)", "mean"),
                 weekly_rides =("WeekyRides",      "sum"),
                 cost_per_pass=("OperatingCostPerPassenger", "mean"),
                 PKM          =("PKM",           "mean"),
                 AverageSpeed =("AverageSpeed",   "mean"),
                 RouteLength  =("RouteLength",    "mean"),
                 WeeklyKM     =("WeeklyKM",       "sum"),
                 WeeklyPassengers=("WeeklyPassengers","sum"),
                 recommendation=("המלצה",          first_valid),
                 peak_period  =("נסועה מקסימלית",  first_valid),
                 peak_period_val=("ערך מקסימום בתקופת יום", "mean"),
                 rank_reduce  =("דרוג הפחתה",       "mean"),
                 rank_add     =("דרוג הוספה",       "mean"),
                 # data period + MOT low-load recommendation flags (max = triggered
                 # on any direction). Surface WHY a line is flagged for reduction.
                 data_year    =("year",            "max"),
                 data_quarter =("Q",               first_valid),
                 flag_peak_lt3 =("ערך מקסימום בתקופת יום קטן מ 3",  "max"),
                 flag_peak_lt7 =("ערך מקסימום בתקופת יום קטן מ 7",  "max"),
                 flag_peak_lt10=("ערך מקסימום בתקופת יום קטן מ 10", "max"),
                 flag_peak_lt15=("ערך מקסימום בתקופת יום קטן מ 15", "max"),
                 flag_low_pkm  =("ממוצע נוסעים לקמ נמוך",            "max"),
             )
             .rename(columns={"RouteID": "makat"}))

    # hourly passenger-per-ride profile per route → JSON column `pax_profile`
    if _band_cols:
        prof = df.groupby("RouteID")[_band_cols].mean()

        def _profile(rid):
            row = prof.loc[rid] if rid in prof.index else None
            out = {}
            for d in _DAYS:
                vals = {}
                for s in _SLOTS:
                    c = f"{d} - {s}"
                    v = None if row is None or c not in _band_cols or pd.isna(row[c]) \
                        else round(float(row[c]), 1)
                    vals[s] = v
                out[d] = vals
            return json.dumps(out, ensure_ascii=False)

        agg["pax_profile"] = agg["makat"].map(_profile)

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

    record("ridership", {"resource_id": RESOURCE_ID})
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
