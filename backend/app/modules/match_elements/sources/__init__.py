"""‌⁠‍Source adapters - BIM (Phase A), DWG/PDF/Photo (Phase B/C/D).

Every adapter implements :class:`SourceAdapter` so the match-elements
service can stay source-agnostic. Adding a new source = adding one file
here and registering it in :mod:`app.modules.match_elements.service`.
"""

from app.modules.match_elements.sources.base import SourceAdapter, SourceElement

__all__ = ["SourceAdapter", "SourceElement"]
