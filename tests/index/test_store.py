import importlib
from pathlib import Path

from vacancy_radar.index import store
from vacancy_radar.index.store import default_index_path, get_index_handle
from vacancy_radar.vault.paths import is_skipped_name


def test_importing_store_module_creates_no_handle() -> None:
    importlib.reload(store)

    assert store._handles == {}  # noqa: SLF001 - inspecting internal cache is the point


def test_repeated_requests_for_the_same_vault_path_return_the_same_handle(
    tmp_path: Path,
) -> None:
    importlib.reload(store)
    vault = tmp_path / "vault"
    vault.mkdir()

    first = get_index_handle(vault)
    second = get_index_handle(vault)

    assert first is second


def test_different_vault_paths_resolve_to_different_handles(tmp_path: Path) -> None:
    importlib.reload(store)
    vault_a = tmp_path / "vault-a"
    vault_b = tmp_path / "vault-b"
    vault_a.mkdir()
    vault_b.mkdir()

    handle_a = get_index_handle(vault_a)
    handle_b = get_index_handle(vault_b)

    assert handle_a is not handle_b
    assert handle_a.index_path != handle_b.index_path


def test_default_index_path_has_a_traversal_skipped_directory_name(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"

    resolved = default_index_path(vault)

    assert is_skipped_name(resolved.name)
