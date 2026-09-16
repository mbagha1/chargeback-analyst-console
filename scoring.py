"""
Evidence scoring and confidence tier calculations.

Design notes
------------
Evidence score is a plain proportion of requirements satisfied/partial.

Confidence is a DIFFERENT axis from the recommendation direction. The
original implementation used `evidence_score in (0, 100)` to mean
"HIGH confidence," which meant a case where the merchant satisfied
ZERO requirements displayed as "HIGH confidence" — a reviewer reading
only the metrics row would misread that as a strong case, when it's
actually a strong case for the *opposite* outcome (accept liability).

Confidence here means "how sure are we in this evidence read," gated
by whether the model itself raised any human_flags — a flagged case is
never allowed to display as HIGH confidence, regardless of score.
"""

from __future__ import annotations


def compute_evidence_score(requirements_met: int, requirements_partial: int, total_requirements: int) -> int:
    if total_requirements <= 0:
        return 0
    raw = (requirements_met + requirements_partial * 0.5) / total_requirements
    return round(raw * 100)


def compute_confidence(evidence_score: int, human_flags: list[str]) -> str:
    if evidence_score >= 90 or evidence_score <= 10:
        return "MEDIUM — flagged for review" if human_flags else "HIGH"
    if evidence_score >= 60 or evidence_score <= 30:
        return "LOW — flagged for review" if human_flags else "MEDIUM"
    return "LOW — flagged for review" if human_flags else "LOW"


def requires_second_reviewer(recommendation: str, evidence_score: int, human_flags: list[str]) -> bool:
    """Four-eyes gate: any case the AI flagged, or any 'represent' call
    resting on weak evidence, must clear a second reviewer before the
    audit report can be exported."""
    if human_flags:
        return True
    if recommendation == "represent" and evidence_score < 60:
        return True
    return False