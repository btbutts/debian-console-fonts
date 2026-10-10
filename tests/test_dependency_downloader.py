"""Tests for the dependency downloader's manifest mode and single-file mode.

Everything runs against a throwaway HTTP server on localhost; no network.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import threading
import zipfile
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest

import archive_extract
import dependencyDownloader
import sources_manifest
import sources_sync

if TYPE_CHECKING:
    from collections.abc import Generator

OCTET_STREAM = "application/octet-stream"
TarMode = Literal["w:gz", "w:bz2", "w:xz"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def make_tar(members: dict, mode: TarMode = "w:gz") -> bytes:
    """Build a tar archive. Values: bytes, (bytes, permissions) or ('symlink', target)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as tar:
        for name, value in members.items():
            info = tarfile.TarInfo(name)
            if isinstance(value, tuple) and value[0] == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = value[1]
                tar.addfile(info)
                continue
            data, perm = value if isinstance(value, tuple) else (value, 0o644)
            info.size = len(data)
            info.mode = perm
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def make_zip(members: dict[str, bytes]) -> bytes:
    """Build a zip archive from a mapping of member name to content."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as bundle:
        for name, data in members.items():
            bundle.writestr(name, data)
    return buf.getvalue()


class FileServer:
    """A throwaway HTTP server that serves files from a directory and records requests."""

    def __init__(self, directory: Path) -> None:
        """Serve *directory*; call :meth:`start` to begin listening."""
        self.directory = directory
        self.requests: list[tuple[str, str]] = []
        self.content_types: dict[str, str] = {}
        self.base = ""
        self._httpd: ThreadingHTTPServer | None = None

    def put(self, name: str, body: bytes, content_type: str = OCTET_STREAM) -> None:
        """Publish *body* under ``/name`` with the given Content-Type."""
        (self.directory / name).write_bytes(body)
        self.content_types[name] = content_type

    def url(self, name: str) -> str:
        """Return the full URL of ``/name``."""
        return f"{self.base}/{name}"

    def start(self) -> None:
        """Begin serving on a free local port in a background thread."""
        class Handler(SimpleHTTPRequestHandler):
            """Serve the directory, record each request and keep quiet."""

            state = self

            def __init__(self, *args, **kwargs) -> None:
                """Bind the handler to the served directory."""
                super().__init__(*args, directory=str(self.state.directory), **kwargs)

            def send_head(self):
                """Record the request, then answer it as usual."""
                self.state.requests.append((self.path, self.headers.get("User-Agent", "")))
                return super().send_head()

            def guess_type(self, path) -> str:
                """Return the Content-Type registered for the file."""
                return self.state.content_types.get(Path(path).name, OCTET_STREAM)

            def log_request(self, code="-", size="-") -> None:
                """Do not log requests."""

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def stop(self) -> None:
        """Stop listening."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()


@contextmanager
def serve(directory: Path) -> Generator[FileServer, None, None]:
    """Run a :class:`FileServer` for the duration of a ``with`` block."""
    server = FileServer(directory)
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(name="no_truststore", autouse=True)
def no_truststore_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the operating system's TLS settings during tests."""
    monkeypatch.setattr(sources_sync, "use_system_trust_store", lambda: None)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return an empty repository root; step outputs go to ``<root>/../github_output.txt``."""
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github_output.txt"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture(name="web")
def web_fixture(tmp_path: Path) -> Generator[FileServer, None, None]:
    """Yield a running :class:`FileServer` with an empty document root."""
    docroot = tmp_path / "www"
    docroot.mkdir()
    with serve(docroot) as server:
        yield server


def run(root: Path, sources: list, *extra: str) -> int:
    """Write a manifest into *root* and run the downloader on it."""
    (root / "sources.json").write_text(json.dumps({"sources": sources}), encoding="utf-8")
    return dependencyDownloader.main(
        ["--sources", "sources.json", "--root", str(root), *extra]
    )


def outputs(root: Path) -> dict[str, str]:
    """Return the GITHUB_OUTPUT values written so far (the last write of a key wins)."""
    result = {}
    for line in (root.parent / "github_output.txt").read_text().splitlines():
        key, _, value = line.partition("=")
        result[key] = value
    return result


def entry(web: FileServer, **overrides) -> dict:
    """Return a manifest entry for ``font.tar.gz`` on *web*, with *overrides* applied."""
    data = {
        "name": "font",
        "url": web.url("font.tar.gz"),
        "dest": "sources/font",
        "strip_components": 1,
    }
    data.update(overrides)
    return data


def files_under(directory: Path) -> list[str]:
    """Return the sorted relative paths of all files below *directory*."""
    return sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file())


# --------------------------------------------------------------------------
# placeholders, globs, manifest validation
# --------------------------------------------------------------------------


def test_version_fields() -> None:
    """Version numbers are split into the placeholder values."""
    assert sources_manifest.version_fields("4.49.1") == {
        "version": "4.49.1",
        "major": "4",
        "minor": "49",
        "patch": "1",
        "major_minor": "4.49",
    }
    assert sources_manifest.version_fields("2.37")["major_minor"] == "2.37"
    odd = sources_manifest.version_fields("1.242~deb13u1")
    assert odd["major_minor"] == "1.242"
    assert "patch" not in odd


def test_expand_placeholders() -> None:
    """Placeholders are filled in, and bad ones are refused."""
    expand = sources_manifest.expand_placeholders
    url = "https://x/terminus-font-{major_minor}/terminus-font-{version}.tar.gz"
    assert expand(url, "4.49.1", "t") == "https://x/terminus-font-4.49/terminus-font-4.49.1.tar.gz"
    assert expand("https://x/plain.tgz", None, "t") == "https://x/plain.tgz"
    with pytest.raises(sources_manifest.SourceError, match="no 'version'"):
        expand(url, None, "t")
    with pytest.raises(sources_manifest.SourceError, match="not available"):
        expand("https://x/{patch}", "2.37", "t")
    with pytest.raises(sources_manifest.SourceError, match="not available"):
        expand("https://x/{bogus}", "1.0.0", "t")


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("Fonts/**", "Fonts/Makefile", True),
        ("Fonts/**", "Fonts/bdf/ter-u16n.bdf", True),
        ("Fonts/**", "debian/control", False),
        ("*.bdf", "8x13.bdf", True),
        ("*.bdf", "sub/8x13.bdf", False),
        ("**/*.bdf", "sub/deep/8x13.bdf", True),
        ("ttf/DejaVuSansMono*.ttf", "ttf/DejaVuSansMono-Bold.ttf", True),
        ("ttf/DejaVuSansMono*.ttf", "ttf/DejaVuSans.ttf", False),
        ("Fonts", "Fonts/Makefile", True),
        ("LICENSE", "LICENSE.txt", False),
    ],
)
def test_glob_matching(pattern: str, path: str, expected: bool) -> None:
    """Include globs match as documented."""
    assert archive_extract.matches(path, archive_extract.compile_globs([pattern])) is expected


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ({"name": "a", "url": "u", "dest": "../x"}, "relative path"),
        ({"name": "a", "url": "u", "dest": "/abs"}, "relative path"),
        ({"name": "a", "url": "u", "dest": "."}, "relative path"),
        ({"name": "a", "url": "u", "dest": "d", "bogus": 1}, "unknown keys"),
        ({"name": "bad name", "url": "u", "dest": "d"}, "name may only"),
        ({"name": "a", "dest": "d"}, "'url' is required"),
        ({"name": "a", "url": "u", "dest": "d", "strip_components": -1}, "integer >= 0"),
        ({"name": "a", "url": "u", "dest": "d", "include": "x"}, "'include'"),
        ({"name": "a", "url": "u", "dest": "d", "enabled": "yes"}, "true or false"),
    ],
)
def test_manifest_validation(tmp_path: Path, bad: dict, message: str) -> None:
    """Invalid manifest entries are rejected with a clear message."""
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"sources": [bad]}))
    with pytest.raises(sources_manifest.SourceError, match=message):
        sources_manifest.load_sources(path)


def test_manifest_rejects_duplicates_and_nested_dests(tmp_path: Path) -> None:
    """Names must be unique and destinations must not overlap."""
    path = tmp_path / "m.json"
    path.write_text(json.dumps([
        {"name": "a", "url": "u", "dest": "s/a"},
        {"name": "a", "url": "u", "dest": "s/b"},
    ]))
    with pytest.raises(sources_manifest.SourceError, match="duplicate"):
        sources_manifest.load_sources(path)
    path.write_text(json.dumps([
        {"name": "a", "url": "u", "dest": "s/a"},
        {"name": "b", "url": "u", "dest": "s/a/inner"},
    ]))
    with pytest.raises(sources_manifest.SourceError, match="inside"):
        sources_manifest.load_sources(path)


# --------------------------------------------------------------------------
# download, extract, lock
# --------------------------------------------------------------------------


def test_first_run_extracts_filters_and_locks(repo: Path, web: FileServer) -> None:
    """A first run unpacks the filtered tree, keeps permissions and writes the lock."""
    archive = make_tar({
        "top/Fonts/Makefile": b"all:\n",
        "top/Fonts/bdf2psf": (b"#!/usr/bin/perl\n", 0o755),
        "top/Fonts/bdf/a.bdf": b"A",
        "top/debian/control": b"skipped",
        "top/README": b"skipped",
    })
    web.put("font.tar.gz", archive)
    assert run(repo, [entry(web, include=["Fonts/**"])]) == 0
    dest = repo / "sources" / "font"
    assert files_under(dest) == ["Fonts/Makefile", "Fonts/bdf/a.bdf", "Fonts/bdf2psf"]
    assert (dest / "Fonts" / "bdf2psf").stat().st_mode & 0o111
    assert not (dest / "Fonts" / "Makefile").stat().st_mode & 0o111
    lock = json.loads((repo / "sources" / "sources.lock.json").read_text())
    assert lock["sources"]["font"]["sha256"] == hashlib.sha256(archive).hexdigest()
    assert outputs(repo) == {"changed": "true", "changed_sources": "font", "failed_sources": ""}


def test_second_run_is_unchanged_and_leaves_files_alone(repo: Path, web: FileServer) -> None:
    """When nothing changed upstream the tree and the lock are not touched."""
    web.put("font.tar.gz", make_tar({"t/a.txt": b"one"}))
    assert run(repo, [entry(web)]) == 0
    target = repo / "sources" / "font" / "a.txt"
    before = target.stat().st_mtime_ns
    lock_before = (repo / "sources" / "sources.lock.json").read_text()
    assert run(repo, [entry(web)]) == 0
    assert target.stat().st_mtime_ns == before
    assert (repo / "sources" / "sources.lock.json").read_text() == lock_before
    assert outputs(repo)["changed"] == "false"


def test_upstream_change_replaces_tree_and_removes_old_files(
    repo: Path, web: FileServer
) -> None:
    """A changed archive replaces the whole tree, including deleting vanished files."""
    web.put("font.tar.gz", make_tar({"t/keep.txt": b"v1", "t/old.txt": b"gone soon"}))
    run(repo, [entry(web)])
    web.put("font.tar.gz", make_tar({"t/keep.txt": b"v2", "t/new.txt": b"new"}))
    assert run(repo, [entry(web)]) == 0
    dest = repo / "sources" / "font"
    assert (dest / "keep.txt").read_text() == "v2"
    assert (dest / "new.txt").exists()
    assert not (dest / "old.txt").exists()
    assert outputs(repo) == {"changed": "true", "changed_sources": "font", "failed_sources": ""}


def test_version_bump_fetches_the_new_url(repo: Path, web: FileServer) -> None:
    """Changing ``version`` in the manifest downloads the new release."""
    web.put("font-1.0.tar.gz", make_tar({"t/f.txt": b"1.0"}))
    web.put("font-1.1.tar.gz", make_tar({"t/f.txt": b"1.1", "t/extra.txt": b"x"}))
    url = {"url": web.url("font-{version}.tar.gz")}
    run(repo, [entry(web, version="1.0", **url)])
    assert (repo / "sources" / "font" / "f.txt").read_text() == "1.0"
    run(repo, [entry(web, version="1.1", **url)])
    assert (repo / "sources" / "font" / "f.txt").read_text() == "1.1"
    lock = json.loads((repo / "sources" / "sources.lock.json").read_text())
    assert lock["sources"]["font"]["version"] == "1.1"
    assert lock["sources"]["font"]["url"].endswith("/font-1.1.tar.gz")


def test_supported_archive_formats(repo: Path, web: FileServer) -> None:
    """tar.xz, tar.bz2 and zip archives are all unpacked."""
    web.put("a.tar.xz", make_tar({"t/f": b"xz"}, "w:xz"))
    web.put("b.tar.bz2", make_tar({"t/f": b"bz2"}, "w:bz2"))
    web.put("c.zip", make_zip({"t/f": b"zip"}))
    sources = [
        {"name": name, "url": web.url(file), "dest": f"sources/{name}", "strip_components": 1}
        for name, file in (("xz", "a.tar.xz"), ("bz2", "b.tar.bz2"), ("zip", "c.zip"))
    ]
    assert run(repo, sources) == 0
    texts = [(repo / "sources" / name / "f").read_text() for name in ("xz", "bz2", "zip")]
    assert texts == ["xz", "bz2", "zip"]


def test_strip_components_zero_keeps_top_level(repo: Path, web: FileServer) -> None:
    """Without stripping, ``include`` globs apply to the archive's own paths."""
    web.put("font.tar.gz", make_tar({"8x13.bdf": b"x", "sub/9x15.bdf": b"y"}))
    run(repo, [entry(web, strip_components=0, include=["*.bdf"])])
    assert files_under(repo / "sources" / "font") == ["8x13.bdf"]


def test_no_matching_files_keeps_the_old_tree(repo: Path, web: FileServer) -> None:
    """An ``include`` that matches nothing fails instead of wiping the destination."""
    web.put("font.tar.gz", make_tar({"t/a.txt": b"original"}))
    run(repo, [entry(web)])
    web.put("font.tar.gz", make_tar({"t/b.txt": b"changed upstream"}))
    assert run(repo, [entry(web, include=["nothing/**"])]) == 1
    assert (repo / "sources" / "font" / "a.txt").read_text() == "original"
    assert outputs(repo)["failed_sources"] == "font"


def test_keep_archive(repo: Path, web: FileServer) -> None:
    """``keep_archive`` stores the downloaded archive next to the unpacked files."""
    web.put("font.tar.gz", make_tar({"t/a.txt": b"x"}))
    run(repo, [entry(web, keep_archive=True)])
    assert (repo / "sources" / "font" / ".archive" / "font.tar.gz").is_file()


# --------------------------------------------------------------------------
# safety, failures, options
# --------------------------------------------------------------------------


def test_path_traversal_is_rejected_and_other_sources_still_run(
    repo: Path, web: FileServer
) -> None:
    """An archive that tries to escape is refused; the other sources are still processed."""
    web.put("evil.tar.gz", make_tar({"t/ok.txt": b"ok", "t/../../escape.txt": b"nope"}))
    web.put("good.tar.gz", make_tar({"t/ok.txt": b"fine"}))
    sources = [
        {"name": n, "url": web.url(f"{n}.tar.gz"), "dest": f"sources/{n}", "strip_components": 1}
        for n in ("evil", "good")
    ]
    assert run(repo, sources) == 1
    assert not (repo / "sources" / "evil").exists()
    assert not (repo.parent / "escape.txt").exists()
    assert (repo / "sources" / "good" / "ok.txt").read_text() == "fine"
    assert outputs(repo) == {
        "changed": "true",
        "changed_sources": "good",
        "failed_sources": "evil",
    }


def test_symlinks_inside_the_tree_are_kept_and_escaping_ones_rejected(
    repo: Path, web: FileServer
) -> None:
    """Relative symlinks inside the tree survive; ones pointing out of it are refused."""
    web.put("ok.tar.gz", make_tar({"t/real.txt": b"r", "t/link.txt": ("symlink", "real.txt")}))
    web.put("bad.tar.gz", make_tar({"t/link": ("symlink", "../../outside")}))
    web.put("abs.tar.gz", make_tar({"t/link": ("symlink", "/etc/passwd")}))
    sources = [
        {"name": n, "url": web.url(f"{n}.tar.gz"), "dest": f"sources/{n}", "strip_components": 1}
        for n in ("ok", "bad", "abs")
    ]
    assert run(repo, sources) == 1
    link = repo / "sources" / "ok" / "link.txt"
    assert link.is_symlink()
    assert link.read_text() == "r"
    assert not (repo / "sources" / "bad").exists()
    assert not (repo / "sources" / "abs").exists()


def test_dangling_symlink_is_reported(
    repo: Path, web: FileServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A symlink whose target was filtered out is reported."""
    members = {"t/COPYRIGHT": ("symlink", "debian/copyright"), "t/keep": b"x"}
    web.put("font.tar.gz", make_tar(members))
    assert run(repo, [entry(web, include=["COPYRIGHT", "keep"])]) == 0
    assert "dangling symlink COPYRIGHT -> debian/copyright" in capsys.readouterr().out


def test_html_response_is_refused_with_a_clear_message(
    repo: Path, web: FileServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A server that answers with an HTML page instead of the archive is reported as such."""
    web.put("font.tar.gz", b"<!doctype html><title>blocked</title>", "text/html; charset=utf-8")
    assert run(repo, [entry(web)]) == 1
    err = capsys.readouterr().err
    assert "HTML page" in err
    assert "filter" in err
    assert not (repo / "sources" / "font").exists()


def test_http_error_fails_only_that_source(
    repo: Path, web: FileServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 404 fails one source and the next one is still processed."""
    web.put("good.tar.gz", make_tar({"t/f": b"x"}))
    sources = [
        {"name": "missing", "url": web.url("nope.tar.gz"), "dest": "sources/missing"},
        {"name": "good", "url": web.url("good.tar.gz"), "dest": "sources/good",
         "strip_components": 1},
    ]
    assert run(repo, sources) == 1
    assert "404" in capsys.readouterr().err
    assert (repo / "sources" / "good" / "f").exists()


def test_disabled_entries_are_never_contacted(repo: Path, web: FileServer) -> None:
    """``enabled: false`` entries are skipped entirely."""
    web.put("font.tar.gz", make_tar({"t/f": b"x"}))
    off = entry(web, name="off", dest="sources/off", enabled=False, url=web.url("off.tar.gz"))
    assert run(repo, [entry(web), off]) == 0
    assert all(path != "/off.tar.gz" for path, _ in web.requests)
    assert not (repo / "sources" / "off").exists()


def test_user_agent_default_and_override(repo: Path, web: FileServer) -> None:
    """Manifest mode sends a non-browser User-Agent unless an entry overrides it."""
    web.put("font.tar.gz", make_tar({"t/f": b"x"}))
    web.put("other.tar.gz", make_tar({"t/f": b"x"}))
    other = entry(
        web, name="other", dest="sources/other", url=web.url("other.tar.gz"), user_agent="custom/9"
    )
    run(repo, [entry(web), other])
    agents = dict(web.requests)
    assert agents["/font.tar.gz"] == sources_sync.MANIFEST_USER_AGENT
    assert "Mozilla" not in agents["/font.tar.gz"]  # SourceForge serves HTML to browsers
    assert agents["/other.tar.gz"] == "custom/9"


def test_only_and_force(repo: Path, web: FileServer, capsys: pytest.CaptureFixture[str]) -> None:
    """``--only`` limits the run and ``--force`` re-extracts an unchanged source."""
    web.put("a.tar.gz", make_tar({"t/f": b"a"}))
    web.put("b.tar.gz", make_tar({"t/f": b"b"}))
    sources = [
        {"name": n, "url": web.url(f"{n}.tar.gz"), "dest": f"sources/{n}", "strip_components": 1}
        for n in ("a", "b")
    ]
    assert run(repo, sources, "--only", "a") == 0
    assert (repo / "sources" / "a").exists()
    assert not (repo / "sources" / "b").exists()
    assert run(repo, sources, "--only", "nope") == 1
    assert "not in the manifest" in capsys.readouterr().err
    assert run(repo, sources, "--only", "a", "--force") == 0
    assert outputs(repo)["changed"] == "true"


def test_dest_replaced_even_if_it_was_a_file(repo: Path, web: FileServer) -> None:
    """A stray file at the destination path is replaced by the unpacked directory."""
    (repo / "sources").mkdir()
    (repo / "sources" / "font").write_text("in the way")
    web.put("font.tar.gz", make_tar({"t/f": b"x"}))
    assert run(repo, [entry(web)]) == 0
    assert (repo / "sources" / "font" / "f").exists()


def test_cli_rules() -> None:
    """Manifest mode and single-file mode cannot be mixed."""
    parse = dependencyDownloader.parse_args
    with pytest.raises(SystemExit):
        parse(["--sources", "m.json", "https://x/y.tgz", "out"])
    with pytest.raises(SystemExit):
        parse(["--force", "https://x/y.tgz", "out"])
    with pytest.raises(SystemExit):
        parse([])
    assert parse(["--sources", "m.json"]).sources == "m.json"


def test_single_file_mode_still_works(
    tmp_path: Path, web: FileServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The original ``<url> <output-dir>`` mode creates, keeps and updates a file."""
    out = tmp_path / "gh.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    url, res = web.url("llvm.sh"), str(tmp_path / "res")
    web.put("llvm.sh", b"#!/bin/sh\n")
    assert dependencyDownloader.main([url, res]) == 0
    assert (tmp_path / "res" / "llvm.sh").read_bytes() == b"#!/bin/sh\n"
    assert dependencyDownloader.main([url, res]) == 0
    web.put("llvm.sh", b"#!/bin/sh\necho new\n")
    assert dependencyDownloader.main([url, res]) == 0
    values = [line.split("=")[1] for line in out.read_text().splitlines() if "changed=" in line]
    assert values == ["true", "false", "true"]
