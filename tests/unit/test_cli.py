from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

import atlas.cli as cli


def test_settings_honours_data_dir_and_provider(tmp_path: Path) -> None:
    settings = cli._settings(Namespace(data_dir=str(tmp_path), provider="fake"))
    assert settings.data_dir == tmp_path
    assert settings.provider == "fake"


def test_storage_flags_parse_before_and_after_serve(tmp_path: Path) -> None:
    before = cli.build_parser().parse_args(
        ["--data-dir", str(tmp_path), "--provider", "fake", "serve"]
    )
    after = cli.build_parser().parse_args(
        ["serve", "--data-dir", str(tmp_path), "--provider", "fake"]
    )
    assert cli._settings(before).data_dir == tmp_path
    assert cli._settings(after).data_dir == tmp_path
    assert cli._settings(after).provider == "fake"


def test_serve_uses_the_resolved_settings(monkeypatch: Any, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    args = Namespace(
        data_dir=str(tmp_path),
        provider="fake",
        host="127.0.0.1",
        port=8123,
        reload=False,
    )

    assert cli.cmd_serve(args) == 0
    app = captured["app"]
    assert app.state.settings.data_dir == tmp_path
    assert app.state.settings.provider == "fake"
    assert captured["kwargs"] == {"host": "127.0.0.1", "port": 8123}
