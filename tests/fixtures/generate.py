"""Seeded, deterministic synthetic vault generator.

Writes a fake vault tree to `tests/fixtures/vault/` (committed to the
repo) so later stages can read a realistic-shaped vault without any
real company, person, or address ever appearing in it. All names,
recruiters, and email bodies are drawn from the fixed pools below —
nothing here is looked up or invented per run.

Layout written per company:

    <company_slug>/
        _company.md
        <vacancy_id>/
            vacancy.md
            documents/
                <doc_id>.md
"""

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

from vacancy_radar import frontmatter
from vacancy_radar.ids import new_vacancy_id, slugify
from vacancy_radar.models import (
    UNKNOWN_ROLE,
    Company,
    Document,
    DocumentKind,
    Status,
    Vacancy,
)

# Placeholder names in the classic "Acme Corp" / "Ромашка" tradition -
# unambiguous stand-ins, never a real company.
SYNTHETIC_COMPANY_NAMES = [
    "Acme Corp",
    "Widget Works",
    "Example Systems",
    "Sample Solutions",
    "Generic Labs",
    "Placeholder Studio",
    "Foobar Industries",
    "Testcorp",
    "Sandbox Systems",
    "Blueprint Works",
    "Prototype Group",
    "Vaporware Studio",
    "Mockup Media",
    "Stubline Analytics",
    "Nullpoint Systems",
    "Dummy Data Co.",
    "Ромашка",
    "Одуванчик",
    "Незабудка",
    "Колокольчик",
]

FIRST_NAMES = [
    "Anna",
    "Mikhail",
    "Elena",
    "Tom",
    "Priya",
    "Wei",
    "Fatima",
    "Lucas",
    "Sofia",
    "Noah",
]

LAST_NAMES = [
    "Ivanova",
    "Smith",
    "Kuznetsova",
    "Andersen",
    "Sharma",
    "Chen",
    "Costa",
    "Nguyen",
    "Berg",
    "Fischer",
]

ROLE_TITLES = [
    "Backend Engineer",
    "Data Analyst",
    "Product Designer",
    "DevOps Engineer",
    "QA Engineer",
    "Machine Learning Engineer",
    "Frontend Developer",
    "Engineering Manager",
    "Site Reliability Engineer",
    "Technical Writer",
]

STAGE_NOTES = [
    "Этап собеседования 🎯",
    "Ожидаем ответ от рекрутера 📩",
    "Second round scheduled",
    "Waiting on take-home feedback",
    "Recruiter call went well 👍",
]

EMAIL_MARKER_PHRASES = (
    "thanks for applying",
    "following up on your application",
    "move forward with other candidates",
    "would like to move forward with an offer",
)

EMAIL_TEMPLATES = [
    (
        "Hi, thanks for applying to the {role} role at {company}. We would "
        "like to schedule a quick call this week. Best, {recruiter}"
    ),
    (
        "Hello, following up on your application for {role} at {company}. "
        "Could you share your availability for a screening call? "
        "Regards, {recruiter}"
    ),
    (
        "Thank you for your interest in the {role} position at {company}. "
        "Unfortunately we have decided to move forward with other "
        "candidates at this time. Best regards, {recruiter}"
    ),
    (
        "Congratulations! We would like to move forward with an offer for "
        "the {role} role at {company}. Let's set up a call to discuss "
        "details. Warmly, {recruiter}"
    ),
]

NON_EMAIL_BODIES = {
    DocumentKind.POSTING: "Original job posting text for {role} at {company}.",
    DocumentKind.NOTE: "Personal note: {role} at {company} looks like a good fit.",
    DocumentKind.TAKEHOME: "Take-home assignment instructions for the {role} role.",
}

VAULT_MARKER_DIRNAME = ".vacancy-radar"
"""The vault marker directory `config.resolve_vault_path` looks for."""

# --- Fixed (non-random) content for stage 4's retrieval tests --------------
#
# Unlike everything above, this content is never drawn from `rng` - stage
# 4's keyword/semantic scenarios need exact, reproducible strings to search
# for for, not merely a deterministic *selection* from a pool. Written by
# `write_search_fixtures`, called unconditionally (like the healthy tree,
# not opt-in like `--broken`).

SEARCH_FIXTURE_COMPANY_SLUG = "search-fixtures-corp"
SEARCH_FIXTURE_COMPANY_NAME = "Search Fixtures Corp"

DISTINCTIVE_PROPER_NOUN = "Glimmerforge"
"""Appears in exactly one document across the whole fixture vault - a
fabricated word chosen so no pool above could ever produce it by chance."""

RARE_TECH_TERM = "ClickHouse"
"""Appears in exactly one document; `ADJACENT_TECH_TERM` appears in a
different document so a query for one must not return the other."""

ADJACENT_TECH_TERM = "PostgreSQL"

SEMANTIC_PARAPHRASE_TARGET_DOC_ID = "search-fixture-paraphrase-doc1"
"""The document `SEMANTIC_PARAPHRASE_QUERY` should retrieve under semantic
search despite sharing no content word with it."""

SEMANTIC_PARAPHRASE_TARGET_TEXT = (
    "The candidate demonstrated strong proficiency in distributed "
    "consensus algorithms and horizontal database sharding strategies "
    "during the onsite technical interview loop."
)

SEMANTIC_PARAPHRASE_QUERY = (
    "How capably did the applicant perform when explaining how a "
    "company's information gets split across many machines and kept "
    "consistent with each other throughout their face-to-face meetings?"
)

MIN_COMPANIES = 12
MAX_COMPANIES = 20
MIN_VACANCIES_PER_COMPANY = 1
MAX_VACANCIES_PER_COMPANY = 3
MIN_DOCS_PER_VACANCY = 2
MAX_DOCS_PER_VACANCY = 6
REQUIRED_UNKNOWN_ROLE_COUNT = 3
REPEAT_APPLICATION_COMPANY_COUNT = 2
STAGE_NOTE_PROBABILITY = 0.6
SALARY_NOTE_PROBABILITY = 0.5
EXTERNAL_ID_PROBABILITY = 0.5
MIN_SALARY_K = 60
MAX_SALARY_K = 180
BASE_YEAR = 2022
YEAR_SPAN = 4  # 2022..2025 - safely in the past regardless of run date


def _recruiter_names(rng: random.Random, count: int) -> list[str]:
    return [f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}" for _ in range(count)]


def _document_body(
    kind: DocumentKind,
    role: str,
    company_name: str,
    recruiter: str | None,
    rng: random.Random,
) -> str:
    if kind is DocumentKind.EMAIL:
        template = rng.choice(EMAIL_TEMPLATES)
        return template.format(
            role=role, company=company_name, recruiter=recruiter or "The Team"
        )
    return NON_EMAIL_BODIES[kind].format(role=role, company=company_name)


def _document_title(kind: DocumentKind, role: str, company_name: str) -> str:
    return f"{kind.value.replace('_', ' ').title()}: {role} at {company_name}"


def _company_names(rng: random.Random, count: int) -> list[str]:
    """Return `count` distinct company display names.

    Draws from `SYNTHETIC_COMPANY_NAMES` without replacement. When
    `count` exceeds the pool (only relevant for scale-testing, since
    the default `MIN_COMPANIES`/`MAX_COMPANIES` bounds never exceed
    it), extends it with numbered variants (`"Acme Corp 2"`, `"Acme
    Corp 3"`, ...) so names stay distinct and slugs stay unique.
    """
    pool = SYNTHETIC_COMPANY_NAMES
    if count <= len(pool):
        return rng.sample(pool, count)

    names = list(pool)
    rng.shuffle(names)
    for i in range(count - len(pool)):
        base = pool[i % len(pool)]
        names.append(f"{base} {i // len(pool) + 2}")
    return names


def generate_vault(
    output_dir: Path,
    seed: int,
    *,
    min_companies: int = MIN_COMPANIES,
    max_companies: int = MAX_COMPANIES,
) -> None:
    """Generate a deterministic synthetic vault at `output_dir`.

    `min_companies`/`max_companies` default to the module constants
    used by the committed fixture; a caller (e.g. a performance test)
    may override them to generate a larger vault without touching the
    committed fixture's seed or size.
    """
    rng = random.Random(seed)

    company_count = rng.randint(min_companies, max_companies)
    chosen_names = _company_names(rng, company_count)

    vacancy_counts = [
        rng.randint(MIN_VACANCIES_PER_COMPANY, MAX_VACANCIES_PER_COMPANY)
        for _ in chosen_names
    ]
    for i in range(REPEAT_APPLICATION_COMPANY_COUNT):
        vacancy_counts[i] = 2

    companies: dict[int, dict[str, object]] = {}
    for index, name in enumerate(chosen_names):
        slug = slugify(name)
        companies[index] = {
            "name": name,
            "slug": slug,
            "domain": f"{slug}.example",
            "recruiters": _recruiter_names(rng, rng.randint(1, 2)),
        }

    slots = [
        (company_index, slot_index)
        for company_index, count in enumerate(vacancy_counts)
        for slot_index in range(count)
    ]

    statuses = list(Status)
    forced_statuses = dict(enumerate(statuses))
    total = len(slots)
    unknown_role_slots = set(range(total - REQUIRED_UNKNOWN_ROLE_COUNT, total))

    existing_ids: set[str] = set()
    vacancy_records: list[dict[str, object]] = []

    for position, (company_index, slot_index) in enumerate(slots):
        company = companies[company_index]
        status = forced_statuses.get(position) or rng.choice(statuses)
        is_unknown_role = position in unknown_role_slots
        role = UNKNOWN_ROLE if is_unknown_role else rng.choice(ROLE_TITLES)

        if company_index < REPEAT_APPLICATION_COMPANY_COUNT:
            year = BASE_YEAR + slot_index * 2
        else:
            year = BASE_YEAR + rng.randint(0, YEAR_SPAN - 1)
        found_date = date(year, rng.randint(1, 12), rng.randint(1, 28))

        applied_date = None
        if status is not Status.FOUND:
            applied_date = found_date + timedelta(days=rng.randint(0, 20))

        recruiters = company["recruiters"]
        recruiter = rng.choice(recruiters) if recruiters else None

        vacancy_id = new_vacancy_id(
            found_date, str(company["slug"]), role, existing_ids
        )
        existing_ids.add(vacancy_id)

        vacancy = Vacancy(
            id=vacancy_id,
            company=str(company["name"]),
            company_slug=str(company["slug"]),
            role=role,
            source_url=f"https://jobs.{company['domain']}/postings/{position + 1}",
            status=status,
            found_date=found_date,
            applied_date=applied_date,
            stage_note=(
                rng.choice(STAGE_NOTES)
                if rng.random() < STAGE_NOTE_PROBABILITY
                else None
            ),
            salary_note=(
                f"{rng.randint(MIN_SALARY_K, MAX_SALARY_K)}k"
                if rng.random() < SALARY_NOTE_PROBABILITY
                else None
            ),
            recruiter=recruiter,
            external_id=(
                f"gmail-{vacancy_id}"
                if rng.random() < EXTERNAL_ID_PROBABILITY
                else None
            ),
            tags=["needs_review"] if is_unknown_role else [],
        )

        doc_count = rng.randint(MIN_DOCS_PER_VACANCY, MAX_DOCS_PER_VACANCY)
        documents = []
        for doc_index in range(doc_count):
            kind = rng.choice(list(DocumentKind))
            # The very first document of the very first vacancy is always
            # forced to a take-home, written as a non-markdown file (see
            # _write_vault) - guarantees the non-markdown-document scenario
            # has a fixture regardless of how the random draws land.
            is_forced_non_markdown_takehome = position == 0 and doc_index == 0
            if is_forced_non_markdown_takehome:
                kind = DocumentKind.TAKEHOME
            doc_date = found_date + timedelta(days=rng.randint(0, 30))
            doc_id = f"{vacancy_id}-doc{doc_index + 1}"
            documents.append(
                {
                    "document": Document(
                        id=doc_id,
                        vacancy_id=vacancy_id,
                        kind=kind,
                        title=_document_title(kind, role, str(company["name"])),
                        date=doc_date,
                        external_id=(
                            f"gmail-{doc_id}" if kind is DocumentKind.EMAIL else None
                        ),
                    ),
                    "body": _document_body(
                        kind, role, str(company["name"]), recruiter, rng
                    ),
                    "non_markdown": is_forced_non_markdown_takehome,
                }
            )

        vacancy_records.append(
            {"company_index": company_index, "vacancy": vacancy, "documents": documents}
        )

    _write_vault(output_dir, companies, vacancy_records)


def _write_vault(
    output_dir: Path,
    companies: dict[int, dict[str, object]],
    vacancy_records: list[dict[str, object]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / VAULT_MARKER_DIRNAME).mkdir(parents=True, exist_ok=True)

    for info in companies.values():
        company_dir = output_dir / str(info["slug"])
        company_dir.mkdir(parents=True, exist_ok=True)
        company_model = Company(
            slug=str(info["slug"]),
            name=str(info["name"]),
            domains=[str(info["domain"])],
            recruiters=list(info["recruiters"]),  # type: ignore[arg-type]
        )
        metadata = company_model.model_dump(mode="json", exclude_none=True)
        (company_dir / "_company.md").write_text(
            frontmatter.serialize(metadata, ""), encoding="utf-8"
        )

    for record in vacancy_records:
        info = companies[record["company_index"]]  # type: ignore[index]
        vacancy: Vacancy = record["vacancy"]  # type: ignore[assignment]
        vacancy_dir = output_dir / str(info["slug"]) / vacancy.id
        vacancy_dir.mkdir(parents=True, exist_ok=True)

        metadata = vacancy.model_dump(
            mode="json", exclude={"role_is_placeholder"}, exclude_none=True
        )
        body = f"# {vacancy.role} at {vacancy.company}\n"
        (vacancy_dir / "vacancy.md").write_text(
            frontmatter.serialize(metadata, body), encoding="utf-8"
        )

        docs_dir = vacancy_dir / "documents"
        docs_dir.mkdir(parents=True, exist_ok=True)
        for doc_record in record["documents"]:  # type: ignore[union-attr]
            document: Document = doc_record["document"]
            if doc_record.get("non_markdown"):
                # A real take-home is often a PDF, not a note - stand in
                # with a non-markdown file, registered by path only, no
                # frontmatter to parse.
                (docs_dir / f"{document.id}.pdf").write_bytes(
                    doc_record["body"].encode("utf-8")
                )
                continue
            doc_metadata = document.model_dump(mode="json", exclude_none=True)
            (docs_dir / f"{document.id}.md").write_text(
                frontmatter.serialize(doc_metadata, doc_record["body"]),
                encoding="utf-8",
            )


def write_search_fixtures(vault_dir: Path) -> None:
    """Add fixed, non-random content stage 4's retrieval tests need.

    Additive only, like `write_broken_fixtures`: a company slug that
    collides with nothing in `SYNTHETIC_COMPANY_NAMES` or the broken-
    fixture slugs, never touching a file the healthy tree writes.
    """
    company_dir = vault_dir / SEARCH_FIXTURE_COMPANY_SLUG
    company_dir.mkdir(parents=True, exist_ok=True)
    company = Company(
        slug=SEARCH_FIXTURE_COMPANY_SLUG,
        name=SEARCH_FIXTURE_COMPANY_NAME,
        domains=[f"{SEARCH_FIXTURE_COMPANY_SLUG}.example"],
    )
    (company_dir / "_company.md").write_text(
        frontmatter.serialize(company.model_dump(mode="json", exclude_none=True), ""),
        encoding="utf-8",
    )

    _write_search_fixture_vacancy(
        company_dir,
        vacancy_id="search-fixture-terms",
        role="Search Fixture Terms Role",
        documents=[
            (
                "search-fixture-terms-doc1",
                DocumentKind.NOTE,
                "Note mentioning a distinctive term",
                (
                    f"Interview notes: the team's data platform runs on "
                    f"{RARE_TECH_TERM} for large-scale analytical queries."
                ),
            ),
            (
                "search-fixture-terms-doc2",
                DocumentKind.NOTE,
                "Note mentioning an adjacent term",
                (
                    f"Interview notes: the team's primary transactional "
                    f"store is {ADJACENT_TECH_TERM}, unrelated to the "
                    f"analytical stack."
                ),
            ),
            (
                "search-fixture-terms-doc3",
                DocumentKind.NOTE,
                "Note mentioning a distinctive proper noun",
                (
                    f"Recruiter mentioned the team ships a side project "
                    f"internally nicknamed {DISTINCTIVE_PROPER_NOUN}."
                ),
            ),
        ],
    )

    _write_search_fixture_vacancy(
        company_dir,
        vacancy_id="search-fixture-paraphrase",
        role="Search Fixture Paraphrase Role",
        documents=[
            (
                SEMANTIC_PARAPHRASE_TARGET_DOC_ID,
                DocumentKind.NOTE,
                "Note phrased in domain-specific language",
                SEMANTIC_PARAPHRASE_TARGET_TEXT,
            ),
        ],
    )


def _write_search_fixture_vacancy(
    company_dir: Path,
    *,
    vacancy_id: str,
    role: str,
    documents: list[tuple[str, DocumentKind, str, str]],
) -> None:
    vacancy_dir = company_dir / vacancy_id
    vacancy_dir.mkdir(parents=True, exist_ok=True)
    vacancy = Vacancy(
        id=vacancy_id,
        company=SEARCH_FIXTURE_COMPANY_NAME,
        company_slug=SEARCH_FIXTURE_COMPANY_SLUG,
        role=role,
        source_url=f"https://jobs.{SEARCH_FIXTURE_COMPANY_SLUG}.example/{vacancy_id}",
        status=Status.FOUND,
        found_date=date(2025, 6, 1),
    )
    metadata = vacancy.model_dump(
        mode="json", exclude={"role_is_placeholder"}, exclude_none=True
    )
    (vacancy_dir / "vacancy.md").write_text(
        frontmatter.serialize(metadata, f"# {role} at {SEARCH_FIXTURE_COMPANY_NAME}\n"),
        encoding="utf-8",
    )

    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for doc_id, kind, title, body in documents:
        document = Document(
            id=doc_id,
            vacancy_id=vacancy_id,
            kind=kind,
            title=title,
            date=date(2025, 6, 2),
        )
        doc_metadata = document.model_dump(mode="json", exclude_none=True)
        (docs_dir / f"{doc_id}.md").write_text(
            frontmatter.serialize(doc_metadata, body), encoding="utf-8"
        )


def _write_broken_company(vault_dir: Path, slug: str, name: str) -> Path:
    company_dir = vault_dir / slug
    company_dir.mkdir(parents=True, exist_ok=True)
    company = Company(slug=slug, name=name, domains=[f"{slug}.example"])
    metadata = company.model_dump(mode="json", exclude_none=True)
    (company_dir / "_company.md").write_text(
        frontmatter.serialize(metadata, ""), encoding="utf-8"
    )
    return company_dir


def _write_malformed_yaml_vacancy(vault_dir: Path) -> None:
    """A vacancy.md whose frontmatter is not parseable YAML."""
    slug = "broken-yaml-vault-corp"
    company_dir = _write_broken_company(vault_dir, slug, "Broken Yaml Vault Corp")
    vacancy_dir = company_dir / "broken-yaml-vacancy"
    vacancy_dir.mkdir(parents=True, exist_ok=True)
    (vacancy_dir / "vacancy.md").write_text(
        "---\n"
        "id: broken-yaml-vacancy\n"
        "company: Broken Yaml Vault Corp\n"
        "  bad_indent: [unterminated\n"
        "---\n"
        "# Malformed frontmatter, on purpose\n",
        encoding="utf-8",
    )


def _write_unknown_status_vacancy(vault_dir: Path) -> None:
    """A vacancy.md whose status is not one of the defined Status values."""
    slug = "unknown-status-vault-corp"
    company_dir = _write_broken_company(vault_dir, slug, "Unknown Status Vault Corp")
    vacancy_dir = company_dir / "unknown-status-vacancy"
    vacancy_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "id": "unknown-status-vacancy",
        "company": "Unknown Status Vault Corp",
        "company_slug": slug,
        "role": "Backend Engineer",
        "source_url": f"https://jobs.{slug}.example/postings/1",
        "status": "not_a_real_status",
        "found_date": "2026-01-01",
    }
    (vacancy_dir / "vacancy.md").write_text(
        frontmatter.serialize(metadata, "# Backend Engineer\n"), encoding="utf-8"
    )


def _write_unreadable_vacancy(vault_dir: Path) -> None:
    """A vacancy.md whose permissions make it unreadable."""
    slug = "unreadable-vault-corp"
    company_dir = _write_broken_company(vault_dir, slug, "Unreadable Vault Corp")
    vacancy_dir = company_dir / "unreadable-vacancy"
    vacancy_dir.mkdir(parents=True, exist_ok=True)
    vacancy = Vacancy(
        id="unreadable-vacancy",
        company="Unreadable Vault Corp",
        company_slug=slug,
        role="Backend Engineer",
        source_url=f"https://jobs.{slug}.example/postings/1",
        status=Status.FOUND,
        found_date=date(2026, 1, 1),
    )
    metadata = vacancy.model_dump(
        mode="json", exclude={"role_is_placeholder"}, exclude_none=True
    )
    vacancy_path = vacancy_dir / "vacancy.md"
    vacancy_path.write_text(
        frontmatter.serialize(metadata, "# Backend Engineer\n"), encoding="utf-8"
    )
    vacancy_path.chmod(0o000)


def _write_duplicate_id_vacancies(vault_dir: Path) -> None:
    """Two vacancy.md files, in different directories, sharing one id."""
    slug = "duplicate-id-vault-corp"
    company_dir = _write_broken_company(vault_dir, slug, "Duplicate Id Vault Corp")
    shared_id = "duplicate-vacancy-id"
    for suffix, role in (("a", "Backend Engineer"), ("b", "Frontend Developer")):
        vacancy_dir = company_dir / f"duplicate-vacancy-{suffix}"
        vacancy_dir.mkdir(parents=True, exist_ok=True)
        vacancy = Vacancy(
            id=shared_id,
            company="Duplicate Id Vault Corp",
            company_slug=slug,
            role=role,
            source_url=f"https://jobs.{slug}.example/postings/{suffix}",
            status=Status.FOUND,
            found_date=date(2026, 1, 1),
        )
        metadata = vacancy.model_dump(
            mode="json", exclude={"role_is_placeholder"}, exclude_none=True
        )
        (vacancy_dir / "vacancy.md").write_text(
            frontmatter.serialize(metadata, f"# {role}\n"), encoding="utf-8"
        )


def _write_orphan_documents_dir(vault_dir: Path) -> None:
    """A documents/ directory with no sibling vacancy.md."""
    slug = "orphan-doc-vault-corp"
    company_dir = _write_broken_company(vault_dir, slug, "Orphan Doc Vault Corp")
    docs_dir = company_dir / "orphan-vacancy" / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    document = Document(
        id="orphan-doc-1",
        vacancy_id="orphan-vacancy",
        kind=DocumentKind.NOTE,
        title="Orphan note",
        date=date(2026, 1, 1),
    )
    metadata = document.model_dump(mode="json", exclude_none=True)
    (docs_dir / f"{document.id}.md").write_text(
        frontmatter.serialize(metadata, "An orphaned note with no vacancy.md.\n"),
        encoding="utf-8",
    )


def write_broken_fixtures(vault_dir: Path) -> None:
    """Add malformed fixtures for vault-reader's resilience tests.

    Additive only: writes new company directories with names that don't
    collide with `SYNTHETIC_COMPANY_NAMES`, and never touches a file the
    healthy tree (`generate_vault`) already wrote.
    """
    _write_malformed_yaml_vacancy(vault_dir)
    _write_unknown_status_vacancy(vault_dir)
    _write_unreadable_vacancy(vault_dir)
    _write_duplicate_id_vacancies(vault_dir)
    _write_orphan_documents_dir(vault_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "vault")
    parser.add_argument(
        "--broken",
        action="store_true",
        help="Also write malformed fixtures for vault-reader's resilience tests",
    )
    args = parser.parse_args()
    generate_vault(args.output, seed=args.seed)
    write_search_fixtures(args.output)
    if args.broken:
        write_broken_fixtures(args.output)


if __name__ == "__main__":
    main()
