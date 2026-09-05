"""All credentials stay server-side; never log this settings object."""

import os
from dataclasses import dataclass, field


@dataclass(repr=False)
class Settings:
    origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    transcription_enabled: bool = False
    privacy_acknowledged: bool = False
    api_key: str = field(default="", repr=False)
    transcription_model: str = "gpt-4o-mini-transcribe"
    max_body_bytes: int = 10 * 1024 * 1024
    max_audio_bytes: int = 9 * 1024 * 1024
    max_audio_seconds: float = 90
    max_text_chars: int = 5000
    session_ttl_seconds: int = 1800
    max_sessions: int = 1000
    session_requests_per_minute: int = 60
    sessions_per_ip_per_minute: int = 10
    global_sessions_per_minute: int = 100
    max_concurrency: int = 4
    max_ingress_requests: int = 16
    provider_calls_per_process: int = 100
    provider_timeout_seconds: float = 35
    request_timeout_seconds: float = 55

    @property
    def provider_ready(self) -> bool:
        return self.transcription_enabled and self.privacy_acknowledged and bool(self.api_key)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            origins=tuple(x.strip() for x in os.getenv("AEYRON_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()),
            transcription_enabled=os.getenv("AEYRON_TRANSCRIPTION_ENABLED", "false").lower() == "true",
            privacy_acknowledged=os.getenv("AEYRON_PROVIDER_PRIVACY_ACKNOWLEDGED", "false").lower() == "true",
            api_key=os.getenv("OPENAI_API_KEY", ""),
            transcription_model=os.getenv("AEYRON_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"),
        )
