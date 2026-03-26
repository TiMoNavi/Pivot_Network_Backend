import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.api.main import api_router
from app.core.db import engine
from app.core.config import REPO_ROOT, settings
from app.models import Base, ImageOffer
from app.core.db import SessionLocal
from app.services.pricing_engine import ensure_current_rate_card, refresh_all_image_offer_prices
from app.services.runtime_sessions import cleanup_expired_runtime_sessions
from app.services.usage_billing import process_due_usage_charges


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
    )
    shutdown_event = threading.Event()

    def has_image_offers() -> bool:
        db = SessionLocal()
        try:
            return bool(db.scalar(select(func.count()).select_from(ImageOffer)) or 0)
        finally:
            db.close()

    def runtime_session_reaper() -> None:
        while not shutdown_event.is_set():
            try:
                cleanup_expired_runtime_sessions()
            except Exception:
                pass
            shutdown_event.wait(15)

    def price_feed_refresher() -> None:
        while not shutdown_event.is_set():
            try:
                if has_image_offers():
                    db = SessionLocal()
                    try:
                        ensure_current_rate_card(db)
                    finally:
                        db.close()
            except Exception:
                pass
            shutdown_event.wait(settings.PRICING_REFRESH_INTERVAL_SECONDS)

    def offer_repricing_worker() -> None:
        while not shutdown_event.is_set():
            try:
                if has_image_offers():
                    db = SessionLocal()
                    try:
                        card = ensure_current_rate_card(db)
                        if card is not None:
                            refresh_all_image_offer_prices(db, rate_card=card)
                    finally:
                        db.close()
            except Exception:
                pass
            shutdown_event.wait(settings.OFFER_REPRICING_INTERVAL_SECONDS)

    def usage_billing_worker() -> None:
        while not shutdown_event.is_set():
            try:
                process_due_usage_charges()
            except Exception:
                pass
            shutdown_event.wait(settings.USAGE_BILLING_INTERVAL_SECONDS)

    @app.on_event("startup")
    def create_tables() -> None:
        Base.metadata.create_all(bind=engine)
        threading.Thread(target=runtime_session_reaper, daemon=True).start()
        threading.Thread(target=price_feed_refresher, daemon=True).start()
        threading.Thread(target=offer_repricing_worker, daemon=True).start()
        threading.Thread(target=usage_billing_worker, daemon=True).start()

    @app.on_event("shutdown")
    def stop_reaper() -> None:
        shutdown_event.set()

    app.include_router(api_router, prefix=settings.API_V1_STR)
    frontend_dir = REPO_ROOT / "frontend"
    if frontend_dir.exists():
        app.mount("/platform-ui", StaticFiles(directory=str(frontend_dir), html=True), name="platform-ui")
    return app


app = create_app()
