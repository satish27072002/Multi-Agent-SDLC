"""Tests for core.workspace module."""

import pytest

from src.agents.coding import GeneratedFile
from src.core.workspace import write_files

pytestmark = pytest.mark.unit


class TestWriteFiles:
    def test_writes_single_file(self, tmp_path):
        files = [GeneratedFile(path="hello.py", content="print('hi')", explanation="test")]
        written = write_files(tmp_path, files)
        assert len(written) == 1
        assert (tmp_path / "hello.py").read_text() == "print('hi')"

    def test_creates_parent_directories(self, tmp_path):
        files = [GeneratedFile(path="src/deep/nested/file.py", content="x = 1", explanation="test")]
        write_files(tmp_path, files)
        assert (tmp_path / "src" / "deep" / "nested" / "file.py").exists()

    def test_writes_multiple_files(self, tmp_path):
        files = [
            GeneratedFile(path="a.py", content="a = 1", explanation="file a"),
            GeneratedFile(path="b.py", content="b = 2", explanation="file b"),
        ]
        written = write_files(tmp_path, files)
        assert len(written) == 2
        assert (tmp_path / "a.py").read_text() == "a = 1"
        assert (tmp_path / "b.py").read_text() == "b = 2"

    def test_overwrites_existing_file(self, tmp_path):
        (tmp_path / "exists.py").write_text("old")
        files = [GeneratedFile(path="exists.py", content="new", explanation="updated")]
        write_files(tmp_path, files)
        assert (tmp_path / "exists.py").read_text() == "new"
