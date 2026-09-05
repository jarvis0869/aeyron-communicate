"""Single-worker public-preview API. No clinical model or persisted user content."""

import asyncio
import hashlib
import json
import re
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartParser

from .audio import AudioError, MIME_FORMATS, validate_audio
from .config import Settings
from .safety import light_cleanup


class RewriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=5000)
    style: Literal["light_cleanup"] = "light_cleanup"


@dataclass
class Session:
    expires: float
    requests: deque = field(default_factory=deque)
    # Store fingerprints and state, never response text. Duplicates are refused.
    submissions: dict = field(default_factory=dict)


class State:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.mint_events: deque = deque()
        self.active = 0
        self.provider_calls = 0


class BodyLimit(Exception):
    pass


@asynccontextmanager
async def closing_form(form):
    try:
        yield form
    finally:
        await form.close()


class SafetyMiddleware:
    """Bound all request bytes before multipart parsing, redact all unhandled errors."""

    def __init__(self, app, settings):
        self.app, self.settings = app, settings
        self.ingress = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # ASGI headers are case-insensitive. Normalize the scope before Starlette
        # Request objects read Authorization and Idempotency-Key.
        scope["headers"] = [(key.lower(), value) for key, value in scope["headers"]]
        if self.ingress >= self.settings.max_ingress_requests:
            return await JSONResponse({"error": "server_busy"}, status_code=429, headers={"Cache-Control": "no-store"})(scope, receive, send)
        self.ingress += 1
        try:
            return await self.handle_http(scope, receive, send)
        finally:
            self.ingress -= 1

    async def handle_http(self, scope, receive, send):
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        body_ceiling = self.settings.max_body_bytes if scope["path"] == "/v1/communication/transcribe" else min(self.settings.max_body_bytes, 65536)
        origin = headers.get("origin")
        response_headers = {
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
        }
        if origin and origin in self.settings.origins:
            response_headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin"})
        async def error(status, code):
            await JSONResponse({"error": code}, status_code=status, headers=response_headers)(scope, receive, send)
        if origin and origin not in self.settings.origins:
            return await error(403, "origin_not_allowed")
        if scope["method"] == "OPTIONS":
            response_headers.update({"Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "Authorization, Content-Type, Idempotency-Key", "Access-Control-Max-Age": "600"})
            return await JSONResponse({}, headers=response_headers)(scope, receive, send)
        # Reject conflicting framing at application boundary. Edge must normalize it.
        if headers.get("content-length") and headers.get("transfer-encoding"):
            return await error(400, "invalid_framing")
        try:
            if int(headers.get("content-length", "0")) > body_ceiling:
                return await error(413, "request_too_large")
        except ValueError:
            return await error(400, "invalid_length")
        messages, size, chunks = [], 0, 0
        try:
            async with asyncio.timeout(15):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    size += len(message.get("body", b""))
                    chunks += 1
                    if size > body_ceiling or chunks > 1024:
                        return await error(413, "request_too_large")
                    messages.append(message)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await error(408, "upload_timeout")
        index, started = 0, False
        async def replay():
            nonlocal index
            if index < len(messages):
                value = messages[index]
                index += 1
                return value
            return await receive()
        async def safe_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                current = list(message.get("headers", []))
                current.extend((k.lower().encode(), v.encode()) for k, v in response_headers.items())
                message["headers"] = current
            await send(message)
        try:
            async with asyncio.timeout(self.settings.request_timeout_seconds):
                await self.app(scope, replay, safe_send)
        except TimeoutError:
            if not started:
                await error(504, "request_timeout")
        except Exception:
            # Do not expose exception bodies, filenames, provider responses or input.
            if not started:
                await error(500, "request_failed")


async def openai_transcribe(data: bytes, mime: str, language: str | None, settings: Settings) -> str:
    fields = {"model": settings.transcription_model, "response_format": "json"}
    if language:
        fields["language"] = language
    async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds, follow_redirects=False, trust_env=False) as client:
        # Do not retry: a network failure does not prove the provider did not bill.
        async with client.stream("POST", "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.api_key}"}, data=fields,
            files={"file": ("recording" + MIME_FORMATS[mime][1], data, mime)}) as response:
            if response.status_code != 200:
                raise AudioError("provider_error", 502)
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise AudioError("provider_error", 502)
            try:
                payload = json.loads(raw)
                text = payload["text"]
                if not isinstance(text, str) or len(text) > settings.max_text_chars:
                    raise ValueError()
                return text
            except (ValueError, KeyError, TypeError):
                raise AudioError("provider_error", 502) from None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Aeyron communication API", docs_url=None, redoc_url=None)
    app.add_middleware(SafetyMiddleware, settings=settings)
    state = State()
    app.state.runtime = state
    app.state.settings = settings
    app.state.transcriber = openai_transcribe

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse({"error": "invalid_request"}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    def prune():
        now = time.monotonic()
        for key in [key for key, session in state.sessions.items() if session.expires <= now]:
            del state.sessions[key]
        while state.mint_events and state.mint_events[0][0] <= now - 60:
            state.mint_events.popleft()

    def session_for(request):
        prune()
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        session = state.sessions.get(hashlib.sha256(token.encode()).hexdigest())
        if not session:
            raise HTTPException(401, "session_required")
        now = time.monotonic()
        while session.requests and session.requests[0] <= now - 60:
            session.requests.popleft()
        if len(session.requests) >= settings.session_requests_per_minute:
            raise HTTPException(429, "rate_limited")
        session.requests.append(now)
        return session

    def reserve(request, session, content):
        key = request.headers.get("idempotency-key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
            raise HTTPException(400, "idempotency_key_required")
        fingerprint = hashlib.sha256(content).hexdigest()
        previous = session.submissions.get(key)
        if previous:
            raise HTTPException(409, "duplicate_submission" if previous == fingerprint else "idempotency_mismatch")
        if len(session.submissions) >= 120:
            raise HTTPException(429, "session_submission_limit")
        session.submissions[key] = fingerprint

    @app.get("/health")
    @app.get("/v1/health")
    async def health():
        return {"status": "ok", "transcription_configured": settings.provider_ready}

    @app.get("/v1/config")
    async def config():
        available = settings.provider_ready and bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))
        return {
            "transcription_enabled": available,
            "transcription_mode": "batch" if available else "disabled",
            "rewrite_mode": "deterministic", "feedback_enabled": False,
            "processor": "OpenAI" if available else None,
            "retention_notice": "Audio is processed in application memory and sent to OpenAI only when transcription is enabled. Application cleanup does not determine provider retention. Notebook content is never uploaded.",
            "max_audio_seconds": settings.max_audio_seconds, "max_audio_bytes": settings.max_audio_bytes,
            "max_text_chars": settings.max_text_chars, "streaming_supported": False,
        }

    @app.post("/v1/session")
    async def new_session(request: Request):
        prune()
        # Never trust forwarded IP headers. Production proxy must enforce ingress rates.
        peer = request.client.host if request.client else "unknown"
        ip_hash = hashlib.sha256(peer.encode()).hexdigest()
        if len(state.sessions) >= settings.max_sessions or len(state.mint_events) >= settings.global_sessions_per_minute or sum(ip == ip_hash for _, ip in state.mint_events) >= settings.sessions_per_ip_per_minute:
            raise HTTPException(429, "session_rate_limited")
        token = secrets.token_urlsafe(32)
        state.sessions[hashlib.sha256(token.encode()).hexdigest()] = Session(time.monotonic() + settings.session_ttl_seconds)
        state.mint_events.append((time.monotonic(), ip_hash))
        return {"token": token, "expires_in": settings.session_ttl_seconds}

    @app.post("/v1/communication/rewrite")
    async def rewrite(body: RewriteInput, request: Request):
        session = session_for(request)
        if not body.text.strip() or len(body.text) > settings.max_text_chars:
            raise HTTPException(422, "empty_or_oversized_text")
        reserve(request, session, ("rewrite:" + body.text).encode())
        suggestion, warnings, risk = light_cleanup(body.text)
        return {"request_id": secrets.token_hex(12), "original": body.text, "suggestion": suggestion, "warnings": warnings, "meaning_risk": risk}

    @app.post("/v1/communication/transcribe")
    async def transcribe(request: Request):
        session = session_for(request)
        request_id = secrets.token_hex(12)
        def result(status, warnings=None, text="", http_status=200):
            return JSONResponse({"request_id": request_id, "transcript": text, "status": status, "warnings": warnings or []}, status_code=http_status)
        if not settings.provider_ready:
            return result("provider_error", ["transcription_not_configured"], http_status=503)
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            return result("provider_error", ["audio_validator_unavailable"], http_status=503)
        if state.active >= settings.max_concurrency:
            return result("provider_error", ["busy_try_later"], http_status=429)
        state.active += 1
        try:
            # Parser spool threshold stays above the already enforced body ceiling:
            # multipart audio remains in memory; explicit context closes all uploads.
            class MemoryParser(MultiPartParser):
                spool_max_size = settings.max_body_bytes + 1
            parser = MemoryParser(request.headers, request.stream(), max_files=1, max_fields=1, max_part_size=1024)
            try:
                form = await parser.parse()
            except Exception:
                raise AudioError("invalid_multipart", 400) from None
            async with closing_form(form):
                audio = form.get("audio")
                language = form.get("language")
                if set(form.keys()) - {"audio", "language"} or not isinstance(audio, UploadFile):
                    raise AudioError("audio_required", 400)
                if language is not None and (not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}", language)):
                    raise AudioError("invalid_language", 422)
                mime = (audio.content_type or "").split(";")[0].strip().lower()
                if mime not in MIME_FORMATS:
                    raise AudioError("unsupported_audio_type", 415)
                name = audio.filename or ""
                extension = name.rsplit(".", 1)[-1].lower()
                allowed_ext = {"webm": {"audio/webm"}, "ogg": {"audio/ogg"}, "wav": {"audio/wav", "audio/x-wav"}, "mp3": {"audio/mpeg"}, "mp4": {"audio/mp4"}, "m4a": {"audio/mp4"}}
                if "/" in name or "\\" in name or "\x00" in name or mime not in allowed_ext.get(extension, set()):
                    raise AudioError("invalid_audio_filename", 415)
                data = await audio.read(settings.max_audio_bytes + 1)
                if len(data) > settings.max_audio_bytes:
                    raise AudioError("audio_too_large", 413)
                reserve(request, session, b"audio:" + mime.encode() + b":" + (language or "").encode() + b":" + data)
                quality = await validate_audio(data, mime, settings.max_audio_seconds)
                if quality != "ok":
                    return result(quality, ["no_signal_detected" if quality == "no_speech" else "signal_too_quiet_to_assess"])
                if state.provider_calls >= settings.provider_calls_per_process:
                    return result("provider_error", ["provider_budget_exhausted"], http_status=503)
                state.provider_calls += 1
                # Watch for disconnect while provider is processing; cancellation
                # closes httpx and decoder resources. No automatic billed retry.
                async def watch_disconnect():
                    while True:
                        message = await request.receive()
                        if message["type"] == "http.disconnect":
                            return
                work = asyncio.create_task(app.state.transcriber(data, mime, language, settings))
                watch = asyncio.create_task(watch_disconnect())
                try:
                    # Yield once so a provider task can register its cancellation
                    # handler before the disconnect watcher waits on the next body event.
                    await asyncio.sleep(0)
                    done, _ = await asyncio.wait([work, watch], timeout=settings.provider_timeout_seconds + 1, return_when=asyncio.FIRST_COMPLETED)
                    if watch in done:
                        raise AudioError("client_disconnected", 499)
                    if work not in done:
                        raise AudioError("provider_timeout", 504)
                    text = await work
                    if not isinstance(text, str) or len(text) > settings.max_text_chars:
                        raise AudioError("provider_error", 502)
                    return result("ok", ["transcript_requires_review", "speech_presence_not_verified"], text) if text.strip() else result("no_speech", ["provider_returned_no_text"])
                finally:
                    for task in (work, watch):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(work, watch, return_exceptions=True)
        except AudioError as exc:
            return result("provider_error", [exc.code], http_status=exc.status)
        except (httpx.HTTPError, TimeoutError):
            return result("provider_error", ["provider_unavailable"], http_status=502)
        finally:
            state.active -= 1

    @app.post("/v1/communication/feedback")
    async def feedback():
        raise HTTPException(503, "feedback_disabled")

    return app


app = create_app()
