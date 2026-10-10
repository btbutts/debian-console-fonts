"""Fetch FreeType's source and build it, in the directory ``sources.json`` gives it."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from psf_font_maker.freetype_lib.errors import FreetypeError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from psf_font_maker.common.manifest import SourceEntry

SOURCE_NAME = "freetype"  # the entry of sources.json
PREFIX_DIR = "prefix"
SOURCE_DIR = "src"
LOG_NAME = "build.log"
COMPILERS = ("cc", "gcc", "clang")
MAKES = ("gmake", "make")
CONFIGURE_OPTIONS = (
    "--enable-shared",
    "--disable-static",
    "--with-zlib=no",
    "--with-bzip2=no",
    "--with-png=no",
    "--with-harfbuzz=no",
    "--with-brotli=no",
)
LOG_TAIL_LINES = 25
TIMEOUT_SECONDS = 60
CHUNK = 1 << 16


def digest_of(path: Path) -> str:
    """Return the SHA-256 of the file *path* as hexadecimal text."""
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            sha.update(block)
    return sha.hexdigest()


def verify(archive: Path, entry: SourceEntry) -> Path:
    """Return *archive* if it has the SHA-256 that sources.json records, else refuse it.

    Unlike the font archives, FreeType's is not data: ``configure`` from it is run on this
    machine. A re-released tarball therefore needs a deliberate update of the SHA-256 in
    sources.json before it is built.
    """
    if not entry.sha256:
        message = f"sources.json records no sha256 for {entry.name!r}; refusing to build it"
        raise FreetypeError(message)
    actual = digest_of(archive)
    if actual != entry.sha256:
        message = (
            f"{archive} has SHA-256 {actual}, but sources.json records {entry.sha256}. If "
            "upstream re-released it and you trust the new file, update sha256 in sources.json"
        )
        raise FreetypeError(message)
    return archive


def provided(entry: SourceEntry, directories: Sequence[Path]) -> Path | None:
    """Return the archive of *entry* if one of *directories* already has it.

    These are directories where a package manager keeps its downloads.
    """
    name = entry.url.rsplit("/", 1)[-1]
    for directory in directories:
        if (directory / name).is_file():
            return verify(directory / name, entry)
    return None


def fetch(entry: SourceEntry, archive_dirs: Sequence[Path] = ()) -> Path:
    """Return the source archive of *entry*, downloading it only if nobody has it yet.

    It is looked for in *archive_dirs* first (Buildroot downloads it there ahead of time, so
    that it can build offline), then in the entry's own directory, where a copy put by hand
    also works; only then is it downloaded into that directory.
    """
    if not entry.url:
        message = f"sources.json gives no url for {entry.name!r}"
        raise FreetypeError(message)
    found = provided(entry, [*archive_dirs, entry.directory])
    if found is not None:
        return found
    archive = entry.directory / entry.url.rsplit("/", 1)[-1]
    entry.directory.mkdir(parents=True, exist_ok=True)
    print(f"downloading {entry.url}", file=sys.stderr)
    partial = archive.with_name(archive.name + ".part")
    try:
        with (
            urllib.request.urlopen(entry.url, timeout=TIMEOUT_SECONDS) as reply,
            partial.open("wb") as handle,
        ):
            shutil.copyfileobj(reply, handle)
    except (urllib.error.URLError, TimeoutError) as exc:
        partial.unlink(missing_ok=True)
        message = (
            f"could not download {entry.url}: {exc}. Check the network, put the archive in "
            f"{entry.directory}, or give FREETYPE_LIB_DIR a FreeType 2.13.3 or later"
        )
        raise FreetypeError(message) from exc
    try:
        verify(partial, entry)
    except FreetypeError:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(archive)
    return archive


def find_tools() -> tuple[str, str]:
    """Return the C compiler and make to use, or explain what to install."""
    compiler = os.environ.get("CC") or next((c for c in COMPILERS if shutil.which(c)), None)
    make = next((m for m in MAKES if shutil.which(m)), None)
    if compiler is None or not shutil.which(compiler.split()[0]):
        message = (
            "FreeType is not installed and there is no C compiler to build it with. Install "
            "GCC or another C compiler (Debian/Ubuntu: apt install build-essential; macOS: "
            "xcode-select --install), or install FreeType 2.13.3 or later yourself"
        )
        raise FreetypeError(message)
    if make is None:
        message = "building FreeType needs make, which was not found"
        raise FreetypeError(message)
    return compiler, make


def unpack(archive: Path, target: Path) -> Path:
    """Extract *archive* into *target* and return the directory of the source tree."""
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(target, filter="data")
    trees = [path for path in target.iterdir() if path.is_dir()]
    if len(trees) != 1:
        message = f"{archive.name} does not hold a single source directory"
        raise FreetypeError(message)
    return trees[0]


def run(command: list[str], cwd: Path, log: Path, env: dict[str, str]) -> None:
    """Run one build step, appending its output to *log*; show the end of it on failure."""
    with log.open("ab") as handle:
        handle.write(f"$ {' '.join(command)}\n".encode())
        handle.flush()
        result = subprocess.run(
            command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT, check=False
        )
    if result.returncode != 0:
        text = log.read_text(encoding="utf-8", errors="replace")
        tail = text.splitlines()[-LOG_TAIL_LINES:]
        message = f"building FreeType failed ({' '.join(command[:2])}); the end of {log}:\n"
        raise FreetypeError(message + "\n".join(tail))


def build(entry: SourceEntry, jobs: int | None = None, archive_dirs: Sequence[Path] = ()) -> Path:
    """Fetch, build and install FreeType below ``entry.directory``; return its library dir."""
    if sys.platform == "win32":
        message = "building FreeType is not supported on Windows; set FREETYPE_LIB_DIR"
        raise FreetypeError(message)
    compiler, make = find_tools()
    archive = fetch(entry, archive_dirs)
    work = entry.directory
    prefix = (work / PREFIX_DIR).resolve()
    log = work / LOG_NAME
    log.unlink(missing_ok=True)
    print(f"building {archive.name} into {prefix} (log: {log})", file=sys.stderr)
    tree = unpack(archive, work / SOURCE_DIR)
    env = {**os.environ, "CC": compiler}
    steps = [
        ["./configure", f"--prefix={prefix}", *CONFIGURE_OPTIONS],
        [make, f"-j{jobs or os.cpu_count() or 1}"],
        [make, "install"],
    ]
    for step in steps:
        run(step, tree, log, env)
    shutil.rmtree(work / SOURCE_DIR, ignore_errors=True)
    return prefix / "lib"
