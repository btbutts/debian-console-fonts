"""Tests for the tool's reading of sources.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from psf_font_maker.common.manifest import Manifest, ManifestError, expand_url

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources.json"
FONT_SOURCES = ("terminus-font", "ucs-fonts", "uni-vga", "debian-legacy-fonts", "dejavu")


def test_every_source_the_tool_uses_is_in_the_manifest() -> None:
    """The five font directories and FreeType are all located by the manifest."""
    manifest = Manifest(SOURCES)
    assert {*FONT_SOURCES, "freetype"} <= set(manifest.names())
    for name in (*FONT_SOURCES, "freetype"):
        assert manifest.entry(name).directory.is_absolute()
    assert manifest.entry("uni-vga").directory == ROOT / "data" / "fontsets" / "uni-vga"


def test_paths_are_relative_to_the_manifest(tmp_path: Path) -> None:
    """A relative ``dest`` is resolved against the directory the manifest is in."""
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"x": {"destination-path": "a/b"}}), encoding="utf-8")
    entry = Manifest(path).entry("x")
    assert entry.directory == tmp_path.resolve() / "a" / "b"
    assert not entry.url


def test_unknown_or_unreadable_manifests_are_reported(tmp_path: Path) -> None:
    """A missing source, a missing file and bad JSON each give a clear error."""
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"x": {"destination-path": "d"}}), encoding="utf-8")
    with pytest.raises(ManifestError, match="no source 'y'"):
        Manifest(path).entry("y")
    with pytest.raises(ManifestError, match="cannot read"):
        Manifest(tmp_path / "missing.json")
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ManifestError, match="cannot read"):
        Manifest(path)


def test_url_placeholders_are_filled_like_the_downloader_does() -> None:
    """``{version}``, ``{major_minor}`` and the others take their values from the version."""
    url = "h/{major_minor}/f-{version}-{major}.{minor}.{patch}"
    assert expand_url(url, "2.14.3", "x") == "h/2.14/f-2.14.3-2.14.3"
    with pytest.raises(ManifestError, match="placeholder"):
        expand_url("{patch}", "2.14", "x")


def test_a_source_marked_not_in_use_is_refused(tmp_path: Path) -> None:
    """``"is-in-use": false`` means every tool ignores the entry."""
    path = tmp_path / "sources.json"
    entry = {"is-in-use": False, "destination-path": "d"}
    path.write_text(json.dumps({"x": entry}), encoding="utf-8")
    with pytest.raises(ManifestError, match="is-in-use"):
        Manifest(path).entry("x")
