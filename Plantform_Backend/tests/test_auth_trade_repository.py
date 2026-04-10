from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend_app.db.base import Base
from backend_app.db import models  # noqa: F401
from backend_app.repositories.auth_repository import AuthRepository
from backend_app.repositories.trade_repository import TradeRepository
from backend_app.storage.memory_store import AccessGrantRecord, AuthSessionRecord, OrderRecord, UserRecord


def test_auth_and_trade_repositories_persist_records(tmp_path) -> None:
    db_path = tmp_path / "auth_trade_repository.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    now = datetime.now(UTC)
    with session_local() as db:
        auth_repository = AuthRepository(db)
        trade_repository = TradeRepository(db)

        user = UserRecord(
            id="user_test_1",
            email="buyer@example.com",
            display_name="Buyer One",
            password_salt="salt-1",
            password_hash="hash-1",
            role="buyer",
            status="active",
            created_at=now,
            updated_at=now,
        )
        auth_repository.save_user(user)
        auth_repository.save_auth_session(
            AuthSessionRecord(
                id="session_test_1",
                user_id=user.id,
                token="token-1",
                scope="api_access",
                expires_at=now + timedelta(hours=12),
                revoked_at=None,
                created_at=now,
            )
        )
        trade_repository.ensure_seed_offers()
        trade_repository.save_order(
            OrderRecord(
                id="order_test_1",
                buyer_user_id=user.id,
                offer_id="offer-medium-gpu",
                status="grant_issued",
                requested_duration_minutes=60,
                price_snapshot={"currency": "CNY", "hourly_price": 12.5},
                runtime_bundle_status="placeholder_pending",
                access_grant_id="grant_test_1",
                created_at=now,
                updated_at=now,
            )
        )
        trade_repository.save_access_grant(
            AccessGrantRecord(
                id="grant_test_1",
                buyer_user_id=user.id,
                order_id="order_test_1",
                runtime_session_id="runtime-1",
                status="issued",
                grant_type="placeholder",
                connect_material_payload={"download_relative_path": "generated/access-grants/grant_test_1.json"},
                issued_at=now,
                expires_at=now + timedelta(hours=12),
                activated_at=None,
                revoked_at=None,
            )
        )
        auth_repository.commit()
        trade_repository.commit()

    with session_local() as db:
        auth_repository = AuthRepository(db)
        trade_repository = TradeRepository(db)
        fetched_user = auth_repository.get_user_by_email("buyer@example.com")
        fetched_session = auth_repository.get_auth_session_by_token("token-1")
        offers = trade_repository.list_offers(status="listed")
        fetched_order = trade_repository.get_order("order_test_1")
        grants = trade_repository.list_active_access_grants("user_test_1", now=now)

    assert fetched_user is not None
    assert fetched_user.display_name == "Buyer One"
    assert fetched_session is not None
    assert fetched_session.user_id == "user_test_1"
    assert len(offers) >= 2
    assert fetched_order is not None
    assert fetched_order.access_grant_id == "grant_test_1"
    assert len(grants) == 1
