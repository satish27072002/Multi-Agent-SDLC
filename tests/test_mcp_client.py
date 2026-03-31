"""Tests for protocols.mcp_client module."""

import asyncio

import pytest

from src.protocols.mcp_client import LocalToolsMCP


@pytest.fixture
def mcp_workspace(tmp_path):
    (tmp_path / "hello.py").write_text("print('hello')")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.py").write_text("x = 1")
    return tmp_path


class TestLocalToolsMCP:
    def test_read_file(self, mcp_workspace):
        mcp = LocalToolsMCP(mcp_workspace)
        result = asyncio.run(mcp.read_file("hello.py"))
        assert not result.is_error
        assert "print('hello')" in result.content

    def test_read_file_not_found(self, mcp_workspace):
        mcp = LocalToolsMCP(mcp_workspace)
        result = asyncio.run(mcp.read_file("nonexistent.py"))
        assert result.is_error
        assert "not found" in result.content.lower()

    def test_write_file(self, mcp_workspace):
        mcp = LocalToolsMCP(mcp_workspace)
        result = asyncio.run(mcp.write_file("new_file.py", "content = True"))
        assert not result.is_error
        assert (mcp_workspace / "new_file.py").read_text() == "content = True"

    def test_write_file_creates_dirs(self, mcp_workspace):
        mcp = LocalToolsMCP(mcp_workspace)
        result = asyncio.run(mcp.write_file("a/b/c.py", "deep = True"))
        assert not result.is_error
        assert (mcp_workspace / "a" / "b" / "c.py").exists()

    def test_list_directory(self, mcp_workspace):
        mcp = LocalToolsMCP(mcp_workspace)
        result = asyncio.run(mcp.list_directory("."))
        assert not result.is_error
        assert "hello.py" in result.content
        assert "subdir" in result.content

    def test_list_directory_not_found(self, mcp_workspace):
        mcp = LocalToolsMCP(mcp_workspace)
        result = asyncio.run(mcp.list_directory("nonexistent"))
        assert result.is_error

    def test_run_command(self, mcp_workspace):
        mcp = LocalToolsMCP(mcp_workspace)
        result = asyncio.run(mcp.run_command("echo hello"))
        assert not result.is_error
        assert "hello" in result.content

    def test_run_command_timeout(self, mcp_workspace):
        mcp = LocalToolsMCP(mcp_workspace)
        result = asyncio.run(mcp.run_command("sleep 10", timeout=1))
        assert result.is_error
        assert "timed out" in result.content.lower()
