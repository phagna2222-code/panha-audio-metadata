"""Background worker that writes metadata to a batch of files."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThread, QThreadPool, pyqtSignal

from ..dialogs.file_info_dialog import FileInformationState
from ..mastering import MasteringSettings
from ..metadata import (
    FfmpegNotFoundError,
    Metadata,
    MetadataWriteError,
    probe_duration_seconds,
    write_metadata,
)


@dataclasses.dataclass
class BatchItem:
    source: str
    target: str
    metadata: Metadata
    mastering: MasteringSettings = dataclasses.field(default_factory=MasteringSettings)


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
            else:
                try:
                    Path(item.target).parent.mkdir(parents=True, exist_ok=True)
                    write_metadata(
                        item.source,
                        item.target,
                        item.metadata,
                        mastering=item.mastering,
                    )
                    self.item_done.emit(idx, "Done")
                except (
                    FfmpegNotFoundError,
                    MetadataWriteError,
                    OSError,
                    FileNotFoundError,
                ) as exc:
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
    mastering = dataclasses.replace(state.mastering)
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
        items.append(BatchItem(
            source=str(src_path),
            target=str(target),
            metadata=meta,
            mastering=mastering,
        ))
    return items


class _ProbeSignals(QObject):
    """Signal carrier for :class:`ProbeTask` (QRunnable can't emit directly)."""

    finished = pyqtSignal(str, float)  # path, duration_seconds


class ProbeTask(QRunnable):
    """Probe a single file's duration on the global thread pool.

    Use :attr:`signals.finished` to receive the result back on the
    Qt thread that connected the slot.
    """

    def __init__(
        self,
        path: str,
        *,
        probe_fn: Callable[[str], float] = probe_duration_seconds,
    ) -> None:
        super().__init__()
        self._path = path
        self._probe_fn = probe_fn
        self.signals = _ProbeSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover - exercised via signals
        try:
            duration = float(self._probe_fn(self._path))
        except Exception:
            duration = 0.0
        self.signals.finished.emit(self._path, duration)


def schedule_probe(
    path: str,
    on_finished: Callable[[str, float], None],
    *,
    pool: QThreadPool | None = None,
    probe_fn: Callable[[str], float] = probe_duration_seconds,
) -> ProbeTask:
    """Submit ``path`` to a background pool; ``on_finished`` runs on the caller's thread."""
    task = ProbeTask(path, probe_fn=probe_fn)
    task.signals.finished.connect(on_finished)
    (pool or QThreadPool.globalInstance()).start(task)
    return task


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
