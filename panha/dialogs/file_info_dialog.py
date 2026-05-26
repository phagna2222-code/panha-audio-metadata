"""Dialog for editing the metadata that will be injected into audio files.

Mirrors the layout of the reference "File Information" panel: basic info,
studio metadata, tracklist options and a template preset selector.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..mastering import MasteringSettings
from ..metadata import Metadata
from ..templates import TemplateStore

RATINGS = ["None", "1", "2", "3", "4", "5"]
GENRES = [
    "", "Pop", "Rock", "Hip-Hop", "Electronic", "Dance",
    "Jazz", "Classical", "Folk", "Country", "R&B",
    "Soundtrack", "World", "Khmer", "Lo-fi", "Ambient", "Other",
]


@dataclasses.dataclass
class TracklistOptions:
    uppercase: bool = False
    remove_track_number: bool = True
    cover_size: int = 1600


@dataclasses.dataclass
class FileInformationState:
    enabled: bool = True
    metadata: Metadata = dataclasses.field(default_factory=Metadata)
    tracklist: TracklistOptions = dataclasses.field(default_factory=TracklistOptions)
    mastering: MasteringSettings = dataclasses.field(default_factory=MasteringSettings)
    title: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "metadata": dataclasses.asdict(self.metadata),
            "tracklist": dataclasses.asdict(self.tracklist),
            "mastering": dataclasses.asdict(self.mastering),
            "title": self.title,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FileInformationState:
        meta = Metadata(**(data.get("metadata") or {}))
        tracklist = TracklistOptions(**(data.get("tracklist") or {}))
        mastering = MasteringSettings(**(data.get("mastering") or {}))
        return cls(
            enabled=bool(data.get("enabled", True)),
            metadata=meta,
            tracklist=tracklist,
            mastering=mastering,
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
        )


class FileInformationDialog(QDialog):
    """Modal editor for the metadata batch template."""

    def __init__(self, state: FileInformationState | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("File Information")
        self.setModal(True)
        self.setMinimumWidth(640)
        self._templates = TemplateStore()
        self._state = state or FileInformationState()
        self._build_ui()
        self._load_state(self._state)
        self._refresh_template_list()

    # -- ui -------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("File Information")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size:16px;")
        root.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#1c3050;background:#1c3050;max-height:1px;")
        root.addWidget(line)

        self.chk_enable = QCheckBox("Enable Info Injection")
        self.chk_enable.setChecked(True)
        root.addWidget(self.chk_enable)

        # Templates
        templates_box = QGroupBox("Templates")
        tpl_layout = QHBoxLayout(templates_box)
        tpl_layout.setContentsMargins(12, 14, 12, 12)
        tpl_layout.addWidget(QLabel("Preset:"))
        self.cmb_template = QComboBox()
        self.cmb_template.setEditable(False)
        self.cmb_template.currentIndexChanged.connect(self._on_template_selected)
        tpl_layout.addWidget(self.cmb_template, 1)
        self.btn_template_save = QPushButton("Save As")
        self.btn_template_save.clicked.connect(self._on_save_template)
        tpl_layout.addWidget(self.btn_template_save)
        self.btn_template_delete = QPushButton("Delete")
        self.btn_template_delete.clicked.connect(self._on_delete_template)
        tpl_layout.addWidget(self.btn_template_delete)
        root.addWidget(templates_box)

        # Basic info
        basic_box = QGroupBox("Basic Info")
        basic_grid = QGridLayout(basic_box)
        basic_grid.setContentsMargins(12, 14, 12, 12)
        basic_grid.setHorizontalSpacing(12)
        basic_grid.setVerticalSpacing(8)

        self.ed_title = QLineEdit()
        self.ed_artist = QLineEdit()
        self.ed_year = QLineEdit()
        self.ed_album = QLineEdit()
        self.ed_rating = QComboBox()
        self.ed_rating.addItems(RATINGS)
        self.ed_genre = QComboBox()
        self.ed_genre.setEditable(True)
        self.ed_genre.addItems(GENRES)
        self.ed_cover = QLineEdit()
        self.ed_cover.setPlaceholderText("Image file or folder")
        self.btn_cover_browse = QPushButton("...")
        self.btn_cover_browse.setFixedWidth(40)
        self.btn_cover_browse.clicked.connect(self._on_browse_cover_file)
        self.btn_cover_folder = QPushButton("Folder")
        self.btn_cover_folder.clicked.connect(self._on_browse_cover_folder)

        basic_grid.addWidget(QLabel("Title:"), 0, 0)
        basic_grid.addWidget(self.ed_title, 0, 1, 1, 5)

        basic_grid.addWidget(QLabel("Artist:"), 1, 0)
        basic_grid.addWidget(self.ed_artist, 1, 1, 1, 2)
        basic_grid.addWidget(QLabel("Year:"), 1, 3)
        basic_grid.addWidget(self.ed_year, 1, 4, 1, 2)

        basic_grid.addWidget(QLabel("Album:"), 2, 0)
        basic_grid.addWidget(self.ed_album, 2, 1, 1, 2)
        basic_grid.addWidget(QLabel("Rating:"), 2, 3)
        basic_grid.addWidget(self.ed_rating, 2, 4, 1, 2)

        basic_grid.addWidget(QLabel("Genre:"), 3, 0)
        basic_grid.addWidget(self.ed_genre, 3, 1, 1, 2)
        basic_grid.addWidget(QLabel("Cover:"), 3, 3)
        basic_grid.addWidget(self.ed_cover, 3, 4)
        basic_grid.addWidget(self.btn_cover_browse, 3, 5)

        basic_grid.addWidget(QLabel("Description:"), 4, 0, Qt.AlignmentFlag.AlignTop)
        self.ed_description = QPlainTextEdit()
        self.ed_description.setFixedHeight(64)
        basic_grid.addWidget(self.ed_description, 4, 1, 1, 5)
        basic_grid.addWidget(self.btn_cover_folder, 3, 6)

        # Cover preview
        self.cover_preview = QLabel()
        self.cover_preview.setFixedSize(120, 120)
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setStyleSheet(
            "background-color:#0a1426;border:1px solid #1c3050;border-radius:6px;color:#4a5a72;"
        )
        self.cover_preview.setText("(no cover)")
        basic_grid.addWidget(self.cover_preview, 0, 6, 3, 1, Qt.AlignmentFlag.AlignTop)
        self.ed_cover.textChanged.connect(self._refresh_cover_preview)

        root.addWidget(basic_box)

        # Studio metadata
        studio_box = QGroupBox("Studio Metadata")
        studio_form = QFormLayout(studio_box)
        studio_form.setContentsMargins(12, 14, 12, 12)
        studio_form.setHorizontalSpacing(12)
        studio_form.setVerticalSpacing(8)
        self.ed_engineer = QLineEdit()
        self.ed_copyright = QLineEdit()
        self.ed_software = QLineEdit()
        self.ed_source = QLineEdit()
        self.ed_comment = QLineEdit()

        row1 = QWidget()
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(12)
        row1_layout.addWidget(QLabel("Engineer:"))
        row1_layout.addWidget(self.ed_engineer, 1)
        row1_layout.addWidget(QLabel("Copyright:"))
        row1_layout.addWidget(self.ed_copyright, 1)
        studio_form.addRow(row1)

        row2 = QWidget()
        row2_layout = QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(12)
        row2_layout.addWidget(QLabel("Software:"))
        row2_layout.addWidget(self.ed_software, 1)
        row2_layout.addWidget(QLabel("Source:"))
        row2_layout.addWidget(self.ed_source, 1)
        studio_form.addRow(row2)

        studio_form.addRow("Comment:", self.ed_comment)
        root.addWidget(studio_box)

        # Tracklist options
        tracklist_box = QGroupBox("Tracklist")
        tl_layout = QHBoxLayout(tracklist_box)
        tl_layout.setContentsMargins(12, 14, 12, 12)
        tl_layout.setSpacing(18)
        self.chk_uppercase = QCheckBox("UPPERCASE")
        self.chk_remove_tracknum = QCheckBox("Remove Track Number")
        self.chk_remove_tracknum.setChecked(True)
        tl_layout.addWidget(self.chk_uppercase)
        tl_layout.addWidget(self.chk_remove_tracknum)
        tl_layout.addWidget(QLabel("Cover Size (px):"))
        self.spn_cover_size = QSpinBox()
        self.spn_cover_size.setRange(64, 8192)
        self.spn_cover_size.setValue(1600)
        self.spn_cover_size.setSingleStep(64)
        tl_layout.addWidget(self.spn_cover_size)
        tl_layout.addStretch(1)
        root.addWidget(tracklist_box)

        # Buttons
        buttons = QDialogButtonBox()
        self.btn_cancel = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_apply = buttons.addButton("Apply setting", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_apply.setObjectName("primaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # -- state ----------------------------------------------------------

    def _load_state(self, state: FileInformationState) -> None:
        meta = state.metadata
        self.chk_enable.setChecked(state.enabled)
        self.ed_title.setText(state.title or meta.title)
        self.ed_description.setPlainText(state.description or meta.description)
        self.ed_artist.setText(meta.artist)
        self.ed_album.setText(meta.album)
        self.ed_year.setText(meta.year)
        rating_index = self.ed_rating.findText(meta.rating or "None")
        self.ed_rating.setCurrentIndex(rating_index if rating_index >= 0 else 0)
        if meta.genre:
            idx = self.ed_genre.findText(meta.genre)
            if idx >= 0:
                self.ed_genre.setCurrentIndex(idx)
            else:
                self.ed_genre.setEditText(meta.genre)
        else:
            self.ed_genre.setCurrentIndex(0)
        self.ed_cover.setText(meta.cover_path)
        self.ed_engineer.setText(meta.engineer)
        self.ed_copyright.setText(meta.copyright)
        self.ed_software.setText(meta.software)
        self.ed_source.setText(meta.source)
        self.ed_comment.setText(meta.comment)
        self.chk_uppercase.setChecked(state.tracklist.uppercase)
        self.chk_remove_tracknum.setChecked(state.tracklist.remove_track_number)
        self.spn_cover_size.setValue(state.tracklist.cover_size)
        self._refresh_cover_preview()

    def collect_state(self) -> FileInformationState:
        rating = self.ed_rating.currentText()
        if rating == "None":
            rating = ""
        meta = Metadata(
            title=self.ed_title.text().strip(),
            artist=self.ed_artist.text().strip(),
            album=self.ed_album.text().strip(),
            year=self.ed_year.text().strip(),
            genre=self.ed_genre.currentText().strip(),
            rating=rating,
            cover_path=self.ed_cover.text().strip(),
            engineer=self.ed_engineer.text().strip(),
            copyright=self.ed_copyright.text().strip(),
            software=self.ed_software.text().strip(),
            source=self.ed_source.text().strip(),
            comment=self.ed_comment.text().strip(),
            description=self.ed_description.toPlainText().strip(),
        )
        tracklist = TracklistOptions(
            uppercase=self.chk_uppercase.isChecked(),
            remove_track_number=self.chk_remove_tracknum.isChecked(),
            cover_size=int(self.spn_cover_size.value()),
        )
        return FileInformationState(
            enabled=self.chk_enable.isChecked(),
            metadata=meta,
            tracklist=tracklist,
            title=self.ed_title.text().strip(),
            description=self.ed_description.toPlainText().strip(),
        )

    # -- cover ----------------------------------------------------------

    def _on_browse_cover_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select cover image", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self.ed_cover.setText(path)

    def _on_browse_cover_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select cover folder")
        if path:
            self.ed_cover.setText(path)

    def _refresh_cover_preview(self) -> None:
        text = self.ed_cover.text().strip()
        if not text:
            self.cover_preview.clear()
            self.cover_preview.setText("(no cover)")
            return
        path = Path(text)
        if path.is_dir():
            # pick first image in folder
            for child in sorted(path.iterdir()):
                if child.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    path = child
                    break
            else:
                self.cover_preview.setText("(no image)")
                return
        pix = QPixmap(str(path))
        if pix.isNull():
            self.cover_preview.setText("(invalid)")
            return
        self.cover_preview.setPixmap(
            pix.scaled(
                self.cover_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # -- templates ------------------------------------------------------

    def _load_templates(self) -> dict[str, dict]:
        return self._templates.load()

    def _save_templates(self, templates: dict[str, dict]) -> None:
        try:
            self._templates.save(templates)
        except OSError as exc:
            QMessageBox.warning(self, "Templates", f"Failed to save templates: {exc}")

    def _refresh_template_list(self) -> None:
        templates = self._load_templates()
        self.cmb_template.blockSignals(True)
        self.cmb_template.clear()
        if not templates:
            self.cmb_template.addItem("(no templates)")
            self.btn_template_delete.setEnabled(False)
        else:
            self.cmb_template.addItem("(no templates)")
            for name in sorted(templates.keys()):
                self.cmb_template.addItem(name)
            self.btn_template_delete.setEnabled(True)
        self.cmb_template.blockSignals(False)

    def _on_template_selected(self, index: int) -> None:
        if index <= 0:
            return
        name = self.cmb_template.currentText()
        templates = self._load_templates()
        if name in templates:
            self._load_state(FileInformationState.from_dict(templates[name]))

    def _on_save_template(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Template", "Template name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        templates = self._load_templates()
        templates[name] = self.collect_state().to_dict()
        self._save_templates(templates)
        self._refresh_template_list()
        idx = self.cmb_template.findText(name)
        if idx >= 0:
            self.cmb_template.setCurrentIndex(idx)

    def _on_delete_template(self) -> None:
        name = self.cmb_template.currentText()
        if name in {"", "(no templates)"}:
            return
        templates = self._load_templates()
        if name in templates:
            del templates[name]
            self._save_templates(templates)
            self._refresh_template_list()
