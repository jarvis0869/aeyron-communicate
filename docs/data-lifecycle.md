# Data lifecycle

| Data | Created | Default location | Retention | User control |
| --- | --- | --- | --- | --- |
| Typed draft | While typing | Browser memory | Until navigation or reload | Edit or clear |
| Approved message | After approval | Browser memory | Until replaced | Copy/share/save |
| Notebook entry | Explicit save | Browser localStorage | Until deleted or browser storage is cleared | Export, delete one, clear all |
| Audio clip | During recording | Browser memory / Blob | Until tab closes, download, or discard | Stop, play, download, discard |
| Session token | API session | Browser memory | Short-lived | Expires automatically |
| Provider transcript request | Explicit transcription | Provider request boundary | Provider policy applies | Disabled unless enabled and acknowledged |

The local recorder does not contact the server. The server does not log request bodies, store audio, or persist message content. Logs may contain route, status, timing, and a pseudonymous request id. Operators must treat request ids and timestamps as potentially sensitive metadata.

## Deletion guarantees

- Client delete removes the notebook entry from localStorage.
- Client clear removes all local notebook entries.
- Server cleanup removes temporary upload files on success, failure, timeout, and cancellation.
- Provider-side deletion is not claimed by this repository. Deployment documentation must name the provider policy and configure retention separately.

## Research extension

Do not add automatic voice trend scores to the communication database. If a participant opts into research, keep an explicit consent record, separate pseudonymous study id from account identity, store raw audio only for the approved period, version every feature extractor, and allow withdrawal plus deletion. Trend output must be labeled as a research signal, never a diagnosis.
