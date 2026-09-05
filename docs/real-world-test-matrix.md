# Real-world test matrix

The test suite treats these as release gates. Every failure should produce an explicit, recoverable state rather than a silent fallback.

| Area | Cases | Expected behavior |
| --- | --- | --- |
| Speech | no microphone, permission denied, muted input, noisy room, long pause, clipped audio, unsupported codec, 90-second cap | Clear status, no fake transcript, typed fallback remains available |
| Motor | tremor, accidental double tap, slow tap, keyboard-only use, switch focus, touch target at 200% zoom | No destructive one-tap action; focus and labels remain usable |
| Cognition/fatigue | interrupted task, stale tab, reload during processing, repeated submit | Preserve draft when safe, invalidate stale result, idempotent response |
| Language | numbers, decimals, negation, medication names, abbreviations, multilingual text, punctuation-only input | Preserve tokens; no unannounced semantic rewrite |
| Connectivity | offline, timeout, 429, provider 5xx, browser sleep/wake | Explain state; typed path works; retry is bounded |
| Privacy | clear notebook, export, external handoff, logs, provider disabled, session expiry | Deletion controls work; no hidden payload or body logging |
| Safety | prompt-injection text, HTML/script text, encoded payloads, huge Unicode, malformed multipart | Render as text; reject or bound input; return content-free errors |
| Accessibility | screen reader labels, keyboard traversal, reduced motion, high contrast, zoom, mobile viewport | All primary actions available without pointer or audio |
| Longitudinal research | missing baseline, variable microphone, illness/fatigue, medication timing, environment shift | Do not compute a clinical trend; record provenance or abstain |

Automated coverage lives in `src/model.test.ts`, `tests/e2e/communicate.spec.ts`, and `backend/tests/`. Physical mobile and assistive-device testing still requires human/device validation before a public clinical or research claim.
