import importlib
import sys
from types import ModuleType


class _BlockingFinder:
    """Meta path finder that fails imports of the given module names."""

    def __init__(self, blocked_names: set[str]) -> None:
        self.blocked_names = blocked_names

    def find_module(self, fullname: str, _path: object = None) -> ModuleType | None:
        if fullname in self.blocked_names:
            msg = f"{fullname} is blocked for this test"
            raise ImportError(msg)
        return None


def test_import_succeeds_without_lancedb_or_fastembed() -> None:
    blocked = {"lancedb", "fastembed"}
    finder = _BlockingFinder(blocked)

    stashed = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "vacancy_radar" or name.startswith("vacancy_radar.")
    }

    sys.meta_path.insert(0, finder)
    try:
        module = importlib.import_module("vacancy_radar")
        assert module is not None
    finally:
        sys.meta_path.remove(finder)
        for name in list(sys.modules):
            if name == "vacancy_radar" or name.startswith("vacancy_radar."):
                del sys.modules[name]
        sys.modules.update(stashed)
