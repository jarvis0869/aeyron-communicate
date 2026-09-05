"""Conservative, deterministic meaning preservation.

No inferred intent, medical completion, spelling correction or lexical substitutions.
Whitespace inside lines is the only permitted modification. Structural newlines,
punctuation, case, token order, numbers and every non-whitespace character survive.
This is a formatting aid, NOT an AI paraphraser or a semantic safety proof.
"""

import re


def protected_signature(text: str) -> list[str]:
    # Token boundaries and line boundaries count: '1 5' must not become '15'.
    return re.findall(r"\n|[^\s]+", text)


def guard_suggestion(original: str, suggestion: str) -> tuple[str, list[str], str]:
    if protected_signature(original) != protected_signature(suggestion):
        return original, ["protected_content_change_rejected"], "blocked"
    return suggestion, ["formatting_only_review_required"], "unchanged_content"


def light_cleanup(text: str) -> tuple[str, list[str], str]:
    # Deliberately retain punctuation, newlines and all Unicode/control characters.
    # Rich text/HTML is never interpreted by this backend.
    suggestion = re.sub(r"[ \t]+", " ", text)
    return guard_suggestion(text, suggestion)
