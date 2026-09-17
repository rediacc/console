"""`rediacc_ci.quality.plan_housekeeping` against the sed and bash it replaces.

WHAT THE SHADOW LEDGER ALREADY PROVES:
`.ci/shadow/w7p2-plan-housekeeping.observations.jsonl` drives both implementations end to end over five distinct committed git trees, each built
with per-file `GIT_COMMITTER_DATE` so the age instrument answers differently per
plan: an over-age plan, a second one plus a plan in the warn band, an allowlist entry that suppresses nothing, an expired entry beside a thin BLOCKER and a dangling path, and a compacted record whose blob does not resolve.

WHAT THE LEDGER CANNOT ISOLATE is the four text readers, and three of them decide an EXEMPTION, which is the only thing in this gate that can turn a red into a green:

  * `record_blob` and `record_status`, two `sed -n '1,10s/.../\\1/p'` programs
    whose two anchors were each paid for. A trailing `.*` accepted a 41-hex
    pointer by reading its first 40 characters, so a value the strict gate
    REJECTS would have been exempted here; and a window wider than ten lines
    lets a plan whose PROSE quotes `Status: compacted` route into the compacted
    branch.
  * `blob_is_real`, whose broken direction exempts every plan carrying the word.
  * the allowlist parser, which is this gate's OWN loop rather than
    `blocker-validator.sh`: a 40-character reason bar, a reason consumed by
    exactly one entry, and `${line// /}` stripping spaces and not tabs.

So every case below runs the REAL sed or the REAL bash against the Python.
"""

import datetime as dt
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import log, paths
from rediacc_ci.quality import plan_housekeeping as hk

TWIN = paths.CI_DIR.parent / ".ci" / "scripts" / "quality" / "check-plan-housekeeping.sh"
CONFIG = paths.CI_DIR.parent / ".ci" / "config" / "plan-lifecycle.json"

# check-plan-housekeeping.sh:128 and :138, verbatim.
BLOB_SED = r"""sed -n '1,10s/^Full-Text-Blob:[[:space:]]*\([0-9a-f]\{40\}\)[[:space:]]*$/\1/p' "$1" | head -1"""
# W12 P3.3. BUILT FROM THE CONFIG, NOT TYPED. This literal used to carry the alternation `compacted\|parked` verbatim, which made it the THIRD copy of one vocabulary beside the two twins. A test that hard-types what it is checking cannot see the two implementations agree on a word the config no longer has.
STATUS_SED = (
    r"""sed -n '1,10s/^Status:[[:space:]]*\(%s\)[[:space:]]*$/\1/p' "$1" | head -1"""
    % r"\|".join(hk.record_states(CONFIG))
)
# check-plan-housekeeping.sh:425, the DISPLAY status, whole-file on purpose.
DISPLAY_SED = (
    r"""sed -n 's/^[[:space:]]*\(\*\*\)\?Status[[:space:]]*[:=][[:space:]]*"""
    r"""\(\*\*\)\?\([A-Za-z][A-Za-z-]*\).*/\3/p' "$1" | head -1"""
)


@pytest.fixture(autouse=True)
def _fresh_logger():
    """See the sibling suites: the module logger caches one stream per process."""
    log.reset()
    yield
    log.reset()


def _sed(program: str, path: pathlib.Path) -> str:
    proc = subprocess.run(
        ["bash", "-c", program, "_", str(path)],
        capture_output=True,
        text=True,
        check=False,
        env={"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == "", proc.stderr
    return proc.stdout.strip()


def _write(tmp: pathlib.Path, body: str) -> pathlib.Path:
    path = tmp / "record.md"
    path.write_text(body, encoding="utf-8")
    return path


FILLER = "".join("filler %d\n" % i for i in range(1, 11))
BLOB = "a" * 40


# --------------------------------------------------------------------------- record_blob, against the real sed ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "want"),
    [
        ("# t\nStatus: compacted\nFull-Text-Blob: %s\n" % BLOB, BLOB),
        # A 41-hex value must be REFUSED, not silently truncated to 40.
        ("# t\nStatus: compacted\nFull-Text-Blob: %sf\n" % BLOB, ""),
        # A 39-hex value is not a pointer either.
        ("# t\nFull-Text-Blob: %s\n" % ("a" * 39), ""),
        # Trailing whitespace is allowed; trailing PROSE is not.
        ("# t\nFull-Text-Blob: %s  \n" % BLOB, BLOB),
        ("# t\nFull-Text-Blob: %s and some prose\n" % BLOB, ""),
        # Uppercase hex is not a git object name in this grammar.
        ("# t\nFull-Text-Blob: %s\n" % ("A" * 40), ""),
        # A pointer below line 10 is a pointer no consumer can see.
        ("# t\nStatus: compacted\n%sFull-Text-Blob: %s\n" % (FILLER, BLOB), ""),
        # ...and one ON line 10 is still inside the window.
        ("%sFull-Text-Blob: %s\n" % ("".join("f %d\n" % i for i in range(1, 10)), BLOB), BLOB),
        ("# t\nno pointer here\n", ""),
    ],
)
def test_record_blob_agrees_with_the_twin_sed(tmp_path: pathlib.Path, body: str, want: str) -> None:
    path = _write(tmp_path, body)
    assert _sed(BLOB_SED, path) == want
    assert hk.record_blob(path) == want


# --------------------------------------------------------------------------- record_status, against the real sed ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "want"),
    [
        ("# t\nStatus: compacted\n", "compacted"),
        ("# t\nStatus: parked\n", "parked"),
        # `parked` is NOT `compacted`: parking buys a smaller file, never an exemption, and collapsing the two is a one-word change.
        ("# t\nStatus: draft\n", ""),
        # The word in PROSE must not exempt anything.
        ("# t\nStatus: draft\n\nWe should set Status: compacted here one day.\n", ""),
        # A real header BELOW the window must not either.
        ("# t\n%sStatus: compacted\n" % FILLER, ""),
        # An indented header is not a header.
        ("# t\n  Status: compacted\n", ""),
        # Trailing prose on the line is not a header either.
        ("# t\nStatus: compacted for now\n", ""),
    ],
)
def test_record_status_agrees_with_the_twin_sed(
    tmp_path: pathlib.Path, body: str, want: str
) -> None:
    path = _write(tmp_path, body)
    assert _sed(STATUS_SED, path) == want
    assert hk.record_status(path) == want


def test_display_status_scans_the_whole_file_unlike_the_exemption_reader(
    tmp_path: pathlib.Path,
) -> None:
    """The two readers ARE different on purpose, and that is worth pinning.

    The DISPLAY status is only printed, so it scans the whole file because some plans put their header low. The EXEMPTION reader must agree with `wl_planrec.parse` exactly, so it does not.
    """
    body = "# t\n%sStatus: executing\n" % FILLER
    path = _write(tmp_path, body)
    assert _sed(DISPLAY_SED, path) == "executing"
    assert hk.display_status(path) == "executing"
    assert hk.record_status(path) == ""

    # THE BOLD FORM THE TWIN ACCEPTS IS `**Status:`, NOT `**Status**:`. The regex allows a leading `**` and then requires `Status` to be followed by
    # optional space and a `:` or `=`, so the closing `**` breaks the match.
    # Both sides agree on that, and the agreement is the assertion: a port that "fixed" the regex would print a status the twin prints as UNKNOWN.
    bold = _write(tmp_path, "# t\n**Status:** executing\n")
    assert _sed(DISPLAY_SED, bold) == hk.display_status(bold)
    closed = tmp_path / "closed.md"
    closed.write_text("# t\n**Status**: executing\n", encoding="utf-8")
    assert _sed(DISPLAY_SED, closed) == ""
    assert hk.display_status(closed) == ""


# --------------------------------------------------------------------------- blob_is_real, against a real repository ---------------------------------------------------------------------------


def test_blob_is_real_answers_yes_for_a_minted_blob_and_no_for_a_fake(
    tmp_path: pathlib.Path,
) -> None:
    """BOTH DIRECTIONS. A `blob_is_real` that always answers yes exempts every
    plan carrying the word `compacted`, which is the worse of the two failures
    and the reason the twin plants both."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=False, capture_output=True)
    minted = subprocess.run(
        ["git", "-C", str(tmp_path), "hash-object", "-w", "--stdin"],
        input="a control blob\n",
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert minted, "could not mint a scratch blob"
    assert hk.blob_is_real(minted, root=tmp_path)
    assert not hk.blob_is_real("0" * 40, root=tmp_path)
    assert not hk.blob_is_real("", root=tmp_path)


# --------------------------------------------------------------------------- The allowlist parser, against the real bash loop ---------------------------------------------------------------------------

ALLOW_LOOP = r"""
declare -A EXEMPT_UNTIL=()
ALLOW_PROBLEMS=()
reason=""
while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^[[:space:]]*#[[:space:]]*BLOCKER: ]]; then
        reason="${line#*BLOCKER:}"
        continue
    fi
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// /}" ]] && continue
    read -r expiry path <<<"$line"
    if [[ -z "${path:-}" ]]; then
        ALLOW_PROBLEMS+=("malformed entry '$line' (want: YYYY-MM-DD  path)")
        continue
    fi
    if [[ -z "${reason// /}" ]] || ((${#reason} < 40)); then
        ALLOW_PROBLEMS+=("$path carries no substantive '# BLOCKER:' line above it")
        reason=""
        continue
    fi
    EXEMPT_UNTIL["$path"]="$expiry"
    reason=""
done <"$1"
for k in "${!EXEMPT_UNTIL[@]}"; do printf 'E\t%s\t%s\n' "$k" "${EXEMPT_UNTIL[$k]}"; done | sort
for m in ${ALLOW_PROBLEMS[@]+"${ALLOW_PROBLEMS[@]}"}; do printf 'P\t%s\n' "$m"; done
"""

GOOD = "this plan is the standing reference for the release rotation and must outlive the window"


def _bash_allowlist(tmp: pathlib.Path, text: str) -> tuple[dict[str, str], list[str]]:
    path = tmp / "allow"
    path.write_text(text, encoding="utf-8")
    proc = subprocess.run(
        ["bash", "-c", ALLOW_LOOP, "_", str(path)],
        capture_output=True,
        text=True,
        check=False,
        env={"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    exempt: dict[str, str] = {}
    problems: list[str] = []
    for line in proc.stdout.split("\n"):
        if line.startswith("E\t"):
            _, key, value = line.split("\t")
            exempt[key] = value
        elif line.startswith("P\t"):
            problems.append(line.split("\t", 1)[1])
    return exempt, problems


@pytest.mark.parametrize(
    "text",
    [
        "# BLOCKER: %s\n2099-12-01  agent/PLAN-a.md\n" % GOOD,
        # A thin reason is refused, and the 40-character bar is this gate's own, stricter than blocker-validator.sh's 30.
        "# BLOCKER: short\n2099-12-01  agent/PLAN-a.md\n",
        "# BLOCKER: %s\n2099-12-01  agent/PLAN-a.md\n2099-12-02  agent/PLAN-b.md\n" % GOOD,
        # No reason at all.
        "2099-12-01  agent/PLAN-a.md\n",
        # One field is malformed.
        "# BLOCKER: %s\njustonefield\n" % GOOD,
        # A plain comment does NOT reset the armed reason.
        "# BLOCKER: %s\n# an ordinary comment\n2099-12-01  agent/PLAN-a.md\n" % GOOD,
        # ...and neither does a blank line, which is the opposite of blocker-validator.sh and is deliberate on the twin's part.
        "# BLOCKER: %s\n\n2099-12-01  agent/PLAN-a.md\n" % GOOD,
        # The last line without a terminating newline is still read.
        "# BLOCKER: %s\n2099-12-01  agent/PLAN-a.md" % GOOD,
        "",
        "# nothing but comments\n",
    ],
)
def test_allowlist_parser_agrees_with_the_twin_loop(tmp_path: pathlib.Path, text: str) -> None:
    want_exempt, want_problems = _bash_allowlist(tmp_path, text)
    got_exempt, got_problems = hk.parse_allowlist(text)
    assert got_exempt == want_exempt
    assert sorted(got_problems) == sorted(want_problems)


def test_a_tab_only_line_is_malformed_not_blank(tmp_path: pathlib.Path) -> None:
    """`${line// /}` STRIPS SPACES AND NOT TABS, so a tab-only line is an entry.

    Reproduced rather than tidied. A fixture full of spaces would never show it, which is exactly why it is asserted against the real loop here.
    """
    text = "# BLOCKER: %s\n\t\n" % GOOD
    want_exempt, want_problems = _bash_allowlist(tmp_path, text)
    got_exempt, got_problems = hk.parse_allowlist(text)
    assert got_exempt == want_exempt == {}
    assert any("malformed" in p for p in got_problems)
    assert sorted(got_problems) == sorted(want_problems)


# --------------------------------------------------------------------------- The age arithmetic ---------------------------------------------------------------------------


def test_age_days_reports_over_and_under_and_refuses_a_bad_date() -> None:
    now = dt.datetime.now(dt.UTC)
    assert hk.age_days((now - dt.timedelta(days=40)).isoformat()) == 40
    assert hk.age_days((now - dt.timedelta(days=2)).isoformat()) == 2
    assert hk.age_days("not-a-date") == hk.UNPARSEABLE
    # A naive stamp is read as UTC, which is the twin's `replace(tzinfo=dt.UTC)`.
    assert hk.age_days((now - dt.timedelta(days=5)).replace(tzinfo=None).isoformat()) == 5


def test_is_shallow_is_dead_in_the_twin_and_therefore_absent_here() -> None:
    """A finding about the twin, pinned so it is not silently re-imported.

    `is_shallow()` is defined at `check-plan-housekeeping.sh:275` and called
    nowhere; the live logic reads the graft list per plan, which is the third
    iteration the header describes. If a future edit gives it a caller, this test fails and whoever ports the twin next has to decide deliberately.
    """
    text = TWIN.read_text(encoding="utf-8")
    assert "is_shallow()" in text, "the twin no longer defines is_shallow"
    assert text.count("is_shallow") == 1, "is_shallow now has a caller in the twin"
    assert "is_shallow" not in (
        paths.CI_DIR / "rediacc_ci" / "quality" / "plan_housekeeping.py"
    ).read_text(encoding="utf-8").replace("`is_shallow()`", "")


def test_inline_controls_hold() -> None:
    """The twin's control block, which runs before any verdict on every run."""
    assert hk.inline_controls(33) == []


def test_selftest_passes() -> None:
    assert hk.selftest() == 0


# --------------------------------------------------------------------------- W12 P3.3. The record-status vocabulary: ONE source, and the mirror is checked ---------------------------------------------------------------------------


def test_the_config_mirror_equals_wl_planrec_record_states_both_directions() -> None:
    """`.ci/config/plan-lifecycle.json` mirrors `wl_planrec.RECORD_STATES`.

    THE ORIGIN IS THE HOOK CONSTANT, not the config. `check_plan_record.py`
    imports `R.RECORD_STATES` by name (`:1405`) and cannot drift; the
    housekeeping pair CANNOT import it, because that gate must stay runnable in a checkout with no `.claude/`, which is the only reason a config exists at all. So the config is a mirror, and this is the comparison that makes it one rather than a fourth copy.

    BOTH DIRECTIONS, and the reverse is the interesting one: a state added to the hook and not to the config makes a plan a record in `check:ci-plan-record` and an OFFENDER in `check:ci-plan-housekeeping`, on a clock, with no way for the author to tell which reader is wrong.

    NOT SKIPPED WHEN THE HOOKS ARE ABSENT WITHOUT SAYING SO. `pytest.skip` prints the reason, which is the difference between "checked and equal" and "not checked".
    """
    stop = paths.CI_DIR.parent / ".claude" / "hooks" / "stop"
    if not (stop / "wl_planrec.py").is_file():
        pytest.skip("no %s in this checkout, so the mirror has no origin to compare against" % stop)

    sys.path.insert(0, str(stop))
    try:
        import wl_planrec  # noqa: PLC0415 -- the sys.path hop above is what makes it importable
    finally:
        sys.path.remove(str(stop))

    mirror = set(hk.record_states(CONFIG))
    origin = set(wl_planrec.RECORD_STATES)
    assert mirror, "the config carries no record_states, so nothing would ever be a record"
    assert origin, "wl_planrec.RECORD_STATES is empty, so the origin itself has no vocabulary"
    assert mirror - origin == set(), "in the config but not in wl_planrec.RECORD_STATES"
    assert origin - mirror == set(), "in wl_planrec.RECORD_STATES but not in the config"


def test_neither_twin_hard_types_the_alternation_any_more() -> None:
    """The point of the config is that the word appears in ONE place.

    A twin that reads the config AND keeps its old literal still works, and the literal is then a copy waiting to be edited by someone who greps for the word. This asserts the copies are gone from both twins rather than merely inert.
    """

    def code_only(text: str, comment: str) -> str:
        """The file with its comment lines dropped.

        BOTH TWINS QUOTE THE OLD LITERAL IN A COMMENT, on purpose: the archaeology of why the vocabulary moved is the most useful thing in either file. A raw substring check reads that prose as a live copy and reds for a reason that has nothing to do with the code, which is the shape of a control that fires on its own fixture.
        """
        return "\n".join(ln for ln in text.split("\n") if not ln.lstrip().startswith(comment))

    py = code_only(
        (paths.CI_DIR / "rediacc_ci" / "quality" / "plan_housekeeping.py").read_text(
            encoding="utf-8"
        ),
        "#",
    )
    sh = code_only(TWIN.read_text(encoding="utf-8"), "#")
    # The Python twin's status regex, and the bash twin's sed alternation.
    assert "(compacted|parked)" not in py
    assert r"\(compacted\|parked\)" not in sh
    # ...and both really do read the key, so this is not passing by deletion.
    assert '"record_states"' in py or "record_states" in py
    assert "record_states" in sh


def test_an_empty_vocabulary_matches_nothing_rather_than_the_empty_status() -> None:
    """The failure mode a naive `"|".join([])` produces.

    The empty alternation `()` matches `Status:` with nothing after it, so a plan whose header is a bare `Status:` would be reported as a record whose
    status is the empty string, and `record_status(path) == "compacted"` would be
    False while `record_status(path)` was truthy nowhere. Cheaper to make the empty vocabulary unmatchable and refuse in `main()`.
    """
    assert hk._status_re(()).match("Status: compacted") is None
    assert hk._status_re(()).match("Status: ") is None
    assert hk._status_re(("compacted",)).match("Status: compacted") is not None
    assert hk._status_re(("compacted",)).match("Status: parked") is None


def test_record_states_reads_nothing_rather_than_guessing(tmp_path: pathlib.Path) -> None:
    """An unreadable or key-less config yields (), never a default vocabulary.

    () is the SAFE direction: nothing is a record, so nothing is exempt and every aged plan stays on the clock. A hard-coded fallback would exempt plans because a file failed to parse.
    """
    missing = tmp_path / "nope.json"
    assert hk.record_states(missing) == ()
    keyless = tmp_path / "keyless.json"
    keyless.write_text('{"warn_days": 26}', encoding="utf-8")
    assert hk.record_states(keyless) == ()
    torn = tmp_path / "torn.json"
    torn.write_text("{not json", encoding="utf-8")
    assert hk.record_states(torn) == ()
    good = tmp_path / "good.json"
    good.write_text('{"record_states": ["compacted"]}', encoding="utf-8")
    assert hk.record_states(good) == ("compacted",)
