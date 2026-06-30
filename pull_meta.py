"""Records when each pipeline stage last pulled from its source → data_meta.json.
Called at the end of every step script so the dashboard footer can show an
accurate 'last pulled' time (the parquet mtime is unreliable on Streamlit Cloud,
where it reflects the git-clone time rather than the actual fetch)."""

import json
import os
from datetime import datetime

_FILE = os.path.join(os.path.dirname(__file__), "data_meta.json")


def record(key, extra=None):
    meta = {}
    if os.path.exists(_FILE):
        try:
            with open(_FILE, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            meta = {}
    entry = {"pulled_at": datetime.now().isoformat(timespec="seconds")}
    if extra:
        entry.update(extra)
    meta[key] = entry
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
