"""FastAPI entrypoint for the local CohortLoom dashboard."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.db import Database
from app.minds import MindsBuilderTransport, MindsError, MindsSchemaError
from app.services import CohortLoomService

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def redirect(
    path: str = "/", *, notice: str | None = None, error: str | None = None
) -> RedirectResponse:
    query: dict[str, str] = {}
    if notice:
        query["notice"] = notice
    if error:
        query["error"] = error
    target = f"{path}?{urlencode(query)}" if query else path
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


async def checked_form(request: Request) -> Any:
    form = await request.form()
    supplied = str(form.get("csrf_token", ""))
    expected = str(request.cookies.get("cohortloom_csrf", ""))
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="表单安全校验失败，请刷新页面")
    return form


def service(request: Request) -> CohortLoomService:
    return request.app.state.service


def settings(request: Request) -> Settings:
    return request.app.state.settings


def transport(request: Request) -> MindsBuilderTransport:
    config = settings(request)
    if not config.minds_api_key or not config.mind_id:
        raise ValueError("尚未在 .env 配置 Minds；离线流程仍可完整测试")
    return MindsBuilderTransport(config.minds_api_key, config.mind_id, config.minds_base_url)


def create_app(config: Settings | None = None) -> FastAPI:
    active = config or Settings.from_env()
    database_path = active.database_path
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    app_service = CohortLoomService(Database(database_path))

    app = FastAPI(title="CohortLoom", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.service = app_service
    app.state.settings = active
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

    @app.middleware("http")
    async def local_security(request: Request, call_next: Any) -> Any:
        token = request.cookies.get("cohortloom_csrf") or secrets.token_urlsafe(32)
        request.state.csrf_token = token
        response = await call_next(request)
        if "cohortloom_csrf" not in request.cookies:
            response.set_cookie(
                "cohortloom_csrf",
                token,
                httponly=True,
                samesite="strict",
                secure=False,
                max_age=86_400,
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; img-src 'self' data:"
        )
        return response

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "paused" if app_service.is_paused() else "ok",
            "database": "local_sqlite",
            "auto_post": False,
            "auto_outreach": False,
            "minds_configured": bool(active.minds_api_key and active.mind_id),
            "credit_floor": active.credit_floor,
        }

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "request": request,
                "csrf_token": request.state.csrf_token,
                "notice": request.query_params.get("notice"),
                "error": request.query_params.get("error"),
                "state": app_service.dashboard(),
                "minds_configured": bool(active.minds_api_key and active.mind_id),
            },
        )

    @app.post("/demo/load")
    async def load_demo(request: Request) -> RedirectResponse:
        try:
            await checked_form(request)
            inserted, duplicates = app_service.load_demo(
                BASE_DIR / "data" / "synthetic_demo.json"
            )
            return redirect(
                notice=f"合成周摘要已载入：新增 {inserted} 个平台，重复 {duplicates} 个"
            )
        except ValueError as exc:
            return redirect(error=str(exc))

    @app.post("/hypotheses")
    async def create_hypothesis(request: Request) -> RedirectResponse:
        try:
            form = await checked_form(request)
            hypothesis_id = app_service.create_hypothesis(
                snapshot_id=int(str(form.get("snapshot_id", "0"))),
                segment_key=str(form.get("segment_key", "")),
                assumption=str(form.get("assumption", "")),
                evidence_basis=str(form.get("evidence_basis", "")),
                risk_note=str(form.get("risk_note", "")),
            )
            return redirect(notice=f"受众假设 #{hypothesis_id} 已记录，等待人工批准")
        except (TypeError, ValueError) as exc:
            return redirect(error=str(exc))

    @app.post("/hypotheses/{hypothesis_id}/approve")
    async def approve_hypothesis(hypothesis_id: int, request: Request) -> RedirectResponse:
        try:
            await checked_form(request)
            exchange_id = app_service.approve_hypothesis(hypothesis_id)
            return redirect(
                notice=f"假设已批准；Minds 记忆请求 #{exchange_id} 已准备但未发送"
            )
        except ValueError as exc:
            return redirect(error=str(exc))

    @app.post("/hypotheses/{hypothesis_id}/reject")
    async def reject_hypothesis(hypothesis_id: int, request: Request) -> RedirectResponse:
        try:
            await checked_form(request)
            app_service.reject_hypothesis(hypothesis_id)
            return redirect(notice="假设已拒绝；没有发送或执行实验")
        except ValueError as exc:
            return redirect(error=str(exc))

    @app.post("/experiments/{experiment_id}/approve")
    async def approve_experiment(experiment_id: int, request: Request) -> RedirectResponse:
        try:
            await checked_form(request)
            app_service.decide_experiment(experiment_id, True)
            return redirect(notice="七天实验已人工批准；仍需创作者逐日手动执行")
        except ValueError as exc:
            return redirect(error=str(exc))

    @app.post("/experiments/{experiment_id}/reject")
    async def reject_experiment(experiment_id: int, request: Request) -> RedirectResponse:
        try:
            await checked_form(request)
            app_service.decide_experiment(experiment_id, False)
            return redirect(notice="七天实验已拒绝；没有外部动作")
        except ValueError as exc:
            return redirect(error=str(exc))

    @app.post("/experiments/{experiment_id}/review")
    async def review_experiment(experiment_id: int, request: Request) -> RedirectResponse:
        try:
            await checked_form(request)
            app_service.mark_review(experiment_id)
            return redirect(notice="WHY NOW 人工复核已记录；没有发送任何消息")
        except ValueError as exc:
            return redirect(error=str(exc))

    @app.post("/experiments/{experiment_id}/result")
    async def record_result(experiment_id: int, request: Request) -> RedirectResponse:
        try:
            form = await checked_form(request)
            app_service.record_result(
                experiment_id, str(form.get("observed_result", ""))
            )
            return redirect(notice="实验结果已由创作者记录；没有外部动作")
        except ValueError as exc:
            return redirect(error=str(exc))

    @app.post("/pause")
    async def toggle_pause(request: Request) -> RedirectResponse:
        form = await checked_form(request)
        paused = str(form.get("paused", "1")) == "1"
        app_service.set_paused(paused)
        return redirect(notice="系统已暂停" if paused else "系统已恢复")

    @app.post("/minds/{exchange_id}/send")
    async def send_minds(exchange_id: int, request: Request) -> RedirectResponse:
        try:
            await checked_form(request)
            receipt = await app_service.send_exchange(
                exchange_id, transport(request), credit_floor=active.credit_floor
            )
            return redirect(
                notice=f"Minds 请求已发送（会话 {receipt.alias}）；没有发布或外联"
            )
        except (ValueError, MindsError) as exc:
            return redirect(error=str(exc))

    @app.post("/minds/{exchange_id}/sync")
    async def sync_minds(exchange_id: int, request: Request) -> RedirectResponse:
        try:
            await checked_form(request)
            found = await app_service.sync_exchange(exchange_id, transport(request))
            return redirect(notice="Minds 回复已核验" if found else "历史暂无回复；未重发")
        except (ValueError, MindsError, MindsSchemaError) as exc:
            return redirect(error=str(exc))

    return app


app = create_app()
