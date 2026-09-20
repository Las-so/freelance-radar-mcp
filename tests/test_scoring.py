"""Unit tests for the scorer — fixture data, no network calls."""

from freelance_radar_mcp.models import JobPosting
from freelance_radar_mcp.scoring import score_job, score_jobs


def _job(title: str, tags: tuple[str, ...] = (), snippet: str | None = None) -> JobPosting:
    return JobPosting(
        id="test:1",
        source="test",
        title=title,
        company="Acme",
        url="https://example.com/job/1",
        tags=tags,
        description_snippet=snippet,
    )


def test_title_match_scores_higher_than_body_match():
    title_hit = _job("Senior Python Automation Engineer")
    body_hit = _job("Backend Engineer", snippet="Some Python scripting is a plus.")

    s_title = score_job(title_hit, ["python"])
    s_body = score_job(body_hit, ["python"])

    assert s_title.score > s_body.score
    assert "python" in s_title.matched_keywords


def test_no_match_scores_zero():
    job = _job("Graphic Designer")
    s = score_job(job, ["python", "mcp", "api integration"])
    assert s.score == 0
    assert s.matched_keywords == ()


def test_empty_keywords_scores_zero_not_error():
    job = _job("Anything")
    s = score_job(job, [])
    assert s.score == 0


def test_score_jobs_sorts_descending():
    strong = _job("MCP and API Integration Developer", tags=("python", "automation"))
    weak = _job("Office Assistant")
    ranked = score_jobs([weak, strong], ["mcp", "api integration", "python", "automation"])
    assert ranked[0].job.title == strong.title
    assert ranked[0].score >= ranked[1].score
