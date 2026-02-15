"""Prompt template helpers for diagnosis module."""

from __future__ import annotations

from typing import Any

from openclaw.diagnosis.faults import FaultDiagnosis, build_diagnosis_prompt


def build_why_stopped_prompt(tags: dict[str, Any], faults: list[FaultDiagnosis]) -> str:
    return build_diagnosis_prompt(
        question="Why is this equipment stopped? What should I check first?",
        tags=tags, faults=faults,
    )


def build_status_summary_prompt(tags: dict[str, Any], faults: list[FaultDiagnosis]) -> str:
    return build_diagnosis_prompt(
        question="Give me a one-sentence status summary of this equipment.",
        tags=tags, faults=faults,
    )
