"""Tests for the ffmpeg metadata writer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from panha.metadata import (
    Metadata,
    format_duration,
    probe_duration_seconds,
    read_metadata,
    write_metadata,
)


def test_metadata_dataclass_defaults():
    m = Metadata()
    assert m.title == ""
    assert m.to_ffmpeg_args() == []


def test_metadata_to_ffmpeg_args_skips_empty_fields():
    m = Metadata(title="Hello", artist="World", year="", comment="ok")
    args = m.to_ffmpeg_args()
    assert "-metadata" in args
    assert "title=Hello" in args
    assert "artist=World" in args
    assert "comment=ok" in args
    assert "date=" not in args
    assert all("year" not in a for a in args)


def test_format_duration():
    assert format_duration(0) == "--:--"
    assert format_duration(-1) == "--:--"
    assert format_duration(65) == "1:05"
    assert format_duration(125) == "2:05"
    assert format_duration(3725) == "1:02:05"


def test_probe_duration_seconds(sample_mp3: Path):
    duration = probe_duration_seconds(sample_mp3)
    assert 0.5 <= duration <= 2.5


def test_probe_duration_missing_file(tmp_path: Path):
    assert probe_duration_seconds(tmp_path / "nope.mp3") == 0.0


def test_write_metadata_basic_fields(sample_mp3: Path, tmp_path: Path):
    out = tmp_path / "tagged.mp3"
    meta = Metadata(
        title="My Song", artist="Panha", album="Echoes",
        year="2026", genre="Lo-fi", comment="hello world",
    )
    result = write_metadata(sample_mp3, out, meta)
    assert Path(result).exists()
    tags = read_metadata(out)
    assert tags.get("title") == "My Song"
    assert tags.get("artist") == "Panha"
    assert tags.get("album") == "Echoes"
    assert "2026" in tags.get("date", "")
    assert tags.get("genre") == "Lo-fi"
    assert tags.get("comment") == "hello world"


def test_write_metadata_overwrites_existing(sample_mp3: Path, tmp_path: Path):
    out = tmp_path / "tagged.mp3"
    write_metadata(sample_mp3, out, Metadata(title="first"))
    write_metadata(sample_mp3, out, Metadata(title="second"))
    tags = read_metadata(out)
    assert tags.get("title") == "second"


def test_write_metadata_in_place(sample_mp3: Path):
    write_metadata(sample_mp3, sample_mp3, Metadata(title="in-place"))
    tags = read_metadata(sample_mp3)
    assert tags.get("title") == "in-place"


def test_write_metadata_embeds_cover(
    sample_mp3: Path, sample_cover: Path, tmp_path: Path
):
    import json

    out = tmp_path / "with-cover.mp3"
    meta = Metadata(title="Cover Test", cover_path=str(sample_cover))
    write_metadata(sample_mp3, out, meta)

    # ffprobe should report a video stream with attached_pic disposition.
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_streams",
            "-of", "json",
            str(out),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(proc.stdout)
    video_streams = [s for s in data["streams"] if s.get("codec_type") == "video"]
    assert video_streams, "expected a video stream for cover art"
    assert any(
        s.get("disposition", {}).get("attached_pic") == 1 for s in video_streams
    ), "expected attached_pic disposition on cover stream"


def test_write_metadata_missing_source(tmp_path: Path, ffmpeg_required):
    with pytest.raises(FileNotFoundError):
        write_metadata(tmp_path / "does-not-exist.mp3", tmp_path / "out.mp3", Metadata())
