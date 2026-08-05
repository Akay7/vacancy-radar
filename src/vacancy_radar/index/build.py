"""Building and incrementally maintaining the disposable LanceDB index.

`build_index` diffs a `VaultSnapshot`'s content hashes against what's
already in the table, embeds only what's new or changed, refreshes
denormalized columns on rows whose own text didn't change but whose
parent vacancy did, deletes rows for vanished sources, and (re)builds
the full-text index - see design.md for the diffing rationale.

Sidecar extraction is a separate, explicitly-gated step
(`extract_sidecars=True`): a build must not silently create sidecar
files on every run.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import lancedb
from lancedb.index import FTS

from vacancy_radar import frontmatter
from vacancy_radar.frontmatter import FrontmatterError
from vacancy_radar.index.embed import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    embed_texts,
    vector_dim,
)
from vacancy_radar.index.extract import ELIGIBLE_SUFFIXES, extract_to_sidecar
from vacancy_radar.index.schema import build_schema
from vacancy_radar.models import Document, Vacancy
from vacancy_radar.vault.paths import sidecar_path_for
from vacancy_radar.vault.reader import VaultSnapshot, VaultWarning

if TYPE_CHECKING:
    from lancedb.pydantic import LanceModel
    from lancedb.table import Table

TABLE_NAME = "documents"
VACANCY_ROW_KIND = "vacancy"


def _vacancy_row_id(vacancy_id: str) -> str:
    return f"vacancy:{vacancy_id}"


@dataclass(frozen=True)
class IndexReport:
    """The outcome of one `build_index` call."""

    added: int = 0
    changed: int = 0
    deleted: int = 0
    unchanged: int = 0
    skipped: int = 0
    elapsed: float = 0.0
    warnings: tuple[VaultWarning, ...] = ()


@dataclass
class _PlannedRow:
    doc_id: str
    text: str
    content_hash: str
    build: "type[LanceModel]"
    kwargs: dict[str, object]


def build_index(
    snapshot: VaultSnapshot,
    index_path: Path,
    *,
    force: bool = False,
    extract_sidecars: bool = False,
    model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
) -> IndexReport:
    """(Re)build the index at `index_path` from `snapshot`.

    Embeds only new/changed rows (or everything, if `force`). Updates
    denormalized columns on unchanged document rows whose vacancy
    changed, without re-embedding them. Deletes rows for sources no
    longer present. Creates/refreshes the FTS index and optimizes so
    everything written this call is searchable immediately after.
    """
    start = time.perf_counter()
    warnings: list[VaultWarning] = list(snapshot.warnings)

    if extract_sidecars:
        _extract_eligible_sidecars(snapshot, warnings)

    dim = vector_dim(model_name)
    connection = lancedb.connect(index_path)
    table, is_fresh = _open_or_create_table(connection, dim)

    existing_hashes = {} if is_fresh else _existing_hashes(table)

    planned: dict[str, _PlannedRow] = {}
    skipped_ids: set[str] = set()
    schema = build_schema(dim)

    changed_vacancy_ids: set[str] = set()
    for vacancy in snapshot.vacancies.values():
        row = _plan_vacancy_row(snapshot, vacancy, schema, warnings)
        if row is None:
            skipped_ids.add(_vacancy_row_id(vacancy.id))
            continue
        if force or is_fresh or existing_hashes.get(row.doc_id) != row.content_hash:
            planned[row.doc_id] = row
            changed_vacancy_ids.add(vacancy.id)

    for document in snapshot.documents.values():
        row = _plan_document_row(snapshot, document, schema, warnings)
        if row is None:
            skipped_ids.add(document.id)
            continue
        if force or is_fresh or existing_hashes.get(row.doc_id) != row.content_hash:
            planned[row.doc_id] = row

    desired_ids = (
        {f"vacancy:{v}" for v in snapshot.vacancies} | set(snapshot.documents)
    ) - skipped_ids

    added, changed = _write_planned_rows(table, planned, existing_hashes, model_name)
    resynced = _resync_denormalized_columns(
        table, snapshot, changed_vacancy_ids, planned, skipped_ids
    )
    deleted = _delete_vanished_rows(table, existing_hashes, desired_ids)

    table.create_index("text", config=FTS(), replace=True)
    table.optimize()

    unchanged = len(desired_ids) - len(planned) - resynced

    return IndexReport(
        added=added,
        changed=changed,
        deleted=deleted,
        unchanged=max(unchanged, 0) + resynced,
        skipped=len(skipped_ids),
        elapsed=time.perf_counter() - start,
        warnings=tuple(warnings),
    )


def _extract_eligible_sidecars(
    snapshot: VaultSnapshot, warnings: list[VaultWarning]
) -> None:
    for doc_id, doc_path in snapshot.document_paths.items():
        if doc_path.suffix.lower() in ELIGIBLE_SUFFIXES and doc_path.is_file():
            extract_to_sidecar(doc_path, warnings)
        del doc_id


def _open_or_create_table(
    connection: "lancedb.DBConnection", dim: int
) -> tuple["Table", bool]:
    """Open the table, creating it if absent. Recreates it from scratch
    if its vector dimensionality no longer matches the configured
    model - `force` alone never drops existing data, only a genuine
    model/dimension change does."""
    schema = build_schema(dim)
    try:
        table = connection.open_table(TABLE_NAME)
    except ValueError:
        return connection.create_table(TABLE_NAME, schema=schema), True

    existing_dim = table.schema.field("vector").type.list_size
    if existing_dim != dim:
        connection.drop_table(TABLE_NAME)
        return connection.create_table(TABLE_NAME, schema=schema), True
    return table, False


def _existing_hashes(table: "Table") -> dict[str, str]:
    rows = table.search().select(["doc_id", "content_hash"]).to_arrow().to_pylist()
    return {row["doc_id"]: row["content_hash"] for row in rows}


def _document_source_text(doc_path: Path) -> str:
    """Text for a document's own row: its body (markdown source) or
    its sidecar's body (non-markdown source) - empty if neither."""
    if doc_path.suffix == ".md":
        try:
            text = doc_path.read_text(encoding="utf-8")
            _, body = frontmatter.parse(text, filename=str(doc_path))
        except (OSError, FrontmatterError):
            return ""
        return body.strip()

    sidecar_path = sidecar_path_for(doc_path)
    if not sidecar_path.is_file():
        return ""
    try:
        sidecar_text = sidecar_path.read_text(encoding="utf-8")
        metadata, body = frontmatter.parse(sidecar_text, filename=str(sidecar_path))
    except (OSError, FrontmatterError):
        return ""
    if metadata.get("extracted_from") == doc_path.name:
        return body.strip()
    return ""


def _applied_date_str(vacancy: Vacancy) -> str | None:
    return vacancy.applied_date.isoformat() if vacancy.applied_date else None


def _compose_vacancy_text(vacancy: Vacancy) -> str:
    parts = [vacancy.role, vacancy.company, vacancy.status.value]
    parts.extend(
        extra
        for extra in (vacancy.stage_note, vacancy.salary_note, vacancy.recruiter)
        if extra
    )
    if vacancy.tags:
        parts.append(" ".join(vacancy.tags))
    return "\n".join(parts)


def _plan_vacancy_row(
    snapshot: VaultSnapshot,
    vacancy: Vacancy,
    schema: "type[LanceModel]",
    warnings: list[VaultWarning],
) -> _PlannedRow | None:
    path = snapshot.vacancy_paths.get(vacancy.id)
    if path is None or not path.is_file():
        warnings.append(
            VaultWarning(
                kind="vanished_source",
                message=f"vacancy {vacancy.id!r}'s vacancy.md is missing at build time",
                paths=() if path is None else (path,),
            )
        )
        return None

    content_hash_value = snapshot.hashes.get(path)
    if content_hash_value is None:
        return None

    last_activity = snapshot.last_activity(vacancy.id)
    kwargs = {
        "doc_id": _vacancy_row_id(vacancy.id),
        "vacancy_id": vacancy.id,
        "company_slug": vacancy.company_slug,
        "company": vacancy.company,
        "role": vacancy.role,
        "status": vacancy.status.value,
        "kind": VACANCY_ROW_KIND,
        "title": vacancy.role,
        "path": str(path),
        "date": vacancy.found_date.isoformat(),
        "found_date": vacancy.found_date.isoformat(),
        "applied_date": _applied_date_str(vacancy),
        "last_activity": last_activity.isoformat(),
        "tags": list(vacancy.tags),
        "text": _compose_vacancy_text(vacancy),
        "content_hash": content_hash_value,
    }
    return _PlannedRow(
        doc_id=kwargs["doc_id"],  # type: ignore[arg-type]
        text=kwargs["text"],  # type: ignore[arg-type]
        content_hash=content_hash_value,
        build=schema,
        kwargs=kwargs,
    )


def _plan_document_row(
    snapshot: VaultSnapshot,
    document: Document,
    schema: "type[LanceModel]",
    warnings: list[VaultWarning],
) -> _PlannedRow | None:
    path = snapshot.document_paths.get(document.id)
    vacancy = snapshot.vacancies.get(document.vacancy_id)
    if path is None or not path.is_file() or vacancy is None:
        warnings.append(
            VaultWarning(
                kind="vanished_source",
                message=f"document {document.id!r}'s source is missing at build time",
                paths=() if path is None else (path,),
            )
        )
        return None

    content_hash_value = snapshot.hashes.get(path)
    if content_hash_value is None:
        return None

    text = _document_source_text(path) or f"{document.title}\n{path.name}"
    last_activity = snapshot.last_activity(vacancy.id)
    kwargs = {
        "doc_id": document.id,
        "vacancy_id": vacancy.id,
        "company_slug": vacancy.company_slug,
        "company": vacancy.company,
        "role": vacancy.role,
        "status": vacancy.status.value,
        "kind": document.kind.value,
        "title": document.title,
        "path": str(path),
        "date": document.date.isoformat(),
        "found_date": vacancy.found_date.isoformat(),
        "applied_date": _applied_date_str(vacancy),
        "last_activity": last_activity.isoformat(),
        "tags": list(vacancy.tags),
        "text": text,
        "content_hash": content_hash_value,
    }
    return _PlannedRow(
        doc_id=kwargs["doc_id"],  # type: ignore[arg-type]
        text=text,
        content_hash=content_hash_value,
        build=schema,
        kwargs=kwargs,
    )


def _write_planned_rows(
    table: "Table",
    planned: dict[str, _PlannedRow],
    existing_hashes: dict[str, str],
    model_name: str,
) -> tuple[int, int]:
    if not planned:
        return 0, 0

    ordered_ids = sorted(planned)
    texts = [planned[doc_id].text for doc_id in ordered_ids]
    vectors = embed_texts(texts, model_name=model_name)

    rows = []
    added = 0
    changed = 0
    for doc_id, vector in zip(ordered_ids, vectors, strict=True):
        plan = planned[doc_id]
        rows.append(plan.build(**plan.kwargs, vector=vector))
        if doc_id in existing_hashes:
            changed += 1
        else:
            added += 1

    table.merge_insert(
        "doc_id"
    ).when_matched_update_all().when_not_matched_insert_all().execute(rows)
    return added, changed


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_literal(value: str | list[str] | None) -> str:
    """A SQL expression for `value`, usable with LanceDB's `values_sql`.

    `values` (the plain-Python-value path) chokes on an empty list -
    LanceDB/Arrow can't infer its element type from nothing (see
    design.md's implementation notes) - so every denormalized-column
    resync goes through `values_sql` uniformly instead.
    """
    if value is None:
        return "NULL"
    if isinstance(value, list):
        if not value:
            return "arrow_cast(array[], 'List(Utf8)')"
        return "array[" + ", ".join(_sql_string_literal(v) for v in value) + "]"
    return _sql_string_literal(value)


def _resync_denormalized_columns(
    table: "Table",
    snapshot: VaultSnapshot,
    changed_vacancy_ids: set[str],
    planned: dict[str, _PlannedRow],
    skipped_ids: set[str],
) -> int:
    """Update status/company/tags/etc. on document rows whose own text
    is unchanged but whose parent vacancy changed - no re-embedding."""
    resynced = 0
    for document in snapshot.documents.values():
        if document.id in planned or document.id in skipped_ids:
            continue
        if document.vacancy_id not in changed_vacancy_ids:
            continue
        vacancy = snapshot.vacancies.get(document.vacancy_id)
        if vacancy is None:
            continue
        last_activity = snapshot.last_activity(vacancy.id)
        values: dict[str, str | list[str] | None] = {
            "company_slug": vacancy.company_slug,
            "company": vacancy.company,
            "role": vacancy.role,
            "status": vacancy.status.value,
            "applied_date": _applied_date_str(vacancy),
            "last_activity": last_activity.isoformat(),
            "tags": list(vacancy.tags),
        }
        table.update(
            where=f"doc_id = {_sql_string_literal(document.id)}",
            values_sql={key: _sql_literal(value) for key, value in values.items()},
        )
        resynced += 1
    return resynced


def _delete_vanished_rows(
    table: "Table", existing_hashes: dict[str, str], desired_ids: set[str]
) -> int:
    to_delete = set(existing_hashes) - desired_ids
    if not to_delete:
        return 0
    quoted = (f"'{doc_id.replace(chr(39), chr(39) * 2)}'" for doc_id in to_delete)
    table.delete(f"doc_id IN ({', '.join(quoted)})")
    return len(to_delete)
