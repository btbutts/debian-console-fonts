#!/usr/bin/env python3
"""Download remote files, either one URL at a time or a whole manifest.

Single-file mode (as in OpenWRT-BuildEnv's repoScripts/dependencyDownloader.py)::

    python3 dependencyDownloader.py <url> <output-dir>

Relative output paths are resolved from this script's directory. The stored
filename is taken from the URL (right-to-left until '/', '=', or an invalid
filename character). An existing file is overwritten only when its SHA-256
differs from the freshly downloaded copy.

Manifest mode::

    python3 .github/actions-scripts/dependencyDownloader.py --sources sources.json

``sources.json`` lists archives to fetch and unpack into fixed directories; its
keys are documented in ``sources_manifest.py``. Every entry is downloaded each
run and compared with ``sources/sources.lock.json``; a directory is rewritten
only when the archive, the URL, the version or the unpack options changed.

When running in GitHub Actions, the step output ``changed`` is written to
``$GITHUB_OUTPUT`` as ``true`` if anything was created or replaced and
``false`` otherwise. Manifest mode also writes ``changed_sources`` and
``failed_sources`` (comma-separated names).
"""

from __future__ import annotations

import argparse
import io
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from downloader_common import (
    GITHUB_OUTPUT_CHANGED,
    MEMORY_LIMIT_BYTES,
    extract_filename,
    format_bytes,
    get_response,
    log,
    new_session,
    parse_content_length,
    read_into_buffer,
    sha256_buffer,
    sha256_file,
    stream_hash,
    write_buffer,
    write_chunks,
    write_github_outputs,
)
from sources_sync import DEFAULT_LOCK, DEFAULT_ROOT, run_sources

if TYPE_CHECKING:
    from collections.abc import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent


class DownloadError(Exception):
    """A single-file download could not be completed."""


def resolve_output_dir(output_arg: str) -> Path:
    """Resolve *output_arg* relative to the script directory, then to absolute."""
    return (SCRIPT_DIR / output_arg).resolve()


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    """Declare the command-line arguments on *parser*."""
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="Remote URL. The filename is taken from the end of this URL.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output directory, relative to this script's directory.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_flag",
        default=None,
        metavar="DIR",
        help="Output directory (alternative to the positional argument).",
    )
    parser.add_argument(
        "--sources",
        metavar="FILE",
        default=None,
        help="JSON manifest of archives to download and unpack "
        "(path relative to --root unless absolute).",
    )
    parser.add_argument(
        "--root",
        metavar="DIR",
        default=None,
        help=f"Repository root that manifest paths are relative to (default: {DEFAULT_ROOT}).",
    )
    parser.add_argument(
        "--lock",
        metavar="FILE",
        default=DEFAULT_LOCK,
        help=f"Lock file, relative to --root (default: {DEFAULT_LOCK}).",
    )
    parser.add_argument(
        "--only",
        metavar="NAME",
        action="append",
        default=[],
        help="Only process this manifest entry (repeatable).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract every selected entry even if the lock matches.",
    )


def _validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Check that the arguments make sense together and set ``args.output_dir``."""
    if args.sources:
        if args.url or args.output or args.output_flag:
            parser.error("--sources cannot be combined with a URL or output directory")
        args.output_dir = None
        return
    if args.only or args.force or args.root:
        parser.error("--only, --force and --root need --sources")
    if not args.url:
        parser.error("a URL is required (or use --sources FILE)")
    if args.output_flag and args.output:
        parser.error(
            "provide the output directory as a positional argument "
            "or as -o/--output, not both"
        )
    args.output_dir = args.output_flag or args.output
    if not args.output_dir:
        parser.error("an output directory is required (positional argument or -o/--output)")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the dependency downloader."""
    parser = argparse.ArgumentParser(
        description=(
            "Download a URL into an output directory resolved relative to this "
            "script's directory (overwriting only when sha256sum differs), or "
            "fetch and unpack every source listed in a JSON manifest (--sources)."
        )
    )
    _add_arguments(parser)
    args = parser.parse_args(argv)
    _validate(parser, args)
    return args


def _begin_transfer(response: requests.Response) -> tuple[int | None, io.BytesIO | None]:
    """Log the remote size and, for files that fit in memory, read the body into a buffer."""
    remote_size = parse_content_length(response.headers)
    if remote_size is None:
        log("Remote size        : unknown (no Content-Length); streaming")
        return None, None
    log(f"Remote size        : {format_bytes(remote_size)} ({remote_size} bytes)")
    if remote_size > MEMORY_LIMIT_BYTES:
        log("Transfer mode      : streaming (chunked SHA-256)")
        return remote_size, None
    log(f"Transfer mode      : in-memory (<= {format_bytes(MEMORY_LIMIT_BYTES)})")
    return remote_size, read_into_buffer(response, remote_size)


def _store_new(
    response: requests.Response,
    dest: Path,
    buffer: io.BytesIO | None,
    remote_size: int | None,
) -> None:
    """Write a download that has no local copy to compare against."""
    if buffer is None:
        write_chunks(response, dest, remote_size)
    else:
        write_buffer(buffer, dest)
        buffer.close()


def download(url: str, dest: Path) -> str:
    """Download *url* to *dest*.

    Returns one of: 'created', 'updated', 'unchanged'.
    """
    local_exists = dest.is_file()
    log(f"Local file exists  : {local_exists}")

    with ThreadPoolExecutor(max_workers=1) as executor, new_session() as session:
        local_hash = executor.submit(sha256_file, dest) if local_exists else None
        with get_response(session, url) as response:
            remote_size, buffer = _begin_transfer(response)
            if local_hash is None:
                _store_new(response, dest, buffer, remote_size)
                return "created"

            # Local copy exists: compare SHA-256 before writing.
            remote_hash = (
                stream_hash(response, remote_size)
                if buffer is None
                else sha256_buffer(buffer)
            )
            log(f"Remote SHA-256     : {remote_hash}")
            log(f"Local  SHA-256     : {local_hash.result()}")

            if remote_hash == local_hash.result():
                if buffer is not None:
                    buffer.close()
                return "unchanged"
            if buffer is not None:
                write_buffer(buffer, dest)
                buffer.close()
                return "updated"

        # Streaming path, hashes differed: the first response body was consumed
        # for hashing, so fetch again and write directly.
        log("SHA-256 mismatch   : re-downloading to overwrite local copy")
        with get_response(session, url) as response:
            write_chunks(response, dest, parse_content_length(response.headers))
        return "updated"


def _destination(args: argparse.Namespace) -> Path:
    """Work out and prepare the destination file for single-file mode."""
    try:
        filename = extract_filename(args.url)
    except ValueError as exc:
        raise DownloadError(str(exc)) from exc

    output_dir = resolve_output_dir(args.output_dir)
    dest = output_dir / filename

    log(f"Script directory   : {SCRIPT_DIR}")
    log(f"Output directory   : {output_dir}")
    log(f"URL                : {args.url}")
    log(f"Filename           : {filename}")
    log(f"Destination        : {dest}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        message = f"cannot create output directory {output_dir}: {exc}"
        raise DownloadError(message) from exc
    if dest.exists() and not dest.is_file():
        message = f"destination exists and is not a regular file: {dest}"
        raise DownloadError(message)
    return dest


def _fetch(url: str, dest: Path) -> str:
    """Run :func:`download`, turning network and file errors into :class:`DownloadError`."""
    try:
        return download(url, dest)
    except requests.HTTPError as exc:
        response = exc.response
        status = response.status_code if response is not None else "?"
        reason = response.reason if response is not None else exc
        message = f"HTTP {status} for {url}: {reason}"
        raise DownloadError(message) from exc
    except requests.RequestException as exc:
        message = f"failed to fetch {url}: {exc}"
        raise DownloadError(message) from exc
    except OSError as exc:
        raise DownloadError(str(exc)) from exc


def run_single(args: argparse.Namespace) -> int:
    """Download the one URL given on the command line; return the exit status."""
    try:
        dest = _destination(args)
        result = _fetch(args.url, dest)
    except DownloadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result == "created":
        log(f"Wrote new file     : {dest}")
    elif result == "updated":
        log(f"Overwrote file     : {dest}\n(SHA-256 differed)")
    else:
        log(f"Left file intact   : {dest}\n(SHA-256 matched; download discarded)")

    write_github_outputs(
        {GITHUB_OUTPUT_CHANGED: "true" if result in {"created", "updated"} else "false"}
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the dependency downloader CLI."""
    args = parse_args(argv)
    if args.sources:
        return run_sources(args)
    return run_single(args)


if __name__ == "__main__":
    sys.exit(main())
