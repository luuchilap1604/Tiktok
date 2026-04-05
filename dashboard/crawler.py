"""
TikTok Vietnam Trending Comments Crawler

Crawls trending videos in Vietnam and collects top comments by likes.
"""

import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone

# Add parent directory to path so we can import TikTokApi
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from TikTokApi import TikTokApi

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
TRENDING_VIDEO_COUNT = 120
MAX_FILTERED_VIDEOS = 30
RECENT_DAYS = 3
COMMENTS_PER_VIDEO = 50
TOP_N = 10
VIDEO_MIN_LIKES = 10_000
COMMENT_MIN_LIKES = 5_000


def is_recent_video(video_dict: dict, max_age_days: int = RECENT_DAYS) -> bool:
    """Return True when video createTime is within max_age_days."""
    create_time = video_dict.get("createTime")
    if create_time is None:
        return False

    try:
        ts = int(create_time)
    except (TypeError, ValueError):
        return False

    now_ts = int(datetime.now(timezone.utc).timestamp())
    return now_ts - ts <= max_age_days * 24 * 60 * 60


def is_vietnam_video(video_dict: dict) -> bool:
    """Best-effort Vietnam filter based on region hints in the payload."""
    candidates = [
        video_dict.get("region"),
        video_dict.get("locationCreated"),
        video_dict.get("author", {}).get("region"),
    ]
    normalized = {str(c).strip().upper() for c in candidates if c}

    # Many payloads do not expose region directly. If no hint exists,
    # keep the video because session params already force VN region.
    if not normalized:
        return True
    return "VN" in normalized


def get_video_like_count(video_dict: dict) -> int:
    """Extract video like count from common TikTok payload fields."""
    stats = video_dict.get("stats", {}) or {}
    candidates = [
        stats.get("diggCount"),
        stats.get("likeCount"),
        video_dict.get("diggCount"),
        video_dict.get("likeCount"),
    ]
    for c in candidates:
        try:
            if c is not None:
                return int(c)
        except (TypeError, ValueError):
            continue
    return 0


async def crawl_top_comments(ms_tokens: list[str] | None = None) -> dict:
    """
    Crawl trending videos in Vietnam, collect comments,
    and return top 10 by likes.

    ms_tokens là optional — nếu không truyền, browser tự lấy token
    bằng cách vào tiktok.com như user bình thường (không cần đăng nhập).
    """
    all_comments = []
    videos_crawled = 0
    errors = []

    async with TikTokApi() as api:
        # Try multiple session strategies to improve reliability on cloud hosts.
        browser_hint = os.getenv("TIKTOK_BROWSER", "chromium")
        strategies = [
            {"browser": browser_hint, "sleep_after": 5},
            {"browser": "chromium", "sleep_after": 8},
            {"browser": "webkit", "sleep_after": 8},
        ]

        session_created = False
        session_errors = []
        for s in strategies:
            try:
                await api.create_sessions(
                    num_sessions=len(ms_tokens) if ms_tokens else 1,
                    ms_tokens=ms_tokens or None,   # None → tự lấy token từ browser
                    headless=True,
                    browser=s["browser"],
                    sleep_after=s["sleep_after"],
                    timeout=45000,
                    allow_partial_sessions=True,
                    min_sessions=1,
                )
                session_created = True
                print(f"[Crawler] Session created with browser={s['browser']}")
                break
            except Exception as e:
                msg = f"session strategy failed ({s['browser']}): {e}"
                print(f"[Crawler] {msg}")
                session_errors.append(msg)

        if not session_created:
            return {
                "crawled_at": datetime.now(timezone.utc).isoformat(),
                "period": f"{datetime.now(timezone.utc).hour:02d}00",
                "videos_crawled": 0,
                "total_comments_found": 0,
                "errors": session_errors or ["Failed to create any valid session"],
                "top_comments": [],
            }

        # Override region to Vietnam
        for session in api.sessions:
            session.params["region"] = "VN"
            session.params["app_language"] = "vi-VN"
            session.params["browser_language"] = "vi-VN"
            session.params["language"] = "vi-VN"

        print(
            f"[Crawler] Fetching up to {TRENDING_VIDEO_COUNT} trending candidates (VN), "
            f"keeping max {MAX_FILTERED_VIDEOS} videos from last {RECENT_DAYS} days, "
            f"video likes >= {VIDEO_MIN_LIKES}, comment likes >= {COMMENT_MIN_LIKES}..."
        )

        try:
            async for video in api.trending.videos(count=TRENDING_VIDEO_COUNT):
                video_payload = video.as_dict or {}
                if not is_recent_video(video_payload, max_age_days=RECENT_DAYS):
                    continue
                if not is_vietnam_video(video_payload):
                    continue
                if get_video_like_count(video_payload) < VIDEO_MIN_LIKES:
                    continue

                video_id = video.id
                video_author = getattr(video.author, "username", "unknown") if video.author else "unknown"
                video_desc = video_payload.get("desc", "")[:100]
                videos_crawled += 1

                print(f"  [{videos_crawled}/{MAX_FILTERED_VIDEOS}] Video {video_id} by @{video_author}")

                try:
                    comment_count = 0
                    async for comment in video.comments(count=COMMENTS_PER_VIDEO):
                        if int(comment.likes_count or 0) < COMMENT_MIN_LIKES:
                            continue
                        all_comments.append({
                            "comment_id": comment.id,
                            "text": comment.text,
                            "likes": comment.likes_count,
                            "author_username": comment.author.username if comment.author else "unknown",
                            "author_uid": comment.as_dict.get("user", {}).get("uid", ""),
                            "video_id": video_id,
                            "video_author": video_author,
                            "video_desc": video_desc,
                        })
                        comment_count += 1
                    print(f"    -> {comment_count} comments collected")
                except Exception as e:
                    err_msg = f"Error fetching comments for video {video_id}: {e}"
                    print(f"    -> {err_msg}")
                    errors.append(err_msg)

                # Random delay giữa các video để tránh rate limiting
                await asyncio.sleep(random.uniform(2, 5))

                if videos_crawled >= MAX_FILTERED_VIDEOS:
                    break

        except Exception as e:
            err_msg = f"Error fetching trending videos: {e}"
            print(f"[Crawler] {err_msg}")
            errors.extend(session_errors)
            errors.append(err_msg)

    # Sort by likes descending, take top N
    all_comments.sort(key=lambda c: c["likes"], reverse=True)
    top_comments = all_comments[:TOP_N]

    now = datetime.now(timezone.utc)
    crawled_at = now.isoformat()

    # Update history BEFORE computing deltas (so current run is recorded)
    from history import update as history_update, get_delta
    history_update(all_comments, crawled_at)

    # Attach delta to each top comment
    for c in top_comments:
        delta = get_delta(c["comment_id"], c["likes"], hours=6)
        c["delta_likes"] = delta["delta_likes"]
        c["delta_pct"] = delta["delta_pct"]
        c["delta_period"] = delta["period_label"]

    result = {
        "crawled_at": crawled_at,
        "period": f"{now.hour:02d}00",
        "videos_crawled": videos_crawled,
        "total_comments_found": len(all_comments),
        "errors": errors,
        "top_comments": top_comments,
    }

    return result


def save_result(result: dict) -> str:
    """Save crawl result to JSON file in data/ directory."""
    os.makedirs(DATA_DIR, exist_ok=True)

    crawled_at = datetime.fromisoformat(result["crawled_at"])
    date_str = crawled_at.strftime("%Y-%m-%d")
    period = result["period"]
    filename = f"{date_str}_{period}.json"
    filepath = os.path.join(DATA_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Also save as latest.json for quick access
    latest_path = os.path.join(DATA_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[Crawler] Saved to {filepath}")
    return filepath


async def run(ms_tokens: list[str] | None = None):
    """Main entry point for the crawler."""
    print(f"[Crawler] Starting at {datetime.now(timezone.utc).isoformat()}")
    result = await crawl_top_comments(ms_tokens)
    filepath = save_result(result)
    print(
        f"[Crawler] Done. "
        f"{result['videos_crawled']} videos, "
        f"{result['total_comments_found']} comments, "
        f"top {len(result['top_comments'])} saved to {filepath}"
    )
    return result


if __name__ == "__main__":
    # Usage:
    #   python crawler.py            ← tự lấy token từ browser
    #   python crawler.py <token>    ← dùng token có sẵn
    tokens = [sys.argv[1]] if len(sys.argv) > 1 else None
    asyncio.run(run(ms_tokens=tokens))
