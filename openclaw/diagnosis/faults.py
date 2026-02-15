"""Rule-based fault detection for conveyor systems.

Ported from factorylm-monorepo/diagnosis/conveyor_faults.py.
Maps PLC tags to fault conditions with technician-friendly explanations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FaultSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class FaultDiagnosis:
    fault_code: str
    severity: FaultSeverity
    title: str
    description: str
    likely_causes: list[str]
    suggested_checks: list[str]
    affected_tags: list[str]
    requires_maintenance: bool = False
    requires_safety_review: bool = False


def detect_faults(tags: dict[str, Any]) -> list[FaultDiagnosis]:
    """Analyze PLC tags and return detected faults, ordered by severity."""
    faults: list[FaultDiagnosis] = []

    motor_running = bool(tags.get("motor_running", 0))
    motor_speed = int(tags.get("motor_speed", 0))
    motor_current = float(tags.get("motor_current", 0))
    temperature = float(tags.get("temperature", 0))
    pressure = int(tags.get("pressure", 0))
    conveyor_running = bool(tags.get("conveyor_running", 0))
    conveyor_speed = int(tags.get("conveyor_speed", 0))
    sensor_1 = bool(tags.get("sensor_1", 0))
    sensor_2 = bool(tags.get("sensor_2", 0))
    fault_alarm = bool(tags.get("fault_alarm", 0))
    e_stop = bool(tags.get("e_stop", 0))
    error_code = int(tags.get("error_code", 0))
    error_message = str(tags.get("error_message", ""))

    if e_stop:
        faults.append(FaultDiagnosis(
            fault_code="E001", severity=FaultSeverity.EMERGENCY,
            title="Emergency Stop Active",
            description="The emergency stop button has been pressed. All motion is halted.",
            likely_causes=["Operator pressed E-stop button", "Safety interlock triggered"],
            suggested_checks=["Verify area is safe before reset", "Check for personnel in hazard zones",
                              "Inspect equipment for damage", "Reset E-stop and clear faults in sequence"],
            affected_tags=["e_stop", "motor_running", "conveyor_running"],
            requires_safety_review=True,
        ))

    if motor_running and motor_current > 5.0:
        faults.append(FaultDiagnosis(
            fault_code="M001", severity=FaultSeverity.CRITICAL,
            title="Motor Overcurrent",
            description=f"Motor current ({motor_current:.1f}A) exceeds safe limit (5.0A).",
            likely_causes=["Mechanical binding or jam", "Bearing failure", "Belt tension too high"],
            suggested_checks=["Check conveyor belt for jams", "Inspect motor bearings",
                              "Verify belt tension", "Check motor thermal overload relay"],
            affected_tags=["motor_current", "motor_running"],
            requires_maintenance=True,
        ))

    if temperature > 80.0:
        faults.append(FaultDiagnosis(
            fault_code="T001", severity=FaultSeverity.CRITICAL,
            title="High Temperature Alarm",
            description=f"Temperature ({temperature:.1f}C) exceeds safe limit (80C).",
            likely_causes=["Cooling fan failure", "Blocked ventilation", "Excessive motor load"],
            suggested_checks=["Check cooling fan operation", "Clear blocked vents",
                              "Reduce motor load temporarily", "Allow cooldown before restart"],
            affected_tags=["temperature"],
            requires_maintenance=True,
        ))

    if motor_running and conveyor_running and sensor_1 and sensor_2:
        faults.append(FaultDiagnosis(
            fault_code="C001", severity=FaultSeverity.CRITICAL,
            title="Conveyor Jam Detected",
            description="Both part sensors are active simultaneously. Product flow is blocked.",
            likely_causes=["Product jam at transfer point", "Misaligned part on conveyor"],
            suggested_checks=["Clear jammed product from conveyor", "Check downstream equipment",
                              "Verify sensor alignment", "Inspect guide rails"],
            affected_tags=["sensor_1", "sensor_2", "conveyor_running"],
        ))

    if not motor_running and conveyor_speed > 0 and not e_stop:
        faults.append(FaultDiagnosis(
            fault_code="M002", severity=FaultSeverity.CRITICAL,
            title="Motor Stopped Unexpectedly",
            description="Motor stopped but conveyor speed setpoint is non-zero.",
            likely_causes=["Thermal overload tripped", "Motor contactor failure", "VFD fault"],
            suggested_checks=["Check motor starter/contactor", "Verify VFD status",
                              "Check thermal overload relay", "Verify power at motor terminals"],
            affected_tags=["motor_running", "conveyor_speed"],
            requires_maintenance=True,
        ))

    if pressure < 60 and motor_running:
        faults.append(FaultDiagnosis(
            fault_code="P001", severity=FaultSeverity.WARNING,
            title="Low Pneumatic Pressure",
            description=f"System pressure ({pressure} PSI) below normal (60+ PSI).",
            likely_causes=["Compressed air supply issue", "Air leak", "Filter or regulator clogged"],
            suggested_checks=["Check main air supply pressure", "Listen for air leaks",
                              "Inspect air filter and regulator", "Verify compressor operation"],
            affected_tags=["pressure"],
        ))

    if motor_running and motor_speed < 30 and conveyor_speed > 50:
        faults.append(FaultDiagnosis(
            fault_code="M003", severity=FaultSeverity.WARNING,
            title="Motor Speed Mismatch",
            description=f"Motor speed ({motor_speed}%) lower than setpoint ({conveyor_speed}%).",
            likely_causes=["Belt slipping on pulleys", "Motor struggling under load"],
            suggested_checks=["Check belt tension and condition", "Verify motor current",
                              "Check VFD parameters", "Inspect drive components"],
            affected_tags=["motor_speed", "conveyor_speed"],
        ))

    if 65.0 < temperature <= 80.0:
        faults.append(FaultDiagnosis(
            fault_code="T002", severity=FaultSeverity.WARNING,
            title="Elevated Temperature",
            description=f"Temperature ({temperature:.1f}C) above normal (65C). Monitor closely.",
            likely_causes=["Heavy continuous operation", "Reduced cooling efficiency"],
            suggested_checks=["Monitor temperature trend", "Ensure cooling is adequate",
                              "Plan maintenance window if trend continues"],
            affected_tags=["temperature"],
        ))

    if fault_alarm and error_code > 0:
        faults.append(FaultDiagnosis(
            fault_code=f"PLC{error_code:03d}", severity=FaultSeverity.CRITICAL,
            title=f"PLC Fault: {error_message or f'Error Code {error_code}'}",
            description=f"The PLC has reported fault code {error_code}.",
            likely_causes=["See PLC fault documentation"],
            suggested_checks=["Review PLC fault log", "Check associated I/O points",
                              "Verify sensor and actuator operation"],
            affected_tags=["fault_alarm", "error_code"],
            requires_maintenance=True,
        ))

    if not faults:
        if motor_running and conveyor_running:
            faults.append(FaultDiagnosis(
                fault_code="OK", severity=FaultSeverity.INFO,
                title="System Running Normally",
                description="All monitored parameters are within normal ranges.",
                likely_causes=[], suggested_checks=[], affected_tags=[],
            ))
        else:
            faults.append(FaultDiagnosis(
                fault_code="IDLE", severity=FaultSeverity.INFO,
                title="System Idle",
                description="Equipment is stopped. Ready to start when commanded.",
                likely_causes=[], suggested_checks=[], affected_tags=[],
            ))

    severity_order = {FaultSeverity.EMERGENCY: 0, FaultSeverity.CRITICAL: 1,
                      FaultSeverity.WARNING: 2, FaultSeverity.INFO: 3}
    faults.sort(key=lambda f: severity_order[f.severity])
    return faults


def build_diagnosis_prompt(
    question: str, tags: dict[str, Any], faults: list[FaultDiagnosis]
) -> str:
    """Build a structured prompt for LLM diagnosis."""
    tag_lines = []
    for key, value in sorted(tags.items()):
        if key.startswith("_") or key in ("id", "timestamp", "node_id"):
            continue
        if isinstance(value, bool) or value in (0, 1):
            display = "ON" if value else "OFF"
        elif isinstance(value, float):
            display = f"{value:.2f}"
        else:
            display = str(value)
        tag_lines.append(f"  {key}: {display}")

    tag_state = "\n".join(tag_lines)

    fault_lines = []
    for f in faults:
        if f.severity == FaultSeverity.INFO:
            continue
        fault_lines.append(f"  [{f.severity.value.upper()}] {f.fault_code}: {f.title}")
        fault_lines.append(f"    {f.description}")
        if f.likely_causes:
            fault_lines.append(f"    Causes: {', '.join(f.likely_causes[:3])}")
    fault_state = "\n".join(fault_lines) if fault_lines else "  No active faults detected"

    return f"""CURRENT EQUIPMENT STATE:
{tag_state}

DETECTED FAULTS:
{fault_state}

TECHNICIAN'S QUESTION:
{question}

INSTRUCTIONS:
1. Answer the technician's question directly and concisely
2. Reference specific tag values when relevant
3. Provide 2-4 actionable troubleshooting steps
4. Use plain language - avoid jargon
5. If safety is a concern, mention it first
6. Keep response under 200 words

RESPONSE:"""
