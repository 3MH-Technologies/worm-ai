"""Server-side guard when building the system prompt from stored pieces.

Mitigations applied here:
- Strip user-controlled substrings that try to impersonate system messages.
- Reject obvious prompt-injection patterns from the *content* of memory items
  (these are user-curated, but a malicious past-self may have written junk).
- Enforce a hard size cap on the assembled system prompt.
- Never embed raw user messages inside the system block.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Phrases that often appear in injection attempts. We strip them defensively.
_BAD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore (?:all )?(?:previous|above|prior) instructions", re.IGNORECASE),
    re.compile(r"disregard (?:the )?(?:system|developer) prompt", re.IGNORECASE),
    re.compile(r"you are now (?:in )?(?:developer|admin|dan) mode", re.IGNORECASE),
    re.compile(r"reveal (?:the )?(?:system|hidden) prompt", re.IGNORECASE),
    re.compile(r"print (?:the )?(?:system|api) (?:prompt|key)", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>", re.IGNORECASE),
)


def sanitize_memory(text: str) -> str:
    """Remove obvious injection patterns from memory items before they enter
    the system prompt. The original memory is left untouched in the DB."""
    if not text:
        return ""
    cleaned = text
    for pat in _BAD_PATTERNS:
        cleaned = pat.sub("[redacted]", cleaned)
    return cleaned


def assemble(parts: Iterable[str], max_chars: int = 8000) -> str:
    """Combine sanitised slices into the final system prompt, capped."""
    joined = "\n\n".join(p for p in parts if p)
    if len(joined) > max_chars:
        joined = joined[: max_chars - 80] + "\n\n[... truncated for safety ...]"
    return joined.strip()
