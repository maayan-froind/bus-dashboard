"""
Stage 5: snap each route's ordered stops to the road network (OSRM) so the map
shows street-following shapes instead of straight "air lines" between stops.
Falls back to the raw stop polyline when routing fails.
Input : stage4_stops.parquet (ordered stop geo per makat) + stage3 (which makats to do)
Output: stage5_shapes.parquet  →  makat, shape (json list of [lat, lon] road points)
"""

import json
from pull_meta import record
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

OSRM = "http://router.project-osrm.org/route/v1/driving/"
MAX_WAYPOINTS = 100          # OSRM demo limit guard — downsample longer routes
MAX_WORKERS = 4              # be polite to the public demo server
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bus-dashboard/1.0"})


def downsample(points, n):
    """Keep first, last and an even spread in between (≤ n points)."""
    if len(points) <= n:
        return points
    step = (len(points) - 1) / (n - 1)
    idx = sorted({round(i * step) for i in range(n)} | {0, len(points) - 1})
    return [points[i] for i in idx]


def road_shape(geo):
    """geo: list of [lat, lon, name, city]. Returns road-following [[lat,lon],…]."""
    pts = [(p[0], p[1]) for p in geo if p and p[0] and p[1]]
    if len(pts) < 2:
        return None
    raw = [[la, lo] for la, lo in pts]          # fallback = straight stop line
    wp = downsample(pts, MAX_WAYPOINTS)
    coords = ";".join(f"{lo},{la}" for la, lo in wp)
    for attempt in range(3):
        try:
            r = SESSION.get(OSRM + coords,
                            params={"overview": "full", "geometries": "geojson"},
                            timeout=30)
            if r.status_code == 200:
                j = r.json()
                if j.get("routes"):
                    g = j["routes"][0]["geometry"]["coordinates"]   # [lon,lat]
                    return [[la, lo] for lo, la in g]
            time.sleep(0.6 * (attempt + 1))
        except Exception:
            time.sleep(0.6 * (attempt + 1))
    return raw                                   # routing failed → straight line


def main():
    s4 = pd.read_parquet("stage4_stops.parquet")
    s4["makat"] = s4["makat"].astype(str)
    try:
        keep = set(pd.read_parquet("stage3_ridership.parquet")["makat"].astype(str))
        s4 = s4[s4["makat"].isin(keep)]
        print(f"Routing shapes for {len(s4)} routes (filtered to ridership makats)")
    except Exception as e:
        print(f"(no ridership filter: {e}) — doing all {len(s4)}")

    work = [(r["makat"], json.loads(r["geo"]) if isinstance(r["geo"], str) else [])
            for _, r in s4.iterrows()]

    shapes, done = {}, 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(road_shape, geo): mk for mk, geo in work}
        for fut in as_completed(futs):
            mk = futs[fut]
            done += 1
            try:
                shapes[mk] = fut.result()
            except Exception:
                shapes[mk] = None
            if done % 50 == 0:
                print(f"  {done}/{len(work)}")

    out = pd.DataFrame({
        "makat": list(shapes.keys()),
        "shape": [json.dumps(s, ensure_ascii=False) if s else "[]"
                  for s in shapes.values()],
    })
    out.to_parquet("stage5_shapes.parquet", index=False)
    record("shapes")
    ok = sum(1 for s in shapes.values() if s and len(s) > 2)
    print(f"\nSaved → stage5_shapes.parquet ({len(out)} routes, {ok} road-matched)")


if __name__ == "__main__":
    main()
