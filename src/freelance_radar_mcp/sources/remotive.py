"""Adapter for the Remotive public jobs API.

Remotive publishes a documented, public, unauthenticated JSON API intended
for exactly this kind of programmatic consumption:
    https://remotive.com/api/remote-jobs

No key, no login, no scraping — this calls the same documented endpoint
Remotive tells developers to use.

VERIFIED PROVIDER BEHAVIOUR (live, 2026-10-17, 8 requests):
`search`, `limit` AND `category` are all accepted and all ignored. Every
combination returns a byte-identical body: the whole feed, 13 postings,
`job-count: 13`. Trusting any of those parameters is a silent correctness
bug, because the caller believes it filtered and it did not. So:

  * every parameter is applied LOCALLY here, after the fetch
  * we no longer send `limit` upstream. Sending it would mean asking for a
    page and then AND-filtering it, which silently under-returns the moment
    Remotive starts honouring it. We take the whole feed and truncate last.

Remotive's API terms require linking back to the posting URL and crediting
Remotive as the source, and forbid republishing its jobs to third-party job
sites. That obligation travels to callers in SOURCE_CAVEATS["remotive"].
"""

from __future__ import annotations

import re

import httpx

from ..http import make_client
from ..models import JobPosting

BASE_URL = "https://remotive.com/api/remote-jobs"
USER_AGENT = "freelance-radar-mcp/0.1 (+https://github.com/Las-so/freelance-radar-mcp)"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z0-9]+")


def _text(value: object) -> str:
    """Coerce any provider value to a string. `.get(k, "")` returns None for
    an explicit JSON null, so defaults are not enough: real feeds ship nulls
    and numbers in string fields."""
    return "" if value is None else str(value)


def _tag_list(value: object) -> list[str]:
    """Normalize `tags` to a list of strings.

    Seen in the wild: a list of ints (crashes str.join), a bare string
    (joins into "s h o p i f y" and never matches), a dict (silently loses
    the values). All three are handled here rather than at the call site.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [str(v) for v in value.values()]
    try:
        return [str(v) for v in value]
    except TypeError:
        return [str(value)]


def _plain(value: object) -> str:
    """Strip HTML and collapse whitespace."""
    text = _TAG_RE.sub(" ", _text(value))
    return _WS_RE.sub(" ", text).strip()


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _matches(job: dict, query: str | None, category: str | None = None) -> bool:
    """Local filter, because Remotive filters nothing.

    Token-based, not substring. Substring matching on raw HTML was measured
    against the live feed and was useless: "li" hit 13/13, "strong" 11/13,
    "java" matched "Javascript". Tokens also keep this consistent with
    scoring.py, which already tokenizes — otherwise one tool call would
    filter by substring and then score by token.
    """
    if not isinstance(job, dict):
        return False

    if category:
        if _text(job.get("category")).strip().lower() != category.strip().lower():
            return False

    if not query:
        return True

    haystack = _tokens(
        " ".join(
            [
                _text(job.get("title")),
                _text(job.get("company_name")),
                _text(job.get("category")),
                " ".join(_tag_list(job.get("tags"))),
                _plain(job.get("description")),
            ]
        )
    )
    return all(term in haystack for term in _tokens(query))


async def search(
    query: str | None = None,
    category: str | None = None,
    limit: int = 10,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[JobPosting]:
    """Search Remotive's public feed and return normalized postings.

    Raises httpx.HTTPStatusError / httpx.TransportError on a real failure —
    the MCP tool layer decides how to surface that; this module never
    silently swallows a broken connector.
    """
    n = max(1, min(int(limit), 100))

    owns_client = client is None
    client = client or make_client(headers={"User-Agent": USER_AGENT})
    try:
        # No params: all three are ignored upstream (see module docstring).
        resp = await client.get(BASE_URL)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    if not isinstance(data, dict):
        raise ValueError(
            f"Remotive returned {type(data).__name__}, expected a JSON object — "
            "the API shape may have changed."
        )

    raw = data.get("jobs")
    if not isinstance(raw, list):
        raw = []

    # Filter the WHOLE feed, then truncate. Never the other way round.
    candidates = [j for j in raw if _matches(j, query, category)]

    postings: list[JobPosting] = []
    for job in candidates[:n]:
        postings.append(
            JobPosting(
                id=f"remotive:{job.get('id')}",
                source="remotive",
                title=_text(job.get("title")).strip(),
                company=_text(job.get("company_name")).strip(),
                url=_text(job.get("url")),
                location=job.get("candidate_required_location"),
                category=job.get("category"),
                tags=tuple(_tag_list(job.get("tags"))),
                description_snippet=_snippet(job.get("description")),
                posted_at=job.get("publication_date"),
                salary=job.get("salary") or None,
            )
        )
    return postings


def _snippet(description: object, max_len: int = 280) -> str | None:
    text = _plain(description)
    if not text:
        return None
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"
