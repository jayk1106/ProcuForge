"""Tests for the relationship-aware anchor computation in the vendor quote agent.

Covers ``_compute_anchors``: floor (last_selling_price) and opening_price are
derived from vendor-org relation history + quantity tiers + a loyalty bump
for preferred long-term partners.
"""

from __future__ import annotations

from db.collections.common import MetadataUpdatedOnly
from db.collections.vendor_org_relation import (
    VendorOrgPricingInsights,
    VendorOrgRelation,
    VendorOrgRelationMetrics,
)
from procu_forge_vendor.subagents.quote.tools import (
    _DEFAULT_AVG_DISCOUNT_PCT,
    _OPENING_BUFFER_PCT,
    _compute_anchors,
)


def _make_relation(
    *,
    avg_disc: float | None = 10.0,
    rel_strength: float | None = None,
    preferred: bool = False,
) -> VendorOrgRelation:
    return VendorOrgRelation(
        id="rel-1",
        organization_id="org-1",
        vendor_id="vendor-1",
        relationship_status="active",
        relationship_strength=rel_strength,
        preferred_vendor=preferred,
        metrics=VendorOrgRelationMetrics(totalOrders=10, totalSpend=10000.0),
        pricing_insights=VendorOrgPricingInsights(averageDiscountPercent=avg_disc)
        if avg_disc is not None
        else None,
        active=True,
        metadata=MetadataUpdatedOnly(),
    )


def test_no_relation_uses_defaults():
    """New buyer: floor and opening derive from _DEFAULT_AVG_DISCOUNT_PCT."""
    anchors = _compute_anchors(listed_unit_price=1000.0, quantity=1, relation=None)
    # Floor = 1000 * (1 - 8/100) = 920
    assert anchors["last_selling_price"] == round(1000.0 * (1 - _DEFAULT_AVG_DISCOUNT_PCT / 100), 2)
    # Opening = 1000 * (1 - max(0, 8 - 5)/100) = 970
    expected_open_disc = max(0.0, _DEFAULT_AVG_DISCOUNT_PCT - _OPENING_BUFFER_PCT)
    assert anchors["opening_price"] == round(1000.0 * (1 - expected_open_disc / 100), 2)
    assert anchors["relation_summary"]["relation_present"] is False


def test_strong_preferred_relation_adds_loyalty_bump():
    """Preferred vendor with strength 10 gets the full +2pp loyalty extra at floor."""
    relation = _make_relation(avg_disc=10.0, rel_strength=10.0, preferred=True)
    anchors = _compute_anchors(listed_unit_price=1000.0, quantity=1, relation=relation)
    # loyalty_extra = min(2, (10-7)/3 * 2) = 2.0 → floor disc = 12, floor = 880
    assert anchors["last_selling_price"] == 880.0
    assert anchors["relation_summary"]["loyalty_extra_pct"] == 2.0


def test_preferred_but_weak_relation_no_loyalty_bump():
    """Preferred but strength <= 7 → no loyalty extra."""
    relation = _make_relation(avg_disc=10.0, rel_strength=7.0, preferred=True)
    anchors = _compute_anchors(listed_unit_price=1000.0, quantity=1, relation=relation)
    assert anchors["last_selling_price"] == 900.0  # 1000 * (1 - 10/100)
    assert anchors["relation_summary"]["loyalty_extra_pct"] == 0.0


def test_non_preferred_strong_relation_no_loyalty_bump():
    """Strength alone (without preferred=True) is not enough for the loyalty extra."""
    relation = _make_relation(avg_disc=10.0, rel_strength=10.0, preferred=False)
    anchors = _compute_anchors(listed_unit_price=1000.0, quantity=1, relation=relation)
    assert anchors["last_selling_price"] == 900.0
    assert anchors["relation_summary"]["loyalty_extra_pct"] == 0.0


def test_quantity_tier_widens_both_floor_and_opening():
    """Quantity >= 50 adds 10pp tier discount to both floor and opening."""
    relation = _make_relation(avg_disc=10.0, preferred=False)
    anchors = _compute_anchors(listed_unit_price=1000.0, quantity=50, relation=relation)
    # Floor disc = 10 + 0 + 10 = 20 → floor = 800
    assert anchors["last_selling_price"] == 800.0
    # Opening disc = max(0, 10 - 5) + 10 = 15 → opening = 850
    assert anchors["opening_price"] == 850.0
    assert anchors["relation_summary"]["qty_tier_pct"] == 10.0


def test_quantity_tier_mid_band():
    """Quantity in [10, 49] gets the 5pp tier discount."""
    relation = _make_relation(avg_disc=10.0, preferred=False)
    anchors = _compute_anchors(listed_unit_price=1000.0, quantity=10, relation=relation)
    # Floor = 1000 * (1 - (10 + 5)/100) = 850
    assert anchors["last_selling_price"] == 850.0
    # Opening = 1000 * (1 - (5 + 5)/100) = 900
    assert anchors["opening_price"] == 900.0


def test_opening_never_below_floor():
    """If avg_disc < buffer, opening would naively undercut floor — clamped to floor."""
    relation = _make_relation(avg_disc=2.0, preferred=False)
    anchors = _compute_anchors(listed_unit_price=1000.0, quantity=1, relation=relation)
    assert anchors["opening_price"] >= anchors["last_selling_price"]


def test_relation_summary_persists_inputs():
    relation = _make_relation(avg_disc=12.0, rel_strength=8.5, preferred=True)
    anchors = _compute_anchors(listed_unit_price=1000.0, quantity=10, relation=relation)
    summary = anchors["relation_summary"]
    assert summary["relation_present"] is True
    assert summary["avg_discount_pct"] == 12.0
    assert summary["relationship_strength"] == 8.5
    assert summary["preferred_vendor"] is True
    assert summary["qty_tier_pct"] == 5.0
