from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any


def evidence_check() -> Callable[[Path], bool]:
    script = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "generate_demo_video_assets.py"
    )
    namespace = runpy.run_path(str(script))
    check: Any = namespace["live_evidence_verified"]
    return check


def test_video_live_label_requires_strict_three_call_evidence(tmp_path: Path) -> None:
    check = evidence_check()
    evidence = tmp_path / "evidence.json"
    assert check(evidence) is False
    evidence.write_text("{", encoding="utf-8")
    assert check(evidence) is False
    evidence.write_text(
        json.dumps(
            {
                "continuity_verified": True,
                "same_mind": True,
                "distinct_conversations": True,
                "calls": [
                    {
                        "operation": operation,
                        "strict_schema_valid": True,
                        "conversation_hash": f"conversation-{index}",
                    }
                    for index, operation in enumerate(
                        (
                            "store_hypothesis",
                            "recall_and_plan",
                            "recall_and_review",
                        )
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    assert check(evidence) is True


def test_video_live_label_rejects_duplicate_conversation_or_wrong_operation(
    tmp_path: Path,
) -> None:
    check = evidence_check()
    evidence = tmp_path / "evidence.json"
    payload = {
        "continuity_verified": True,
        "same_mind": True,
        "distinct_conversations": True,
        "calls": [
            {
                "operation": operation,
                "strict_schema_valid": True,
                "conversation_hash": "same",
            }
            for operation in (
                "store_hypothesis",
                "recall_and_plan",
                "recall_and_review",
            )
        ],
    }
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    assert check(evidence) is False
    payload["calls"][2]["conversation_hash"] = "different"
    payload["calls"][1]["conversation_hash"] = "other"
    payload["calls"][2]["operation"] = "recall_and_plan"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    assert check(evidence) is False
