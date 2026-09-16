"""
Builds the exportable audit report text.

Kept separate from the Streamlit UI so the report format is testable
without spinning up the app, and so the same builder can later back a
non-Streamlit export path (an API/webhook push to a case management
system) without duplicating formatting logic.
"""

from __future__ import annotations


def build_report(*, timestamp, app_version, ai_model, case, scheme, reason_code,
                  rules, evidence_files, requirements_met, total_requirements,
                  evidence_score, confidence, ai_recommendation, human_decision,
                  override_note, checklist, analyst, second_reviewer,
                  ruleset_hash, record_hash) -> str:

    override_block = (
        override_note.strip()
        if human_decision != ai_recommendation
        else "AI recommendation accepted — no override."
    )

    lines = [
        "=" * 80,
        "CHARGEBACK REPRESENTMENT — AUDIT WORKUP REPORT",
        "=" * 80,
        "",
        "GENERATION DETAILS",
        "-" * 18,
        f"Generated (UTC):   {timestamp}",
        f"Application:       Chargeback Representment Console v{app_version}",
        f"AI Model:          {ai_model}",
        f"Rule Set Hash:     {ruleset_hash}",
        f"Record Hash:       {record_hash}",
        "",
        "REVIEW CHAIN",
        "-" * 12,
        f"Primary Analyst:   {analyst}",
        f"Second Reviewer:   {second_reviewer or 'Not required for this case'}",
        "",
        "CASE IDENTIFICATION",
        "-" * 19,
        f"Case ID:           {case.get('case_id')}",
        f"Scheme:            {scheme.upper()}",
        f"Reason Code:       {reason_code}",
        f"Rule Source:       {rules.get('source', 'Not specified')}",
        f"Rule Effective:    {rules.get('effective_date', 'Not specified')}",
        "",
        "EVIDENCE SUMMARY",
        "-" * 16,
        f"Documents Provided: {len(evidence_files)}",
        f"Requirements Met:   {requirements_met}/{total_requirements}",
        f"Evidence Score:     {evidence_score}%",
        f"Confidence Level:   {confidence}",
        "",
        "AI RECOMMENDATION",
        "-" * 17,
        ai_recommendation,
        "",
        "HUMAN DECISION",
        "-" * 14,
        human_decision,
        "",
        "OVERRIDE JUSTIFICATION",
        "-" * 22,
        override_block,
        "",
        "RULE-BY-RULE ASSESSMENT",
        "-" * 24,
    ]

    for item in checklist:
        note = f"\n      Note:   {item['_note']}" if item.get("_note") else ""
        lines.append(
            f"\n[{item.get('status', 'unknown').upper()}] REQUIREMENT: {item.get('requirement')}"
            f"\n      Source: {item.get('source')}"
            f"\n      Quote:  \"{item.get('quote')}\"{note}"
        )

    lines += ["", "=" * 80]
    return "\n".join(lines)