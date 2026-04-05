"""
Manual crawl-and-upload helper.

Usage:
  python dashboard/manual_sync.py \
      --base-url https://your-app.up.railway.app \
      --upload-key <UPLOAD_API_KEY>

Optional:
  --ms-token <token>
  --snapshot-only   (crawl locally but do not upload)
"""

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR.parent))

from crawler import run as run_crawler


def post_json(url: str, payload: dict, upload_key: str) -> tuple[int, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Upload-Key": upload_key,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.getcode(), r.read().decode("utf-8", errors="ignore")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual local crawl then upload latest result")
    parser.add_argument("--base-url", required=True, help="Dashboard base URL, e.g. https://xxx.up.railway.app")
    parser.add_argument("--upload-key", default=os.environ.get("UPLOAD_API_KEY", ""), help="Upload key for /api/upload-latest")
    parser.add_argument("--ms-token", default=os.environ.get("TIKTOK_MS_TOKEN", ""), help="TikTok ms token (optional)")
    parser.add_argument("--snapshot-only", action="store_true", help="Do not upload, only crawl locally")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    tokens = [args.ms_token] if args.ms_token else None
    result = asyncio.run(run_crawler(ms_tokens=tokens))

    print(
        "Local crawl summary:",
        {
            "videos_crawled": result.get("videos_crawled"),
            "total_comments_found": result.get("total_comments_found"),
            "top_comments": len(result.get("top_comments", [])),
            "errors": len(result.get("errors", [])),
        },
    )

    if args.snapshot_only:
        print("Snapshot-only mode, upload skipped.")
        return 0

    if not args.upload_key:
        print("Upload key missing. Use --upload-key or set UPLOAD_API_KEY.")
        return 2

    base = args.base_url.rstrip("/")
    code, text = post_json(f"{base}/api/upload-latest", result, args.upload_key)
    print(f"Upload response: {code} {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
