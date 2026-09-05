# Threat model

## Assets

- Voice recordings and transcripts
- Medication names, numbers, and personal messages
- Notebook entries
- Session and request metadata
- Accessibility state and possible health context

## Main threats and controls

| Threat | Control | Residual risk |
| --- | --- | --- |
| Accidental upload | Typed path works offline; recording stays local; no upload action exists in the local recorder | A future transcription feature must be a separate explicit action |
| Model changes meaning | Original is shown; approval is mandatory; revision invalidates stale suggestions | User may approve a bad edit |
| Prompt injection in text | Text is rendered as text; no tool execution; rewrite is deterministic by default | External systems receiving copied text are out of scope |
| Replay or duplicate request | Short-lived session, idempotency key, rate limits | In-memory state resets on restart |
| Oversized or malicious audio | Content-length limits, ffprobe validation, duration cap, ffmpeg safety flags, cleanup | Codec edge cases depend on installed ffmpeg |
| Cross-origin abuse | Explicit CORS allowlist, no credentials, authorization header required | Misconfigured deployment origins remain possible |
| ParkiBot data leakage | Plain external link with `noopener noreferrer` and `no-referrer`; no query payload | Browser history may still contain destination |
| Notebook exposure | Local-only storage, export/delete controls, clear privacy copy | Any local browser profile compromise is out of scope |
| Availability failure | Offline typed path and explicit speech-disabled state | Speech is unavailable until provider is healthy |

## Security invariants

- Never claim a transcript or rewrite exists unless the service returned one.
- Never put message content, audio, API keys, or provider responses in logs.
- Never use model output as a diagnosis or treatment recommendation.
- Never send notebook content to ParkiBot implicitly.
