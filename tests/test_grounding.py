from vacancy_radar import grounding
from vacancy_radar.models import (
    CandidateFlag,
    CandidateReport,
    CandidateSentence,
    Citation,
    DraftSentence,
)

SOURCES = {
    "bullet-0": "Built a FastAPI service handling 200 req/s with async SQLAlchemy.",
    "filter-rules": "Must be remote. No on-call rotation.",
}


def _candidate(flags=None, gaps=None, draft_sentences=None) -> CandidateReport:
    return CandidateReport(
        match_band="good",
        flags=flags or [],
        gaps=gaps or [],
        draft_sentences=draft_sentences or [],
    )


def test_flag_with_verbatim_quote_is_kept():
    candidate = _candidate(
        flags=[
            CandidateFlag(
                label="Backend",
                severity="green",
                reason="Built a FastAPI service.",
                quote="Built a FastAPI service handling 200 req/s",
                source_id="bullet-0",
            )
        ]
    )
    result = grounding.enforce(candidate, SOURCES)
    assert len(result.flags) == 1
    assert result.flags[0].label == "Backend"
    assert result.citations == [
        Citation(quote="Built a FastAPI service handling 200 req/s", source_id="bullet-0")
    ]


def test_flag_with_fabricated_quote_is_dropped():
    candidate = _candidate(
        flags=[
            CandidateFlag(
                label="Fabricated",
                severity="green",
                reason="Invented.",
                quote="launched a rocket to Mars",
                source_id="bullet-0",
            )
        ]
    )
    result = grounding.enforce(candidate, SOURCES)
    assert result.flags == []
    assert result.citations == []


def test_quote_with_echoed_source_prefix_is_still_grounded():
    # A real model (see specs/003-analyze-report-generation/quickstart.md manual pass) echoed
    # the "[bullet-0] " display prefix from the prompt back as part of its "quote" — this must
    # still be recognized as grounded, not silently dropped as a false-fabrication.
    candidate = _candidate(
        draft_sentences=[
            CandidateSentence(
                text="I built a FastAPI service.",
                quote="[bullet-0] Built a FastAPI service handling 200 req/s",
                source_id="bullet-0",
            )
        ]
    )
    result = grounding.enforce(candidate, SOURCES)
    assert result.draft_paragraph == "I built a FastAPI service."


def test_flag_with_unknown_source_id_is_dropped():
    candidate = _candidate(
        flags=[
            CandidateFlag(
                label="Bad source",
                severity="red",
                reason="Unknown source.",
                quote="anything",
                source_id="bullet-99",
            )
        ]
    )
    result = grounding.enforce(candidate, SOURCES)
    assert result.flags == []


def test_quote_is_matched_case_and_whitespace_insensitively():
    candidate = _candidate(
        flags=[
            CandidateFlag(
                label="Backend",
                severity="green",
                reason="Match despite different casing/whitespace.",
                quote="built   a fastapi SERVICE handling 200 req/s",
                source_id="bullet-0",
            )
        ]
    )
    result = grounding.enforce(candidate, SOURCES)
    assert len(result.flags) == 1


def test_flag_can_cite_filter_rules():
    candidate = _candidate(
        flags=[
            CandidateFlag(
                label="Remote requirement",
                severity="red",
                reason="Posting doesn't mention remote work.",
                quote="Must be remote",
                source_id="filter-rules",
            )
        ]
    )
    result = grounding.enforce(candidate, SOURCES)
    assert len(result.flags) == 1


def test_gaps_pass_through_without_citation():
    candidate = _candidate(gaps=["No Kubernetes experience found in ingested bullets"])
    result = grounding.enforce(candidate, SOURCES)
    assert result.gaps == ["No Kubernetes experience found in ingested bullets"]


def test_draft_paragraph_joins_only_grounded_sentences_in_order():
    candidate = _candidate(
        draft_sentences=[
            CandidateSentence(
                text="I built a FastAPI service handling real load.",
                quote="Built a FastAPI service handling 200 req/s",
                source_id="bullet-0",
            ),
            CandidateSentence(
                text="I also invented cold fusion.",
                quote="invented cold fusion",
                source_id="bullet-0",
            ),
        ]
    )
    result = grounding.enforce(candidate, SOURCES)
    assert result.draft_paragraph == "I built a FastAPI service handling real load."


def test_draft_sentences_pairs_each_kept_sentence_with_its_citation():
    candidate = _candidate(
        draft_sentences=[
            CandidateSentence(
                text="I built a FastAPI service handling real load.",
                quote="Built a FastAPI service handling 200 req/s",
                source_id="bullet-0",
            ),
            CandidateSentence(
                text="I also invented cold fusion.",
                quote="invented cold fusion",
                source_id="bullet-0",
            ),
        ]
    )
    result = grounding.enforce(candidate, SOURCES)
    assert result.draft_sentences == [
        DraftSentence(
            text="I built a FastAPI service handling real load.",
            citation=Citation(
                quote="Built a FastAPI service handling 200 req/s", source_id="bullet-0"
            ),
        )
    ]
    # the flat draft_paragraph is exactly the space-joined draft_sentences texts
    assert result.draft_paragraph == " ".join(d.text for d in result.draft_sentences)


def test_empty_source_registry_grounds_nothing():
    candidate = _candidate(
        flags=[
            CandidateFlag(
                label="Backend",
                severity="green",
                reason="x",
                quote="Built a FastAPI service handling 200 req/s",
                source_id="bullet-0",
            )
        ],
        draft_sentences=[
            CandidateSentence(text="x", quote="Built a FastAPI service", source_id="bullet-0")
        ],
    )
    result = grounding.enforce(candidate, {})
    assert result.flags == []
    assert result.draft_paragraph == ""
    assert result.citations == []
