from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_cli_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run-local-ai-enrichment.py"
    spec = importlib.util.spec_from_file_location("run_local_ai_enrichment_cli", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_move_files_without_apply_library_layout_errors(monkeypatch, capsys):
    cli = _load_cli_module()
    args = SimpleNamespace(
        move_files=True,
        apply_library_layout=None,
        plan_library_layout=False,
        use_local_ai=False,
    )
    monkeypatch.setattr(cli, "parse_args", lambda: args)

    assert cli.main() == 1

    err = capsys.readouterr().err
    assert "--move-files requires --apply-library-layout <PLAN_ID>" in err
    assert "--plan-library-layout" in err


def test_plan_library_layout_dispatches_without_enrichment(monkeypatch, tmp_path, capsys):
    cli = _load_cli_module()
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    args = SimpleNamespace(plan_library_layout=True, limit=1)
    calls: dict[str, object] = {}
    config = SimpleNamespace(model="test-model")

    monkeypatch.setattr(cli.JellyfinConfig, "get_music_library_path", lambda: str(music_dir))
    monkeypatch.setattr(cli, "scan_music_files", lambda path: [{"title": "Song", "artist": "Artist", "path": str(music_dir / "song.mp3")}, {"title": "Extra"}])
    monkeypatch.setitem(sys.modules, "app.logic.local_ai.config", SimpleNamespace(get_config=lambda: config))

    def fake_plan_library_layout(songs, *, music_dir, config):
        calls["songs"] = songs
        calls["music_dir"] = music_dir
        calls["config"] = config
        return {"plan_id": "abcd1234abcd1234", "tree": [], "moves": [], "conflicts": []}

    planner = SimpleNamespace(
        plan_library_layout=fake_plan_library_layout,
        save_layout_plan=lambda plan: tmp_path / "plans" / f"{plan['plan_id']}.json",
        format_layout_plan_tree=lambda plan: "TREE OUTPUT",
    )
    monkeypatch.setitem(sys.modules, "app.logic.local_ai.library_layout_planner", planner)

    assert cli._run_library_layout_plan(args) == 0

    out = capsys.readouterr().out
    assert "abcd1234abcd1234" in out
    assert "TREE OUTPUT" in out
    assert calls["songs"] == [{"title": "Song", "artist": "Artist", "path": str(music_dir / "song.mp3")}]
    assert calls["music_dir"] == str(music_dir)
    assert calls["config"] is config


def test_apply_library_layout_dispatches_saved_plan(monkeypatch, tmp_path, capsys):
    cli = _load_cli_module()
    music_dir = tmp_path / "music"
    calls: dict[str, object] = {}

    monkeypatch.setattr(cli.JellyfinConfig, "get_music_library_path", lambda: str(music_dir))

    def fake_apply_library_layout_plan(plan_id, *, current_music_dir):
        calls["plan_id"] = plan_id
        calls["current_music_dir"] = current_music_dir
        return {"errors": 0, "files_moved": 2}

    monkeypatch.setitem(
        sys.modules,
        "app.logic.local_ai.library_layout_planner",
        SimpleNamespace(apply_library_layout_plan=fake_apply_library_layout_plan),
    )

    assert cli._run_library_layout_apply("abcd1234abcd1234") == 0

    out = capsys.readouterr().out
    assert '"files_moved": 2' in out
    assert calls == {"plan_id": "abcd1234abcd1234", "current_music_dir": str(music_dir)}
