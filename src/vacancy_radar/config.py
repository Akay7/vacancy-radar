"""Vault path resolution, and stage 4's configurable search defaults.

Vault path precedence: an explicit path argument, then the `VAULT_PATH`
environment variable, then `VaultNotConfiguredError`. The explicit
argument is also the seam a future MCP-roots-based caller (stage 8)
will use — it can resolve a client-supplied root and pass it in here
without this function's signature changing.

Search defaults (`SearchConfig`/`resolve_search_config`) follow the
same explicit-then-env-var-then-field-default shape, minus the
explicit-argument seam: `search()` has no top-level config parameter
(see design.md), so an explicit `search()` call argument is the only
"explicit" layer, resolved inside `search.py` itself, not here.
"""

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME, vault_marker_path


class VaultNotConfiguredError(Exception):
    """Raised when no vault path was given, explicitly or via VAULT_PATH."""

    def __init__(self) -> None:
        super().__init__(
            "No vault path configured: pass an explicit path or set the "
            "VAULT_PATH environment variable."
        )


class VaultNotFoundError(Exception):
    """Raised when a configured path isn't a valid vault."""

    def __init__(self, path: Path, *, reason: str) -> None:
        self.path = path
        super().__init__(f"{path} is not a valid vault: {reason}")


def _resolve_candidate_path(explicit: Path | str | None) -> Path:
    """The explicit-then-`VAULT_PATH` precedence shared by
    `resolve_vault_path` and `resolve_target_path` - resolution only,
    no existence/directory/marker check. Raises `VaultNotConfiguredError`
    when neither `explicit` nor `VAULT_PATH` is given; that's the one
    error both callers still need identically (see vault-init change's
    design.md decision 2)."""
    candidate = explicit if explicit is not None else os.environ.get("VAULT_PATH")
    if candidate is None:
        raise VaultNotConfiguredError
    return Path(candidate).resolve()


def resolve_target_path(explicit: Path | str | None = None) -> Path:
    """Resolve a target path for an operation that may create a vault
    (`core.init_vault`) rather than assume one already exists: same
    explicit-then-`VAULT_PATH` precedence as `resolve_vault_path`, but
    the returned path is not required to exist, be a directory, or
    carry a `.vacancy-radar/` marker - it may be exactly the path
    `init_vault` is about to create."""
    return _resolve_candidate_path(explicit)


def resolve_vault_path(explicit: Path | str | None = None) -> Path:
    """Resolve the vault path to use.

    `explicit`, when given, takes precedence over `VAULT_PATH`. The
    result is always absolute, and is verified to exist, be a
    directory, and contain a `.vacancy-radar/` marker directory before
    being returned.
    """
    path = _resolve_candidate_path(explicit)

    if not path.exists():
        raise VaultNotFoundError(path, reason="path does not exist")
    if not path.is_dir():
        raise VaultNotFoundError(path, reason="path is not a directory")
    if not vault_marker_path(path).is_dir():
        raise VaultNotFoundError(
            path,
            reason=f"expected a {VAULT_MARKER_DIRNAME!r} marker directory at its root",
        )

    return path


class FusionStrategy(StrEnum):
    """How hybrid mode combines its keyword and semantic candidate sets.

    A config-layer concept, not `search`'s: `search.py` reads whichever
    member is configured to decide which LanceDB reranker class to use
    (see design.md) - defined here, not there, since `SearchConfig`
    needs it and nothing about it is retrieval-specific.
    """

    RRF = "rrf"
    LINEAR_COMBINATION = "linear_combination"


class InvalidSearchConfigError(Exception):
    """Raised when an environment variable `resolve_search_config` reads
    holds a value that can't become the field it configures."""

    def __init__(self, env_var: str, value: str, *, reason: str) -> None:
        self.env_var = env_var
        self.value = value
        super().__init__(f"{env_var}={value!r} is invalid: {reason}")


_SEARCH_DEFAULT_MODE_ENV = "SEARCH_DEFAULT_MODE"
_SEARCH_DEFAULT_VECTOR_WEIGHT_ENV = "SEARCH_DEFAULT_VECTOR_WEIGHT"
_SEARCH_DEFAULT_LIMIT_ENV = "SEARCH_DEFAULT_LIMIT"
_SEARCH_FUSION_STRATEGY_ENV = "SEARCH_FUSION_STRATEGY"


@dataclass(frozen=True)
class SearchConfig:
    """`search()`'s configurable defaults - stage 5 retuned
    `default_vector_weight` and `fusion_strategy` from measurement,
    without editing `search.py` (see design.md).

    `default_vector_weight=0.5` and `fusion_strategy=LINEAR_COMBINATION`
    are the eval-harness change's measured winner, not a guess: a
    30-query sweep across keyword, semantic, and hybrid (5 weights x 2
    fusion strategies) against the fixture vault found Linear
    Combination fusion at vector_weight 0.3-0.6 tied for the best
    overall recall@5 (0.794, vs. keyword's 0.761 and semantic's 0.678),
    with 0.7 tying on recall but scoring lower on MRR - 0.5 is the
    middle of that tied band. This **contradicts stage 4's default
    fusion choice**: RRF (the previous default) actually
    *underperforms* plain keyword search on this corpus (overall
    recall@5 0.672, identical across every weight, since RRF is rank-
    based and weight-agnostic) - see README.md's retrieval evaluation
    table and this change's tasks.md section 5 for the full numbers.
    Stage 4's keyword-favors-proper-nouns hypothesis held on the
    `exact_name` category specifically, but not as a reason to prefer
    RRF fusion overall.

    `default_mode` is a plain `str` (one of `SearchMode`'s values, e.g.
    `"hybrid"`), not a `SearchMode` member: importing `SearchMode` here
    would cycle back through `search.py`'s import of this module for
    `resolve_search_config`. `SearchMode` being a `StrEnum` means every
    comparison and construction (`SearchMode(config.default_mode)`,
    `config.default_mode == SearchMode.HYBRID`) works identically either
    way.
    """

    default_mode: str = "hybrid"
    default_vector_weight: float = 0.5
    default_limit: int = 10
    fusion_strategy: FusionStrategy = FusionStrategy.LINEAR_COMBINATION


_VALID_SEARCH_MODES = frozenset({"keyword", "semantic", "hybrid"})
"""Mirrors `search.SearchMode`'s values without importing it - see
`SearchConfig`'s docstring for why. `search.py`'s test suite cross-checks
this set against `SearchMode`'s actual members so the two can't drift
silently."""


def _env_search_mode(env_var: str, default: str) -> str:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    if raw not in _VALID_SEARCH_MODES:
        valid = sorted(_VALID_SEARCH_MODES)
        raise InvalidSearchConfigError(
            env_var, raw, reason=f"not a valid SearchMode (expected one of {valid})"
        )
    return raw


def _env_fusion_strategy(env_var: str, default: FusionStrategy) -> FusionStrategy:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return FusionStrategy(raw)
    except ValueError as exc:
        raise InvalidSearchConfigError(
            env_var, raw, reason=f"not a valid FusionStrategy ({exc})"
        ) from exc


def _env_float(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise InvalidSearchConfigError(env_var, raw, reason="not a float") from exc


def _env_int(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise InvalidSearchConfigError(env_var, raw, reason="not an int") from exc


def resolve_search_config() -> SearchConfig:
    """Resolve `search()`'s defaults from environment variables, falling
    back to `SearchConfig`'s field defaults for any that are unset.

    `SEARCH_DEFAULT_MODE`, `SEARCH_DEFAULT_VECTOR_WEIGHT`,
    `SEARCH_DEFAULT_LIMIT`, `SEARCH_FUSION_STRATEGY` - each resolved
    independently, mirroring `resolve_vault_path`'s
    explicit-then-env-then-default precedence (minus the explicit-
    argument layer: `search()` itself is where an explicit call
    argument overrides what this function resolves - see design.md).
    """
    fields = SearchConfig()
    return SearchConfig(
        default_mode=_env_search_mode(_SEARCH_DEFAULT_MODE_ENV, fields.default_mode),
        default_vector_weight=_env_float(
            _SEARCH_DEFAULT_VECTOR_WEIGHT_ENV, fields.default_vector_weight
        ),
        default_limit=_env_int(_SEARCH_DEFAULT_LIMIT_ENV, fields.default_limit),
        fusion_strategy=_env_fusion_strategy(
            _SEARCH_FUSION_STRATEGY_ENV, fields.fusion_strategy
        ),
    )
