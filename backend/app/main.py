from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import ai
from .auth import require_access
from .auth import router as auth_router
from .config import settings
from .extract import read_homework
from .rate_limit import RateLimitMiddleware

ALLOWED_LEVELS = {"primary", "middle", "high", "university"}
ALLOWED_ENGINES = {"auto", "local", "cloud"}
MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_FILES = 10

# Built React app (frontend/dist), served by this same server in production.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class ChatMessage(BaseModel):
    role: str
    content: str


class FollowupRequest(BaseModel):
    context: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    level: str = "high"
    subject: str = ""
    engine: str = "auto"

app = FastAPI(title="Student Tutor API", version="0.1.0")

# Middleware order: the last one added is the outermost. We want
# CORS (outermost, so its headers reach even 429 responses) -> Session
# (so the rate limiter can see who the user is) -> rate limiting -> routes.
app.add_middleware(
    RateLimitMiddleware,
    limit_per_minute=settings.rate_limit_per_minute,
    daily_quota=settings.daily_quota,
    store_path=settings.limits_db or None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=settings.cookie_secure,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Quota-Limit", "X-Quota-Remaining"],
)

app.include_router(auth_router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "cloud_enabled": settings.cloud_enabled,
        "auth_required": settings.auth_enabled or settings.oauth_enabled,
        "api_key_required": settings.auth_enabled,
        "oauth_providers": settings.oauth_providers,
        "ollama_model": settings.ollama_model,
        "openrouter_model": settings.openrouter_model,
        "openrouter_vision_model": settings.openrouter_vision_model,
    }


@app.post("/api/explain", dependencies=[Depends(require_access)])
async def explain(
    text: str = Form(""),
    files: list[UploadFile] | None = File(None),
    level: str = Form("high"),
    subject: str = Form(""),
    question: str = Form(""),
    engine: str = Form("auto"),
) -> dict:
    if level not in ALLOWED_LEVELS:
        raise HTTPException(400, f"level must be one of {sorted(ALLOWED_LEVELS)}")
    if engine not in ALLOWED_ENGINES:
        raise HTTPException(400, f"engine must be one of {sorted(ALLOWED_ENGINES)}")

    typed = (text or "").strip()
    file_list = [f for f in (files or []) if f and f.filename]

    if not typed and not file_list:
        raise HTTPException(
            400, "Type the problem/work, or add a photo or PDF of it."
        )
    if len(file_list) > MAX_FILES:
        raise HTTPException(400, f"Too many files (max {MAX_FILES}).")

    cloud_reader = ai.make_cloud_vision_reader()
    texts: list[str] = []
    methods: set[str] = set()

    if typed:
        texts.append(typed)
        methods.add("typed")

    for f in file_list:
        data = await f.read()
        if not data:
            continue
        if len(data) > MAX_BYTES:
            raise HTTPException(413, f"{f.filename or 'file'} is too large (max 20 MB).")
        try:
            ocr_text, method = await run_in_threadpool(
                read_homework, f.filename or "upload", data, cloud_reader
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, f"Could not read {f.filename or 'the file'}: {exc}") from exc
        if ocr_text.strip():
            texts.append(ocr_text.strip())
        methods.add(method)

    if not texts:
        raise HTTPException(422, "No readable text was found in the uploaded file(s).")

    extracted_text = "\n\n".join(texts)
    read_method = " + ".join(sorted(methods))

    try:
        explanation, engine_used = await ai.explain(
            extracted_text=extracted_text,
            level=level,
            subject=subject.strip() or None,
            question=question.strip() or None,
            engine=engine,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"The AI backend failed: {exc}") from exc

    return {
        "explanation": explanation,
        "extracted_text": extracted_text,
        "read_method": read_method,
        "engine_used": engine_used,
        "level": level,
        "subject": subject or None,
        "file_count": len(file_list),
    }


@app.post("/api/followup", dependencies=[Depends(require_access)])
async def followup(payload: FollowupRequest) -> dict:
    if payload.level not in ALLOWED_LEVELS:
        raise HTTPException(400, f"level must be one of {sorted(ALLOWED_LEVELS)}")
    if payload.engine not in ALLOWED_ENGINES:
        raise HTTPException(400, f"engine must be one of {sorted(ALLOWED_ENGINES)}")
    if not payload.messages:
        raise HTTPException(400, "A follow-up question is required.")

    try:
        answer, engine_used = await ai.followup(
            context=payload.context,
            history=[m.model_dump() for m in payload.messages],
            level=payload.level,
            subject=payload.subject.strip() or None,
            engine=payload.engine,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"The AI backend failed: {exc}") from exc

    return {"answer": answer, "engine_used": engine_used}


# ---------------------------------------------------------------------------
# Serve the built frontend (single-server production mode).  API routes are
# registered above, so they always take precedence over the SPA catch-all.
# ---------------------------------------------------------------------------
if (FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )


@app.get("/{full_path:path}")
async def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")

    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(
            503,
            "Frontend build not found. Run 'npm run build' in frontend/ "
            "(or the VS Code task 'app: build + run').",
        )

    candidate = FRONTEND_DIST / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(index)
