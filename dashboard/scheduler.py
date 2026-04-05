"""
Scheduler for TikTok Vietnam Top Comments Crawler

Runs the crawler at 6:00 AM and 6:00 PM (Asia/Ho_Chi_Minh timezone).
"""

import asyncio
import os
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crawler import run as run_crawler

# Read ms_token from environment variable
MS_TOKEN = os.environ.get("TIKTOK_MS_TOKEN", "")


def crawl_job():
    """Job wrapper to run the async crawler."""
    tokens = [MS_TOKEN] if MS_TOKEN else None
    print("[Scheduler] Starting crawl job...")
    asyncio.run(run_crawler(ms_tokens=tokens))
    print("[Scheduler] Crawl job completed.")


def main():
    scheduler = BlockingScheduler()

    # Mỗi 6 tiếng: 0h, 6h, 12h, 18h (Vietnam time)
    scheduler.add_job(
        crawl_job,
        CronTrigger(hour="0,6,12,18", minute=0, timezone="Asia/Ho_Chi_Minh"),
        id="crawl_every_6h",
        name="Crawl every 6h (0h/6h/12h/18h VN)",
    )

    print("[Scheduler] Started. Jobs scheduled:")
    print("  - 0:00 AM / 6:00 AM / 12:00 PM / 6:00 PM (Asia/Ho_Chi_Minh)")
    print("[Scheduler] Waiting for next job... (Ctrl+C to stop)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[Scheduler] Stopped.")


if __name__ == "__main__":
    main()
