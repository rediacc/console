"""`rediacc_ci.proxies.ops_host_check` against its bash twin
`.ci/scripts/test/proxies/proxy-ops-host-check.sh` (gate
`check:ci-proxy-ops-host-check`, `package.json:389`).

Sibling of `test_proxies_linux_packages.py`; see that file for why the two
invocations are compared byte for byte rather than as a finding set.

ONE CASE DRIVES THE REAL 213 MB renet binary. The rest point the twin's own
`RENET_BINARY` override (`:144`) at a two-line shim that prints a canned
report, which is the only way to drive a malformed one: the Go type
`Checks []HostCheckResult` (`private/renet/cmd/renet/ops_host.go:29`) cannot
emit anything else.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-ops-host-check.observations.jsonl` (9 rows,
9 distinct trees, 9 distinct finding sets), re-recorded on 2026-09-10 after the
jq-abort fix; the pre-fix rows were DISCARDED rather than appended to, because
two of them recorded the exit 0 the twin no longer gives.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.core import bash_dialect
from rediacc_ci.proxies import ops_host_check

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/test/proxies/proxy-ops-host-check.sh"
PORT_REL = ".ci/rediacc_ci/proxies/ops_host_check.py"
PORT_MODULE = "rediacc_ci.proxies.ops_host_check"
TWIN = ROOT / TWIN_REL

FIXTURE_FILES = (
    TWIN_REL,
    ".ci/scripts/test/proxies/proxy-lib.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/proxyx.py",
    ".ci/rediacc_ci/proxies/__init__.py",
    PORT_REL,
)

SHIM = '#!/bin/bash\ncat "$(dirname "$0")/report.json"\nexit "$(cat "$(dirname "$0")/rc")"\n'

GOOD_REPORT = {
    "platform": "linux",
    "arch": "amd64",
    "backend": "kvm",
    "checks": [
        {"name": "kvm", "value": "available", "status": "ok"},
        {"name": "virsh", "value": "not found", "status": "fail", "hint": "install libvirt"},
    ],
}

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None,
    reason="jq absent; both sides would report 77, proving nothing",
)


def build_fixture(
    tmp_path: pathlib.Path,
    *,
    report: str,
    rc: int = 0,
    port_source: str | None = None,
) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    for rel in FIXTURE_FILES:
        dst = fixture / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT / rel).read_bytes())
    (fixture / TWIN_REL).chmod(0o755)
    if port_source is not None:
        (fixture / PORT_REL).write_text(port_source, encoding="utf-8")
    shim = fixture / "shim"
    shim.mkdir(parents=True, exist_ok=True)
    (shim / "renet").write_text(SHIM, encoding="utf-8")
    (shim / "renet").chmod(0o755)
    (shim / "report.json").write_text(
        report if report.endswith("\n") else report + "\n", encoding="utf-8"
    )
    (shim / "rc").write_text(f"{rc}\n", encoding="utf-8")
    return fixture


def _env(fixture: pathlib.Path, path: str | None = None) -> dict[str, str]:
    return {
        "PATH": path if path is not None else os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "RENET_BINARY": str(fixture / "shim" / "renet"),
        "PYTHONPATH": str(fixture / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_both(
    fixture: pathlib.Path, *args: str, path: str | None = None
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    env = _env(fixture, path)
    kwargs = {"env": env, "cwd": str(fixture), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(fixture / TWIN_REL), *args], timeout=300, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, *args], timeout=300, check=False, **kwargs
    )
    return old, new


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s (%r)" % (
        old.returncode,
        new.returncode,
        old.stderr,
    )
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr


def _bin_without(tmp_path: pathlib.Path, drop: str) -> str:
    d = tmp_path / f"bin-no-{drop}"
    d.mkdir(exist_ok=True)
    for tool in (
        "bash",
        "sh",
        "env",
        "python3",
        "jq",
        "sed",
        "cat",
        "mktemp",
        "rm",
        "mkdir",
        "chmod",
        "dirname",
        "grep",
        "head",
        "tail",
        "printf",
        "cut",
        "tr",
        "sort",
        "wc",
        "uname",
    ):
        if tool == drop:
            continue
        src = shutil.which(tool)
        if src and not (d / tool).exists():
            (d / tool).symlink_to(src)
    return str(d)


def _real_tree_env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if os.environ.get("RENET_BINARY"):
        env["RENET_BINARY"] = os.environ["RENET_BINARY"]
    return env


# ---------------------------------------------------------------------------
# The real tree
# ---------------------------------------------------------------------------


def test_selftest_is_byte_identical() -> None:
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN), "--selftest"], timeout=180, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, "--selftest"], timeout=180, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "proxy ops-host-check selftest: 10 case(s) passed" in old.stdout
    assert "proxy-lib selftest: 4 case(s) passed" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_real_tree_agrees_byte_for_byte() -> None:
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN)], timeout=600, check=False, **kwargs
    )
    if old.returncode == 77:
        pytest.skip(f"the twin reports cannot-run here: {old.stderr.strip()[:200]}")
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE], timeout=600, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "2 check(s) passed, 2 requirement(s) present" in old.stdout
    assert "probe(s) reported --" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


# ---------------------------------------------------------------------------
# Fixture cases
# ---------------------------------------------------------------------------


def test_a_well_formed_report_satisfies_the_contract(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, report=json.dumps(GOOD_REPORT))
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert "the report satisfies the JSON contract" in old.stdout
    assert "2 probe(s) reported -- 1 ok, 0 warn, 1 fail on this host" in old.stdout
    assert "    - virsh: not found -- install libvirt" in old.stdout
    assert_same(old, new)


def test_a_malformed_report_names_every_violation(tmp_path: pathlib.Path) -> None:
    """And renders them as ONE bullet, because `:178` quotes `$FINDINGS`."""
    report = json.dumps(
        {
            "platform": "windows",
            "backend": "",
            "checks": [
                {"name": "a", "value": "v", "status": "okish"},
                {"name": "b", "value": "v", "status": "fail"},
                {"value": "v", "status": "ok"},
            ],
        }
    )
    fixture = build_fixture(tmp_path, report=report)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert '  - .platform is "windows" but this host is "linux"\n' in old.stderr
    # The three that follow share the SAME bullet: no `  - ` prefix on them.
    assert "\n.backend is missing or empty\n" in old.stderr
    assert '\nchecks[0] (a) has unknown status "okish"\n' in old.stderr
    assert "\nchecks[2] has no name\n" in old.stderr
    assert_same(old, new)


def test_an_empty_checks_array_is_a_failure_never_a_pass(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(
        tmp_path, report=json.dumps({"platform": "linux", "backend": "kvm", "checks": []})
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "the report enumerated nothing, so its green would mean nothing" in old.stderr
    assert_same(old, new)


def test_a_nonzero_subject_exit_is_not_masked(tmp_path: pathlib.Path) -> None:
    """CI writes `|| true` at ci-ops-test.yml:573-575. This proxy does not."""
    fixture = build_fixture(tmp_path, report=json.dumps(GOOD_REPORT), rc=3)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "exited 3 (CI masks this with '|| true'; this proxy does not)" in old.stderr
    assert_same(old, new)


def test_a_missing_jq_is_77_not_a_verdict(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, report=json.dumps(GOOD_REPORT))
    old, new = run_both(fixture, path=_bin_without(tmp_path, "jq"))
    assert old.returncode == 77
    assert "jq is not on PATH" in old.stderr
    assert_same(old, new)


# ---------------------------------------------------------------------------
# THE HOLE THAT WAS: a jq error folded into "no findings". FIXED 2026-09-10.
#
# Every case here reaches the validator through `RENET_BINARY`, which is the
# ONE override-reachable path to a malformed report: the subject is a Go binary
# whose `Checks []HostCheckResult` cannot emit anything else. Both directions
# are covered -- two that MUST fire, one that must NOT.
# ---------------------------------------------------------------------------


def test_a_checks_array_of_non_objects_is_now_a_named_refusal(tmp_path: pathlib.Path) -> None:
    """MUST FIRE. `:101`'s `2>/dev/null` used to turn jq's abort into silence.

    Every rule about name/value/status/hint evaporated on exactly the input it
    exists to catch, and the gate said the contract was satisfied (exit 0).
    Now jq's status is read, its diagnostic is kept, and the refusal names what
    was NOT asserted. Live paths today: zero, because `ops_host.go:29` declares
    `Checks []HostCheckResult`. Override-reachable paths: one, `RENET_BINARY`,
    and this test drives it.
    """
    fixture = build_fixture(
        tmp_path,
        report=json.dumps({"platform": "linux", "backend": "kvm", "checks": [1, 2, 3]}),
    )
    old, new = run_both(fixture)
    assert old.returncode == 1, "the twin must no longer certify this"
    assert "the report satisfies the JSON contract" not in old.stdout
    assert "VACUOUS: the per-entry contract check could not run -- jq exited 5" in old.stderr
    assert "NOTHING about checks[].{name,value,status,hint} was asserted" in old.stderr
    assert 'jq said: jq: error (at <stdin>:0): Cannot index number with string "name"' in (
        old.stderr
    )
    # The tally still collapses VISIBLY beside the refusal; it was the only
    # trace before the fix and it is kept, because printing the shape is not
    # the same as asserting it.
    assert "3 probe(s) reported --  ok,  warn,  fail on this host" in old.stdout
    assert old.stderr.count('Cannot index number with string "status"') == 3
    assert_same(old, new)


def test_checks_as_a_string_is_now_a_named_refusal(tmp_path: pathlib.Path) -> None:
    """MUST FIRE. jq's `length` of a 4-character string is 4, so the empty rule misses.

    Nothing else in the validator objected to `"checks":"nope"` before the fix:
    `to_entries` on a string aborted the program and the abort was discarded.
    The refusal now carries `to_entries`' OWN wording, which differs from the
    `.[]` wording the tally block emits three times just below it.
    """
    fixture = build_fixture(
        tmp_path,
        report=json.dumps({"platform": "linux", "backend": "kvm", "checks": "nope"}),
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "the report satisfies the JSON contract" not in old.stdout
    assert 'jq said: jq: error (at <stdin>:0): string ("nope") has no keys' in old.stderr
    assert "4 probe(s) reported --  ok,  warn,  fail on this host" in old.stdout
    assert old.stderr.count('Cannot iterate over string ("nope")') == 3
    assert_same(old, new)


def test_a_null_entry_is_still_read_field_by_field(tmp_path: pathlib.Path) -> None:
    """MUST NOT FIRE. jq's `null.name` is null, not an error, so no abort happens.

    This is the direction that would be quietly lost by "fixing" the hole with
    a blanket type guard: `checks:[null]` is reachable from a Go `json.Marshal`
    of a nil element, it must still be reported field by field, and it must NOT
    collapse into the one-line refusal.
    """
    fixture = build_fixture(
        tmp_path,
        report=json.dumps({"platform": "linux", "backend": "kvm", "checks": [None]}),
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "VACUOUS" not in old.stderr, "a null entry must not read as a jq abort"
    assert "checks[0] has no name" in old.stderr
    assert "checks[0] (?) has no value" in old.stderr
    assert "checks[0] (?) has no status" in old.stderr
    assert_same(old, new)


def test_a_non_object_document_emits_jqs_own_diagnostics(tmp_path: pathlib.Path) -> None:
    """`:61-63` do NOT discard stderr, so jq's text is part of the contract."""
    fixture = build_fixture(tmp_path, report="[1]")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert 'jq: error (at <stdin>:0): Cannot index array with string "platform"' in old.stderr
    assert 'jq: error (at <stdin>:1): Cannot index array with string "checks"' in old.stderr
    assert ".checks is empty; the report enumerated nothing" in old.stderr
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The ONE named divergence, pinned as still real rather than silently fixed
# ---------------------------------------------------------------------------


def test_a_two_document_stream_is_the_one_named_divergence(tmp_path: pathlib.Path) -> None:
    """jq reads a STREAM of values; `json.loads` reads exactly one.

    Unreachable from a Go `json.Marshal`, which emits one document. Both sides
    still go RED, so no green escapes -- but the bytes differ, and this pins
    the twin's half so a future reader does not mistake the port for the
    authority.
    """
    doc = json.dumps({"platform": "linux", "backend": "kvm", "checks": [{"name": "a"}]})
    fixture = build_fixture(tmp_path, report=f"{doc} {doc}")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert new.returncode == 1
    # The twin: bash's own arithmetic diagnostic, carrying its path and line.
    # Asked of the running bash rather than spelled: 5.3 says "arithmetic syntax
    # error" where 5.2 says "syntax error", and CI runs 5.2.
    assert bash_dialect.arith_syntax_error() in old.stderr
    assert 'is "linux\nlinux" but this host is "linux"' in old.stderr
    # The port: one document or nothing.
    assert "stdout is not parseable JSON" in new.stderr
    assert bash_dialect.arith_syntax_error() not in new.stderr


# ---------------------------------------------------------------------------
# The planted defect: this differential must be able to go RED
# ---------------------------------------------------------------------------


def test_a_planted_defect_in_the_port_is_caught(tmp_path: pathlib.Path) -> None:
    """The plant RE-OPENS the hole on the port side only.

    Swallowing the `_JqError` is exactly the shape the twin carried until
    2026-09-10, so this is the regression a future edit is most likely to
    reintroduce: the port would go back to exit 0 while the twin reds.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    marker = "    except _JqError as exc:\n        findings.append(\n"
    assert marker in source, "the jq-abort refusal moved; re-aim the plant"
    head, _sep, tail = source.partition(marker)
    close = tail.index("        )\n") + len("        )\n")
    planted = head + "    except _JqError:\n        pass\n" + tail[close:]
    assert planted != source

    report = json.dumps({"platform": "linux", "backend": "kvm", "checks": [1, 2, 3]})
    good = build_fixture(tmp_path / "good", report=report)
    old_g, new_g = run_both(good)
    assert_same(old_g, new_g)

    bad = build_fixture(tmp_path / "bad", report=report, port_source=planted)
    old_b, new_b = run_both(bad)
    assert (old_b.returncode, old_b.stdout) != (new_b.returncode, new_b.stdout), (
        "THE PLANT DID NOT FIRE"
    )
    assert old_b.returncode == 1, "the twin refuses"
    assert new_b.returncode == 0, "the planted port certifies it, which is the blindness"


# ---------------------------------------------------------------------------
# The pure validator, driven directly in BOTH directions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("want", "body"), [(w, b) for w, _, b in ops_host_check.SELFTEST_CASES])
def test_the_selftest_corpus_still_rules_the_way_the_twin_does(want: int, body: str) -> None:
    _, rc = ops_host_check.validate_report("linux", body)
    assert rc == want


def test_the_selftest_corpus_has_both_directions() -> None:
    """A validator with only positive controls will happily accept anything."""
    codes = {want for want, _, _ in ops_host_check.SELFTEST_CASES}
    assert codes == {0, 1}, codes
    assert len(ops_host_check.SELFTEST_CASES) == 10


def test_jq_alt_treats_false_as_absent_but_not_zero() -> None:
    """`a // b` fires on null OR false, which is why a `false` value is "missing"."""
    findings, rc = ops_host_check.validate_report(
        "linux",
        json.dumps(
            {
                "platform": "linux",
                "backend": "k",
                "checks": [{"name": "a", "value": False, "status": "ok"}],
            }
        ),
    )
    assert rc == 1
    assert findings == "checks[0] (a) has no value"

    _, rc_zero = ops_host_check.validate_report(
        "linux",
        json.dumps(
            {
                "platform": "linux",
                "backend": "k",
                "checks": [{"name": "a", "value": 0, "status": "ok"}],
            }
        ),
    )
    assert rc_zero == 0


def test_a_checks_object_keys_the_findings_on_the_key_string() -> None:
    findings, rc = ops_host_check.validate_report(
        "linux",
        json.dumps(
            {
                "platform": "linux",
                "backend": "k",
                "checks": {"zz": {"name": "", "value": "v", "status": "bogus"}},
            }
        ),
    )
    assert rc == 1
    assert "checks[zz] has no name" in findings
    assert 'checks[zz] () has unknown status "bogus"' in findings


def test_a_null_document_is_rejected_because_jq_e_says_so() -> None:
    assert ops_host_check.validate_report("linux", "null")[1] == 1
    assert ops_host_check.validate_report("linux", "false")[1] == 1
    # ... but a truthy non-object is NOT rejected there; it fails on the rules.
    findings, rc = ops_host_check.validate_report("linux", "[1]")
    assert rc == 1
    assert ".platform is missing or empty" in findings


def test_want_platform_for_covers_every_arm_including_the_empty_one() -> None:
    assert ops_host_check.want_platform_for("Linux") == "linux"
    assert ops_host_check.want_platform_for("Darwin") == "darwin"
    assert ops_host_check.want_platform_for("MINGW64_NT-10.0") == "windows"
    assert ops_host_check.want_platform_for("MSYS_NT-10.0") == "windows"
    assert ops_host_check.want_platform_for("CYGWIN_NT-10.0") == "windows"
    assert ops_host_check.want_platform_for("Plan9") == ""


def test_the_renet_report_type_is_still_a_slice_of_structs() -> None:
    """The measurement behind "live paths today: zero" in the module docstring.

    If this ever reads something else, the hole above stops being latent and
    the finding needs re-triaging rather than re-reading.
    """
    src = ROOT / "private" / "renet" / "cmd" / "renet" / "ops_host.go"
    if not src.is_file():
        pytest.skip("private/renet is not checked out")
    text = src.read_text(encoding="utf-8")
    assert 'Checks   []HostCheckResult `json:"checks"`' in text
