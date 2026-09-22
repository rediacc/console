r"""Port of `.ci/scripts/test/gates/test-commit-identity.sh`, retired in W7 P5.

Drives the REAL `.ci/scripts/quality/check_commit_identity.py` against a fake `gh`. The bash gate script this test used to drive (`check-commit-identity.sh`) is retired in the same change: `.github/workflows/ci-quality.yml` already invokes the Python entry point directly, and the K=5 shadow ledger under `.ci/shadow/w7p2-commit-identity.observations.jsonl` licenses the equivalence
this port checks once more, case for case, before the twin leaves.

THAT GATE'S VERDICT IS AN API ANSWER, so the only way to test it without a live PR is to control what the API says. A fake `gh` on PATH serves fixture JSON and applies the caller's own `--jq` to it, which is the pattern `test_gate_review_status.py` already uses.

WHAT IT GUARDS. 30 of 42 commits on branch 0903-1 carried an email GitHub does not link to the operator's account -- same display name as the good ones, so `git log` looked clean, while GitHub rendered them with no avatar and no contribution credit. Fixing it cost a history rewrite across four repositories.

THE CASES THAT MATTER MOST are the ones where a wrong gate would be QUIET: an empty commit list, a failed `gh`, and a truncated page. Each of those is a way to inspect nothing and print a checkmark, which is the exact shape `check-claude-attribution.sh` was repaired for.
"""

import json
import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_commit_identity.py")

# A fake `gh` that ROUTES BY URL and applies the caller's own `--jq` to the matching fixture. Two shapes, because the gate reads the PR object for the compare range and its commit count, then the compare endpoint for the commits. A single-fixture fake would feed the commit list to the metadata read and the gate would refuse every case
# for the wrong reason.
#
# `-c` MATTERS: real `gh --jq` emits ONE COMPACT OBJECT PER LINE, and the gate's commit count is measured against exactly that shape. A bare `jq -r` pretty-prints, which would make this fake misreport the commit count -- invisible while nothing depended on the exact count, fatal now that completeness is judged against `.commits`.
FAKE_GH = r"""#!/bin/bash
set -uo pipefail
[ "$FAKE_GH_RC" -ne 0 ] && { echo "simulated gh failure" >&2; exit "$FAKE_GH_RC"; }
jqexpr=""
prev=""
url=""
for a in "$@"; do
  [ "$prev" = "--jq" ] && jqexpr="$a"
  case "$a" in repos/*) [ -z "$url" ] && url="$a" ;; esac
  prev="$a"
done
case "$url" in
  */compare/*) fixture="$GH_FIXTURE_COMPARE" ;;
  *)           fixture="$GH_FIXTURE_META" ;;
esac
if [ -n "$jqexpr" ]; then jq -r -c "$jqexpr" <"$fixture"; else cat "$fixture"; fi
"""


def write_fake_gh(bindir) -> None:
    path = bindir / "gh"
    path.write_text(FAKE_GH, encoding="utf-8")
    path.chmod(0o755)


def commit_json(sha, login, clogin, email) -> dict:
    """`commit_json <sha> <author-login|None> <committer-login|None> <email>`.

    `author`/`committer` are the GitHub ACCOUNTS, null when the email resolves to nobody -- which is the whole subject of the gate. Returns a DICT, not pre-serialised text: `run_gate` embeds several of these inside one `{"commits": [...]}` document, and stringifying here would double-encode each one into a JSON STRING rather than a JSON OBJECT -- the exact
    "Cannot index string with string" shape jq reports when handed an array of strings instead of objects.
    """
    return {
        "sha": sha,
        "author": None if login is None else {"login": login},
        "committer": None if clogin is None else {"login": clogin},
        "commit": {"author": {"email": email, "name": "N"}},
    }


def run_gate(tmp_path, commits, gh_rc=0, declared=None) -> harness.RunResult:
    """`run_gate <commits> [gh_rc] [declared-count]` -- LAST_OUT is `result.combined`."""
    compare_doc = {"commits": commits}
    compare_path = tmp_path / "compare.json"
    compare_path.write_text(json.dumps(compare_doc), encoding="utf-8")
    n = len(commits)
    if declared is None:
        declared = n
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        json.dumps({"base": {"sha": "base0000"}, "head": {"sha": "head0000"}, "commits": declared}),
        encoding="utf-8",
    )
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    write_fake_gh(bindir)
    return harness.run(
        ["python3", str(GATE)],
        env={
            "PATH": "%s%s%s" % (bindir, os.pathsep, os.environ.get("PATH", "")),
            "GH_FIXTURE_META": str(meta_path),
            "GH_FIXTURE_COMPARE": str(compare_path),
            "FAKE_GH_RC": str(gh_rc),
            "GITHUB_TOKEN": "x",
            "PR_NUMBER": "1",
            "GITHUB_REPOSITORY": "rediacc/console",
        },
    )


# -- 1. THE PLANT: an unattributed author is named ---------------------------


def test_null_author_fails(gate, tmp_path):
    result = run_gate(
        tmp_path, [commit_json("0d6611aaaa", None, "mfbayraktar", "muhammed@rediacc.com")]
    )
    gate.assert_exit_code(1, result.rc, "a commit GitHub attributes to nobody must fail")
    gate.assert_contains(result.combined, "0d6611a", "naming the sha")
    gate.assert_contains(result.combined, "muhammed@rediacc.com", "and the email")
    gate.log_pass("an unattributed author is reported by sha and address")


# -- 2. CONTROL: an attributed commit passes ---------------------------------


def test_attributed_passes(gate, tmp_path):
    result = run_gate(
        tmp_path, [commit_json("1111111aaa", "mfbayraktar", "mfbayraktar", "mfbayraktar@live.com")]
    )
    gate.assert_exit_code(
        0, result.rc, "a fully attributed commit must pass, or every PR fails forever"
    )
    gate.assert_contains(result.combined, "all attributed", "and say what it cleared")
    gate.log_pass("CONTROL: an attributed commit passes, so case 1 means something")


# -- 3. Bots attribute, and must not need a special case --------------------- main carries github-actions[bot] commits. If they failed, the gate would not run on main and someone would add an exemption for a non-problem.


def test_bot_passes(gate, tmp_path):
    result = run_gate(
        tmp_path,
        [
            commit_json(
                "2222222aaa",
                "github-actions[bot]",
                "github-actions[bot]",
                "github-actions[bot]@users.noreply.github.com",
            )
        ],
    )
    gate.assert_exit_code(0, result.rc, "a bot commit resolves to an account and must pass")
    gate.log_pass("bot commits pass without an exemption")


# -- 4. The COMMITTER half is judged too ------------------------------------- The 30 real commits had both fields wrong together, which is exactly how a committer-only defect would have been missed if only the author were checked.


def test_null_committer_fails(gate, tmp_path):
    result = run_gate(
        tmp_path, [commit_json("3333333aaa", "mfbayraktar", None, "mfbayraktar@live.com")]
    )
    gate.assert_exit_code(
        1, result.rc, "an unattributed COMMITTER must fail even when the author is fine"
    )
    # `rc=1` ALONE IS NOT THIS CASE. The gate exits 1 for an unreadable API, a
    # missing token and a failed probe too, so without naming the finding this
    # case passed whenever anything at all went wrong.
    gate.assert_contains(
        result.combined,
        "does not attribute to any account",
        "and it must fail FOR the unattributed commit, not for some other reason",
    )
    gate.log_pass("the committer field is judged, not just the author")


# -- 5-7. The QUIET failures: ways to inspect nothing and print a checkmark --


def test_empty_list_refuses(gate, tmp_path):
    result = run_gate(tmp_path, [])
    gate.assert_exit_code(1, result.rc, "an EMPTY commit list is a failed read, not a clean PR")
    gate.assert_contains(result.combined, "empty", "and say so")
    gate.log_pass("an empty commit list refuses instead of passing vacuously")


def test_gh_failure_refuses(gate, tmp_path):
    result = run_gate(
        tmp_path,
        [commit_json("4444444aaa", "mfbayraktar", "mfbayraktar", "ok@example.com")],
        gh_rc=1,
    )
    gate.assert_exit_code(1, result.rc, "a failed gh call must refuse, never report clean")
    gate.assert_contains(result.combined, "Cannot certify", "with the fail-closed wording")
    gate.log_pass("an unreadable API refuses rather than clearing the PR")


def test_short_read_refuses(gate, tmp_path):
    # A SHORT READ is refused -- the shape that replaced the old 250 page cap. The cap could only notice truncation at one number; this notices it at any.
    result = run_gate(
        tmp_path,
        [commit_json("6666666aaa", "mfbayraktar", "mfbayraktar", "ok@example.com")],
        declared=3,
    )
    gate.assert_exit_code(1, result.rc, "reading 1 of a declared 3 commits cannot clear the PR")
    gate.assert_contains(result.combined, "read 1 commit(s)", "naming what it actually read")
    gate.assert_contains(result.combined, "the PR reports 3", "and what the PR says it should have")
    gate.log_pass("an incomplete commit list is refused, not judged in part")


def test_over_the_old_cap_is_judged(gate, tmp_path):
    # MIRROR, and the regression this whole endpoint change exists to prevent: a PR LARGER than the old 250 cap must now be judged, not refused. Before the change this exact fixture produced "Cannot certify" on every run, which is how a 254-commit PR came to have two unattributed commits nobody could see.
    commits = [
        commit_json("c%09d" % i, "mfbayraktar", "mfbayraktar", "ok@example.com")
        for i in range(1, 255)
    ]
    result = run_gate(tmp_path, commits)
    gate.assert_exit_code(
        0, result.rc, "254 complete commits must be JUDGED; refusing on size is the bug"
    )
    gate.assert_contains(
        result.combined, "254 commit(s), all attributed", "and say how many it cleared"
    )
    gate.log_pass("a PR over the retired 250 cap is judged rather than refused")


def test_over_the_old_cap_still_finds_the_offender(gate, tmp_path):
    # And the plant inside that same over-cap set: one bad commit among 254 must still be named. A completeness check that passed the set through without judging it would look identical to the case above.
    commits = [
        commit_json("c%09d" % i, "mfbayraktar", "mfbayraktar", "ok@example.com")
        for i in range(1, 254)
    ]
    commits.append(commit_json("917d1902dd", None, None, "muhammed@rediacc.com"))
    result = run_gate(tmp_path, commits)
    gate.assert_exit_code(1, result.rc, "one unattributed commit among 254 must still fail")
    gate.assert_contains(result.combined, "917d190", "naming the sha")
    gate.assert_contains(result.combined, "muhammed@rediacc.com", "and the address")
    gate.log_pass("PLANT: an offender hidden in a 254-commit PR is found")


# -- 8. CONTROL over the whole file: the fake must be what decides -----------


def test_control_fixture_decides(gate, tmp_path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    a = run_gate(a_dir, [commit_json("5555555aaa", None, "mfbayraktar", "bad@example.com")])
    b = run_gate(
        b_dir, [commit_json("5555555aaa", "mfbayraktar", "mfbayraktar", "good@example.com")]
    )
    if not (a.rc == 1 and b.rc == 0):
        gate.log_fail(
            "CONTROL: fixtures gave rc=%s and rc=%s; the fake gh is not deciding the verdict"
            % (a.rc, b.rc)
        )
    gate.log_pass("CONTROL: the fixture, and nothing else, flips the verdict")
