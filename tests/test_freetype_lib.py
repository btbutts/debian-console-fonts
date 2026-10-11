"""Tests for the freetype tool: finding a FreeType, building one, handing it to the renderer."""

from __future__ import annotations

import ctypes.util
import hashlib
import io
import json
import shutil
import sys
import tarfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path

import pytest

from psf_font_maker.common.manifest import Manifest, SourceEntry
from psf_font_maker.fonts.options import Options
from psf_font_maker.fonts.plan import Planner
from psf_font_maker.freetype_lib import cli as freetype_cli
from psf_font_maker.freetype_lib import locate as locate_module
from psf_font_maker.freetype_lib.build import PREFIX_DIR, build, fetch, find_tools
from psf_font_maker.freetype_lib.errors import FreetypeError
from psf_font_maker.freetype_lib.locate import Located, explicit, search
from psf_font_maker.main import main
from psf_font_maker.otf2bdf import render
from psf_font_maker.otf2bdf.errors import RenderError
from psf_font_maker.otf2bdf.library import (
    LIBRARY_DIR_ENV,
    library_files,
    probe_version,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCES = ROOT / "sources.json"
LIBRARY_NAME = "libfreetype.dylib" if sys.platform == "darwin" else "libfreetype.so"
FAKE_VERSION = (2, 14, 3)
SHA256_DIGITS = 64
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="builds with configure and make")
has_tools = pytest.mark.skipif(
    shutil.which("make") is None or shutil.which("cc") is None,
    reason="needs make and a C compiler",
)

# A stand-in for FreeType's source tree: ./configure writes a Makefile that installs a file.
FAKE_CONFIGURE = """#!/bin/sh
for option in "$@"; do
  case "$option" in --prefix=*) prefix="${option#--prefix=}" ;; esac
done
printf 'all:\\n\\ttrue\\ninstall:\\n\\tmkdir -p %s/lib\\n\\techo built > %s/lib/%s\\n' \\
  "$prefix" "$prefix" "%(library)s" > Makefile
"""
FAILING_CONFIGURE = "#!/bin/sh\necho 'configure: error: no luck'\nexit 1\n"
# Like FreeType's: the install target honours DESTDIR, as every autotools project does.
DESTDIR_AWARE_CONFIGURE = """#!/bin/sh
for option in "$@"; do
  case "$option" in --prefix=*) prefix="${option#--prefix=}" ;; esac
done
printf 'all:\\n\\ttrue\\ninstall:\\n\\tmkdir -p $(DESTDIR)%s/lib\\n' "$prefix" > Makefile
printf '\\techo built > $(DESTDIR)%s/lib/%s\\n' "$prefix" "%(library)s" >> Makefile
"""


def make_manifest(directory: Path, configure: str | None = None, *, url: str = "") -> Path:
    """Write a ``sources.json`` whose FreeType is a fake source archive; return its path.

    The archive (when *configure* is given) is made in the directory and named by a ``file:``
    URL, so that downloading it needs no network.
    """
    entry: dict[str, str | bool] = {"download": False, "destination-path": "work"}
    if configure is not None:
        script = directory / "configure"
        script.write_text(configure.replace("%(library)s", LIBRARY_NAME), encoding="utf-8")
        script.chmod(0o755)
        archive = directory / "freetype-9.9.9.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(script, arcname="freetype-9.9.9/configure")
        script.unlink()
        entry["url"] = archive.as_uri()
        entry["version"] = "9.9.9"
        entry["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    if url:
        entry["url"] = url
    manifest = directory / "sources.json"
    manifest.write_text(json.dumps({"freetype": entry}), encoding="utf-8")
    return manifest


def entry_of(manifest: Path) -> SourceEntry:
    """Return the FreeType entry of *manifest*."""
    return Manifest(manifest).entry("freetype")


def run_cli(*args: str) -> tuple[int, str, str]:
    """Run the command line tool; return its status, standard output and standard error."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = main(list(args))
    return status, out.getvalue(), err.getvalue()


def installed_freetype() -> Located | None:
    """Return a FreeType of this machine that is new enough, if there is one."""
    rejected: list[str] = []
    return search(locate_module.host_dirs() + locate_module.system_dirs(), rejected)


def test_library_files_lists_only_libraries(tmp_path: Path) -> None:
    """Only files that look like FreeType libraries are listed, the plain name first."""
    (tmp_path / "libother.so").write_text("x", encoding="utf-8")
    (tmp_path / "libfreetype.txt").write_text("x", encoding="utf-8")
    assert library_files(tmp_path) == []
    longer = tmp_path / LIBRARY_NAME.replace("libfreetype", "libfreetype.6")
    plain = tmp_path / LIBRARY_NAME
    longer.write_text("x", encoding="utf-8")
    plain.write_text("x", encoding="utf-8")
    assert library_files(tmp_path) == [plain, longer]


def test_a_file_that_is_not_a_library_has_no_version(tmp_path: Path) -> None:
    """A text file named like the library is rejected, with its reason."""
    fake = tmp_path / LIBRARY_NAME
    fake.write_text("not a library", encoding="utf-8")
    assert probe_version(fake) is None
    rejected: list[str] = []
    assert search([tmp_path], rejected) is None
    assert "not a usable FreeType" in rejected[0]


def test_a_directory_without_freetype_is_an_error_when_the_user_names_it(tmp_path: Path) -> None:
    """A directory given explicitly must hold a usable library; there is no fallback."""
    with pytest.raises(FreetypeError, match="not usable"):
        explicit([tmp_path])


def test_a_real_freetype_is_found_and_new_enough() -> None:
    """If this machine has FreeType 2.13.3 or later, the search finds it."""
    found = installed_freetype()
    if found is None:
        pytest.skip("no FreeType 2.13.3 or later on this machine")
    assert found.version >= render.MINIMUM_FREETYPE
    assert found.directory is not None
    assert probe_version(library_files(found.directory)[0]) == found.version


def test_the_name_lookup_is_used_last(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """With nothing in the directories, the loader's own answer is tried."""
    monkeypatch.setattr(locate_module, "host_dirs", list)
    monkeypatch.setattr(locate_module, "system_dirs", list)
    monkeypatch.setattr(ctypes.util, "find_library", lambda _name: None)
    found, rejected = locate_module.locate(tmp_path)
    assert found is None
    assert not rejected
    monkeypatch.setattr(locate_module, "probe_version", lambda _name: FAKE_VERSION)
    monkeypatch.setattr(ctypes.util, "find_library", lambda _name: "libfreetype.so.6")
    found, _ = locate_module.locate(tmp_path)
    assert found == Located(None, FAKE_VERSION, "libfreetype.so.6")


def test_too_old_a_freetype_is_rejected_and_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A library older than the minimum is not used, and the report says which."""
    (tmp_path / LIBRARY_NAME).write_text("x", encoding="utf-8")
    monkeypatch.setattr(locate_module, "probe_version", lambda _name: (2, 13, 2))
    rejected: list[str] = []
    assert search([tmp_path], rejected) is None
    assert rejected == [f"{tmp_path / LIBRARY_NAME}: FreeType 2.13.2"]


def test_the_real_manifest_describes_where_freetype_comes_from() -> None:
    """The project's own sources.json names a GNU URL, a checksum and a build directory."""
    entry = entry_of(SOURCES)
    assert entry.url == "https://download.savannah.gnu.org/releases/freetype/freetype-2.14.3.tar.gz"
    assert len(entry.sha256) == SHA256_DIGITS
    assert entry.directory == ROOT / "build" / "freetype"


def test_the_downloader_does_not_fetch_freetype() -> None:
    """The entry says ``"download": false``, so the dependency downloader leaves it alone."""
    freetype = json.loads(SOURCES.read_text(encoding="utf-8"))["freetype"]
    assert freetype["download"] is False


def test_fetch_downloads_checks_and_reuses(tmp_path: Path) -> None:
    """The archive is fetched into the entry's directory, checked, and not fetched again."""
    entry = entry_of(make_manifest(tmp_path, FAKE_CONFIGURE))
    archive = fetch(entry)
    assert archive == entry.directory / "freetype-9.9.9.tar.gz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == entry.sha256
    (tmp_path / "freetype-9.9.9.tar.gz").unlink()  # the "server" is gone
    assert fetch(entry) == archive


def test_a_download_with_another_checksum_is_refused_and_not_kept(tmp_path: Path) -> None:
    """FreeType's archive is built and run, so one that is not the recorded file is refused."""
    manifest = make_manifest(tmp_path, FAKE_CONFIGURE)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["freetype"]["sha256"] = "0" * SHA256_DIGITS
    manifest.write_text(json.dumps(data), encoding="utf-8")
    entry = entry_of(manifest)
    with pytest.raises(FreetypeError, match="update sha256"):
        fetch(entry)
    assert not list(entry.directory.iterdir())


def test_no_recorded_checksum_means_no_build(tmp_path: Path) -> None:
    """Without a sha256 in sources.json nothing downloaded is run."""
    manifest = make_manifest(tmp_path, FAKE_CONFIGURE)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["freetype"]["sha256"] = ""
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(FreetypeError, match="records no sha256"):
        fetch(entry_of(manifest))


def test_fetch_reports_an_unreachable_server(tmp_path: Path) -> None:
    """A failed download says what to do instead."""
    missing = (tmp_path / "gone.tar.gz").as_uri()
    entry = entry_of(make_manifest(tmp_path, url=missing))
    with pytest.raises(FreetypeError, match="FREETYPE_LIB_DIR"):
        fetch(entry)


def test_fetch_needs_a_url(tmp_path: Path) -> None:
    """An entry without a URL cannot be fetched."""
    with pytest.raises(FreetypeError, match="no url"):
        fetch(entry_of(make_manifest(tmp_path)))


@posix_only
@has_tools
def test_build_runs_configure_make_install_and_cleans_up(tmp_path: Path) -> None:
    """The archive is fetched and the three steps run in order; the source tree is removed."""
    entry = entry_of(make_manifest(tmp_path, FAKE_CONFIGURE))
    directory = build(entry, jobs=2)
    assert directory == (entry.directory / PREFIX_DIR).resolve() / "lib"
    assert (directory / LIBRARY_NAME).read_text(encoding="utf-8") == "built\n"
    assert not (entry.directory / "src").exists()
    log = (entry.directory / "build.log").read_text(encoding="utf-8")
    assert log.index("./configure") < log.index("install")


@posix_only
@has_tools
def test_the_destination_of_our_own_install_does_not_reach_freetype(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``make install DESTDIR=...`` must not move FreeType's own install.

    GNU make passes DESTDIR to the tool in the environment and in MAKEFLAGS. FreeType's
    ``make install`` honours it, so it would end up below the font destination (for
    Buildroot, in the target root file system) and not in its prefix, where it is looked for.
    """
    target = tmp_path / "target"
    monkeypatch.setenv("DESTDIR", str(target))
    monkeypatch.setenv("MAKEFLAGS", f"DESTDIR={target}")
    entry = entry_of(make_manifest(tmp_path, DESTDIR_AWARE_CONFIGURE))
    directory = build(entry, jobs=1)
    assert directory == (entry.directory / PREFIX_DIR).resolve() / "lib"
    assert (directory / LIBRARY_NAME).read_text(encoding="utf-8") == "built\n"
    assert not target.exists()


@posix_only
@has_tools
def test_a_failed_build_shows_the_end_of_the_log(tmp_path: Path) -> None:
    """When a step fails, the error carries what it printed."""
    entry = entry_of(make_manifest(tmp_path, FAILING_CONFIGURE))
    with pytest.raises(FreetypeError, match="no luck"):
        build(entry)


def test_no_compiler_gives_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a C compiler the error says to install one."""
    monkeypatch.delenv("CC", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(FreetypeError, match="GCC"):
        find_tools()


def test_no_build_option_reports_instead_of_building(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--no-build`` fails with the rejected libraries listed when nothing is usable."""
    found = (None, ["/x/libfreetype.so: 2.1.0"])
    monkeypatch.setattr(freetype_cli, "locate", lambda _prefix: found)
    status, out, err = run_cli(
        "freetype", "--data", str(DATA), "--sources", str(SOURCES), "--always", "--no-build"
    )
    assert status == 1
    assert not out
    assert "/x/libfreetype.so: 2.1.0" in err
    assert "make freetype" in err


def test_missing_freetype_is_built_and_its_directory_printed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With nothing found, the build runs and its library directory is what is printed."""
    made = tmp_path / "made" / "lib"
    made.mkdir(parents=True)
    calls: list[Path] = []

    def fake_build(entry: SourceEntry, _jobs: int | None, _archives: list[Path]) -> Path:
        calls.append(entry.directory)
        return made

    monkeypatch.setattr(freetype_cli, "locate", lambda _prefix: (None, []))
    monkeypatch.setattr(freetype_cli, "build", fake_build)
    monkeypatch.setattr(freetype_cli, "explicit", lambda _dirs: Located(made, FAKE_VERSION))
    status, out, err = run_cli(
        "freetype", "--data", str(DATA), "--sources", str(SOURCES), "--always"
    )
    assert status == 0
    assert out.strip() == str(made)
    assert calls == [ROOT / "build" / "freetype"]
    assert "no FreeType 2.13.3 or later found" in err


def test_nothing_is_provided_when_no_font_needs_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terminus is drawn from BDF files, so no FreeType is looked for, let alone built."""
    if not (ROOT / "data" / "fontsets" / "terminus-font").is_dir():
        pytest.skip("fonts not downloaded")

    def fail(_prefix: Path) -> None:
        pytest.fail("looked for FreeType")

    monkeypatch.setattr(freetype_cli, "locate", fail)
    status, out, err = run_cli(
        "freetype", "--data", str(DATA), "--sources", str(SOURCES), "--faces", "Terminus16"
    )
    assert (status, out) == (0, "")
    assert "no selected font needs FreeType" in err


def test_a_truetype_selection_needs_it() -> None:
    """DejaVu faces are drawn from TrueType files, Terminus faces are not."""
    if not (ROOT / "data" / "fontsets" / "dejavu").is_dir():
        pytest.skip("DejaVu not downloaded")
    options = Options(data=DATA, sources=SOURCES)
    assert Planner(replace(options, faces=("DejaVu%",))).needs_truetype()
    assert not Planner(replace(options, faces=("Terminus%",))).needs_truetype()


def test_clean_removes_what_was_built(tmp_path: Path) -> None:
    """``--clean`` deletes the entry's directory and nothing else."""
    manifest = make_manifest(tmp_path)
    work = tmp_path / "work"
    (work / "prefix").mkdir(parents=True)
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
    status, _, _ = run_cli("freetype", "--data", str(DATA), "--sources", str(manifest), "--clean")
    assert status == 0
    assert not work.exists()
    assert (tmp_path / "keep.txt").exists()


def test_the_renderer_uses_the_chosen_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """While freetype-py is imported, the loader's answer for FreeType is the chosen file."""
    library = tmp_path / LIBRARY_NAME
    library.write_text("x", encoding="utf-8")
    original = ctypes.util.find_library
    monkeypatch.setenv(LIBRARY_DIR_ENV, "")  # so that the test's change is undone afterwards
    render.use_library_dir(tmp_path)
    with render.chosen_library():
        assert ctypes.util.find_library("freetype") == str(library)
    assert ctypes.util.find_library("freetype") == original("freetype")


def test_the_renderer_rejects_a_directory_without_freetype(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A chosen directory with no library is an error, not a silent fallback."""
    monkeypatch.setenv(LIBRARY_DIR_ENV, str(tmp_path))
    with pytest.raises(RenderError, match="no FreeType library"), render.chosen_library():
        pass


def test_an_archive_from_the_package_manager_is_used_not_downloaded(tmp_path: Path) -> None:
    """An archive in a given directory (Buildroot's) is used in place, with no download."""
    entry = entry_of(make_manifest(tmp_path, FAKE_CONFIGURE))
    downloads = tmp_path / "dl"
    downloads.mkdir()
    shutil.copy(tmp_path / "freetype-9.9.9.tar.gz", downloads)
    (tmp_path / "freetype-9.9.9.tar.gz").unlink()  # nothing could be downloaded now
    assert fetch(entry, [tmp_path / "elsewhere", downloads]) == downloads / "freetype-9.9.9.tar.gz"
    assert not entry.directory.exists()


def test_an_archive_from_the_package_manager_with_another_checksum_is_refused(
    tmp_path: Path,
) -> None:
    """The recorded checksum applies to a given archive too; it is left where it is."""
    entry = entry_of(make_manifest(tmp_path, FAKE_CONFIGURE))
    downloads = tmp_path / "dl"
    downloads.mkdir()
    (downloads / "freetype-9.9.9.tar.gz").write_bytes(b"re-released")
    with pytest.raises(FreetypeError, match="update sha256"):
        fetch(entry, [downloads])
    assert (downloads / "freetype-9.9.9.tar.gz").exists()


@posix_only
@has_tools
def test_the_archive_dir_option_reaches_the_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``--archive-dir`` on the command line is where the build looks for the archive."""
    manifest = make_manifest(tmp_path, FAKE_CONFIGURE)
    downloads = tmp_path / "dl"
    downloads.mkdir()
    shutil.move(tmp_path / "freetype-9.9.9.tar.gz", downloads)
    monkeypatch.setattr(freetype_cli, "locate", lambda _prefix: (None, []))
    monkeypatch.setattr(freetype_cli, "explicit", lambda dirs: Located(dirs[0], FAKE_VERSION))
    status, out, _ = run_cli(
        "freetype", "--data", str(DATA), "--sources", str(manifest), "--always",
        "--archive-dir", str(downloads),
    )
    assert status == 0
    assert out.strip().endswith("prefix/lib")
