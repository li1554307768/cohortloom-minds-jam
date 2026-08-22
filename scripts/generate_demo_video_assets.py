#!/usr/bin/env python3
"""Generate the deterministic CohortLoom manifest and English narration."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
OUTPUT_DIR: Final = ROOT / "output" / "demo-video"
MANIFEST_PATH: Final = OUTPUT_DIR / "scene_manifest.json"
NARRATION_TEXT_PATH: Final = OUTPUT_DIR / "narration.txt"
NARRATION_AUDIO_PATH: Final = OUTPUT_DIR / "narration.aiff"
LIVE_EVIDENCE_PATH: Final = ROOT / "output" / "live_minds_evidence.json"

WIDTH: Final = 1920
HEIGHT: Final = 1080
FPS: Final = 30
TARGET_SECONDS: Final = 111.0

SCENES: Final = [
    {
        "duration": 7.0,
        "style": "title",
        "eyebrow": "AUDIENCE GROWTH & COMMUNITY ENGAGEMENT",
        "title": "The persistent experiment memory for creator growth",
        "subtitle": (
            "CohortLoom turns weekly engagement signals into one falsifiable audience "
            "hypothesis, a bounded seven-day test, and an evidence-based due review."
        ),
    },
    {
        "duration": 10.0,
        "style": "branch",
        "eyebrow": "SYNTHETIC CROSS-PLATFORM PULSE",
        "title": "Views alone hide the audience signal",
        "subtitle": (
            "This demo uses a fictional creator and synthetic X, LinkedIn, and YouTube "
            "summaries. CohortLoom compares saves, substantive comments, new followers, and "
            "qualified replies without connecting a social account."
        ),
    },
    {
        "duration": 10.0,
        "style": "truth",
        "eyebrow": "A CLAIM THAT CAN FAIL",
        "title": "Observation becomes a testable hypothesis—not a fact",
        "subtitle": (
            "The creator proposes that practical teardown posts activate quiet viewers better "
            "than broad motivation. The small synthetic sample remains an explicit risk, and "
            "nothing enters memory before human approval."
        ),
    },
    {
        "duration": 12.0,
        "style": "scan",
        "eyebrow": "DETERMINISTIC ANALYSIS FIRST",
        "title": "Bound the metrics before any model call",
        "subtitle": (
            "Local rules normalize three approved summaries, preserve the evidence basis, "
            "isolate instruction-like text, and create success and stop placeholders. This "
            "step is deterministic, auditable, and uses zero Minds cognition."
        ),
    },
    {
        "duration": 12.0,
        "style": "memory",
        "eyebrow": "CREATOR-APPROVED PERSISTENT MEMORY",
        "title": "Store the hypothesis, not a personality profile",
        "subtitle": (
            "After approval, Session A stores the exact falsifiable hypothesis, its evidence "
            "basis, and uncertainty. CohortLoom never stores voice, style, customer messages, "
            "content corrections, or social credentials."
        ),
    },
    {
        "duration": 12.0,
        "style": "sessions",
        "eyebrow": "ONE MIND • THREE DISTINCT CONVERSATIONS",
        "title": "Plan, then review, without repeating the hypothesis",
        "subtitle": (
            "Live evidence under one Mind verifies three distinct conversations. Session B "
            "recalls the approved hypothesis for a bounded plan; Session C sends results and "
            "thresholds, not the hypothesis text, and asks for continue, stop, or revise."
        ),
    },
    {
        "duration": 11.0,
        "style": "plan",
        "eyebrow": "A SEVEN-DAY HUMAN-REVIEWED EXPERIMENT",
        "title": "Every day is bounded; every action stays manual",
        "subtitle": (
            "The schema requires exactly seven numbered days across approved creator-owned "
            "channels. Each day has one bounded action and one human checkpoint. Direct "
            "messages, mass outreach, automatic posting, and automatic following are rejected."
        ),
    },
    {
        "duration": 11.0,
        "style": "review",
        "eyebrow": "SUCCESS AND STOP CONDITIONS",
        "title": "The experiment knows when not to continue",
        "subtitle": (
            "Success means measurable qualified participation while preserving a save-rate "
            "floor. The stop rule protects against weak response or negative feedback. At the "
            "due review, Minds recommends revise, but only the creator can decide."
        ),
    },
    {
        "duration": 9.0,
        "style": "pause",
        "eyebrow": "FAIL-CLOSED OPERATIONS",
        "title": "Low balance, timeout, or pause means stop",
        "subtitle": (
            "A reported Minds balance of ten or less stops new calls. A global send lease "
            "prevents double clicks across workers. A timeout becomes uncertain and triggers "
            "history lookup only—never a blind resend."
        ),
    },
    {
        "duration": 9.0,
        "style": "audit",
        "eyebrow": "EVIDENCE WITHOUT INFLATION",
        "title": "Synthetic, local, live, approved, and executed stay separate",
        "subtitle": (
            "The audit trail separates synthetic metrics, human hypothesis approval, verified "
            "memory exchanges, experiment review, and any manually recorded result. This demo "
            "claims no real user, posting, outreach, revenue, or growth result."
        ),
    },
    {
        "duration": 8.0,
        "style": "close",
        "eyebrow": "COHORTLOOM",
        "title": "Remember the experiment. Respect the evidence.",
        "subtitle": (
            "CohortLoom is not an inbox, content-idea generator, correction tool, scheduler, or "
            "outreach bot. It is persistent experiment memory for creator-controlled growth."
        ),
    },
]


def validate_scenes() -> None:
    total = sum(float(scene["duration"]) for scene in SCENES)
    if abs(total - TARGET_SECONDS) > 0.001:
        raise ValueError(f"Scene duration must total {TARGET_SECONDS:.1f}s, got {total:.1f}s")
    required = {"duration", "style", "eyebrow", "title", "subtitle"}
    for index, scene in enumerate(SCENES, start=1):
        if set(scene) != required or float(scene["duration"]) <= 0:
            raise ValueError(f"Scene {index} has an invalid schema or duration")


def live_evidence_verified(path: Path = LIVE_EVIDENCE_PATH) -> bool:
    """Fail closed: only a strict redacted three-call artifact unlocks the live label."""
    if not path.is_file():
        return False
    try:
        evidence: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(evidence, dict):
        return False
    calls = evidence.get("calls")
    operations = [
        "store_hypothesis",
        "recall_and_plan",
        "recall_and_review",
    ]
    return bool(
        evidence.get("continuity_verified") is True
        and evidence.get("same_mind") is True
        and evidence.get("distinct_conversations") is True
        and isinstance(calls, list)
        and len(calls) == 3
        and all(isinstance(call, dict) for call in calls)
        and [call.get("operation") for call in calls] == operations
        and all(call.get("strict_schema_valid") is True for call in calls)
        and len({call.get("conversation_hash") for call in calls}) == 3
    )


def narration_text() -> str:
    return "\n\n".join(str(scene["subtitle"]) for scene in SCENES) + "\n"


def generate_narration() -> None:
    say = shutil.which("say")
    if say is None:
        raise RuntimeError("macOS 'say' command is required")
    subprocess.run(  # noqa: S603 - fixed local macOS command and fixed arguments
        [
            say,
            "-v",
            "Samantha",
            "-r",
            "240",
            "-f",
            str(NARRATION_TEXT_PATH),
            "-o",
            str(NARRATION_AUDIO_PATH),
        ],
        check=True,
    )
    if not NARRATION_AUDIO_PATH.exists() or NARRATION_AUDIO_PATH.stat().st_size < 10_000:
        raise RuntimeError("Narration audio was not generated correctly")


def main() -> None:
    validate_scenes()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    verified = live_evidence_verified()
    live_label = (
        "LIVE MINDS CONTINUITY VERIFIED" if verified else "LIVE PROOF PENDING"
    )
    manifest = {
        "schema_version": "1.0",
        "brand": "CohortLoom",
        "dataset_label": "SYNTHETIC_DEMO_ONLY",
        "live_evidence_label": live_label,
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "duration": TARGET_SECONDS,
        "scenes": SCENES,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    NARRATION_TEXT_PATH.write_text(narration_text(), encoding="utf-8")
    generate_narration()
    print(f"manifest={MANIFEST_PATH}")  # noqa: T201
    print(f"narration_audio={NARRATION_AUDIO_PATH}")  # noqa: T201
    print(f"live_evidence_label={live_label}")  # noqa: T201
    print(f"scene_duration_seconds={TARGET_SECONDS:.1f}")  # noqa: T201


if __name__ == "__main__":
    main()
