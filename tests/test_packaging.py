"""Asserts the built distribution's metadata contract.

A degraded PyPI page - no license, no classifiers, a missing console
script - is only discoverable after a release, and a released version
number can never be reused. Building here on every run makes that a CI
failure instead.

The build runs once per session into a temp dir, so the repo's own
`dist/` is never touched, and skips when `uv` is absent rather than
failing a bare environment. `uv build` with hatchling resolves no
dependencies, so this needs no network.
"""

import re
import shutil
import subprocess
import tarfile
import zipfile
from email.message import Message
from email.parser import BytesHeaderParser
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv is not on PATH; nothing to build the distribution with",
)

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Development status, license, intended audience, and a 3.12 language
# classifier are the four the spec requires; more is fine.
_MIN_CLASSIFIERS = 4


@pytest.fixture(scope="session")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Build the wheel and sdist once per session; return their paths."""
    out_dir = tmp_path_factory.mktemp("dist")
    subprocess.run(  # noqa: S603
        [shutil.which("uv"), "build", "--out-dir", str(out_dir)],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )
    wheels = list(out_dir.glob("*.whl"))
    sdists = list(out_dir.glob("*.tar.gz"))
    assert len(wheels) == 1, f"expected one wheel, got {wheels}"
    assert len(sdists) == 1, f"expected one sdist, got {sdists}"
    return wheels[0], sdists[0]


@pytest.fixture(scope="session")
def wheel(built_dist: tuple[Path, Path]) -> Path:
    return built_dist[0]


@pytest.fixture(scope="session")
def sdist(built_dist: tuple[Path, Path]) -> Path:
    return built_dist[1]


def _dist_info_name(archive: zipfile.ZipFile) -> str:
    for name in archive.namelist():
        head = name.split("/")[0]
        if head.endswith(".dist-info"):
            return head
    pytest.fail("wheel contains no .dist-info directory")


def _metadata(wheel: Path) -> tuple[Message, str]:
    """Return the wheel's parsed METADATA headers and its body."""
    with zipfile.ZipFile(wheel) as archive:
        raw = archive.read(f"{_dist_info_name(archive)}/METADATA")
    head, _, body = raw.partition(b"\n\n")
    return BytesHeaderParser().parsebytes(head), body.decode()


def test_wheel_declares_both_console_scripts(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        entry_points = archive.read(
            f"{_dist_info_name(archive)}/entry_points.txt"
        ).decode()

    console_scripts, _, _ = entry_points.partition("\n[")
    assert "[console_scripts]" in console_scripts
    assert re.search(r"^vacancy-radar\s*=", console_scripts, re.MULTILINE)
    assert re.search(r"^vacancy-radar-mcp\s*=", console_scripts, re.MULTILINE)


def test_wheel_metadata_declares_license_expression(wheel: Path) -> None:
    headers, _ = _metadata(wheel)
    assert headers["License-Expression"] == "MIT"


def test_wheel_metadata_has_landing_page_fields(wheel: Path) -> None:
    headers, _ = _metadata(wheel)

    assert len(headers.get_all("Classifier") or []) >= _MIN_CLASSIFIERS
    assert headers.get_all("Project-URL")
    assert headers["Author-email"] or headers["Author"]
    assert "3.12" in (headers["Requires-Python"] or "")


def test_wheel_carries_the_readme_as_long_description(wheel: Path) -> None:
    headers, body = _metadata(wheel)
    assert headers["Description-Content-Type"].startswith("text/markdown")
    assert body.strip()


def test_wheel_ships_the_license_file(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        dist_info = _dist_info_name(archive)
        names = archive.namelist()
    assert f"{dist_info}/licenses/LICENSE" in names


def test_sdist_ships_the_license_file(sdist: Path) -> None:
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
    roots = {name.split("/")[0] for name in names}
    assert len(roots) == 1, f"sdist has more than one root: {roots}"
    root = roots.pop()
    assert f"{root}/LICENSE" in names
