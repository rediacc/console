"""`rediacc_ci.core.review_budget` against the live `.ci/scripts/lib/common.sh`.

THE TWIN IS LIVE AND MERGE-BLOCKING. `.ci/scripts/review/review-status.sh:343` and `.ci/scripts/review/claude-review-gate.sh:858` both call `review_spend_total`, and `.github/workflows/review-status.yml:115` turns the first one's verdict into the required "Review Complete" check run. So these comparisons source the real file.

THE AWK IS COMPARED AGAINST THE REAL AWK, EXTRACTED FROM THE TWIN AT TEST TIME.
`review_attempt_states` cannot be driven end to end without `gh` and a live PR, but the interesting half of it is a pure awk program, and `_twin_awk()` below pulls that program out of the twin's own source rather than pasting a copy into
this file. A copy would agree with itself forever; the extraction goes red when
the twin's awk changes, which is exactly when a reader should look.

DEFECT 1 WAS FIXED 2026-09-10, IN THE TWIN, IN LOCKSTEP WITH THIS FILE.
`review_report_count`, `review_attempt_states`, `review_spend_total` and `review_spent_attempt_count` now route through `gh_retry` (the exact fix their own file already carried 160 lines above them) and propagate a `gh` failure as a real nonzero return instead of `... || true`. `pr_diff_loc` is UNCHANGED and UNCHANGED ON PURPOSE: its own comment states failing to 0 is the
deliberate, safe direction (an unreadable PR lands in the smallest review-cost tier), which is the opposite of the other three's problem (a swallowed failure zeroes the NUMERATOR, so the cap never arrives and every push pays for another review). `test_the_twin_now_fails_loudly_on_a_gh_failure` drives the TWIN with a failing `gh` on PATH and asserts the three fixed functions now
exit nonzero while `pr_diff_loc` still answers `0` at exit 0. `test_the_port_refuses_rather_than_
answering_zero` drives the PORT the same way; both sides now agree.
"""

import re
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.core import ghx
from rediacc_ci.core import review_budget as rb
from rediacc_ci.tests import differential as diff

TWIN_REL = ".ci/scripts/lib/common.sh"
TWIN = paths.from_root(TWIN_REL)
PY = "PYTHONPATH=%s python3 -m rediacc_ci.core.review_budget" % paths.from_root(".ci")


def _sh(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def twin(body: str, stdin: str = "", **env):
    script = "source %s\n%s\n" % (_sh(str(TWIN)), body)
    proc = subprocess.run(
        ["bash", "-c", "bash -c %s" % _sh(script)],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.repo_root()),
        env=diff.env_for(**env),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def port(argv: list[str], stdin: str = "", **env):
    proc = subprocess.run(
        ["bash", "-c", "%s %s" % (PY, " ".join(_sh(a) for a in argv))],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.repo_root()),
        env=diff.env_for(**env),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------- 1. THE DENOMINATOR (common.sh:534-550) ---------------------------------------------------------------------------

CAP_CASES = [
    "0",
    "1",
    "9999",
    "10000",
    "10001",
    "49999",
    "50000",
    "50001",
    "250000",
    # Every non-`^[0-9]+$` value lands in the SMALLEST tier, which is the conservative direction for this number.
    "abc",
    "",
    "-5",
    "1e3",
    "007",
    " 10 ",
]


@pytest.mark.parametrize("value", CAP_CASES)
def test_cap_for_agrees_with_the_twin(value):
    old = twin("review_cap_for %s" % _sh(value))
    new = port(["cap-for", value])
    assert old == new, "cap_for(%r): twin=%r port=%r" % (value, old, new)


def test_the_cap_bands_are_the_operators_table():
    """common.sh:522-524, asserted as numbers rather than trusted as a comment."""
    assert [rb.cap_for(n) for n in (0, 10000, 10001, 50000, 50001, 10**9)] == [
        3,
        3,
        5,
        5,
        7,
        7,
    ]


def test_the_cap_fallback_is_unreachable_while_the_last_tier_is_open():
    """common.sh:549's `echo 3`. Reachable only if someone closes the top tier."""
    assert rb.CAP_TIERS[-1][0] is None
    assert rb.CAP_FALLBACK == 3


# --------------------------------------------------------------------------- 2. THE INFRA CLASSES (common.sh:661-672) ---------------------------------------------------------------------------

CLASS_CASES = [
    "error_max_turns",
    "error_during_execution",
    "unknown",
    "",
    # The twin word-splits its space-separated string, so a multi-word value could never match a member. Both sides say no.
    "error_max_turns extra",
    "review step did not succeed",
]


@pytest.mark.parametrize("cls", CLASS_CASES)
def test_class_is_infra_agrees_with_the_twin(cls):
    old = twin("review_attempt_class_is_infra %s" % _sh(cls))
    new = port(["class-is-infra", cls])
    assert old == new, "class_is_infra(%r): twin=%r port=%r" % (cls, old, new)


def test_no_infra_class_contains_a_space():
    """common.sh:655-660 can only state this rule in a comment. Here it is checked.

    "Space-separated, and therefore SINGLE-TOKEN ONLY: the membership test word- splits this string, so a multi-word class added here would silently never match."
    """
    assert rb.INFRA_CLASSES
    for cls in rb.INFRA_CLASSES:
        assert " " not in cls, cls
        assert "\t" not in cls, cls


def test_the_unclassified_fallback_is_deliberately_not_infra():
    """common.sh:658-660 names it: an unclassified failure gets no free retries."""
    assert rb.class_is_infra("review step did not succeed") is False


# --------------------------------------------------------------------------- 3. THE AWK PARSER, against the twin's OWN awk program ---------------------------------------------------------------------------


def _twin_awk_program() -> str:
    """Extract the awk program from `review_attempt_states` in the live twin.

    NOT A PASTED COPY. A copy would agree with itself forever. This reads the real function body and pulls the single-quoted awk script out of it, so a change to the twin's awk turns these tests red.
    """
    source = TWIN.read_text(encoding="utf-8")
    match = re.search(r"^review_attempt_states\(\) \{(.*?)^\}", source, re.DOTALL | re.MULTILINE)
    assert match, "review_attempt_states() is no longer in %s" % TWIN_REL
    body = match.group(1)
    awk = re.search(r"awk '\n(.*?)\n\s*'", body, re.DOTALL)
    assert awk, "the awk program in review_attempt_states() is no longer single-quoted"
    return awk.group(1)


def _twin_parse(raw: str) -> str:
    program = _twin_awk_program()
    proc = subprocess.run(
        ["awk", program],
        input=raw,
        capture_output=True,
        text=True,
        check=False,
        env=diff.env_for(),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_the_awk_program_is_actually_extracted():
    """Anti-vacuity: an extraction that silently found nothing proves nothing."""
    program = _twin_awk_program()
    assert "claude-review-attempt:" in program
    assert "---REVIEW-ATTEMPT-EOF---" in program
    assert program.count("\n") >= 15


AWK_CASES = [
    (
        "full-marker",
        "claude-review-attempt: abc123 more\nattempts: 3\nclass: error_max_turns\n---REVIEW-ATTEMPT-EOF---",
    ),
    # A LEGACY marker, written before the count existed: one attempt, no class.
    ("legacy-marker", "claude-review-attempt: def456\n---REVIEW-ATTEMPT-EOF---"),
    (
        "two-markers",
        "x\nclaude-review-attempt: a1\nattempts: 2\n---REVIEW-ATTEMPT-EOF---\nclaude-review-attempt: b2\nclass: other\n---REVIEW-ATTEMPT-EOF---",
    ),
    # `END { flush() }` emits a trailing partial record.
    ("no-final-sentinel", "claude-review-attempt: zz\nattempts: 7"),
    # `&& sha == ""` means the SECOND key in one record is ignored.
    (
        "second-key-ignored",
        "claude-review-attempt: first\nclaude-review-attempt: second\n---REVIEW-ATTEMPT-EOF---",
    ),
    (
        "class-before-sha",
        "class: error_max_turns\nclaude-review-attempt: s1\n---REVIEW-ATTEMPT-EOF---",
    ),
    ("attempts-zero", "claude-review-attempt: s\nattempts: 0\n---REVIEW-ATTEMPT-EOF---"),
    # The `[0-9]+` guard: a non-numeric count leaves the default of 1, which is what makes DEFECT 2 latent.
    ("attempts-non-numeric", "claude-review-attempt: s\nattempts: zz\n---REVIEW-ATTEMPT-EOF---"),
    (
        "attempts-numeric-prefix",
        "claude-review-attempt: s\nattempts: 12x\n---REVIEW-ATTEMPT-EOF---",
    ),
    ("class-empty", "claude-review-attempt: s\nclass:\n---REVIEW-ATTEMPT-EOF---"),
    (
        "class-trailing-whitespace",
        "claude-review-attempt: s\nclass: error_max_turns   \n---REVIEW-ATTEMPT-EOF---",
    ),
    ("empty-input", ""),
    # UNANCHORED match, so an HTML comment carries the marker.
    ("html-comment", "prefix <!-- claude-review-attempt: sha9 --> tail\n---REVIEW-ATTEMPT-EOF---"),
    # `flush()` tests `sha != ""`, so a record with no sha emits nothing.
    ("no-sha-at-all", "attempts: 4\nclass: error_max_turns\n---REVIEW-ATTEMPT-EOF---"),
    ("tab-after-key", "claude-review-attempt:\tsha7\tjunk\n---REVIEW-ATTEMPT-EOF---"),
    # `attempts:` is ANCHORED, so an indented one does not match.
    ("attempts-indented", "claude-review-attempt: s\n attempts: 5\n---REVIEW-ATTEMPT-EOF---"),
    # `sub(/.*key/, ...)` is GREEDY, so the LAST key on a line wins.
    (
        "key-twice-one-line",
        "claude-review-attempt: one claude-review-attempt: two\n---REVIEW-ATTEMPT-EOF---",
    ),
    (
        "three-records",
        "claude-review-attempt: r1\n---REVIEW-ATTEMPT-EOF---\nclaude-review-attempt: r2\nattempts: 2\nclass: error_during_execution\n---REVIEW-ATTEMPT-EOF---\nclaude-review-attempt: r3\nattempts: 9\nclass: unknown\n---REVIEW-ATTEMPT-EOF---",
    ),
]


@pytest.mark.parametrize(("name", "raw"), AWK_CASES, ids=[c[0] for c in AWK_CASES])
def test_parse_attempt_states_matches_the_twins_awk(name, raw):
    expected = _twin_parse(raw)
    got = "".join(state.tsv() + "\n" for state in rb.parse_attempt_states(raw))
    assert got == expected, "%s: awk=%r port=%r" % (name, expected, got)


def test_the_awk_corpus_is_not_empty():
    assert len(AWK_CASES) >= 15


# --------------------------------------------------------------------------- 4. THE CHARGE LEDGER (common.sh:708-743) ---------------------------------------------------------------------------

STATE_CASES = [
    ("infra-discount-plus-plain", "a1\t3\terror_max_turns\nb2\t5\tunknown"),
    # `[[ "$charge" -lt 0 ]] && charge=0`: the discount CLAMPS.
    ("infra-underflow-clamps", "a1\t1\terror_max_turns"),
    ("infra-exactly-free", "a1\t2\terror_max_turns"),
    ("empty", ""),
    ("legacy-no-class", "a1\t1\t"),
    ("many-heads", "a\t1\t\nb\t2\terror_max_turns\nc\t7\tunknown\nd\t4\terror_during_execution"),
]


@pytest.mark.parametrize(("name", "states"), STATE_CASES, ids=[c[0] for c in STATE_CASES])
def test_chargeable_attempts_agrees_with_the_twin(name, states):
    old = twin('review_chargeable_attempts "$(cat)"', stdin=states)
    new = port(["chargeable"], stdin=states)
    assert old == new, "%s: twin=%r port=%r" % (name, old, new)


HEAD_CASES = [
    # LAST match wins: the twin overwrites without breaking.
    ("last-wins", "a\t1\tx\na\t9\terror_max_turns", "a"),
    ("absent-sha", "a\t1\tx", "zz"),
    ("single", "a\t4\terror_max_turns", "a"),
    ("empty-class", "a\t4\t", "a"),
]


@pytest.mark.parametrize(("name", "states", "sha"), HEAD_CASES, ids=[c[0] for c in HEAD_CASES])
def test_head_attempt_state_agrees_with_the_twin(name, states, sha):
    old = twin('review_head_attempt_state "$(cat)" %s' % _sh(sha), stdin=states)
    new = port(["head-state", sha], stdin=states)
    assert old == new, "%s: twin=%r port=%r" % (name, old, new)


EXHAUST_CASES = [
    ("infra-at-max", "a\t3\terror_max_turns", "a"),
    ("infra-above-max", "a\t9\terror_max_turns", "a"),
    ("infra-below-max", "a\t2\terror_max_turns", "a"),
    # Only the infra path can exhaust (common.sh:733-735).
    ("non-infra-never-exhausted", "a\t99\tunknown", "a"),
    ("legacy-never-exhausted", "a\t99\t", "a"),
    ("absent-sha", "a\t9\terror_max_turns", "zz"),
]


@pytest.mark.parametrize(
    ("name", "states", "sha"), EXHAUST_CASES, ids=[c[0] for c in EXHAUST_CASES]
)
def test_head_is_exhausted_agrees_with_the_twin(name, states, sha):
    old = twin('review_head_is_exhausted "$(cat)" %s' % _sh(sha), stdin=states)
    new = port(["head-exhausted", sha], stdin=states)
    assert old == new, "%s: twin=%r port=%r" % (name, old, new)


# Both operands non-empty ONLY. An empty operand makes the TWIN treat it as
# "not provided" and attempt a network fetch (common.sh:757-759); the port's
# `spend-total` CLI verb never fetches at all -- "THE FETCHING FORM IS DELIBERATELY NOT HERE" above -- so the two sides are not comparable on an empty operand. Before the DEFECT 1 fix this test happened to pass anyway,
# for the wrong reason: the twin's failed fetch silently zeroed to the same
# number the port's CLI produces by never fetching. The fix correctly broke
# that coincidence (the twin now fails loudly instead); the real fetch-failure
# behavior is covered by test_the_twin_now_fails_loudly_on_a_gh_failure and test_the_twin_now_fails_loudly_on_an_unbound_variable instead.
SPEND_CASES = [("3", "4"), (" 3 ", " 4 "), ("0", "0"), ("10", "0")]


@pytest.mark.parametrize(("posted", "spent"), SPEND_CASES)
def test_spend_total_agrees_with_the_twin(posted, spent):
    """The pre-fetched form, which is the one both live callers pass.

    `claude-review-gate.sh:858` passes both counts because it needs them
    separately for its log line; `review-status.sh:343` does not, and that arm
    goes through the network -- see DEFECT 1.
    """
    old = twin("review_spend_total 1 P %s %s" % (_sh(posted), _sh(spent)), GITHUB_REPOSITORY="o/r")
    new = port(["spend-total", posted, spent])
    assert old[0] == new[0] == 0, "twin=%r port=%r" % (old, new)
    assert old[1] == new[1], "twin=%r port=%r" % (old, new)


# --------------------------------------------------------------------------- 5. THE SNAPSHOT (common.sh:603-617) ---------------------------------------------------------------------------

SNAPSHOT_LINES = (
    "`PR-TASK: abc123`",
    "PR-TASK: deadbeefcafe",
    "PR-TASK:aabbcc",
    # NOT matched: the grep is anchored at `^`.
    "  PR-TASK: 112233",
    # NOT matched: lowercase hex only.
    "PR-TASK: ABCDEF",
    # NOT matched: fewer than 6 characters, and not hex.
    "PR-TASK:zzz",
    # NOT matched: trailing text after the id.
    "PR-TASK: abc123 and more",
)
SNAPSHOT = "\n".join(SNAPSHOT_LINES)


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    root = tmp_path_factory.mktemp("epics")
    (root / "agent" / "pr").mkdir(parents=True)
    (root / "agent" / "pr" / "0906-1.md").write_text(SNAPSHOT, encoding="utf-8")
    (root / "agent" / "pr" / "feat-x.md").write_text(SNAPSHOT, encoding="utf-8")
    (root / "agent" / "pr" / "quiet.md").write_text("nothing here\n", encoding="utf-8")
    return root


EPIC_CASES = ["0906-1", "feat/x", "quiet", "absent", ""]


@pytest.mark.parametrize("branch", EPIC_CASES)
def test_epic_ids_agrees_with_the_twin(snap, branch):
    env = {"WORKLIST_PUBLISH_ROOT": str(snap)}
    old = twin("review_epic_ids %s" % _sh(branch), **env)
    new = port(["epic-ids", branch], **env)
    assert old == new, "%s: twin=%r port=%r" % (branch, old, new)


def test_epic_ids_finds_exactly_the_three_well_formed_ids(snap):
    """The negative half. A test that only checked "found some" would pass a
    regex that matched every line."""
    found = rb.epic_ids("0906-1", {"WORKLIST_PUBLISH_ROOT": str(snap)})
    assert found == ["abc123", "deadbeefcafe", "aabbcc"]


def test_epic_ids_maps_a_slash_in_the_branch_to_a_dash(snap):
    env = {"WORKLIST_PUBLISH_ROOT": str(snap)}
    assert rb.epic_ids("feat/x", env) == rb.epic_ids("feat-x", env)


def test_epic_ids_treats_a_missing_snapshot_as_no_epics_not_an_error(snap):
    """common.sh:600-602: no snapshot means the flat, pre-epic review."""
    assert rb.epic_ids("absent", {"WORKLIST_PUBLISH_ROOT": str(snap)}) == []


def test_epic_ids_does_not_depend_on_the_cwd(snap, monkeypatch, tmp_path):
    """common.sh:606-611 records what a bare relative path cost."""
    env = {"WORKLIST_PUBLISH_ROOT": str(snap)}
    monkeypatch.chdir(tmp_path)
    assert rb.epic_ids("0906-1", env) == ["abc123", "deadbeefcafe", "aabbcc"]


# --------------------------------------------------------------------------- 6. DEFECT 1 -- pinned from BOTH sides ---------------------------------------------------------------------------


@pytest.fixture
def failing_gh(tmp_path):
    """A `gh` on PATH that fails the way a rate limit does."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "gh"
    stub.write_text(
        '#!/bin/bash\necho "gh: HTTP 403: API rate limit exceeded" >&2\nexit 1\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return str(bindir)


def test_the_twin_now_fails_loudly_on_a_gh_failure(failing_gh):
    """DEFECT 1, FIXED 2026-09-10. If this goes red, the fix has regressed.

    Three functions now route through `gh_retry`, so a failing `gh` (pipefail on, `gh_retry` returning 1) propagates as a real nonzero return instead of being discarded by `|| true`. `pr_diff_loc` is deliberately UNCHANGED: its own comment says failing to 0 is the safe, intended direction there.
    """
    env = {
        "PATH": "%s:/usr/bin:/bin" % failing_gh,
        "GITHUB_REPOSITORY": "o/r",
    }
    for body in [
        "review_report_count 553",
        "review_attempt_states 553 P",
        "review_spend_total 553 P",
        "review_spent_attempt_count 553 P",
    ]:
        rc, out, err = twin(body, **env)
        assert rc != 0, "%s: expected a loud failure, got exit 0 (%r)" % (body, out)
        assert "gh failed after 3 attempts" in err, "%s: %s" % (body, err)

    # pr_diff_loc is the one deliberate exception: still fails to 0 at exit 0.
    rc, out, err = twin('out="$(pr_diff_loc 553)"; echo "[$out]"', **env)
    assert rc == 0
    assert out.strip() == "[0]"


def test_the_twin_now_fails_loudly_on_an_unbound_variable(failing_gh):
    """DEFECT 1's second face, also closed by the same fix.

    Before the fix, `set -u` firing inside the command substitution left `posted` empty and `$(( + 4))` silently evaluated to 4 -- a hard abort produced a number. The new `|| return 1` on the assignment itself now catches that too, since bash gives a failed command substitution's exit status to the assignment statement that captured it.
    """
    rc, _out, err = twin(
        'review_spend_total 553 P "" 4',
        PATH="%s:/usr/bin:/bin" % failing_gh,
        GITHUB_REPOSITORY=None,
    )
    assert rc != 0
    assert "GITHUB_REPOSITORY: unbound variable" in err


def test_the_file_now_uses_the_fix_it_used_to_carry_unused():
    """`_gh_probe` / `gh_retry` / `gh_json` are 160 lines ABOVE these four.

    Before the fix this asserted the swallow sites did NOT use them, which was the contradiction DEFECT 1 named. Now it asserts the opposite: the three repaired functions adopted the pattern the file already had. `pr_diff_loc` deliberately did not, and is asserted to still swallow.
    """
    source = TWIN.read_text(encoding="utf-8")
    assert "_gh_probe()" in source
    assert "gh_retry()" in source
    assert "gh_json()" in source
    for fn in ("review_report_count", "review_attempt_states"):
        body = re.search(r"^%s\(\) \{(.*?)^\}" % fn, source, re.DOTALL | re.MULTILINE)
        assert body, fn
        assert "gh_retry" in body.group(1), "%s should route through gh_retry" % fn
    spend_total = re.search(r"^review_spend_total\(\) \{(.*?)^\}", source, re.DOTALL | re.MULTILINE)
    assert spend_total
    assert "|| return 1" in spend_total.group(1)
    diff_loc = re.search(r"^pr_diff_loc\(\) \{(.*?)^\}", source, re.DOTALL | re.MULTILINE)
    assert diff_loc
    assert "2>/dev/null" in diff_loc.group(1), "pr_diff_loc should still swallow (deliberate)"


def test_the_port_refuses_rather_than_answering_zero(failing_gh, monkeypatch):
    """The port's half of DEFECT 1: `core.ghx` raises where the twin returns 0."""
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % failing_gh)
    for call in (
        lambda: rb.report_count(553, repo="o/r"),
        lambda: rb.attempt_states(553, "P", repo="o/r"),
        lambda: rb.diff_loc(553, repo="o/r"),
        lambda: rb.spent_attempt_count(553, "P", repo="o/r"),
    ):
        with pytest.raises(ghx.GhError):
            call()


def test_diff_loc_reproduces_the_twins_zero_only_when_asked(failing_gh, monkeypatch):
    """common.sh:764-765's stated decision, opted into VISIBLY at the call site."""
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % failing_gh)
    assert rb.diff_loc(553, repo="o/r", on_error=rb.DIFF_LOC_FAILS_TO_ZERO) == 0
    assert rb.DIFF_LOC_FAILS_TO_ZERO == 0
    # And the smallest bucket is what that 0 buys, which is why it is not safe
    # while the NUMERATOR also fails to zero.
    assert rb.cap_for(0) == 3


def test_a_missing_github_repository_is_a_sentence_not_an_unbound_variable():
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY") as caught:
        rb.report_count(553, env={})
    assert "GITHUB_REPOSITORY is not set" in str(caught.value)
    assert "common.sh:592" in str(caught.value)


# --------------------------------------------------------------------------- 7. DEFECT 2 -- the non-numeric attempt count ---------------------------------------------------------------------------


def test_the_twin_aborts_on_a_non_numeric_attempt_count():
    """DEFECT 2, driven. `$((zz - 2))` under `set -u` is `zz: unbound variable`."""
    rc, _out, err = twin('review_chargeable_attempts "$(cat)"', stdin="a\tzz\tunknown")
    assert rc != 0
    assert "zz: unbound variable" in err


def test_the_port_names_the_row_instead_of_aborting():
    with pytest.raises(ValueError, match="not a number") as caught:
        rb.attempts_from_tsv("a\tzz\tunknown")
    assert "not a number" in str(caught.value)
    assert "common.sh:714" in str(caught.value)


def test_defect_2_is_latent_because_the_awk_forces_a_number():
    """Why nobody has hit DEFECT 2, asserted rather than assumed.

    The only producer is `review_attempt_states`, whose awk guards on `[0-9]+`
    and then does `n = line + 0`. A marker carrying `attempts: zz` therefore
    yields 1.
    """
    states = rb.parse_attempt_states(
        "claude-review-attempt: s\nattempts: zz\n---REVIEW-ATTEMPT-EOF---"
    )
    assert [s.attempts for s in states] == [1]
    assert (
        _twin_parse("claude-review-attempt: s\nattempts: zz\n---REVIEW-ATTEMPT-EOF---")
        == "s\t1\t\n"
    )


# --------------------------------------------------------------------------- 8. PLANTED DEFECTS -- proving the controls can fire ---------------------------------------------------------------------------


def test_planted_a_cap_tier_edit_is_caught_by_the_band_assertion(monkeypatch):
    monkeypatch.setattr(rb, "CAP_TIERS", ((10000, 3), (50000, 5), (100000, 7)))
    # The top tier is now CLOSED, so the fallback becomes reachable and a 200k-line diff gets 3 instead of 7 -- the smallest budget for the biggest diff, which is exactly backwards.
    assert rb.cap_for(200000) == 3
    assert rb.cap_for(200000) != 7


def test_planted_an_off_by_one_in_the_free_reattempts_changes_the_charge(monkeypatch):
    states = rb.parse_attempt_states(
        "claude-review-attempt: a\nattempts: 3\nclass: error_max_turns\n---REVIEW-ATTEMPT-EOF---"
    )
    assert rb.chargeable_attempts(states) == 1
    monkeypatch.setattr(rb, "REVIEW_FREE_REATTEMPTS_PER_HEAD", 3)
    assert rb.chargeable_attempts(states) == 0


def test_planted_a_non_infra_class_that_can_exhaust_is_a_new_restriction(monkeypatch):
    """common.sh:733-735: making a non-infra head exhaustible would be a NEW
    restriction wearing the costume of a relaxation."""
    states = rb.parse_attempt_states(
        "claude-review-attempt: a\nattempts: 99\nclass: unknown\n---REVIEW-ATTEMPT-EOF---"
    )
    assert rb.head_is_exhausted(states, "a") is False
    monkeypatch.setattr(rb, "INFRA_CLASSES", ("error_max_turns", "unknown"))
    assert rb.head_is_exhausted(states, "a") is True


def test_planted_a_content_qualifier_on_the_report_needle_undercounts(monkeypatch):
    """common.sh:560-573 measured what a content qualifier cost: #551 counted 0
    of 1, a completed review costing $4.66 registering as never having happened."""
    assert rb.REPORT_NEEDLE == "**Claude finished"
    monkeypatch.setattr(rb, "REPORT_NEEDLE", "**Claude finished with json:review-findings")
    body = "**Claude finished the review\n\nsome wrap-up text"
    assert body.startswith("**Claude finished")
    assert not body.startswith(rb.REPORT_NEEDLE), "the qualifier drops a real report"


def test_planted_an_unanchored_epic_regex_matches_an_indented_line():
    assert rb.EPIC_LINE.match("  PR-TASK: 112233") is None
    loose = re.compile(r"`?PR-TASK:[ \t]*([0-9a-f]{6,32})`?")
    assert loose.search("  PR-TASK: 112233") is not None, "which is the defect"


def test_planted_a_parse_states_that_takes_the_last_key_per_record():
    raw = "claude-review-attempt: first\nclaude-review-attempt: second\n---REVIEW-ATTEMPT-EOF---"
    assert [s.sha for s in rb.parse_attempt_states(raw)] == ["first"]
    assert _twin_parse(raw) == "first\t1\t\n"
