# Test fixtures

Keep fixtures synthetic or openly licensed. Do not commit identifiable patient speech, transcripts, medication lists, or raw recordings.

Recommended fixture labels:

- `synthetic-clean`: short valid audio and ordinary text
- `synthetic-noisy`: bounded audio with background noise
- `malformed`: truncated, wrong MIME, oversized, or invalid multipart payloads
- `semantic-sensitive`: synthetic numbers, negation, medication names, and uncertainty

If a real-world dataset is used for research, store only a manifest and acquisition instructions here. Record license, consent, split policy, speaker independence, microphone/environment metadata, and preprocessing version.
