"""Tests for what a release tarball holds: .github/release-files.txt and the release workflow."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE_LIST = ROOT / ".github" / "release-files.txt"
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
SOURCES = ROOT / "sources.json"

# The tracked files that are not in a release tarball (the workflow's NOT_SHIPPED).
NOT_SHIPPED = re.compile(r"^(\.github/|tests/|pyproject\.toml$|\.gitignore$)")
NOT_SHIPPED_IN_WORKFLOW = r"'^(\.github/|tests/|pyproject\.toml$|\.gitignore$)'"

needs_git = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(),
    reason="needs git and a checkout of the repository",
)


def listed() -> list[str]:
    """Return the paths of ``release-files.txt`` (comments and blank lines left out)."""
    lines = FILE_LIST.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def tracked() -> list[str]:
    """Return every file git tracks, relative to the repository root."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.splitlines()


def covers(entry: str, path: str) -> bool:
    """Say whether the pathspec *entry* (a file or a directory) includes *path*."""
    return path == entry or path.startswith(entry.rstrip("/") + "/")


def test_the_list_names_only_what_ships() -> None:
    """Nothing the tarball must not hold is listed, and nothing is listed twice."""
    entries = listed()
    assert entries, "release-files.txt lists nothing"
    assert len(entries) == len(set(entries))
    for entry in entries:
        assert not NOT_SHIPPED.match(entry + "/"), f"{entry} must not be in the release"
        assert not Path(entry).is_absolute()
        assert ".." not in Path(entry).parts


@needs_git
def test_every_listed_path_is_tracked() -> None:
    """A path that matches no tracked file would make ``git archive`` fail in the workflow."""
    files = tracked()
    for entry in listed():
        assert any(covers(entry, path) for path in files), f"{entry} matches no tracked file"


@needs_git
def test_no_tracked_file_is_left_out_by_accident() -> None:
    """Everything tracked is listed, except what the workflow says is not shipped."""
    entries = listed()
    left_out = [
        path
        for path in tracked()
        if not NOT_SHIPPED.match(path) and not any(covers(entry, path) for entry in entries)
    ]
    assert not left_out, f"tracked but neither shipped nor in NOT_SHIPPED: {left_out[:5]}"


@needs_git
def test_what_is_not_shipped_is_not_listed() -> None:
    """The excluded paths are tracked files, so the exclusion is not a dead pattern."""
    excluded = [path for path in tracked() if NOT_SHIPPED.match(path)]
    assert any(path.startswith(".github/") for path in excluded)
    assert any(path.startswith("tests/") for path in excluded)
    assert "pyproject.toml" in excluded


def test_every_font_source_in_use_is_shipped() -> None:
    """A source of sources.json that lives under data/ is in the list (as its directory)."""
    manifest = json.loads(SOURCES.read_text(encoding="utf-8"))
    entries = listed()
    for name, entry in manifest.items():
        destination = str(entry.get("destination-path", ""))
        if entry.get("is-in-use") is False or not destination.startswith("data/"):
            continue
        assert any(covers(listed_path, destination + "/x") for listed_path in entries), (
            f"the source {name!r} ({destination}) is in use but not in release-files.txt"
        )


def test_the_tool_and_the_makefile_are_shipped() -> None:
    """The things a build cannot do without are named explicitly."""
    entries = listed()
    for required in ("Makefile", "sources.json", "LICENSE", "README.md", "tools/psf_font_maker"):
        assert required in entries
    assert any(entry.startswith("data/") for entry in entries)


def test_the_workflow_uses_the_list_and_the_same_exclusions() -> None:
    """The workflow builds from release-files.txt and excludes what this test excludes."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert ".github/release-files.txt" in text
    assert f"NOT_SHIPPED: {NOT_SHIPPED_IN_WORKFLOW}" in text
    # Built from the tag's commit, with a deterministic gzip, and a checksum next to it.
    assert 'git archive --format=tar --prefix="${name}/" "$TAG"' in text
    assert "gzip -n" in text
    assert "sha256sum" in text
    assert ".tar.gz.sha256" in text
    assert "--verify-tag" in text
    assert "--prerelease" in text


def test_the_workflows_follow_the_branch_the_repository_uses() -> None:
    """The repository's default branch is master; no workflow may wait for ``main``."""
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        assert '"main"' not in text, f"{workflow.name} still names a main branch"
    assert 'branches: ["master"]' in (WORKFLOWS / "download-sources.yml").read_text(
        encoding="utf-8"
    )
    assert "DEFAULT_BRANCH: master" in RELEASE_WORKFLOW.read_text(encoding="utf-8")


def test_the_release_workflow_only_gets_the_permission_it_needs() -> None:
    """Read access for the workflow, write access for the one job that publishes."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"^permissions:\n  contents: read$", text, re.MULTILINE)
    assert text.count("contents: write") == 1
    # The tag only reaches shell through an environment variable, never ${{ }} in a script.
    scripts = re.findall(r"run: \|\n((?:\s{10}.*\n|\n)+)", text)
    assert scripts
    assert all("${{" not in script for script in scripts)
