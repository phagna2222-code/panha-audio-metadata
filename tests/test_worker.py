"""Tests for the batch worker."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import QThreadPool  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from panha.metadata import FfmpegNotFoundError, Metadata  # noqa: E402
from panha.widgets.worker import BatchItem, BatchWorker, schedule_probe  # noqa: E402


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
    done, failed, progress, finished = _drain_signals(worker)

    assert finished is True
    assert failed == []
    assert [s for _, s in done] == ["Cancelled", "Cancelled", "Cancelled"]
    # Progress must still tick to total for cancelled items so the bar
    # doesn't get stuck partway.
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_schedule_probe_runs_off_thread_and_emits_result(qapp, tmp_path: Path):
    """schedule_probe must defer the probe to a worker and report back
    via signal so the UI thread doesn't block on ffprobe."""
    pool = QThreadPool()
    pool.setMaxThreadCount(2)

    received: list[tuple[str, float]] = []

    def fake_probe(path: str) -> float:
        return 1.5 if path.endswith("a.mp3") else 2.25

    a = str(tmp_path / "a.mp3")
    b = str(tmp_path / "b.mp3")
    schedule_probe(a, lambda p, d: received.append((p, d)), pool=pool, probe_fn=fake_probe)
    schedule_probe(b, lambda p, d: received.append((p, d)), pool=pool, probe_fn=fake_probe)

    # Wait for both tasks to finish, draining the Qt event queue so
    # queued signal connections deliver.
    pool.waitForDone(5000)
    qapp.processEvents()

    assert sorted(received) == [(a, 1.5), (b, 2.25)]


def test_schedule_probe_reports_zero_when_probe_raises(qapp, tmp_path: Path):
    """A probe failure must surface as duration=0.0, never propagate."""
    pool = QThreadPool()
    pool.setMaxThreadCount(1)

    received: list[tuple[str, float]] = []

    def boom(_path: str) -> float:
        raise RuntimeError("ffprobe explosion")

    path = str(tmp_path / "x.mp3")
    schedule_probe(path, lambda p, d: received.append((p, d)), pool=pool, probe_fn=boom)
    pool.waitForDone(5000)
    qapp.processEvents()

    assert received == [(path, 0.0)]


def test_worker_emits_cancelled_when_write_metadata_raises_cancelled(
    qapp, monkeypatch, tmp_path: Path
):
    """When write_metadata raises MetadataWriteCancelledError mid-batch, the
    worker must surface it as a 'Cancelled' done event (not 'Error: ...').
    """
    from panha.metadata import MetadataWriteCancelledError

    src = tmp_path / "in.mp3"
    src.write_bytes(b"not really an mp3")

    def boom(*_args, **kwargs):
        # Sanity check: BatchWorker must pass cancel_check through.
        assert "cancel_check" in kwargs
        raise MetadataWriteCancelledError("cancelled mid-export")

    monkeypatch.setattr("panha.widgets.worker.write_metadata", boom)

    item = BatchItem(
        source=str(src), target=str(tmp_path / "out.mp3"),
        metadata=Metadata(title="x"),
    )
    worker = BatchWorker([item])
    done, failed, progress, finished = _drain_signals(worker)

    assert finished is True
    assert failed == []
    assert done == [(0, "Cancelled")]
    assert progress == [(1, 1)]
