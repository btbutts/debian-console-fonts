"""Tests for .github/actions-scripts/dependencyDownloader.py (manifest mode).

Everything runs against a throwaway HTTP server on localhost; no network.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
import threading
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "actions-scripts" / "dependencyDownloader.py"
spec = importlib.util.spec_from_file_location("dependencyDownloader", SCRIPT)
dd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dd  # dataclasses looks the module up while it executes
spec.loader.exec_module(dd)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def make_tar(members: dict, mode: str = "w:gz") -> bytes:
    """members: name -> bytes | (bytes, mode) | ('symlink', target)."""
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


def make_zip(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as bundle:
        for name, data in members.items():
            bundle.writestr(name, data)
    return buf.getvalue()


class Server:
    def __init__(self) -> None:
        self.routes: dict[str, tuple[bytes, str]] = {}
        self.requests: list[tuple[str, str]] = []

    def put(self, path: str, body: bytes, ctype: str = "application/octet-stream") -> None:
        self.routes[path] = (body, ctype)


@contextmanager
def serve():
    state = Server()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            state.requests.append((self.path, self.headers.get("User-Agent", "")))
            if self.path not in state.routes:
                self.send_error(404)
                return
            body, ctype = state.routes[self.path]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state.base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield state
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture(autouse=True)
def _no_truststore(monkeypatch):
    monkeypatch.setattr(dd, "use_system_trust_store", lambda: None)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    out = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def run(root: Path, sources: list, *extra: str) -> int:
    (root / "sources.json").write_text(json.dumps({"sources": sources}), encoding="utf-8")
    return dd.main(["--sources", "sources.json", "--root", str(root), *extra])


def outputs(root: Path) -> dict:
    result = {}
    for line in (root.parent / "github_output.txt").read_text().splitlines():
        key, _, value = line.partition("=")
        result[key] = value  # last write wins, like Actions
    return result


def entry(base: str, **overrides) -> dict:
    data = {"name": "font", "url": f"{base}/font.tar.gz", "dest": "sources/font", "strip_components": 1}
    data.update(overrides)
    return data


# --------------------------------------------------------------------------
# placeholders, globs, manifest validation
# --------------------------------------------------------------------------


def test_version_fields():
    assert dd.version_fields("4.49.1") == {
        "version": "4.49.1", "major": "4", "minor": "49", "patch": "1", "major_minor": "4.49",
    }
    assert dd.version_fields("2.37")["major_minor"] == "2.37"
    odd = dd.version_fields("1.242~deb13u1")
    assert odd["major_minor"] == "1.242" and "patch" not in odd


def test_expand_placeholders():
    url = "https://x/terminus-font-{major_minor}/terminus-font-{version}.tar.gz"
    assert dd.expand_placeholders(url, "4.49.1", "t") == "https://x/terminus-font-4.49/terminus-font-4.49.1.tar.gz"
    assert dd.expand_placeholders("https://x/plain.tgz", None, "t") == "https://x/plain.tgz"
    with pytest.raises(dd.SourceError, match="no 'version'"):
        dd.expand_placeholders(url, None, "t")
    with pytest.raises(dd.SourceError, match="not available"):
        dd.expand_placeholders("https://x/{patch}", "2.37", "t")
    with pytest.raises(dd.SourceError, match="not available"):
        dd.expand_placeholders("https://x/{bogus}", "1.0.0", "t")


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
def test_glob_matching(pattern, path, expected):
    assert dd._matches(path, [(pattern, dd._glob_to_regex(pattern))]) is expected


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
    ],
)
def test_manifest_validation(tmp_path, bad, message):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"sources": [bad]}))
    with pytest.raises(dd.SourceError, match=message):
        dd.load_sources(path)


def test_manifest_rejects_duplicates_and_nested_dests(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps([{"name": "a", "url": "u", "dest": "s/a"}, {"name": "a", "url": "u", "dest": "s/b"}]))
    with pytest.raises(dd.SourceError, match="duplicate"):
        dd.load_sources(path)
    path.write_text(json.dumps([{"name": "a", "url": "u", "dest": "s/a"}, {"name": "b", "url": "u", "dest": "s/a/inner"}]))
    with pytest.raises(dd.SourceError, match="inside"):
        dd.load_sources(path)


# --------------------------------------------------------------------------
# download, extract, lock
# --------------------------------------------------------------------------


def test_first_run_extracts_filters_and_locks(repo):
    archive = make_tar({
        "top/Fonts/Makefile": b"all:\n",
        "top/Fonts/bdf2psf": (b"#!/usr/bin/perl\n", 0o755),
        "top/Fonts/bdf/a.bdf": b"A",
        "top/debian/control": b"skipped",
        "top/README": b"skipped",
    })
    with serve() as srv:
        srv.put("/font.tar.gz", archive)
        assert run(repo, [entry(srv.base, include=["Fonts/**"])]) == 0
    dest = repo / "sources" / "font"
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == [
        "Fonts/Makefile", "Fonts/bdf/a.bdf", "Fonts/bdf2psf",
    ]
    assert (dest / "Fonts" / "bdf2psf").stat().st_mode & 0o111
    assert not (dest / "Fonts" / "Makefile").stat().st_mode & 0o111
    lock = json.loads((repo / "sources" / "sources.lock.json").read_text())
    assert lock["sources"]["font"]["sha256"] == dd.hashlib.sha256(archive).hexdigest()
    assert outputs(repo) == {"changed": "true", "changed_sources": "font", "failed_sources": ""}


def test_second_run_is_unchanged_and_leaves_files_alone(repo):
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"t/a.txt": b"one"}))
        assert run(repo, [entry(srv.base)]) == 0
        target = repo / "sources" / "font" / "a.txt"
        before = target.stat().st_mtime_ns
        lock_before = (repo / "sources" / "sources.lock.json").read_text()
        assert run(repo, [entry(srv.base)]) == 0
    assert target.stat().st_mtime_ns == before
    assert (repo / "sources" / "sources.lock.json").read_text() == lock_before
    assert outputs(repo)["changed"] == "false"


def test_upstream_change_replaces_tree_and_removes_old_files(repo):
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"t/keep.txt": b"v1", "t/old.txt": b"gone soon"}))
        run(repo, [entry(srv.base)])
        srv.put("/font.tar.gz", make_tar({"t/keep.txt": b"v2", "t/new.txt": b"new"}))
        assert run(repo, [entry(srv.base)]) == 0
    dest = repo / "sources" / "font"
    assert (dest / "keep.txt").read_text() == "v2"
    assert (dest / "new.txt").exists() and not (dest / "old.txt").exists()
    assert outputs(repo) == {"changed": "true", "changed_sources": "font", "failed_sources": ""}


def test_version_bump_fetches_the_new_url(repo):
    with serve() as srv:
        srv.put("/font-1.0.tar.gz", make_tar({"t/f.txt": b"1.0"}))
        srv.put("/font-1.1.tar.gz", make_tar({"t/f.txt": b"1.1", "t/extra.txt": b"x"}))
        base = {"url": f"{srv.base}/font-{{version}}.tar.gz"}
        run(repo, [entry(srv.base, version="1.0", **base)])
        assert (repo / "sources" / "font" / "f.txt").read_text() == "1.0"
        run(repo, [entry(srv.base, version="1.1", **base)])
    assert (repo / "sources" / "font" / "f.txt").read_text() == "1.1"
    lock = json.loads((repo / "sources" / "sources.lock.json").read_text())
    assert lock["sources"]["font"]["version"] == "1.1"
    assert lock["sources"]["font"]["url"].endswith("/font-1.1.tar.gz")


def test_supported_archive_formats(repo):
    with serve() as srv:
        srv.put("/a.tar.xz", make_tar({"t/f": b"xz"}, "w:xz"))
        srv.put("/b.tar.bz2", make_tar({"t/f": b"bz2"}, "w:bz2"))
        srv.put("/c.zip", make_zip({"t/f": b"zip"}))
        sources = [
            {"name": "xz", "url": f"{srv.base}/a.tar.xz", "dest": "sources/xz", "strip_components": 1},
            {"name": "bz2", "url": f"{srv.base}/b.tar.bz2", "dest": "sources/bz2", "strip_components": 1},
            {"name": "zip", "url": f"{srv.base}/c.zip", "dest": "sources/zip", "strip_components": 1},
        ]
        assert run(repo, sources) == 0
    assert [(repo / "sources" / n / "f").read_text() for n in ("xz", "bz2", "zip")] == ["xz", "bz2", "zip"]


def test_strip_components_zero_keeps_top_level(repo):
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"8x13.bdf": b"x", "sub/9x15.bdf": b"y"}))
        run(repo, [entry(srv.base, strip_components=0, include=["*.bdf"])])
    assert sorted(p.name for p in (repo / "sources" / "font").rglob("*") if p.is_file()) == ["8x13.bdf"]


def test_no_matching_files_keeps_the_old_tree(repo):
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"t/a.txt": b"original"}))
        run(repo, [entry(srv.base)])
        srv.put("/font.tar.gz", make_tar({"t/b.txt": b"changed upstream"}))
        assert run(repo, [entry(srv.base, include=["nothing/**"])]) == 1
    assert (repo / "sources" / "font" / "a.txt").read_text() == "original"
    assert outputs(repo)["failed_sources"] == "font"


def test_keep_archive(repo):
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"t/a.txt": b"x"}))
        run(repo, [entry(srv.base, keep_archive=True)])
    assert (repo / "sources" / "font" / ".archive" / "font.tar.gz").is_file()


# --------------------------------------------------------------------------
# safety, failures, options
# --------------------------------------------------------------------------


def test_path_traversal_is_rejected_and_other_sources_still_run(repo):
    with serve() as srv:
        srv.put("/evil.tar.gz", make_tar({"t/ok.txt": b"ok", "t/../../escape.txt": b"nope"}))
        srv.put("/good.tar.gz", make_tar({"t/ok.txt": b"fine"}))
        sources = [
            {"name": "evil", "url": f"{srv.base}/evil.tar.gz", "dest": "sources/evil", "strip_components": 1},
            {"name": "good", "url": f"{srv.base}/good.tar.gz", "dest": "sources/good", "strip_components": 1},
        ]
        assert run(repo, sources) == 1
    assert not (repo / "sources" / "evil").exists() and not (repo.parent / "escape.txt").exists()
    assert (repo / "sources" / "good" / "ok.txt").read_text() == "fine"
    assert outputs(repo) == {"changed": "true", "changed_sources": "good", "failed_sources": "evil"}


def test_symlinks_inside_the_tree_are_kept_and_escaping_ones_rejected(repo):
    with serve() as srv:
        srv.put("/ok.tar.gz", make_tar({"t/real.txt": b"r", "t/link.txt": ("symlink", "real.txt")}))
        srv.put("/bad.tar.gz", make_tar({"t/link": ("symlink", "../../outside")}))
        srv.put("/abs.tar.gz", make_tar({"t/link": ("symlink", "/etc/passwd")}))
        sources = [
            {"name": n, "url": f"{srv.base}/{n}.tar.gz", "dest": f"sources/{n}", "strip_components": 1}
            for n in ("ok", "bad", "abs")
        ]
        assert run(repo, sources) == 1
    assert (repo / "sources" / "ok" / "link.txt").is_symlink()
    assert (repo / "sources" / "ok" / "link.txt").read_text() == "r"
    assert not (repo / "sources" / "bad").exists() and not (repo / "sources" / "abs").exists()


def test_html_response_is_refused_with_a_clear_message(repo, capsys):
    with serve() as srv:
        srv.put("/font.tar.gz", b"<!doctype html><title>blocked</title>", "text/html; charset=utf-8")
        assert run(repo, [entry(srv.base)]) == 1
    err = capsys.readouterr().err
    assert "HTML page" in err and "filter" in err
    assert not (repo / "sources" / "font").exists()


def test_http_error_fails_only_that_source(repo, capsys):
    with serve() as srv:
        srv.put("/good.tar.gz", make_tar({"t/f": b"x"}))
        sources = [
            {"name": "missing", "url": f"{srv.base}/nope.tar.gz", "dest": "sources/missing"},
            {"name": "good", "url": f"{srv.base}/good.tar.gz", "dest": "sources/good", "strip_components": 1},
        ]
        assert run(repo, sources) == 1
    assert "404" in capsys.readouterr().err
    assert (repo / "sources" / "good" / "f").exists()


def test_disabled_entries_are_never_contacted(repo):
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"t/f": b"x"}))
        assert run(repo, [entry(srv.base), entry(srv.base, name="off", dest="sources/off", enabled=False, url=f"{srv.base}/off.tar.gz")]) == 0
        assert all(path != "/off.tar.gz" for path, _ in srv.requests)
    assert not (repo / "sources" / "off").exists()


def test_user_agent_default_and_override(repo):
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"t/f": b"x"}))
        srv.put("/other.tar.gz", make_tar({"t/f": b"x"}))
        run(repo, [
            entry(srv.base),
            entry(srv.base, name="other", dest="sources/other", url=f"{srv.base}/other.tar.gz", user_agent="custom/9"),
        ])
        agents = dict(srv.requests)
    assert agents["/font.tar.gz"] == dd.MANIFEST_USER_AGENT
    assert "Mozilla" not in agents["/font.tar.gz"]  # SourceForge serves HTML to browsers
    assert agents["/other.tar.gz"] == "custom/9"


def test_only_and_force(repo, capsys):
    with serve() as srv:
        srv.put("/a.tar.gz", make_tar({"t/f": b"a"}))
        srv.put("/b.tar.gz", make_tar({"t/f": b"b"}))
        sources = [
            {"name": n, "url": f"{srv.base}/{n}.tar.gz", "dest": f"sources/{n}", "strip_components": 1}
            for n in ("a", "b")
        ]
        assert run(repo, sources, "--only", "a") == 0
        assert (repo / "sources" / "a").exists() and not (repo / "sources" / "b").exists()
        assert run(repo, sources, "--only", "nope") == 1
        assert "not in the manifest" in capsys.readouterr().err
        assert run(repo, sources, "--only", "a", "--force") == 0
        assert outputs(repo)["changed"] == "true"


def test_dest_replaced_even_if_it_was_a_file(repo):
    (repo / "sources").mkdir()
    (repo / "sources" / "font").write_text("in the way")
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"t/f": b"x"}))
        assert run(repo, [entry(srv.base)]) == 0
    assert (repo / "sources" / "font" / "f").exists()


def test_cli_rules():
    with pytest.raises(SystemExit):
        dd.parse_args(["--sources", "m.json", "https://x/y.tgz", "out"])
    with pytest.raises(SystemExit):
        dd.parse_args(["--force", "https://x/y.tgz", "out"])
    with pytest.raises(SystemExit):
        dd.parse_args([])
    assert dd.parse_args(["--sources", "m.json"]).sources == "m.json"


def test_single_file_mode_still_works(tmp_path, monkeypatch):
    out = tmp_path / "gh.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    with serve() as srv:
        srv.put("/llvm.sh", b"#!/bin/sh\n")
        assert dd.main([f"{srv.base}/llvm.sh", str(tmp_path / "res")]) == 0
        assert (tmp_path / "res" / "llvm.sh").read_bytes() == b"#!/bin/sh\n"
        assert dd.main([f"{srv.base}/llvm.sh", str(tmp_path / "res")]) == 0
        srv.put("/llvm.sh", b"#!/bin/sh\necho new\n")
        assert dd.main([f"{srv.base}/llvm.sh", str(tmp_path / "res")]) == 0
    values = [line.split("=")[1] for line in out.read_text().splitlines() if line.startswith("changed=")]
    assert values == ["true", "false", "true"]


def test_dangling_symlink_is_reported(repo, capsys):
    with serve() as srv:
        srv.put("/font.tar.gz", make_tar({"t/COPYRIGHT": ("symlink", "debian/copyright"), "t/keep": b"x"}))
        assert run(repo, [entry(srv.base, include=["COPYRIGHT", "keep"])]) == 0
    assert "dangling symlink COPYRIGHT -> debian/copyright" in capsys.readouterr().out
