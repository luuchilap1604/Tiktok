"""
TikTok Vietnam Top Comments Dashboard - FastAPI Backend

Serves the dashboard UI and crawled data.
Scheduler is integrated into FastAPI lifespan (runs in same process).
"""

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from glob import glob
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Allow importing TikTokApi from parent dir (local dev)
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Scheduler ──────────────────────────────────────────────────────────────

async def crawl_job():
    """Called by APScheduler every 6h."""
    try:
        from crawler import run as run_crawler
        ms_token = os.environ.get("TIKTOK_MS_TOKEN")
        tokens = [ms_token] if ms_token else None
        logger.info("[Scheduler] Starting scheduled crawl...")
        await run_crawler(ms_tokens=tokens)
        logger.info("[Scheduler] Crawl complete.")
    except Exception as e:
        logger.error(f"[Scheduler] Crawl failed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        crawl_job,
        CronTrigger(hour="0,6,12,18", minute=0, timezone="Asia/Ho_Chi_Minh"),
        id="crawl_every_6h",
        name="Crawl every 6h",
    )
    scheduler.start()
    logger.info("[Scheduler] Started — jobs at 0h/6h/12h/18h (VN time)")
    yield
    scheduler.shutdown()
    logger.info("[Scheduler] Stopped.")


# ── App ────────────────────────────────────────────────────────────────────

app = FastAPI(title="TikTok VN Top Comments Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ── Data helpers ───────────────────────────────────────────────────────────

def load_latest() -> dict | None:
    latest_path = DATA_DIR / "latest.json"
    if latest_path.exists():
        with open(latest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def list_snapshots() -> list[dict]:
    snapshots = []
    for filepath in sorted(glob(str(DATA_DIR / "*.json")), reverse=True):
        filename = os.path.basename(filepath)
        if filename == "latest.json":
            continue
        name = filename.replace(".json", "")
        parts = name.split("_")
        if len(parts) == 2:
            time_str = parts[1]
            label_time = f"{time_str[:2]}:{time_str[2:]}" if len(time_str) == 4 else time_str
            snapshots.append({
                "filename": filename,
                "date": parts[0],
                "period": parts[1],
                "label": f"{parts[0]} - {label_time}",
            })
    return snapshots


def load_snapshot(filename: str) -> dict | None:
    filepath = DATA_DIR / filename
    if filepath.exists() and filepath.suffix == ".json":
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, snapshot: str | None = None):
    snapshots = list_snapshots()
    data = load_snapshot(snapshot) if snapshot else load_latest()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "data": data,
            "snapshots": snapshots,
            "selected_snapshot": snapshot,
        },
    )


@app.get("/api/latest")
async def api_latest():
    data = load_latest()
    if data is None:
        return {"error": "No data yet. Waiting for first scheduled crawl."}
    return data


@app.get("/api/snapshots")
async def api_snapshots():
    return list_snapshots()


@app.get("/api/snapshot/{filename}")
async def api_snapshot(filename: str):
    data = load_snapshot(filename)
    if data is None:
        return {"error": "Snapshot not found."}
    return data


@app.post("/api/crawl")
async def trigger_crawl():
    """Manually trigger a crawl (for testing)."""
    import asyncio
    asyncio.create_task(crawl_job())
    return {"status": "crawl started"}
