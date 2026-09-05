# Aeyron Communicate

A privacy-first communication companion for people whose voice, speech, or typing becomes harder in real-world conditions. The product keeps the person in control: capture, review, approve, then share.

## What works now

- Speak: record a short clip, then transcribe only when an explicitly configured provider is enabled.
- Type: compose text with a large, forgiving editor.
- Review: show the original and editable draft. No rewrite is sent without approval.
- Output: copy, share, read aloud, or save privately on the device.
- Notebook: local-only history with export and delete controls.
- ParkiBot: a visible, user-initiated external handoff with no text or audio payload.
- Offline-safe typed path: typed communication remains usable when the backend is unavailable.

## Quick start

```bash
npm install
npm run dev
```

The frontend uses Vite on port 4173 and proxies `/v1` to `127.0.0.1:8000`.

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

The backend defaults to speech disabled. To enable OpenAI transcription, set the variables in `backend/.env.example`, provide a valid key, and separately acknowledge the provider privacy policy. The app never pretends that transcription succeeded when it is unavailable.

## Checks

```bash
npm test
npm run build
cd backend && python -m pytest -q
```

See `docs/` for the architecture, data lifecycle, threat model, test matrix, and launch checklist.

## Scope and safety

This is an assistive communication tool, not a diagnostic device or medical treatment. It does not infer Parkinson's disease, diagnose hypophonia, score a person's health, or replace a clinician. Voice trend features require a separate research protocol, consent, and validation before being added.
