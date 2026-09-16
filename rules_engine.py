"""
Reconciles AI-returned checklist items against the authoritative rule
set, and provides a stable hash of the rule set in force for a given
decision.

Why reconciliation matters: the original app computed
`requirements_met` directly from whatever checklist the model
returned, with no check that the model actually addressed every
requirement in `rules["requirements"]`. If the model silently dropped
a requirement (common with smaller/faster models under time pressure),
the evidence score was computed against a shorter, easier list without
anyone knowing. Reconciling against the rule set closes that gap: a
requirement with no matching checklist entry is explicitly marked
missing, never just absent.

Why the rule-set hash matters: reason codes and requirements change
over time (scheme rule updates). Stamping the hash of the exact rule
content used for a decision into the audit record means a later change
to reason_codes.json can never retroactively obscure what was actually
applied when the decision was made.
"""

from __future__ import annotations
import hashlib
import json


def reconcile_checklist(checklist: list[dict], requirements: list[str]) -> list[dict]:
    by_requirement = {}
    for item in checklist:
        key = (item.get("requirement") or "").strip()
        by_requirement[key] = item

    reconciled = []
    for req in requirements:
        key = req.strip()
        item = by_requirement.get(key)
        if item is None:
            reconciled.append({
                "requirement": req,
                "status": "missing",
                "source": None,
                "quote": None,
                "_note": "Not returned by AI — auto-marked missing during reconciliation",
            })
        else:
            reconciled.append(dict(item))
    return reconciled


def hash_ruleset(rules: dict) -> str:
    payload = json.dumps(rules, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]