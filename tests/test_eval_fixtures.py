from pathlib import Path

from eval.lib.fixtures import load_jsonl


def test_load_jsonl_parses_one_object_per_line(tmp_path: Path):
    path = tmp_path / "sample.jsonl"
    path.write_text('{"id": "a", "value": 1}\n{"id": "b", "value": 2}\n')

    result = load_jsonl(path)

    assert result == [{"id": "a", "value": 1}, {"id": "b", "value": 2}]


def test_load_jsonl_skips_blank_lines(tmp_path: Path):
    path = tmp_path / "sample.jsonl"
    path.write_text('{"id": "a"}\n\n{"id": "b"}\n')

    result = load_jsonl(path)

    assert result == [{"id": "a"}, {"id": "b"}]


def test_load_jsonl_returns_empty_list_for_missing_file(tmp_path: Path):
    result = load_jsonl(tmp_path / "does-not-exist.jsonl")

    assert result == []


def test_load_jsonl_returns_empty_list_for_empty_file(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("")

    result = load_jsonl(path)

    assert result == []
