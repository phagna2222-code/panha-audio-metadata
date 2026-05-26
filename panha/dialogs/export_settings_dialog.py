"""Export settings dialog (format, sample rate, bit depth, threads)."""

from __future__ import annotations

import dataclasses

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

FORMATS = ["MP3", "WAV", "FLAC", "M4A", "OGG"]
SAMPLE_RATES = ["22050 Hz", "44100 Hz", "48000 Hz", "96000 Hz"]
BIT_DEPTHS = ["16-bit", "24-bit", "32-bit"]
LUFS_TARGETS = ["Off", "-23 LUFS", "-16 LUFS", "-14 LUFS", "-9 LUFS"]


@dataclasses.dataclass
class ExportSettings:
    format: str = "MP3"
    sample_rate: str = "44100 Hz"
    bit_depth: str = "24-bit"
    max_threads: int = 4
    suno_bypass: bool = False
    vocal_clarity: bool = False
    soft_clip: bool = False
    lufs_target: str = "Off"
    output_dir: str = ""


class ExportSettingsDialog(QDialog):
    """Modal export configuration."""

    def __init__(
        self, settings: ExportSettings | None = None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Export Settings")
        self.setModal(True)
        self.setFixedWidth(360)
        self._settings = settings or ExportSettings()
        self._build_ui()
        self._load(self._settings)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Export Settings")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size:15px;")
        root.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#1c3050;background:#1c3050;max-height:1px;")
        root.addWidget(line)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(FORMATS)
        self.cmb_sample = QComboBox()
        self.cmb_sample.addItems(SAMPLE_RATES)
        self.cmb_bitdepth = QComboBox()
        self.cmb_bitdepth.addItems(BIT_DEPTHS)
        self.spn_threads = QSpinBox()
        self.spn_threads.setRange(1, 32)
        self.spn_threads.setValue(4)
        form.addRow("Format", self.cmb_format)
        form.addRow("Sample Rate", self.cmb_sample)
        form.addRow("Bit Depth", self.cmb_bitdepth)
        form.addRow("Max Threads", self.spn_threads)
        root.addLayout(form)

        proc_box = QGroupBox("Processing Options")
        proc_layout = QVBoxLayout(proc_box)
        proc_layout.setContentsMargins(12, 14, 12, 10)
        self.chk_suno = QCheckBox("SUNO Bypass")
        self.chk_vocal = QCheckBox("Vocal Clarity Boost")
        self.chk_softclip = QCheckBox("Soft Clip Ceiling")
        for w in (self.chk_suno, self.chk_vocal, self.chk_softclip):
            proc_layout.addWidget(w)
        root.addWidget(proc_box)

        master_box = QGroupBox("Mastering Target")
        master_layout = QFormLayout(master_box)
        master_layout.setContentsMargins(12, 14, 12, 10)
        self.cmb_lufs = QComboBox()
        self.cmb_lufs.addItems(LUFS_TARGETS)
        master_layout.addRow("LUFS Target", self.cmb_lufs)
        root.addWidget(master_box)

        self.btn_start = QPushButton("\u25B6  Start Export")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.clicked.connect(self.accept)
        root.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        root.addWidget(self.btn_cancel)

    def _load(self, s: ExportSettings) -> None:
        for combo, value in (
            (self.cmb_format, s.format),
            (self.cmb_sample, s.sample_rate),
            (self.cmb_bitdepth, s.bit_depth),
            (self.cmb_lufs, s.lufs_target),
        ):
            idx = combo.findText(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.spn_threads.setValue(s.max_threads)
        self.chk_suno.setChecked(s.suno_bypass)
        self.chk_vocal.setChecked(s.vocal_clarity)
        self.chk_softclip.setChecked(s.soft_clip)

    def collect(self) -> ExportSettings:
        return ExportSettings(
            format=self.cmb_format.currentText(),
            sample_rate=self.cmb_sample.currentText(),
            bit_depth=self.cmb_bitdepth.currentText(),
            max_threads=int(self.spn_threads.value()),
            suno_bypass=self.chk_suno.isChecked(),
            vocal_clarity=self.chk_vocal.isChecked(),
            soft_clip=self.chk_softclip.isChecked(),
            lufs_target=self.cmb_lufs.currentText(),
            output_dir=self._settings.output_dir,
        )
