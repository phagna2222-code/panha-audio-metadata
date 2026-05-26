"""Background worker that writes metadata to a batch of files."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..dialogs.file_info_dialog import FileInformationState
from ..metadata import Metadata, MetadataWriteError, write_metadata


@dataclasses.dataclass
class BatchItem:
    source: str
    target: str
    metadata: Metadata


class BatchWorker(QObject):
    progress = pyqtSignal(int, int)  # index, total
    item_done = pyqtSignal(int, str)  # index, status text
    item_failed = pyqtSignal(int, str)  # index, error message
    finished = pyqtSignal()

    def __init__(self, items: list[BatchItem], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items = items
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        total = len(self._items)
        for idx, item in enumerate(self._items):
            if self._cancel:
                self.item_done.emit(idx, "Cancelled")
                continue
            try:
                Path(item.target).parent.mkdir(parents=True, exist_ok=True)
                write_metadata(item.source, item.target, item.metadata)
                self.item_done.emit(idx, "Done")
            except (MetadataWriteError, OSError, FileNotFoundError) as exc:
                self.item_failed.emit(idx, str(exc))
            self.progress.emit(idx + 1, total)
        self.finished.emit()


def build_items(
    sources: list[str], output_dir: str, state: FileInformationState
) -> list[BatchItem]:
    """Combine a source list + UI state into a list of BatchItem."""
    items: list[BatchItem] = []
    out_root = Path(output_dir).expanduser().resolve()
    base = dataclasses.replace(state.metadata)
    for src in sources:
        src_path = Path(src)
        stem = src_path.stem
        if state.tracklist.remove_track_number:
            cleaned = stem.lstrip("0123456789. _-")
            if cleaned:
                stem = cleaned
        if state.tracklist.uppercase:
            stem = stem.upper()
        target_name = f"{stem}{src_path.suffix or '.mp3'}"
        target = out_root / target_name
        meta = dataclasses.replace(base)
        if not meta.title:
            meta.title = stem
        items.append(BatchItem(source=str(src_path), target=str(target), metadata=meta))
    return items


def start_worker(items: list[BatchItem]) -> tuple[BatchWorker, QThread]:
    """Create + start a worker thread; caller is responsible for cleanup."""
    thread = QThread()
    worker = BatchWorker(items)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return worker, thread
