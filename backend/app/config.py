import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "Qwen-Hermes:latest")
    ollama_timeout: float = float(os.getenv("OLLAMA_TIMEOUT", "600"))

    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_url: str = os.getenv(
        "OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions"
    )
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    openrouter_vision_model: str = os.getenv(
        "OPENROUTER_VISION_MODEL", "openai/gpt-4o-mini"
    )

    # Comma-separated list of browser origins allowed to call the API.
    # The single-server build is same-origin and needs no entry here.
    cors_origins: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )

    # Max requests per client IP per minute to the AI endpoints (0 disables).
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))

    # When set, the AI endpoints require this key (X-API-Key header or
    # Authorization: Bearer <key>). Leave empty to run open (local/self-hosted).
    api_key: str = os.getenv("API_KEY", "")

    # Upload guardrails for untrusted files.
    max_image_pixels: int = int(os.getenv("MAX_IMAGE_PIXELS", "40000000"))
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "20"))

    @property
    def cloud_enabled(self) -> bool:
        return bool(self.openrouter_api_key.strip())

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
