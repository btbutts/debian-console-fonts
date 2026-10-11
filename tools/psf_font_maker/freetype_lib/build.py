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
from time import monotonic
from typing import TYPE_CHECKING

from psf_font_maker.common.log import Heartbeat, detail
from psf_font_maker.freetype_lib.errors import FreetypeError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import BinaryIO

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
# Variables of the make that runs this tool. DESTDIR is where *our* ``make install`` puts
# the fonts, and GNU make hands every command-line variable on to a sub-make in MAKEFLAGS
# (and MAKEOVERRIDES, MFLAGS), which overrides what a makefile sets. FreeType's own
# ``make install`` honours DESTDIR, so left alone it would install FreeType below the font
# destination (a Buildroot ``DESTDIR=$(TARGET_DIR)``) instead of in its prefix.
BUILD_ONLY_VARIABLES = ("DESTDIR", "MAKEFLAGS", "MAKEOVERRIDES", "MFLAGS", "GNUMAKEFLAGS")
LOG_TAIL_LINES = 25
TIMEOUT_SECONDS = 60
CHUNK = 1 << 16
PROGRESS_SECONDS = 3.0
MEGABYTE = 1 << 20


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
    detail(f"checking the SHA-256 of {archive.name.removesuffix('.part')}", 2)
    actual = digest_of(archive)
    if actual == entry.sha256:
        detail(f"SHA-256 {actual}: matches sources.json: PASS", 3)
    if actual != entry.sha256:
        message = (
            f"{archive} has SHA-256 {actual}, but sources.json records {entry.sha256}. If "
            "upstream re-released it and you trust the new file, update sha256 in sources.json"
        )
        raise FreetypeError(message)
    return archive


def copy_with_progress(source: BinaryIO, target: BinaryIO, total: int) -> None:
    """Copy *source* to *target*, writing a line every few seconds about how far it is."""
    done = 0
    reported = monotonic()
    while block := source.read(CHUNK):
        target.write(block)
        done += len(block)
        if monotonic() - reported >= PROGRESS_SECONDS:
            reported = monotonic()
            of = f" of {total / MEGABYTE:.1f} MB ({100 * done // total}%)" if total else ""
            detail(f"downloaded {done / MEGABYTE:.1f} MB{of}", 3)
    detail(f"downloaded {done / MEGABYTE:.1f} MB: done", 3)


def provided(entry: SourceEntry, directories: Sequence[Path]) -> Path | None:
    """Return the archive of *entry* if one of *directories* already has it.

    These are directories where a package manager keeps its downloads.
    """
    name = entry.url.rsplit("/", 1)[-1]
    for directory in directories:
        if (directory / name).is_file():
            detail(f"the source archive is already at hand: {directory / name}", 2)
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
    detail(f"downloading {entry.url}", 2)
    partial = archive.with_name(archive.name + ".part")
    try:
        with (
            urllib.request.urlopen(entry.url, timeout=TIMEOUT_SECONDS) as reply,
            partial.open("wb") as handle,
        ):
            copy_with_progress(reply, handle, int(reply.headers.get("Content-Length") or 0))
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


def step_environment(compiler: str) -> dict[str, str]:
    """Return the environment for FreeType's configure and make.

    It is ours, without the variables that belong to the make that started this tool (see
    ``BUILD_ONLY_VARIABLES``), and with the compiler chosen.
    """
    env = {name: value for name, value in os.environ.items() if name not in BUILD_ONLY_VARIABLES}
    env["CC"] = compiler
    return env


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


def short_name(command: list[str]) -> str:
    """Return a command's name without its options (``./configure``, ``make install``)."""
    words = [command[0], *(word for word in command[1:2] if not word.startswith("-"))]
    return " ".join(words)


def run(command: list[str], cwd: Path, log: Path, env: dict[str, str]) -> None:
    """Run one build step, appending its output to *log*; show the end of it on failure."""
    started = monotonic()
    name = short_name(command)
    with log.open("ab") as handle:
        handle.write(f"$ {' '.join(command)}\n".encode())
        handle.flush()
        with Heartbeat(lambda: f"still running {name} ({monotonic() - started:.0f}s)"):
            result = subprocess.run(
                command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT, check=False
            )
    if result.returncode != 0:
        text = log.read_text(encoding="utf-8", errors="replace")
        tail = text.splitlines()[-LOG_TAIL_LINES:]
        message = f"building FreeType failed ({name}); the end of {log}:\n"
        raise FreetypeError(message + "\n".join(tail))
    detail(f"{name}: done in {monotonic() - started:.0f}s", 3)


def build(entry: SourceEntry, jobs: int | None = None, archive_dirs: Sequence[Path] = ()) -> Path:
    """Fetch, build and install FreeType below ``entry.directory``; return its library dir."""
    if sys.platform == "win32":
        message = "building FreeType is not supported on Windows; set FREETYPE_LIB_DIR"
        raise FreetypeError(message)
    detail("build tools:", 2)
    compiler, make = find_tools()
    detail(f"C compiler: {compiler}; make: {make}", 3)
    detail("getting the source archive:", 2)
    archive = fetch(entry, archive_dirs)
    work = entry.directory
    prefix = (work / PREFIX_DIR).resolve()
    log = work / LOG_NAME
    log.unlink(missing_ok=True)
    detail(f"unpacking {archive.name}", 2)
    tree = unpack(archive, work / SOURCE_DIR)
    detail(f"building it into {prefix} (full output: {log})", 2)
    env = step_environment(compiler)
    steps = [
        ["./configure", f"--prefix={prefix}", *CONFIGURE_OPTIONS],
        [make, f"-j{jobs or os.cpu_count() or 1}"],
        [make, "install"],
    ]
    for number, step in enumerate(steps, start=1):
        detail(f"step {number} of {len(steps)}: {short_name(step)}", 2)
        run(step, tree, log, env)
    shutil.rmtree(work / SOURCE_DIR, ignore_errors=True)
    detail(f"FreeType is installed in {prefix}", 2)
    return prefix / "lib"
