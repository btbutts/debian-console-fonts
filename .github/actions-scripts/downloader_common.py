"""HTTP, hashing and progress helpers shared by the dependency downloader's modes.

Adapted from OpenWRT-BuildEnv's ``repoScripts/dependencyDownloader.py`` (MIT).
"""

from __future__ import annotations

import hashlib
import io
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote

import requests

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

MEMORY_LIMIT_BYTES = 250 * 1024 * 1024  # 250 MiB
CHUNK_SIZE = 8192
HTTP_TIMEOUT_SECONDS = 120
GITHUB_OUTPUT_CHANGED = "changed"
REDRAW_INTERVAL_SECONDS = 0.05  # ~20 Hz

# Characters that terminate the filename scan. Includes path/query
# delimiters plus characters illegal in Windows, macOS, or Linux names.
_INVALID_FILENAME_CHARS = set('<>:"/\\|?*=' + "".join(chr(i) for i in range(32)))

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.4196.66 Safari/537.36 Edg/152.0.4196.66"
)

_REQUEST_HEADERS = {
    "User-Agent": _USER_AGENT,
    # Identity so Content-Length matches the bytes we hash/write. requests
    # would otherwise advertise gzip and decompress, making the header lie.
    "Accept-Encoding": "identity",
}

_MIB = 1024 * 1024
_KIB = 1024


def log(message: str) -> None:
    """Print a message to stdout."""
    print(message, flush=True)


def extract_filename(url: str) -> str:
    """Return the filename at the end of *url*.

    Characters are collected from the right until the first '/', '=', or
    any character that is not legal in a Windows/macOS/Linux filename.
    Percent-encoded sequences are decoded afterwards.
    """
    collected: list[str] = []
    for char in reversed(url.rstrip()):
        if char in _INVALID_FILENAME_CHARS:
            break
        collected.append(char)

    filename = unquote("".join(reversed(collected))).rstrip(" .")
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        message = f"could not extract a valid filename from URL: {url!r}"
        raise ValueError(message)
    return filename


def format_bytes(num_bytes: int) -> str:
    """Return *num_bytes* as a human-readable size string."""
    if num_bytes < _KIB:
        return f"{num_bytes} B"
    for unit, size in (("GiB", _KIB**3), ("MiB", _MIB), ("KiB", _KIB)):
        if num_bytes >= size:
            return f"{num_bytes / size:.2f} {unit}"
    return f"{num_bytes} B"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest for a file at *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_buffer(buffer: io.BytesIO) -> str:
    """Return the SHA-256 hex digest for the current contents of *buffer*."""
    digest = hashlib.sha256()
    buffer.seek(0)
    while chunk := buffer.read(CHUNK_SIZE):
        digest.update(chunk)
    buffer.seek(0)
    return digest.hexdigest()


def parse_content_length(headers) -> int | None:
    """Return the parsed Content-Length value, or None if unavailable."""
    raw = headers.get("Content-Length")
    if raw is None or raw == "":
        return None
    try:
        length = int(raw)
    except (TypeError, ValueError):
        return None
    return length if length >= 0 else None


def write_github_outputs(values: dict[str, str]) -> None:
    """Append step outputs when running under GitHub Actions.

    No-op locally: ``GITHUB_OUTPUT`` is only set inside a workflow step.
    Values are strings; booleans are the lowercase ``true`` / ``false`` that
    Actions ``if:`` expressions compare against.
    """
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
            log(f"GitHub output      : {key}={value}")


class ProgressMeter:
    """Redraw a two-line stderr block with download / hash progress.

    Uses ANSI cursor-up so the meter occupies a fixed terminal block
    instead of scrolling (wget/curl style). In streaming SHA-256 mode
    the total chunk count is ceil(Content-Length / CHUNK_SIZE).
    """

    _LABEL = "Downloading        :"  # 19 chars; chunk line is indented to match

    def __init__(self, total_bytes: int | None, chunk_size: int, show_chunks: bool) -> None:
        """Start a meter for *total_bytes* (None if unknown) read in *chunk_size* pieces."""
        self.total_bytes = total_bytes
        self.chunk_size = chunk_size
        self.show_chunks = show_chunks
        self.bytes_done = 0
        self.chunks_done = 0
        self._last_draw = 0.0
        self._lines_drawn = 0

    @property
    def total_chunks(self) -> int | None:
        """Number of chunks the whole body will take, or None if the size is unknown."""
        if self.total_bytes is None:
            return None
        return (self.total_bytes + self.chunk_size - 1) // self.chunk_size

    def update(self, nbytes: int) -> None:
        """Account for one received chunk and redraw at ~20 Hz."""
        self.bytes_done += nbytes
        self.chunks_done += 1
        now = time.monotonic()
        if now - self._last_draw < REDRAW_INTERVAL_SECONDS:
            return
        self._draw()
        self._last_draw = now

    def close(self) -> None:
        """Force a final draw, leaving the cursor on the line below the meter."""
        self._draw()

    def _render_lines(self) -> list[str]:
        """Return the text lines of the current meter state."""
        downloaded = self.bytes_done / _MIB
        indent = " " * len(self._LABEL)
        if self.total_bytes is not None:
            total = self.total_bytes / _MIB
            pct = 100.0 * self.bytes_done / self.total_bytes if self.total_bytes else 100.0
            lines = [f"{self._LABEL}{downloaded:7.2f}  /  {total:7.2f} MiB ({pct:.1f}%)"]
        else:
            lines = [f"{self._LABEL}{downloaded:7.2f} MiB"]

        if not self.show_chunks:
            return lines

        if self.total_chunks is not None:
            lines.append(
                f"{indent}{self.chunks_done:7d}  /  {self.total_chunks:7d} total chunks hashed"
            )
        else:
            lines.append(f"{indent}{self.chunks_done:7d} chunks hashed")
        return lines

    def _draw(self) -> None:
        """Redraw the meter block in place."""
        lines = self._render_lines()
        if self._lines_drawn:
            sys.stderr.write(f"\033[{self._lines_drawn}A")
        for line in lines:
            sys.stderr.write("\r\033[2K" + line + "\n")
        sys.stderr.flush()
        self._lines_drawn = len(lines)


def iter_chunks(
    response: requests.Response, chunk_size: int = CHUNK_SIZE
) -> Iterator[bytes]:
    """Yield non-empty content chunks from a streamed HTTP response."""
    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:  # drop keep-alive padding
            yield chunk


def consume_chunks(
    response: requests.Response,
    total_bytes: int | None,
    show_chunks: bool,
    on_chunk: Callable[[bytes], object],
) -> None:
    """Feed each response body chunk to *on_chunk* while updating progress."""
    meter = ProgressMeter(total_bytes, CHUNK_SIZE, show_chunks)
    try:
        for chunk in iter_chunks(response):
            on_chunk(chunk)
            meter.update(len(chunk))
    finally:
        meter.close()


def new_session() -> requests.Session:
    """Create a preconfigured session for dependency downloads."""
    session = requests.Session()
    session.headers.update(_REQUEST_HEADERS)
    return session


def get_response(session: requests.Session, url: str) -> requests.Response:
    """Fetch a URL as a streamed response and fail fast on HTTP errors."""
    response = session.get(url, stream=True, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response


def write_chunks(
    response: requests.Response,
    dest: Path,
    total_bytes: int | None = None,
) -> None:
    """Stream *response* to *dest* via a sibling .part file, then replace."""
    part_path = dest.with_name(dest.name + ".part")
    try:
        with part_path.open("wb") as handle:
            consume_chunks(response, total_bytes, False, handle.write)
        part_path.replace(dest)
    except Exception:
        part_path.unlink(missing_ok=True)
        raise


def write_buffer(buffer: io.BytesIO, dest: Path) -> None:
    """Write buffer contents to *dest* via a sibling .part file, then replace."""
    part_path = dest.with_name(dest.name + ".part")
    try:
        buffer.seek(0)
        with part_path.open("wb") as handle:
            handle.write(buffer.getbuffer())
        part_path.replace(dest)
    except Exception:
        part_path.unlink(missing_ok=True)
        raise


def read_into_buffer(
    response: requests.Response,
    total_bytes: int | None = None,
) -> io.BytesIO:
    """Download a response body into an in-memory buffer with progress."""
    buffer = io.BytesIO()
    consume_chunks(response, total_bytes, False, buffer.write)
    buffer.seek(0)
    return buffer


def stream_hash(
    response: requests.Response,
    total_bytes: int | None = None,
) -> str:
    """Return the SHA-256 hash of a streamed response body."""
    digest = hashlib.sha256()
    consume_chunks(response, total_bytes, True, digest.update)
    return digest.hexdigest()
