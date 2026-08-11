from ai_layer import __version__
import json
import os
import signal

from ai_layer.core.config import get_settings
from ai_layer.core import mcp_process
from ai_layer.core.mcp_process import list_mcp_processes, registered_mcp_process


def test_running_mcp_process_registers_version(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / ".ai-layer"))
    get_settings.cache_clear()
    with registered_mcp_process() as marker:
        items = list_mcp_processes()
        assert marker["version"] == __version__
        assert len(items) == 1
        assert items[0]["version_match"] is True
        assert items[0]["current_version"] == __version__
    assert list_mcp_processes() == []
    get_settings.cache_clear()


def test_mcp_server_main_registers_process_lifecycle():
    from pathlib import Path

    source = (Path(__file__).parents[1] / "src" / "ai_layer" / "mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    assert "with registered_mcp_process():" in source
    assert "mcp.run()" in source


def test_mcp_process_match_requires_exact_argv_token(tmp_path):
    entry = tmp_path / "12345"
    entry.mkdir()
    (entry / "cmdline").write_bytes(b"python\x00/tmp/notes-ai-layer-mcp-debug.txt\x00")
    assert mcp_process._is_our_mcp_process(entry, os.getuid(), exclude_pid=-1) is False

    (entry / "cmdline").write_bytes(b"/venv/bin/python\x00/venv/bin/ai-layer-mcp\x00")
    assert mcp_process._is_our_mcp_process(entry, os.getuid(), exclude_pid=-1) is True


def test_mcp_stop_targets_only_registered_exact_processes(tmp_path, monkeypatch):
    process_dir = tmp_path / "markers"
    process_dir.mkdir()
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    registered_pid = 42420
    unrelated_pid = 42421

    (process_dir / f"{registered_pid}.json").write_text(
        json.dumps({"pid": registered_pid, "version": "0.1.5.1"}),
        encoding="utf-8",
    )
    reg_entry = proc_root / str(registered_pid)
    reg_entry.mkdir()
    (reg_entry / "cmdline").write_bytes(b"/venv/bin/python\x00/venv/bin/ai-layer-mcp\x00")

    unrelated = proc_root / str(unrelated_pid)
    unrelated.mkdir()
    (unrelated / "cmdline").write_bytes(b"/usr/bin/editor\x00ai-layer-mcp-notes\x00")

    monkeypatch.setattr(mcp_process, "_process_dir", lambda: process_dir)
    monkeypatch.setattr(
        mcp_process,
        "Path",
        lambda value: proc_root if str(value) == "/proc" else __import__("pathlib").Path(value),
    )
    calls = []

    def fake_kill(pid, sig):
        calls.append((pid, sig))
        if pid == registered_pid and sig == signal.SIGTERM:
            import shutil

            shutil.rmtree(reg_entry)

    monkeypatch.setattr(mcp_process.os, "kill", fake_kill)
    result = mcp_process.stop_user_mcp_processes(timeout_seconds=0)

    assert result["stopped"] == [registered_pid]
    assert result["forced"] == []
    assert all(pid != unrelated_pid for pid, _ in calls)
