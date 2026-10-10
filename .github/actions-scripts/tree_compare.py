"""Compare unpacked trees by content, so that an unchanged set of files is left alone."""

from __future__ import annotations

from typing import TYPE_CHECKING

from downloader_common import sha256_file

if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path

EXEC_BITS = 0o111


def _fingerprint(path: Path) -> str:
    """Return what identifies a file: its content and whether it is executable, or a link."""
    if path.is_symlink():
        return f"link:{path.readlink()}"
    mode = "x" if path.stat().st_mode & EXEC_BITS else "-"
    return f"{mode}:{sha256_file(path)}"


def tree_files(root: Path, ignore: Collection[str] = ()) -> dict[str, str]:
    """Return {relative path: fingerprint} for the files below *root*, except those in *ignore*."""
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in ignore:
            files[relative] = _fingerprint(path)
    return files
