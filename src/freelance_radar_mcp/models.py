"""Normalized data model shared across every source adapter.

Every source module (remotive.py, adzuna.py, ...) must translate its
provider-specific JSON into this shape before returning it. That keeps
the MCP tool layer (server.py) and the scorer (scoring.py) source-agnostic:
add a new legitimate API tomorrow and nothing downstream has to change.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True, slots=True)
class JobPosting:
    id: str  # stable id, namespaced by source e.g. "remotive:2091141"
    source: str  # "remotive" | "adzuna" | ...
    title: str
    company: str
    url: str
    location: str | None = None
    category: str | None = None
    tags: tuple[str, ...] = ()
    description_snippet: str | None = None
    posted_at: str | None = None  # ISO 8601 string as given by the source
    salary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tags"] = list(self.tags)
        return d
