import logging
import os
from collections.abc import Callable
from urllib.parse import urlparse

from clustering.service import cluster_cleaned_news
from database.session import SessionLocal, create_tables
from expansion.service import expand_from_timeline
from impact.service import analyze_impact
from ingestion.rss import fetch_rss_feed
from ingestion.service import insert_raw_news
from preprocessing.service import preprocess_and_store
from signal_detection.service import detect_and_store_signals
from timeline.service import build_timeline

logger = logging.getLogger(__name__)


def _infer_source(feed_url: str) -> str:
    host = urlparse(feed_url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown-source"


def _load_feed_urls() -> list[str]:
    raw = os.getenv("RSS_FEEDS", "").strip()
    if not raw:
        return []
    return [url.strip() for url in raw.split(",") if url.strip()]


def _run_step(name: str, fn: Callable[[], dict[str, int] | dict[str, int | str]]) -> dict[str, object]:
    logger.info("Starting %s", name)
    try:
        output = fn()
        logger.info("Completed %s: %s", name, output)
        return {"status": "ok", "result": output}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed %s", name)
        return {"status": "error", "error": str(exc)}


def run_full_pipeline() -> dict[str, object]:
    """
    Execute the full deterministic pipeline end-to-end.
    Order:
    1) ingestion
    2) preprocessing
    3) clustering
    4) timeline generation
    5) expansion
    6) impact analysis
    7) signal detection
    """
    create_tables()
    summary: dict[str, object] = {"status": "ok", "steps": {}}

    with SessionLocal() as db:
        def step1_ingestion() -> dict[str, int]:
            feed_urls = _load_feed_urls()
            if not feed_urls:
                logger.warning("No RSS feeds configured. Set RSS_FEEDS in .env")
                return {"feeds_processed": 0, "fetched_items": 0, "inserted": 0, "skipped_duplicates": 0}

            total_fetched = 0
            total_inserted = 0
            total_skipped = 0

            for feed_url in feed_urls:
                source = _infer_source(feed_url)
                entries = fetch_rss_feed(feed_url=feed_url, source=source)
                total_fetched += len(entries)
                inserted, skipped = insert_raw_news(db=db, items=entries)
                total_inserted += inserted
                total_skipped += skipped

            return {
                "feeds_processed": len(feed_urls),
                "fetched_items": total_fetched,
                "inserted": total_inserted,
                "skipped_duplicates": total_skipped,
            }

        def step2_preprocessing() -> dict[str, int]:
            return preprocess_and_store(db=db)

        def step3_clustering() -> dict[str, int]:
            return cluster_cleaned_news(db=db)

        def step4_timeline() -> dict[str, int | str]:
            return build_timeline(db=db)

        def step5_expansion() -> dict[str, int]:
            return expand_from_timeline(db=db)

        def step6_impact() -> dict[str, int]:
            return analyze_impact(db=db)

        def step7_signal() -> dict[str, int]:
            return detect_and_store_signals(db=db)

        steps: list[tuple[str, Callable[[], dict[str, int] | dict[str, int | str]]]] = [
            ("step_1_ingestion", step1_ingestion),
            ("step_2_preprocessing", step2_preprocessing),
            ("step_3_clustering", step3_clustering),
            ("step_4_timeline", step4_timeline),
            ("step_5_expansion", step5_expansion),
            ("step_6_impact", step6_impact),
            ("step_7_signal", step7_signal),
        ]

        for step_name, step_fn in steps:
            step_result = _run_step(step_name, step_fn)
            summary["steps"][step_name] = step_result
            if step_result["status"] == "error":
                summary["status"] = "error"
                break

    return summary

