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

from panha.dialogs.ai_detector_dialog import AIDetectorDialog  # noqa: E402
from panha.dialogs.config_dialog import ConfigDialog  # noqa: E402
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
from panha.mastering import MasteringSettings  # noqa: E402
from panha.metadata import Metadata  # noqa: E402
from panha.widgets import (  # noqa: E402
    MasteringPanel,
    SystemStatsWidget,
    TransportBar,
)
from panha.widgets.worker import build_items  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_constructs(qapp):
    win = MainWindow()
    try:
        assert win.windowTitle() == "Panha Audio Meta Data"
        assert win.table.columnCount() == 4
        assert hasattr(win, "mastering_panel")
        assert hasattr(win, "transport")
        assert hasattr(win, "system_stats")
        # The X-MIXM grid has exactly 13 slider columns.
        assert len(win.mastering_panel._columns) == 13
    finally:
        win.system_stats.stop()
        win.close()


def test_mastering_panel_emits_changed(qapp):
    panel = MasteringPanel()
    captured: list[MasteringSettings] = []
    panel.changed.connect(captured.append)
    panel._columns["bass"].set_value(50)
    panel._columns["gain"].set_value(20)
    assert captured, "MasteringPanel.changed never fired"
    final = captured[-1]
    assert final.bass == 50
    assert final.gain == 20
    panel.deleteLater()


def test_mastering_panel_set_settings_roundtrip(qapp):
    panel = MasteringPanel()
    panel.set_settings(MasteringSettings(bass=70, comp=30, gain=10))
    out = panel.settings()
    assert out.bass == 70
    assert out.comp == 30
    assert out.gain == 10
    panel.deleteLater()


def test_mastering_panel_bypass_dims_widget(qapp):
    panel = MasteringPanel()
    panel.set_bypass(True)
    assert panel.isEnabled() is False
    panel.set_bypass(False)
    assert panel.isEnabled() is True
    panel.deleteLater()


def test_transport_bar_loads_source_and_clears(qapp, tmp_path: Path):
    bar = TransportBar()
    fake = tmp_path / "x.mp3"
    fake.write_bytes(b"")
    bar.load_source(fake)
    bar.load_source(None)
    assert bar.lbl_position.text() == "0:00"
    bar.deleteLater()


def test_transport_bar_emits_bypass_signal(qapp):
    bar = TransportBar()
    received: list[bool] = []
    bar.bypass_changed.connect(received.append)
    bar.btn_bypass.click()
    bar.btn_bypass.click()
    assert received == [True, False]
    bar.deleteLater()


def test_config_dialog_emits_action_signals(qapp):
    dlg = ConfigDialog()
    fired: list[str] = []
    dlg.add_files_requested.connect(lambda: fired.append("add_files"))
    dlg.start_export_requested.connect(lambda: fired.append("start"))
    dlg.stop_export_requested.connect(lambda: fired.append("stop"))
    dlg.btn_add_files.click()
    dlg.btn_start.click()
    dlg.btn_stop.click()
    assert fired == ["add_files", "start", "stop"]
    dlg.set_export_running(True)
    assert dlg.btn_start.isEnabled() is False
    assert dlg.btn_stop.isEnabled() is True
    dlg.deleteLater()


def test_ai_detector_dialog_lists_added_files(qapp, tmp_path: Path):
    dlg = AIDetectorDialog()
    a = tmp_path / "a.mp3"
    b = tmp_path / "b.mp3"
    c = tmp_path / "c.txt"
    for p in (a, b, c):
        p.write_bytes(b"")

    added = dlg.add_paths([str(a), str(b), str(c)])
    assert added == 2, "non-audio files must be skipped"
    assert dlg.table.rowCount() == 2
    assert dlg.table.item(0, 0).text() == "a.mp3"
    # Analysis columns start as placeholder em-dashes with a tooltip.
    placeholder = dlg.table.item(0, 1)
    assert placeholder.text() == "\u2014"
    assert "not implemented" in placeholder.toolTip().lower()

    # Re-adding the same file is idempotent.
    assert dlg.add_paths([str(a)]) == 0
    assert dlg.table.rowCount() == 2

    # Backend hook lets a future analyser fill in real values.
    dlg.set_row_result(0, platform="Suno", confidence="92%", verdict="AI")
    assert dlg.table.item(0, 1).text() == "Suno"
    assert dlg.table.item(0, 2).text() == "92%"
    assert dlg.table.item(0, 3).text() == "AI"

    dlg._on_clear()
    assert dlg.table.rowCount() == 0
    dlg.deleteLater()


def test_system_stats_widget_reports_values(qapp):
    widget = SystemStatsWidget(interval_ms=5000)
    widget._refresh()
    assert widget.cpu_text().startswith("CPU: ")
    assert widget.ram_text().startswith("RAM: ")
    widget.stop()
    widget.deleteLater()


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
