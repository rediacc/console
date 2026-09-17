"""Differential: `rediacc_ci.infra.ci_start_elite` against its twin
`.ci/scripts/infra/ci-start-elite.sh`.

THE SEAM IS PATH AND THE FIXTURE ROOT, on the `test_infra_ci_stop_elite.py` precedent. Both subjects derive the console root from their own file location (`BASH_SOURCE[0]` / `__file__`), so each case COPIES both of them into a fresh
tree at the right relative depth and runs the copies; driving the tracked files
would point both at this checkout's real `private/elite` and its real `.ci/docker/ci`. `run.sh`, `curl` and `docker` are recording fakes, so the comparison asserts on the ARGV SEQUENCE both sides produced as well as on stdout: a port that printed "Starting Elite services via ./run.sh up" and never ran it would pass a stdout-only comparison.

THE REAL `ci-env.sh` IS COPIED IN AND SOURCED FOR REAL. It is not stubbed, because the whole question this differential answers about the `source` on the twin's :23 is whether the port's `env -0` round trip delivers the same exported set that bash's `source` delivers into the caller's own shell. Every secret it would otherwise GENERATE is pre-set in the fixture environment so that
both
sides take its `${VAR:-...}` arms and the result is deterministic -- a generated
Ed25519 pair differs on every run and would make byte comparison impossible. `test_generated_secrets_path_agrees_on_shape` covers the generating arm separately, on names rather than values.

THE SLEEP IS NULLED IN THE COPIES, AND NOTHING ELSE IS. The health budget is 180s at a 2s interval, so waiting it out on both sides costs six minutes per
timeout case. The obvious shortcut -- shrinking `timeout=180` -- also shrinks
the PROBE COUNT, which is the thing this differential can actually see. So the copies keep every constant and replace only `sleep $interval` / `sleep 0`, which means both sides still perform all 90 probes and the comparison is over the real arithmetic rather than over a miniature of it. `test_the_null_sleep_anchors_still_exist` fails the moment either anchor moves, so the rewrite
can never silently stop applying and leave a case that waits three real minutes, or -- far worse -- passes because both sides skipped the loop.

ONE LINE IS NORMALIZED, and only one: ` load average (1m 5m 15m): ...`. Both sides read the real `/proc/loadavg`, seconds apart, so the numbers legitimately differ. `_normalize` masks the values and `test_the_load_line_is_really_there` asserts both sides printed a well-formed one, so the mask cannot hide its absence.

K=5 LEDGER: `.ci/shadow/w7p6-ci-start-elite.observations.jsonl`, recorded
against a disposable git repo built outside this checkout (this checkout is never clean and `shadow-gate.ts --record` refuses a dirty tree). See that file's own recording notes in the wave report.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "ci-start-elite.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "ci_start_elite.py"
CI_ENV = ROOT / ".ci" / "scripts" / "infra" / "ci-env.sh"

# The health budget as both files really carry it. The copies keep it.
REAL_TIMEOUT = 180

# Pre-set so `ci-env.sh` generates nothing: every generating arm is guarded by
# `[[ -z "${VAR:-}" ]]` or `${VAR:-$(...)}`.
DETERMINISTIC_SECRETS = {
    "ACCOUNT_ED25519_PRIVATE_KEY": "fixture-ed25519-private",
    "ACCOUNT_ED25519_PUBLIC_KEY": "fixture-ed25519-public",
    "ACCOUNT_X25519_PRIVATE_KEY": "fixture-x25519-private",
    "ACCOUNT_X25519_PUBLIC_KEY": "fixture-x25519-public",
    "ACCOUNT_SERVER_API_KEY": "fixture-api-key",
    "ACCOUNT_JWT_SECRET": "fixture-jwt-secret",
    "STRIPE_WEBHOOK_SECRET": "whsec_fixture",
}

FAKE_RUN_SH = """#!/usr/bin/env python3
import sys
LOG = %(log)r
UP_RC = %(up_rc)d
LOGS_RC = %(logs_rc)d
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("run.sh\\t" + "\\t".join(sys.argv[1:]) + "\\n")
argv = sys.argv[1:]
if argv[:1] == ["up"]:
    sys.stdout.write("[fake run.sh] up\\n")
    sys.exit(UP_RC)
if argv[:1] == ["logs"]:
    sys.stdout.write("[fake run.sh] logs " + " ".join(argv[1:]) + "\\n")
    sys.exit(LOGS_RC)
sys.exit(0)
"""

# A curl that fails the first FAIL_TIMES probes and then succeeds, counting in a file so the count survives across processes exactly as a real service coming up slowly would.
FAKE_CURL = """#!/usr/bin/env python3
import os, sys
LOG = %(log)r
COUNTER = %(counter)r
FAIL_TIMES = %(fail_times)d
NEVER = %(never)d
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("curl\\t" + "\\t".join(sys.argv[1:]) + "\\n")
n = 0
if os.path.exists(COUNTER):
    n = int(open(COUNTER).read() or "0")
with open(COUNTER, "w") as fh:
    fh.write(str(n + 1))
if NEVER or n < FAIL_TIMES:
    sys.stderr.write("curl: (7) Failed to connect\\n")
    sys.exit(7)
sys.exit(0)
"""

FAKE_DOCKER = """#!/usr/bin/env python3
import sys
LOG = %(log)r
PS_LINES = %(ps_lines)r
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("docker\\t" + "\\t".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["ps"]:
    for line in PS_LINES:
        sys.stdout.write(line + "\\n")
    sys.exit(0)
sys.exit(0)
"""


BASH_SLEEP_ANCHOR = "        sleep $interval\n"
PY_SLEEP_ANCHOR = "        time.sleep(INTERVAL_SECONDS)\n"


def _null_sleep_bash(text: str) -> str:
    if text.count(BASH_SLEEP_ANCHOR) != 1:
        raise AssertionError("the bash sleep anchor moved; see the module docstring")
    return text.replace(BASH_SLEEP_ANCHOR, "        sleep 0\n")


def _null_sleep_python(text: str) -> str:
    if text.count(PY_SLEEP_ANCHOR) != 1:
        raise AssertionError("the Python sleep anchor moved; see the module docstring")
    return text.replace(PY_SLEEP_ANCHOR, "        time.sleep(0)\n")


def _fixture(
    base: pathlib.Path,
    *,
    elite_dir: bool = True,
    up_rc: int = 0,
    logs_rc: int = 0,
    curl_fail_times: int = 0,
    curl_never: bool = False,
    ps_lines: tuple[str, ...] = (
        "NAMES\tSTATUS\tPORTS",
        "rediacc-web\tUp 3 seconds\t0.0.0.0:80->80/tcp",
        "unrelated-thing\tUp 1 second\t",
    ),
    with_docker: bool = True,
    port_source: str | None = None,
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects."""
    root = base / "tree"
    (root / ".ci" / "scripts" / "infra").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "infra").mkdir(parents=True)
    (root / ".ci" / "docker" / "ci").mkdir(parents=True)

    (root / ".ci" / "scripts" / "infra" / TWIN.name).write_text(
        _null_sleep_bash(TWIN.read_text(encoding="utf-8")), encoding="utf-8"
    )
    shutil.copy2(CI_ENV, root / ".ci" / "scripts" / "infra" / CI_ENV.name)
    (root / ".ci" / "rediacc_ci" / "infra" / PORT.name).write_text(
        _null_sleep_python(
            port_source if port_source is not None else PORT.read_text(encoding="utf-8")
        ),
        encoding="utf-8",
    )

    log = root / "calls.log"
    log.write_text("", encoding="utf-8")

    if elite_dir:
        elite = root / "private" / "elite"
        elite.mkdir(parents=True)
        run_sh = elite / "run.sh"
        run_sh.write_text(
            FAKE_RUN_SH % {"log": str(log), "up_rc": up_rc, "logs_rc": logs_rc},
            encoding="utf-8",
        )
        run_sh.chmod(0o755)

    binder = root / "fxbin"
    binder.mkdir()
    curl = binder / "curl"
    curl.write_text(
        FAKE_CURL
        % {
            "log": str(log),
            "counter": str(root / "curl.count"),
            "fail_times": curl_fail_times,
            "never": int(curl_never),
        },
        encoding="utf-8",
    )
    curl.chmod(0o755)
    if with_docker:
        docker = binder / "docker"
        docker.write_text(
            FAKE_DOCKER % {"log": str(log), "ps_lines": list(ps_lines)}, encoding="utf-8"
        )
        docker.chmod(0o755)
    return root


LOAD_LINE = re.compile(r"^  load average \(1m 5m 15m\): .*, cores: .*$", re.MULTILINE)


def _normalize(text: str, root: pathlib.Path) -> str:
    text = text.replace(str(root), "<root>")
    return LOAD_LINE.sub("  load average (1m 5m 15m): <masked>, cores: <masked>", text)


def _run(
    which: str, root: pathlib.Path
) -> tuple[subprocess.CompletedProcess[str], list[str], str | None]:
    env = dict(os.environ)
    env.update(DETERMINISTIC_SECRETS)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PATH"] = "%s:%s" % (root / "fxbin", env.get("PATH", ""))
    # PREPENDED, not replaced: the subjects need the system's real bash, env, grep and nproc. The fakes come first, so a real docker or curl on this host is shadowed and never reached -- asserted by `test_the_fakes_are_actually_reached`.
    env.pop("GITHUB_ACTIONS", None)
    env.pop("GITHUB_ENV", None)
    if which == "old":
        cmd = ["bash", str(root / ".ci" / "scripts" / "infra" / TWIN.name)]
    else:
        cmd = ["python3", str(root / ".ci" / "rediacc_ci" / "infra" / PORT.name)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, timeout=180)
    calls = [line for line in (root / "calls.log").read_text(encoding="utf-8").splitlines() if line]
    written = root / "private" / "elite" / ".env"
    return proc, calls, written.read_text(encoding="utf-8") if written.exists() else None


CASES = [
    # name, kwargs
    ("happy-web-ready-first-probe", {}),
    ("web-slow-two-failed-probes", {"curl_fail_times": 2}),
    ("run-sh-up-fails", {"up_rc": 3}),
    ("web-never-ready-logs-ok", {"curl_never": True}),
    ("web-never-ready-logs-fails-suppresses-exit-1", {"curl_never": True, "logs_rc": 42}),
    ("docker-ps-matches-nothing", {"ps_lines": ("zzz\tUp\t",)}),
    ("docker-missing-entirely", {"with_docker": False}),
]


@pytest.mark.parametrize(("name", "kwargs"), CASES, ids=[c[0] for c in CASES])
def test_port_and_twin_agree(name: str, kwargs: dict[str, object]) -> None:
    """Same fixture, both subjects: same exit, same streams, same calls, same .env."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        root_a = _fixture(base / "a", **kwargs)  # type: ignore[arg-type]
        old, old_calls, old_env = _run("old", root_a)
        root_b = _fixture(base / "b", **kwargs)  # type: ignore[arg-type]
        new, new_calls, new_env = _run("new", root_b)

        assert new.returncode == old.returncode, (
            "%s: exit diverged: %r vs %r\ntwin err:\n%s\nport err:\n%s"
            % (
                name,
                old.returncode,
                new.returncode,
                old.stderr,
                new.stderr,
            )
        )
        assert _normalize(new.stdout, root_b) == _normalize(old.stdout, root_a), (
            "%s: stdout diverged:\n--- twin ---\n%s\n--- port ---\n%s"
            % (name, old.stdout, new.stdout)
        )
        assert new_calls == old_calls, "%s: the CALLS diverged:\n twin: %s\n port: %s" % (
            name,
            old_calls,
            new_calls,
        )
        assert new_env == old_env, "%s: the written .env diverged:\n%r\n%r" % (
            name,
            old_env,
            new_env,
        )


def test_the_fakes_are_actually_reached() -> None:
    """ANTI-VACUITY. Without this every comparison above could be two programs
    that never invoked anything agreeing trivially."""
    with tempfile.TemporaryDirectory() as td:
        root = _fixture(pathlib.Path(td) / "v")
        proc, calls, written = _run("new", root)
        assert proc.returncode == 0, proc.stderr
        assert calls, "no fake was invoked; this file proves nothing"
        verbs = [c.split("\t")[0] for c in calls]
        assert "run.sh" in verbs, "run.sh was never invoked: %r" % verbs
        assert "curl" in verbs, "the health endpoint was never probed: %r" % verbs
        assert "docker" in verbs, "docker ps was never run: %r" % verbs
        assert written is not None, "no .env was written at all"
        assert "DOCKER_REGISTRY=ghcr.io/rediacc" in written, (
            "the .env was not written from ci-env.sh's exported values: %r" % written
        )


def test_the_load_line_is_really_there() -> None:
    """CONTROL for `_normalize`: the one masked line must actually be printed by
    both sides on the timeout path, or the mask would be hiding its absence."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        old, _, _ = _run("old", _fixture(base / "a", curl_never=True))
        new, _, _ = _run("new", _fixture(base / "b", curl_never=True))
        assert LOAD_LINE.search(old.stdout), "the twin printed no load line:\n%s" % old.stdout
        assert LOAD_LINE.search(new.stdout), "the port printed no load line:\n%s" % new.stdout


def test_the_null_sleep_anchors_still_exist() -> None:
    """The rewrite the fixture performs must still have exactly one target on
    each side, and the two files must still agree on the real budget."""
    twin = TWIN.read_text(encoding="utf-8")
    port = PORT.read_text(encoding="utf-8")
    assert twin.count(BASH_SLEEP_ANCHOR) == 1, "the bash sleep anchor moved"
    assert port.count(PY_SLEEP_ANCHOR) == 1, "the Python sleep anchor moved"
    assert twin.count("    local timeout=%d\n" % REAL_TIMEOUT) == 1
    assert port.count("TIMEOUT_SECONDS = %d\n" % REAL_TIMEOUT) == 1
    assert "    local interval=2\n" in twin
    assert "INTERVAL_SECONDS = 2\n" in port


def test_the_probe_count_is_the_real_one() -> None:
    """ANTI-VACUITY for the null-sleep rewrite: the timeout path must really
    perform TIMEOUT/INTERVAL probes on both sides, not a shrunken few. A copy that had accidentally kept a shrunken budget would still "agree" while
    proving nothing about the loop the twin actually runs in CI."""
    expected = REAL_TIMEOUT // 2
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        _, old_calls, _ = _run("old", _fixture(base / "a", curl_never=True))
        _, new_calls, _ = _run("new", _fixture(base / "b", curl_never=True))
    for label, calls in (("twin", old_calls), ("port", new_calls)):
        probes = [c for c in calls if c.startswith("curl\t")]
        assert len(probes) == expected, "%s probed %d times, expected %d" % (
            label,
            len(probes),
            expected,
        )


def test_missing_elite_dir_is_a_named_divergence() -> None:
    """Both sides die rc=1 when `private/elite` is absent, and the port does NOT
    forge bash's `ci-start-elite.sh: line 45:` prefix. Pinned so the divergence
    stays deliberate rather than becoming a surprise."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        old, _, _ = _run("old", _fixture(base / "a", elite_dir=False))
        new, _, _ = _run("new", _fixture(base / "b", elite_dir=False))
        assert old.returncode == 1
        assert new.returncode == 1
        assert "No such file or directory" in old.stderr
        assert "No such file or directory" in new.stderr
        assert "line 45" in old.stderr, "bash stopped naming its own line: %r" % old.stderr
        assert "line 45" not in new.stderr, "the port must not forge a bash line number"


def test_generated_secrets_path_agrees_on_shape() -> None:
    """The OTHER arm of ci-env.sh: with nothing pre-set it generates a fresh key
    pair per run, so the values cannot be compared -- but the NAMES written into
    `.env`, and the exit code, still must agree."""
    if not all(shutil.which(t) for t in ("node", "jq", "openssl")):
        pytest.skip("ci-env.sh's generating arm needs node, jq and openssl")
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        results = []
        for side, sub in (("old", "a"), ("new", "b")):
            root = _fixture(base / sub)
            env = dict(os.environ)
            for key in DETERMINISTIC_SECRETS:
                env.pop(key, None)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PATH"] = "%s:%s" % (root / "fxbin", env.get("PATH", ""))
            env.pop("GITHUB_ACTIONS", None)
            env.pop("GITHUB_ENV", None)
            cmd = (
                ["bash", str(root / ".ci" / "scripts" / "infra" / TWIN.name)]
                if side == "old"
                else ["python3", str(root / ".ci" / "rediacc_ci" / "infra" / PORT.name)]
            )
            proc = subprocess.run(
                cmd, capture_output=True, text=True, env=env, check=False, timeout=180
            )
            body = (root / "private" / "elite" / ".env").read_text(encoding="utf-8")
            names = [ln.split("=", 1)[0] for ln in body.splitlines() if "=" in ln]
            values_nonempty = [ln.split("=", 1)[0] for ln in body.splitlines() if ln.endswith("=")]
            results.append((proc.returncode, names, values_nonempty))
        assert results[0] == results[1], "the generating arm diverged: %r" % (results,)
        assert results[0][0] == 0, "both sides failed: %r" % (results,)


# --------------------------------------------------------------------------- The control: a planted defect must turn this differential red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential() -> None:
    """Delete the `set -e` reproduction on the failure path from a COPY.

    `./run.sh logs web` failing suppresses the twin's own `exit 1` and the script exits with the LOGS command's status. A port that "tidied" that into a plain `return 1` would be right-looking and wrong, and would only diverge
    on a case nobody runs by hand. This mutates an in-memory copy; the real file
    on disk is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = "        return logs.returncode if logs.returncode != 0 else 1\n"
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken = source.replace(anchor, "        return 1\n")
    assert broken != source

    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        kwargs = {"curl_never": True, "logs_rc": 42}
        old, _, _ = _run("old", _fixture(base / "a", **kwargs))  # type: ignore[arg-type]
        new, _, _ = _run("new", _fixture(base / "b", port_source=broken, **kwargs))  # type: ignore[arg-type]
        assert old.returncode == 42, "the twin must exit with the logs command's status"
        assert new.returncode != old.returncode, (
            "PLANT DID NOT FIRE: the differential cannot see a suppressed exit status"
        )

    # And the real, unmutated file still agrees on the same case.
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        old, _, _ = _run("old", _fixture(base / "a", curl_never=True, logs_rc=42))
        new, _, _ = _run("new", _fixture(base / "b", curl_never=True, logs_rc=42))
        assert new.returncode == old.returncode == 42
