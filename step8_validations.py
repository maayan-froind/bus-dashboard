"""
Stage 8: per-stop validations ("תיקופי מסלקה לתחנה", data.gov.il).
Real boarding counts at each stop, from all ticketing means. StationId equals
our public stop code (verified), so it joins directly to stage7 / GTFS stops.

The resource has one row per (StationId × time-band × month) with daily tap
counts day_1..day_31. We aggregate per station:
  taps_total       — sum of all taps in the period (year-to-date)
  taps_daily_avg   — taps_total / number of calendar days covered
  taps_peak        — taps during peak bands (שיא)
  taps_offpeak     — taps during off-peak bands (שפל)
Output: stage8_validations.parquet → code, taps_total, taps_daily_avg,
        taps_peak, taps_offpeak
"""

import time
import requests
import pandas as pd

CKAN = "https://data.gov.il/api/3/action/datastore_search"
RESOURCE_2026 = "3ad014c3-e0a6-4ba0-9b2b-12a29d273512"   # תיקופי מסלקה לתחנה 2026
PAGE = 32000
DAY_COLS = [f"day_{i}" for i in range(1, 32)]


def fetch_aggregate(resource_id):
    totals = {}          # code -> [total, peak, offpeak]
    dates = set()        # distinct (month_key, day) with any data → days covered
    offset, n = 0, 0
    while True:
        for attempt in range(3):
            try:
                r = requests.get(CKAN, params={"resource_id": resource_id,
                                               "limit": PAGE, "offset": offset}, timeout=90)
                r.raise_for_status()
                recs = r.json()["result"]["records"]
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
        if not recs:
            break
        for rec in recs:
            code = rec.get("StationId")
            if code is None:
                continue
            code = str(int(code))
            band = rec.get("LowOrPeakDescFull") or ""
            is_peak = "שיא" in band
            is_off = "שפל" in band
            mk = rec.get("month_key")
            row_sum = 0.0
            for di, c in enumerate(DAY_COLS, start=1):
                v = rec.get(c)
                if v:
                    row_sum += float(v)
                    dates.add((mk, di))
            t = totals.setdefault(code, [0.0, 0.0, 0.0])
            t[0] += row_sum
            if is_peak:
                t[1] += row_sum
            elif is_off:
                t[2] += row_sum
        n += len(recs)
        print(f"  {n} rows aggregated … ({len(totals)} stations)")
        if len(recs) < PAGE:
            break
        offset += PAGE
    return totals, max(1, len(dates))


def main():
    print("Fetching per-stop validations (2026) …")
    totals, days = fetch_aggregate(RESOURCE_2026)
    print(f"Covered {days} calendar days across {len(totals)} stations")
    rows = []
    for code, (tot, pk, off) in totals.items():
        rows.append({
            "code": code,
            "taps_total": round(tot),
            "taps_daily_avg": round(tot / days, 1),
            "taps_peak": round(pk),
            "taps_offpeak": round(off),
        })
    out = pd.DataFrame(rows)
    out.to_parquet("stage8_validations.parquet", index=False)
    print(f"\nSaved → stage8_validations.parquet ({len(out)} stations)")
    print(out.sort_values("taps_total", ascending=False).head(8).to_string(index=False))


if __name__ == "__main__":
    main()
