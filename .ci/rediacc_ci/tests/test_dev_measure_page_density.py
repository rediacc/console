"""`rediacc_ci.dev.measure_page_density`, the port of `packages/www/scripts/measure-page-density.sh`.

THE BASH WAS RETIRED WITH THIS FILE (PLAN-retire-bash-oracles B5, W10). It is a manual harness that needs a built `packages/www/dist` and a real browser, so what is pinned here is what it must never get wrong, driven against a throwaway `dist` and a stub `agent-browser`: the three verifications (the listening pid is ours, the served page links an asset present in dist, every page clears the DOM-node floor) each refuse on a planted fault, the viewport height is read back and never assumed, and the exit status of `agent-browser open` does not decide control flow. Each deliberate delta from the bash (Rule T) has a case that fails on the old behaviour.
"""

from __future__ import annotations

import os
import socket
import stat
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.dev import measure_page_density as mpd

if TYPE_CHECKING:
    import pathlib

STUB = """#!/bin/sh
case "$1" in
  open) echo "opened $2" >> "$STUB_LOG"; exit "${STUB_OPEN_RC:-1}" ;;
  eval)
    printf '{"vph":%s,"vpw":1280,"h":%s,"words":%s,"atoms":7,"nodes":%s}\\n' \\
      "${STUB_VPH:-900}" "${STUB_H:-2700}" "${STUB_WORDS:-123}" "${STUB_NODES:-400}" ;;
esac
"""


def _site(tmp_path: pathlib.Path, asset: bool = True) -> pathlib.Path:
    """A throwaway packages/www with a dist whose /en/ links an asset, and three solution pages."""
    www = tmp_path / "www"
    (www / "dist" / "en").mkdir(parents=True)
    (www / "dist" / "assets").mkdir()
    (www / "dist" / "en" / "index.html").write_text(
        '<html><link rel="stylesheet" href="/assets/app.abc123.css"></html>', encoding="utf-8"
    )
    if asset:
        (www / "dist" / "assets" / "app.abc123.css").write_text("x{}", encoding="utf-8")
    solutions = www / "src" / "pages" / "[lang]" / "solutions"
    solutions.mkdir(parents=True)
    for name in ("index", "beta", "alpha"):
        (solutions / ("%s.astro" % name)).write_text("---\n---\n", encoding="utf-8")
    return www


@pytest.fixture
def browser(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "agent-browser"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", "%s:/usr/local/bin:/usr/bin:/bin" % bindir)
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "stub.log"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
    return bindir


# ---------------------------------------------------------------------------- the run


@pytest.mark.usefixtures("browser")
def test_full_run_writes_one_row_per_page_and_ignores_open_exit_status(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The stub's `open` exits 1, as the real one does with redirected stdout; the run must carry on."""
    www = _site(tmp_path)
    out = tmp_path / "out.csv"
    assert mpd.main([str(out)], www=www) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "slug,height,screens,words,atoms,nodes"
    assert [line.split(",")[0] for line in lines[1:]] == [
        "alpha",
        "beta",
        "home",
        "for-devops",
        "for-ctos",
        "for-ceos",
        "for-ai-agents",
    ]
    assert lines[1] == "alpha,2700,3.0,123,7,400"
    printed = capsys.readouterr().out
    assert "wrote %s" % out in printed
    assert "slug" in printed.splitlines()[1]
    opened = (tmp_path / "stub.log").read_text(encoding="utf-8").splitlines()
    assert opened[0].startswith("opened http://localhost:")
    assert opened[0].endswith("/en/solutions/alpha/")


@pytest.mark.usefixtures("browser")
def test_screens_divide_by_the_viewport_read_back_not_the_one_asked_for(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`open --viewport` is ignored by the real tool and reports 577; dividing by the requested 900 would lie."""
    monkeypatch.setenv("STUB_VPH", "577")
    monkeypatch.setenv("STUB_H", "2885")
    www = _site(tmp_path)
    out = tmp_path / "o.csv"
    assert mpd.main([str(out)], www=www) == 0
    assert out.read_text(encoding="utf-8").splitlines()[1].startswith("alpha,2885,5.0,")


# ---------------------------------------------------------------------------- verification 3: the floor


@pytest.mark.usefixtures("browser")
def test_a_page_under_the_node_floor_fails_the_run(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STUB_NODES", "5")
    assert mpd.main([str(tmp_path / "o.csv")], www=_site(tmp_path)) == 1
    err = capsys.readouterr().err
    assert "FLOOR: alpha has 5 DOM nodes (< 50). That is not a page." in err


def test_an_eval_with_no_json_is_the_floor_failure(
    tmp_path: pathlib.Path, browser: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (browser / "agent-browser").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert mpd.main([str(tmp_path / "o.csv")], www=_site(tmp_path)) == 1
    assert "FLOOR: alpha has no DOM nodes" in capsys.readouterr().err


@pytest.mark.usefixtures("browser")
def test_a_tiny_reported_viewport_is_refused(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STUB_VPH", "100")
    assert mpd.main([str(tmp_path / "o.csv")], www=_site(tmp_path)) == 1
    assert "VIEWPORT: alpha reported innerHeight=100" in capsys.readouterr().err


def test_rows_already_measured_survive_a_later_failure(
    tmp_path: pathlib.Path, browser: pathlib.Path
) -> None:
    """Rule T: the bash left the header alone when it died; the port rewrites the CSV per page."""
    (browser / "agent-browser").write_text(
        STUB.replace(
            'printf \'{"vph"',
            'n=$(wc -l < "$STUB_LOG"); [ "$n" -ge 3 ] && STUB_NODES=1\n    printf \'{"vph"',
        ),
        encoding="utf-8",
    )
    out = tmp_path / "o.csv"
    assert mpd.main([str(out)], www=_site(tmp_path)) == 1
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3


# ---------------------------------------------------------------------------- verification 2: the asset


@pytest.mark.usefixtures("browser")
def test_a_served_asset_missing_from_dist_is_refused(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert mpd.main([str(tmp_path / "o.csv")], www=_site(tmp_path, asset=False)) == 1
    assert "is not in dist/; reading someone else's build" in capsys.readouterr().err


@pytest.mark.usefixtures("browser")
def test_a_page_with_no_hashed_asset_is_refused_not_passed(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    www = _site(tmp_path)
    (www / "dist" / "en" / "index.html").write_text("<html>no assets</html>", encoding="utf-8")
    assert mpd.main([str(tmp_path / "o.csv")], www=www) == 1
    assert "no hashed asset in the served HTML" in capsys.readouterr().err


# ---------------------------------------------------------------------------- verification 1: the pid


@pytest.mark.usefixtures("browser")
def test_a_squatter_on_the_port_is_refused(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Someone else already listens where the harness would serve; its bytes must never be measured."""
    squatter = socket.socket()
    squatter.bind(("127.0.0.1", 0))
    squatter.listen()
    port = squatter.getsockname()[1]
    try:
        monkeypatch.setattr(mpd, "pick_port", lambda: port)
        assert mpd.main([str(tmp_path / "o.csv")], www=_site(tmp_path)) == 1
        assert "is not served by our pid" in capsys.readouterr().err
    finally:
        squatter.close()


def test_listening_pids_finds_this_process_and_nobody_for_a_closed_port() -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    try:
        port = sock.getsockname()[1]
        assert os.getpid() in mpd.listening_pids(port)
    finally:
        sock.close()
    assert mpd.listening_pids(port) == set()


def test_listening_pids_ignores_connected_sockets_on_the_port() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    try:
        assert mpd.listening_pids(port) == {os.getpid()}
    finally:
        client.close()
        server.close()


# ---------------------------------------------------------------------------- the rest


def test_missing_dist_and_missing_browser_are_named(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert mpd.main([str(tmp_path / "o.csv")], www=empty) == 1
    assert "no dist/. Run: npm run build -w @rediacc/www" in capsys.readouterr().err

    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    assert mpd.main([str(tmp_path / "o.csv")], www=_site(tmp_path)) == 1
    assert "agent-browser is not on PATH" in capsys.readouterr().err


@pytest.mark.usefixtures("browser")
def test_the_server_is_stopped_after_the_run(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ports: list[int] = []
    real = mpd.pick_port

    def spy() -> int:
        port = real()
        ports.append(port)
        return port

    monkeypatch.setattr(mpd, "pick_port", spy)
    assert mpd.main([str(tmp_path / "o.csv")], www=_site(tmp_path)) == 0
    assert mpd.listening_pids(ports[0]) == set()


def test_parse_eval_handles_quoted_and_noisy_output() -> None:
    raw = (
        '"{\\"vph\\":900,\\"vpw\\":1280,\\"h\\":1800,\\"words\\":10,\\"atoms\\":2,\\"nodes\\":99}"'
    )
    data = mpd.parse_eval(raw)
    assert data is not None
    assert (data["h"], data["vph"], data["nodes"]) == (1800, 900, 99)
    assert mpd.parse_eval("nothing here") is None
    assert mpd.parse_eval('{"h":1}') is None
    assert mpd.parse_eval("{not json}") is None


def test_h_is_not_confused_with_vph() -> None:
    """The reason the bash parses JSON: a grep for `h:NNN` also matches the h inside vph."""
    data = mpd.parse_eval('{"vph":577,"vpw":1280,"h":2885,"words":1,"atoms":1,"nodes":60}')
    assert data is not None
    assert data["h"] == 2885


def test_page_list_orders_solutions_then_home_and_personas(tmp_path: pathlib.Path) -> None:
    pages = mpd.page_list(_site(tmp_path))
    assert pages[0] == ("/en/solutions/alpha/", "alpha")
    assert pages[2] == ("/en/", "home")
    assert pages[-1] == ("/en/for-ai-agents/", "for-ai-agents")
    assert all(label != "index" for _, label in pages)


def test_column_table_aligns_like_column_t() -> None:
    table = mpd.column_table("slug,height\nalpha,10\nb,2000\n")
    assert table == "slug   height\nalpha  10\nb      2000"


def test_runs_as_a_module_with_the_documented_command() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", "import rediacc_ci.dev.measure_page_density"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(mpd.paths.repo_root() / ".ci")},
    )
    assert proc.returncode == 0, proc.stderr
