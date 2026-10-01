"""`rediacc_ci.testrun.account_e2e` against its bash twin `.ci/scripts/test/run-account-e2e.sh`, on a FIXTURE tree.

The twin resolves its root from its own location and the port from `$REDIACC_CI_ROOT`, so one fixture (a copy of the script and `common.sh`, plus a fake `private/account` with its `e2e/tests`) is handed to both. Fakes: `npx` (starts `testrun_stub_server.py` for `tsx`, records everything else), `npm`, and `stripe`. Compared: the ordered call log, stdout, stderr and exit code. The REAL account server and a real Playwright run are exercised by the live run in the porting report, not here.

INTENTIONAL DELTAS (Rule T), each a `test_delta_*` failing on the bash behaviour: unknown flags refused; secrets checked before anything starts; the backend's process tree is stopped; a missing account checkout fails under CI.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import typing

import pytest

from rediacc_ci.testrun import account_e2e
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import testrun_support as ts

# THE HOST'S PORT SPACE IS SHARED: free_port() releases the port before the server binds it, so two xdist workers can draw the same one (a 1-in-4 flake under load on 2026-10-01). Same group as test_core_ports.py and test_core_account.py.
XDIST_GROUP = "ports"

STUB = pathlib.Path(__file__).with_name("testrun_stub_server.py")
SCRIPT_REL = ".ci/scripts/test/run-account-e2e.sh"
TWIN = SCRIPT_REL
MODULE = "rediacc_ci.testrun.account_e2e"
SECRETS = {
    "ACCOUNT_ED25519_PRIVATE_KEY": "edpriv",
    "ACCOUNT_ED25519_PUBLIC_KEY": "edpub",
    "ACCOUNT_SERVER_API_KEY": "k" * 40,
    "ACCOUNT_JWT_SECRET": "j" * 40,
    "ROOT_EMAIL": "root@example.invalid",
}

# `tsx` becomes the stub server (so /health answers) after leaving a child behind that outlives a wrapper-only kill; everything else is the recording fake.
NPX_BODY = ts.FAKE_TEMPLATE.replace(
    'out="FAKE_OUT_$up"',
    'if [[ "$1" == "tsx" && "$2" == src/entry/node.ts ]]; then python3 -c "import threading; threading.Event().wait()" >/dev/null 2>&1 & echo $! > "$FAKE_ORPHAN"; exec python3 "'
    + str(STUB)
    + '" "$PORT" "$STUB_LOG" "$STUB_MODE" >/dev/null 2>&1; fi\nout="FAKE_OUT_$up"',
    1,
)


def webauthn_fixture(counts: dict[str, int]) -> dict:
    tests = []
    for status, n in counts.items():
        tests += [
            {
                "title": f"t-{status}-{i}",
                "tests": [{"projectName": "chromium", "status": status}],
                "tags": ["@webauthn"],
            }
            for i in range(n)
        ]
    return {
        "suites": [
            {
                "title": "root",
                "specs": tests[:1],
                "suites": [{"title": "inner", "specs": tests[1:]}],
            }
        ]
    }


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fixture(directory: pathlib.Path, report: bool = True) -> pathlib.Path:
    root = directory / "root"
    (root / ".ci/scripts/test").mkdir(parents=True)
    (root / ".ci/scripts/lib").mkdir(parents=True)
    if (
        ts.ROOT / SCRIPT_REL
    ).is_file():  # only a re-freeze from bash runs the twin (PLAN-retire-bash-oracles B3)
        shutil.copy(ts.ROOT / SCRIPT_REL, root / SCRIPT_REL)
    shutil.copy(ts.ROOT / ".ci/scripts/lib/common.sh", root / ".ci/scripts/lib/common.sh")
    (root / ".ci/config").mkdir(parents=True)
    shutil.copy(ts.ROOT / ".ci/config/well-known.env", root / ".ci/config/well-known.env")
    # common.sh sources the generated projection (410f34073); without it the twin died on its first line.
    shutil.copy(
        ts.ROOT / ".ci/config/well-known.generated.sh",
        root / ".ci/config/well-known.generated.sh",
    )
    (root / ".git").write_text("gitdir: x\n")
    (root / "package.json").write_text("{}")
    account = root / "private" / "account"
    for sub in ("", "web", "e2e"):
        (account / sub / "node_modules").mkdir(parents=True)
    (account / "package.json").write_text("{}")
    for name, body in {
        "01-auth/a.spec.ts": "x",
        "10-stripe/s.spec.ts": "y",
        "20-webauthn/w.spec.ts": "@webauthn",
    }.items():
        target = account / "e2e" / "tests" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    if report:
        results = account / "e2e" / "reports" / "e2e" / "results.json"
        results.parent.mkdir(parents=True)
        results.write_text(json.dumps(webauthn_fixture({"expected": 21})))
    return root


class Case(typing.NamedTuple):
    out: ts.Outcome
    root: pathlib.Path
    orphan: int | None
    # The retired twin's answer to "is its backend's child still running": frozen, since the twin no longer runs.
    orphan_up: bool | None = None


def drive(
    tmp_path: pathlib.Path,
    name: str,
    args: list[str],
    env: dict[str, str] | None = None,
    root: pathlib.Path | None = None,
    tools: tuple[str, ...] = ("npx", "npm"),
    report: bool = True,
) -> Case:
    directory = tmp_path / name
    directory.mkdir()
    root = root or fixture(directory, report)
    full = {
        "ACCOUNT_API_PORT": str(free_port()),
        "E2E_PORT": "5999",
        "STUB_LOG": str(directory / "stub.jsonl"),
        "FAKE_ORPHAN": str(directory / "orphan.pid"),
        "CI": "",
        "GITHUB_ACTIONS": "",
        "GITLAB_CI": "",
        **SECRETS,
        **(env or {}),
    }
    if name.startswith("bash"):
        return bash_drive(tmp_path, directory, root, args, full, tools)
    runner = ts.py_cmd(MODULE, *args)
    full = ts.py_env({**full, "REDIACC_CI_ROOT": str(root)})
    outcome = ts.run_side(
        runner, directory, tools, full, cwd=directory, bodies={"npx": NPX_BODY}, timeout=90
    )
    orphan_file = directory / "orphan.pid"
    return Case(outcome, root, int(orphan_file.read_text()) if orphan_file.exists() else None)


def bash_drive(
    tmp_path: pathlib.Path,
    directory: pathlib.Path,
    root: pathlib.Path,
    args: list[str],
    full: dict[str, str],
    tools: tuple[str, ...],
) -> Case:
    """The retired twin's run, from `goldens/twins/test.run-account-e2e.jsonl` (PLAN-retire-bash-oracles B3).

    The backend's port is random per run, so records carry `<PORT>` and a replay puts this run's port back. What the twin left behind (its backend's child, the account database) is a record of its own.
    """
    port = full["ACCOUNT_API_PORT"]
    cell: dict[str, ts.Outcome] = {}

    def sub(text: str) -> str:
        return text.replace(port, "<PORT>")

    def go() -> tuple[int, str, str]:
        out = ts.run_side(
            ts.bash_cmd(str(root / SCRIPT_REL), *args),
            directory,
            tools,
            full,
            cwd=directory,
            bodies={"npx": NPX_BODY},
            timeout=90,
        )
        cell["o"] = out
        return out.code, sub(out.out), sub(out.err)

    def orphan() -> str:
        pid_file = directory / "orphan.pid"
        if not pid_file.exists():
            return diff.ABSENT
        return "1" if alive(int(pid_file.read_text())) else "0"

    def db() -> str:
        return "1" if (root / "private/account/e2e-account.db").exists() else "0"

    keyed = {k: ("<PORT>" if k == "ACCOUNT_API_PORT" else v) for k, v in full.items()}
    rc, out, err, got = diff.twin_run(
        TWIN,
        ["args=%r" % (args,), "env=%r" % (sorted(keyed.items()),), "tools=%r" % (tools,)],
        go,
        extras={
            "calls": lambda: sub(json.dumps(cell["o"].calls)),
            "orphan": orphan,
            "db": db,
        },
        work=(str(tmp_path),),
    )
    live = diff.regolden_mode(TWIN) is not None
    calls = cell["o"].calls if live else json.loads(got["calls"].replace("<PORT>", port))
    if got["db"] == "1" and not live:
        (root / "private/account/e2e-account.db").write_text("")
    outcome = ts.Outcome(rc, out.replace("<PORT>", port), err.replace("<PORT>", port), calls)
    orphan_file = directory / "orphan.pid"
    pid = int(orphan_file.read_text()) if live and orphan_file.exists() else None
    up = None if live else got["orphan"] == "1"
    return Case(outcome, root, pid, up)


def alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def orphan_alive(case: Case) -> bool:
    return alive(case.orphan) if case.orphan_up is None else case.orphan_up


def norm_calls(case: Case) -> list[tuple]:
    rows = []
    for call in case.out.calls:
        cwd = call["cwd"].replace(str(case.root), "<ROOT>")
        rows.append((call["tool"], [a for a in call["argv"] if "localhost" not in a], cwd))
    return rows


def norm_text(text: str, case: Case) -> str:
    return text.replace(str(case.root), "<ROOT>")


def same(a: Case, b: Case) -> None:
    assert norm_calls(a)[1:] == norm_calls(b)[1:] or norm_calls(a) == norm_calls(b)
    assert (a.out.code, norm_text(a.out.out, a), norm_text(a.out.err, a)) == (
        b.out.code,
        norm_text(b.out.out, b),
        norm_text(b.out.err, b),
    )


@pytest.fixture
def reap() -> typing.Iterator[list[int | None]]:
    seen: list[int | None] = []
    yield seen
    for pid in seen:
        if pid is not None:
            with contextlib.suppress(OSError):
                os.kill(pid, 9)


def run_both(
    tmp_path: pathlib.Path,
    reaper: list[int | None],
    args: list[str],
    env: dict[str, str] | None = None,
    report: bool = True,
) -> tuple[Case, Case]:
    old = drive(tmp_path, "bash", args, env, report=report)
    new = drive(tmp_path, "py", args, env, report=report)
    reaper.extend([old.orphan, new.orphan])
    return old, new


def test_default_run_matches_the_twin(tmp_path: pathlib.Path, reap: list[int | None]) -> None:
    old, new = run_both(tmp_path, reap, [])
    assert old.out.code == 0, old.out.err
    assert norm_calls(old) == norm_calls(new)
    assert old.out.code == new.out.code
    assert any(c[1][:2] == ["playwright", "install"] for c in norm_calls(old))
    assert any(c[1][:2] == ["playwright", "test"] for c in norm_calls(old))
    assert not (old.root / "private/account/e2e-account.db").exists()


def test_projects_grep_and_workers_reach_playwright(
    tmp_path: pathlib.Path, reap: list[int | None]
) -> None:
    old, new = run_both(
        tmp_path,
        reap,
        ["--projects", "chromium firefox", "--grep", "@auth", "--workers", "3", "--skip-setup"],
    )
    argv = next(c[1] for c in norm_calls(old) if c[1][:2] == ["playwright", "test"])
    assert argv == [
        "playwright",
        "test",
        "--project=chromium",
        "--project=firefox",
        "--workers=3",
        "--timeout=60000",
        "--grep",
        "@auth",
    ]
    assert not any(c[1][:1] == ["tsx"] for c in norm_calls(old)), "--skip-setup starts no backend"
    assert norm_calls(old) == norm_calls(new)
    assert old.out.code == new.out.code == 0


def test_shard_files_are_appended(tmp_path: pathlib.Path, reap: list[int | None]) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps({"of": 4, "legs": [{"index": 2, "ids": ["account-e2e:01-auth/a.spec.ts"]}]})
    )
    old, new = run_both(
        tmp_path, reap, ["--shard-manifest", str(manifest), "--shard", "2/4", "--skip-setup"]
    )
    argv = next(c[1] for c in norm_calls(old) if c[1][:2] == ["playwright", "test"])
    assert argv[-1] == "01-auth/a.spec.ts"
    assert old.out.code == new.out.code == 0
    assert norm_calls(old) == norm_calls(new)


def test_stripe_listen_is_started_for_the_stripe_leg(
    tmp_path: pathlib.Path, reap: list[int | None]
) -> None:
    env = {
        "STRIPE_SANDBOX_SECRET_KEY": "sk_test_x",
        "FAKE_OUT_STRIPE": "Ready! signing secret is whsec_fake123",
    }
    old = drive(tmp_path, "bash", [], env, tools=("npx", "npm", "stripe"))
    new = drive(tmp_path, "py", [], env, tools=("npx", "npm", "stripe"))
    reap.extend([old.orphan, new.orphan])
    assert old.out.code == new.out.code == 0, (old.out.err, new.out.err)
    stripe_calls = [c for c in norm_calls(old) if c[0] == "stripe"]
    assert stripe_calls
    assert any(c[1][:2] == ["tsx", "scripts/stripe-sync.ts"] for c in norm_calls(old)), (
        "the sandbox sync ran before listening"
    )
    assert norm_calls(old) == norm_calls(new)


def test_test_failure_is_exit_one(tmp_path: pathlib.Path, reap: list[int | None]) -> None:
    old, new = run_both(
        tmp_path, reap, ["--skip-setup"], {"FAKE_RC_NPX": "5", "FAKE_RCWHEN_NPX": "test"}
    )
    assert old.out.code == new.out.code == 1
    assert "Account Portal E2E tests failed" in old.out.err
    assert "Account Portal E2E tests failed" in new.out.err


def test_missing_report_fails_the_webauthn_floor_on_both_sides(
    tmp_path: pathlib.Path, reap: list[int | None]
) -> None:
    old, new = run_both(tmp_path, reap, ["--skip-setup"], report=False)
    assert old.out.code == new.out.code == 1
    assert "no Playwright JSON report at" in old.out.err
    assert "no Playwright JSON report at" in new.out.err
    assert "WebAuthn virtual-authenticator coverage check failed" in new.out.err


def test_shard_pair_alone_matches_the_twin(tmp_path: pathlib.Path, reap: list[int | None]) -> None:
    old, new = run_both(tmp_path, reap, ["--shard", "1/4"])
    assert old.out.code == new.out.code == 1
    assert "must both be given" in old.out.err
    assert "must both be given" in new.out.err


@pytest.mark.parametrize(
    "counts",
    [
        {"expected": 21},
        {"expected": 20},
        {"expected": 19},
        {"expected": 25, "skipped": 1},
        {"expected": 25, "unexpected": 1},
    ],
)
def test_webauthn_verdict_matches_the_embedded_node_program(
    tmp_path: pathlib.Path, counts: dict[str, int]
) -> None:
    """The twin's heredoc is extracted verbatim and run under node, then compared with the Python judgement."""

    def read_twin() -> tuple[int, str, str]:
        text = (ts.ROOT / SCRIPT_REL).read_text()
        return 0, text.split("<<'NODE'; then\n", 1)[1].split("\nNODE\n", 1)[0], ""

    # Frozen with the retired twin: its embedded node program, verbatim.
    program = diff.twin_call(
        SCRIPT_REL, ["embedded node program"], read_twin, label="node-program"
    )[1]
    report = tmp_path / "results.json"
    report.write_text(json.dumps(webauthn_fixture(counts)))
    done = subprocess.run(
        ["node", "-", str(report), "20"], input=program, capture_output=True, text=True, check=False
    )
    assert (done.returncode == 0) == account_e2e.check_webauthn(report, 20)


# ---- intentional deltas ----------------------------------------------------------------------------------------------------


def test_delta_unknown_flag_is_refused(tmp_path: pathlib.Path, reap: list[int | None]) -> None:
    old, new = run_both(tmp_path, reap, ["--proejcts", "firefox", "--skip-setup"])
    assert old.out.code == 0, "bash ignored the typo and ran chromium"
    assert new.out.code == 2
    assert not new.out.calls


def test_delta_skip_setup_is_a_switch(tmp_path: pathlib.Path, reap: list[int | None]) -> None:
    old = drive(tmp_path, "bash", ["--skip-setup", "yes"])
    reap.append(old.orphan)
    assert any(c[1][:1] == ["tsx"] for c in norm_calls(old)), (
        "bash read the word as the value, so setup was NOT skipped"
    )
    new = drive(tmp_path, "py", ["--skip-setup", "yes"])
    assert new.out.code == 2, "a stray word is an unknown argument, never a silent value"


def test_delta_missing_secret_is_refused_before_anything_starts(
    tmp_path: pathlib.Path, reap: list[int | None]
) -> None:
    env = {
        "ACCOUNT_JWT_SECRET": "",
        "STRIPE_SANDBOX_SECRET_KEY": "sk_test_x",
        "FAKE_OUT_STRIPE": "Ready! signing secret is whsec_fake123",
    }
    old = drive(tmp_path, "bash", [], env, tools=("npx", "npm", "stripe"))
    new = drive(tmp_path, "py", [], env, tools=("npx", "npm", "stripe"))
    reap.extend([old.orphan, new.orphan])
    assert old.out.code == 1
    assert "ACCOUNT_JWT_SECRET" in old.out.err
    assert any(c["tool"] == "stripe" for c in old.out.calls), (
        "bash had already started stripe listen"
    )
    assert new.out.code == 1
    assert "ACCOUNT_JWT_SECRET must be set" in new.out.err
    assert not new.out.calls, "nothing was started"


def test_delta_the_backend_process_tree_is_stopped(
    tmp_path: pathlib.Path, reap: list[int | None]
) -> None:
    old, new = run_both(tmp_path, reap, ["--projects", "firefox"])
    assert old.out.code == new.out.code == 0
    assert orphan_alive(old), "bash killed the npx wrapper and left the backend's child running"
    assert not orphan_alive(new)


def test_delta_a_missing_checkout_fails_under_ci(tmp_path: pathlib.Path) -> None:
    results = []
    for name in ("bash", "py"):
        directory = tmp_path / name
        directory.mkdir()
        root = fixture(directory)
        (root / "private/account/package.json").unlink()
        results.append(drive(tmp_path, name + "2", ["--skip-setup"], {"CI": "true"}, root=root))
    old, new = results
    assert old.out.code == 0, "bash warned and passed"
    assert new.out.code == 1
    assert "submodules: true" in new.out.err
    outside_ci = drive(tmp_path, "py3", ["--skip-setup"], root=results[1].root)
    assert outside_ci.out.code == 0, "outside CI the skip is kept"
