"""Canonicalize node text before embedding.

Port of production ``utils/canonicalize_kql.apply_regex_masks`` (Phase 1
universal masking). Replaces incident-specific tokens (GUIDs, timestamps,
IPs, etc.) with stable placeholders so structurally identical strings
produce similar embeddings.

The paper §3.3 ("Ours" variant in Figure 3) applies this before
embedding-based agglomerative clustering. The KQL-specific Phase 2
(learned column-value masks) is intentionally omitted — that requires a
fitted KQLCanonicalizer over a corpus of KQL queries and is not needed
for free-text problem/action/observation/resolution labels.
"""

from __future__ import annotations

import re

_GUID_RE = re.compile(
    r"""[\"\']?\{?"""
    r"""[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"""
    r"""\}?[\"\']?""")
_DATETIME_FUNC_RE = re.compile(r"""\b(?:datetime|todatetime)\s*\([^)]*\)""", re.IGNORECASE)
_AGO_RE = re.compile(r"""\bago\s*\(\s*[^)]*\)""", re.IGNORECASE)
_ISO_DATETIME_RE = re.compile(
    r"""\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b""")
_ISO_DATE_RE = re.compile(r"""\b\d{4}-\d{2}-\d{2}\b""")
_HEX_HASH_RE = re.compile(r"""\b0x[0-9A-Fa-f]{8,}\b""")
_LARGE_NUM_RE = re.compile(r"""\b\d{7,}\b""")
_LONG_QUOTED_RE = re.compile(r"""(?P<q>[\"'])(?P<content>[^\"'|]{80,}?)(?P=q)""")
_IPV4_RE = re.compile(r"""\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b""")
_EMAIL_RE = re.compile(r"""\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b""")
_URL_VALUE_RE = re.compile(r"""https?://[^\s\"')\]]+""", re.IGNORECASE)


def canonicalize(text: str) -> str:
    """Apply Phase 1 regex masking. Order matters: datetime funcs before GUIDs."""
    if not text:
        return text
    result = text
    result = _DATETIME_FUNC_RE.sub("<DATETIME>", result)
    result = _AGO_RE.sub("ago(<DURATION>)", result)
    result = _GUID_RE.sub("<GUID>", result)
    result = _ISO_DATETIME_RE.sub("<DATETIME>", result)
    result = _ISO_DATE_RE.sub("<DATE>", result)
    result = _HEX_HASH_RE.sub("<HASH>", result)
    result = _URL_VALUE_RE.sub("<URL>", result)
    result = _EMAIL_RE.sub("<EMAIL>", result)
    result = _IPV4_RE.sub("<IP>", result)
    result = _LONG_QUOTED_RE.sub(lambda m: m.group("q") + "<TEXT>" + m.group("q"), result)
    result = _LARGE_NUM_RE.sub("<NUM>", result)
    return result


__all__ = ["canonicalize"]
