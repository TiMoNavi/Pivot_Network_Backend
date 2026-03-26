from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings


class PricingSourceError(RuntimeError):
    pass


AZURE_VM_SAMPLE_SKUS: dict[str, tuple[int, float]] = {
    "standard d2s v5": (2, 8.0),
    "standard f2s v2": (2, 4.0),
    "standard e2s v5": (2, 16.0),
}

AWS_VM_SAMPLE_TYPES: dict[str, tuple[int, float]] = {
    "m6i.large": (2, 8.0),
    "c6i.large": (2, 4.0),
    "r6i.large": (2, 16.0),
}

AWS_GPU_INSTANCE_MAP: dict[str, dict[str, Any]] = {
    "nvidia t4": {"instance_type": "g4dn.xlarge", "gpu_count": 1, "vcpu": 4, "memory_gib": 16.0},
    "nvidia a10": {"instance_type": "g5.xlarge", "gpu_count": 1, "vcpu": 4, "memory_gib": 16.0},
    "nvidia a10g": {"instance_type": "g5.xlarge", "gpu_count": 1, "vcpu": 4, "memory_gib": 16.0},
    "nvidia v100": {"instance_type": "p3.2xlarge", "gpu_count": 1, "vcpu": 8, "memory_gib": 61.0},
    "nvidia a100": {"instance_type": "p4d.24xlarge", "gpu_count": 8, "vcpu": 96, "memory_gib": 1152.0},
}


@dataclass
class ProviderRates:
    provider: str
    region: str
    cpu_price_usd_per_hour: float
    ram_price_usd_per_gib_hour: float
    gpu_price_usd_per_hour: dict[str, float]
    matched_samples: dict[str, Any]
    source_url: str


def _load_json(url: str, timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_memory_gib(value: str) -> float:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", value or "")
    return float(match.group(1)) if match else 0.0


def _solve_cpu_ram_rates(samples: list[tuple[float, float, float]]) -> tuple[float, float]:
    if len(samples) < 2:
        raise PricingSourceError("insufficient_samples_for_cpu_ram_rate")

    sum_xx = sum(cpu * cpu for cpu, _, _ in samples)
    sum_xy = sum(cpu * ram for cpu, ram, _ in samples)
    sum_yy = sum(ram * ram for _, ram, _ in samples)
    sum_xp = sum(cpu * price for cpu, _, price in samples)
    sum_yp = sum(ram * price for _, ram, price in samples)
    determinant = (sum_xx * sum_yy) - (sum_xy * sum_xy)
    if math.isclose(determinant, 0.0):
        raise PricingSourceError("cpu_ram_rate_matrix_singular")

    cpu_rate = ((sum_xp * sum_yy) - (sum_yp * sum_xy)) / determinant
    ram_rate = ((sum_yp * sum_xx) - (sum_xp * sum_xy)) / determinant
    if cpu_rate <= 0 or ram_rate <= 0:
        raise PricingSourceError("invalid_cpu_ram_rate_solution")
    return cpu_rate, ram_rate


def _extract_price_dimension_usd(term_block: dict[str, Any]) -> float:
    for dimension in term_block.get("priceDimensions", {}).values():
        usd = dimension.get("pricePerUnit", {}).get("USD")
        if usd is None:
            continue
        return float(usd)
    raise PricingSourceError("aws_price_dimension_missing")


def fetch_azure_vm_provider_rates(settings: Settings) -> ProviderRates:
    query = urllib.parse.quote(
        f"serviceName eq 'Virtual Machines' and armRegionName eq '{settings.PRICING_REFERENCE_AZURE_REGION}' and priceType eq 'Consumption'"
    )
    base_url = f"https://prices.azure.com/api/retail/prices?$filter={query}"
    items: list[dict[str, Any]] = []
    url = base_url
    matched: dict[str, dict[str, Any]] = {}
    max_pages = 12
    while url and max_pages > 0 and len(matched) < len(AZURE_VM_SAMPLE_SKUS):
        payload = _load_json(url)
        for item in payload.get("Items", []):
            arm_sku_name = _normalize_label(str(item.get("armSkuName") or item.get("skuName") or ""))
            if arm_sku_name in AZURE_VM_SAMPLE_SKUS and arm_sku_name not in matched:
                matched[arm_sku_name] = {
                    "retailPrice": float(item.get("retailPrice") or item.get("unitPrice") or 0.0),
                    "armSkuName": item.get("armSkuName") or item.get("skuName"),
                }
                items.append(item)
        url = payload.get("NextPageLink")
        max_pages -= 1

    if len(matched) < 2:
        raise PricingSourceError("azure_vm_samples_missing")

    sample_rows = []
    for sku_name, (vcpu, memory_gib) in AZURE_VM_SAMPLE_SKUS.items():
        if sku_name not in matched:
            continue
        sample_rows.append((float(vcpu), memory_gib, float(matched[sku_name]["retailPrice"])))
    cpu_rate, ram_rate = _solve_cpu_ram_rates(sample_rows)
    return ProviderRates(
        provider="azure",
        region=settings.PRICING_REFERENCE_AZURE_REGION,
        cpu_price_usd_per_hour=cpu_rate,
        ram_price_usd_per_gib_hour=ram_rate,
        gpu_price_usd_per_hour={},
        matched_samples=matched,
        source_url=base_url,
    )


def fetch_aws_ec2_provider_rates(settings: Settings) -> ProviderRates:
    source_url = (
        f"https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/"
        f"{settings.PRICING_REFERENCE_AWS_REGION}/index.json"
    )
    payload = _load_json(source_url, timeout=120)
    products = payload.get("products", {})
    terms = payload.get("terms", {}).get("OnDemand", {})

    matched_vm_samples: dict[str, dict[str, Any]] = {}
    matched_gpu_samples: dict[str, dict[str, Any]] = {}

    for sku, product in products.items():
        attributes = product.get("attributes", {})
        instance_type = str(attributes.get("instanceType") or "")
        if attributes.get("operatingSystem") != "Linux":
            continue
        if attributes.get("tenancy") != "Shared":
            continue
        if str(attributes.get("preInstalledSw") or "NA") != "NA":
            continue
        if product.get("productFamily") != "Compute Instance":
            continue
        term_block = next(iter(terms.get(sku, {}).values()), None)
        if term_block is None:
            continue
        try:
            hourly_price = _extract_price_dimension_usd(term_block)
        except PricingSourceError:
            continue

        if instance_type in AWS_VM_SAMPLE_TYPES and instance_type not in matched_vm_samples:
            matched_vm_samples[instance_type] = {
                "hourly_price": hourly_price,
                "vcpu": float(AWS_VM_SAMPLE_TYPES[instance_type][0]),
                "memory_gib": float(AWS_VM_SAMPLE_TYPES[instance_type][1]),
            }

        for gpu_model, spec in AWS_GPU_INSTANCE_MAP.items():
            if spec["instance_type"] == instance_type and gpu_model not in matched_gpu_samples:
                matched_gpu_samples[gpu_model] = {
                    "hourly_price": hourly_price,
                    "vcpu": float(spec["vcpu"]),
                    "memory_gib": float(spec["memory_gib"]),
                    "gpu_count": int(spec["gpu_count"]),
                    "instance_type": instance_type,
                }

    if len(matched_vm_samples) < 2:
        raise PricingSourceError("aws_vm_samples_missing")

    cpu_rate, ram_rate = _solve_cpu_ram_rates(
        [
            (sample["vcpu"], sample["memory_gib"], sample["hourly_price"])
            for sample in matched_vm_samples.values()
        ]
    )

    gpu_rates: dict[str, float] = {}
    for gpu_model, sample in matched_gpu_samples.items():
        residual = sample["hourly_price"] - (cpu_rate * sample["vcpu"]) - (ram_rate * sample["memory_gib"])
        if residual > 0:
            gpu_rates[gpu_model] = residual / max(sample["gpu_count"], 1)

    return ProviderRates(
        provider="aws",
        region=settings.PRICING_REFERENCE_AWS_REGION,
        cpu_price_usd_per_hour=cpu_rate,
        ram_price_usd_per_gib_hour=ram_rate,
        gpu_price_usd_per_hour=gpu_rates,
        matched_samples={"vm": matched_vm_samples, "gpu": matched_gpu_samples},
        source_url=source_url,
    )
