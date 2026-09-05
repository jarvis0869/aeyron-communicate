# Aeyron communication backend

Python 3.12+, FFmpeg and ffprobe are required. These files are self-contained;
there is no database, no training pipeline, no fake production transcription.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Run commands from this `backend/` directory. The frontend should proxy `/v1` to
this server, or use an explicitly configured allowed frontend origin. Do not
use a wildcard origin. No account is needed; POST `/v1/session` supplies a random
30-minute anonymous Bearer token, held in frontend memory. It is an abuse limit,
not verified identity. Do not log or persist the token.

## Contract

- GET `/health` and `/v1/health`: liveness, not a live paid provider check.
- GET `/v1/config`: truthful capabilities and processing notice.
- POST `/v1/session`: `{token, expires_in}`.
- POST `/v1/communication/rewrite`: JSON `{text,style:'light_cleanup'}`;
  returns `{request_id,original,suggestion,warnings,meaning_risk}`.
- POST `/v1/communication/transcribe`: multipart `audio` and optional ISO 639-1
  two/three lowercase character `language`; returns
  `{request_id,transcript,status,warnings}`. WAV, MP3, MP4/M4A, WebM, Ogg allowed.
- POST `/v1/communication/feedback`: explicitly disabled (503), no persistence.

Both communication calls require `Authorization: Bearer <token>` and a unique
`Idempotency-Key` (8–128 letters/digits/hyphen/underscore). The same key and body
returns 409 `duplicate_submission`; a changed body returns 409
`idempotency_mismatch`. We retain hashes rather than sensitive cached output.
Retries are NEVER automatic. A failed request may already have been billed;
the user can deliberately submit a new operation using a new key.

`status` distinguishes `ok`, `no_speech`, `low_quality`, `provider_error`.
Validation failures have non-2xx HTTP status and content-free error/warning codes.
401 means request a new session; do not silently re-submit audio. 429 means stop
and ask the user to try later. No result is ever sent/shared/played automatically.

## Safety and actual functionality

Cleanup is **deterministic formatting**, not an AI paraphrase. It collapses
horizontal spaces/tabs only. No word, punctuation, case, number, newline or
relationship can change. UI must call it "Light cleanup (spacing only)".
The invariant protects represented tokens but does not prove human intent.

Transcription is **batch, disabled by default**. To opt in after completing a
provider/privacy review, configure server-only `AEYRON_TRANSCRIPTION_ENABLED=true`,
`AEYRON_PROVIDER_PRIVACY_ACKNOWLEDGED=true` and `OPENAI_API_KEY`. The server makes
at most one request per submission to the documented OpenAI audio transcriptions
endpoint using multipart and JSON output. No client API key, redirect, proxy,
automatic retry, streaming claim or fabricated confidence is used. See
https://developers.openai.com/api/docs/guides/speech-to-text . No paid request was
made during implementation. Actual account/model availability remains untested.

Exact digital silence is rejected before provider access. Very low amplitude is
flagged for retry/typing. This is NOT speech activity detection: fan noise,
television, other speakers, tones, breathing and severe dysarthria cannot be
reliably distinguished by this filter. This is a documented public voice-launch
blocker pending representative speech/noise evaluation. No automatic message
approval is permitted. No clinical validity claim is made.

## Privacy/lifecycle

Application audio is bounded in memory. Multipart spool threshold exceeds the
10 MiB request cap, all upload handles close in `finally`, and ffprobe/ffmpeg
receive stdin pipes, not filenames. Decoded output is limited to 91 seconds.
No temporary raw files are created, so there is no application temp-file
sweeper. Parser partial-upload cleanup and Python reference release occur on
success, error and cancellation. Decoder processes are killed and reaped on
timeout/cancellation. Process restart destroys memory and anonymous sessions.
Python release is NOT cryptographic RAM zeroization. Configure no swap/core
dumps; memory snapshots and OS-level operator access remain deployment risks.
No notebooks, feedback or model outputs are stored server-side. Hash tombstones
and rate counters last at most the session lifetime (pruned at the next request).

No request-body logging is configured. Run uvicorn with `--no-access-log` and
disable proxy payload/query logging and third-party trace/body collection. Error
responses never include validation input or upstream error bodies. Responses are
no-store. Application cleanup does not imply provider zero retention. Provider
terms, processor list and any contractual retention controls require review.

## Deployment limits and hardening

Run **one worker / one replica**. All session, concurrency, idempotency and budget
counters are process-local. A second worker would break session routing and
multiply limits. Restart resets the budget. Default caps: 16 concurrent incoming
requests, 4 audio processors, 100 provider requests per process, 100 session
mints/minute globally, 10 per peer IP/minute, 60 operations/session/minute,
120 idempotency entries/session, 1,000 active sessions, 15-second upload timeout.
The provider-call cap is NOT a durable dollar spend ceiling. Configure a provider
project hard spend cap and ingress global/IP quotas before enabling transcription.
The API intentionally ignores forwarded IP headers. Configure the reverse proxy
appropriately and rate-limit there; otherwise users may share the proxy's limit.

Use TLS, origin allowlist, ingress size/header/time limits, a non-root container,
CPU/memory/PID limits, read-only filesystem, no outbound access except the provider,
and seccomp/isolation for FFmpeg parsing. Audio decoder protocol allowlist permits
only `pipe`, and filenames cannot become filesystem paths. Resource budgets and
container/proxy behavior require deployment verification. Batch decoding via pipes
can reject unusual seek-dependent MP4 variants; test physical Safari recordings.

Rollback: set `AEYRON_TRANSCRIPTION_ENABLED=false` and restart the single worker.
Typed input remains functional client-side. Never deploy using the test adapter.

## Evidence

`python -m pytest -q` exercises the 160-case spacing corpus, 160 adversarial
mutations, protected concepts, API/auth/CORS/limits/idempotency, audio metadata,
real FFmpeg parsing, synthetic signal thresholds, provider fake/timeout/error,
no-content state/log checks and memory-only file-handle cleanup. A passing test
does not prove clinical benefit, real-user usability, robust real-world ASR,
physical-device capture, upstream retention or deployment security.
