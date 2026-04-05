"""
Comment likes history store.

Tracks likes over time per comment_id so we can compute deltas
between crawl runs (e.g. +likes in last 12h / 24h).
"""

import json
import os
from datetime import datetime, timezone, timedelta

_DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
HISTORY_FILE = os.path.join(_DATA_DIR, "history.json")


def _load() -> dict:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(history: dict):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update(comments: list[dict], crawled_at: str):
    """
    Record the current likes count for each comment.
    comments: list of comment dicts with 'comment_id' and 'likes'.
    crawled_at: ISO timestamp string of this crawl.
    """
    history = _load()

    for c in comments:
        cid = c["comment_id"]
        if cid not in history:
            history[cid] = []
        history[cid].append({
            "ts": crawled_at,
            "likes": c["likes"],
        })
        # Keep only last 30 snapshots per comment to avoid file bloat
        history[cid] = history[cid][-30:]

    _save(history)


def get_delta(comment_id: str, current_likes: int, hours: int = 12) -> dict:
    """
    Returns delta likes and delta % vs the snapshot closest to `hours` ago.

    Returns:
        {
            "delta_likes": int | None,
            "delta_pct": float | None,
            "period_label": str,   e.g. "12h ago"
        }
    """
    history = _load()
    snapshots = history.get(comment_id, [])

    if len(snapshots) < 2:
        return {"delta_likes": None, "delta_pct": None, "period_label": f"{hours}h ago"}

    now = datetime.now(timezone.utc)
    target_time = now - timedelta(hours=hours)

    # Find the snapshot closest to `hours` ago (but not in the future)
    best = None
    best_diff = None
    for snap in snapshots[:-1]:  # exclude current
        try:
            ts = datetime.fromisoformat(snap["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts <= now:
                diff = abs((ts - target_time).total_seconds())
                if best_diff is None or diff < best_diff:
                    best = snap
                    best_diff = diff
        except Exception:
            continue

    if best is None:
        return {"delta_likes": None, "delta_pct": None, "period_label": f"{hours}h ago"}

    past_likes = best["likes"]
    delta_likes = current_likes - past_likes
    delta_pct = (delta_likes / past_likes * 100) if past_likes > 0 else None

    # Label: how long ago was that snapshot?
    try:
        snap_ts = datetime.fromisoformat(best["ts"])
        if snap_ts.tzinfo is None:
            snap_ts = snap_ts.replace(tzinfo=timezone.utc)
        hours_ago = (now - snap_ts).total_seconds() / 3600
        if hours_ago < 1:
            label = f"{int(hours_ago * 60)}m ago"
        elif hours_ago < 24:
            label = f"{hours_ago:.0f}h ago"
        else:
            label = f"{hours_ago / 24:.0f}d ago"
    except Exception:
        label = f"{hours}h ago"

    return {
        "delta_likes": delta_likes,
        "delta_pct": round(delta_pct, 1) if delta_pct is not None else None,
        "period_label": label,
    }
