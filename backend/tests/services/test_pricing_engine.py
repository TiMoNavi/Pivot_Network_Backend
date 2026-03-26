from datetime import UTC, datetime

from app.core.db import SessionLocal
from app.models.identity import User
from app.models.platform import ImageArtifact, ImageOffer, Node, ResourceRateCard
from app.services.pricing_engine import price_image_offer, refresh_resource_rate_card
from app.services.pricing_sources import (
    PricingSourceError,
    fetch_aws_ec2_provider_rates,
    fetch_azure_vm_provider_rates,
)


def test_fetch_azure_vm_provider_rates_parses_samples(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.pricing_sources._load_json",
        lambda url, timeout=60: {
            "Items": [
                {"armSkuName": "Standard D2s v5", "retailPrice": 0.1},
                {"armSkuName": "Standard F2s v2", "retailPrice": 0.08},
                {"armSkuName": "Standard E2s v5", "retailPrice": 0.12},
            ],
            "NextPageLink": None,
        },
    )

    rates = fetch_azure_vm_provider_rates(__import__("app.core.config", fromlist=["settings"]).settings)

    assert rates.provider == "azure"
    assert rates.cpu_price_usd_per_hour > 0
    assert rates.ram_price_usd_per_gib_hour > 0
    assert "standard d2s v5" in rates.matched_samples


def test_fetch_aws_ec2_provider_rates_parses_samples(monkeypatch) -> None:
    payload = {
        "products": {
            "sku-m6i": {"productFamily": "Compute Instance", "attributes": {"instanceType": "m6i.large", "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA"}},
            "sku-c6i": {"productFamily": "Compute Instance", "attributes": {"instanceType": "c6i.large", "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA"}},
            "sku-r6i": {"productFamily": "Compute Instance", "attributes": {"instanceType": "r6i.large", "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA"}},
            "sku-g4dn": {"productFamily": "Compute Instance", "attributes": {"instanceType": "g4dn.xlarge", "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA"}},
            "sku-g5": {"productFamily": "Compute Instance", "attributes": {"instanceType": "g5.xlarge", "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA"}},
            "sku-p3": {"productFamily": "Compute Instance", "attributes": {"instanceType": "p3.2xlarge", "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA"}},
            "sku-p4d": {"productFamily": "Compute Instance", "attributes": {"instanceType": "p4d.24xlarge", "operatingSystem": "Linux", "tenancy": "Shared", "preInstalledSw": "NA"}},
        },
        "terms": {
            "OnDemand": {
                "sku-m6i": {"term-m6i": {"priceDimensions": {"dim": {"pricePerUnit": {"USD": "0.12"}}}}},
                "sku-c6i": {"term-c6i": {"priceDimensions": {"dim": {"pricePerUnit": {"USD": "0.10"}}}}},
                "sku-r6i": {"term-r6i": {"priceDimensions": {"dim": {"pricePerUnit": {"USD": "0.14"}}}}},
                "sku-g4dn": {"term-g4dn": {"priceDimensions": {"dim": {"pricePerUnit": {"USD": "0.52"}}}}},
                "sku-g5": {"term-g5": {"priceDimensions": {"dim": {"pricePerUnit": {"USD": "1.00"}}}}},
                "sku-p3": {"term-p3": {"priceDimensions": {"dim": {"pricePerUnit": {"USD": "3.06"}}}}},
                "sku-p4d": {"term-p4d": {"priceDimensions": {"dim": {"pricePerUnit": {"USD": "32.77"}}}}},
            }
        },
    }
    monkeypatch.setattr("app.services.pricing_sources._load_json", lambda url, timeout=60: payload)

    rates = fetch_aws_ec2_provider_rates(__import__("app.core.config", fromlist=["settings"]).settings)

    assert rates.provider == "aws"
    assert rates.cpu_price_usd_per_hour > 0
    assert rates.ram_price_usd_per_gib_hour > 0
    assert rates.gpu_price_usd_per_hour["nvidia t4"] > 0


def test_refresh_resource_rate_card_marks_previous_card_stale_on_failure(monkeypatch) -> None:
    db = SessionLocal()
    try:
        previous = ResourceRateCard(
            status="active",
            effective_hour=datetime.now(UTC).replace(tzinfo=None),
            usd_cny_rate=7.2,
            cpu_price_usd_per_hour=0.03,
            ram_price_usd_per_gib_hour=0.004,
            gpu_price_usd_per_hour={},
            source_summary={},
        )
        db.add(previous)
        db.commit()
        monkeypatch.setattr("app.services.pricing_engine.fetch_azure_vm_provider_rates", lambda settings: (_ for _ in ()).throw(PricingSourceError("azure_failed")))
        monkeypatch.setattr("app.services.pricing_engine.fetch_aws_ec2_provider_rates", lambda settings: (_ for _ in ()).throw(PricingSourceError("aws_failed")))

        card = refresh_resource_rate_card(db)

        assert card is not None
        assert card.id == previous.id
        db.refresh(previous)
        assert previous.stale_at is not None
    finally:
        db.close()


def test_price_image_offer_blocks_unmapped_gpu() -> None:
    db = SessionLocal()
    try:
        user = User(email="gpu@example.com", password_hash="hash")
        db.add(user)
        db.flush()
        node = Node(
            seller_user_id=user.id,
            node_key="gpu-node",
            device_fingerprint="gpu-device",
            hostname="gpu-host",
            system="Linux",
            machine="x86_64",
            capabilities={"cpu_count_logical": 16, "memory_total_mb": 65536},
        )
        db.add(node)
        db.flush()
        image = ImageArtifact(
            seller_user_id=user.id,
            node_id=node.id,
            repository="seller/gpu-demo",
            tag="v1",
            digest="sha256:demo",
            registry="registry.example.com",
            status="uploaded",
        )
        db.add(image)
        db.flush()
        offer = ImageOffer(
            seller_user_id=user.id,
            node_id=node.id,
            image_artifact_id=image.id,
            repository=image.repository,
            tag=image.tag,
            digest=image.digest,
            runtime_image_ref="registry.example.com/seller/gpu-demo:v1",
            offer_status="draft",
            probe_status="completed",
            probe_measured_capabilities={"cpu_logical": 16, "memory_total_mb": 65536, "gpus": [{"model": "Unknown RTX", "count": 1}]},
        )
        db.add(offer)
        card = ResourceRateCard(
            status="active",
            effective_hour=datetime.now(UTC).replace(tzinfo=None),
            usd_cny_rate=7.2,
            cpu_price_usd_per_hour=0.03,
            ram_price_usd_per_gib_hour=0.004,
            gpu_price_usd_per_hour={"nvidia t4": 0.35},
            source_summary={},
        )
        db.add(card)
        db.commit()

        priced = price_image_offer(db, offer, card)

        assert priced.offer_status == "pricing_blocked"
        assert priced.pricing_error is not None
        assert "gpu_unmapped" in priced.pricing_error
    finally:
        db.close()
