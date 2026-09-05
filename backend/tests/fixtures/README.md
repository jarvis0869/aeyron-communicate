# Synthetic fixture provenance

All text in `test_safety.py` is authored for this repository, not from users.
The 40 base utterances cover medication, numeric, relationship, temporal,
uncertainty, injection, crisis, multilingual and structural meaning risks.
Four spacing variants yield 160 reproducible positive fixtures. Each also has
independent adversarial additions/substitutions tested against the invariant.
Synthetic PCM is generated in memory in `test_audio.py`, never recorded from a
person. Tone, silence and low-amplitude fixtures test parser/signal boundaries;
they do NOT simulate or validate dysarthria, Parkinson's, intelligibility or ASR.
No live provider is called by tests. The injected transcriber is test-only.
