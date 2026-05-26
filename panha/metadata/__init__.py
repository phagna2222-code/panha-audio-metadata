"""Audio metadata I/O backed by ffmpeg."""

from .ffmpeg_writer import (
    FfmpegNotFoundError,
    Metadata,
    MetadataWriteError,
    format_duration,
    probe_duration_seconds,
    read_metadata,
    write_metadata,
)

__all__ = [
    "FfmpegNotFoundError",
    "Metadata",
    "MetadataWriteError",
    "format_duration",
    "probe_duration_seconds",
    "read_metadata",
    "write_metadata",
]
