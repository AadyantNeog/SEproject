"""The single D-02 policy gate shared by every live code path."""

from __future__ import annotations

import json
from pathlib import Path

D02_RECORD = Path("docs/evidence/policy-and-consent/d02-status.json")


def policy_resolved(path: Path) -> bool:
    """Accept only a human-recorded D-02 resolution with an https evidence link.

    A model, environment flag or tool argument cannot change this. Only the
    reviewed record file can.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(record, dict):
        return False
    evidence, recorded_by = record.get("evidence_url"), record.get("recorded_by")
    return (
        record.get("state") == "resolved"
        and isinstance(evidence, str)
        and evidence.startswith("https://")
        and isinstance(recorded_by, str)
        and bool(recorded_by.strip())
    )
