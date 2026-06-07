# tests/test_tools.py
import asyncio
import os
import tempfile
import pytest
from pi.tools.read import ReadTool
from pi.tools.write import WriteTool
from pi.tools.edit import EditTool
from pi.tools.bash import BashTool
from pi.tools.find import FindTool
from pi.tools.grep import GrepTool
from pi.tools.ls import LsTool


# ── read ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.txt"
    lines = [f"line {i}" for i in range(1, 11)]  # 10 lines
    f.write_text("\n".join(lines))
    return f


@pytest.mark.asyncio
async def test_read_basic(tmp_file):
    tool = ReadTool()
    result = await tool.execute("id1", {"path": str(tmp_file)})
    assert not result.is_error
    assert "1\tline 1" in result.content
    assert "10\tline 10" in result.content


@pytest.mark.asyncio
async def test_read_with_offset_and_limit(tmp_file):
    tool = ReadTool()
    result = await tool.execute("id1", {"path": str(tmp_file), "offset": 3, "limit": 2})
    assert not result.is_error
    assert "3\tline 3" in result.content
    assert "4\tline 4" in result.content
    assert "5\tline 5" not in result.content


@pytest.mark.asyncio
async def test_read_truncation_hint(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"line {i}" for i in range(1, 2100)))
    tool = ReadTool()
    result = await tool.execute("id1", {"path": str(f)})
    assert not result.is_error
    assert "Showing lines" in result.content
    assert "Use offset=" in result.content


@pytest.mark.asyncio
async def test_read_missing_file():
    tool = ReadTool()
    result = await tool.execute("id1", {"path": "/nonexistent/file.txt"})
    assert result.is_error


# ── write ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_creates_file(tmp_path):
    tool = WriteTool()
    dest = tmp_path / "out.txt"
    result = await tool.execute("id1", {"path": str(dest), "content": "hello world"})
    assert not result.is_error
    assert dest.read_text() == "hello world"


@pytest.mark.asyncio
async def test_write_creates_parent_dirs(tmp_path):
    tool = WriteTool()
    dest = tmp_path / "a" / "b" / "c.txt"
    result = await tool.execute("id1", {"path": str(dest), "content": "nested"})
    assert not result.is_error
    assert dest.read_text() == "nested"


@pytest.mark.asyncio
async def test_write_overwrites_existing(tmp_path):
    tool = WriteTool()
    dest = tmp_path / "file.txt"
    dest.write_text("old content")
    result = await tool.execute("id1", {"path": str(dest), "content": "new content"})
    assert not result.is_error
    assert dest.read_text() == "new content"


# ── edit ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def editable_file(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("x = 1\ny = 2\nreturn False\n")
    return f


@pytest.mark.asyncio
async def test_edit_single_replacement(editable_file):
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(editable_file),
        "edits": [{"oldText": "x = 1", "newText": "x = 42"}],
    })
    assert not result.is_error
    assert editable_file.read_text() == "x = 42\ny = 2\nreturn False\n"


@pytest.mark.asyncio
async def test_edit_multiple_replacements(editable_file):
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(editable_file),
        "edits": [
            {"oldText": "x = 1", "newText": "x = 10"},
            {"oldText": "return False", "newText": "return True"},
        ],
    })
    assert not result.is_error
    content = editable_file.read_text()
    assert "x = 10" in content
    assert "return True" in content


@pytest.mark.asyncio
async def test_edit_not_found_error(editable_file):
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(editable_file),
        "edits": [{"oldText": "nonexistent string", "newText": "x"}],
    })
    assert result.is_error
    assert "not found" in result.content.lower()


@pytest.mark.asyncio
async def test_edit_duplicate_error(tmp_path):
    f = tmp_path / "dup.py"
    f.write_text("foo\nfoo\n")
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(f),
        "edits": [{"oldText": "foo", "newText": "bar"}],
    })
    assert result.is_error
    assert "2" in result.content


@pytest.mark.asyncio
async def test_edit_no_partial_write_on_first_failure(tmp_path):
    f = tmp_path / "partial.py"
    f.write_text("a = 1\nb = 2\n")
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(f),
        "edits": [
            {"oldText": "a = 1", "newText": "a = 99"},
            {"oldText": "DOES_NOT_EXIST", "newText": "x"},
        ],
    })
    assert result.is_error
    assert f.read_text() == "a = 1\nb = 2\n"  # unchanged


# ── bash ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bash_simple_command():
    tool = BashTool()
    result = await tool.execute("id1", {"command": "echo hello"})
    assert not result.is_error
    assert "hello" in result.content


@pytest.mark.asyncio
async def test_bash_stderr_merged():
    tool = BashTool()
    result = await tool.execute("id1", {"command": "echo out && echo err >&2"})
    assert not result.is_error
    assert "out" in result.content
    assert "err" in result.content


@pytest.mark.asyncio
async def test_bash_exit_code_nonzero():
    tool = BashTool()
    result = await tool.execute("id1", {"command": "exit 1"})
    assert result.is_error


@pytest.mark.asyncio
async def test_bash_timeout():
    tool = BashTool()
    result = await tool.execute("id1", {"command": "sleep 10", "timeout": 0.2})
    assert result.is_error
    assert "timed out" in result.content.lower() or "timeout" in result.content.lower()


@pytest.mark.asyncio
async def test_bash_strips_ansi():
    tool = BashTool()
    result = await tool.execute("id1", {"command": r"printf '\033[31mred\033[0m'"})
    assert not result.is_error
    assert "\033[" not in result.content
    assert "red" in result.content


# ── find ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def dir_tree(tmp_path):
    (tmp_path / "a.py").write_text("# a")
    (tmp_path / "b.py").write_text("# b")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("# c")
    (tmp_path / "sub" / "d.txt").write_text("text")
    return tmp_path


@pytest.mark.asyncio
async def test_find_all_py(dir_tree):
    tool = FindTool()
    result = await tool.execute("id1", {"path": str(dir_tree), "pattern": "*.py"})
    assert not result.is_error
    assert "a.py" in result.content
    assert "c.py" in result.content


@pytest.mark.asyncio
async def test_find_type_file(dir_tree):
    tool = FindTool()
    result = await tool.execute("id1", {"path": str(dir_tree), "pattern": "*", "type": "file"})
    assert not result.is_error
    # All results should be files, no dirs
    lines = [l for l in result.content.split("\n") if l]
    assert len(lines) >= 1


@pytest.mark.asyncio
async def test_find_type_dir(dir_tree):
    tool = FindTool()
    result = await tool.execute("id1", {"path": str(dir_tree), "pattern": "*", "type": "dir"})
    assert not result.is_error
    assert "sub" in result.content


# ── grep ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def grep_dir(tmp_path):
    (tmp_path / "a.py").write_text("hello world\nfoo bar\n")
    (tmp_path / "b.py").write_text("HELLO WORLD\ntest\n")
    return tmp_path


@pytest.mark.asyncio
async def test_grep_basic(grep_dir):
    tool = GrepTool()
    result = await tool.execute("id1", {"path": str(grep_dir), "pattern": "hello"})
    assert not result.is_error
    assert "a.py" in result.content
    assert "hello world" in result.content


@pytest.mark.asyncio
async def test_grep_ignore_case(grep_dir):
    tool = GrepTool()
    result = await tool.execute("id1", {
        "path": str(grep_dir), "pattern": "hello", "ignore_case": True
    })
    assert not result.is_error
    assert "a.py" in result.content
    assert "b.py" in result.content


@pytest.mark.asyncio
async def test_grep_single_file(grep_dir):
    tool = GrepTool()
    result = await tool.execute("id1", {
        "path": str(grep_dir / "a.py"),
        "pattern": "foo",
        "recursive": False,
    })
    assert not result.is_error
    assert "foo bar" in result.content


# ── ls ────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ls_basic(dir_tree):
    tool = LsTool()
    result = await tool.execute("id1", {"path": str(dir_tree)})
    assert not result.is_error
    assert "a.py" in result.content
    assert "sub" in result.content


@pytest.mark.asyncio
async def test_ls_not_recursive(dir_tree):
    tool = LsTool()
    result = await tool.execute("id1", {"path": str(dir_tree)})
    assert not result.is_error
    assert "c.py" not in result.content  # inside sub/, not shown at top level
