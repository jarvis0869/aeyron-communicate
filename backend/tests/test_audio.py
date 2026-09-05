import asyncio
import io
import math
import struct
import wave
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.audio import AudioError, validate_audio
from app.config import Settings
from app.main import create_app
from tests.test_api import auth


def wav(seconds=0.3, gain=0.0):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"".join(struct.pack("<h", int(gain * 32767 * math.sin(i * math.tau * 440 / 16000))) for i in range(int(seconds * 16000))))
    return stream.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("gain,expected", [(0, "no_speech"), (0.00008, "low_quality"), (0.01, "ok"), (0.1, "ok"), (0.8, "ok")])
async def test_synthetic_signal_boundaries(gain, expected):
    assert await validate_audio(wav(gain=gain), "audio/wav", 90) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("data,mime,code", [(b"", "audio/wav", "empty_audio"), (b"garbage", "audio/wav", "invalid_audio"), (b"data", "text/plain", "unsupported_audio_type")])
async def test_invalid_audio(data, mime, code):
    with pytest.raises(AudioError) as exc:
        await validate_audio(data, mime, 90)
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_duration_mime_and_minimum():
    for data, mime, code in [(wav(0.2), "audio/ogg", "audio_mime_mismatch"), (wav(0.01), "audio/wav", "audio_too_short"), (wav(0.5), "audio/wav", "audio_too_long")]:
        with pytest.raises(AudioError) as exc:
            await validate_audio(data, mime, 0.2)
        assert exc.value.code == code


def enabled_app(**kwargs):
    app = create_app(Settings(transcription_enabled=True, privacy_acknowledged=True, api_key="synthetic-test-key", **kwargs))
    async def fake(*args):
        return "I did not take 0.5 tablets."
    app.state.transcriber = fake
    return app


def test_silence_never_sent_to_provider():
    app = enabled_app()
    async def forbidden(*args):
        raise AssertionError("provider must not be called")
    app.state.transcriber = forbidden
    with TestClient(app) as client:
        response = client.post("/v1/communication/transcribe", headers=auth(client), files={"audio": ("capture.wav", wav(), "audio/wav")})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "no_speech"
        assert response.json()["transcript"] == ""
        assert app.state.runtime.provider_calls == 0
        assert app.state.runtime.active == 0


def test_valid_audio_calls_only_test_adapter_and_duplicate_no_billing():
    app = enabled_app()
    with TestClient(app) as client:
        headers = auth(client)
        for i in range(2):
            response = client.post("/v1/communication/transcribe", headers=headers, files={"audio": ("capture.wav", wav(gain=0.1), "audio/wav")})
            assert response.status_code == (200 if i == 0 else 409), response.text
        assert app.state.runtime.provider_calls == 1
        assert app.state.runtime.active == 0


@pytest.mark.parametrize("name,data,mime,status", [
    ("capture.wav", b"bad", "audio/wav", 422),
    ("../../escape.wav", wav(), "audio/wav", 415),
    ("capture.txt", wav(), "text/plain", 415),
    ("capture.wav", b"", "audio/wav", 400),
    ("capture.ogg", wav(), "audio/ogg", 415),
    ("capture.wav", wav(0.01), "audio/wav", 422),
])
def test_invalid_uploads_cleanup_active(name, data, mime, status):
    app = enabled_app()
    with TestClient(app) as client:
        response = client.post("/v1/communication/transcribe", headers=auth(client), files={"audio": (name, data, mime)})
        assert response.status_code == status, response.text
        assert response.json()["transcript"] == ""
        assert app.state.runtime.active == app.state.runtime.provider_calls == 0


def test_provider_failure_redacted_and_slot_released():
    app = enabled_app()
    async def failed(*args):
        raise httpx.ConnectError("PRIVATE_PROVIDER_ERROR")
    app.state.transcriber = failed
    with TestClient(app) as client:
        response = client.post("/v1/communication/transcribe", headers=auth(client), files={"audio": ("capture.wav", wav(gain=0.1), "audio/wav")})
        assert response.status_code == 502
        assert "PRIVATE_PROVIDER_ERROR" not in response.text
        assert app.state.runtime.active == 0


def test_budget_and_concurrency_fail_closed():
    for option, status in [("provider_calls_per_process", 503), ("max_concurrency", 429)]:
        app = enabled_app(**{option: 0})
        with TestClient(app) as client:
            response = client.post("/v1/communication/transcribe", headers=auth(client), files={"audio": ("capture.wav", wav(gain=0.1), "audio/wav")})
            assert response.status_code == status
            assert app.state.runtime.provider_calls == 0


def test_timeout_cancels_provider():
    app = enabled_app(provider_timeout_seconds=0.01)
    cancelled = []
    async def slow(*args):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    app.state.transcriber = slow
    with TestClient(app) as client:
        response = client.post("/v1/communication/transcribe", headers=auth(client), files={"audio": ("capture.wav", wav(gain=0.1), "audio/wav")})
        assert response.status_code == 504
        assert cancelled == [True]
        assert app.state.runtime.active == 0
