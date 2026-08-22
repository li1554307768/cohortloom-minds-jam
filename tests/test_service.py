from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.minds import MindsError, MindsSendUncertain, SendReceipt, VerifiedReply, sha256_text
from app.services import CohortLoomService

HYPOTHESIS = "Practical teardown posts activate quiet viewers better than broad motivation."


def create_hypothesis(service: CohortLoomService, demo_path: Path, suffix: str = "") -> int:
    service.load_demo(demo_path)
    snapshot_id = int(service.list_snapshots()[0]["id"])
    return service.create_hypothesis(
        snapshot_id=snapshot_id,
        segment_key=f"quiet_creators{suffix}",
        assumption=HYPOTHESIS,
        evidence_basis="Synthetic saves and qualified replies were stronger for teardowns.",
        risk_note="Small synthetic sample; do not generalize before a bounded test.",
    )


def _memory_key(message: str) -> str:
    marker = '"memory_key":"'
    return message.split(marker, 1)[1].split('"', 1)[0]


def _channels(message: str) -> list[str]:
    marker = "Quoted request data:\n"
    envelope = json.loads(message.split(marker, 1)[1].split("\n\nPlease provide", 1)[0])
    return [item["platform"] for item in envelope["data"]["weekly_summaries"]]


class FakeTransport:
    def __init__(
        self,
        *,
        credits: float = 30,
        timeout: bool = False,
        recalled_hypothesis: str = HYPOTHESIS,
        empty_history: bool = False,
        bad_receipt: bool = False,
        credit_error: bool = False,
    ):
        self.credits = credits
        self.timeout = timeout
        self.recalled_hypothesis = recalled_hypothesis
        self.empty_history = empty_history
        self.bad_receipt = bad_receipt
        self.credit_error = credit_error
        self.messages: dict[str, str] = {}
        self.send_calls = 0

    async def get_credits(self) -> float:
        await asyncio.sleep(0)
        if self.credit_error:
            raise MindsError("credit unavailable")
        return self.credits

    async def ensure_conversation(self, alias: str) -> str:
        return f"conversation-{alias}"

    async def send_message(self, alias: str, message: str) -> SendReceipt:
        self.send_calls += 1
        self.messages[alias] = message
        conversation_id = f"conversation-{alias}"
        if self.timeout:
            self.timeout = False
            raise MindsSendUncertain("timeout", alias, conversation_id)
        request_hash = "0" * 64 if self.bad_receipt else sha256_text(message)
        return SendReceipt(alias, conversation_id, f"message-{self.send_calls}", request_hash)

    async def find_reply(
        self, receipt: SendReceipt, request_id: str, expected_request_hash: str
    ) -> VerifiedReply | None:
        if self.empty_history:
            return None
        message = self.messages.get(receipt.alias, "")
        if not message or sha256_text(message) != expected_request_hash:
            return None
        if '"operation":"store_hypothesis"' in message:
            payload: dict[str, Any] = {
                "schema_version": "1.0",
                "operation": "store_hypothesis",
                "memory_key": _memory_key(message),
                "stored": True,
                "summary": "Approved hypothesis stored.",
            }
        elif '"operation":"recall_and_plan"' in message:
            channels = _channels(message)
            payload = {
                "schema_version": "1.0",
                "operation": "recall_and_plan",
                "memory_key": _memory_key(message),
                "recalled_hypothesis": self.recalled_hypothesis,
                "why_now": "A specific synthetic signal is ready for a bounded test.",
                "success_condition": "At least 12 qualified replies and 3% save rate.",
                "stop_condition": "Stop below 4 replies or above 5% negative feedback.",
                "manual_only": True,
                "seven_day_plan": [
                    {
                        "day": day,
                        "channel": channels[(day - 1) % len(channels)],
                        "action": f"Creator reviews bounded test action {day}.",
                        "review_checkpoint": "Human approval before any platform action.",
                    }
                    for day in range(1, 8)
                ],
            }
        else:
            payload = {
                "schema_version": "1.0",
                "operation": "recall_and_review",
                "memory_key": _memory_key(message),
                "recalled_hypothesis": self.recalled_hypothesis,
                "why_now": "The local due review is ready.",
                "review_decision": "REVISE",
                "review_reason": "The unfinished experiment has not reached success.",
                "manual_only": True,
            }
        raw = json.dumps(payload)
        return VerifiedReply(
            raw_text=raw,
            clean_text=raw,
            reply_id=f"reply-{request_id}",
            conversation_id=receipt.conversation_id,
            request_created_at="2026-08-20T00:00:01Z",
            reply_created_at="2026-08-20T00:00:02Z",
            outbound_request_hash=sha256_text(message),
            timestamp_order_verified=True,
            timestamp_evidence_limitation=None,
        )


def exchange_id(service: CohortLoomService, operation: str) -> int:
    item = next(
        item
        for item in service.dashboard()["exchanges"]
        if item["operation"] == operation
    )
    return int(item["id"])


def send_and_sync(
    service: CohortLoomService, exchange: int, transport: FakeTransport
) -> None:
    asyncio.run(service.send_exchange(exchange, transport, credit_floor=10))
    assert asyncio.run(service.sync_exchange(exchange, transport)) is True


def test_demo_idempotence_and_dashboard_boundaries(
    service: CohortLoomService, demo_path: Path
) -> None:
    assert service.load_demo(demo_path) == (3, 0)
    assert service.load_demo(demo_path) == (0, 3)
    state = service.dashboard()
    assert len(state["metrics"]) == 3
    assert {item["platform"] for item in state["metrics"]} == {"x", "linkedin", "youtube"}
    assert state["auto_outreach"] is False
    assert state["snapshots"][0]["synthetic"] == 1


def test_hypothesis_approval_and_three_session_workflow(
    service: CohortLoomService, demo_path: Path
) -> None:
    hypothesis_id = create_hypothesis(service, demo_path)
    store_id = service.approve_hypothesis(hypothesis_id)
    fake = FakeTransport()
    send_and_sync(service, store_id, fake)
    plan_id = exchange_id(service, "recall_and_plan")
    send_and_sync(service, plan_id, fake)
    review_id = exchange_id(service, "recall_and_review")
    review_request = next(
        item for item in service.dashboard()["exchanges"] if item["id"] == review_id
    )["request_body"]
    assert HYPOTHESIS not in review_request
    send_and_sync(service, review_id, fake)

    state = service.dashboard()
    experiment = state["experiments"][0]
    assert len(experiment["days"]) == 7
    assert experiment["status"] == "PENDING_REVIEW"
    assert experiment["review_decision"] == "REVISE"
    assert experiment["observed_result"]
    assert fake.send_calls == 3
    service.record_result(
        int(experiment["id"]),
        "Creator observed 9 qualified replies and a 3.4% synthetic save rate.",
    )
    service.mark_review(int(experiment["id"]))
    service.decide_experiment(int(experiment["id"]), True)
    approved = service.dashboard()["experiments"][0]
    assert approved["status"] == "APPROVED"
    assert approved["follow_up_count"] == 1
    assert approved["observed_result"].startswith("Creator observed")


def test_reject_pause_validation_and_credit_floor(
    service: CohortLoomService, demo_path: Path
) -> None:
    hypothesis_id = create_hypothesis(service, demo_path)
    service.set_paused(True)
    with pytest.raises(ValueError, match="暂停"):
        service.approve_hypothesis(hypothesis_id)
    service.set_paused(False)
    service.reject_hypothesis(hypothesis_id)
    assert service.dashboard()["hypotheses"][0]["status"] == "REJECTED"

    second = create_hypothesis(service, demo_path, "_b")
    exchange = service.approve_hypothesis(second)
    with pytest.raises(ValueError, match="余额"):
        asyncio.run(service.send_exchange(exchange, FakeTransport(credits=10), credit_floor=10))
    assert exchange_id(service, "store_hypothesis") == exchange
    with pytest.raises(ValueError, match="阈值"):
        asyncio.run(service.send_exchange(exchange, FakeTransport(), credit_floor=9))


def test_hypothesis_input_validation(service: CohortLoomService, demo_path: Path) -> None:
    service.load_demo(demo_path)
    snapshot = int(service.list_snapshots()[0]["id"])
    base = {
        "snapshot_id": snapshot,
        "segment_key": "quiet_creators",
        "assumption": HYPOTHESIS,
        "evidence_basis": "Evidence",
        "risk_note": "Risk",
    }
    with pytest.raises(ValueError, match="segment_key"):
        service.create_hypothesis(**{**base, "segment_key": "?"})
    with pytest.raises(ValueError, match="不存在"):
        service.create_hypothesis(**{**base, "snapshot_id": 999})
    with pytest.raises(ValueError, match="不能为空"):
        service.create_hypothesis(**{**base, "assumption": " "})


def test_invalid_demo_data_is_fail_closed(service: CohortLoomService, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"dataset_label":"REAL"}', encoding="utf-8")
    with pytest.raises(ValueError, match="SYNTHETIC"):
        service.load_demo(bad)
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="无法读取"):
        service.load_demo(malformed)


def test_double_click_sends_once(service: CohortLoomService, demo_path: Path) -> None:
    exchange = service.approve_hypothesis(create_hypothesis(service, demo_path))
    fake = FakeTransport()

    async def run() -> list[object]:
        return await asyncio.gather(
            service.send_exchange(exchange, fake, credit_floor=10),
            service.send_exchange(exchange, fake, credit_floor=10),
            return_exceptions=True,
        )

    results = asyncio.run(run())
    assert fake.send_calls == 1
    assert sum(isinstance(item, SendReceipt) for item in results) == 1
    assert sum(isinstance(item, ValueError) for item in results) == 1


def test_timeout_recovers_only_from_history(
    service: CohortLoomService, demo_path: Path
) -> None:
    exchange = service.approve_hypothesis(create_hypothesis(service, demo_path))
    fake = FakeTransport(timeout=True)
    with pytest.raises(MindsSendUncertain):
        asyncio.run(service.send_exchange(exchange, fake, credit_floor=10))
    assert fake.send_calls == 1
    assert asyncio.run(service.sync_exchange(exchange, fake)) is True
    assert fake.send_calls == 1
    completed = next(item for item in service.dashboard()["exchanges"] if item["id"] == exchange)
    assert completed["status"] == "COMPLETED"
    assert completed["history_request_hash"] == completed["request_hash"]


def test_empty_history_does_not_resend(service: CohortLoomService, demo_path: Path) -> None:
    exchange = service.approve_hypothesis(create_hypothesis(service, demo_path))
    fake = FakeTransport(empty_history=True)
    asyncio.run(service.send_exchange(exchange, fake, credit_floor=10))
    assert asyncio.run(service.sync_exchange(exchange, fake)) is False
    assert fake.send_calls == 1


@pytest.mark.parametrize("recalled", ["Different.", "The memory is unavailable."])
def test_recall_must_exactly_match_approved_hypothesis(
    service: CohortLoomService, demo_path: Path, recalled: str
) -> None:
    store = service.approve_hypothesis(create_hypothesis(service, demo_path))
    fake = FakeTransport(recalled_hypothesis=recalled)
    send_and_sync(service, store, fake)
    plan = exchange_id(service, "recall_and_plan")
    asyncio.run(service.send_exchange(plan, fake, credit_floor=10))
    with pytest.raises(ValueError, match="不精确匹配"):
        asyncio.run(service.sync_exchange(plan, fake))
    assert service.dashboard()["experiments"][0]["days"] == []


def test_global_lock_serializes_different_exchanges(
    service: CohortLoomService, demo_path: Path
) -> None:
    first = service.approve_hypothesis(create_hypothesis(service, demo_path, "_a"))
    second = service.approve_hypothesis(create_hypothesis(service, demo_path, "_b"))

    class Slow(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0

        async def get_credits(self) -> float:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return self.credits

        async def send_message(self, alias: str, message: str) -> SendReceipt:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            result = await super().send_message(alias, message)
            self.active -= 1
            return result

    fake = Slow()
    async def send_both() -> None:
        await asyncio.gather(
            service.send_exchange(first, fake, credit_floor=10),
            service.send_exchange(second, fake, credit_floor=10),
        )

    asyncio.run(send_both())
    assert fake.max_active == 1


def test_database_lease_fails_before_credit_check(
    service: CohortLoomService, demo_path: Path
) -> None:
    exchange = service.approve_hypothesis(create_hypothesis(service, demo_path))
    with service.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO app_state(key, value) VALUES ('minds_send_lease', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            ('{"token":"other","exchange_id":999,"expires_at":9999999999}',),
        )
        connection.commit()
    fake = FakeTransport()
    with pytest.raises(ValueError, match="正忙"):
        asyncio.run(service.send_exchange(exchange, fake, credit_floor=10))
    assert fake.send_calls == 0


def test_receipt_mismatch_becomes_uncertain(
    service: CohortLoomService, demo_path: Path
) -> None:
    exchange = service.approve_hypothesis(create_hypothesis(service, demo_path))
    with pytest.raises(ValueError, match="哈希"):
        asyncio.run(
            service.send_exchange(exchange, FakeTransport(bad_receipt=True), credit_floor=10)
        )
    item = next(item for item in service.dashboard()["exchanges"] if item["id"] == exchange)
    assert item["status"] == "UNCERTAIN"


def test_credit_error_releases_claim_for_safe_retry(
    service: CohortLoomService, demo_path: Path
) -> None:
    exchange = service.approve_hypothesis(create_hypothesis(service, demo_path))
    with pytest.raises(MindsError):
        asyncio.run(
            service.send_exchange(exchange, FakeTransport(credit_error=True), credit_floor=10)
        )
    item = next(item for item in service.dashboard()["exchanges"] if item["id"] == exchange)
    assert item["status"] == "PREPARED"


def test_experiment_cannot_be_decided_before_plan(
    service: CohortLoomService, demo_path: Path
) -> None:
    service.approve_hypothesis(create_hypothesis(service, demo_path))
    experiment = int(service.dashboard()["experiments"][0]["id"])
    with pytest.raises(ValueError, match="不存在或已决策"):
        service.decide_experiment(experiment, True)
    with pytest.raises(ValueError, match="待审核"):
        service.mark_review(experiment)
    with pytest.raises(ValueError, match="待审核或已批准"):
        service.record_result(experiment, "No result yet")
