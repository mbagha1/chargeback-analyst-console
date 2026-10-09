"""
Chargeback Representment — Analyst Console
============================================
Purpose:  Merchant risk assessment, evidence review, audit reporting
Design:   Professional, governed, auditable, export-ready
Features:
  - AI-powered case evaluation against scheme rules
  - Evidence document repository & review
  - Rule-by-rule compliance assessment
  - Human decision override — no mandatory justification blocks
  - Full audit trail with cryptographic hashing
  - Download report ALWAYS enabled
  - Portfolio metrics & history
"""
import streamlit as st
import json
import os
from datetime import datetime, timezone
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import ValidationError
from evidence_store import EVIDENCE
from schema import WorkupResult
from scoring import compute_evidence_score, compute_confidence
from rules_engine import reconcile_checklist, hash_ruleset
from report_builder import build_report
import audit_store

# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(
    page_title="Chargeback Representment — Analyst Console",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# PROFESSIONAL STYLING
# ============================================================
st.markdown("""
<style>
.stApp {
    background-color: #F7F8FA;
}
.block-container {
    max-width: 1300px;
    padding: 1.5rem 2rem;
}
h1, h2, h3 {
    color: #1D2129;
    font-weight: 600;
    margin-bottom: 0.5rem;
}
p, div {
    color: #4E5969;
    font-size: 0.95rem;
}
.audit-row {
    font-size: 0.85rem;
    color: #4E5969;
    background: #F9FAFB;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    border-left: 3px solid #0070F3;
    margin: 0.5rem 0 1rem 0;
}
div[data-testid="stMetric"] label {
    color: #86909C;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #1D2129;
    font-weight: 700;
    font-size: 1.4rem;
}
div[data-testid="stProgress"] > div > div {
    background-color: #0070F3;
    border-radius: 4px;
}
.stButton > button {
    background-color: #D64545;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    padding: 0.5rem 1rem;
}
.stButton > button:hover {
    background-color: #005ED6;
}
hr {
    border: none;
    border-top: 1px solid #E5E6EB;
    margin: 1.5rem 0;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# ENVIRONMENT & INITIALIZATION
# ============================================================
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
AI_MODEL = "gpt-4o-mini"
APPLICATION_VERSION = "2.2.0"

# ============================================================
# HEADER
# ============================================================
st.title("Chargeback Representment — Analyst Console")
st.caption("AI Workup | Evidence Review | Audit Reporting — Download Always Enabled")
tab_workup, tab_history = st.tabs(["Case Workup", "Audit History"])

# ============================================================
# TAB 1 — CASE WORKUP
# ============================================================
with tab_workup:

    # Validate API key before proceeding
    if not API_KEY or not API_KEY.strip():
        st.error("Configuration Error: OPENAI_API_KEY is missing or empty. Verify your .env file.")
        st.stop()
    client = OpenAI(api_key=API_KEY)

    # ============================================================
    # DATA LOADING WITH ERROR HANDLING
    # ============================================================
    @st.cache_data
    def load_json(path: str):
        """Load and parse JSON file with error handling."""
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            st.error(f"Data file not found: {path}")
            st.stop()
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON in {path}: {str(e)}")
            st.stop()

    CASES = load_json("cases.json")
    RULES = load_json("reason_codes.json")

    # ============================================================
    # SIDEBAR — CASE SELECTION
    # ============================================================
    with st.sidebar:
        st.header("Case Selection")
        analyst_name = st.text_input("Analyst Name (Optional)", placeholder="Enter your name")
        st.divider()
        selected_index = st.selectbox(
            "Select Case",
            options=range(len(CASES)),
            format_func=lambda idx: f"{CASES[idx].get('case_id')} | {CASES[idx].get('reason_code_label')}"
        )

    # ============================================================
    # LOAD SELECTED CASE
    # ============================================================
    current_case = CASES[selected_index]
    scheme = current_case.get("scheme", "visa").lower()
    reason_code = current_case.get("reason_code", "13.1")
    rule_key = f"{scheme}_{reason_code}"
    rules = RULES.get(rule_key, {
        "name": "Undefined Reason",
        "requirements": [],
        "source": "",
        "effective_date": ""
    })
    ruleset_hash = hash_ruleset(rules)
    evidence_files = current_case.get("merchant_evidence_documents", [])

    # ============================================================
    # EVIDENCE DISPLAY & ASSEMBLY
    # ============================================================
    evidence_payload = ""
    with st.expander("Evidence Documents", expanded=False):
        if not evidence_files:
            st.info("No evidence documents attached to this case.")
        elif not EVIDENCE:
            st.warning("Evidence store is empty. Verify evidence_store.py is configured.")
        else:
            for filename in evidence_files:
                content = EVIDENCE.get(filename, f"Content not found: {filename}")
                evidence_payload += f"\n--- {filename} ---\n{content}\n"
                st.markdown(f"**{filename}**")
                st.text(content)

    # ============================================================
    # RUN AI WORKUP — WITH IMPROVED ERROR FEEDBACK
    # ============================================================
    st.subheader("1. Generate Workup")
    if st.button("Run Full Analysis", use_container_width=True, type="primary"):

        # Pre-flight checks
        if not evidence_payload.strip():
            st.warning("No evidence content found. Proceeding with case details only.")

        with st.spinner("Evaluating evidence against scheme rules..."):
            try:
                response = client.chat.completions.create(
                    model=AI_MODEL,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": """You are a Merchant Risk Analyst evaluating chargeback evidence.
Evaluate each requirement separately against the evidence provided.
Return ONLY valid JSON matching this schema:
{
  "summary": "Brief one-paragraph summary of the case",
  "checklist": [
    {
      "requirement": "Exact requirement text from the rules",
      "status": "satisfied / partial / missing",
      "source": "Name of evidence document",
      "quote": "Exact quote from evidence"
    }
  ],
  "human_flags": ["Items needing human attention or manual review"],
  "recommendation": "represent / accept_liability / request_more_evidence",
  "rationale": "Clear professional explanation of recommendation"
}"""
                        },
                        {
                            "role": "user",
                            "content": f"""CASE DETAILS:
{json.dumps(current_case, indent=2)}

APPLICABLE RULES:
{json.dumps(rules, indent=2)}

EVIDENCE:
{evidence_payload}

Evaluate each requirement and return your assessment."""
                        }
                    ]
                )
                raw_content = response.choices[0].message.content

            except Exception as exc:
                st.error(f"AI Service Error: {type(exc).__name__} — {str(exc)}")
                st.stop()

            # Validate AI output against schema
            try:
                validated = WorkupResult.model_validate_json(raw_content)
                result = validated.model_dump()
            except ValidationError as exc:
                st.error("AI output validation failed. Review this case manually.")
                with st.expander("Validation Details"):
                    st.code(str(exc))
                st.stop()

        # ============================================================
        # PROCESS RESULTS
        # ============================================================
        checklist = reconcile_checklist(result.get("checklist", []), rules.get("requirements", []))
        human_flags = result.get("human_flags", [])

        total_requirements = len(rules.get("requirements", []))
        requirements_met = sum(1 for i in checklist if i.get("status") == "satisfied")
        requirements_partial = sum(1 for i in checklist if i.get("status") == "partial")
        evidence_score = compute_evidence_score(requirements_met, requirements_partial, total_requirements)
        confidence = compute_confidence(evidence_score, human_flags)
        ai_recommendation = result.get("recommendation", "").upper().replace("_", " ")
        audit_timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # ============================================================
        # DISPLAY AUDIT HEADER
        # ============================================================
        st.markdown(f"""<div class='audit-row'>
        Generated: {audit_timestamp} UTC |
        Case: {current_case.get('case_id')} |
        Analyst: {analyst_name or 'Not recorded'} |
        Rule Set Hash: {ruleset_hash[:16]}...
        </div>""", unsafe_allow_html=True)

        # ============================================================
        # METRICS
        # ============================================================
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Requirements Met", f"{requirements_met}/{total_requirements}")
        col2.metric("Evidence Score", f"{evidence_score}%")
        col3.metric("Confidence", confidence)
        col4.metric("AI Recommendation", ai_recommendation)
        st.progress(evidence_score / 100 if total_requirements else 0)

        # ============================================================
        # SUMMARY & RATIONALE
        # ============================================================
        st.info(f"Case Summary: {result.get('summary')}")
        st.success(f"AI Rationale: {result.get('rationale')}")

        # ============================================================
        # RULE-BY-RULE ASSESSMENT
        # ============================================================
        st.subheader("Rule-by-Rule Assessment")
        for item in checklist:
            status = item.get("status", "UNKNOWN").upper()
            st.markdown(f"**[{status}]** {item.get('requirement')}")
            if item.get("_note"):
                st.caption(f"Note: {item.get('_note')}")
            st.caption(f"Source: {item.get('source')}")
            st.code(f'"{item.get("quote")}"', language="markdown")
            st.divider()

        # ============================================================
        # HUMAN REVIEW FLAGS
        # ============================================================
        if human_flags:
            st.subheader("Review Notes")
            for flag in human_flags:
                st.markdown(f"- {flag}")

        # ============================================================
        # FINAL DECISION — NO BLOCKS, DOWNLOAD ALWAYS ENABLED
        # ============================================================
        st.subheader("2. Final Decision & Export")

        # Decision selector defaults to AI recommendation
        decision_options = ["REPRESENT", "ACCEPT_LIABILITY", "REQUEST_MORE_EVIDENCE"]
        default_index = decision_options.index(ai_recommendation) if ai_recommendation in decision_options else 0
        final_decision = st.selectbox("Your Decision", decision_options, index=default_index)

        # Optional notes — never blocks download
        notes = st.text_area(
            "Notes / Justification (Optional)",
            placeholder="Add comments if needed. Report can be downloaded without this.",
            height=120
        )

        # ============================================================
        # SAVE TO AUDIT DATABASE
        # ============================================================
        record_data = {
            "timestamp": audit_timestamp,
            "case_id": current_case.get("case_id"),
            "reason_code": reason_code,
            "scheme": scheme,
            "analyst": analyst_name or "Not recorded",
            "second_reviewer": "",
            "ai_recommendation": ai_recommendation,
            "human_decision": final_decision,
            "evidence_score": evidence_score,
            "confidence": confidence,
            "ruleset_hash": ruleset_hash,
            "checklist": checklist,
            "human_flags": human_flags,
        }
        record_hash = audit_store.persist_record(record_data)

        # ============================================================
        # GENERATE REPORT
        # ============================================================
        report_document = build_report(
            timestamp=audit_timestamp,
            app_version=APPLICATION_VERSION,
            ai_model=AI_MODEL,
            case=current_case,
            scheme=scheme,
            reason_code=reason_code,
            rules=rules,
            evidence_files=evidence_files,
            requirements_met=requirements_met,
            total_requirements=total_requirements,
            evidence_score=evidence_score,
            confidence=confidence,
            ai_recommendation=ai_recommendation,
            human_decision=final_decision,
            override_note=notes or "No notes added.",
            checklist=checklist,
            analyst=analyst_name or "Not recorded",
            second_reviewer="",
            ruleset_hash=ruleset_hash,
            record_hash=record_hash,
        )

        # ============================================================
        # DOWNLOAD — ALWAYS ENABLED
        # ============================================================
        st.download_button(
            label="Download Full Audit Report",
            data=report_document,
            file_name=f"{current_case.get('case_id', 'CASE')}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.txt",
            use_container_width=True,
            type="primary"
        )
        st.caption(f"Audit record saved. Record Hash: {record_hash[:20]}...")

# ============================================================
# TAB 2 — AUDIT HISTORY
# ============================================================
with tab_history:
    st.subheader("Audit History & Portfolio Metrics")
    metrics = audit_store.fetch_portfolio_metrics()

    if metrics["total_cases"] == 0:
        st.info("No cases processed yet. Complete a workup to see history here.")
    else:
        col1, col2 = st.columns(2)
        col1.metric("Total Cases", metrics["total_cases"])
        col2.metric("Decision Changes", f"{metrics['override_rate']}%")

        st.subheader("By Reason Code")
        for code, data in metrics["by_reason_code"].items():
            st.markdown(
                f"- {code}: {data['count']} cases | "
                f"Avg Score: {data['avg_evidence_score']}% | "
                f"Represent Rate: {data['represent_rate']}%"
            )

        with st.expander("View All Records"):
            for rec in audit_store.fetch_all_records():
                st.markdown(f"""
**{rec['case_id']}** — {rec['ts_utc']}
Analyst: {rec['analyst']} | Score: {rec['evidence_score']}%
AI: {rec['ai_recommendation']} | Decision: {rec['human_decision']}
Hash: {rec['record_hash'][:16]}...
---
""")
