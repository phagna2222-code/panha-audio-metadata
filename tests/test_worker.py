"""Tests for the batch worker."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from panha.metadata import FfmpegNotFoundError, Metadata  # noqa: E402
from panha.widgets.worker import BatchItem, BatchWorker  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _drain_signals(worker: BatchWorker):
    """Collect emissions from a worker run synchronously on the test thread."""
    done: list[tuple[int, str]] = []
    failed: list[tuple[int, str]] = []
    progress: list[tuple[int, int]] = []
    finished = [False]
    worker.item_done.connect(lambda i, s: done.append((i, s)))
    worker.item_failed.connect(lambda i, m: failed.append((i, m)))
    worker.progress.connect(lambda i, t: progress.append((i, t)))
    worker.finished.connect(lambda: finished.__setitem__(0, True))
    worker.run()
    return done, failed, progress, finished[0]


def test_worker_reports_ffmpeg_not_found_instead_of_crashing(
    qapp, monkeypatch, tmp_path: Path
):
    """Regression: a missing ffmpeg binary raises FfmpegNotFoundError,
    which subclasses RuntimeError. The worker thread must surface that
    as an item failure rather than dying silently.
    """
    src = tmp_path / "in.mp3"
    src.write_bytes(b"not really an mp3")
    dst = tmp_path / "out.mp3"

    def boom(*_args, **_kwargs):
        raise FfmpegNotFoundError("ffmpeg not installed")

    monkeypatch.setattr("panha.metadata.ffmpeg_writer._resolve_ffmpeg", boom)

    item = BatchItem(source=str(src), target=str(dst), metadata=Metadata(title="x"))
    worker = BatchWorker([item])
    done, failed, progress, finished = _drain_signals(worker)

    assert finished is True
    assert done == []
    assert len(failed) == 1
    assert failed[0][0] == 0
    assert "ffmpeg" in failed[0][1].lower()
    assert progress == [(1, 1)]


def test_worker_cancels_remaining_items(qapp, tmp_path: Path):
    src = tmp_path / "in.mp3"
    src.write_bytes(b"not really an mp3")
    items = [
        BatchItem(source=str(src), target=str(tmp_path / f"o{i}.mp3"),
                  metadata=Metadata())
        for i in range(3)
    ]
    worker = BatchWorker(items)
    worker.cancel()
    done, failed, _progress, finished = _drain_signals(worker)

    assert finished is True
    assert failed == []
    assert [s for _, s in done] == ["Cancelled", "Cancelled", "Cancelled"]
