"""`rediacc_ci.deploy.wait_for_preview_worker` against its bash twin.

THE STUB IS THE SAME TECHNIQUE `.ci/scripts/test/gates/test-preview-readiness.sh` ALREADY USES, ported from a Node one-off to a small `http.server` here so both sides of the differential can point at it: `/health` always answers 200, `/server-info` flaps according to `mode` (`steady` always good, `flap` good on one probe in three so the streak never reaches 2, `late` cold for the
first three probes then steady). Nothing here is a fake Cloudflare Worker or a real network call -- it is a loopback HTTP server this process owns and tears down.

EACH SIDE GETS ITS OWN FRESH SERVER INSTANCE, restarted between the bash run and the python run, because the flap/late counters are per-server state keyed on request order: reusing one server across both sides would let whichever side runs SECOND see a different sequence of good/bad answers than the side that ran first, which is a test artifact, not a real divergence.

`PROBE_INTERVAL_SECONDS=0.02` and `MAX_ATTEMPTS=9`, the same budget the bash
gate test uses, so this file runs in well under a second per case.
"""

from __future__ import annotations

import http.server
import pathlib
import threading

from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/deploy/wait-for-preview-worker.sh"
MODULE = "wait_for_preview_worker"

GOOD_BODY = b'{"e2e":{"keys":[{"keyId":"v1","publicKeySpki":"AAAA"}]}}'
COLD_BODY = b'{"error":"cold"}'
# The exact counterexample the twin's own header names: `"keys"` is present (private/account/src/app.ts unconditionally emits the key) even when the array is EMPTY, which is the body a mis-grepped check would wrongly accept.
EMPTY_KEYS_BODY = b'{"e2e":{"keys":[]}}'


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        mode = self.server.mode  # type: ignore[attr-defined]
        if self.path.endswith("/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        if self.path.endswith("/server-info"):
            self.server.n += 1  # type: ignore[attr-defined]
            n = self.server.n  # type: ignore[attr-defined]
            if mode == "steady":
                good = True
            elif mode == "flap":
                good = n % 3 == 1
            elif mode == "emptykeys":
                good = None  # always 200, never usable -- see EMPTY_KEYS_BODY
            else:  # "late": cold for the first 3, steady after
                good = n > 3
            if mode == "emptykeys":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(EMPTY_KEYS_BODY)
            elif good:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(GOOD_BODY)
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(COLD_BODY)
            return
        self.send_response(404)
        self.end_headers()


def _start_stub(mode: str) -> tuple[http.server.HTTPServer, threading.Thread]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    server.mode = mode  # type: ignore[attr-defined]
    server.n = 0  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_stub(server: http.server.HTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


_BUDGET = {"MAX_ATTEMPTS": "9", "PROBE_INTERVAL_SECONDS": "0.02"}


def probe(mode: str, **env_extra: str) -> tuple[int, str, str]:
    """Run the BASH twin against a fresh stub of the given mode. Returns streams."""
    server, thread = _start_stub(mode)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        env = diff.env_for(PREVIEW_URL_OVERRIDE=url, **_BUDGET, **env_extra)
        return diff.bash_streams("bash %s" % TWIN, env=env, timeout=30)
    finally:
        _stop_stub(server, thread)


def probe_new(mode: str, **env_extra: str) -> tuple[int, str, str]:
    """Run the PYTHON port against a fresh stub of the given mode. Returns streams."""
    server, thread = _start_stub(mode)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        env = diff.env_for(
            PREVIEW_URL_OVERRIDE=url,
            **_BUDGET,
            **env_extra,
            PYTHONPATH=".ci",
            PYTHONDONTWRITEBYTECODE="1",
        )
        return diff.bash_streams("python3 -m rediacc_ci.deploy.%s" % MODULE, env=env, timeout=30)
    finally:
        _stop_stub(server, thread)


def test_steady_worker_is_ready_on_both_sides() -> None:
    old_rc, _, old_err = probe("steady")
    new_rc, _, new_err = probe_new("steady")
    assert old_rc == 0
    assert new_rc == 0
    assert "consecutive probes" in old_err
    assert "consecutive probes" in new_err


def test_flapping_worker_is_rejected_on_both_sides() -> None:
    old_rc, _, old_err = probe("flap")
    new_rc, _, new_err = probe_new("flap")
    assert old_rc == 1
    assert new_rc == 1
    assert "streak reset" in old_err
    assert "streak reset" in new_err


def test_streak_is_load_bearing_on_both_sides() -> None:
    """Anti-vacuity: REQUIRED_STREAK=1 on the same flapping stub must PASS on
    both sides, or the rejection above proves nothing about the streak."""
    old_rc, _, _ = probe("flap", REQUIRED_STREAK="1")
    new_rc, _, _ = probe_new("flap", REQUIRED_STREAK="1")
    assert old_rc == 0
    assert new_rc == 0


def test_slow_worker_still_becomes_ready_on_both_sides() -> None:
    old_rc, _, _ = probe("late")
    new_rc, _, _ = probe_new("late")
    assert old_rc == 0
    assert new_rc == 0


def test_a_200_with_an_empty_keys_array_is_never_ready_on_either_side() -> None:
    """The counterexample from the twin's own header: `"keys"` is present even when the array is empty, so a check that greps for `"keys"` would wrongly pass. Both sides must exhaust MAX_ATTEMPTS and fail."""
    old_rc, _, _ = probe("emptykeys")
    new_rc, _, _ = probe_new("emptykeys")
    assert old_rc == 1
    assert new_rc == 1


def test_override_needs_no_pr_number(tmp_path: pathlib.Path) -> None:
    del tmp_path
    server, thread = _start_stub("steady")
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        old_env = diff.env_for(PREVIEW_URL_OVERRIDE=url, **_BUDGET, PR_NUMBER=None)
        old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    finally:
        _stop_stub(server, thread)
    server, thread = _start_stub("steady")
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        new_env = diff.env_for(
            PREVIEW_URL_OVERRIDE=url,
            **_BUDGET,
            PR_NUMBER=None,
            PYTHONPATH=".ci",
            PYTHONDONTWRITEBYTECODE="1",
        )
        new = diff.bash_streams("python3 -m rediacc_ci.deploy.%s" % MODULE, env=new_env, timeout=30)
    finally:
        _stop_stub(server, thread)
    assert old[0] == 0
    assert new[0] == 0


def test_pr_number_still_required_without_override_reworded() -> None:
    """Exit code and the identified variable agree; wording does not, and is not supposed to -- see the port's module docstring."""
    old_env = diff.env_for(PR_NUMBER=None, PREVIEW_URL_OVERRIDE=None)
    new_env = diff.env_for(
        PR_NUMBER=None, PREVIEW_URL_OVERRIDE=None, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.deploy.%s" % MODULE, env=new_env, timeout=30)
    assert old[0] == 1
    assert new[0] == 1
    assert "PR_NUMBER" in old[2]
    assert "PR_NUMBER" in new[2]


def test_ci_defaults_are_still_strict() -> None:
    """The knobs are test-only; if the DEFAULTS drift apart, CI silently changes behaviour and every case above would still pass because they all set their own values."""
    twin_src = diff.repo()

    bash_src = (pathlib.Path(twin_src) / TWIN).read_text(encoding="utf-8")
    py_src = (
        pathlib.Path(twin_src) / ".ci" / "rediacc_ci" / "deploy" / "wait_for_preview_worker.py"
    ).read_text(encoding="utf-8")
    assert 'REQUIRED_STREAK="${REQUIRED_STREAK:-3}"' in bash_src
    assert 'REQUIRED_STREAK", "3"' in py_src
    assert 'MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"' in bash_src
    assert 'MAX_ATTEMPTS", "60"' in py_src
    assert 'PROBE_INTERVAL_SECONDS="${PROBE_INTERVAL_SECONDS:-2}"' in bash_src
    assert 'PROBE_INTERVAL_SECONDS", "2"' in py_src
