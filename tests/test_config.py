from pathlib import Path

import pytest

from vacancy_radar.config import (
    FusionStrategy,
    InvalidSearchConfigError,
    SearchConfig,
    VaultNotConfiguredError,
    VaultNotFoundError,
    resolve_search_config,
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


# --- SearchConfig / resolve_search_config (stage 4) -------------------------

_SEARCH_ENV_VARS = (
    "SEARCH_DEFAULT_MODE",
    "SEARCH_DEFAULT_VECTOR_WEIGHT",
    "SEARCH_DEFAULT_LIMIT",
    "SEARCH_FUSION_STRATEGY",
)


@pytest.fixture(autouse=True)
def _clear_search_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SEARCH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_search_config_constructs_with_documented_defaults() -> None:
    """`default_vector_weight` and `fusion_strategy` are stage 5's
    eval-harness-measured winner, not stage 4's original guess - see
    `SearchConfig`'s docstring and README.md's retrieval evaluation
    table."""
    config = SearchConfig()

    assert config.default_mode == "hybrid"
    assert config.default_vector_weight == 0.5  # noqa: PLR2004 - the documented default
    assert config.default_limit == 10  # noqa: PLR2004 - the documented default
    assert config.fusion_strategy == FusionStrategy.LINEAR_COMBINATION


def test_resolve_search_config_with_unset_environment_matches_field_defaults() -> None:
    assert resolve_search_config() == SearchConfig()


def test_resolve_search_config_default_limit_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_DEFAULT_LIMIT", "25")

    resolved = resolve_search_config()

    assert resolved.default_limit == 25  # noqa: PLR2004
    assert resolved.default_mode == SearchConfig().default_mode
    assert resolved.default_vector_weight == SearchConfig().default_vector_weight
    assert resolved.fusion_strategy == SearchConfig().fusion_strategy


def test_resolve_search_config_default_mode_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_DEFAULT_MODE", "keyword")

    assert resolve_search_config().default_mode == "keyword"


def test_resolve_search_config_default_vector_weight_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_DEFAULT_VECTOR_WEIGHT", "0.3")

    assert resolve_search_config().default_vector_weight == 0.3  # noqa: PLR2004


def test_resolve_search_config_fusion_strategy_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_FUSION_STRATEGY", "linear_combination")

    assert resolve_search_config().fusion_strategy == FusionStrategy.LINEAR_COMBINATION


def test_resolve_search_config_invalid_mode_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_DEFAULT_MODE", "not_a_real_mode")

    with pytest.raises(InvalidSearchConfigError, match="SEARCH_DEFAULT_MODE"):
        resolve_search_config()


def test_resolve_search_config_invalid_fusion_strategy_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_FUSION_STRATEGY", "not_a_real_strategy")

    with pytest.raises(InvalidSearchConfigError, match="SEARCH_FUSION_STRATEGY"):
        resolve_search_config()
