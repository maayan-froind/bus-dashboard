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

import json
import time
from pull_meta import record
import requests
import pandas as pd

CKAN = "https://data.gov.il/api/3/action/datastore_search"
RESOURCE_2026 = "3ad014c3-e0a6-4ba0-9b2b-12a29d273512"   # תיקופי מסלקה לתחנה 2026
PAGE = 32000
DAY_COLS = [f"day_{i}" for i in range(1, 32)]
# time-of-day bands (the hour-range prefix of LowOrPeakDescFull), in order
BANDS = ["04:00 - 05:59", "06:00 - 08:59", "09:00 - 11:59", "12:00 - 14:59",
         "15:00 - 18:59", "19:00 - 23:59", "24:00 - 27:59"]


def fetch_aggregate(resource_id):
    totals = {}          # code -> {"t","pk","off","bands":{band:val}}
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
            band_key = band.rsplit(" - ", 1)[0] if " - " in band else band
            is_peak = "שיא" in band
            mk = rec.get("month_key")
            row_sum = 0.0
            for di, c in enumerate(DAY_COLS, start=1):
                v = rec.get(c)
                if v:
                    row_sum += float(v)
                    dates.add((mk, di))
            t = totals.setdefault(code, {"t": 0.0, "pk": 0.0, "off": 0.0, "bands": {}})
            t["t"] += row_sum
            t["pk" if is_peak else "off"] += row_sum
            t["bands"][band_key] = t["bands"].get(band_key, 0.0) + row_sum
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
    for code, t in totals.items():
        profile = {b: round(t["bands"].get(b, 0.0)) for b in BANDS}
        rows.append({
            "code": code,
            "taps_total": round(t["t"]),
            "taps_daily_avg": round(t["t"] / days, 1),
            "taps_peak": round(t["pk"]),
            "taps_offpeak": round(t["off"]),
            "taps_profile": json.dumps(profile, ensure_ascii=False),
        })
    out = pd.DataFrame(rows)
    out.to_parquet("stage8_validations.parquet", index=False)
    record("validations", {"resource_id": RESOURCE_2026})
    print(f"\nSaved → stage8_validations.parquet ({len(out)} stations)")
    print(out.sort_values("taps_total", ascending=False).head(8).to_string(index=False))


if __name__ == "__main__":
    main()
