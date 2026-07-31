from vacancy_radar import manifest as manifest_module


def test_content_hash_stable_for_same_bytes():
    assert manifest_module.content_hash(b"hello") == manifest_module.content_hash(b"hello")


def test_content_hash_differs_for_different_bytes():
    assert manifest_module.content_hash(b"hello") != manifest_module.content_hash(b"world")


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "manifest.json"
    m = manifest_module.IngestManifest()
    m.files["a/vacancy.yaml"] = manifest_module.FileEntry(
        content_hash="abc123", chunk_ids=["a/vacancy.yaml"]
    )
    manifest_module.save(m, path=path)

    loaded = manifest_module.load(path=path)
    assert loaded.files["a/vacancy.yaml"].content_hash == "abc123"
    assert loaded.compat_stamp == m.compat_stamp


def test_load_missing_file_returns_empty_manifest(tmp_path):
    loaded = manifest_module.load(path=tmp_path / "does-not-exist.json")
    assert loaded.files == {}


def test_delete_removes_manifest_file(tmp_path):
    path = tmp_path / "manifest.json"
    manifest_module.save(manifest_module.IngestManifest(), path=path)
    assert path.exists()
    manifest_module.delete(path=path)
    assert not path.exists()


def test_delete_missing_file_does_not_raise(tmp_path):
    manifest_module.delete(path=tmp_path / "does-not-exist.json")
