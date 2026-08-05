"""Vault path resolution.

Precedence: an explicit path argument, then the `VAULT_PATH`
environment variable, then `VaultNotConfiguredError`. The explicit
argument is also the seam a future MCP-roots-based caller (stage 8)
will use — it can resolve a client-supplied root and pass it in here
without this function's signature changing.
"""

import os
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


def resolve_vault_path(explicit: Path | str | None = None) -> Path:
    """Resolve the vault path to use.

    `explicit`, when given, takes precedence over `VAULT_PATH`. The
    result is always absolute, and is verified to exist, be a
    directory, and contain a `.vacancy-radar/` marker directory before
    being returned.
    """
    candidate = explicit if explicit is not None else os.environ.get("VAULT_PATH")
    if candidate is None:
        raise VaultNotConfiguredError

    path = Path(candidate).resolve()

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
