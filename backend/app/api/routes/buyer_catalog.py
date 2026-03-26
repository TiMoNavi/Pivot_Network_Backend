from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.identity import User
from app.models.platform import BuyerWallet, ImageOffer, Node, WalletLedger
from app.schemas.platform import BuyerCatalogOfferResponse, BuyerWalletResponse, WalletLedgerResponse

router = APIRouter(prefix="/buyer")


def _serialize_wallet(wallet: BuyerWallet) -> BuyerWalletResponse:
    return BuyerWalletResponse(
        buyer_user_id=wallet.buyer_user_id,
        balance_cny_credits=wallet.balance_cny_credits,
        created_at=wallet.created_at,
        updated_at=wallet.updated_at,
    )


def _serialize_wallet_ledger(entry: WalletLedger) -> WalletLedgerResponse:
    return WalletLedgerResponse(
        id=entry.id,
        buyer_user_id=entry.buyer_user_id,
        session_id=entry.session_id,
        usage_charge_id=entry.usage_charge_id,
        entry_type=entry.entry_type,
        amount_delta_cny=entry.amount_delta_cny,
        balance_after=entry.balance_after,
        detail=entry.detail,
        created_at=entry.created_at,
    )


def _serialize_catalog_offer(offer: ImageOffer, node: Node | None) -> BuyerCatalogOfferResponse:
    return BuyerCatalogOfferResponse(
        offer_id=offer.id,
        seller_node_key=node.node_key if node else "",
        repository=offer.repository,
        tag=offer.tag,
        runtime_image_ref=offer.runtime_image_ref,
        offer_status=offer.offer_status,
        probe_status=offer.probe_status,
        current_billable_price_cny_per_hour=offer.current_billable_price_cny_per_hour,
        pricing_stale_at=offer.pricing_stale_at,
        probe_measured_capabilities=offer.probe_measured_capabilities,
    )


@router.get("/catalog/offers", response_model=list[BuyerCatalogOfferResponse])
def list_buyer_catalog_offers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BuyerCatalogOfferResponse]:
    offers = db.scalars(select(ImageOffer).where(ImageOffer.offer_status == "active").order_by(ImageOffer.id)).all()
    nodes = (
        {node.id: node for node in db.scalars(select(Node).where(Node.id.in_([offer.node_id for offer in offers]))).all()}
        if offers
        else {}
    )
    return [_serialize_catalog_offer(offer, nodes.get(offer.node_id)) for offer in offers]


@router.get("/catalog/offers/{offer_id}", response_model=BuyerCatalogOfferResponse)
def read_buyer_catalog_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerCatalogOfferResponse:
    offer = db.get(ImageOffer, offer_id)
    if offer is None or offer.offer_status != "active":
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")
    node = db.get(Node, offer.node_id)
    return _serialize_catalog_offer(offer, node)


@router.get("/wallet", response_model=BuyerWalletResponse)
def read_buyer_wallet(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerWalletResponse:
    wallet = db.scalar(select(BuyerWallet).where(BuyerWallet.buyer_user_id == current_user.id))
    if wallet is None:
        wallet = BuyerWallet(
            buyer_user_id=current_user.id,
            balance_cny_credits=settings.DEFAULT_TEST_BALANCE_CNY_CREDITS,
        )
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return _serialize_wallet(wallet)


@router.get("/wallet/ledger", response_model=list[WalletLedgerResponse])
def read_buyer_wallet_ledger(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WalletLedgerResponse]:
    entries = db.scalars(
        select(WalletLedger).where(WalletLedger.buyer_user_id == current_user.id).order_by(WalletLedger.id.desc()).limit(200)
    ).all()
    return [_serialize_wallet_ledger(entry) for entry in entries]
