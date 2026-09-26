"""`rediacc_ci.quality.go_deps` against the shell text-handling it replaces.

WHAT THE SHADOW LEDGER ALREADY PROVES:
`.ci/shadow/w7p2-go-deps.observations.jsonl` drives both implementations end to end over five distinct committed trees, with an outdated minor dep, a probe that exits non-zero, a low-effort BLOCKER, an entry with no BLOCKER, and a two-module tree carrying every kind at once (minor, major, blocked, too-fresh, indirect and an unparseable timestamp).

WHAT THE LEDGER CANNOT ISOLATE is the three pieces of shell text handling that decide what any of that MEANS, and each of them is quiet when it goes wrong:

  * `get_major`, a four-stage pipeline ending in `grep -o '^[0-9]*' || echo 0`.
    Get it wrong in one direction and every major update is demanded as a minor
    one; wrong in the other and a genuine minor bump is waved through as major.
  * `IFS=' ' read -r path current latest kind`, whose LAST variable takes the
    remainder verbatim. That is the only reason the probe sentinel's error text
    survives into the report at all.
  * `jq -s` over `go list -json`'s stream of back-to-back objects, where a
    parse failure must become a sentinel and never an empty result set. The
    empty result set IS the 2026-07-27 defect this gate was rewritten for.

So each case below runs the REAL bash or the REAL jq against the Python.
"""

import json
import pathlib
import subprocess
import time

import pytest

from rediacc_ci import log
from rediacc_ci.quality import go_deps
from rediacc_ci.tests import differential as diff

# check-go-deps.sh:63-67, verbatim.
GET_MAJOR = (
    "get_major() { echo \"$1\" | sed 's/^v//' | cut -d. -f1 | grep -o '^[0-9]*' || echo \"0\"; }"
)

# check-go-deps.sh:171, the aggregation loop's field split.
READ_FIELDS = (
    "IFS=' ' read -r path current latest kind <<<\"$1\"\n"
    'printf "%s\\n%s\\n%s\\n%s\\n" "$path" "$current" "$latest" "$kind"'
)

# check-go-deps.sh:114-115, the record projection.
JQ_RECORDS = (
    "jq -rs '"
    ".[] | select((.Indirect != true) and (.Update != null))"
    r' | "\(.Path) \(.Version) \(.Update.Version) \(.Update.Time // "")"'
    "'"
)


@pytest.fixture(autouse=True)
def _fresh_logger():
    """Rebind the module logger to whatever stream this test runs under.

    `rediacc_ci.log` caches ONE default Logger bound to `sys.stderr` at first use, which is right for a gate and wrong under pytest's `capsys`: the capture fixture swaps `sys.stderr` per test and closes the previous one, so a logger cached by an EARLIER test writes into a closed file and every later test dies with `ValueError: I/O operation on closed file`. That failure names the
    logger rather than the test that poisoned it, which is why this is an autouse fixture and not a line in the two tests that use capsys.
    """
    log.reset()
    yield
    log.reset()


def _bash(script: str, *args: str) -> str:
    proc = subprocess.run(
        ["bash", "-c", script, "_", *args], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, "%s / %s" % (proc.returncode, proc.stderr)
    return proc.stdout


def _bash_major(version: str) -> int:
    """The twin's answer, with its ONE coercion made explicit.

    `get_major` returns the EMPTY STRING for a non-numeric version, because its trailing `|| echo "0"` is dead code: `grep -o '^[0-9]*'` matches a zero-length string and exits 0 while printing nothing. The twin survives it because its only consumer is `[[ a -gt b ]]`, where bash reads an empty operand as 0, so that coercion is applied HERE and nowhere else. Writing `int(out or 0)`
    inline would hide the fact that the two implementations differ in what they RETURN and agree only in what they COMPARE.
    """
    out = _bash('%s\nget_major "$1"' % GET_MAJOR, version).strip()
    return int(out) if out else 0


# --------------------------------------------------------------------------- get_major, against the real pipeline ---------------------------------------------------------------------------


def test_get_major_agrees_with_the_pipeline_on_every_shape() -> None:
    for version in (
        "v1.2.3",
        "1.2.3",
        "v0.0.0-20240101120000-abcdef123456",
        "v2+incompatible",
        "v10.4.1",
        "vlatest",
        "",
        "v",
        "master",
    ):
        assert go_deps.get_major(version) == _bash_major(version), version


def test_get_major_orders_a_major_bump_above_a_minor_one() -> None:
    """The MIRROR. Without it a `get_major` returning 0 for everything passes."""
    assert go_deps.get_major("v2.0.0") > go_deps.get_major("v1.9.9")
    assert not go_deps.get_major("v1.9.9") > go_deps.get_major("v1.2.3")


# --------------------------------------------------------------------------- The bash read, against the real read ---------------------------------------------------------------------------


def test_read_fields_agrees_with_bash_read() -> None:
    for line in (
        "github.com/a/b v1.0.0 v1.0.1 minor",
        "__PROBE_FAILED__ go-list exit=2 go: some error with  interior  spacing ",
        "__PROBE_FAILED__ go-list returned no modules at all",
        "  leading and trailing   ",
        "one",
        "",
    ):
        want = _bash(READ_FIELDS, line).split("\n")[:4]
        assert go_deps._read_fields(line, 4) == want, line


def test_the_sentinel_remainder_survives_into_the_report() -> None:
    """The only reason a probe failure says WHY. `str.split()` would not do it."""
    fields = go_deps._read_fields("__PROBE_FAILED__ go-list exit=2 a  b   c", 4)
    assert fields[3] == "a  b   c"


# --------------------------------------------------------------------------- The JSON slurp, against the real jq ---------------------------------------------------------------------------

STREAM = (
    '{"Path":"main","Version":"v0.1.0","Main":true}\n'
    '{"Path":"github.com/a/b","Version":"v1.0.0","Update":{"Version":"v1.0.1","Time":"2024-01-01T00:00:00Z"}}\n'
    '{"Path":"github.com/c/d","Version":"v1.0.0","Indirect":true,"Update":{"Version":"v1.0.1"}}\n'
    '{"Path":"github.com/e/f","Version":"v1.0.0","Update":{"Version":"v2.0.0"}}\n'
)


def _python_records(stream: str) -> list[str]:
    out: list[str] = []
    for item in go_deps.slurp_json(stream):
        if item.get("Indirect") is True or item.get("Update") is None:
            continue
        update = item["Update"]
        out.append(
            "%s %s %s %s"
            % (
                item.get("Path", ""),
                item.get("Version", ""),
                update.get("Version", ""),
                update.get("Time") or "",
            )
        )
    return out


def test_slurp_and_projection_agree_with_jq() -> None:
    code, out, err = diff.bash_streams(
        "printf '%%s' \"$STREAM\" | %s" % JQ_RECORDS,
        env={"STREAM": STREAM, "PATH": "/usr/bin:/bin"},
    )
    assert code == 0, err
    # jq renders the trailing empty Time as a trailing space, and so does the projection above. Compared as-is rather than stripped: that space reaches `read`, where it decides whether `uptime` is empty.
    assert _python_records(STREAM) == out.split("\n")[:-1]


def test_slurp_reads_back_to_back_objects_with_no_separator() -> None:
    assert [d["Path"] for d in go_deps.slurp_json('{"Path":"a"}{"Path":"b"}')] == ["a", "b"]


def test_slurp_raises_on_garbage_rather_than_returning_empty() -> None:
    """A PARSE FAILURE MUST NOT LOOK LIKE A CLEAN TREE.

    This is the 2026-07-27 defect in miniature: the old pipeline sent both commands' errors to /dev/null and `|| true`d the result, so an unreadable stream produced zero records, which is byte-identical to "nothing is outdated". The caller turns this exception into a `__PROBE_FAILED__` sentinel; returning `[]` here would put the defect straight back.
    """
    for bad in ("{oops", "[1,2", "not json at all"):
        try:
            go_deps.slurp_json(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


# --------------------------------------------------------------------------- The date parser and the module discovery ---------------------------------------------------------------------------


def test_parse_date_is_gnu_date() -> None:
    assert go_deps.parse_date("1970-01-02T00:00:00Z") == "86400"
    assert go_deps.parse_date("not-a-date") is None


def test_go_dirs_finds_only_directories_carrying_a_go_mod(tmp_path: pathlib.Path) -> None:
    (tmp_path / "private" / "renet").mkdir(parents=True)
    (tmp_path / "private" / "renet" / "go.mod").write_text("module x\n", encoding="utf-8")
    (tmp_path / "private" / "account").mkdir()
    (tmp_path / "private" / "nothing").mkdir()
    found = go_deps.go_dirs(tmp_path)
    assert [pathlib.Path(p).name for p in found] == ["renet"]


def test_go_dirs_on_a_tree_with_no_private_directory(tmp_path: pathlib.Path) -> None:
    """THE TWIN'S VACUITY HOLE, pinned here as it is pinned in the selftest.

    An empty list makes `main` print "No Go submodules found to check" and exit 0, having probed nothing. That is the twin's verdict, reproduced on purpose, and it is reported as a defect rather than fixed inside a port.
    """
    assert go_deps.go_dirs(tmp_path) == []


# --------------------------------------------------------------------------- The advisory shape ---------------------------------------------------------------------------


def test_emit_advisory_header_is_id_then_name_in_parens(capsys, monkeypatch) -> None:
    # RESET INSIDE THE TEST, not in the autouse fixture. `capsys` installs its replacement streams AFTER fixture setup, so a logger bound during setup writes to pytest's outer capture and `capsys.readouterr().err` comes back empty -- a test that reads as "the gate printed nothing" when the gate printed exactly the right thing somewhere else.
    #
    # BOTH RENDERINGS ARE PINNED, and the environment is SET rather than
    # inherited. `ci_error` is `::error::` on STDOUT when CI=true and
    # `log_error` on STDERR otherwise (go_deps.py:222-232) -- "THE PREFIX IS THE ENVIRONMENT'S DECISION, NOT THE GATE'S". This test used to assert `captured.err` unconditionally, which is true only off CI: it passed on every developer machine and failed in run 34970782616, the first in this wave to let quality-security finish, with the header sitting in `out`. Asserting one
    # rendering while the code documents two is how a gate gets exercised in only half the world it runs in.
    monkeypatch.delenv("CI", raising=False)
    log.reset()
    go_deps.emit_advisory("error", "github.com/a/b", "go-deps-blocklist entry", "do the thing")
    captured = capsys.readouterr()
    assert "github.com/a/b (go-deps-blocklist entry)" in captured.err
    # The hints go to STDOUT while the header goes to STDERR. That split is emit-advisory.sh's, and it is what the shadow comparator sees.
    assert captured.out == "  Fix: do the thing\n"

    monkeypatch.setenv("CI", "true")
    log.reset()
    go_deps.emit_advisory("error", "github.com/a/b", "go-deps-blocklist entry", "do the thing")
    captured = capsys.readouterr()
    # Under CI the annotation and the hint share STDOUT, because a GitHub workflow command is only read there.
    assert captured.out == (
        "::error::github.com/a/b (go-deps-blocklist entry)\n  Fix: do the thing\n"
    )
    assert captured.err == ""


def test_emit_advisory_omits_an_absent_action_line(capsys) -> None:
    log.reset()
    go_deps.emit_advisory("warn", "id", "name", "fix")
    assert "Action:" not in capsys.readouterr().out


def test_module_record_projection_matches_the_gates_own_json_helper() -> None:
    """A guard on the test's own fixture builder, not on the gate.

    `_module_json` is what the selftest plants with; if it stopped producing an `Update` block, every plant below would fire against a module the gate is not even meant to report.
    """
    record = json.loads(go_deps._module_json("a", "v1", "v2", "2024-01-01T00:00:00Z"))
    assert record["Update"]["Version"] == "v2"
    assert record["Update"]["Time"] == "2024-01-01T00:00:00Z"
    assert "Time" not in json.loads(go_deps._module_json("a", "v1", "v2"))["Update"]


# --------------------------------------------------------------------------- check_entry_age: the age-based blocklist rot check, end to end ---------------------------------------------------------------------------

# The same isolation `test_core_age.py`'s git fixtures use: without it a fixture inherits the developer's `init.defaultBranch`, commit template and gpg signing, and passes or fails per machine.
_GIT_ISOLATED_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


def _age_fixture(tmp_path: pathlib.Path, name: str, age_days: int, content: str) -> pathlib.Path:
    """A repository whose `listfile` line was added `age_days` ago.

    `check_entry_age`'s own contract -- verdict, then `emit_advisory`, then the exit-code-as-return-value split -- used to be proved here through the now-deleted `.ci/scripts/lib/age-check.sh` shim (`test_core_age.py`'s `test_shim_emits_through_emit_advisory_and_returns_one` and its control). That shim's only caller, `check-go-deps.sh`, was deleted in W7P5-c, and the shim went
    with it. This is the same fixture shape, driving the SURVIVING Python composition directly rather than through bash.
    """
    repo = tmp_path / name
    repo.mkdir()
    env = dict(_GIT_ISOLATED_ENV)
    subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
    (repo / "listfile").write_text(content + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "listfile"], cwd=repo, env=env, check=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - age_days * 86400))
    commit_env = dict(env, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=repo, env=commit_env, check=True)
    return repo


def test_check_entry_age_an_old_entry_fails_and_emits(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    log.reset()
    repo = _age_fixture(tmp_path, "old", 400, "ENTRY_OLD")
    failed = go_deps.check_entry_age("listfile", "ENTRY_OLD", "test-id", "name", root=repo)
    assert failed is True
    combined = "".join(capsys.readouterr())
    assert "days old" in combined
    assert "yearly re-review required" in combined


def test_check_entry_age_control_a_fresh_entry_is_silent_and_passes(
    tmp_path, capsys, monkeypatch
) -> None:
    """CONTROL for the case above: an emitter that always emits passes that one too."""
    monkeypatch.delenv("CI", raising=False)
    log.reset()
    repo = _age_fixture(tmp_path, "fresh", 5, "ENTRY_FRESH")
    failed = go_deps.check_entry_age("listfile", "ENTRY_FRESH", "test-id", "name", root=repo)
    assert failed is False
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_selftest_passes() -> None:
    assert go_deps.selftest() == 0
