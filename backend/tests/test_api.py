import hashlib
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def app():
    return create_app(Settings())


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def auth(client):
    response = client.post("/v1/session")
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"], "Idempotency-Key": uuid4().hex}


def test_default_configuration_does_not_promise_speech(client):
    body = client.get("/v1/config").json()
    assert body["transcription_enabled"] is False
    assert body["streaming_supported"] is False
    assert body["transcription_mode"] == "disabled"
    assert body["rewrite_mode"] == "deterministic"
    assert body["feedback_enabled"] is False
    assert "api_key" not in body


def test_rewrite_roundtrip(client):
    response = client.post("/v1/communication/rewrite", headers=auth(client), json={"text": "I  did not take 0.5 tablets.", "style": "light_cleanup"})
    assert response.status_code == 200
    assert response.json()["suggestion"] == "I did not take 0.5 tablets."
    assert response.json()["original"] == "I  did not take 0.5 tablets."
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("body", [
    {}, {"text": ""}, {"text": " "}, {"text": "x" * 5001},
    {"text": "hello", "style": "paraphrase"},
    {"text": "hello", "secret": "a"}, {"text": 5}, {"text": None},
])
def test_invalid_rewrite_redacts_input(client, body):
    response = client.post("/v1/communication/rewrite", headers=auth(client), json=body)
    assert response.status_code == 422
    assert "input" not in response.text
    assert "hello" not in response.text


def test_auth_is_not_cors(client):
    response = client.post("/v1/communication/rewrite", headers={"Origin": "http://localhost:5173"}, json={"text": "hello"})
    assert response.status_code == 401


def test_untrusted_origin_rejected(client):
    assert client.post("/v1/session", headers={"Origin": "https://evil.invalid"}).status_code == 403


def test_preflight(client):
    response = client.options("/v1/session", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "Idempotency-Key" in response.headers["access-control-allow-headers"]


def test_duplicate_not_reprocessed_and_mismatch_rejected(client):
    headers = auth(client)
    url = "/v1/communication/rewrite"
    assert client.post(url, headers=headers, json={"text": "I did not."}).status_code == 200
    same = client.post(url, headers=headers, json={"text": "I did not."})
    changed = client.post(url, headers=headers, json={"text": "I did."})
    assert same.json()["error"] == "duplicate_submission"
    assert changed.json()["error"] == "idempotency_mismatch"
    assert same.status_code == changed.status_code == 409


def test_no_idempotency_key(client):
    headers = auth(client)
    del headers["Idempotency-Key"]
    assert client.post("/v1/communication/rewrite", headers=headers, json={"text": "hello"}).status_code == 400


def test_expired_session(client, app):
    headers = auth(client)
    token = headers["Authorization"][7:]
    app.state.runtime.sessions[hashlib.sha256(token.encode()).hexdigest()].expires = time.monotonic() - 1
    assert client.post("/v1/communication/rewrite", headers=headers, json={"text": "hello"}).status_code == 401


def test_session_mint_rate_limit(client):
    for _ in range(10):
        assert client.post("/v1/session").status_code == 200
    assert client.post("/v1/session").status_code == 429


def test_request_rate_limit():
    with TestClient(create_app(Settings(session_requests_per_minute=2))) as client:
        headers = auth(client)
        for i in range(3):
            headers["Idempotency-Key"] = uuid4().hex
            response = client.post("/v1/communication/rewrite", headers=headers, json={"text": "test"})
            assert response.status_code == (200 if i < 2 else 429)


def test_body_limit():
    with TestClient(create_app(Settings(max_body_bytes=100))) as client:
        assert client.post("/v1/session", content=b"x" * 101).status_code == 413


def test_feedback_disabled(client):
    assert client.post("/v1/communication/feedback", json={"category": "changed_meaning"}).status_code == 503


def test_no_fake_transcription(client):
    response = client.post("/v1/communication/transcribe", headers=auth(client), files={"audio": ("audio.wav", b"audio", "audio/wav")})
    assert response.status_code == 503
    assert response.json()["transcript"] == ""
    assert response.json()["status"] == "provider_error"


@pytest.mark.parametrize("enabled,ack,key", [(False, True, "test"), (True, False, "test"), (True, True, "")])
def test_provider_requires_all_gates(enabled, ack, key):
    assert not Settings(transcription_enabled=enabled, privacy_acknowledged=ack, api_key=key).provider_ready


def test_response_does_not_log_content(client, caplog):
    secret = "PRIVATE_SENTINEL_789"
    client.post("/v1/communication/rewrite", headers=auth(client), json={"text": secret})
    assert secret not in caplog.text


def test_state_contains_hashes_not_messages(app, client):
    message = "PRIVATE_SENTINEL_789"
    client.post("/v1/communication/rewrite", headers=auth(client), json={"text": message})
    assert message not in repr(app.state.runtime.sessions)


def test_health_and_no_cache(client):
    response = client.get("/health")
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_session_isolation(client):
    first, second = auth(client), auth(client)
    second["Idempotency-Key"] = first["Idempotency-Key"]
    for headers in (first, second):
        assert client.post("/v1/communication/rewrite", headers=headers, json={"text": "hello"}).status_code == 200
