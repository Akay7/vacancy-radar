"""Byte-faithful parsing and serialization of markdown + YAML frontmatter.

Round-trip fidelity (key order, comments, quoting style, body whitespace)
matters because the vault is hand-edited and git-tracked: a writer that
reformats what a human wrote produces unreadable diffs. `ruamel.yaml`'s
round-trip mode is what makes that guarantee possible.
"""

import io
from collections.abc import Mapping

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

_DELIMITER = "---"

_yaml = YAML(typ="rt")
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)


class FrontmatterError(Exception):
    """Base class for frontmatter parsing errors."""


class MissingFrontmatterError(FrontmatterError):
    """Raised when the text has no opening frontmatter delimiter."""

    def __init__(self, filename: str | None = None) -> None:
        self.filename = filename
        where = f" in {filename}" if filename else ""
        super().__init__(f"No frontmatter delimiter found{where}")


class MalformedFrontmatterError(FrontmatterError):
    """Raised when the frontmatter block is not parseable YAML."""

    def __init__(self, filename: str | None, cause: Exception) -> None:
        self.filename = filename
        self.cause = cause
        where = f" in {filename}" if filename else ""
        super().__init__(f"Malformed frontmatter YAML{where}: {cause}")


def parse(text: str, *, filename: str | None = None) -> tuple[CommentedMap, str]:
    """Parse `text` into (metadata, body).

    `text` must start with a `---` delimiter line, followed by a YAML
    block, followed by a closing `---` delimiter line, followed by the
    body. Only the first `---` line encountered after the opening
    delimiter is treated as the close — a `---` line inside the body is
    left alone.
    """
    lines = text.splitlines(keepends=True)

    if not lines or lines[0].rstrip("\r\n") != _DELIMITER:
        raise MissingFrontmatterError(filename)

    close_index = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == _DELIMITER:
            close_index = i
            break

    if close_index is None:
        raise MalformedFrontmatterError(
            filename, ValueError("frontmatter block is never closed")
        )

    yaml_text = "".join(lines[1:close_index])
    body = "".join(lines[close_index + 1 :])

    try:
        metadata = _yaml.load(yaml_text)
    except Exception as exc:
        raise MalformedFrontmatterError(filename, exc) from exc

    return metadata, body


def serialize(metadata: Mapping[str, object], body: str) -> str:
    """Serialize `metadata` and `body` back into frontmatter + body text."""
    stream = io.StringIO()
    _yaml.dump(metadata, stream)
    yaml_text = stream.getvalue()
    return f"{_DELIMITER}\n{yaml_text}{_DELIMITER}\n{body}"
