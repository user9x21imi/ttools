import pytest

from tspotify import paths


@pytest.fixture(autouse=True)
def private_test_paths(tmp_path, monkeypatch):
    for name in ("DATA", "CACHE", "CONFIG", "BACKEND_CONFIG", "BACKEND_CACHE"):
        monkeypatch.setattr(paths, name, tmp_path / name.lower())
    monkeypatch.setattr(paths, "TOKEN_FILE", paths.BACKEND_CACHE / "token.json")
    paths.prepare()
