"""Pure-function tests for vendor_search filtering, ranking, and helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from db.collections.common import MetadataUpdatedOnly
from db.collections.vendor_org_relation import (
    VendorOrgPricingInsights,
    VendorOrgRelation,
    VendorOrgRelationMetrics,
    VendorOrgRiskInsights,
)
from db.collections.vendor_product import VendorProduct, VendorProductPricing
from procu_forge_buyer.subagents.vendor_search.schema import VendorOffer
from procu_forge_buyer.subagents.vendor_search.tools import (
    _build_offer,
    _days_until,
    _filter_candidates,
    _rank_key,
    _summarize_relation,
)


def _make_product(
    *,
    id: str = "vp-1",
    vendor_id: str = "v-1",
    unit_price: float = 100.0,
    currency: str = "USD",
    minimum_order_qty: int = 1,
    lead_time_days: int = 5,
    contracted: bool = False,
    availability_status: str = "in_stock",
) -> VendorProduct:
    return VendorProduct(
        id=id,
        vendorId=vendor_id,
        productId="p-1",
        vendorSku=f"sku-{id}",
        unit="piece",
        pricing=VendorProductPricing(
            currency=currency,
            unitPrice=unit_price,
            minimumOrderQty=minimum_order_qty,
        ),
        leadTimeDays=lead_time_days,
        contracted=contracted,
        availabilityStatus=availability_status,
        active=True,
        metadata=MetadataUpdatedOnly(),
    )


def _make_relation(
    *,
    vendor_id: str = "v-1",
    preferred: bool = False,
    strength: float | None = 5.0,
) -> VendorOrgRelation:
    return VendorOrgRelation(
        id=f"rel-{vendor_id}",
        organizationId="org-1",
        vendorId=vendor_id,
        relationshipStatus="active",
        relationshipStrength=strength,
        preferredVendor=preferred,
        metrics=VendorOrgRelationMetrics(totalOrders=1, totalSpend=1000.0),
        pricingInsights=VendorOrgPricingInsights(usuallyOffersDiscount=True),
        riskInsights=VendorOrgRiskInsights(riskLevel="low"),
        active=True,
        metadata=MetadataUpdatedOnly(),
    )


def _offer_from(item: VendorProduct, *, relation: VendorOrgRelation | None = None) -> VendorOffer:
    return _build_offer(item, request_currency="USD", relation=relation)


# ---------------------------------------------------------------------------
# _days_until
# ---------------------------------------------------------------------------

def test_days_until_returns_positive_for_future_date():
    target = (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()
    assert _days_until(target) == 7


def test_days_until_returns_negative_for_past_date():
    target = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
    assert _days_until(target) == -2


@pytest.mark.parametrize("raw", [None, "", "not-a-date", "2026-13-99"])
def test_days_until_returns_none_for_invalid(raw):
    assert _days_until(raw) is None


# ---------------------------------------------------------------------------
# _filter_candidates
# ---------------------------------------------------------------------------

def test_filter_drops_unavailable_vendors():
    items = [
        _make_product(id="ok", availability_status="in_stock"),
        _make_product(id="limited", availability_status="limited"),
        _make_product(id="oos", availability_status="out_of_stock"),
        _make_product(id="dead", availability_status="discontinued"),
    ]
    kept, counts = _filter_candidates(items, requested_quantity=10, days_until_required=30)
    assert [k.id for k in kept] == ["ok", "limited"]
    assert counts == {"availability": 2, "moq": 0, "leadTime": 0}


def test_filter_drops_moq_above_quantity():
    items = [
        _make_product(id="ok", minimum_order_qty=5),
        _make_product(id="too-high", minimum_order_qty=11),
    ]
    kept, counts = _filter_candidates(items, requested_quantity=10, days_until_required=30)
    assert [k.id for k in kept] == ["ok"]
    assert counts["moq"] == 1


def test_filter_drops_slow_lead_time_when_deadline_known():
    items = [
        _make_product(id="fast", lead_time_days=3),
        _make_product(id="slow", lead_time_days=15),
    ]
    kept, counts = _filter_candidates(items, requested_quantity=1, days_until_required=7)
    assert [k.id for k in kept] == ["fast"]
    assert counts["leadTime"] == 1


def test_filter_skips_lead_time_when_deadline_unknown():
    items = [
        _make_product(id="slow", lead_time_days=99),
    ]
    kept, counts = _filter_candidates(items, requested_quantity=1, days_until_required=None)
    assert [k.id for k in kept] == ["slow"]
    assert counts["leadTime"] == 0


def test_filter_short_circuits_in_order():
    # availability fails first, never counted against moq even if both would fail.
    items = [_make_product(id="bad", availability_status="out_of_stock", minimum_order_qty=999)]
    _, counts = _filter_candidates(items, requested_quantity=1, days_until_required=30)
    assert counts == {"availability": 1, "moq": 0, "leadTime": 0}


# ---------------------------------------------------------------------------
# _build_offer + _summarize_relation
# ---------------------------------------------------------------------------

def test_build_offer_flags_currency_mismatch():
    item = _make_product(currency="EUR")
    offer = _offer_from(item)
    assert offer.currency_matches_request is False


def test_build_offer_matches_currency_case_insensitively():
    item = _make_product(currency="usd")
    offer = _offer_from(item)
    assert offer.currency_matches_request is True


def test_build_offer_surfaces_relation_summary():
    item = _make_product(vendor_id="v-9")
    relation = _make_relation(vendor_id="v-9", preferred=True, strength=8.5)
    offer = _offer_from(item, relation=relation)
    assert offer.vendor_relation is not None
    assert offer.vendor_relation.preferred_vendor is True
    assert offer.vendor_relation.relationship_strength == 8.5
    assert offer.vendor_relation.risk_level == "low"


def test_build_offer_without_relation_yields_none():
    offer = _offer_from(_make_product(), relation=None)
    assert offer.vendor_relation is None


def test_summarize_relation_handles_missing_subblocks():
    relation = VendorOrgRelation(
        id="rel-x",
        organizationId="org-1",
        vendorId="v-x",
        relationshipStatus="active",
        preferredVendor=False,
        metrics=VendorOrgRelationMetrics(totalOrders=0, totalSpend=0.0),
        active=True,
        metadata=MetadataUpdatedOnly(),
    )
    summary = _summarize_relation(relation)
    assert summary is not None
    assert summary.risk_level is None
    assert summary.usually_offers_discount is None


# ---------------------------------------------------------------------------
# _rank_key
# ---------------------------------------------------------------------------

def _offer(
    *,
    id: str,
    vendor_id: str = "v-1",
    contracted: bool = False,
    preferred: bool = False,
    strength: float | None = None,
    lead_time: int = 7,
    unit_price: float = 100.0,
) -> VendorOffer:
    item = _make_product(
        id=id, vendor_id=vendor_id, lead_time_days=lead_time,
        unit_price=unit_price, contracted=contracted,
    )
    relation = _make_relation(vendor_id=vendor_id, preferred=preferred, strength=strength) if (preferred or strength is not None) else None
    return _offer_from(item, relation=relation)


def test_rank_contracted_beats_non_contracted():
    contracted = _offer(id="c", contracted=True)
    plain = _offer(id="p", contracted=False, preferred=True, strength=10.0)
    assert _rank_key(contracted) < _rank_key(plain)


def test_rank_preferred_beats_non_preferred_within_contracted():
    pref = _offer(id="pref", contracted=True, preferred=True, strength=1.0)
    plain = _offer(id="plain", contracted=True, preferred=False, strength=9.0)
    assert _rank_key(pref) < _rank_key(plain)


def test_rank_uses_strength_to_break_ties():
    high = _offer(id="hi", contracted=True, preferred=True, strength=9.0)
    low = _offer(id="lo", contracted=True, preferred=True, strength=2.0)
    assert _rank_key(high) < _rank_key(low)


def test_rank_falls_back_to_lead_time_then_price():
    fast = _offer(id="a", lead_time=3, unit_price=200.0)
    slow_cheap = _offer(id="b", lead_time=8, unit_price=50.0)
    assert _rank_key(fast) < _rank_key(slow_cheap)
    cheap = _offer(id="c", lead_time=5, unit_price=50.0)
    pricey = _offer(id="d", lead_time=5, unit_price=200.0)
    assert _rank_key(cheap) < _rank_key(pricey)


def test_rank_treats_missing_relation_as_zero_strength():
    # None strength must coalesce to 0 in the rank key so the offer isn't crash-sorted.
    relationless = _offer(id="r1", lead_time=3, unit_price=80.0)
    zero_strength = _offer(id="r2", strength=0.0, lead_time=3, unit_price=80.0)
    # Tied on every term except the stable id tiebreak.
    a, b = _rank_key(relationless), _rank_key(zero_strength)
    assert a[:-1] == b[:-1]


def test_rank_strength_wins_over_lead_time_among_non_contracted():
    # Relationship strength is intentionally weighted above lead time / price.
    weak_strong_relation = _offer(id="strong", strength=8.0, lead_time=9, unit_price=120.0)
    no_relation_fast = _offer(id="fast", lead_time=3, unit_price=80.0)
    assert _rank_key(weak_strong_relation) < _rank_key(no_relation_fast)


# ---------------------------------------------------------------------------
# Top-3 truncation (integration of sort + slice)
# ---------------------------------------------------------------------------

def test_top_three_truncation_after_sort():
    offers = [
        _offer(id="a", contracted=False, strength=1.0),
        _offer(id="b", contracted=True, preferred=False, strength=5.0),
        _offer(id="c", contracted=True, preferred=True, strength=9.0),
        _offer(id="d", contracted=True, preferred=True, strength=3.0),
        _offer(id="e", contracted=True, preferred=False, strength=8.0),
        _offer(id="f", contracted=False, strength=10.0),
    ]
    ranked = sorted(offers, key=_rank_key)
    top3 = [o.id for o in ranked[:3]]
    # Preferred+contracted go first (c then d), then contracted-only sorted by strength (e then b).
    assert top3 == ["c", "d", "e"]
