from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.supply import ImageOffer
from backend_app.db.models.trade import AccessCode, BuyerOrder


class BuyerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_ready_offers(self) -> list[ImageOffer]:
        statement = (
            select(ImageOffer)
            .where(ImageOffer.offer_status == "offer_ready")
            .order_by(ImageOffer.updated_at.desc())
        )
        return list(self.session.scalars(statement))

    def get_offer(self, offer_id) -> ImageOffer | None:
        return self.session.scalar(select(ImageOffer).where(ImageOffer.id == offer_id))

    def create_order(self, **kwargs) -> BuyerOrder:
        order = BuyerOrder(**kwargs)
        self.session.add(order)
        self.session.flush()
        return order

    def create_access_code(self, **kwargs) -> AccessCode:
        code = AccessCode(**kwargs)
        self.session.add(code)
        self.session.flush()
        return code

    def get_order(self, order_id, buyer_user_id) -> BuyerOrder | None:
        statement = select(BuyerOrder).where(
            BuyerOrder.id == order_id,
            BuyerOrder.buyer_user_id == buyer_user_id,
        )
        return self.session.scalar(statement)

    def get_access_code(self, access_code: str, buyer_user_id) -> AccessCode | None:
        statement = select(AccessCode).where(
            AccessCode.access_code == access_code,
            AccessCode.buyer_user_id == buyer_user_id,
        )
        return self.session.scalar(statement)

    def list_orders(self, *, limit: int = 100, status: str | None = None) -> list[BuyerOrder]:
        statement = select(BuyerOrder)
        if status:
            statement = statement.where(BuyerOrder.order_status == status)
        statement = statement.order_by(BuyerOrder.updated_at.desc(), BuyerOrder.created_at.desc()).limit(limit)
        return list(self.session.scalars(statement))

    def list_expired_access_codes(
        self,
        *,
        now: datetime,
        limit: int = 100,
        statuses: tuple[str, ...] = ("issued",),
    ) -> list[AccessCode]:
        statement = (
            select(AccessCode)
            .where(
                AccessCode.status.in_(statuses),
                AccessCode.expires_at <= now,
            )
            .order_by(AccessCode.expires_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def get_access_code_by_id(self, access_code_id) -> AccessCode | None:
        return self.session.scalar(select(AccessCode).where(AccessCode.id == access_code_id))
