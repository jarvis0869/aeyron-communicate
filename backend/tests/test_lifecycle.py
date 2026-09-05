import asyncio
import io
import json
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from app.audio import AudioError, run_decoder
from app.config import Settings
from app.main import create_app, openai_transcribe
from tests.test_api import auth
from tests.test_audio import enabled_app, wav


@pytest.mark.parametrize("kind", ["success", "silence", "invalid", "provider_failure"])
def test_upload_handles_closed_and_not_spooled_to_disk(monkeypatch, kind):
    closed = []
    original = UploadFile.close
    async def observed_close(self):
        # Starlette's in-memory spooled file must never have rolled to disk.
        assert getattr(self.file, "_rolled", False) is False
        await original(self)
        assert self.file.closed
        closed.append(True)
    monkeypatch.setattr(UploadFile, "close", observed_close)
    app = enabled_app()
    if kind == "provider_failure":
        async def failing(*args):
            raise httpx.ReadTimeout("PRIVATE")
        app.state.transcriber = failing
    data = b"invalid" if kind == "invalid" else wav(gain=0 if kind == "silence" else 0.2)
    with TestClient(app) as client:
        client.post("/v1/communication/transcribe", headers=auth(client), files={"audio": ("audio.wav", data, "audio/wav")})
    assert closed == [True]
    assert app.state.runtime.active == 0


@pytest.mark.asyncio
async def test_decoder_timeout_kills_and_reaps(monkeypatch):
    processes = []
    real_create = asyncio.create_subprocess_exec
    async def tracked(*args, **kwargs):
        process = await real_create(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", tracked)
    with pytest.raises(AudioError) as exc:
        await run_decoder([sys.executable, "-c", "import time; time.sleep(20)"], b"", 100, timeout=0.05)
    assert exc.value.code == "audio_validation_timeout"
    assert len(processes) == 1
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_decoder_output_limit_kills_and_reaps():
    with pytest.raises(AudioError) as exc:
        await run_decoder([sys.executable, "-c", "import sys; sys.stdout.write('x' * 10000)"], b"", 100)
    assert exc.value.code == "decoded_audio_too_large"


@pytest.mark.asyncio
@pytest.mark.parametrize("code,payload", [(200, {"text": "I did not."}), (401, {"error": "PRIVATE_PROVIDER_DETAIL"}), (200, {"unexpected": "secret"}), (200, {"text": 12})])
async def test_real_provider_adapter_with_mock_transport_only(monkeypatch, code, payload):
    observed = []
    async def handler(request):
        observed.append(request)
        assert str(request.url) == "https://api.openai.com/v1/audio/transcriptions"
        assert request.headers["authorization"] == "Bearer synthetic-key"
        assert b"recording.wav" in await request.aread()
        return httpx.Response(code, json=payload)
    real_client = httpx.AsyncClient
    def isolated_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", isolated_client)
    settings = Settings(api_key="synthetic-key")
    if code == 200 and isinstance(payload.get("text"), str):
        assert await openai_transcribe(wav(), "audio/wav", "en", settings) == "I did not."
    else:
        with pytest.raises(AudioError) as exc:
            await openai_transcribe(wav(), "audio/wav", None, settings)
        assert exc.value.code == "provider_error"
    assert len(observed) == 1  # No automatic retry or duplicate billing.


def test_ingress_overload_before_body_allocation():
    with TestClient(create_app(Settings(max_ingress_requests=0))) as client:
        response = client.post("/v1/session")
        assert response.status_code == 429
        assert response.json()["error"] == "server_busy"


def test_text_body_ceiling_is_smaller_than_audio():
    with TestClient(create_app(Settings())) as client:
        assert client.post("/v1/communication/rewrite", content=b"x" * 65537).status_code == 413


def test_kill_switch_is_checked_on_each_request():
    app = enabled_app()
    with TestClient(app) as client:
        headers = auth(client)
        app.state.settings.transcription_enabled = False
        result = client.post("/v1/communication/transcribe", headers=headers, files={"audio": ("audio.wav", wav(gain=0.1), "audio/wav")})
        assert result.status_code == 503
        assert app.state.runtime.provider_calls == 0


@pytest.mark.asyncio
async def test_client_disconnect_cancels_provider():
    app = enabled_app()
    cancelled = []
    started = asyncio.Event()
    async def slow(*args):
        started.set()
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    app.state.transcriber = slow
    # Acquire session through a normal in-process request, then drive raw ASGI
    # receive messages to model the disconnect while provider work is pending.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        token = (await client.post("/v1/session")).json()["token"]
    req = httpx.Request("POST", "http://test/v1/communication/transcribe", headers={"Authorization": "Bearer " + token, "Idempotency-Key": "disconnect-test"}, files={"audio": ("audio.wav", wav(gain=0.1), "audio/wav")})
    raw = req.read()
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http", "path": "/v1/communication/transcribe", "raw_path": b"/v1/communication/transcribe", "query_string": b"", "headers": req.headers.raw, "client": ("test", 123), "server": ("test", 80)}
    consumed = False
    async def receive():
        nonlocal consumed
        if not consumed:
            consumed = True
            return {"type": "http.request", "body": raw, "more_body": False}
        await started.wait()
        return {"type": "http.disconnect"}
    sent = []
    async def send(message):
        sent.append(message)
    await asyncio.wait_for(app(scope, receive, send), timeout=3)
    assert cancelled == [True]
    assert app.state.runtime.active == 0
    assert sent[0]["status"] == 499
