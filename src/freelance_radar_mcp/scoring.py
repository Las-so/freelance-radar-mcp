"""Lightweight, transparent relevance scoring.

Deliberately not ML, not a black box: a weighted keyword-overlap score you
can read and adjust in thirty seconds. Mirrors the score / capability_match
columns already used in the existing work-ops pipeline tracker, so output
from this tool can be pasted straight into that spreadsheet without a
format translation step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import JobPosting


@dataclass(frozen=True, slots=True)
class ScoredJob:
    job: JobPosting
    score: int  # 0-100
    matched_keywords: tuple[str, ...]

    def to_dict(self) -> dict:
        d = self.job.to_dict()
        d["score"] = self.score
        d["matched_keywords"] = list(self.matched_keywords)
        return d


_WORD_RE = re.compile(r"[a-z0-9+.#]+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def score_job(job: JobPosting, capability_keywords: list[str]) -> ScoredJob:
    """Score a single posting 0-100 against a list of your capability keywords.

    Title matches count double vs. tag/snippet matches, since a title hit is
    a much stronger signal than a keyword buried in a long description.
    """
    if not capability_keywords:
        return ScoredJob(job=job, score=0, matched_keywords=())

    kw_tokens = [kw.lower().strip() for kw in capability_keywords if kw.strip()]
    title_tokens = _tokenize(job.title)
    body_tokens = _tokenize(
        " ".join(filter(None, [job.description_snippet, " ".join(job.tags), job.category or ""]))
    )

    matched: list[str] = []
    raw = 0
    for kw in kw_tokens:
        kw_words = _tokenize(kw)
        if not kw_words:
            continue
        in_title = kw_words.issubset(title_tokens) or any(w in title_tokens for w in kw_words)
        in_body = kw_words.issubset(body_tokens) or any(w in body_tokens for w in kw_words)
        if in_title:
            raw += 2
            matched.append(kw)
        elif in_body:
            raw += 1
            matched.append(kw)

    max_possible = len(kw_tokens) * 2
    score = round(100 * raw / max_possible) if max_possible else 0
    return ScoredJob(job=job, score=min(score, 100), matched_keywords=tuple(matched))


def score_jobs(jobs: list[JobPosting], capability_keywords: list[str]) -> list[ScoredJob]:
    scored = [score_job(j, capability_keywords) for j in jobs]
    return sorted(scored, key=lambda s: s.score, reverse=True)
