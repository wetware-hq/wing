"""Optional conjunctive policy evaluation for recorded L2 metrics (WP-D).

Default: all criteria ``skipped``. Policies are CLI opt-in and are not ``FLEET.toml`` gates.
"""

from __future__ import annotations

from typing import Any, Iterable


def evaluate_recorded(
    tier0: dict[str, Any],
    policies: Iterable[str] = (),
) -> dict[str, str]:
    """Return ``{criterion_id: pass|fail|skipped}`` for items 3, 5, 6."""
    active = set(policies)
    out = {
        "item_3_buried_anchors_zero": "skipped",
        "item_5_pose_agreement": "skipped",
        "item_6_complementarity_delta": "skipped",
    }
    if "buried-anchors-zero" in active:
        n = tier0.get("item_3_buried_anchor_contact_count")
        if n is None:
            out["item_3_buried_anchors_zero"] = "skipped"
        elif n == 0:
            out["item_3_buried_anchors_zero"] = "pass"
        else:
            out["item_3_buried_anchors_zero"] = "fail"
    return out


def policy_violations(policy_results: dict[str, str]) -> list[str]:
    return [k for k, v in policy_results.items() if v == "fail"]
