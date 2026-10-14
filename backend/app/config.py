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

    @property
    def cloud_enabled(self) -> bool:
        return bool(self.openrouter_api_key.strip())


settings = Settings()
