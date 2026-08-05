from pathlib import Path

import pytest

from vacancy_radar.config import (
    VaultNotConfiguredError,
    VaultNotFoundError,
    resolve_vault_path,
)
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME


def _make_vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / VAULT_MARKER_DIRNAME).mkdir(parents=True)
    return vault


def test_explicit_argument_overrides_vault_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_vault = _make_vault(tmp_path / "env")
    explicit_vault = _make_vault(tmp_path / "explicit")
    monkeypatch.setenv("VAULT_PATH", str(env_vault))

    resolved = resolve_vault_path(explicit_vault)

    assert resolved == explicit_vault.resolve()


def test_vault_path_env_used_when_no_argument_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_vault = _make_vault(tmp_path / "env")
    monkeypatch.setenv("VAULT_PATH", str(env_vault))

    resolved = resolve_vault_path()

    assert resolved == env_vault.resolve()


def test_neither_present_raises_vault_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)

    with pytest.raises(VaultNotConfiguredError):
        resolve_vault_path()


def test_path_without_marker_raises_vault_not_found_naming_what_was_expected(
    tmp_path: Path,
) -> None:
    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()

    with pytest.raises(VaultNotFoundError, match=VAULT_MARKER_DIRNAME):
        resolve_vault_path(unmarked)


def test_nonexistent_path_raises_vault_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(VaultNotFoundError):
        resolve_vault_path(missing)


def test_path_pointing_at_a_file_raises_vault_not_found(tmp_path: Path) -> None:
    a_file = tmp_path / "not-a-directory"
    a_file.write_text("x", encoding="utf-8")

    with pytest.raises(VaultNotFoundError):
        resolve_vault_path(a_file)


def test_resolved_path_is_absolute_even_when_input_was_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative_vault = tmp_path / "relative-vault"
    (relative_vault / VAULT_MARKER_DIRNAME).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    resolved = resolve_vault_path(Path("relative-vault"))

    assert resolved.is_absolute()
    assert resolved == relative_vault.resolve()
