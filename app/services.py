"""Deterministic audience-experiment workflow and audit trail."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from app.db import Database
from app.minds import (
    MindsError,
    MindsPacket,
    MindsSendUncertain,
    MindsTransport,
    SendReceipt,
    VerifiedReply,
    build_due_check_packet,
    build_recall_packet,
    build_store_packet,
    has_prompt_injection,
    parse_minds_response,
    sha256_text,
    stable_json,
)

ALLOWED_PLATFORMS = {"x", "linkedin", "youtube"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def clean_text(value: str, field: str, maximum: int = 2_000) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{field} 不能为空")
    if len(cleaned) > maximum:
        raise ValueError(f"{field} 超过 {maximum} 字符")
    return cleaned


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


class CohortLoomService:
    """Local-first service; the only network-capable action is an explicit Minds send."""

    def __init__(self, database: Database):
        self.database = database
        self._send_lock = asyncio.Lock()

    def _audit(
        self,
        connection: sqlite3.Connection,
        action: str,
        entity_type: str,
        entity_id: str | int,
        details: dict[str, Any],
        *,
        actor: str = "local_human",
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events(
                occurred_at, actor, action, entity_type, entity_id, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (utc_now(), actor, action, entity_type, str(entity_id), stable_json(details)),
        )

    def is_paused(self) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key='paused'"
            ).fetchone()
        return bool(row and row["value"] == "1")

    def set_paused(self, paused: bool) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE app_state SET value=? WHERE key='paused'", ("1" if paused else "0",)
            )
            self._audit(
                connection,
                "PAUSE_ENABLED" if paused else "PAUSE_DISABLED",
                "system",
                "global",
                {"paused": paused, "auto_outreach": False},
            )
            connection.commit()

    def assert_not_paused(self) -> None:
        if self.is_paused():
            raise ValueError("CohortLoom 已暂停；新建和 Minds 发送均已锁定")

    def _acquire_send_lease(self, exchange_id: int) -> str:
        """Acquire a database-backed lease shared across workers and processes."""
        token = f"lease-{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).timestamp()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value FROM app_state WHERE key='minds_send_lease'"
            ).fetchone()
            if row is not None:
                try:
                    lease = json.loads(str(row["value"]))
                    expires_at = float(lease["expires_at"])
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError("Minds 全局发送租约损坏；已失败关闭") from exc
                if expires_at > now:
                    raise ValueError("Minds 全局发送通道正忙；本次未进入余额检查")
            connection.execute(
                """
                INSERT INTO app_state(key, value) VALUES ('minds_send_lease', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (
                    stable_json(
                        {
                            "token": token,
                            "exchange_id": exchange_id,
                            "expires_at": now + 120,
                        }
                    ),
                ),
            )
            connection.commit()
        return token

    def _release_send_lease(self, token: str) -> None:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value FROM app_state WHERE key='minds_send_lease'"
            ).fetchone()
            if row is not None:
                try:
                    lease = json.loads(str(row["value"]))
                except json.JSONDecodeError:
                    connection.rollback()
                    return
                if isinstance(lease, dict) and lease.get("token") == token:
                    connection.execute("DELETE FROM app_state WHERE key='minds_send_lease'")
            connection.commit()

    def load_demo(self, path: Path) -> tuple[int, int]:
        self.assert_not_paused()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("无法读取合成演示数据") from exc
        if payload.get("dataset_label") != "SYNTHETIC_DEMO_ONLY":
            raise ValueError("演示数据必须明确标注 SYNTHETIC_DEMO_ONLY")
        snapshot = payload.get("snapshot")
        metrics = payload.get("metrics")
        if not isinstance(snapshot, dict) or snapshot.get("synthetic") is not True:
            raise ValueError("合成周快照标记缺失")
        if not isinstance(metrics, list) or not 1 <= len(metrics) <= 3:
            raise ValueError("合成互动指标必须包含 1–3 个平台")
        week_label = clean_text(str(snapshot.get("week_label", "")), "week_label", 80)
        audience_size = snapshot.get("audience_size")
        if not isinstance(audience_size, int) or isinstance(audience_size, bool):
            raise ValueError("audience_size 必须是整数")
        if audience_size < 0:
            raise ValueError("audience_size 不能为负数")
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM weekly_snapshots WHERE week_label=?", (week_label,)
            ).fetchone()
            if existing:
                snapshot_id = int(existing["id"])
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO weekly_snapshots(
                        week_label, audience_size, summary, synthetic, created_at
                    ) VALUES (?, ?, ?, 1, ?)
                    """,
                    (
                        week_label,
                        audience_size,
                        clean_text(str(snapshot.get("summary", "")), "summary", 4_000),
                        utc_now(),
                    ),
                )
                snapshot_id = int(cursor.lastrowid or 0)
            inserted = 0
            duplicates = 0
            seen: set[str] = set()
            for item in metrics:
                if not isinstance(item, dict) or item.get("synthetic") is not True:
                    raise ValueError("每个平台指标都必须标注 synthetic=true")
                platform = clean_text(str(item.get("platform", "")), "platform", 30).casefold()
                if platform not in ALLOWED_PLATFORMS or platform in seen:
                    raise ValueError("平台必须是唯一的 x、linkedin 或 youtube")
                seen.add(platform)
                numeric_fields = (
                    "views",
                    "comments",
                    "saves",
                    "shares",
                    "new_followers",
                    "qualified_replies",
                )
                values: list[int] = []
                for field in numeric_fields:
                    value = item.get(field)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        raise ValueError(f"{field} 必须是非负整数")
                    values.append(value)
                try:
                    connection.execute(
                        """
                        INSERT INTO engagement_metrics(
                            snapshot_id, platform, views, comments, saves, shares,
                            new_followers, qualified_replies, synthetic
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (snapshot_id, platform, *values),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    duplicates += 1
            self._audit(
                connection,
                "SYNTHETIC_SNAPSHOT_LOADED",
                "weekly_snapshot",
                snapshot_id,
                {"inserted_metrics": inserted, "duplicates": duplicates, "synthetic": True},
            )
            connection.commit()
        return inserted, duplicates

    def list_snapshots(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM weekly_snapshots ORDER BY id DESC"
            ).fetchall()
        return [row_dict(row) for row in rows]

    def list_metrics(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT m.*, s.week_label FROM engagement_metrics m
                JOIN weekly_snapshots s ON s.id=m.snapshot_id
                ORDER BY m.id
                """
            ).fetchall()
        return [row_dict(row) for row in rows]

    def create_hypothesis(
        self,
        *,
        snapshot_id: int,
        segment_key: str,
        assumption: str,
        evidence_basis: str,
        risk_note: str,
    ) -> int:
        self.assert_not_paused()
        safe_key = clean_text(segment_key, "segment_key", 100).casefold().replace(" ", "_")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,99}", safe_key):
            raise ValueError("segment_key 只能使用小写字母、数字、下划线和连字符")
        safe_assumption = clean_text(assumption, "assumption", 1_200)
        safe_evidence = clean_text(evidence_basis, "evidence_basis", 1_500)
        safe_risk = clean_text(risk_note, "risk_note", 800)
        memory_key = f"cohortloom:hypothesis:{safe_key}:{uuid.uuid4().hex[:12]}"
        flagged = has_prompt_injection(safe_assumption, safe_evidence, safe_risk)
        with self.database.connect() as connection:
            snapshot = connection.execute(
                "SELECT * FROM weekly_snapshots WHERE id=?", (snapshot_id,)
            ).fetchone()
            if snapshot is None:
                raise ValueError("周快照不存在")
            cursor = connection.execute(
                """
                INSERT INTO audience_hypotheses(
                    snapshot_id, segment_key, assumption, evidence_basis, risk_note,
                    memory_key, injection_flagged, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?)
                """,
                (
                    snapshot_id,
                    safe_key,
                    safe_assumption,
                    safe_evidence,
                    safe_risk,
                    memory_key,
                    int(flagged),
                    utc_now(),
                ),
            )
            hypothesis_id = int(cursor.lastrowid or 0)
            connection.execute(
                """
                INSERT INTO growth_experiments(
                    hypothesis_id, title, status, why_now, success_condition,
                    stop_condition, seven_day_plan_json, review_due_label
                ) VALUES (?, ?, 'BLOCKED_PENDING_APPROVAL', ?, ?, ?, '[]', ?)
                """,
                (
                    hypothesis_id,
                    f"7-day experiment for {safe_key}",
                    f"Candidate signal from {snapshot['week_label']}: {safe_evidence}",
                    "Pending creator approval and a schema-valid memory recall.",
                    "Stop before execution if the hypothesis or evidence is rejected.",
                    "Day 7 manual review",
                ),
            )
            self._audit(
                connection,
                "AUDIENCE_HYPOTHESIS_RECORDED",
                "audience_hypothesis",
                hypothesis_id,
                {"segment_key": safe_key, "injection_flagged": flagged},
            )
            connection.commit()
        return hypothesis_id

    def _create_exchange(
        self, connection: sqlite3.Connection, hypothesis: sqlite3.Row, packet: MindsPacket
    ) -> int:
        existing = connection.execute(
            "SELECT id FROM minds_exchanges WHERE semantic_hash=?", (packet.semantic_hash,)
        ).fetchone()
        if existing:
            return int(existing["id"])
        alias_prefix = {
            "store_hypothesis": "cl-store",
            "recall_and_plan": "cl-plan",
            "recall_and_review": "cl-review",
        }[packet.operation]
        alias = f"{alias_prefix}-{packet.request_id[-12:]}"
        cursor = connection.execute(
            """
            INSERT INTO minds_exchanges(
                hypothesis_id, operation, request_id, memory_key, session_alias,
                request_body, request_hash, semantic_hash, expected_channels_json,
                injection_flagged, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PREPARED', ?)
            """,
            (
                int(hypothesis["id"]),
                packet.operation,
                packet.request_id,
                packet.memory_key,
                alias,
                packet.body,
                packet.request_hash,
                packet.semantic_hash,
                stable_json({"channels": list(packet.expected_channels)}),
                int(packet.injection_flagged),
                utc_now(),
            ),
        )
        exchange_id = int(cursor.lastrowid or 0)
        self._audit(
            connection,
            "MINDS_REQUEST_PREPARED",
            "minds_exchange",
            exchange_id,
            {
                "operation": packet.operation,
                "semantic_hash": packet.semantic_hash,
                "new_session": True,
                "sent": False,
            },
            actor="system",
        )
        return exchange_id

    def approve_hypothesis(self, hypothesis_id: int) -> int:
        self.assert_not_paused()
        with self.database.connect() as connection:
            hypothesis = connection.execute(
                "SELECT * FROM audience_hypotheses WHERE id=?", (hypothesis_id,)
            ).fetchone()
            if hypothesis is None or hypothesis["status"] != "PENDING_APPROVAL":
                raise ValueError("受众假设不存在或已决策")
            connection.execute(
                "UPDATE audience_hypotheses SET status='APPROVED', decided_at=? WHERE id=?",
                (utc_now(), hypothesis_id),
            )
            connection.execute(
                "UPDATE growth_experiments SET status='WAITING_FOR_MEMORY' WHERE hypothesis_id=?",
                (hypothesis_id,),
            )
            packet = build_store_packet(
                str(hypothesis["memory_key"]),
                segment_key=str(hypothesis["segment_key"]),
                audience_hypothesis=str(hypothesis["assumption"]),
                evidence_basis=str(hypothesis["evidence_basis"]),
                risk_note=str(hypothesis["risk_note"]),
            )
            exchange_id = self._create_exchange(connection, hypothesis, packet)
            self._audit(
                connection,
                "AUDIENCE_HYPOTHESIS_APPROVED",
                "audience_hypothesis",
                hypothesis_id,
                {"memory_write_exchange_id": exchange_id, "auto_outreach": False},
            )
            connection.commit()
        return exchange_id

    def reject_hypothesis(self, hypothesis_id: int) -> None:
        self.assert_not_paused()
        with self.database.connect() as connection:
            changed = connection.execute(
                """
                UPDATE audience_hypotheses SET status='REJECTED', decided_at=?
                WHERE id=? AND status='PENDING_APPROVAL'
                """,
                (utc_now(), hypothesis_id),
            ).rowcount
            if changed != 1:
                raise ValueError("受众假设不存在或已决策")
            connection.execute(
                "UPDATE growth_experiments SET status='CANCELLED' WHERE hypothesis_id=?",
                (hypothesis_id,),
            )
            self._audit(
                connection,
                "AUDIENCE_HYPOTHESIS_REJECTED",
                "audience_hypothesis",
                hypothesis_id,
                {"sent": False},
            )
            connection.commit()

    def _packet_from_exchange(self, exchange: sqlite3.Row) -> MindsPacket:
        operation = cast(Any, str(exchange["operation"]))
        expected_payload = json.loads(str(exchange["expected_channels_json"]))
        expected_values = expected_payload.get("channels", [])
        if not isinstance(expected_values, list) or not all(
            isinstance(value, str) for value in expected_values
        ):
            raise ValueError("Minds 预期平台证据格式无效")
        return MindsPacket(
            request_id=str(exchange["request_id"]),
            operation=operation,
            memory_key=str(exchange["memory_key"]),
            body=str(exchange["request_body"]),
            request_hash=str(exchange["request_hash"]),
            semantic_hash=str(exchange["semantic_hash"]),
            injection_flagged=bool(exchange["injection_flagged"]),
            expected_channels=tuple(expected_values),
        )

    def _accept_verified_minds_response(
        self, exchange_id: int, reply: VerifiedReply
    ) -> int | None:
        """Persist immutable transport evidence before parsing model-authored JSON."""
        with self.database.connect() as connection:
            exchange = connection.execute(
                "SELECT * FROM minds_exchanges WHERE id=?", (exchange_id,)
            ).fetchone()
            if exchange is None or exchange["status"] not in {"SENT", "UNCERTAIN"}:
                raise ValueError("只接受已发送且运输可核验的 Minds 回复")
            if (
                not exchange["remote_conversation_id"]
                or reply.conversation_id != exchange["remote_conversation_id"]
            ):
                raise ValueError("Minds 回复与已知会话不匹配")
            if reply.outbound_request_hash != str(exchange["request_hash"]):
                raise ValueError("Minds 历史中的出站原文哈希不匹配")
            raw_hash = sha256_text(reply.raw_text)
            clean_hash = sha256_text(reply.clean_text)
            connection.execute(
                """
                UPDATE minds_exchanges SET remote_reply_id=?, raw_response_hash=?,
                    clean_response_hash=?, history_request_hash=?, request_created_at=?,
                    reply_created_at=?, timestamp_order_verified=?,
                    timestamp_evidence_limitation=? WHERE id=?
                """,
                (
                    reply.reply_id,
                    raw_hash,
                    clean_hash,
                    reply.outbound_request_hash,
                    reply.request_created_at,
                    reply.reply_created_at,
                    int(reply.timestamp_order_verified),
                    reply.timestamp_evidence_limitation,
                    exchange_id,
                ),
            )
            self._audit(
                connection,
                "MINDS_TRANSPORT_VERIFIED",
                "minds_exchange",
                exchange_id,
                {
                    "raw_response_hash": raw_hash,
                    "clean_response_hash": clean_hash,
                    "history_request_hash": reply.outbound_request_hash,
                    "timestamp_order_verified": reply.timestamp_order_verified,
                    "timestamp_evidence_limitation": reply.timestamp_evidence_limitation,
                },
                actor="system",
            )
            connection.commit()

        with self.database.connect() as connection:
            exchange = connection.execute(
                "SELECT * FROM minds_exchanges WHERE id=?", (exchange_id,)
            ).fetchone()
            if exchange is None:
                raise ValueError("Minds 请求不存在")
            packet = self._packet_from_exchange(exchange)
            parsed = parse_minds_response(packet, reply.clean_text, transport_verified=True)
            response_json = stable_json(parsed)
            response_hash = sha256_text(response_json)
            duplicate = connection.execute(
                "SELECT id FROM minds_exchanges WHERE response_hash=? AND id!=?",
                (response_hash, exchange_id),
            ).fetchone()
            if duplicate:
                raise ValueError("该 Minds 响应已绑定到其他请求")
            hypothesis = connection.execute(
                "SELECT * FROM audience_hypotheses WHERE id=?",
                (int(exchange["hypothesis_id"]),),
            ).fetchone()
            if hypothesis is None:
                raise ValueError("受众假设不存在")
            if exchange["operation"] in {"recall_and_plan", "recall_and_review"}:
                recalled = parsed.get("recalled_hypothesis")
                if not isinstance(recalled, str) or normalize(recalled) != normalize(
                    str(hypothesis["assumption"])
                ):
                    raise ValueError("Minds 召回假设与人工批准内容不精确匹配；已拒绝计划")
            next_exchange_id: int | None = None
            if exchange["operation"] == "store_hypothesis":
                snapshot = connection.execute(
                    "SELECT * FROM weekly_snapshots WHERE id=?",
                    (int(hypothesis["snapshot_id"]),),
                ).fetchone()
                metrics = connection.execute(
                    "SELECT * FROM engagement_metrics WHERE snapshot_id=? ORDER BY id",
                    (int(hypothesis["snapshot_id"]),),
                ).fetchall()
                if snapshot is None or not metrics:
                    raise ValueError("受众假设缺少周快照指标")
                summaries = [
                    {
                        "platform": str(item["platform"]),
                        "observation": (
                            f"{snapshot['summary']} Platform={item['platform']}; "
                            f"views={item['views']}; comments={item['comments']}; "
                            f"saves={item['saves']}; shares={item['shares']}; "
                            f"new_followers={item['new_followers']}; "
                            f"qualified_replies={item['qualified_replies']}."
                        ),
                        "synthetic": bool(item["synthetic"]),
                    }
                    for item in metrics
                ]
                recall = build_recall_packet(
                    str(hypothesis["memory_key"]),
                    week_label=str(snapshot["week_label"]),
                    experiment_goal=str(hypothesis["assumption"]),
                    weekly_summaries=summaries,
                )
                next_exchange_id = self._create_exchange(connection, hypothesis, recall)
            elif exchange["operation"] == "recall_and_plan":
                plan = parsed.get("seven_day_plan")
                if not isinstance(plan, list) or len(plan) != 7:
                    raise ValueError("Minds 七天计划格式无效")
                connection.execute(
                    """
                    UPDATE growth_experiments SET status='PENDING_REVIEW', why_now=?,
                        success_condition=?, stop_condition=?, seven_day_plan_json=?
                    WHERE hypothesis_id=? AND status='WAITING_FOR_MEMORY'
                    """,
                    (
                        str(parsed["why_now"]),
                        str(parsed["success_condition"]),
                        str(parsed["stop_condition"]),
                        stable_json({"days": plan}),
                        int(hypothesis["id"]),
                    ),
                )
                due_packet = build_due_check_packet(
                    str(hypothesis["memory_key"]),
                    experiment_ref=f"growth-experiment-{hypothesis['id']}",
                    due_label="Day 7 manual review",
                    observed_result=(
                        "No creator result is recorded yet; the experiment remains unfinished "
                        "and is due for a local review."
                    ),
                    success_condition=str(parsed["success_condition"]),
                    stop_condition=str(parsed["stop_condition"]),
                )
                next_exchange_id = self._create_exchange(
                    connection, hypothesis, due_packet
                )
            else:
                connection.execute(
                    """
                    UPDATE growth_experiments SET observed_result=COALESCE(observed_result, ?),
                        review_decision=?, review_reason=? WHERE hypothesis_id=?
                    """,
                    (
                        "No creator result recorded; unfinished experiment due for review.",
                        str(parsed["review_decision"]),
                        str(parsed["review_reason"]),
                        int(hypothesis["id"]),
                    ),
                )
            connection.execute(
                """
                UPDATE minds_exchanges SET status='COMPLETED', response_json=?,
                    response_hash=?, completed_at=? WHERE id=?
                """,
                (response_json, response_hash, utc_now(), exchange_id),
            )
            self._audit(
                connection,
                "MINDS_RESPONSE_ACCEPTED",
                "minds_exchange",
                exchange_id,
                {
                    "operation": str(exchange["operation"]),
                    "response_hash": response_hash,
                    "next_exchange_id": next_exchange_id,
                    "auto_outreach": False,
                },
                actor="system",
            )
            connection.commit()
        return next_exchange_id

    async def send_exchange(
        self, exchange_id: int, transport: MindsTransport, *, credit_floor: float
    ) -> SendReceipt:
        self.assert_not_paused()
        if credit_floor < 10:
            raise ValueError("余额安全阈值不能低于 10")
        async with self._send_lock:
            self.assert_not_paused()
            lease_token = self._acquire_send_lease(exchange_id)
            try:
                return await self._send_exchange_locked(
                    exchange_id, transport, credit_floor=credit_floor
                )
            finally:
                self._release_send_lease(lease_token)

    async def _send_exchange_locked(
        self, exchange_id: int, transport: MindsTransport, *, credit_floor: float
    ) -> SendReceipt:
        with self.database.connect() as connection:
            exchange = connection.execute(
                "SELECT * FROM minds_exchanges WHERE id=?", (exchange_id,)
            ).fetchone()
            if exchange is None:
                raise ValueError("Minds 请求不存在")
            claimed = connection.execute(
                "UPDATE minds_exchanges SET status='SENDING' WHERE id=? AND status='PREPARED'",
                (exchange_id,),
            ).rowcount
            if claimed != 1:
                raise ValueError("请求不存在或已发送；禁止重发")
            connection.commit()
        try:
            credits = await transport.get_credits()
        except Exception:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE minds_exchanges SET status='PREPARED' WHERE id=? AND status='SENDING'",
                    (exchange_id,),
                )
                connection.commit()
            raise
        if credits <= 10 or credits <= credit_floor:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE minds_exchanges SET status='PREPARED' WHERE id=? AND status='SENDING'",
                    (exchange_id,),
                )
                connection.commit()
            raise ValueError(f"Minds 余额 {credits:.2f} 已达安全线，停止发送")
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE minds_exchanges SET credits_before=? WHERE id=?", (credits, exchange_id)
            )
            connection.commit()
        try:
            receipt = await transport.send_message(
                str(exchange["session_alias"]), str(exchange["request_body"])
            )
        except MindsError as exc:
            with self.database.connect() as connection:
                conversation_id = (
                    exc.conversation_id if isinstance(exc, MindsSendUncertain) else None
                )
                connection.execute(
                    """
                    UPDATE minds_exchanges SET status=?, remote_conversation_id=COALESCE(?,
                        remote_conversation_id) WHERE id=?
                    """,
                    (
                        "UNCERTAIN" if exc.uncertain else "REJECTED",
                        conversation_id,
                        exchange_id,
                    ),
                )
                self._audit(
                    connection,
                    "MINDS_SEND_UNCERTAIN" if exc.uncertain else "MINDS_SEND_REJECTED",
                    "minds_exchange",
                    exchange_id,
                    {"blind_retry_allowed": False},
                    actor="system",
                )
                connection.commit()
            raise
        if receipt.request_hash != str(exchange["request_hash"]):
            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE minds_exchanges SET status='UNCERTAIN', remote_conversation_id=?,
                        remote_message_id=? WHERE id=?
                    """,
                    (receipt.conversation_id, receipt.message_id, exchange_id),
                )
                self._audit(
                    connection,
                    "MINDS_RECEIPT_HASH_MISMATCH",
                    "minds_exchange",
                    exchange_id,
                    {"blind_retry_allowed": False},
                    actor="system",
                )
                connection.commit()
            raise ValueError("Minds 运输回执的请求哈希不匹配")
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE minds_exchanges SET status='SENT', remote_conversation_id=?,
                    remote_message_id=? WHERE id=?
                """,
                (receipt.conversation_id, receipt.message_id, exchange_id),
            )
            self._audit(
                connection,
                "MINDS_REQUEST_SENT",
                "minds_exchange",
                exchange_id,
                {"credits_before": credits, "auto_outreach": False},
                actor="system",
            )
            connection.commit()
        return receipt

    async def sync_exchange(self, exchange_id: int, transport: MindsTransport) -> bool:
        with self.database.connect() as connection:
            exchange = connection.execute(
                "SELECT * FROM minds_exchanges WHERE id=?", (exchange_id,)
            ).fetchone()
        if exchange is None or exchange["status"] not in {"SENT", "UNCERTAIN"}:
            raise ValueError("只能查询已发送或结果未知的请求")
        if not exchange["remote_conversation_id"]:
            raise ValueError("结果未知且缺少会话证据；不得盲目重发")
        receipt = SendReceipt(
            str(exchange["session_alias"]),
            str(exchange["remote_conversation_id"]),
            str(exchange["remote_message_id"] or ""),
            str(exchange["request_hash"]),
        )
        reply = await transport.find_reply(
            receipt, str(exchange["request_id"]), str(exchange["request_hash"])
        )
        if reply is None:
            return False
        self._accept_verified_minds_response(exchange_id, reply)
        return True

    def decide_experiment(self, experiment_id: int, approved: bool) -> None:
        self.assert_not_paused()
        desired = "APPROVED" if approved else "REJECTED"
        with self.database.connect() as connection:
            experiment = connection.execute(
                "SELECT * FROM growth_experiments WHERE id=?", (experiment_id,)
            ).fetchone()
            if experiment is None or experiment["status"] != "PENDING_REVIEW":
                raise ValueError("实验计划不存在或已决策")
            plan = json.loads(str(experiment["seven_day_plan_json"]))
            if approved and (
                not isinstance(plan, dict)
                or not isinstance(plan.get("days"), list)
                or len(plan["days"]) != 7
            ):
                raise ValueError("尚无严格校验的七天计划，不能批准")
            connection.execute(
                "UPDATE growth_experiments SET status=?, decided_at=? WHERE id=?",
                (desired, utc_now(), experiment_id),
            )
            self._audit(
                connection,
                f"EXPERIMENT_{desired}",
                "growth_experiment",
                experiment_id,
                {
                    "auto_posted": False,
                    "auto_outreach": False,
                    "manual_execution_required": approved,
                },
            )
            connection.commit()

    def mark_review(self, experiment_id: int) -> None:
        self.assert_not_paused()
        with self.database.connect() as connection:
            experiment = connection.execute(
                "SELECT * FROM growth_experiments WHERE id=?", (experiment_id,)
            ).fetchone()
            if experiment is None or experiment["status"] != "PENDING_REVIEW":
                raise ValueError("只能记录待审核实验的复核")
            connection.execute(
                """
                UPDATE growth_experiments SET follow_up_count=follow_up_count+1,
                    last_follow_up_at=? WHERE id=?
                """,
                (utc_now(), experiment_id),
            )
            self._audit(
                connection,
                "WHY_NOW_REVIEW_LOGGED",
                "growth_experiment",
                experiment_id,
                {"external_action": False},
            )
            connection.commit()

    def record_result(self, experiment_id: int, observed_result: str) -> None:
        """Record a creator-observed result; never infer or fetch one automatically."""
        self.assert_not_paused()
        safe_result = clean_text(observed_result, "observed_result", 1_500)
        with self.database.connect() as connection:
            experiment = connection.execute(
                "SELECT status FROM growth_experiments WHERE id=?", (experiment_id,)
            ).fetchone()
            if experiment is None or experiment["status"] not in {
                "PENDING_REVIEW",
                "APPROVED",
            }:
                raise ValueError("只能为待审核或已批准实验记录结果")
            connection.execute(
                "UPDATE growth_experiments SET observed_result=? WHERE id=?",
                (safe_result, experiment_id),
            )
            self._audit(
                connection,
                "EXPERIMENT_RESULT_RECORDED",
                "growth_experiment",
                experiment_id,
                {"creator_supplied": True, "external_action": False},
            )
            connection.commit()

    def dashboard(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            hypotheses = [
                row_dict(row)
                for row in connection.execute(
                    """
                    SELECT h.*, s.week_label FROM audience_hypotheses h
                    JOIN weekly_snapshots s ON s.id=h.snapshot_id ORDER BY h.id DESC
                    """
                ).fetchall()
            ]
            experiments = [
                row_dict(row)
                for row in connection.execute(
                    """
                    SELECT e.*, h.segment_key, h.assumption FROM growth_experiments e
                    JOIN audience_hypotheses h ON h.id=e.hypothesis_id ORDER BY e.id DESC
                    """
                ).fetchall()
            ]
            exchanges = [
                row_dict(row)
                for row in connection.execute(
                    "SELECT * FROM minds_exchanges ORDER BY id DESC"
                ).fetchall()
            ]
            audits = [
                row_dict(row)
                for row in connection.execute(
                    "SELECT * FROM audit_events ORDER BY id DESC LIMIT 50"
                ).fetchall()
            ]
        for experiment in experiments:
            try:
                decoded = json.loads(str(experiment["seven_day_plan_json"]))
            except json.JSONDecodeError:
                decoded = {}
            experiment["days"] = decoded.get("days", []) if isinstance(decoded, dict) else []
        for exchange in exchanges:
            exchange["recalled_hypothesis"] = None
            response_json = exchange.get("response_json")
            if isinstance(response_json, str) and response_json:
                try:
                    response = json.loads(response_json)
                except json.JSONDecodeError:
                    continue
                recalled = (
                    response.get("recalled_hypothesis")
                    if isinstance(response, dict)
                    else None
                )
                if isinstance(recalled, str):
                    exchange["recalled_hypothesis"] = recalled
        return {
            "paused": self.is_paused(),
            "auto_outreach": False,
            "snapshots": self.list_snapshots(),
            "metrics": self.list_metrics(),
            "hypotheses": hypotheses,
            "experiments": experiments,
            "exchanges": exchanges,
            "audits": audits,
        }
