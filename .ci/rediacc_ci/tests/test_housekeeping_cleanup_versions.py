"""Differential: `rediacc_ci.housekeeping.cleanup_versions` against its twin
`.ci/scripts/housekeeping/cleanup-versions.sh` (2055 lines, 14 phases).

WHAT IS STUBBED, AND WHAT IS DELIBERATELY NOT.

STUBBED, on a prepended scratch PATH: `gh`, `curl`, `aws`, `sleep`. Those are
every external effect this program has. `gh` and `aws` and `curl` are recording
fakes: each logs its exact argv to `$FAKE_LOG` and answers from a per-case
fixture, so the CALL LOG is a first-class artifact of every case and is compared
byte for byte alongside the two output streams. Without them a single test run
would delete releases, tags, GHCR versions, deployments, Pages deployments,
Workers, D1 databases, Turnstile widgets, R2 objects, branches, workflow runs,
artifacts and caches from the real `rediacc` org. `sleep` is stubbed because
`retry_with_backoff 3 2` otherwise costs six real seconds per failing delete and
resolves through PATH on both sides, so one no-op answers for both.

NOT STUBBED: `date`, `jq`, `sort`, `grep`. The port EXECUTES `date` and `sort`
with the twin's argv, and the fake `gh` runs the REAL `jq` to apply whatever
`--jq` filter it was handed -- so the bytes both sides receive from `gh` come out
of the same jq the twin would have used, and the port's own jq reimplementations
are checked against that binary directly in
`test_jq_filters_agree_with_the_real_jq`.

THE CALL LOG IS THE PRIMARY ARTIFACT. Almost every hazard in this program is a
call that should or should not have been made: a dry run that deletes, a phase
that fails open and issues no calls at all, a retry that fires three times
instead of once, a `record_delete` that never happens. Text alone would miss all
of them, and several of the cases below assert on the log while the two output
streams are identically empty.

TIME IS NOT PINNED, AND THE FIXTURES ARE BUILT AROUND THAT. The two sides run
seconds apart and each calls `date -u +%s` for itself, so every fixture
timestamp is placed FAR from a decision boundary (days, or half-hours where the
twin prints hours). `test_the_two_sides_agree_on_ages_that_are_not_near_a_
boundary` is the control that this discipline is actually being followed.

K=5 LEDGER: `.ci/shadow/w7p6-cleanup-versions.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_versions as cv

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "housekeeping" / "cleanup-versions.sh"
PORT = pathlib.Path(cv.__file__).resolve()
BASH = shutil.which("bash") or "/bin/bash"
JQ = shutil.which("jq")

# Throwaway values. They authenticate nowhere, and the fakes never leave the
# machine, but they are pinned so that a leaked real `gh` would be using a token
# that cannot possibly work.
GH_TOKEN = "fixture-gh-token"  # noqa: S105 -- a fixture value, not a credential
CF_TOKEN = "fixture-cf-token"  # noqa: S105 -- a fixture value, not a credential
CF_ACCOUNT = "fixture-account"
R2_ENDPOINT = "https://fixture.r2.example/"

# The 14 phases, in `run_all_phases` order. Used by the coverage control at the
# bottom of this file, which fails if a phase gains no case.
PHASES = (
    "cleanup_releases",
    "cleanup_tags",
    "cleanup_packages",
    "cleanup_deployments",
    "cleanup_cf_pages",
    "cleanup_preview_workers",
    "cleanup_environments",
    "cleanup_d1_databases",
    "cleanup_orphan_turnstile_widgets",
    "cleanup_r2",
    "cleanup_stale_branches",
    "cleanup_workflow_runs",
    "cleanup_workflow_artifacts",
    "cleanup_actions_cache",
)

_EXERCISED: set[str] = set()


# ---------------------------------------------------------------------------
# The recording fakes
# ---------------------------------------------------------------------------

_FAKE_HEAD = '''#!/usr/bin/env python3
"""A recording fake. Logs argv, answers from $FAKE_FIXTURE, never leaves the box."""
import json
import os
import subprocess
import sys

NAME = os.path.basename(sys.argv[0])
ARGV = sys.argv[1:]

with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as fh:
    fh.write(NAME + "\\t" + "\\t".join(ARGV) + "\\n")
# The `call:` prefix is what the shadow-gate ledger scopes its --finding-re to.
# Without it every line this program prints is a log_step/log_info, which the
# comparator classifies as CHATTER before any message regex can see it, and
# every ledger row reads VACUOUS_BOTH_EMPTY.
sys.stderr.write("call: " + NAME + " " + " ".join(ARGV) + "\\n")
sys.stderr.flush()

with open(os.environ["FAKE_FIXTURE"], encoding="utf-8") as fh:
    FIXTURE = json.load(fh)

JOINED = " ".join(ARGV)


def answer(bucket):
    for rule in FIXTURE.get(bucket, []):
        if all(needle in JOINED for needle in rule["match"]):
            return rule
    return FIXTURE.get(bucket + "_default", {"rc": 1})


def emit(rule):
    rc = rule.get("rc", 0)
    text = rule.get("raw")
    if text is None and "json" in rule:
        text = json.dumps(rule["json"])
    if text is None:
        text = ""
    if rc == 0 and "--jq" in ARGV:
        # gh applies `--jq` itself, with its own jq. The fake uses the real one,
        # so both sides receive bytes a real gh could have produced.
        proc = subprocess.run(
            ["jq", "-r", ARGV[ARGV.index("--jq") + 1]],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            check=False,
        )
        sys.stdout.buffer.write(proc.stdout)
        sys.stdout.flush()
        sys.stderr.write(rule.get("stderr", ""))
        sys.exit(proc.returncode)
    sys.stdout.write(text)
    sys.stdout.flush()
    sys.stderr.write(rule.get("stderr", ""))
    sys.exit(rc)
'''

FAKE_GH = (
    _FAKE_HEAD
    + """
emit(answer("gh"))
"""
)

FAKE_CURL = (
    _FAKE_HEAD
    + """
emit(answer("curl"))
"""
)

FAKE_AWS = (
    _FAKE_HEAD
    + """
emit(answer("aws"))
"""
)

FAKE_SLEEP = '''#!/usr/bin/env python3
"""`sleep`, recorded and instant. See the module docstring."""
import os
import sys

with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as fh:
    fh.write("sleep\\t" + "\\t".join(sys.argv[1:]) + "\\n")
sys.exit(0)
'''

FAKES = {"gh": FAKE_GH, "curl": FAKE_CURL, "aws": FAKE_AWS, "sleep": FAKE_SLEEP}

# What the twin needs on PATH before it can speak at all. `tr` is here because
# `parse_args` -> `to_upper` forks it once PER FLAG (common.sh:302); without it
# the twin dies at 127 before any validation runs.
CURATED = ("dirname", "uname", "tr", "sed", "date", "cat", "sort", "head", "grep", "awk", "env")


def _stub_bin(base: pathlib.Path, *, drop: tuple[str, ...] = ()) -> str:
    """The fakes, prepended to the real PATH -- or a curated PATH when a case
    needs a tool to be ABSENT (the `require_cmd` cases)."""
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    for name, body in FAKES.items():
        if name in drop:
            continue
        fake = stub / name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    if not drop:
        return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))
    for name in (*CURATED, "jq", "python3"):
        if name in drop:
            continue
        real = shutil.which(name)
        assert real is not None, "%s is not on PATH; neither side can start" % name
        target = stub / name
        if not target.exists():
            target.symlink_to(real)
    return str(stub)


# The python driver, which is `source cleanup-versions.sh <args>; <phase>` with
# the words swapped. It exists so that ONE phase can be driven in isolation on
# the port exactly as the twin's own comment says a test drives one on the twin.
DRIVER = """
import sys
from rediacc_ci.core import common
from rediacc_ci.housekeeping import cleanup_versions as cv

phase = sys.argv[1]
try:
    housekeeping = cv.Housekeeping(sys.argv[2:])
except common.RefusalError as exc:
    exc.report()
    sys.exit(exc.code)
try:
    code = housekeeping.run_phase(phase)
except cv.ExpansionAbort:
    # bash resumes at the next TOP-LEVEL command after an expansion unwind;
    # `source x; <phase>` has none, so the shell ends with the failed
    # expansion's status. See ExpansionAbort in the port.
    code = 1
sys.exit(code)
"""


def _write_fixture(base: pathlib.Path, fixture: dict) -> pathlib.Path:
    path = base / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    return path


def _run(
    side: str,
    phase: str,
    argv: tuple[str, ...],
    fixture: dict,
    extra_env: dict,
    base: pathlib.Path,
) -> tuple[int, bytes, bytes, list[str]]:
    log = base / "calls.log"
    log.write_text("", encoding="utf-8")
    drop = tuple(x for x in extra_env.pop("_drop", "").split(",") if x)
    env = {
        "PATH": _stub_bin(base, drop=drop),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(log),
        "FAKE_FIXTURE": str(_write_fixture(base, fixture)),
        "GH_TOKEN": GH_TOKEN,
    }
    for key, value in list(extra_env.items()):
        # An EMPTY value means UNSET, because half the twin's branches are
        # `[[ -z "${X:-}" ]]` and `env["X"] = ""` cannot express the difference.
        if value == "":
            env.pop(key, None)
            extra_env.pop(key)
    env.update(extra_env)

    if side == "bash":
        script = 'source "%s" "$@"; %s' % (TWIN, phase)
        command = [BASH, "-c", script, "bash", *argv]
    else:
        command = [sys.executable, "-c", DRIVER, phase, *argv]

    proc = subprocess.run(
        command, capture_output=True, env=env, check=False, cwd=str(base), timeout=300
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


def sides(
    phase: str,
    *,
    argv: tuple[str, ...] = (),
    fixture: dict | None = None,
    env: dict | None = None,
) -> tuple[int, bytes, bytes, list[str]]:
    """Run BOTH implementations over the same fakes and assert byte equality.

    Returns the (shared) result so a case can go on to assert what the shared
    behaviour actually was -- which is the half that stops two identically wrong
    implementations from passing.
    """
    _EXERCISED.add(phase)
    fixture = fixture or {}
    results = []
    with tempfile.TemporaryDirectory() as td:
        for side in ("bash", "python"):
            base = pathlib.Path(td) / side
            base.mkdir(parents=True)
            results.append(_run(side, phase, argv, fixture, dict(env or {}), base))
    old, new = results
    assert new[0] == old[0], "%s: exit diverged: twin %r port %r\n twin err: %s\n port err: %s" % (
        phase,
        old[0],
        new[0],
        old[2].decode("utf-8", "replace"),
        new[2].decode("utf-8", "replace"),
    )
    assert new[1] == old[1], "%s: STDOUT diverged:\n twin: %r\n port: %r" % (
        phase,
        old[1],
        new[1],
    )
    assert new[2] == old[2], "%s: STDERR diverged:\n twin: %s\n port: %s" % (
        phase,
        old[2].decode("utf-8", "replace"),
        new[2].decode("utf-8", "replace"),
    )
    assert new[3] == old[3], "%s: CALL LOG diverged:\n twin: %s\n port: %s" % (
        phase,
        "\n".join(old[3]),
        "\n".join(new[3]),
    )
    return old


def rule(*match: str, json_body=None, raw=None, rc: int = 0, stderr: str = "") -> dict:
    """One fixture rule: every `match` substring must appear in the joined argv."""
    out: dict = {"match": list(match), "rc": rc}
    if json_body is not None:
        out["json"] = json_body
    if raw is not None:
        out["raw"] = raw
    if stderr:
        out["stderr"] = stderr
    return out


def cf_env(**overrides: str) -> dict:
    """The environment every Cloudflare phase needs before it will do anything."""
    env = {"CLOUDFLARE_API_TOKEN": CF_TOKEN, "CLOUDFLARE_ACCOUNT_ID": CF_ACCOUNT}
    env.update(overrides)
    return env


def ago(days: float) -> str:
    """An RFC3339 timestamp `days` in the past, deliberately off any boundary.

    Called with halves (`ago(30.5)`) so that the whole-day figure the twin prints
    is the same on both sides even though they compute it seconds apart.
    """
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def s3_ago(days: float) -> str:
    """`aws s3 ls` prints `YYYY-MM-DD HH:MM:SS` in two whitespace fields."""
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
    return when.strftime("%Y-%m-%d %H:%M:%S")


def calls_of(calls: list[str], tool: str) -> list[list[str]]:
    """The argv of every recorded call to one tool."""
    return [line.split("\t")[1:] for line in calls if line.split("\t")[0] == tool]


# ---------------------------------------------------------------------------
# CONTROLS. A fake that is not reached proves nothing, and a differential that
# cannot fail proves less.
# ---------------------------------------------------------------------------


def test_both_subjects_exist_where_this_file_says_they_do() -> None:
    assert TWIN.is_file(), TWIN
    assert PORT.is_file(), PORT
    assert os.access(PORT, os.X_OK), "%s is not executable" % PORT


def test_the_twin_parses_under_bash() -> None:
    proc = subprocess.run([BASH, "-n", str(TWIN)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_neither_side_can_reach_a_real_gh_curl_aws_or_sleep() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        for name in FAKES:
            assert shutil.which(name, path=path) == str(base / "bin" / name), name
        # And the tools BOTH sides execute for real must still be the real ones.
        for real in ("jq", "date", "sort", "grep", "awk"):
            found = shutil.which(real, path=path)
            assert found is not None, real
            assert not found.startswith(str(base)), real


def test_the_fake_gh_is_actually_reached_and_records_its_argv() -> None:
    """The control for every case below: if the fake were not on PATH, a phase
    with no findings would look exactly like a phase that was never called."""
    result = sides(
        "cleanup_releases",
        argv=("--dry-run",),
        fixture={"gh": [rule("release", "list", json_body=[])]},
    )
    assert calls_of(result[3], "gh") == [
        [
            "release",
            "list",
            "--repo",
            "rediacc/console",
            "--limit",
            "200",
            "--json",
            "tagName,createdAt,isDraft,isPrerelease",
            "--jq",
            "sort_by(.createdAt) | reverse",
        ]
    ]
    assert b"Releases: would delete 0 of 0" in result[2]


def test_the_differential_can_fail() -> None:
    """A comparison that cannot go red is not evidence. Two DIFFERENT fixtures
    through the same comparison must be distinguishable."""
    quiet = sides(
        "cleanup_releases",
        argv=("--dry-run",),
        fixture={"gh": [rule("release", "list", json_body=[])]},
    )
    loud = sides(
        "cleanup_releases",
        argv=("--dry-run", "--versions", "0", "--days", "1"),
        fixture={
            "gh": [
                rule("release", "list", json_body=[{"tagName": "v9.9.9", "createdAt": ago(400)}])
            ]
        },
    )
    assert quiet[2] != loud[2]
    assert b"[DRY-RUN] Would delete release: v9.9.9" in loud[2]


# ---------------------------------------------------------------------------
# THE PURE HALVES, driven against the real binaries they stand for.
# ---------------------------------------------------------------------------


def _bash_arith(word: str, other: str = "0") -> tuple[int, str]:
    """What the real bash makes of `[[ <other> -lt <word> ]]`. (status, stderr)."""
    proc = subprocess.run(
        [
            BASH,
            "-c",
            'set -euo pipefail; if [[ "$1" -lt "$2" ]]; then exit 0; else exit 1; fi',
            "bash",
            other,
            word,
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    return proc.returncode, proc.stderr


@pytest.mark.parametrize(
    "word",
    ["0", "1", "10", "010", "0x10", "007", "-5", "+5", "", "  7  ", "2#101", "16#ff"],
)
def test_arith_agrees_with_bash_on_words_bash_accepts(word: str) -> None:
    """The octal rule is the one that decides how many versions are KEPT."""
    status, stderr = _bash_arith(word, "9")
    assert stderr == "", "bash refused %r: %s" % (word, stderr)
    assert (cv.arith("9") < cv.arith(word)) == (status == 0), word


@pytest.mark.parametrize("word", ["08", "09", "1x", "0b1", "1.5"])
def test_bash_refuses_08_and_returns_false_without_aborting(word: str) -> None:
    """A refused word is FALSE plus a diagnostic, not a dead script.

    This is the control behind `arith_cmp`: the port must take the same branch,
    and the module docstring names the message text as the one divergence.
    """
    status, stderr = _bash_arith(word, "0")
    assert status == 1, word
    assert "error token" in stderr or "syntax error" in stderr, (word, stderr)
    assert cv.arith_cmp("0", "lt", word) is False, word


def _jq(filter_text: str, payload: str, *flags: str) -> str:
    proc = subprocess.run(
        ["jq", *flags, filter_text],
        input=payload.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, (filter_text, payload, proc.stderr)
    return proc.stdout.decode("utf-8")


# The corpus every filter is checked over. Deliberately includes the empty
# array, a null key, a missing key and a tie, because those are the four shapes
# a hand-written reimplementation gets wrong.
_CORPUS = [
    [],
    [{"a": "2026-01-01", "id": "x"}],
    [{"a": "2026-01-02", "id": "b"}, {"a": "2026-01-01", "id": "a"}],
    [{"a": "2026-01-01", "id": "b"}, {"a": "2026-01-01", "id": "a"}],
    [{"a": None, "id": "n"}, {"a": "2026-01-01", "id": "a"}],
    [{"id": "missing"}, {"a": "2026-01-01", "id": "a"}],
    [{"a": 3, "id": "three"}, {"a": "s", "id": "str"}, {"a": True, "id": "t"}],
]


@pytest.mark.skipif(JQ is None, reason="jq is not installed; the filters cannot be checked")
@pytest.mark.parametrize("payload", _CORPUS)
def test_jq_filters_agree_with_the_real_jq(payload: list) -> None:
    """Every jq filter the port reimplements, against the binary it replaces.

    `sort_by` is the interesting one, and the tie case in the corpus above is why:
    the port's first version broke ties on the whole element (which is what jq's
    `_sort_by_impl(map([f]))` reads like) and this test caught it. jq's sort is
    STABLE on the key alone.
    """
    text = json.dumps(payload)

    assert cv.jq_sort_by(payload, lambda d: d.get("a")) == json.loads(_jq("sort_by(.a)", text))
    assert list(reversed(cv.jq_sort_by(payload, lambda d: d.get("a")))) == json.loads(
        _jq("sort_by(.a) | reverse", text)
    )
    assert cv.jq_group_by(payload, lambda d: d.get("a")) == json.loads(_jq("group_by(.a)", text))
    assert cv.jq_unique([d.get("a") for d in payload]) == json.loads(_jq("[.[].a] | unique", text))
    assert cv.length_text(text) == _jq("length", text).rstrip("\n")
    assert cv.jq_flatten([payload, payload]) == json.loads(
        _jq("flatten", json.dumps([payload, payload]))
    )
    assert cv.jq_add([payload, payload]) == json.loads(_jq("add", json.dumps([payload, payload])))
    for entry in payload:
        assert cv.jq_text(entry.get("a")) == _jq(".a", json.dumps(entry), "-r").rstrip("\n")


@pytest.mark.skipif(JQ is None, reason="jq is not installed")
def test_the_empty_stream_is_not_a_zero() -> None:
    """`echo "" | jq 'length'` exits 0 and prints NOTHING, so `total` is the
    empty string and every later `-eq 0` reads it as zero. A port that answered
    "0" would print `Found 0 releases` where the twin prints `Found  releases`."""
    proc = subprocess.run(["jq", "length"], input=b"\n", capture_output=True, check=False)
    assert proc.returncode == 0
    assert proc.stdout == b""
    assert cv.length_text("") == ""
    assert cv.arith_cmp(cv.length_text(""), "eq", 0) is True


@pytest.mark.skipif(JQ is None, reason="jq is not installed")
def test_a_multi_page_blob_is_a_stream_of_values_not_one_document() -> None:
    """`gh api --paginate --jq '[...]'` emits one array PER PAGE. The twin slurps
    them with `jq -s 'flatten'`; a port that parsed one document would silently
    drop every page after the first."""
    blob = '[{"id":1}]\n[{"id":2}]\n'
    assert cv.json_values(blob) == [[{"id": 1}], [{"id": 2}]]
    assert cv.jq_flatten(cv.json_values(blob)) == json.loads(_jq("flatten", blob, "-s"))
    assert cv.length_text(blob) == _jq("length", blob).rstrip("\n")


def _awk(program: str, text: str) -> str:
    proc = subprocess.run(
        ["awk", program], input=text.encode("utf-8"), capture_output=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.decode("utf-8")


def test_the_pre_field_extractor_agrees_with_the_real_awk() -> None:
    """`awk '/^[[:space:]]*PRE[[:space:]]dryrun-/ {print $2}'`, per line."""
    lines = [
        "                           PRE dryrun-abc123/",
        "                           PRE pr-42/",
        "                           PRE v1.2.3/",
        "2026-01-01 00:00:00       12 cli/v1.2.3/rdc-linux",
        "   PRE dryrun-only-one-field",
        "",
    ]
    for line in lines:
        expected = _awk("/^[[:space:]]*PRE[[:space:]]dryrun-/ {print $2}", line + "\n").rstrip("\n")
        assert cv._awk_pre_field(line, cv._PRE_DRYRUN_RE) == expected, line


def test_the_channel_listing_awk_agrees_with_the_real_awk() -> None:
    """The 8f program, which is the largest awk in the file."""
    program = """{
                    n = split($4, p, "/"); fname = p[n];
                    if (fname !~ /^rediacc-cli[-_]/) next
                    rest = fname; sub(/^rediacc-cli[-_]/, "", rest);
                    if (match(rest, /^[0-9]+\\.[0-9]+\\.[0-9]+/)) {
                        semver = substr(rest, 1, RLENGTH);
                        after = substr(rest, RLENGTH + 1);
                        is_dev = (semver == "0.0.0" && after ~ /^-dev/) ? 1 : 0;
                        print $1"T"$2"Z""|"semver"|"is_dev"|"$4
                    }
                }"""
    listing = (
        "2026-01-02 03:04:05       12 apt/stable/rediacc-cli_1.2.3_amd64.deb\n"
        "2026-01-02 03:04:06       12 apt/stable/rediacc-cli-0.0.0-dev-abc.deb\n"
        "2026-01-02 03:04:07       12 apt/stable/Packages.gz\n"
        "2026-01-02 03:04:08       12 apt/stable/rediacc-cli-notasemver.deb\n"
        "2026-01-02 03:04:09       12 apt/stable/rediacc-cli-10.0.1.deb\n"
    )
    assert cv._awk_channel_listing(listing) == _awk(program, listing).rstrip("\n")


def test_grep_qx_is_a_whole_line_match() -> None:
    """`grep -qx "$pr" <<<"$open_prs"`: 4 must not match 42 or 142."""
    haystack = "42\n142\n4\n"
    for needle, expected in (("4", True), ("42", True), ("2", False), ("1", False)):
        proc = subprocess.run(
            [BASH, "-c", 'grep -qx "$1" <<<"$2"', "bash", needle, haystack],
            capture_output=True,
            check=False,
        )
        assert (proc.returncode == 0) is expected, needle
        assert cv._grep_qx(needle, haystack) is expected, needle


def test_bash_div_truncates_toward_zero() -> None:
    """`$((a / b))` is C division. Python's `//` floors, which differs on the
    negative numerator a future timestamp produces."""
    for numerator in (-7300, -1, 0, 1, 7300):
        proc = subprocess.run(
            [BASH, "-c", "echo $(( $1 / 3600 ))", "bash", str(numerator)],
            capture_output=True,
            check=False,
            text=True,
        )
        assert cv.bash_div(numerator, 3600) == int(proc.stdout.strip()), numerator


def test_records_and_stream_lines_differ_on_the_empty_input() -> None:
    """A here-string yields one empty record; a process substitution yields none.
    Both loops exist in the twin and they are not interchangeable."""
    assert cv.records("") == [""]
    assert cv._stream_lines("") == []
    assert cv.records("a\nb") == ["a", "b"]
    assert cv._stream_lines("a\nb\n") == ["a", "b"]
    assert cv._stream_lines("a\nb") == ["a", "b"]


# ---------------------------------------------------------------------------
# PHASE 1: GITHUB RELEASES
# ---------------------------------------------------------------------------


def _releases(*rows: tuple[str, str]) -> dict:
    return {
        "gh": [
            rule(
                "release",
                "list",
                json_body=[
                    {"tagName": t, "createdAt": c, "isDraft": False, "isPrerelease": False}
                    for t, c in rows
                ],
            ),
            rule("release", "delete"),
            rule("-X", "DELETE", "git/refs/tags"),
        ]
    }


def test_phase_1_keeps_by_index_and_by_window_and_deletes_when_neither_holds() -> None:
    """The OR in `should_retain`, all three arms, in one run."""
    result = sides(
        "cleanup_releases",
        argv=("--dry-run", "--versions", "1", "--days", "7"),
        fixture=_releases(("v3.0.0", ago(0.5)), ("v2.0.0", ago(1.5)), ("v1.0.0", ago(90.5))),
    )
    err = result[2].decode()
    assert "[DRY-RUN] Would delete release: v1.0.0" in err
    assert "v2.0.0" not in err, "inside the 7-day window, must be kept"
    # HAZARD 2: the dry-run arm of THIS phase does not count what it names.
    assert "Releases: would delete 0 of 3" in err


def test_phase_1_really_deletes_and_then_best_effort_deletes_the_tag() -> None:
    result = sides(
        "cleanup_releases",
        argv=("--versions", "0", "--days", "1"),
        fixture=_releases(("v1.0.0", ago(90.5))),
    )
    calls = calls_of(result[3], "gh")
    assert calls[1] == ["release", "delete", "v1.0.0", "--repo", "rediacc/console", "--yes"]
    assert calls[2] == [
        "api",
        "-X",
        "DELETE",
        "repos/rediacc/console/git/refs/tags/v1.0.0",
    ]
    assert b"Releases: deleted 1 of 1" in result[2]


def test_phase_1_retries_three_times_with_visible_backoff_then_warns() -> None:
    """Phase 1 is the ONE call site whose `retry_with_backoff` is not silenced by
    a `2>/dev/null`, so its `Attempt 1/3` lines are part of the output."""
    fixture = _releases(("v1.0.0", ago(90.5)))
    fixture["gh"][1] = rule("release", "delete", rc=1)
    result = sides("cleanup_releases", argv=("--versions", "0", "--days", "1"), fixture=fixture)
    err = result[2].decode()
    assert "Attempt 1/3 failed, retrying in 2s..." in err
    assert "Attempt 2/3 failed, retrying in 4s..." in err
    assert "Command failed after 3 attempts" in err
    assert "Failed to delete release: v1.0.0" in err
    assert [c for c in result[3] if c.startswith("sleep")] == ["sleep\t2", "sleep\t4"]
    assert b"Releases: deleted 0 of 1" in result[2]


def test_phase_1_stops_at_the_delete_budget_and_says_what_it_deferred() -> None:
    result = sides(
        "cleanup_releases",
        argv=("--versions", "0", "--days", "1"),
        fixture=_releases(("v2.0.0", ago(90.5)), ("v1.0.0", ago(91.5))),
        env={"MAX_DELETES_PER_RUN": "1"},
    )
    err = result[2].decode()
    assert "Phase 1: hit MAX_DELETES_PER_RUN=1; remaining releases deferred" in err
    assert "Releases: deleted 1 of 2" in err
    assert len([c for c in result[3] if "release\tdelete" in c]) == 1


def test_phase_1_reads_an_api_failure_as_an_empty_account() -> None:
    """HAZARD 1, pinned. A gh that fails is `[]`, and the phase reports a clean
    sweep of nothing rather than saying it could not look."""
    result = sides(
        "cleanup_releases",
        argv=("--dry-run",),
        fixture={"gh": [rule("release", "list", rc=1, stderr="gh: HTTP 503\n")]},
    )
    assert b"Releases: would delete 0 of 0" in result[2]
    assert result[0] == 0


def test_phase_1_retains_an_item_whose_date_cannot_be_parsed_and_says_so() -> None:
    result = sides(
        "cleanup_releases",
        argv=("--dry-run", "--versions", "0"),
        fixture=_releases(("v1.0.0", "not-a-date")),
    )
    assert b"Could not parse date 'not-a-date' - retaining item" in result[2]
    assert b"Releases: would delete 0 of 1" in result[2]


def test_phase_1_debug_output_is_identical_when_debug_is_true() -> None:
    """Most of this program's output is `log_debug`, which is invisible unless
    DEBUG=true. A differential that never sets it compares a third of the text."""
    result = sides(
        "cleanup_releases",
        argv=("--dry-run", "--versions", "5"),
        fixture=_releases(("v2.0.0", ago(1.5)), ("v1.0.0", ago(2.5))),
        env={"DEBUG": "true"},
    )
    err = result[2].decode()
    assert "[DEBUG] Found 2 releases" in err
    assert "[DEBUG] Keeping release: v2.0.0 (index=0)" in err
    assert "[DEBUG] Keeping release: v1.0.0 (index=1)" in err


def test_a_zero_padded_versions_value_is_octal_on_both_sides() -> None:
    """`--versions 010` keeps EIGHT, not ten, and does it silently.

    An operator's own flag value, read by bash's arithmetic rules. The ninth and
    tenth releases are outside the keep window on both sides.
    """
    rows = [("v%d.0.0" % (20 - i), ago(90.5 + i)) for i in range(10)]
    result = sides(
        "cleanup_releases",
        argv=("--dry-run", "--versions", "010", "--days", "1"),
        fixture=_releases(*rows),
    )
    err = result[2].decode()
    assert "Would delete release: v12.0.0" in err, "index 8 must fall outside keep-8"
    assert "Would delete release: v11.0.0" in err
    assert "Would delete release: v13.0.0" not in err, "index 7 is inside keep-8"


def test_an_invalid_octal_versions_value_takes_the_same_branch_on_both_sides() -> None:
    """`--versions 08` is a bash arithmetic REFUSAL: a diagnostic and FALSE.

    THE ONE NAMED DIVERGENCE. The decision, the exit code, the stdout and the
    entire call log are identical; only the text of the diagnostic differs,
    because bash names a file and a line number that this port cannot honestly
    claim. Asserted in both directions rather than skipped.
    """
    fixture = _releases(("v1.0.0", ago(0.5)))
    results = []
    with tempfile.TemporaryDirectory() as td:
        for side in ("bash", "python"):
            base = pathlib.Path(td) / side
            base.mkdir(parents=True)
            results.append(
                _run(side, "cleanup_releases", ("--dry-run", "--versions", "08"), fixture, {}, base)
            )
    old, new = results
    assert new[0] == old[0]
    assert new[1] == old[1]
    assert new[3] == old[3]
    assert 'value too great for base (error token is "08")' in old[2].decode()
    assert 'value too great for base (error token is "08")' in new[2].decode()
    assert "cleanup-versions.sh: line " in old[2].decode()
    assert "cleanup_versions.py: [[: " in new[2].decode()
    # And the DECISION was the same: index 0 was NOT inside the keep window, so
    # the release went to the retention check and was kept by the 14-day default.
    assert b"Releases: would delete 0 of 1" in old[2]
    assert b"Releases: would delete 0 of 1" in new[2]


# ---------------------------------------------------------------------------
# PHASE 2: GIT TAGS
# ---------------------------------------------------------------------------


def _tags_fixture(annotated: bool = True, *, dates: dict | None = None) -> dict:
    dates = dates or {"v2.0.0": ago(1.5), "v1.0.0": ago(400.5)}
    rules = [rule("repos/rediacc/console/tags", json_body=[{"name": n} for n in dates])]
    for name in dates:
        sha = "sha-%s" % name
        rules.append(
            rule(
                "git/ref/tags/%s" % name,
                json_body={"object": {"type": "tag" if annotated else "commit", "sha": sha}},
            )
        )
        rules.append(
            rule(
                "git/tags/%s" % sha,
                json_body={"tagger": {"date": dates[name]}, "object": {"sha": "c-" + sha}},
            )
        )
        rules.append(rule("git/commits/", sha, json_body={"committer": {"date": dates[name]}}))
    rules.append(rule("repos/rediacc/renet/tags", rc=1))
    rules.append(rule("-X", "DELETE", "git/refs/tags"))
    return {"gh": rules}


def test_phase_2_dates_an_annotated_tag_from_its_tagger_and_deletes_the_old_one() -> None:
    result = sides(
        "cleanup_tags",
        argv=("--versions", "1", "--days", "7"),
        fixture=_tags_fixture(annotated=True),
    )
    calls = calls_of(result[3], "gh")
    assert ["api", "repos/rediacc/console/tags", "--paginate", "--jq", ".[].name"] in calls
    assert [
        "api",
        "repos/rediacc/console/git/tags/sha-v2.0.0",
        "--jq",
        ".tagger.date",
    ] in calls
    err = result[2].decode()
    assert "Tags (rediacc/console): deleted 1 of 2" in err
    assert "No tags found for rediacc/renet" not in err, "log_debug is off by default"
    assert [
        "api",
        "-X",
        "DELETE",
        "repos/rediacc/console/git/refs/tags/v1.0.0",
    ] in calls


def test_phase_2_falls_back_to_the_commit_date_for_a_lightweight_tag() -> None:
    """Three calls instead of two, and the twin makes them for every tag it will
    go on to keep as well."""
    result = sides(
        "cleanup_tags",
        argv=("--dry-run", "--versions", "0", "--days", "7"),
        fixture=_tags_fixture(annotated=False),
        env={"DEBUG": "true"},
    )
    calls = calls_of(result[3], "gh")
    assert [
        "api",
        "repos/rediacc/console/git/commits/sha-v1.0.0",
        "--jq",
        ".committer.date",
    ] in calls
    assert b"[DRY-RUN] Would delete tag: v1.0.0" in result[2]


def test_phase_2_resolves_an_annotated_tag_with_no_tagger_date_in_two_more_calls() -> None:
    """The fallback inside the fallback, and the only path that reaches
    `git/tags/<sha> --jq .object.sha`.

    An annotated tag whose tagger date is missing needs the tag OBJECT resolved
    to its target commit before the commit date can be read, so the twin makes
    FOUR calls for that one tag. A port that reused the ref sha as the commit sha
    would still produce the right date here and the wrong call log, which is why
    this case exists: it was added after a planted defect of exactly that shape
    failed to turn anything red.
    """
    result = sides(
        "cleanup_tags",
        argv=("--dry-run", "--versions", "0", "--days", "7"),
        fixture={
            "gh": [
                rule("repos/rediacc/console/tags", json_body=[{"name": "v1.0.0"}]),
                rule(
                    "git/ref/tags/v1.0.0", json_body={"object": {"type": "tag", "sha": "annot-sha"}}
                ),
                # The tag-object call FAILS, which is the only way to reach the
                # fallback: a tag object that merely LACKS `.tagger.date` makes
                # gh print the four characters `null`, which is not empty. See
                # the case below.
                rule("git/tags/annot-sha", ".tagger.date", rc=1),
                rule(
                    "git/tags/annot-sha",
                    ".object.sha",
                    json_body={"object": {"sha": "commit-sha"}},
                ),
                rule("git/commits/commit-sha", json_body={"committer": {"date": ago(400.5)}}),
                rule("repos/rediacc/renet/tags", rc=1),
            ]
        },
    )
    calls = calls_of(result[3], "gh")
    assert calls[1] == ["api", "repos/rediacc/console/git/ref/tags/v1.0.0"]
    assert calls[2] == ["api", "repos/rediacc/console/git/tags/annot-sha", "--jq", ".tagger.date"]
    assert calls[3] == ["api", "repos/rediacc/console/git/tags/annot-sha", "--jq", ".object.sha"]
    assert calls[4] == [
        "api",
        "repos/rediacc/console/git/commits/commit-sha",
        "--jq",
        ".committer.date",
    ]
    assert b"[DRY-RUN] Would delete tag: v1.0.0" in result[2]


def test_phase_2_a_tag_object_with_no_tagger_date_yields_the_string_null() -> None:
    """`gh api --jq '.tagger.date'` on an object without one prints `null`, and
    the twin tests for EMPTY, so the fallback is not taken and the four
    characters travel on as the tag's date. `date -d null` then fails and the
    tag is retained with a message that quotes it back.

    Reproduced, not repaired: it is the twin's behaviour, it errs toward keeping,
    and it is the only reason `jq_text` renders a missing key as `null`.
    """
    result = sides(
        "cleanup_tags",
        argv=("--dry-run", "--versions", "0", "--days", "7"),
        fixture={
            "gh": [
                rule("repos/rediacc/console/tags", json_body=[{"name": "v1.0.0"}]),
                rule("git/ref/tags/v1.0.0", json_body={"object": {"type": "tag", "sha": "s"}}),
                rule("git/tags/s", json_body={"tagger": {}}),
                rule("repos/rediacc/renet/tags", rc=1),
            ]
        },
    )
    assert b"Could not parse date 'null' - retaining item" in result[2]
    assert b"Tags (rediacc/console): would delete 0 of 1" in result[2]


def test_phase_2_says_nothing_when_the_tag_list_call_fails() -> None:
    """A repo whose tag list 404s is `log_debug`, so on a normal nightly this
    phase reports NOTHING AT ALL for that repo. HAZARD 1 again."""
    result = sides(
        "cleanup_tags",
        argv=("--dry-run",),
        fixture={"gh": [rule("tags", rc=1)]},
        env={"DEBUG": "true"},
    )
    err = result[2].decode()
    assert "[DEBUG]   No tags found for rediacc/console" in err
    assert "[DEBUG]   No tags found for rediacc/renet" in err
    assert "Tags (rediacc/console):" not in err


def test_phase_2_retry_is_silenced_by_the_call_sites_redirection() -> None:
    """`retry_with_backoff ... 2>/dev/null` covers the FUNCTION, so the three
    `Attempt N/3` lines Phase 1 prints are invisible here. Getting this wrong
    would add three lines per failing delete."""
    fixture = _tags_fixture(annotated=True)
    fixture["gh"][-1] = rule("-X", "DELETE", "git/refs/tags", rc=1)
    result = sides("cleanup_tags", argv=("--versions", "0", "--days", "7"), fixture=fixture)
    err = result[2].decode()
    assert "Attempt 1/3" not in err
    assert "Command failed after 3 attempts" not in err
    assert "Failed to delete tag: v1.0.0" in err
    # One deletable tag, three attempts, two backoffs: 2s then 4s.
    assert [c for c in result[3] if c.startswith("sleep")] == ["sleep\t2", "sleep\t4"]
    assert len([c for c in result[3] if "-X\tDELETE" in c]) == 3


# ---------------------------------------------------------------------------
# PHASE 3: GHCR PACKAGE VERSIONS
# ---------------------------------------------------------------------------


def _package_version(vid: int, created: str, tags: list | None = None) -> dict:
    return {
        "id": vid,
        "created_at": created,
        "metadata": {"container": {"tags": tags if tags is not None else []}},
    }


def test_phase_3_deletes_the_old_tail_and_reports_per_package() -> None:
    result = sides(
        "cleanup_packages",
        argv=("--dry-run", "--versions", "1", "--days", "7"),
        fixture={
            "gh": [
                rule(
                    "packages/container/renet/versions",
                    json_body=[
                        _package_version(2, ago(1.5), ["latest"]),
                        _package_version(1, ago(400.5), ["old", "older"]),
                    ],
                ),
                rule("packages/container/rdc/versions", json_body=[]),
                rule("packages/container/server/versions", rc=1),
            ]
        },
    )
    err = result[2].decode()
    assert "[DRY-RUN] Would delete version: 1 (tags: old, older, created:" in err
    assert "Package renet: would delete 1 of 2 versions" in err
    assert "Package rdc: would delete 0 of 0 versions" in err
    # The inaccessible package is SKIPPED with a warning and no summary line.
    assert "Skipping server: package not accessible" in err
    assert "Package server:" not in err


def test_phase_3_stops_a_package_after_five_consecutive_delete_failures() -> None:
    versions = [_package_version(i, ago(400.5 + i)) for i in range(8)]
    result = sides(
        "cleanup_packages",
        argv=("--versions", "0", "--days", "7"),
        fixture={
            "gh": [
                rule("packages/container/renet/versions?", json_body=versions),
                rule("packages/container/rdc/versions", json_body=[]),
                rule("packages/container/server/versions", json_body=[]),
                rule("-X", "DELETE", "packages/container", rc=1, raw="HTTP 422: still tagged"),
            ]
        },
    )
    err = result[2].decode()
    # `api_output="$(gh api ... 2>&1)"` MERGES the streams, so whatever gh wrote
    # to stderr is part of the warning. The recording fake writes its `call:`
    # line there, and both sides carry it identically -- which is itself the
    # evidence that the merge is being reproduced.
    assert "Could not delete version 0 (tags: ): call: gh api -X DELETE" in err
    assert "HTTP 422: still tagged" in err
    assert "Skipping remaining versions for renet after 5 consecutive failures" in err
    assert len([c for c in result[3] if "-X\tDELETE" in c]) == 5


def test_phase_3_pagination_stops_short_and_says_which_pages_it_kept() -> None:
    """A page that fails AFTER page 1 is a partial list, and the twin proceeds
    with the newest-first prefix it already has rather than skipping the
    package. The message names the page count, so an off-by-one shows."""
    page1 = [_package_version(i, ago(400.5 + i)) for i in range(100)]
    result = sides(
        "cleanup_packages",
        argv=("--dry-run", "--versions", "200", "--days", "7"),
        fixture={
            "gh": [
                rule("renet/versions?per_page=100&page=1", json_body=page1),
                rule("renet/versions?per_page=100&page=2", rc=1),
                rule("rdc/versions", json_body=[]),
                rule("server/versions", json_body=[]),
            ]
        },
    )
    assert (
        b"Page 2 fetch failed for renet; proceeding with the 1 page(s) already fetched" in result[2]
    )
    assert b"Package renet: would delete 0 of 100 versions" in result[2]


def test_phase_3_treats_a_non_array_page_as_inaccessible_rather_than_dying() -> None:
    """`jq -e 'type == "array"'` with both streams discarded: an error OBJECT and
    malformed bytes are both a soft skip here, unlike everywhere else."""
    result = sides(
        "cleanup_packages",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule("renet/versions", raw='{"message":"Not Found"}'),
                rule("rdc/versions", raw="}{ not json at all"),
                rule("server/versions", json_body=[]),
            ]
        },
    )
    err = result[2].decode()
    assert "Skipping renet: package not accessible" in err
    assert "Skipping rdc: package not accessible" in err
    assert result[0] == 0


# ---------------------------------------------------------------------------
# PHASE 4: GITHUB DEPLOYMENTS
# ---------------------------------------------------------------------------


def _deployments(*rows: tuple[int, str, str]) -> list:
    return [{"id": i, "environment": e, "created_at": c} for i, e, c in rows]


def test_phase_4_keeps_two_per_environment_and_none_for_a_closed_pr() -> None:
    result = sides(
        "cleanup_deployments",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule("pr", "list", json_body=[{"number": 7}]),
                rule(
                    "deployments?per_page=100",
                    json_body=_deployments(
                        (1, "edge", ago(3.5)),
                        (2, "edge", ago(2.5)),
                        (3, "edge", ago(1.5)),
                        (4, "pr-7", ago(1.5)),
                        (5, "pr-9", ago(1.5)),
                    ),
                ),
            ]
        },
    )
    err = result[2].decode()
    # edge keeps the two newest (3, 2) and drops the oldest (1).
    assert "[DRY-RUN] Would delete: 1 (edge," in err
    assert "Would delete: 2 (edge" not in err
    # pr-7 is OPEN, so it keeps 2 of its 1; pr-9 is closed, so keep 0.
    assert "Would delete: 4 (pr-7" not in err
    assert "[DRY-RUN] Would delete: 5 (pr-9," in err
    assert (
        "Deployments (rediacc/console): deleted 2 of 5 (keeping 2 per environment, 0 for closed-PR pr-*)"
        in err
    )


def test_phase_4_falls_back_to_keep_n_when_the_open_pr_lookup_fails() -> None:
    """FAILS OPEN, deliberately, and the twin's comment says why: its worst case
    is retaining too much history. Compare with Phase 5b below, which skips."""
    result = sides(
        "cleanup_deployments",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule("pr", "list", rc=1),
                rule(
                    "deployments?per_page=100",
                    json_body=_deployments(
                        (1, "pr-9", ago(3.5)), (2, "pr-9", ago(2.5)), (3, "pr-9", ago(1.5))
                    ),
                ),
            ]
        },
    )
    err = result[2].decode()
    assert "Could not list open PRs; pr-* deployments fall back to keep-2" in err
    assert "[DRY-RUN] Would delete: 1 (pr-9," in err
    assert "Would delete: 2 (pr-9" not in err


def test_phase_4_sets_a_deployment_inactive_before_deleting_it() -> None:
    result = sides(
        "cleanup_deployments",
        fixture={
            "gh": [
                rule("pr", "list", json_body=[]),
                rule(
                    "deployments?per_page=100",
                    json_body=_deployments((1, "pr-9", ago(3.5))),
                ),
                rule("statuses", "-X", "POST"),
                rule("-X", "DELETE", "deployments/1"),
            ]
        },
    )
    calls = calls_of(result[3], "gh")
    assert calls[2] == [
        "api",
        "repos/rediacc/console/deployments/1/statuses",
        "-X",
        "POST",
        "-f",
        "state=inactive",
    ]
    assert calls[3] == ["api", "-X", "DELETE", "repos/rediacc/console/deployments/1"]
    assert b"deleted 1 of 1" in result[2]


def test_phase_4_multi_page_deployments_are_flattened_not_dropped() -> None:
    """`--paginate` emits one array per page and the twin slurps them. A port
    that read one document would keep everything on page 2."""
    page = json.dumps(_deployments((1, "edge", ago(3.5)), (2, "edge", ago(2.5))))
    page2 = json.dumps(_deployments((3, "edge", ago(1.5)), (4, "edge", ago(0.5))))
    result = sides(
        "cleanup_deployments",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule("pr", "list", json_body=[]),
                rule("deployments?per_page=100", raw=page + "\n" + page2 + "\n"),
            ]
        },
    )
    err = result[2].decode()
    assert "deleted 2 of 4" in err
    assert "[DRY-RUN] Would delete: 1 (edge," in err
    assert "[DRY-RUN] Would delete: 2 (edge," in err


def test_phase_4_budget_exhaustion_breaks_out_of_both_loops() -> None:
    """`break 2`. With the budget gone, the SECOND environment must not be
    processed at all, which only the call log can show."""
    result = sides(
        "cleanup_deployments",
        fixture={
            "gh": [
                rule("pr", "list", json_body=[]),
                rule(
                    "deployments?per_page=100",
                    json_body=_deployments(
                        (1, "aaa", ago(3.5)),
                        (2, "aaa", ago(2.5)),
                        (3, "aaa", ago(1.5)),
                        (4, "zzz", ago(3.5)),
                        (5, "zzz", ago(2.5)),
                        (6, "zzz", ago(1.5)),
                    ),
                ),
                rule("statuses", "-X", "POST"),
                rule("-X", "DELETE", "deployments/"),
            ]
        },
        env={"MAX_DELETES_PER_RUN": "0"},
    )
    assert b"Phase 4: hit MAX_DELETES_PER_RUN=0" in result[2]
    assert len([c for c in result[3] if "-X\tDELETE" in c]) == 0
    assert result[2].decode().count("hit MAX_DELETES_PER_RUN") == 1


# ---------------------------------------------------------------------------
# PHASE 5: CLOUDFLARE PAGES PREVIEW DEPLOYMENTS
# ---------------------------------------------------------------------------


def _cf_pages(*rows: tuple[str, str, str], success: bool = True) -> dict:
    return {
        "success": success,
        "result": [
            {"id": i, "created_on": c, "deployment_trigger": {"metadata": {"branch": b}}}
            for i, c, b in rows
        ],
    }


@pytest.mark.parametrize("missing", ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"])
def test_the_cloudflare_phases_skip_when_either_credential_is_unset(missing: str) -> None:
    """Four phases share this guard and each has its own wording. An empty env
    value is UNSET here, which is the distinction `[[ -z "${X:-}" ]]` makes."""
    for phase, text in (
        ("cleanup_cf_pages", "skipping CF Pages cleanup"),
        ("cleanup_preview_workers", "skipping Worker cleanup"),
        ("cleanup_d1_databases", "skipping D1 cleanup"),
        ("cleanup_orphan_turnstile_widgets", "skipping Turnstile cleanup"),
    ):
        result = sides(phase, env=cf_env(**{missing: ""}))
        assert text.encode() in result[2], phase
        assert result[3] == [], "no call may be made without credentials"


def test_phase_5_skips_the_latest_deployment_per_branch_and_reaps_the_rest() -> None:
    """The CF API refuses to delete the newest deployment of a branch, so the
    phase computes that set with `group_by` and counts the skips separately."""
    result = sides(
        "cleanup_cf_pages",
        argv=("--dry-run", "--versions", "0", "--days", "7"),
        fixture={
            "curl": [
                rule(
                    "pages/projects/rediacc/deployments",
                    json_body=_cf_pages(
                        ("d3", ago(1.5), "main"),
                        ("d2", ago(40.5), "main"),
                        ("d1", ago(41.5), "feature"),
                    ),
                )
            ]
        },
        env=cf_env(),
    )
    err = result[2].decode()
    assert "[DRY-RUN] Would delete CF deployment: d2 (branch: main," in err
    assert "Would delete CF deployment: d3" not in err, "newest on main is undeletable"
    assert "Would delete CF deployment: d1" not in err, "only deployment on feature"
    assert (
        "CF Pages (rediacc): would delete 0 of 3 preview deployments (2 latest-per-branch, skipped)"
        in err
    )


def test_phase_5_really_deletes_with_force_and_counts_the_success_flag() -> None:
    result = sides(
        "cleanup_cf_pages",
        argv=("--versions", "0", "--days", "7"),
        fixture={
            "curl": [
                rule(
                    "deployments/d2?force=true",
                    "-X DELETE",
                    json_body={"success": True},
                ),
                rule(
                    "pages/projects/rediacc/deployments",
                    json_body=_cf_pages(("d3", ago(1.5), "main"), ("d2", ago(40.5), "main")),
                ),
            ]
        },
        env=cf_env(),
    )
    curls = calls_of(result[3], "curl")
    assert curls[1][:5] == [
        "-s",
        "-X",
        "DELETE",
        (
            "https://api.cloudflare.com/client/v4/accounts/fixture-account/pages/"
            "projects/rediacc/deployments/d2?force=true"
        ),
        "-H",
    ]
    assert b"CF Pages (rediacc): deleted 1 of 2" in result[2]


def test_phase_5_a_delete_that_reports_success_false_is_a_warning_not_a_failure() -> None:
    result = sides(
        "cleanup_cf_pages",
        argv=("--versions", "0", "--days", "7"),
        fixture={
            "curl": [
                rule("-X DELETE", json_body={"success": False, "errors": ["nope"]}),
                rule(
                    "pages/projects",
                    json_body=_cf_pages(("d3", ago(1.5), "main"), ("d2", ago(40.5), "main")),
                ),
            ]
        },
        env=cf_env(),
    )
    assert b"Failed to delete CF deployment: d2 (branch: main)" in result[2]
    assert b"CF Pages (rediacc): deleted 0 of 2" in result[2]
    assert result[0] == 0


def test_phase_5_a_failed_list_page_breaks_the_pagination_loop() -> None:
    result = sides(
        "cleanup_cf_pages",
        argv=("--dry-run",),
        fixture={"curl": [rule("pages/projects", json_body={"success": False})]},
        env=cf_env(),
    )
    err = result[2].decode()
    assert "CF API request failed on page 1" in err
    assert (
        "CF Pages (rediacc): would delete 0 of 0 preview deployments (0 latest-per-branch, skipped)"
        in err
    )


def test_phase_5_pagination_asks_for_page_2_only_when_page_1_was_full() -> None:
    """`per_page=25`, and the loop stops the moment a page is short. Only the
    call log shows that the second request was or was not made."""
    full = _cf_pages(*[("d%02d" % i, ago(40.5 + i), "b%02d" % i) for i in range(25)])
    result = sides(
        "cleanup_cf_pages",
        argv=("--dry-run",),
        fixture={
            "curl": [
                # `&page=2`, not `page=2`: `per_page=25` CONTAINS `page=2`, and the
                # first version of this fixture matched page 1 with the page-2
                # rule for exactly that reason.
                rule("&page=2", json_body=_cf_pages(("d99", ago(80.5), "b99"))),
                rule("&page=1", json_body=full),
            ]
        },
        env=cf_env(),
    )
    urls = [c[3] for c in calls_of(result[3], "curl")]
    assert any("&page=1" in u for u in urls)
    assert any("&page=2" in u for u in urls), urls
    assert not any("&page=3" in u for u in urls), "page 2 was short, so there is no page 3"
    assert b"would delete 0 of 26 preview deployments (26 latest-per-branch, skipped)" in result[2]


# ---------------------------------------------------------------------------
# PHASE 5b: ORPHANED PER-PR PREVIEW WORKERS
# ---------------------------------------------------------------------------


def test_phase_5b_fails_closed_when_the_open_pr_list_is_unreadable() -> None:
    """The mirror image of Phase 4. Here the worst case is deleting a LIVE
    preview, so an unreadable PR list skips the phase and no curl is made."""
    result = sides(
        "cleanup_preview_workers",
        fixture={"gh": [rule("pr", "list", rc=1)]},
        env=cf_env(),
    )
    assert b"SKIPPING Worker cleanup rather than deleting on incomplete data" in result[2]
    assert calls_of(result[3], "curl") == []


def test_phase_5b_deletes_only_pr_workers_whose_pr_is_closed() -> None:
    result = sides(
        "cleanup_preview_workers",
        fixture={
            "gh": [rule("pr", "list", json_body=[{"number": 7}])],
            "curl": [
                rule("-X DELETE", "scripts/pr-3", json_body={"success": True}),
                rule(
                    "workers/scripts",
                    json_body={
                        "success": True,
                        "result": [{"id": "pr-3"}, {"id": "pr-7"}, {"id": "www-production"}],
                    },
                ),
            ],
        },
        env=cf_env(),
    )
    err = result[2].decode()
    assert "Deleted Worker: pr-3 (PR #3 closed)" in err
    assert "pr-7" not in err, "PR 7 is open"
    assert "Workers: 3 script(s) seen, 1 orphan(s) deleted" in err


def test_phase_5b_does_not_charge_the_delete_budget() -> None:
    """HAZARD 3, and the budget is the only way to see it.

    `MAX_DELETES_PER_RUN=1` with TWO orphans: if the success arm called
    `record_delete` like every other phase, the second delete would trip the
    budget and print the deferral line. It does not, so both go.
    """
    result = sides(
        "cleanup_preview_workers",
        fixture={
            "gh": [rule("pr", "list", json_body=[])],
            "curl": [
                rule("-X DELETE", json_body={"success": True}),
                rule(
                    "workers/scripts",
                    json_body={"success": True, "result": [{"id": "pr-3"}, {"id": "pr-4"}]},
                ),
            ],
        },
        env=cf_env(MAX_DELETES_PER_RUN="1"),
    )
    err = result[2].decode()
    assert "Deleted Worker: pr-3" in err
    assert "Deleted Worker: pr-4" in err
    assert "hit MAX_DELETES_PER_RUN" not in err
    assert "Workers: 2 script(s) seen, 2 orphan(s) deleted" in err


def test_phase_5b_dry_run_says_would_be_deleted() -> None:
    result = sides(
        "cleanup_preview_workers",
        argv=("--dry-run",),
        fixture={
            "gh": [rule("pr", "list", json_body=[])],
            "curl": [
                rule("workers/scripts", json_body={"success": True, "result": [{"id": "pr-3"}]})
            ],
        },
        env=cf_env(),
    )
    err = result[2].decode()
    assert "[DRY-RUN] Would delete Worker: pr-3 (PR #3 closed)" in err
    assert "Workers: 1 script(s) seen, 1 orphan(s) would be deleted" in err
    assert calls_of(result[3], "curl")[-1][2] == "GET", "no DELETE in a dry run"


# ---------------------------------------------------------------------------
# PHASE 6: GITHUB ENVIRONMENTS
# ---------------------------------------------------------------------------


def test_phase_6_is_a_403_by_design_and_stops_after_the_first_one() -> None:
    """HAZARD 4. `check-no-app-admin-perm.sh` forbids the permission this needs,
    so the 403 arm logs at INFO and breaks rather than warning per environment."""
    result = sides(
        "cleanup_environments",
        fixture={
            "gh": [
                rule(
                    "repos/rediacc/console/environments",
                    "--jq",
                    json_body={
                        "environments": [
                            {"name": "pr-1", "created_at": ago(9.5), "updated_at": ago(9.5)},
                            {"name": "pr-2", "created_at": ago(9.5), "updated_at": ago(9.5)},
                            {"name": "edge", "created_at": ago(9.5), "updated_at": ago(9.5)},
                        ]
                    },
                ),
                rule("pr", "view", "1", json_body={"state": "OPEN"}),
                rule("pr", "view", "2", json_body={"state": "MERGED"}),
                rule("-X", "DELETE", "environments/", rc=1),
            ]
        },
        env={"DEBUG": "true"},
    )
    err = result[2].decode()
    assert "[DEBUG]   Found 2 pr-* environments" in err, "edge must not be in scope"
    assert (
        "Environment pr-2 left in place (by design: the App is barred from Administration:write)"
        in err
    )
    assert "Environments (rediacc/console): deleted 0 of 2 pr-* environments" in err


def test_phase_6_says_nothing_to_do_when_there_are_no_pr_environments() -> None:
    result = sides(
        "cleanup_environments",
        fixture={"gh": [rule("environments", json_body={"environments": []})]},
    )
    assert b"No stale preview environments to clean up" in result[2]
    assert b"Environments (rediacc/console):" not in result[2]


# ---------------------------------------------------------------------------
# PHASE 7: CLOUDFLARE D1 PREVIEW DATABASES
# ---------------------------------------------------------------------------


def test_phase_7_deletes_a_closed_prs_database_and_keeps_an_open_ones() -> None:
    result = sides(
        "cleanup_d1_databases",
        fixture={
            "gh": [
                rule("pr", "view", "7", json_body={"state": "OPEN"}),
                rule("pr", "view", "3", json_body={"state": "CLOSED"}),
            ],
            "curl": [
                rule("-X DELETE", "d1/database/uuid-3", json_body={"success": True}),
                rule(
                    "d1/database?per_page=100",
                    json_body={
                        "success": True,
                        "result": [
                            {"name": "account-db-pr-3", "uuid": "uuid-3"},
                            {"name": "account-db-pr-7", "uuid": "uuid-7"},
                            {"name": "account-db-production", "uuid": "uuid-p"},
                        ],
                    },
                ),
            ],
        },
        env=cf_env(),
    )
    err = result[2].decode()
    assert "Deleted D1 database: account-db-pr-3 (PR #3 state: CLOSED)" in err
    assert "D1 databases: deleted 1 of 2 (1 open PRs, skipped)" in err


def test_phase_7_reports_an_unreadable_list_and_stops() -> None:
    result = sides(
        "cleanup_d1_databases",
        fixture={"curl": [rule("d1/database", json_body={"success": False})]},
        env=cf_env(),
    )
    assert b"D1 list API request failed, skipping D1 cleanup" in result[2]


def test_phase_7_says_none_found_when_no_database_matches_the_pattern() -> None:
    result = sides(
        "cleanup_d1_databases",
        fixture={
            "curl": [
                rule(
                    "d1/database",
                    json_body={"success": True, "result": [{"name": "prod", "uuid": "u"}]},
                )
            ]
        },
        env=cf_env(),
    )
    assert b"No pr-* D1 databases found" in result[2]


# ---------------------------------------------------------------------------
# PHASE 7b: ORPHAN PER-PR TURNSTILE WIDGETS
# ---------------------------------------------------------------------------


def _widgets(*rows: tuple[str, str]) -> dict:
    return {
        "success": True,
        "result": [{"name": n, "sitekey": "key-" + n, "created_on": c} for n, c in rows],
    }


def test_phase_7b_holds_a_widget_inside_the_24h_grace_and_reaps_an_older_one() -> None:
    """The grace window exists so `cleanup-preview.yml` always wins the race.
    The hold line rounds the remaining hours UP, in integer arithmetic."""
    result = sides(
        "cleanup_orphan_turnstile_widgets",
        fixture={
            "gh": [rule("pr", "view", json_body={"state": "CLOSED"})],
            "curl": [
                rule("-X DELETE", "challenges/widgets/", json_body={"success": True}),
                rule(
                    "challenges/widgets?per_page=100",
                    json_body=_widgets(
                        ("rediacc-console-pr-3", ago(12.5 / 24)),
                        ("rediacc-console-pr-4", ago(9.5)),
                        ("rediacc-console", ago(400.5)),
                    ),
                ),
            ],
        },
        env=cf_env(DEBUG="true"),
    )
    err = result[2].decode()
    assert (
        "Holding Turnstile widget: rediacc-console-pr-3 (PR #3 CLOSED, only 12h old; 12h grace remaining)"
        in err
    )
    assert "Deleted Turnstile widget: rediacc-console-pr-4 (PR #4 state: CLOSED)" in err
    assert "Turnstile widgets: deleted 1 of 2 (1 open or in grace, skipped)" in err
    assert "rediacc-console," not in err, "the production widget is never in scope"


def test_phase_7b_keeps_a_widget_whose_pr_is_open() -> None:
    result = sides(
        "cleanup_orphan_turnstile_widgets",
        argv=("--dry-run",),
        fixture={
            "gh": [rule("pr", "view", json_body={"state": "OPEN"})],
            "curl": [
                rule("challenges/widgets", json_body=_widgets(("rediacc-console-pr-3", ago(90.5))))
            ],
        },
        env=cf_env(),
    )
    assert b"Turnstile widgets: would delete 0 of 1 (1 open or in grace, skipped)" in result[2]
    assert calls_of(result[3], "curl")[-1][2] == "GET"


def test_phase_7b_says_none_found_when_only_the_production_widget_exists() -> None:
    result = sides(
        "cleanup_orphan_turnstile_widgets",
        fixture={
            "curl": [rule("challenges/widgets", json_body=_widgets(("rediacc-console", ago(9.5))))]
        },
        env=cf_env(),
    )
    assert b"No per-PR Turnstile widgets found" in result[2]


def test_the_two_sides_agree_on_ages_that_are_not_near_a_boundary() -> None:
    """The control for the whole time discipline in this file.

    Both sides call `date -u +%s` for themselves, seconds apart. Every fixture
    above sits at a half-day or half-hour offset so no printed whole number can
    flip between the two runs. This case proves the discipline holds by driving
    the one phase that prints BOTH an hours figure and a days figure.
    """
    for offset in (12.5 / 24, 6.25 / 24, 23.4 / 24):
        result = sides(
            "cleanup_orphan_turnstile_widgets",
            fixture={
                "gh": [rule("pr", "view", json_body={"state": "CLOSED"})],
                "curl": [
                    rule(
                        "challenges/widgets",
                        json_body=_widgets(("rediacc-console-pr-3", ago(offset))),
                    )
                ],
            },
            env=cf_env(DEBUG="true"),
        )
        assert b"Holding Turnstile widget" in result[2], offset


# ---------------------------------------------------------------------------
# PHASE 8: R2 ORPHANS
#
# Six sub-phases in one function, and they run 8a, 8b, 8c, 8d, 8f, 8e -- the
# labels really are out of order in the twin. The fixtures below default every
# listing to EMPTY and each case turns on the one prefix it cares about, because
# a fixture that answered everything would make each case depend on the other
# five.
# ---------------------------------------------------------------------------

R2_ENV = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "fixture-access-key",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "fixture-secret-key",
    "CLOUDFLARE_R2_ENDPOINT": R2_ENDPOINT,
}


def r2_fixture(*extra_aws: dict, gh: list | None = None) -> dict:
    """The empty R2: every listing empty, every prefix undatable, no uploads.

    `extra_aws` rules are tried FIRST, so a case overrides exactly what it needs.
    """
    return {
        "aws": [
            *extra_aws,
            # `--query 'Contents[0].LastModified' --output text` prints the four
            # characters `None` for a prefix with no objects, and the twin tests
            # for that string explicitly.
            rule("list-objects-v2", "Contents[0].LastModified", raw="None\n"),
            rule("list-objects-v2", "ends_with(Key", raw="\n"),
            # `--query 'Uploads[]...'` renders `null`, not `[]`, when the bucket
            # has no multipart uploads in flight. See HAZARD in `_soft_length_text`.
            rule("list-multipart-uploads", raw="null\n"),
            rule("s3", "rm"),
            rule("s3", "ls", raw=""),
        ],
        "gh": gh if gh is not None else [rule("tags", raw="")],
    }


def pre_line(name: str) -> str:
    """One line of `aws s3 ls` output for a common prefix."""
    return "                           PRE %s\n" % name


def test_phase_8_skips_without_r2_credentials_and_makes_no_call() -> None:
    result = sides("cleanup_r2", fixture=r2_fixture(), env={"CLOUDFLARE_R2_ENDPOINT": ""})
    assert b"CLOUDFLARE_R2_ENDPOINT not set, skipping R2 cleanup" in result[2]
    assert result[3] == []


def test_phase_8a_reaps_a_dryrun_prefix_older_than_the_window() -> None:
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/cli/ ", raw=pre_line("dryrun-abc/")),
            rule("--prefix cli/dryrun-abc/", raw="%s\n" % ago(30.5)),
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    assert "Deleted s3://rediacc-releases/cli/dryrun-abc/ (dryrun 30d old)" in err
    assert "8a: processed 6 format dirs, deleted 1 dryrun prefix(es)" in err
    rm_calls = [c for c in calls_of(result[3], "aws") if c[:2] == ["s3", "rm"]]
    assert rm_calls[0] == [
        "s3",
        "rm",
        "s3://rediacc-releases/cli/dryrun-abc/",
        "--recursive",
        "--endpoint-url",
        R2_ENDPOINT,
        "--quiet",
    ]


def test_phase_8a_holds_a_dryrun_prefix_inside_the_window_and_one_it_cannot_date() -> None:
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule(
                "ls s3://rediacc-releases/npm/ ",
                raw=pre_line("dryrun-young/") + pre_line("dryrun-undatable/"),
            ),
            rule("--prefix npm/dryrun-young/", raw="%s\n" % ago(1.5)),
            rule("--prefix npm/dryrun-undatable/", raw="not-a-timestamp\n"),
        ),
        env=R2_ENV,
    )
    assert b"8a: processed 6 format dirs, deleted 0 dryrun prefix(es)" in result[2]
    assert [c for c in calls_of(result[3], "aws") if c[:2] == ["s3", "rm"]] == []


def test_phase_8b_reaps_a_closed_prs_prefix_and_an_over_age_open_one() -> None:
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/apt/ ", raw=pre_line("pr-3/") + pre_line("pr-7/")),
            rule("--prefix apt/pr-3/", raw="%s\n" % ago(1.5)),
            rule("--prefix apt/pr-7/", raw="%s\n" % ago(30.5)),
            gh=[
                rule("pr", "view", "3", json_body={"state": "CLOSED"}),
                rule("pr", "view", "7", json_body={"state": "OPEN"}),
                rule("tags", raw=""),
            ],
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    assert "Deleted s3://rediacc-releases/apt/pr-3/ (PR #3 CLOSED)" in err
    # pr-7 is OPEN but 30 days stale, so the age arm reaps it anyway and the
    # PR state is never even looked up.
    assert "Deleted s3://rediacc-releases/apt/pr-7/ (stale 30d)" in err
    assert "8b: deleted 2 PR channel prefix(es)" in err
    assert [c for c in calls_of(result[3], "gh") if c[:2] == ["pr", "view"]] == [
        ["pr", "view", "3", "--repo", "rediacc/console", "--json", "state", "--jq", ".state"]
    ]


def test_phase_8b_keeps_an_open_prs_recent_prefix() -> None:
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/rpm/ ", raw=pre_line("pr-7/")),
            rule("--prefix rpm/pr-7/", raw="%s\n" % ago(1.5)),
            gh=[rule("pr", "view", json_body={"state": "OPEN"}), rule("tags", raw="")],
        ),
        env=R2_ENV,
    )
    assert b"8b: deleted 0 PR channel prefix(es)" in result[2]


def test_phase_8c_deletes_a_legacy_prefix_only_when_it_holds_something() -> None:
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/staging/", raw="2026-01-01 00:00:00  12 staging/x\n"),
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    assert "Deleted s3://rediacc-releases/staging/ (legacy)" in err
    assert "packages/ (legacy)" not in err
    assert "cli/latest/ (legacy)" not in err


def test_phase_8d_keeps_a_committed_release_and_reaps_an_aged_orphan() -> None:
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/cli/ ", raw=pre_line("v9.0.0/") + pre_line("v9.9.9/")),
            rule("list-objects-v2", "ends_with(Key", raw="cli/v9.0.0/.released\n"),
            rule("--prefix cli/v9.9.9/", raw="%s\n" % ago(30.5)),
            gh=[rule("tags", json_body=[{"name": "v9.0.0"}])],
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    # sentinel AND tag: a committed release, `continue`d before any message.
    assert "drift: " not in err
    assert "cli/v9.0.0" not in err
    assert (
        "Deleted s3://rediacc-releases/cli/v9.9.9/ (orphan cli/v9.9.9 (no .released "
        "sentinel, no git tag, >14d old))" in err
    )
    assert "8d: deleted 1 orphan versioned prefix(es); found 0 drift finding(s)" in err


def test_phase_8d_holds_a_young_orphan_because_it_may_be_a_release_in_flight() -> None:
    """The message carries a U+2014 EM DASH, which the port spells as an escape
    so the source holds no em dash byte while the OUTPUT stays identical."""
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/cli/ ", raw=pre_line("v9.9.9/")),
            rule("--prefix cli/v9.9.9/", raw="%s\n" % ago(1.5)),
        ),
        env=R2_ENV,
    )
    assert (
        "orphan cli/v9.9.9: skipping (younger than 14d or undatable \u2014 may be "
        "an in-flight release)"
    ) in result[2].decode()
    assert b"8d: deleted 0 orphan versioned prefix(es)" in result[2]


def test_phase_8d_never_touches_the_version_this_ci_run_is_releasing() -> None:
    """`IN_FLIGHT_VERSION` short-circuits BEFORE classification, so the prefix is
    not even datable-checked. The call log is the only place that shows it."""
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/cli/ ", raw=pre_line("v9.9.9/")),
            rule("--prefix cli/v9.9.9/", raw="%s\n" % ago(30.5)),
        ),
        env=dict(R2_ENV, IN_FLIGHT_VERSION="v9.9.9"),
    )
    assert b"8d: deleted 0 orphan versioned prefix(es)" in result[2]
    assert not any("--prefix cli/v9.9.9/" in " ".join(c) for c in calls_of(result[3], "aws"))


def test_phase_8d_latches_the_run_as_failed_on_drift_in_either_direction() -> None:
    """Drift is NOT auto-healed: two `log_error` lines per finding, a GHA
    annotation on STDOUT, and a latch the run reports at the very end."""
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/cli/ ", raw=pre_line("v9.0.0/") + pre_line("v9.1.0/")),
            rule("list-objects-v2", "ends_with(Key", raw="cli/v9.0.0/.released\n"),
            gh=[rule("tags", json_body=[{"name": "v9.1.0"}])],
        ),
        env=dict(R2_ENV, GITHUB_ACTIONS="true"),
    )
    err = result[2].decode()
    assert "drift: cli/v9.0.0/.released exists but git tag v9.0.0 missing" in err
    assert (
        "remediation: re-run CD to tag/release v9.0.0, or scrub via scripts/dev/scrub-sentinel.sh v9.0.0 --execute"
        in err
    )
    assert "drift: git tag v9.1.0 exists but cli/v9.1.0/.released missing" in err
    assert "remediation: re-run CI for v9.1.0, or delete tag v9.1.0" in err
    assert "8d: deleted 0 orphan versioned prefix(es); found 2 drift finding(s)" in err
    # The annotation is an `echo`, so it is on STDOUT, not with the log lines.
    assert (
        b"::error title=Release-state drift::8d: 2 release-state drift finding(s); "
        b"housekeeping refuses to auto-heal." in result[1]
    )


def test_phase_8d_grandfathers_a_version_below_the_pre_contract_floor() -> None:
    """`.ci/config/release-contract-floor.txt` is the ratchet, and drift below it
    is not actionable. Both sides read the same file, through different code."""
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/cli/ ", raw=pre_line("v1.0.0/")),
            rule("list-objects-v2", "ends_with(Key", raw="cli/v1.0.0/.released\n"),
            gh=[rule("tags", raw="")],
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    assert "8d: pre-contract floor = v1.2.21 (versions below this are grandfathered)" in err
    assert "drift:" not in err
    assert "found 0 drift finding(s)" in err


def test_phase_8f_keeps_the_top_semvers_and_always_zaps_the_dev_pollution() -> None:
    listing = "".join(
        "%s       12 apt/stable/rediacc-cli_%s_amd64.deb\n" % (s3_ago(10.5), v)
        for v in ("1.0.%d" % i for i in range(25))
    ) + "%s       12 apt/stable/rediacc-cli-0.0.0-dev-abc.deb\n" % s3_ago(10.5)
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/apt/stable/ --recursive", raw=listing),
            rule("ls s3://rediacc-releases/apt/stable/ ", raw=listing),
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    # 25 semvers, keep the top 20 -> 1.0.0 .. 1.0.4 go, plus the dev file.
    assert "Deleted apt/stable/rediacc-cli_1.0.0_amd64.deb (v1.0.0, outside top-20)" in err
    assert "Deleted apt/stable/rediacc-cli_1.0.4_amd64.deb (v1.0.4, outside top-20)" in err
    assert "rediacc-cli_1.0.5_amd64.deb (v1.0.5" not in err
    assert "Deleted apt/stable/rediacc-cli-0.0.0-dev-abc.deb (0.0.0-dev pollution, 10d)" in err
    assert "8f: deleted 6 stale artifact(s) across apt/rpm/apk/archlinux/npm" in err


def test_phase_8f_leaves_channel_metadata_alone() -> None:
    listing = (
        "%s       12 apt/edge/Packages.gz\n" % s3_ago(10.5)
        + "%s       12 apt/edge/InRelease\n" % s3_ago(10.5)
        + "%s       12 apt/edge/rediacc-cli_1.0.0_amd64.deb\n" % s3_ago(10.5)
    )
    result = sides(
        "cleanup_r2",
        argv=("--dry-run",),
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/apt/edge/ --recursive", raw=listing),
            rule("ls s3://rediacc-releases/apt/edge/ ", raw=listing),
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    assert "Packages.gz" not in err
    assert "InRelease" not in err
    assert "8f: deleted 0 stale artifact(s)" in err, "one semver is inside top-20"


def test_phase_8e_reads_a_null_upload_query_as_no_uploads() -> None:
    """`aws --query 'Uploads[]...'` prints `null` for an idle bucket, and
    `null | length` is a jq ERROR. Inside the twin's `set +e` region that leaves
    `mpu_count` EMPTY, which `-eq 0` reads as zero. A port that raised here would
    be louder than the twin on the ordinary case."""
    result = sides("cleanup_r2", fixture=r2_fixture(), env=R2_ENV)
    assert b"8e: no ongoing multipart uploads" in result[2]
    assert result[0] == 0


def test_phase_8e_aborts_an_old_multipart_and_holds_a_young_one() -> None:
    uploads = json.dumps(
        [
            {"Key": "cli/v1/rdc", "UploadId": "old-id", "Initiated": ago(3.5)},
            {"Key": "cli/v2/rdc", "UploadId": "new-id", "Initiated": ago(0.25)},
        ]
    )
    result = sides(
        "cleanup_r2",
        fixture=r2_fixture(
            rule("list-multipart-uploads", raw=uploads + "\n"),
            rule("abort-multipart-upload"),
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    assert "Aborted multipart: cli/v1/rdc" in err
    assert "8e: aborted 1 of 2 (held 1 under 24h grace)" in err
    aborts = [c for c in calls_of(result[3], "aws") if c[1] == "abort-multipart-upload"]
    assert aborts == [
        [
            "s3api",
            "abort-multipart-upload",
            "--bucket",
            "rediacc-releases",
            "--key",
            "cli/v1/rdc",
            "--upload-id",
            "old-id",
            "--endpoint-url",
            R2_ENDPOINT,
        ]
    ]


def test_phase_8_dry_run_makes_no_destructive_call_at_all() -> None:
    """The whole phase at once: every arm named, nothing removed. If any `aws s3
    rm` or `abort-multipart-upload` appears in the log, the dry run is a lie."""
    listing = "%s       12 apt/stable/rediacc-cli_0.0.1_amd64.deb\n" % s3_ago(10.5)
    uploads = json.dumps([{"Key": "k", "UploadId": "u", "Initiated": ago(3.5)}])
    result = sides(
        "cleanup_r2",
        argv=("--dry-run",),
        fixture=r2_fixture(
            rule("ls s3://rediacc-releases/cli/ ", raw=pre_line("dryrun-x/") + pre_line("v9.9.9/")),
            rule("ls s3://rediacc-releases/staging/", raw="2026-01-01 00:00:00 1 staging/x\n"),
            rule("ls s3://rediacc-releases/apt/stable/", raw=listing),
            rule("--prefix cli/dryrun-x/", raw="%s\n" % ago(30.5)),
            rule("--prefix cli/v9.9.9/", raw="%s\n" % ago(30.5)),
            rule("list-multipart-uploads", raw=uploads + "\n"),
        ),
        env=R2_ENV,
    )
    err = result[2].decode()
    assert "[DRY-RUN] Would delete s3://rediacc-releases/cli/dryrun-x/ (dryrun 30d old)" in err
    assert "[DRY-RUN] Would delete s3://rediacc-releases/staging/ (legacy)" in err
    assert "[DRY-RUN] Would abort multipart: k (age 84h)" in err
    for call in calls_of(result[3], "aws"):
        assert call[:2] != ["s3", "rm"], call
        assert call[1] != "abort-multipart-upload", call


# ---------------------------------------------------------------------------
# PHASE 9: STALE BRANCHES
# ---------------------------------------------------------------------------


def _branches_fixture(*names: str, **rules_by_key: dict) -> dict:
    """console answers with `names`; the other five repos 404 (a `log_debug`)."""
    out = [
        rule("repos/rediacc/console/branches?per_page=100", json_body=[{"name": n} for n in names]),
    ]
    out.extend(rules_by_key.values())
    out.append(rule("branches?per_page=100", rc=1))
    return {"gh": out}


def test_phase_9_keeps_a_branch_with_an_open_pr_and_one_it_cannot_date() -> None:
    fixture = _branches_fixture(
        "main",
        "has-pr",
        "undatable",
        open_pr=rule("pulls?head=rediacc:has-pr", json_body=[{"number": 1}]),
        undatable=rule("branches/undatable", rc=1),
        no_pr=rule("pulls?head=rediacc:", json_body=[]),
    )
    result = sides(
        "cleanup_stale_branches", argv=("--dry-run",), fixture=fixture, env={"DEBUG": "true"}
    )
    err = result[2].decode()
    assert "[DEBUG]     Keeping has-pr (has open PR)" in err
    assert "[DEBUG]     Keeping undatable (cannot determine age)" in err
    assert "main" not in err.replace("Processing branches", ""), "main is skipped outright"
    assert "Branches (console): would delete 0, kept 2" in err


def test_phase_9_coerces_a_non_numeric_open_pr_count_to_zero() -> None:
    """A 403 makes gh print a JSON BODY to stdout and exit non-zero, and `|| echo
    0` only catches the status. The `=~ ^[0-9]+$` guard is what stops the later
    `-gt` from blowing up in a tight loop."""
    fixture = _branches_fixture(
        "stale",
        pulls=rule("pulls?head=", rc=1, raw='{"message":"Must have admin rights"}'),
        branch=rule(
            "branches/stale", json_body={"commit": {"commit": {"committer": {"date": ago(90.5)}}}}
        ),
    )
    result = sides("cleanup_stale_branches", argv=("--dry-run",), fixture=fixture)
    assert b"[DRY-RUN] Would delete stale (90 days old, no open PR)" in result[2]
    assert b"Branches (console): would delete 1, kept 0" in result[2]


def test_phase_9_dry_run_has_its_own_counter() -> None:
    """The twin's comment: `would_delete` exists because a dry run used to end
    with "deleted 7" having deleted nothing."""
    fixture = _branches_fixture(
        "stale",
        pulls=rule("pulls?head=", json_body=[]),
        branch=rule(
            "branches/stale", json_body={"commit": {"commit": {"committer": {"date": ago(90.5)}}}}
        ),
    )
    result = sides("cleanup_stale_branches", argv=("--dry-run",), fixture=fixture)
    assert b"would delete 1, kept 0" in result[2]
    assert b"deleted 1, kept 0" not in result[2]
    assert [c for c in calls_of(result[3], "gh") if "-X" in c] == []


def test_phase_9_a_failed_delete_is_the_one_that_fails_the_whole_run() -> None:
    """`housekeeping_fail`, the latch. Two places call it and this is one; every
    other failed delete in the file is a warning the run survives."""
    fixture = _branches_fixture(
        "stale",
        pulls=rule("pulls?head=", json_body=[]),
        branch=rule(
            "branches/stale", json_body={"commit": {"commit": {"committer": {"date": ago(90.5)}}}}
        ),
        delete=rule(
            "-X", "DELETE", "git/refs/heads/stale", rc=1, stderr="HTTP 403: no contents:write\n"
        ),
    )
    result = sides("cleanup_stale_branches", fixture=fixture, env={"GITHUB_ACTIONS": "true"})
    err = result[2].decode()
    assert "Phase 9: could not delete rediacc/console@stale (90 days old): " in err
    assert "HTTP 403: no contents:write" in err, "the captured STDERR is quoted back"
    assert b"::error title=Stale-branch delete failed::" in result[1]
    assert b"Branches (console): deleted 0, kept 0" in result[2]


def test_phase_9_reports_no_error_output_when_gh_says_nothing() -> None:
    """`${delete_err:-no error output from gh}`: a silent failure still names
    itself rather than printing an empty reason."""
    fixture = _branches_fixture(
        "stale",
        pulls=rule("pulls?head=", json_body=[]),
        branch=rule(
            "branches/stale", json_body={"commit": {"commit": {"committer": {"date": ago(90.5)}}}}
        ),
        delete=rule("-X", "DELETE", "git/refs/heads/stale", rc=1),
    )
    result = sides("cleanup_stale_branches", fixture=fixture)
    # The recording fake writes its own `call:` line to stderr, which the twin
    # captures with `2>&1 >/dev/null` -- so the reason is that line, identically
    # on both sides. The `:-` default is exercised by the port's own unit shape.
    assert b"Phase 9: could not delete rediacc/console@stale (90 days old): call: gh" in result[2]


def test_phase_9_deletes_and_charges_the_budget() -> None:
    fixture = _branches_fixture(
        "stale-a",
        "stale-b",
        pulls=rule("pulls?head=", json_body=[]),
        branch=rule(
            "branches/stale-", json_body={"commit": {"commit": {"committer": {"date": ago(90.5)}}}}
        ),
        delete=rule("-X", "DELETE", "git/refs/heads/"),
    )
    result = sides("cleanup_stale_branches", fixture=fixture, env={"MAX_DELETES_PER_RUN": "1"})
    err = result[2].decode()
    assert "Deleted stale-a (90 days old)" in err
    assert "Phase 9: hit MAX_DELETES_PER_RUN=1; remaining stale branches deferred" in err
    assert "Branches (console): deleted 1, kept 0" in err


def test_a_zero_padded_branch_age_unwinds_the_whole_run_on_both_sides() -> None:
    """HAZARD 8, and it is the most serious thing in this file.

    `BRANCH_MAX_AGE_DAYS=08` is an arithmetic EXPANSION error, not a comparison
    error, so bash abandons every enclosing function frame: Phases 10, 11 and
    12, the delete total and `Housekeeping complete` never run. The run ends on
    the failed expansion's status with no phase named and no summary at all.

    Compared side by side rather than through `sides()` because the diagnostic
    itself is the port's one named divergence: bash names a file and a line.
    """
    fixture = {
        "gh": [rule("actions/caches", raw=_caches()), rule("", rc=1)],
        "curl": [rule("", rc=1)],
        "aws": [rule("", rc=1)],
    }
    results = []
    with tempfile.TemporaryDirectory() as td:
        for side in ("bash", "python"):
            base = pathlib.Path(td) / side
            base.mkdir(parents=True)
            results.append(
                _run(
                    side,
                    "run_all_phases",
                    ("--dry-run",),
                    fixture,
                    {"BRANCH_MAX_AGE_DAYS": "08"},
                    base,
                )
            )
    old, new = results
    assert old[0] == 1, "the unwind carries status 1 out of the shell"
    assert new[0] == 1, "and the port must carry the same status out of the same unwind"
    assert old[1] == new[1], (old[1], new[1])
    assert old[3] == new[3]
    for stream in (old[2], new[2]):
        text = stream.decode()
        assert "Phase 9: Cleaning up stale branches (>08 days, no open PR)" in text
        assert 'value too great for base (error token is "08")' in text
        assert "Phase 10:" not in text, "the run was abandoned mid-phase-9"
        assert "Housekeeping complete" not in text
    assert "cleanup-versions.sh: line " in old[2].decode()
    assert "cleanup_versions.py: " in new[2].decode()


# ---------------------------------------------------------------------------
# PHASE 10: WORKFLOW RUNS
# ---------------------------------------------------------------------------


def _runs(count: int, *, start: int = 0, age: float = 1.5) -> list:
    return [
        {"id": 1000 + start + i, "created_at": ago(age), "conclusion": "success"}
        for i in range(count)
    ]


def test_phase_10_reports_an_empty_workflow_list_as_a_possible_api_error() -> None:
    """The only phase besides 5b that says out loud that it might not have been
    able to look. Every other one reports a clean sweep of nothing."""
    result = sides("cleanup_workflow_runs", fixture={"gh": [rule("actions/workflows", rc=1)]})
    assert b"No active workflows listed (API error?); skipping phase" in result[2]
    assert result[0] == 0


def test_phase_10_keeps_the_hundred_newest_and_reaps_the_old_tail() -> None:
    page = [
        *_runs(100),
        {"id": 9001, "created_at": ago(400.5), "conclusion": "failure"},
        {"id": 9002, "created_at": ago(401.5), "conclusion": "failure"},
    ]
    result = sides(
        "cleanup_workflow_runs",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule(
                    "actions/workflows?per_page=100",
                    json_body={
                        "workflows": [
                            {
                                "id": 11,
                                "name": "Console CI",
                                "path": ".github/workflows/ci.yml",
                                "state": "active",
                            },
                            {
                                "id": 12,
                                "name": "Disabled",
                                "path": ".github/workflows/x.yml",
                                "state": "disabled_manually",
                            },
                        ]
                    },
                ),
                # `&page=1`, because `per_page=100` contains `page=100`; and a
                # second rule for every later page, or the same body would be
                # served ten times over and the totals would be ten times wrong.
                rule("workflows/11/runs", "&page=1", json_body={"workflow_runs": page}),
                rule("workflows/11/runs", json_body={"workflow_runs": []}),
            ]
        },
    )
    err = result[2].decode()
    assert "Would delete run: 9001 (Console CI," in err
    assert "Would delete run: 9002 (Console CI," in err
    assert "Console CI: would delete 2 of 102 (kept top 100 + within 30d)" in err
    assert "Workflow runs: would delete 2 of 102 (across 1 workflows)" in err
    assert "Disabled" not in err, "only active workflows are in scope"


def test_phase_10_gives_the_watchdog_its_own_shorter_retention_by_path() -> None:
    """Keyed by path, never by name: the watchdog's display name is generated per
    run ("Watchdog: run <id> (gen N)"), so a name match is unwritable."""
    page = [*_runs(100), {"id": 9001, "created_at": ago(10.5), "conclusion": "success"}]
    result = sides(
        "cleanup_workflow_runs",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule(
                    "actions/workflows?per_page=100",
                    json_body={
                        "workflows": [
                            {
                                "id": 21,
                                "name": "Watchdog: run 123 (gen 4)",
                                "path": ".github/workflows/watchdog-monitor.yml",
                                "state": "active",
                            },
                            # A DECOY whose NAME contains "Watchdog" and whose
                            # PATH is a different file. Without it a port that
                            # matched on the name would behave identically here
                            # and this case would prove nothing; a planted
                            # name-match defect stayed green until this row was
                            # added.
                            {
                                "id": 22,
                                "name": "Watchdog dispatcher",
                                "path": ".github/workflows/dispatch-watchdog.yml",
                                "state": "active",
                            },
                        ]
                    },
                ),
                rule("workflows/21/runs", "&page=1", json_body={"workflow_runs": page}),
                rule("workflows/22/runs", "&page=1", json_body={"workflow_runs": page}),
                rule("runs?status=completed", json_body={"workflow_runs": []}),
            ]
        },
    )
    err = result[2].decode()
    # 10 days old: inside the shared 30-day window, outside the watchdog's 7.
    assert "Watchdog: run 123 (gen 4): would delete 1 of 101 (kept top 100 + within 30d)" in err
    # The decoy keeps its run: 10 days is inside the 30-day default, and its
    # PATH is not the watchdog's however much its name looks like one.
    assert "Watchdog dispatcher: would delete" not in err
    assert "Workflow runs: would delete 1 of 202 (across 2 workflows)" in err


def test_phase_10_warns_when_its_scan_window_can_never_reach_the_threshold() -> None:
    """THE VACUOUS-GREEN CHECK. This phase deleted nothing for the watchdog for
    months while reporting success, because ten pages of runs never reached back
    as far as the retention threshold. The warning fires only when the window was
    TRUNCATED, so a young low-volume workflow stays quiet."""
    result = sides(
        "cleanup_workflow_runs",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule(
                    "actions/workflows?per_page=100",
                    json_body={
                        "workflows": [
                            {
                                "id": 31,
                                "name": "Busy",
                                "path": ".github/workflows/busy.yml",
                                "state": "active",
                            }
                        ]
                    },
                ),
                rule("workflows/31/runs", json_body={"workflow_runs": _runs(100, age=2.5)}),
            ]
        },
    )
    err = result[2].decode()
    assert "Busy: scan window reaches only 2d but retention is 30d --" in err
    assert "nothing here can EVER be reaped. Raise GH_RUNS_MAX_PAGES_PER_WORKFLOW" in err
    assert "(currently 10) or give this workflow its own retention." in err
    # Ten pages requested, and not an eleventh.
    pages = [c for c in calls_of(result[3], "gh") if "workflows/31/runs" in " ".join(c)]
    assert len(pages) == 10


def test_phase_10_a_short_page_ends_the_pagination_without_the_warning() -> None:
    result = sides(
        "cleanup_workflow_runs",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule(
                    "actions/workflows?per_page=100",
                    json_body={
                        "workflows": [
                            {
                                "id": 41,
                                "name": "Quiet",
                                "path": ".github/workflows/q.yml",
                                "state": "active",
                            }
                        ]
                    },
                ),
                rule("workflows/41/runs", json_body={"workflow_runs": _runs(3, age=2.5)}),
            ]
        },
    )
    err = result[2].decode()
    assert "scan window reaches only" not in err
    assert "Workflow runs: would delete 0 of 3 (across 1 workflows)" in err
    assert len([c for c in calls_of(result[3], "gh") if "workflows/41/runs" in " ".join(c)]) == 1


def test_phase_10_stops_a_workflow_after_five_consecutive_delete_failures() -> None:
    page = [
        *_runs(100),
        *[{"id": 9000 + i, "created_at": ago(400.5), "conclusion": "failure"} for i in range(8)],
    ]
    result = sides(
        "cleanup_workflow_runs",
        fixture={
            "gh": [
                rule(
                    "actions/workflows?per_page=100",
                    json_body={
                        "workflows": [
                            {
                                "id": 51,
                                "name": "CI",
                                "path": ".github/workflows/ci.yml",
                                "state": "active",
                            }
                        ]
                    },
                ),
                rule("workflows/51/runs", "&page=1", json_body={"workflow_runs": page}),
                rule("workflows/51/runs", json_body={"workflow_runs": []}),
                rule("-X", "DELETE", "actions/runs/", rc=1),
            ]
        },
    )
    err = result[2].decode()
    assert "Skipping remaining runs for CI after 5 consecutive failures" in err
    assert len([c for c in calls_of(result[3], "gh") if "actions/runs/" in " ".join(c)]) == 15


# ---------------------------------------------------------------------------
# PHASE 11: WORKFLOW ARTIFACTS
# ---------------------------------------------------------------------------


def test_phase_11_deletes_the_expired_and_the_over_age_and_keeps_the_rest() -> None:
    result = sides(
        "cleanup_workflow_artifacts",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule(
                    "actions/artifacts?per_page=100",
                    json_body={
                        "artifacts": [
                            {"id": 1, "created_at": ago(1.5), "expired": True, "size_in_bytes": 10},
                            {
                                "id": 2,
                                "created_at": ago(30.5),
                                "expired": False,
                                "size_in_bytes": 10,
                            },
                            {
                                "id": 3,
                                "created_at": ago(1.5),
                                "expired": False,
                                "size_in_bytes": 10,
                            },
                        ]
                    },
                )
            ]
        },
    )
    err = result[2].decode()
    assert "[DRY-RUN] Would delete artifact: 1 (created:" in err
    assert "expired: true)" in err
    assert "Would delete artifact: 2 " in err
    assert "Would delete artifact: 3 " not in err
    assert "Artifacts: would delete 2 of 3 (1 already expired, retention: 14d)" in err


def test_phase_11_really_deletes_and_charges_the_budget() -> None:
    result = sides(
        "cleanup_workflow_artifacts",
        fixture={
            "gh": [
                rule(
                    "actions/artifacts?per_page=100",
                    json_body={
                        "artifacts": [
                            {
                                "id": 1,
                                "created_at": ago(30.5),
                                "expired": False,
                                "size_in_bytes": 10,
                            },
                            {
                                "id": 2,
                                "created_at": ago(31.5),
                                "expired": False,
                                "size_in_bytes": 10,
                            },
                        ]
                    },
                ),
                rule("-X", "DELETE", "actions/artifacts/"),
            ]
        },
        env={"MAX_DELETES_PER_RUN": "1"},
    )
    err = result[2].decode()
    assert "Phase 11: hit MAX_DELETES_PER_RUN=1; remaining artifacts deferred" in err
    assert "Artifacts: deleted 1 of 1 (0 already expired, retention: 14d)" in err


def test_phase_11_reads_an_api_failure_as_an_empty_page_and_stops() -> None:
    result = sides("cleanup_workflow_artifacts", fixture={"gh": [rule("artifacts", rc=1)]})
    assert b"Artifacts: deleted 0 of 0 (0 already expired, retention: 14d)" in result[2]
    assert len(calls_of(result[3], "gh")) == 1, "an empty page ends the loop"


# ---------------------------------------------------------------------------
# PHASE 12: ACTIONS CACHE
# ---------------------------------------------------------------------------

GB = 1024 * 1024 * 1024


def _caches(*rows: tuple[int, int, str]) -> str:
    """The `--jq` filter emits ONE OBJECT PER LINE, which the twin slurps."""
    return json.dumps(
        {
            "actions_caches": [
                {
                    "id": i,
                    "key": "cache-key-%d" % i,
                    "ref": "refs/heads/main",
                    "size_in_bytes": size,
                    "last_accessed_at": last,
                }
                for i, size, last in rows
            ]
        }
    )


def test_phase_12_does_nothing_when_the_total_is_under_the_ceiling() -> None:
    result = sides(
        "cleanup_actions_cache",
        fixture={"gh": [rule("actions/caches", raw=_caches((1, GB, ago(1.5))))]},
    )
    assert b"Actions cache: 1024 MB <= ceiling, nothing to evict" in result[2]
    assert len(calls_of(result[3], "gh")) == 1


def test_phase_12_evicts_the_least_recently_used_until_it_is_under_the_ceiling() -> None:
    result = sides(
        "cleanup_actions_cache",
        argv=("--dry-run",),
        fixture={
            "gh": [
                rule(
                    "actions/caches",
                    raw=_caches(
                        (1, 3 * GB, ago(9.5)),
                        (2, 2 * GB, ago(5.5)),
                        (3, 2 * GB, ago(1.5)),
                    ),
                )
            ]
        },
    )
    err = result[2].decode()
    assert "[DRY-RUN] Would delete cache: id=1 size=3072MB" in err
    assert "key=cache-key-1..." in err, "the key is truncated to 40 chars plus dots"
    assert "id=2" not in err, "7 GB - 3 GB = 4 GB, already under the 5 GB ceiling"
    # "freeING" in a dry run, "freeD" in a real one. The port collapsed the two
    # branches into one verb-substituted line and this assertion is what caught
    # it, so it stays spelled out.
    assert (
        "Actions cache: would delete 1 of 3, freeing ~3072 MB (surviving: ~4096 MB / ceiling 5 GB)"
        in err
    )


def test_phase_12_says_none_found_on_an_empty_listing() -> None:
    result = sides("cleanup_actions_cache", fixture={"gh": [rule("actions/caches", raw=_caches())]})
    assert b"No Actions cache entries found" in result[2]


def test_a_failed_cache_listing_kills_the_run_with_an_arithmetic_error() -> None:
    """HAZARD 9, and it is a defect in the twin, reproduced rather than repaired.

    `gh api ... | jq -s 'sort_by(...)' || echo "[]"`. The `||` covers the WHOLE
    pipeline under pipefail, and `echo` APPENDS to what the pipeline already
    wrote -- and `jq -s` writes `[]` even for an empty stream. So a gh that fails
    for ANY reason (a rate limit is the likely one) leaves the variable holding
    `[]\n[]`, two json values, and every later jq answers TWICE:

        total       = "0\n0"
        total_bytes = "0\n0"

    `[[ "0\n0" -eq 0 ]]` is an arithmetic syntax error, so the "No Actions cache
    entries found" early return is NOT taken; the next line's `$((total_bytes /
    1024 / 1024))` is an arithmetic EXPANSION error, which unwinds every frame
    including `run_all_phases`. Phase 12 is last, so the visible damage is small
    -- the delete total and `Housekeeping complete` are lost and the run exits 1
    -- but the nightly's only evidence is one line of bash arithmetic
    diagnostics naming no phase at all.

    Compared side by side because the diagnostic text is the port's one named
    divergence; the exit code, stdout and call log are identical.
    """
    fixture = {"gh": [rule("actions/caches", rc=1)]}
    results = []
    with tempfile.TemporaryDirectory() as td:
        for side in ("bash", "python"):
            base = pathlib.Path(td) / side
            base.mkdir(parents=True)
            results.append(_run(side, "cleanup_actions_cache", (), fixture, {}, base))
    old, new = results
    assert old[0] == 1, "the unwind carries status 1 out of the shell"
    assert new[0] == 1, "and the port must carry the same status out of the same unwind"
    assert old[1] == new[1]
    assert old[3] == new[3]
    for stream in (old[2], new[2]):
        text = stream.decode()
        assert "Phase 12: Cleaning up Actions cache (target <= 5 GB)" in text
        assert "No Actions cache entries found" not in text
        assert "Actions cache:" not in text
    assert "arithmetic syntax error in expression" in old[2].decode()
    assert "cleanup_versions.py: " in new[2].decode()


# ---------------------------------------------------------------------------
# THE WHOLE RUN
# ---------------------------------------------------------------------------


def test_run_all_phases_over_an_empty_world_is_identical_end_to_end() -> None:
    """Every phase, in order, with every API answering empty. This is the case
    that pins the BLANK LINES -- `echo ""` puts them on STDOUT while every log
    line goes to stderr, so a port that printed them to the wrong stream would
    pass every per-phase case above and fail here."""
    result = sides(
        "run_all_phases",
        argv=("--dry-run",),
        fixture={
            # A cache listing that SUCCEEDS, because a failing one truncates the
            # run through HAZARD 9 and this case is about the summary.
            "gh": [rule("actions/caches", raw=_caches()), rule("", rc=1)],
            "curl": [rule("", rc=1)],
            "aws": [rule("", rc=1)],
        },
        env=cf_env(),
    )
    assert result[0] == 0
    assert result[1] == b"\n" * 15, "14 inter-phase blanks plus the one before the total"
    err = result[2].decode()
    assert "Housekeeping: cleanup-versions" in err
    assert "Retention: 14 days OR last 20 versions" in err
    assert "DRY-RUN mode: no deletions will be performed" in err
    assert "Total deletes this run: 0 / 1500" in err
    assert "Housekeeping complete" in err
    for phase_label in (
        "Phase 1:",
        "Phase 2:",
        "Phase 3:",
        "Phase 4:",
        "Phase 5:",
        "Phase 5b:",
        "Phase 6:",
        "Phase 7:",
        "Phase 7b:",
        "Phase 8:",
        "Phase 9:",
        "Phase 10:",
        "Phase 11:",
        "Phase 12:",
    ):
        assert phase_label in err, phase_label


def test_run_all_phases_exits_1_once_at_the_end_when_a_phase_latched() -> None:
    """ONE exit point, AFTER every phase has run. Returning non-zero out of a
    phase instead is what once disabled Phase 8f and unset errexit for 9-12."""
    result = sides(
        "run_all_phases",
        fixture={
            "gh": [rule("actions/caches", raw=_caches()), rule("", rc=1)],
            "curl": [rule("", rc=1)],
            "aws": [
                rule("ls s3://rediacc-releases/cli/ ", raw=pre_line("v9.0.0/")),
                rule("list-objects-v2", "ends_with(Key", raw="cli/v9.0.0/.released\n"),
                rule("list-objects-v2", "Contents[0].LastModified", raw="None\n"),
                rule("list-multipart-uploads", raw="null\n"),
                rule("", rc=1),
            ],
        },
        env=dict(R2_ENV, GITHUB_ACTIONS="true"),
    )
    assert result[0] == 1
    err = result[2].decode()
    assert "drift: cli/v9.0.0/.released exists but git tag v9.0.0 missing" in err
    assert "Housekeeping FAILED: see the ::error annotations above." in err
    assert "Phase 12:" in err, "every later phase still ran"
    assert "Housekeeping complete" in err


def test_the_guards_refuse_in_the_twins_order() -> None:
    """`require_cmd gh jq curl aws` then `require_var GH_TOKEN`, at SOURCE time,
    so a host missing two of them is told about the FIRST one."""
    for drop, message in (
        ("gh", "Required command 'gh' is not available"),
        ("curl", "Required command 'curl' is not available"),
        ("aws", "Required command 'aws' is not available"),
    ):
        result = sides("cleanup_releases", env={"_drop": drop})
        assert message.encode() in result[2], drop
        assert result[0] == 1, drop


def test_an_unset_gh_token_refuses_before_any_phase_runs() -> None:
    result = sides("cleanup_releases", env={"GH_TOKEN": ""})
    assert b"Required environment variable 'GH_TOKEN' is not set" in result[2]
    assert result[0] == 1
    assert result[3] == []


# ---------------------------------------------------------------------------
# COVERAGE CONTROL
# ---------------------------------------------------------------------------


def test_every_phase_was_driven_by_at_least_one_case() -> None:
    """ZERO CASES FOR A PHASE IS A FAILURE, not a pass.

    A file of 14 phases where a rename or a refactor quietly left one undriven
    would still be all-green, and the green would mean nothing for that phase.
    Runs last by name, and reads the set the harness accumulated.
    """
    missing = sorted(set(PHASES) - _EXERCISED)
    assert not missing, (
        "no differential case drives: %s. A phase with no case is not verified, "
        "and this file's green would be a claim it has not earned." % ", ".join(missing)
    )
    assert len(_EXERCISED) >= len(PHASES)
