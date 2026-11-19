import pytest


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKSAPP_DATA_DIR", str(tmp_path / "data"))
    from marksapp.db import connect
    c = connect()
    yield c
    c.close()


@pytest.fixture
def marks_files(tmp_path):
    from tests.fixtures import builders
    return builders.write_all_marks_files(tmp_path / "files")
