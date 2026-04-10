from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.supply import ImageArtifact, ImageOffer, NodeCapabilitySnapshot


class SupplyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_image_artifact(self, **kwargs) -> ImageArtifact:
        artifact = ImageArtifact(**kwargs)
        self.session.add(artifact)
        self.session.flush()
        return artifact

    def create_or_update_offer(self, artifact: ImageArtifact, **kwargs) -> ImageOffer:
        offer = self.session.scalar(select(ImageOffer).where(ImageOffer.image_artifact_id == artifact.id))
        if offer is None:
            offer = ImageOffer(image_artifact_id=artifact.id, **kwargs)
            self.session.add(offer)
            self.session.flush()
            return offer

        for key, value in kwargs.items():
            setattr(offer, key, value)
        self.session.add(offer)
        self.session.flush()
        return offer

    def add_capability_snapshot(self, **kwargs) -> NodeCapabilitySnapshot:
        snapshot = NodeCapabilitySnapshot(**kwargs)
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def list_artifacts_for_seller(self, seller_user_id: str) -> list[ImageArtifact]:
        statement = select(ImageArtifact).where(ImageArtifact.seller_user_id == seller_user_id).order_by(ImageArtifact.created_at.desc())
        return list(self.session.scalars(statement))

    def list_offers_for_seller(self, seller_user_id: str) -> list[ImageOffer]:
        statement = select(ImageOffer).where(ImageOffer.seller_user_id == seller_user_id).order_by(ImageOffer.updated_at.desc())
        return list(self.session.scalars(statement))
