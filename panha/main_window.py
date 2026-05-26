"""Main application window for Panha Audio Meta Data."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __app_name__, __version__
from .dialogs import (
    ExportSettings,
    ExportSettingsDialog,
    FileInformationDialog,
)
from .dialogs.file_info_dialog import FileInformationState
from .metadata import format_duration, probe_duration_seconds
from .widgets import WaveformView
from .widgets.worker import BatchWorker, build_items, start_worker

SUPPORTED_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}


@dataclasses.dataclass
class QueueRow:
    path: str
    duration_seconds: float
    status: str = "Pending"

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def file_type(self) -> str:
        return os.path.splitext(self.path)[1].lstrip(".").upper() or "FILE"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(__app_name__)
        self.resize(1180, 760)
        self.setWindowIcon(self._make_icon())

        self._rows: list[QueueRow] = []
        self._info_state = FileInformationState()
        self._export_settings = ExportSettings(format="MP3", sample_rate="44100 Hz", bit_depth="24-bit")
        self._output_dir: str = str(Path.home() / "PanhaExports")
        self._worker: BatchWorker | None = None
        self._thread: QThread | None = None

        self._build_ui()
        self._update_buttons()

    # -- icon -----------------------------------------------------------

    def _make_icon(self) -> QIcon:
        # Use the small "musical-note like" emoji glyph rendered as fallback
        # icon to avoid bundling a binary asset. Falls back to default icon.
        from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap

        pm = QPixmap(64, 64)
        pm.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#5fa8ff"))
        f = QFont()
        f.setBold(True)
        f.setPointSize(36)
        painter.setFont(f)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "\u266B")
        painter.end()
        return QIcon(pm)

    # -- ui -------------------------------------------------------------

    def _section_frame(self, title: str | None = None) -> tuple[QWidget, QVBoxLayout]:
        frame = QWidget()
        frame.setObjectName("sectionFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(8)
        if title:
            label = QLabel(title)
            label.setObjectName("sectionTitle")
            layout.addWidget(label)
        return frame, layout

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        logo = QLabel("\u266B")
        logo.setStyleSheet("color:#5fa8ff;font-size:22px;font-weight:700;")
        title = QLabel(__app_name__)
        title.setStyleSheet("color:#c8d2e0;font-size:16px;font-weight:600;letter-spacing:1px;")
        header.addWidget(logo)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        # Batch queue section
        queue_frame, queue_layout = self._section_frame("Batch Queue")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Filename", "Duration", "Type", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        queue_layout.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        queue_layout.addWidget(self.progress)
        root.addWidget(queue_frame, 1)

        # Toolbar
        toolbar_frame, toolbar_layout = self._section_frame("Setting Console")
        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.btn_add_files = QPushButton("Add Files")
        self.btn_add_folder = QPushButton("Add Folder")
        self.btn_remove = QPushButton("Remove")
        self.btn_clear = QPushButton("Clear all")
        self.btn_info = QPushButton("File Information")
        self.btn_info.setObjectName("accentButton")
        self.btn_output = QPushButton("Output Folder")
        self.btn_export = QPushButton("\u25B6 Start Export")
        self.btn_export.setObjectName("primaryButton")
        self.btn_stop = QPushButton("\u25A0 Stop")
        self.btn_open_output = QPushButton("Open Output")
        self.btn_export_settings = QPushButton("Export Settings")
        for btn in (
            self.btn_add_files,
            self.btn_add_folder,
            self.btn_remove,
            self.btn_clear,
            self.btn_info,
            self.btn_output,
            self.btn_export_settings,
            self.btn_export,
            self.btn_stop,
            self.btn_open_output,
        ):
            tools.addWidget(btn)
        tools.addStretch(1)
        toolbar_layout.addLayout(tools)

        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        self.lbl_output = QLabel(f"Output: {self._output_dir}")
        self.lbl_output.setObjectName("fieldLabel")
        info_row.addWidget(self.lbl_output, 1)
        toolbar_layout.addLayout(info_row)

        root.addWidget(toolbar_frame)

        # Waveform footer
        wave_frame = QFrame()
        wave_frame.setObjectName("sectionFrame")
        wave_layout = QVBoxLayout(wave_frame)
        wave_layout.setContentsMargins(14, 8, 14, 8)
        self.waveform = WaveformView()
        wave_layout.addWidget(self.waveform)
        root.addWidget(wave_frame)

        # Status bar
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_active = QLabel("Status: Active")
        self.status_active.setObjectName("statusActive")
        status.addPermanentWidget(QLabel(f"\u00A9 {self._year()} Panha \u2022 v{__version__}"))
        status.addPermanentWidget(self.status_active)

        # Connections
        self.btn_add_files.clicked.connect(self._on_add_files)
        self.btn_add_folder.clicked.connect(self._on_add_folder)
        self.btn_remove.clicked.connect(self._on_remove_selected)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_info.clicked.connect(self._on_open_info_dialog)
        self.btn_output.clicked.connect(self._on_pick_output)
        self.btn_export_settings.clicked.connect(self._on_open_export_dialog)
        self.btn_export.clicked.connect(self._on_start_export)
        self.btn_stop.clicked.connect(self._on_stop_export)
        self.btn_open_output.clicked.connect(self._on_open_output)

    # -- helpers --------------------------------------------------------

    def _year(self) -> int:
        from datetime import datetime

        return datetime.now().year

    def _update_buttons(self) -> None:
        running = self._worker is not None
        has_rows = bool(self._rows)
        has_selection = bool(self.table.selectionModel() and self.table.selectionModel().hasSelection())
        self.btn_export.setEnabled(has_rows and not running)
        self.btn_stop.setEnabled(running)
        self.btn_remove.setEnabled(has_rows and has_selection and not running)
        self.btn_clear.setEnabled(has_rows and not running)
        self.btn_add_files.setEnabled(not running)
        self.btn_add_folder.setEnabled(not running)
        self.btn_info.setEnabled(not running)
        self.btn_output.setEnabled(not running)
        self.btn_export_settings.setEnabled(not running)

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_idx, row in enumerate(self._rows):
            for col, value in enumerate((row.filename, format_duration(row.duration_seconds), row.file_type, row.status)):
                item = QTableWidgetItem(value)
                if col == 3:
                    if row.status == "Done":
                        item.setForeground(Qt.GlobalColor.green)
                    elif row.status.startswith("Error"):
                        item.setForeground(Qt.GlobalColor.red)
                    elif row.status == "Processing":
                        item.setForeground(Qt.GlobalColor.cyan)
                self.table.setItem(row_idx, col, item)
        self._update_buttons()

    def _update_row_status(self, idx: int, status: str) -> None:
        if 0 <= idx < len(self._rows):
            self._rows[idx].status = status
            item = QTableWidgetItem(status)
            if status == "Done":
                item.setForeground(Qt.GlobalColor.green)
            elif status.startswith("Error"):
                item.setForeground(Qt.GlobalColor.red)
            elif status == "Processing":
                item.setForeground(Qt.GlobalColor.cyan)
            self.table.setItem(idx, 3, item)

    def _add_paths(self, paths: list[str]) -> None:
        existing = {row.path for row in self._rows}
        added = 0
        for raw in paths:
            path = os.path.abspath(raw)
            if path in existing:
                continue
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in SUPPORTED_EXTS:
                continue
            duration = probe_duration_seconds(path)
            self._rows.append(QueueRow(path=path, duration_seconds=duration))
            existing.add(path)
            added += 1
        if added:
            self._refresh_table()

    # -- slots ----------------------------------------------------------

    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add audio files",
            str(Path.home()),
            "Audio (*.mp3 *.wav *.flac *.m4a *.ogg *.aac)",
        )
        if files:
            self._add_paths(files)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add folder", str(Path.home()))
        if not folder:
            return
        candidates: list[str] = []
        for root_dir, _dirs, files in os.walk(folder):
            for name in files:
                if os.path.splitext(name)[1].lower() in SUPPORTED_EXTS:
                    candidates.append(os.path.join(root_dir, name))
        candidates.sort()
        self._add_paths(candidates)

    def _on_remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._rows):
                del self._rows[r]
        self._refresh_table()

    def _on_clear(self) -> None:
        self._rows.clear()
        self._refresh_table()
        self.progress.setValue(0)

    def _on_open_info_dialog(self) -> None:
        dlg = FileInformationDialog(self._info_state, parent=self)
        if dlg.exec() == FileInformationDialog.DialogCode.Accepted:
            self._info_state = dlg.collect_state()

    def _on_open_export_dialog(self) -> None:
        dlg = ExportSettingsDialog(self._export_settings, parent=self)
        if dlg.exec() == ExportSettingsDialog.DialogCode.Accepted:
            self._export_settings = dlg.collect()

    def _on_pick_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose output folder", self._output_dir or str(Path.home())
        )
        if folder:
            self._output_dir = folder
            self.lbl_output.setText(f"Output: {self._output_dir}")

    def _on_open_output(self) -> None:
        out = Path(self._output_dir)
        out.mkdir(parents=True, exist_ok=True)
        # Cross-platform best-effort open
        import subprocess
        import sys

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(out)])
            elif sys.platform.startswith("win"):
                os.startfile(str(out))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(out)])
        except (OSError, subprocess.SubprocessError):
            QMessageBox.information(self, "Output Folder", str(out))

    def _on_start_export(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "Nothing to export", "Add some files first.")
            return
        if not self._info_state.enabled:
            reply = QMessageBox.question(
                self,
                "Info Injection disabled",
                "Info Injection is currently disabled in File Information.\n"
                "Continue without writing metadata?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        sources = [row.path for row in self._rows]
        items = build_items(sources, self._output_dir, self._info_state)
        for idx in range(len(self._rows)):
            self._update_row_status(idx, "Pending")
        self.progress.setValue(0)
        worker, thread = start_worker(items)
        worker.progress.connect(self._on_progress)
        worker.item_done.connect(self._on_item_done)
        worker.item_failed.connect(self._on_item_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._thread = thread
        self.waveform.setActive(True)
        self._update_buttons()

    def _on_stop_export(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _on_progress(self, done: int, total: int) -> None:
        pct = int(done * 100 / max(total, 1))
        self.progress.setValue(pct)

    def _on_item_done(self, idx: int, status: str) -> None:
        self._update_row_status(idx, status)

    def _on_item_failed(self, idx: int, message: str) -> None:
        self._update_row_status(idx, f"Error: {message[:60]}")

    def _on_worker_finished(self) -> None:
        self._worker = None
        self._thread = None
        self.waveform.setActive(False)
        self.progress.setValue(100)
        self._update_buttons()

    # -- context menu --------------------------------------------------

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_select_all = QAction("Select all", self)
        act_select_all.triggered.connect(self.table.selectAll)
        act_add_files = QAction("Add files", self)
        act_add_files.triggered.connect(self._on_add_files)
        act_add_folder = QAction("Add folder", self)
        act_add_folder.triggered.connect(self._on_add_folder)
        act_remove = QAction("Remove selected", self)
        act_remove.triggered.connect(self._on_remove_selected)
        act_clear = QAction("Clear all", self)
        act_clear.triggered.connect(self._on_clear)
        act_start = QAction("\u25B6  START EXPORT", self)
        act_start.triggered.connect(self._on_start_export)
        act_stop = QAction("\u25A0  STOP EXPORT", self)
        act_stop.triggered.connect(self._on_stop_export)
        act_open = QAction("Open output", self)
        act_open.triggered.connect(self._on_open_output)
        menu.addAction(act_select_all)
        menu.addAction(act_add_files)
        menu.addAction(act_add_folder)
        menu.addSeparator()
        menu.addAction(act_remove)
        menu.addAction(act_clear)
        menu.addSeparator()
        menu.addAction(act_start)
        menu.addAction(act_stop)
        menu.addSeparator()
        menu.addAction(act_open)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker:
            self._worker.cancel()
        if self._thread:
            self._thread.quit()
            self._thread.wait(1500)
        super().closeEvent(event)
