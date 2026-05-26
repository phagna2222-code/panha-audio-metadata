"""Smoke tests for the PyQt6 UI (run under the ``offscreen`` Qt platform).

These verify the main window, dialogs and helper widgets can be constructed
without errors. They do not exercise the event loop beyond construction.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from panha.dialogs.export_settings_dialog import (  # noqa: E402
    ExportSettings,
    ExportSettingsDialog,
)
from panha.dialogs.file_info_dialog import (  # noqa: E402
    FileInformationDialog,
    FileInformationState,
    TracklistOptions,
)
from panha.main_window import MainWindow  # noqa: E402
from panha.metadata import Metadata  # noqa: E402
from panha.widgets.worker import build_items  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_constructs(qapp):
    win = MainWindow()
    assert win.windowTitle() == "Panha Audio Meta Data"
    assert win.table.columnCount() == 4
    win.close()


def test_file_information_dialog_roundtrip(qapp, tmp_path: Path, monkeypatch):
    # Redirect template storage into tmp_path so we don't touch $HOME.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    state = FileInformationState(
        metadata=Metadata(title="X", artist="Y", album="Z", year="2030", genre="Pop"),
        tracklist=TracklistOptions(uppercase=True, remove_track_number=False, cover_size=2048),
    )
    dlg = FileInformationDialog(state)
    collected = dlg.collect_state()
    assert collected.metadata.title == "X"
    assert collected.metadata.artist == "Y"
    assert collected.metadata.year == "2030"
    assert collected.tracklist.uppercase is True
    assert collected.tracklist.remove_track_number is False
    assert collected.tracklist.cover_size == 2048


def test_export_settings_dialog_roundtrip(qapp):
    s = ExportSettings(format="WAV", sample_rate="48000 Hz", bit_depth="16-bit", max_threads=8)
    dlg = ExportSettingsDialog(s)
    out = dlg.collect()
    assert out.format == "WAV"
    assert out.sample_rate == "48000 Hz"
    assert out.bit_depth == "16-bit"
    assert out.max_threads == 8


def test_build_items_renames_and_strips_track_number(tmp_path: Path):
    src = tmp_path / "01. Song.mp3"
    src.write_bytes(b"")
    state = FileInformationState(
        metadata=Metadata(artist="A"),
        tracklist=TracklistOptions(uppercase=True, remove_track_number=True, cover_size=1600),
    )
    items = build_items([str(src)], str(tmp_path / "out"), state)
    assert len(items) == 1
    item = items[0]
    assert Path(item.target).name == "SONG.mp3"
    # Title was empty in template, so it is auto-filled with the stem
    assert item.metadata.title == "SONG"
    assert item.metadata.artist == "A"
