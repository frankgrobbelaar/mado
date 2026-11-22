from pathlib import Path

import pytest

from mado.config import DataPaths


def test_data_lives_in_local_app_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("MADO_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert DataPaths.default().root == tmp_path / "Mado"


def test_mado_data_dir_moves_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("MADO_DATA_DIR", str(tmp_path / "Elsewhere"))

    assert DataPaths.default().root == tmp_path / "Elsewhere"


def test_a_mado_data_dir_with_dot_dots_is_tidied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("MADO_DATA_DIR", f"{tmp_path}/app/../Elsewhere")

    assert DataPaths.default().root == tmp_path / "Elsewhere"


def test_everything_sits_inside_the_data_folder(tmp_path: Path):
    paths = DataPaths(tmp_path)

    assert paths.database == tmp_path / "mado.db"
    assert paths.backups == tmp_path / "backups"
    assert paths.logs == tmp_path / "logs"
    assert paths.cache == tmp_path / "cache"
    assert paths.tools == tmp_path / "tools"
