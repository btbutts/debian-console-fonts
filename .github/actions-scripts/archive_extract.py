"""Unpack tar and zip archives safely.

Handles stripping leading path components, keeping only files that match
``include`` globs, and refuses anything that would be written outside the
target directory (absolute paths, ``..``, symlinks that point out of the tree).
"""

from __future__ import annotations

import posixpath
import re
import shutil
import stat
import tarfile
import zipfile
from typing import TYPE_CHECKING

from downloader_common import log
from sources_manifest import SourceError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

EXEC_BITS = 0o111
EXEC_FILE_MODE = 0o755
PLAIN_FILE_MODE = 0o644
_DRIVE_RE = re.compile(r"^[A-Za-z]:")

GlobList = list[tuple[str, re.Pattern[str]]]


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob (``*``, ``?``, ``**``) into a full-match regex."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def compile_globs(globs: Sequence[str]) -> GlobList:
    """Pair each glob with its compiled regex."""
    return [(glob, glob_to_regex(glob)) for glob in globs]


def matches(rel: str, patterns: GlobList) -> bool:
    """Return True if *rel* matches a pattern, or sits below a literal directory pattern.

    An empty pattern list matches everything.
    """
    if not patterns:
        return True
    for raw, regex in patterns:
        if regex.match(rel):
            return True
        if not any(char in raw for char in "*?") and rel.startswith(raw.rstrip("/") + "/"):
            return True
    return False


def member_path(name: str, strip: int) -> str | None:
    """Return the cleaned in-archive path after stripping, or None to skip the entry."""
    posix = name.replace("\\", "/")
    if posix.startswith("/") or _DRIVE_RE.match(posix):
        message = f"unsafe absolute path in archive: {name!r}"
        raise SourceError(message)
    parts = [part for part in posix.split("/") if part not in {"", "."}]
    if ".." in parts:
        message = f"unsafe path in archive: {name!r}"
        raise SourceError(message)
    parts = parts[strip:]
    return "/".join(parts) if parts else None


def check_symlink(rel: str, target: str) -> None:
    """Refuse symlinks that point outside the extracted tree."""
    if target.startswith("/") or _DRIVE_RE.match(target):
        message = f"unsafe absolute symlink in archive: {rel!r} -> {target!r}"
        raise SourceError(message)
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
    if resolved == ".." or resolved.startswith("../"):
        message = f"symlink escapes the archive: {rel!r} -> {target!r}"
        raise SourceError(message)


def _place(staging: Path, rel: str) -> Path:
    """Return the path for *rel* inside *staging*, creating its parent directory."""
    target = staging / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _file_mode(mode: int) -> int:
    """Return the permission bits to use: executable if any execute bit was set."""
    return EXEC_FILE_MODE if mode & EXEC_BITS else PLAIN_FILE_MODE


def _write_tar_member(tar: tarfile.TarFile, member: tarfile.TarInfo, target: Path, rel: str) -> bool:
    """Write one tar member to *target*; return False if it is skipped."""
    if member.issym():
        check_symlink(rel, member.linkname)
        target.symlink_to(member.linkname)
        return True
    if member.isfile() or member.islnk():
        source = tar.extractfile(member)
        if source is None:
            return False
        with source, target.open("wb") as handle:
            shutil.copyfileobj(source, handle)
        target.chmod(_file_mode(member.mode))
        return True
    log(f"Skipping special file in archive: {member.name}")
    return False


def _extract_tar(archive: Path, staging: Path, strip: int, patterns: GlobList) -> int:
    """Unpack a tar archive (any compression) and return the number of entries written."""
    count = 0
    with tarfile.open(archive, "r:*") as tar:
        for member in tar:
            rel = member_path(member.name, strip)
            if rel is None or member.isdir() or not matches(rel, patterns):
                continue
            if _write_tar_member(tar, member, _place(staging, rel), rel):
                count += 1
    return count


def _extract_zip(archive: Path, staging: Path, strip: int, patterns: GlobList) -> int:
    """Unpack a zip archive and return the number of entries written."""
    count = 0
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            rel = member_path(info.filename, strip)
            if rel is None or info.is_dir() or not matches(rel, patterns):
                continue
            mode = info.external_attr >> 16
            target = _place(staging, rel)
            if stat.S_ISLNK(mode):
                link = bundle.read(info).decode("utf-8")
                check_symlink(rel, link)
                target.symlink_to(link)
            else:
                with bundle.open(info) as source, target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
                target.chmod(_file_mode(mode))
            count += 1
    return count


def extract_archive(
    archive: Path,
    staging: Path,
    strip_components: int = 0,
    include: Sequence[str] = (),
) -> int:
    """Unpack a tar or zip *archive* into *staging*; return the number of entries."""
    patterns = compile_globs(include)
    if tarfile.is_tarfile(archive):
        return _extract_tar(archive, staging, strip_components, patterns)
    if zipfile.is_zipfile(archive):
        return _extract_zip(archive, staging, strip_components, patterns)
    message = f"{archive.name} is not a tar or zip archive"
    raise SourceError(message)
