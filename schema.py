"""
Pydantic schema for validating AI-generated workup responses.

Why this exists: the previous version trusted `response_format={"type":
"json_object"}` plus `.get()` defaults to avoid crashes. That means a
missing field, wrong type, or unexpected status string doesn't fail —
it silently produces a wrong evidence score. Validating against an
explicit schema turns "quietly wrong" into "loudly rejected," which is
the correct failure mode for a compliance tool: if the AI's output
can't be trusted, the case should fall to manual review, not display a
confident-looking number built on bad data.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ChecklistItem(BaseModel):
    requirement: str
    status: Literal["satisfied", "partial", "missing"]
    source: Optional[str] = None
    quote: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v):
        if isinstance(v, str):
            return v.strip().lower()
        return v


class WorkupResult(BaseModel):
    summary: str
    checklist: list[ChecklistItem] = Field(default_factory=list)
    human_flags: list[str] = Field(default_factory=list)
    recommendation: Literal["represent", "accept_liability", "request_more_evidence"]
    rationale: str