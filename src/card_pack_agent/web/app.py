"""Eval UI — FastAPI + Jinja2.

Routes:
  GET  /                           list packs
  GET  /packs/{pack_id}            detail view (strategy, cards, script, evaluator, judge)
  POST /api/generate               trigger new pack generation (form-encoded)
  POST /api/judge-rerun/{pack_id}  rerun judge once, append to artifact
  POST /api/image/{pack_id}        generate single image for a card via provider dropdown
  GET  /api/providers              list registered image providers
  GET  /generated/{rest:path}      serve local generated images

Kickoff:
  uvicorn card_pack_agent.web.app:app --reload --port 8000
  (or `python scripts/run_web.py`)
"""
from __future__ import annotations

import json
from pathlib import Path

import structlog
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import feedback as feedback_mod
from ..config import settings
from ..orchestrator import (
    ARTIFACTS_DIR,
    _dump_artifact,
    list_artifacts,
    load_artifact,
    run as orchestrator_run,
)
from ..schemas import Pack, TopicInput
from ..tools import evaluator as evaluator_mod
from ..tools.image.base import GenerationParams, ProviderName
from ..tools.image.registry import get_provider, list_providers

log = structlog.get_logger()

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="card-pack-agent eval", version="0.1.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve generated images (so <img src="/generated/mock/xxx.png"> works)
settings.storage_local_path.mkdir(parents=True, exist_ok=True)
app.mount(
    "/generated",
    StaticFiles(directory=str(settings.storage_local_path)),
    name="generated",
)


# --- HTML routes ---


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    summaries = list_artifacts()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "packs": summaries,
            "app_mode": settings.app_mode.value,
            "providers": [p.value for p in list_providers()],
        },
    )


@app.get("/packs/{pack_id}", response_class=HTMLResponse)
def pack_detail(request: Request, pack_id: str) -> HTMLResponse:
    data = load_artifact(pack_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"pack {pack_id} not found")
    fb_summary = feedback_mod.summary_for_pack(pack_id)
    fb_events = feedback_mod.load_for_pack(pack_id)
    return templates.TemplateResponse(
        "pack_detail.html",
        {
            "request": request,
            "data": data,
            "providers": [p.value for p in list_providers()],
            "app_mode": settings.app_mode.value,
            "feedback_summary": fb_summary,
            "feedback_events": fb_events,
        },
    )


# --- API routes ---


@app.get("/api/providers")
def api_providers() -> dict:
    return {"providers": [p.value for p in list_providers()]}


@app.post("/api/generate")
def api_generate(
    topic: str = Form(...),
    category: str | None = Form(None),
    mechanism: str | None = Form(None),
    generate_images: bool = Form(False),
) -> RedirectResponse:
    """Trigger a full pack generation. Blocking — returns redirect to detail page.

    In mock mode this is fast (<1s). In dev mode this costs ~$0.5-0.9 and takes
    3-7 minutes — the client will hang in the browser; acceptable for an internal
    single-operator tool.
    """
    category_v = category.strip() or None if category else None
    mechanism_v = mechanism.strip() or None if mechanism else None

    result = orchestrator_run(
        TopicInput(raw_topic=topic.strip()),
        hint_l1=category_v,
        hint_l2=mechanism_v,
        generate_images=generate_images,
    )

    if result.pack is None:
        return JSONResponse(
            status_code=500,
            content={
                "error": result.fatal_error or "generation failed with no pack",
                "cost": result.cost.as_dict(),
            },
        )

    return RedirectResponse(url=f"/packs/{result.pack.pack_id}", status_code=303)


@app.post("/api/judge-rerun/{pack_id}")
def api_judge_rerun(pack_id: str) -> dict:
    """Run Judge once more on an existing pack. Appends to artifact under judge_reruns."""
    data = load_artifact(pack_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"pack {pack_id} not found")

    pack = Pack.model_validate(data["pack"])
    scores = evaluator_mod.judge_with_llm(pack)

    # Append to artifact
    reruns = data.setdefault("judge_reruns", [])
    reruns.append(scores)
    path = ARTIFACTS_DIR / f"{pack_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"pack_id": pack_id, "scores": scores, "n_reruns": len(reruns)}


@app.post("/api/image/{pack_id}")
def api_image(
    pack_id: str,
    provider: str = Form(...),
    position: int = Form(...),
) -> dict:
    """Generate a single card's image via the selected provider.

    Reads the card's visual prompt from the artifact. Stores the result back
    into artifact["rendered_images"][str(position)][provider].
    """
    data = load_artifact(pack_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"pack {pack_id} not found")

    cards = data.get("pack", {}).get("cards", [])
    card = next((c for c in cards if c.get("position") == position), None)
    if card is None:
        raise HTTPException(status_code=404, detail=f"card position {position} not found")

    try:
        provider_name = ProviderName(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider}")

    provider_inst = get_provider(provider_name)
    params = GenerationParams(
        prompt=card.get("prompt", ""),
        negative_prompt=card.get("negative_prompt", ""),
        aspect_ratio="9:16",
    )
    result = provider_inst.generate(params)

    rendered = data.setdefault("rendered_images", {})
    slot = rendered.setdefault(str(position), {})
    slot[provider] = {
        "ok": result.ok,
        "image_url": result.image_url,
        "error": result.error,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
        "model": result.model,
    }
    path = ARTIFACTS_DIR / f"{pack_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Make the local image URL web-accessible
    web_url = _local_to_web_url(result.image_url)
    return {
        "ok": result.ok,
        "error": result.error,
        "image_url": web_url,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
        "provider": provider,
        "position": position,
        "model": result.model,
    }


@app.post("/api/feedback/pack/{pack_id}")
def api_feedback_pack(
    pack_id: str,
    event: str = Form(...),          # "pack_reject" | "pack_approve"
    reason: str = Form(""),
    tags: str = Form(""),             # comma-separated
) -> dict:
    if event not in ("pack_reject", "pack_approve"):
        raise HTTPException(status_code=400, detail=f"invalid event: {event}")
    if load_artifact(pack_id) is None:
        raise HTTPException(status_code=404, detail=f"pack {pack_id} not found")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    entry = feedback_mod.record(
        pack_id=pack_id, event=event, reason=reason, tags=tag_list,
    )
    return {"ok": True, "entry": entry}


@app.post("/api/feedback/card/{pack_id}/{position}")
def api_feedback_card(
    pack_id: str,
    position: int,
    event: str = Form(...),          # "card_reject" | "card_approve"
    reason: str = Form(""),
    tags: str = Form(""),
) -> dict:
    if event not in ("card_reject", "card_approve"):
        raise HTTPException(status_code=400, detail=f"invalid event: {event}")
    data = load_artifact(pack_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"pack {pack_id} not found")
    cards = data.get("pack", {}).get("cards", [])
    if not any(c.get("position") == position for c in cards):
        raise HTTPException(status_code=404, detail=f"position {position} not found")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    entry = feedback_mod.record(
        pack_id=pack_id, event=event, reason=reason,
        position=position, tags=tag_list,
    )
    return {"ok": True, "entry": entry}


@app.get("/api/feedback/export")
def api_feedback_export() -> JSONResponse:
    """Dump all collected feedback. Handy for `curl | jq` analysis."""
    return JSONResponse(content={"events": feedback_mod.load_all()})


@app.post("/api/backfill")
def api_backfill() -> dict:
    """One-shot helper: import F:/card-pack-agent/tmp_pack.json into artifacts if present."""
    tmp_path = Path(__file__).resolve().parents[3] / "tmp_pack.json"
    if not tmp_path.exists():
        return {"ok": False, "reason": "tmp_pack.json not present"}
    try:
        raw = tmp_path.read_text(encoding="utf-8")
        pack = Pack.model_validate_json(raw)
    except Exception as e:
        return {"ok": False, "reason": f"parse failed: {e}"}

    from ..orchestrator import CostSummary
    _dump_artifact(
        pack=pack,
        report=None,
        cost=CostSummary(),
        topic_input=TopicInput(raw_topic=pack.topic),
        hint_l1=None,
        hint_l2=None,
    )
    return {"ok": True, "pack_id": str(pack.pack_id)}


# --- helpers ---


def _local_to_web_url(local_path: str) -> str:
    """Convert an absolute file path under storage_local_path to a /generated/... URL."""
    if not local_path:
        return ""
    try:
        p = Path(local_path).resolve()
        base = settings.storage_local_path.resolve()
        rel = p.relative_to(base)
        return "/generated/" + str(rel).replace("\\", "/")
    except (ValueError, OSError):
        return local_path
