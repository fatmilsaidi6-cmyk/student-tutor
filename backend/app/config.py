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

    # Max AI requests per user (or IP when signed out) per UTC day (0 disables).
    daily_quota: int = int(os.getenv("DAILY_QUOTA", "100"))

    # When set, the AI endpoints require this key (X-API-Key header or
    # Authorization: Bearer <key>). Leave empty to run open (local/self-hosted).
    api_key: str = os.getenv("API_KEY", "")

    # Upload guardrails for untrusted files.
    max_image_pixels: int = int(os.getenv("MAX_IMAGE_PIXELS", "40000000"))
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "20"))

    # --- OAuth sign-in (Google / GitHub) ---
    # Signing key for the session cookie. Set a long random value in production.
    session_secret: str = os.getenv("SESSION_SECRET", "dev-insecure-change-me")
    # Public base URL of the deployment (used to build OAuth redirect URIs and
    # to decide whether the session cookie is Secure). e.g. https://app.fly.dev
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    github_client_id: str = os.getenv("GITHUB_CLIENT_ID", "")
    github_client_secret: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    # Optional comma-separated allowlist of emails. Empty = allow any signed-in user.
    allowed_emails: str = os.getenv("ALLOWED_EMAILS", "")

    # Trust the client IP from X-Forwarded-For / Fly-Client-IP (set behind a proxy).
    trust_proxy: bool = os.getenv("TRUST_PROXY", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    @property
    def cloud_enabled(self) -> bool:
        return bool(self.openrouter_api_key.strip())

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def oauth_providers(self) -> list[str]:
        providers: list[str] = []
        if self.google_client_id and self.google_client_secret:
            providers.append("google")
        if self.github_client_id and self.github_client_secret:
            providers.append("github")
        return providers

    @property
    def oauth_enabled(self) -> bool:
        return bool(self.oauth_providers)

    @property
    def allowed_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()]

    @property
    def cookie_secure(self) -> bool:
        return self.public_base_url.startswith("https://")


settings = Settings()
