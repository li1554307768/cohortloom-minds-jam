from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

HYPOTHESIS_FORM = {
    "segment_key": "quiet_creators",
    "assumption": "Practical teardown posts activate quiet viewers.",
    "evidence_basis": "Synthetic saves and qualified replies rose.",
    "risk_note": "Small synthetic sample.",
}


def create_web_hypothesis(client: TestClient, app: object, token: str) -> int:
    client.post("/demo/load", data={"csrf_token": token})
    snapshot = app.state.service.list_snapshots()[0]["id"]  # type: ignore[attr-defined]
    response = client.post(
        "/hypotheses",
        data={"csrf_token": token, "snapshot_id": snapshot, **HYPOTHESIS_FORM},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(app.state.service.dashboard()["hypotheses"][0]["id"])  # type: ignore[attr-defined]


def test_web_hypothesis_approval_pause_and_unconfigured_minds(tmp_path: Path) -> None:
    app = create_app(Settings(database_path=tmp_path / "web.db"))
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "CohortLoom" in home.text
        assert "Auto-post: OFF · Outreach: OFF" in home.text
        assert "not an inbox" in home.text.lower()
        token = client.cookies["cohortloom_csrf"]
        hypothesis = create_web_hypothesis(client, app, token)
        approved = client.post(
            f"/hypotheses/{hypothesis}/approve",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert approved.status_code == 303
        exchange = int(app.state.service.dashboard()["exchanges"][0]["id"])
        send = client.post(
            f"/minds/{exchange}/send",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert "error=" in send.headers["location"]
        sync = client.post(
            f"/minds/{exchange}/sync",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert "error=" in sync.headers["location"]
        paused = client.post(
            "/pause",
            data={"csrf_token": token, "paused": "1"},
            follow_redirects=False,
        )
        assert paused.status_code == 303
        health = client.get("/health").json()
        assert health["status"] == "paused"
        assert health["auto_post"] is False
        assert health["auto_outreach"] is False
        resumed = client.post(
            "/pause",
            data={"csrf_token": token, "paused": "0"},
            follow_redirects=False,
        )
        assert resumed.status_code == 303


def test_web_reject_and_invalid_create(tmp_path: Path) -> None:
    app = create_app(Settings(database_path=tmp_path / "reject.db"))
    with TestClient(app) as client:
        client.get("/")
        token = client.cookies["cohortloom_csrf"]
        hypothesis = create_web_hypothesis(client, app, token)
        rejected = client.post(
            f"/hypotheses/{hypothesis}/reject",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert rejected.status_code == 303
        assert app.state.service.dashboard()["hypotheses"][0]["status"] == "REJECTED"
        bad = client.post(
            "/hypotheses",
            data={"csrf_token": token, "snapshot_id": 0, **HYPOTHESIS_FORM},
            follow_redirects=False,
        )
        assert "error=" in bad.headers["location"]


def test_web_experiment_review_approve_and_reject_routes(tmp_path: Path) -> None:
    app = create_app(Settings(database_path=tmp_path / "experiments.db"))
    with TestClient(app) as client:
        client.get("/")
        token = client.cookies["cohortloom_csrf"]
        first = create_web_hypothesis(client, app, token)
        second = create_web_hypothesis(client, app, token)
        days = {
            "days": [
                {
                    "day": day,
                    "channel": "x",
                    "action": "Manual bounded action.",
                    "review_checkpoint": "Human review.",
                }
                for day in range(1, 8)
            ]
        }
        with app.state.service.database.connect() as connection:
            connection.execute(
                """
                UPDATE growth_experiments SET status='PENDING_REVIEW',
                    seven_day_plan_json=? WHERE hypothesis_id IN (?, ?)
                """,
                (json.dumps(days), first, second),
            )
            connection.commit()
        experiments = app.state.service.dashboard()["experiments"]
        first_experiment = int(experiments[0]["id"])
        second_experiment = int(experiments[1]["id"])
        review = client.post(
            f"/experiments/{first_experiment}/review",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert review.status_code == 303
        result = client.post(
            f"/experiments/{first_experiment}/result",
            data={
                "csrf_token": token,
                "observed_result": "Creator-recorded synthetic result.",
            },
            follow_redirects=False,
        )
        assert result.status_code == 303
        approved = client.post(
            f"/experiments/{first_experiment}/approve",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert approved.status_code == 303
        rejected = client.post(
            f"/experiments/{second_experiment}/reject",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert rejected.status_code == 303


def test_csrf_is_required(tmp_path: Path) -> None:
    app = create_app(Settings(database_path=tmp_path / "csrf.db"))
    with TestClient(app) as client:
        response = client.post("/demo/load", data={"csrf_token": "wrong"})
        assert response.status_code == 403
