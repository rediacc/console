"""Differential: `rediacc_ci.infra.ci_start_account` against its twin `.ci/scripts/infra/ci-start-account.sh`.

Same seam and same discipline as `test_infra_ci_start_elite.py`: both subjects derive the console root from their own file location, so every case copies both into a fresh tree at the right relative depth, runs the copies, and asserts on the DOCKER ARGV SEQUENCE as well as on both streams, the written `.env` and `$GITHUB_OUTPUT`. A port that printed "Account server is healthy"
without ever inspecting anything would pass a stdout-only comparison.

THE REAL `ci-env.sh` IS COPIED IN AND SOURCED FOR REAL, with every secret it
would otherwise generate pre-set so both sides take its `${VAR:-...}` arms and
the result is byte-deterministic.

ONLY THE SLEEPS ARE REWRITTEN IN THE COPIES. The twin polls for 180s at a 3s interval and then sleeps a further 2s; nulling those three sleeps keeps every constant, so both sides still perform all 60 probes, still print the progress line on the same multiples of 15, and the comparison is over the real arithmetic instead of a miniature of it.
`test_the_null_sleep_anchors_still_exist` and `test_the_probe_count_is_the_real_one` are the controls on that rewrite.

ONE LINE IS NORMALIZED: ` load average (1m 5m 15m): ...`, which both sides read
from the real `/proc/loadavg` seconds apart. `test_the_load_line_is_really_there`
asserts both printed a well-formed one so the mask cannot hide its absence.

THE `unhealthy` DEFECT IS PINNED HERE, NOT FIXED. `ci-start-account.sh:106` greps for the SUBSTRING `healthy`, which `unhealthy` contains, so a container docker has failed is announced as healthy. The port reproduces the match and `test_unhealthy_is_read_as_healthy` locks it in with the measurement of how reachable it is today. Fixing the twin changes a live CI step's pass/fail
behaviour and is outside this port's file ownership.

K=5 LEDGER: `.ci/shadow/w7p6-ci-start-account.observations.jsonl`.
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
TWIN = ROOT / ".ci" / "scripts" / "infra" / "ci-start-account.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "ci_start_account.py"
CI_ENV = ROOT / ".ci" / "scripts" / "infra" / "ci-env.sh"

REAL_TIMEOUT = 180
REAL_INTERVAL = 3

DETERMINISTIC_SECRETS = {
    "ACCOUNT_ED25519_PRIVATE_KEY": "fixture-ed25519-private",
    "ACCOUNT_ED25519_PUBLIC_KEY": "fixture-ed25519-public",
    "ACCOUNT_X25519_PRIVATE_KEY": "fixture-x25519-private",
    "ACCOUNT_X25519_PUBLIC_KEY": "fixture-x25519-public",
    "ACCOUNT_SERVER_API_KEY": "fixture-api-key",
    "ACCOUNT_JWT_SECRET": "fixture-jwt-secret",
    "STRIPE_WEBHOOK_SECRET": "whsec_fixture",
}

# `logs` writes to BOTH streams, deterministically ordered, because the twin redirects them differently in two places: `2>&1` on :150 and not at all on :113/:124. A fake that only wrote stdout could not tell those apart.
FAKE_DOCKER = """#!/usr/bin/env python3
import os, sys
LOG = %(log)r
COUNTER = %(counter)r
HEALTH = %(health)r
PS_NAMES = %(ps_names)r
PS_NAMES_AFTER = %(ps_names_after)r
PS_FLIP_AT = %(ps_flip_at)d
FINAL_STATUS = %(final_status)r
FINAL_INSPECT_RC = %(final_inspect_rc)d
UP_RC = %(up_rc)d
COMPOSE_LOGS_RC = %(compose_logs_rc)d
argv = sys.argv[1:]
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("docker\\t" + "\\t".join(argv) + "\\n")


def bump():
    n = 0
    if os.path.exists(COUNTER):
        n = int(open(COUNTER).read() or "0")
    with open(COUNTER, "w") as fh:
        fh.write(str(n + 1))
    return n


if argv[:1] == ["compose"] and "up" in argv:
    sys.stdout.write("[fake docker] compose up\\n")
    sys.exit(UP_RC)
if argv[:1] == ["compose"] and "logs" in argv:
    sys.stdout.write("[fake docker] compose logs\\n")
    sys.exit(COMPOSE_LOGS_RC)
if argv[:1] == ["inspect"] and argv[-1] == "--format={{.State.Health.Status}}":
    n = bump()
    sys.stdout.write(HEALTH[min(n, len(HEALTH) - 1)] + "\\n")
    sys.exit(0)
if argv[:1] == ["inspect"] and argv[-1] == "--format={{.State.Status}}":
    if FINAL_INSPECT_RC != 0:
        sys.stderr.write("Error: No such object\\n")
        sys.exit(FINAL_INSPECT_RC)
    sys.stdout.write(FINAL_STATUS + "\\n")
    sys.exit(0)
if argv[:2] == ["ps", "--format"] and argv[2] == "{{.Names}}":
    seen = 0
    if os.path.exists(COUNTER):
        seen = int(open(COUNTER).read() or "0")
    names = PS_NAMES_AFTER if (PS_FLIP_AT and seen >= PS_FLIP_AT) else PS_NAMES
    for n in names:
        sys.stdout.write(n + "\\n")
    sys.exit(0)
if argv[:1] == ["ps"]:
    sys.stdout.write("NAMES\\tSTATUS\\tPORTS\\n")
    sys.stdout.write("rediacc-account-server\\tUp 4 seconds\\t3000/tcp\\n")
    sys.exit(0)
if argv[:1] == ["logs"]:
    sys.stdout.write("[fake docker] logs stdout " + " ".join(argv[1:]) + "\\n")
    sys.stdout.flush()
    sys.stderr.write("[fake docker] logs stderr\\n")
    sys.stderr.flush()
    sys.exit(0)
sys.exit(0)
"""

BASH_SLEEP_ANCHOR = "        sleep $interval\n"
BASH_SETTLE_ANCHOR = "\nsleep 2\n"
PY_SLEEP_ANCHOR = "        time.sleep(INTERVAL_SECONDS)\n"
PY_SETTLE_ANCHOR = "    time.sleep(SETTLE_SECONDS)\n"


def _null_sleep_bash(text: str) -> str:
    if text.count(BASH_SLEEP_ANCHOR) != 1 or text.count(BASH_SETTLE_ANCHOR) != 1:
        raise AssertionError("a bash sleep anchor moved; see the module docstring")
    return text.replace(BASH_SLEEP_ANCHOR, "        sleep 0\n").replace(
        BASH_SETTLE_ANCHOR, "\nsleep 0\n"
    )


def _null_sleep_python(text: str) -> str:
    if text.count(PY_SLEEP_ANCHOR) != 1 or text.count(PY_SETTLE_ANCHOR) != 1:
        raise AssertionError("a Python sleep anchor moved; see the module docstring")
    return text.replace(PY_SLEEP_ANCHOR, "        time.sleep(0)\n").replace(
        PY_SETTLE_ANCHOR, "    time.sleep(0)\n"
    )


def _fixture(
    base: pathlib.Path,
    *,
    health: tuple[str, ...] = ("healthy",),
    ps_names: tuple[str, ...] = ("rediacc-account-server", "other"),
    ps_names_after: tuple[str, ...] = (),
    ps_flip_at: int = 0,
    final_status: str = "running",
    final_inspect_rc: int = 0,
    up_rc: int = 0,
    compose_logs_rc: int = 0,
    with_docker: bool = True,
    port_source: str | None = None,
) -> pathlib.Path:
    root = base / "tree"
    (root / ".ci" / "scripts" / "infra").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "infra").mkdir(parents=True)
    (root / ".ci" / "docker" / "ci").mkdir(parents=True)
    (root / ".ci" / "docker" / "ci" / "docker-compose.yml").write_text(
        "# fixture placeholder; the recording fake never reads it\n", encoding="utf-8"
    )

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
    binder = root / "fxbin"
    binder.mkdir()
    if with_docker:
        docker = binder / "docker"
        docker.write_text(
            FAKE_DOCKER
            % {
                "log": str(log),
                "counter": str(root / "health.count"),
                "health": list(health),
                "ps_names": list(ps_names),
                "ps_names_after": list(ps_names_after),
                "ps_flip_at": ps_flip_at,
                "final_status": final_status,
                "final_inspect_rc": final_inspect_rc,
                "up_rc": up_rc,
                "compose_logs_rc": compose_logs_rc,
            },
            encoding="utf-8",
        )
        docker.chmod(0o755)
    return root


LOAD_LINE = re.compile(r"^  load average \(1m 5m 15m\): .*, cores: .*$", re.MULTILINE)


def _normalize(text: str, root: pathlib.Path) -> str:
    text = text.replace(str(root), "<root>")
    return LOAD_LINE.sub("  load average (1m 5m 15m): <masked>, cores: <masked>", text)


def _run(
    which: str, root: pathlib.Path, *, secrets: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], list[str], str | None, str | None]:
    env = dict(os.environ)
    env.update(DETERMINISTIC_SECRETS if secrets is None else secrets)
    for key in DETERMINISTIC_SECRETS:
        if env.get(key) == "":
            env.pop(key)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # PREPENDED, not replaced: the subjects need the system's real bash, env and grep. The fake docker comes first, so this host's real daemon is never reached -- asserted by `test_the_fake_docker_is_actually_reached`.
    env["PATH"] = "%s:%s" % (root / "fxbin", env.get("PATH", ""))
    env.pop("GITHUB_ACTIONS", None)
    env.pop("GITHUB_ENV", None)
    gho = root / "github_output.txt"
    env["GITHUB_OUTPUT"] = str(gho)
    if which == "old":
        cmd = ["bash", str(root / ".ci" / "scripts" / "infra" / TWIN.name)]
    else:
        cmd = ["python3", str(root / ".ci" / "rediacc_ci" / "infra" / PORT.name)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, timeout=300)
    calls = [line for line in (root / "calls.log").read_text(encoding="utf-8").splitlines() if line]
    written = root / ".ci" / "docker" / "ci" / ".env"
    return (
        proc,
        calls,
        written.read_text(encoding="utf-8") if written.exists() else None,
        gho.read_text(encoding="utf-8") if gho.exists() else None,
    )


CASES: list[tuple[str, dict[str, object], dict[str, str] | None]] = [
    ("happy-healthy-first-probe", {}, None),
    (
        "healthy-after-five-probes-prints-the-15s-line",
        {"health": ("starting", "starting", "starting", "starting", "starting", "healthy")},
        None,
    ),
    ("compose-up-fails", {"up_rc": 5}, None),
    (
        "container-vanishes-mid-wait",
        {
            "health": ("starting",),
            "ps_names": ("rediacc-account-server",),
            "ps_names_after": ("something-else",),
            "ps_flip_at": 3,
        },
        None,
    ),
    (
        "container-vanishes-and-compose-logs-fails-suppressing-exit-1",
        {
            "health": ("starting",),
            "ps_names": ("rediacc-account-server",),
            "ps_names_after": (),
            "ps_flip_at": 2,
            "compose_logs_rc": 9,
        },
        None,
    ),
    ("never-healthy-times-out", {"health": ("starting",)}, None),
    ("healthy-but-restarting-afterwards", {"final_status": "restarting"}, None),
    ("healthy-but-final-inspect-fails-is-missing", {"final_inspect_rc": 1}, None),
    (
        "near-miss-container-name-is-not-a-match",
        {
            "health": ("starting",),
            "ps_names": ("rediacc-account-server-2",),
        },
        None,
    ),
    (
        "missing-ed25519-private",
        {},
        {**DETERMINISTIC_SECRETS, "ACCOUNT_ED25519_PRIVATE_KEY": ""},
    ),
    ("missing-ed25519-public", {}, {**DETERMINISTIC_SECRETS, "ACCOUNT_ED25519_PUBLIC_KEY": ""}),
    ("missing-api-key", {}, {**DETERMINISTIC_SECRETS, "ACCOUNT_SERVER_API_KEY": ""}),
    ("docker-missing-entirely", {"with_docker": False}, None),
]


@pytest.mark.parametrize(("name", "kwargs", "secrets"), CASES, ids=[c[0] for c in CASES])
def test_port_and_twin_agree(
    name: str, kwargs: dict[str, object], secrets: dict[str, str] | None
) -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        root_a = _fixture(base / "a", **kwargs)  # type: ignore[arg-type]
        old, old_calls, old_env, old_gho = _run("old", root_a, secrets=secrets)
        root_b = _fixture(base / "b", **kwargs)  # type: ignore[arg-type]
        new, new_calls, new_env, new_gho = _run("new", root_b, secrets=secrets)

        assert new.returncode == old.returncode, (
            "%s: exit diverged: %r vs %r\ntwin err:\n%s\nport err:\n%s"
            % (name, old.returncode, new.returncode, old.stderr, new.stderr)
        )
        assert _normalize(new.stdout, root_b) == _normalize(old.stdout, root_a), (
            "%s: stdout diverged:\n--- twin ---\n%s\n--- port ---\n%s"
            % (name, old.stdout, new.stdout)
        )
        assert _normalize(new.stderr, root_b) == _normalize(old.stderr, root_a), (
            "%s: stderr diverged:\n--- twin ---\n%s\n--- port ---\n%s"
            % (name, old.stderr, new.stderr)
        )
        assert new_calls == old_calls, "%s: the docker CALLS diverged:\n twin: %s\n port: %s" % (
            name,
            old_calls,
            new_calls,
        )
        assert new_env == old_env, "%s: the written .env diverged:\n%r\n%r" % (
            name,
            old_env,
            new_env,
        )
        assert new_gho == old_gho, "%s: $GITHUB_OUTPUT diverged:\n%r\n%r" % (
            name,
            old_gho,
            new_gho,
        )


def test_the_fake_docker_is_actually_reached() -> None:
    """ANTI-VACUITY: without this, two programs that never called docker agree."""
    with tempfile.TemporaryDirectory() as td:
        root = _fixture(pathlib.Path(td) / "v")
        proc, calls, written, gho = _run("new", root)
        assert proc.returncode == 0, proc.stderr
        assert calls, "the recording docker was never invoked; this file proves nothing"
        verbs = [c.split("\t")[1] for c in calls]
        assert "compose" in verbs, "compose up was never attempted: %r" % verbs
        assert "inspect" in verbs, "health was never inspected: %r" % verbs
        assert written is not None, "no .env was written at all"
        assert "ACCOUNT_JWT_SECRET=fixture-jwt-secret" in written, (
            "the .env was not written from ci-env.sh's exported values: %r" % written
        )
        assert gho == "account_server_url=http://localhost:3000\n", (
            "$GITHUB_OUTPUT was not written: %r" % gho
        )


def test_the_secret_guards_run_before_anything_else() -> None:
    """CONTROL for the three refusal cases: nothing is started and nothing is written when a secret is absent. A port that sourced first would generate keys and write a `.env` on a host with no secrets at all."""
    with tempfile.TemporaryDirectory() as td:
        root = _fixture(pathlib.Path(td) / "g")
        proc, calls, written, gho = _run(
            "new", root, secrets={**DETERMINISTIC_SECRETS, "ACCOUNT_SERVER_API_KEY": ""}
        )
        assert proc.returncode == 1
        assert calls == [], "docker was touched despite a missing secret: %r" % calls
        assert written is None, "a .env was written despite a missing secret"
        assert gho is None or gho == "", "$GITHUB_OUTPUT was written despite a missing secret"


def test_unhealthy_is_read_as_healthy() -> None:
    """THE PINNED DEFECT, on both sides.

    `ci-start-account.sh:106` is `docker inspect ... | grep -q "healthy"`, a SUBSTRING test. Both the twin and this port therefore announce a container docker has marked UNHEALTHY as healthy and let the job continue.

    HOW REACHABLE IT IS TODAY, MEASURED RATHER THAN ESTIMATED, and the margin is thinner than it looks. The container's healthcheck (`.ci/docker/ci/docker-compose.yml:52-62`) declares `start_period: 150s`, `interval: 10s`, `retries: 6`. Docker does not count a failing probe against `retries` during `start_period`, so the failing streak can only begin at
    t=150s and the earliest `unhealthy` is around t=200s.

    The loop's 180s is a budget of SLEEPS, not a deadline: the wall clock the probes themselves consume is never added to `elapsed`. Timed against the real daemon on this host (docker 29.7.2), `docker inspect <missing>
    --format=...` costs 0.131s and `docker ps --format {{.Names}}` 0.052s, so 60
    iterations add 11.0s and the last probe lands at roughly t=191s. That clears
    t=200s by about 9 seconds. The defect therefore goes LIVE, with no change to
    any file, as soon as the average inspect+ps round trip exceeds about 0.33s against the 0.183s measured here -- a factor of 1.8, which a contended runner supplies routinely. It also goes live if `start_period` drops below 120s or `retries` below 3.

    It is pinned, not fixed: correcting it changes a live CI step's pass/fail behaviour and is outside this port's file ownership.
    """
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        old, old_calls, _, _ = _run("old", _fixture(base / "a", health=("unhealthy",)))
        new, new_calls, _, _ = _run("new", _fixture(base / "b", health=("unhealthy",)))
        assert old.returncode == 0, "the twin stopped accepting `unhealthy`; re-read this test"
        assert "  Account server is healthy" in old.stdout
        assert new.returncode == old.returncode
        assert "  Account server is healthy" in new.stdout
        # And the loop really did read `unhealthy` rather than never inspecting.
        assert any("Health.Status" in c for c in old_calls)
        assert any("Health.Status" in c for c in new_calls)


def test_the_load_line_is_really_there() -> None:
    """CONTROL for `_normalize`: the masked line must actually be printed."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        old, _, _, _ = _run("old", _fixture(base / "a", health=("starting",)))
        new, _, _, _ = _run("new", _fixture(base / "b", health=("starting",)))
        assert LOAD_LINE.search(old.stdout), "the twin printed no load line:\n%s" % old.stdout
        assert LOAD_LINE.search(new.stdout), "the port printed no load line:\n%s" % new.stdout


def test_the_null_sleep_anchors_still_exist() -> None:
    twin = TWIN.read_text(encoding="utf-8")
    port = PORT.read_text(encoding="utf-8")
    assert twin.count(BASH_SLEEP_ANCHOR) == 1, "the bash poll-sleep anchor moved"
    assert twin.count(BASH_SETTLE_ANCHOR) == 1, "the bash settle-sleep anchor moved"
    assert port.count(PY_SLEEP_ANCHOR) == 1, "the Python poll-sleep anchor moved"
    assert port.count(PY_SETTLE_ANCHOR) == 1, "the Python settle-sleep anchor moved"
    assert twin.count("    local timeout=%d\n" % REAL_TIMEOUT) == 1
    assert twin.count("    local interval=%d\n" % REAL_INTERVAL) == 1
    assert port.count("TIMEOUT_SECONDS = %d\n" % REAL_TIMEOUT) == 1
    assert port.count("INTERVAL_SECONDS = %d\n" % REAL_INTERVAL) == 1
    assert port.count("SETTLE_SECONDS = 2\n") == 1


def test_the_probe_count_is_the_real_one() -> None:
    """ANTI-VACUITY for the null-sleep rewrite: the timeout path must perform TIMEOUT/INTERVAL probes on both sides, not a shrunken few."""
    expected = REAL_TIMEOUT // REAL_INTERVAL
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        _, old_calls, _, _ = _run("old", _fixture(base / "a", health=("starting",)))
        _, new_calls, _, _ = _run("new", _fixture(base / "b", health=("starting",)))
    for label, calls in (("twin", old_calls), ("port", new_calls)):
        probes = [c for c in calls if "Health.Status" in c]
        assert len(probes) == expected, "%s probed %d times, expected %d" % (
            label,
            len(probes),
            expected,
        )


def test_the_progress_line_fires_only_on_multiples_of_fifteen() -> None:
    """`((elapsed % 15 == 0))` at a 3s interval: every fifth iteration and no
    other. A port that printed it every iteration would still 'agree' on the happy path, where the loop runs once."""
    with tempfile.TemporaryDirectory() as td:
        root = _fixture(pathlib.Path(td) / "p", health=("starting",))
        proc, _, _, _ = _run("new", root)
    stamps = re.findall(r"^    Still waiting\.\.\. \((\d+)s / 180s\)$", proc.stdout, re.MULTILINE)
    assert stamps == [str(n) for n in range(15, 181, 15)], stamps


# --------------------------------------------------------------------------- The control: a planted defect must turn this differential red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential() -> None:
    """"Fix" the substring match in a COPY of the port and watch it diverge.

    Turning `grep -q "healthy"` into an equality test is the change a reader would make on sight, and it is a real behaviour change against the twin. This mutates an in-memory copy; the file on disk is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = '    return any("healthy" in line for line in inspect_stdout.splitlines())\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken = source.replace(
        anchor,
        '    return any(line.strip() == "healthy" for line in inspect_stdout.splitlines())\n',
    )
    assert broken != source

    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        old, _, _, _ = _run("old", _fixture(base / "a", health=("unhealthy",)))
        new, _, _, _ = _run("new", _fixture(base / "b", health=("unhealthy",), port_source=broken))
        assert old.returncode == 0, "the twin must still accept `unhealthy`"
        assert new.returncode != old.returncode or new.stdout != old.stdout, (
            "PLANT DID NOT FIRE: the differential cannot see the substring semantics"
        )

    # And the real, unmutated file still agrees on the same case.
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        root_a = _fixture(base / "a", health=("unhealthy",))
        root_b = _fixture(base / "b", health=("unhealthy",))
        old, _, _, _ = _run("old", root_a)
        new, _, _, _ = _run("new", root_b)
        assert new.returncode == old.returncode == 0
        assert _normalize(new.stdout, root_b) == _normalize(old.stdout, root_a)
