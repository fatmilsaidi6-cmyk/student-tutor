"""AI backends: local Ollama (private) + OpenRouter cloud, with hybrid routing."""

from __future__ import annotations

import base64

import httpx

from .config import settings
from .prompts import build_system_prompt, build_user_prompt

VISION_PROMPT = (
    "You are an OCR + layout engine for a student's homework. "
    "Transcribe ALL readable text exactly as written, including numbers, symbols, "
    "and mathematical notation (write equations inline, e.g. 2x + 3 = 7). "
    "If there are diagrams, describe them briefly in [brackets]. "
    "If multiple questions are present, label them Q1, Q2, etc. "
    "Output only the transcription, nothing else."
)


def _cloud_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Student Tutor",
    }


async def _chat(
    url: str,
    model: str,
    messages: list,
    headers: dict,
    temperature: float = 0.4,
    timeout: float = 240.0,
) -> str:
    payload = {"model": model, "messages": messages, "temperature": temperature}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return (data["choices"][0]["message"].get("content") or "").strip()


def make_cloud_vision_reader():
    """Return a sync callable(images: list[bytes]) -> text, or None if no key."""
    if not settings.cloud_enabled:
        return None

    def reader(images: list[bytes]) -> str:
        content = [{"type": "text", "text": VISION_PROMPT}]
        for b in images[:8]:
            b64 = base64.b64encode(b).decode()
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                }
            )
        messages = [{"role": "user", "content": content}]
        payload = {"model": settings.openrouter_vision_model, "messages": messages}
        with httpx.Client(timeout=240.0) as client:
            resp = client.post(
                settings.openrouter_url,
                json=payload,
                headers=_cloud_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return (data["choices"][0]["message"].get("content") or "").strip()

    return reader


async def _explain_local(messages: list) -> str:
    url = f"{settings.ollama_base_url.rstrip('/')}/v1/chat/completions"
    return await _chat(
        url,
        settings.ollama_model,
        messages,
        headers={},
        timeout=settings.ollama_timeout,
    )


async def _explain_cloud(messages: list) -> str:
    return await _chat(
        settings.openrouter_url,
        settings.openrouter_model,
        messages,
        headers=_cloud_headers(),
    )


async def _route(messages: list, engine: str) -> tuple[str, str]:
    """Route a message list to the right backend. Returns (text, engine_used)."""
    if engine == "local":
        return await _explain_local(messages), "local"

    if engine == "cloud":
        if not settings.cloud_enabled:
            raise RuntimeError("Cloud engine requested but OPENROUTER_API_KEY is not set.")
        return await _explain_cloud(messages), "cloud"

    # auto: prefer cloud when available, fall back to the local model.
    if settings.cloud_enabled:
        try:
            return await _explain_cloud(messages), "cloud"
        except Exception:  # noqa: BLE001
            return await _explain_local(messages), "local (cloud fallback)"

    return await _explain_local(messages), "local"


async def explain(
    extracted_text: str,
    level: str,
    subject: str | None,
    question: str | None,
    engine: str = "auto",
) -> tuple[str, str]:
    """First explanation of a piece of homework. Returns (explanation, engine_used)."""
    system = build_system_prompt(level, subject)
    user = build_user_prompt(extracted_text, question, level)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return await _route(messages, engine)


async def followup(
    context: str,
    history: list,
    level: str,
    subject: str | None,
    engine: str = "auto",
) -> tuple[str, str]:
    """Answer a follow-up question in the ongoing thread.

    `history` is the prior conversation (role/content dicts, oldest first); the
    homework text is injected into the system prompt so the tutor keeps context.
    """
    system = build_system_prompt(level, subject)
    if context.strip():
        system += (
            "\n\nThe student's homework (for your reference in this conversation):\n"
            "---\n" + context.strip() + "\n---"
        )
    messages = [{"role": "system", "content": system}, *history]
    return await _route(messages, engine)
