#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Idle-stop detection (I6), tick/completion evidence (I7), path citations, and the crashing-hook fail-closed control.

echo "== 91. I6: a stop with NOTHING inbound blocks on the first stop =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
CRONS='[]'
check "pending task + no cron + no bg + no lease blocks immediately" block "NOTHING WILL WAKE THIS SESSION"

echo "== 92. I6 CONTROLS: each wake-up source suppresses it =="
# Fresh fixture per control: chaining them on one fixture walks the stuck
# counter to its threshold and a later control fails for the wrong reason.
i6_fixture() {
    setup
    brief_now
    hand_now
    say "answer

## Remaining
| #7 | thing | pending, me |"
    task 7 pending "thing"
    CRONS='[]'
}
i6_fixture
CRONS='[{"id":"w","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
check "a live work cron is a wake-up" allow ""
i6_fixture
CRONS='[{"id":"p","schedule":"*/5 * * * *"}]'
check "v9: a poll cron ALONE is not a wake-up (it only reacts to others)" block "NOTHING WILL WAKE THIS SESSION"
i6_fixture
BG='[{"status":"running","description":"agent"}]'
check "a running background task is a wake-up" allow ""
i6_fixture
echo "- [>] (deadbeef) until:$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ) delegated to agent" >>"$WL"
check "a fresh [>] lease is a wake-up" allow ""

echo "== 93. I6: a CONFIRMED operator-blocked task is a legitimate idle =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | blocked, You (User Thinks So) |"
task 7 pending "thing"
CRONS='[]'
check "confirmed 'You (User Thinks So)' waits without a wake-up" allow ""

echo "== 94. I7: a tick without evidence blocks; a REAL pointer clears it =="
setup
say "done for now"
brief_now
reg_repo
run >/dev/null # marker init
echo '- [x] (deadbeef) fixed the flaky teardown' >>"$WL"
check "an evidence-free tick blocks" block "COMPLETION WITHOUT EVIDENCE"
# A fabricated hex pointer must NOT count: it names no real object.
python3 - "$WL" <<'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read().replace(
    "fixed the flaky teardown",
    "fixed the flaky teardown, see 0123abc4567",
)
open(p, "w").write(s)
PYEOF
check "a fabricated sha is not evidence" block "COMPLETION WITHOUT EVIDENCE"
python3 - "$WL" "$(git -C "$BASE/proj" rev-parse --short HEAD)" <<'PYEOF'
import sys
p, sha = sys.argv[1], sys.argv[2]
s = open(p).read().replace("see 0123abc4567", "proof " + sha)
open(p, "w").write(s)
PYEOF
check "a REAL git object in the line is evidence" allow ""

echo "== 95. I7: a task flipping to completed needs evidence near its #id =="
setup
brief_now
hand_now
reg_repo
task 7 pending "prove the budget flag binds"
say "working on it

## Remaining
| #7 | prove the budget flag binds | pending, me |"
run >/dev/null # marker init snapshots task 7 as pending
task 7 completed "prove the budget flag binds"
newturn
say "All done."
check "S-2 REPLAY: completed with no evidence anywhere blocks" block "COMPLETION WITHOUT EVIDENCE"
newturn
say "Done: #7 verified, exit 0 from the budget run."
check "evidence on the #id line clears it" allow ""

echo "== 96b. I7: the SHA arm spends its budget on the LONGEST candidates =="
# THE BUG THIS PINS, found live 2026-08-23. completion_evidence git-verifies at
# most five hex candidates to bound the git calls, and it took the first five in
# TEXT order. Every rendered item line opens with the mandatory session tag
# TWICE, and cited worklist ids are 8 hex as well, so a tick that cross-
# references its siblings spent the whole budget before reaching its real SHA:
# the more carefully an item was written, the more certainly it failed. It
# blocked five consecutive stops on a tick whose tree hash resolves.
#
# The controls below matter more than the regression case. A predicate that
# answers True more often is trivially "fixed" by deleting it, so the no-
# evidence, fabricated-SHA and fabricated-path arms have to keep FAILING, and
# the git-call count has to stay bounded or the fix is just "check them all".
OUT=$(
    python3 - "$(dirname "$HOOK")" "$(cd "$(dirname "$HOOK")/../../.." && pwd)" <<'PYEOF'
import sys

sys.path.insert(0, sys.argv[1])
import wl_checks as W  # noqa: E402
import wl_core as C  # noqa: E402

root = sys.argv[2]

# Counted, not assumed: the cap is the whole reason this arm orders candidates
# instead of simply checking all of them, so a fix that quietly unbounded the
# git calls has to red here rather than read as a pass.
calls = []
_orig = C._git


def _counting(r, *a):
    calls.append(a)
    return _orig(r, *a)


C._git = _counting
W.C._git = _counting

# Two leading tags is the REAL rendered shape, not a worst case: the session tag
# is mandatory and _render_line emits it on the folded line.
TAG = "- [x] (0ad063bf) (0ad063bf) "
# A tree hash that genuinely resolves in this checkout. DERIVED, not hardcoded,
# and that is the whole point: this was pinned to 444e9c09 -- the rewritten
# repo's root tree -- which resolves in a full local clone and NOT in the
# checkout CI builds. It went red in CI on run 32657161009 while passing
# locally, and the fixture control below is what named it rather than leaving a
# confusing downstream failure. `HEAD^{tree}` resolves in every checkout that
# has a HEAD at all: full, blobless, or shallow.
#
# Verified below rather than trusted, because a case built on a SHA that stopped
# resolving would go green by turning into the no-evidence case.
SHA = (C._git(root, "rev-parse", "HEAD^{tree}") or "").strip() or "d" * 40
IDS = "23d99308 ebe8b570 e263d2cc"

cases = [
    ("regression-real-sha-at-position-6", TAG + "rewrite verified " + IDS + " tree " + SHA, True),
    # THE CONTROL. Without this arm failing on purpose, the "fix" above is
    # indistinguishable from deleting the check.
    ("CONTROL-no-evidence-anywhere", TAG + "did the thing, it works now, all good", False),
    ("CONTROL-fabricated-40-hex-is-not-an-object", TAG + "verified " + IDS + " at " + "d" * 40, False),
    ("CONTROL-fabricated-file-line", TAG + "fixed at .claude/hooks/stop/no_such_file.py:617", False),
    ("resolving-file-line-alone-passes", TAG + "fixed at .claude/hooks/stop/wl_checks.py:617", True),
]

print(
    ("PASS " if C._git(root, "rev-parse", "--verify", "--quiet", SHA + "^{object}") else "FAIL ")
    + "fixture-sha-actually-resolves"
)
for name, text, want in cases:
    calls.clear()
    got = W.completion_evidence(root, text)
    print(("PASS " if got == want else "FAIL ") + "%s (got %s)" % (name, got))
    print(("PASS " if len(calls) <= 5 else "FAIL ") + "%s-git-calls-bounded (%d)" % (name, len(calls)))
PYEOF
)
if grep -qF "FAIL" <<<"$OUT"; then
    fail "96b: $OUT"
else
    pass "96b: a real SHA behind five short hex ids is found, and the fabricated/absent arms still report"
fi

echo "== 96. I7 CONTROL: completions that predate the marker never nag =="
setup
brief_now
reg_repo
task 9 completed "long-finished thing"
say "nothing new"
check "an init-stop snapshot asks nothing about old completions" allow ""
check "and the next stop sees no transition" allow ""

echo "== 97. a DOT-LEADING path is a valid citation (.ci, .github, .claude) =="
# `\b[\w]` cannot start on a dot, so `.ci/x.sh:9` matched but CAPTURED `ci/x.sh`,
# which resolves to nothing. That made most of this repo uncitable while the
# check looked strict. Caught by I7 firing on a real tick of mine.
setup
brief_now
hand_now
mkdir -p "$BASE/proj/.ci/scripts"
printf 'a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n' >"$BASE/proj/.ci/scripts/thing.sh"
say "answer

## Remaining
| #7 | thing | blocked, .ci/scripts/thing.sh:3 |"
task 7 pending "thing"
check "a .ci path resolves as a citation" allow ""

echo "== 98. CONTROL: a dot-leading path that does NOT exist is still rejected =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | blocked, .ci/scripts/nope.sh:3 |"
task 7 pending "thing"
check "an invented .ci path is caught" block "which does not exist"

echo "== 99. A CRASHING HOOK BLOCKS, it does not wave the stop through =="
# The hook's global escape hatch, and nobody put it there on purpose: an
# unhandled exception writes a traceback to stderr and NOTHING to stdout, the
# harness sees no decision, and the stop is ALLOWED. One bug anywhere silently
# disabled every check. A v8 cut really did crash on a tuple unpack and sail
# through; only a needle assertion caught it.
setup
CRASHED="$BASE/crashy.py"
sed "s/^def main():/def main():\n    raise RuntimeError('planted crash')/" "$HOOK" >"$CRASHED"
OUT=$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s"}' "$SID" "$BASE/proj" "$BASE/t.jsonl" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        GITHUB_ACTIONS="" python3 "$CRASHED" 2>/dev/null)
GOT=$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)
if [[ "$GOT" == "block" ]] && grep -qF 'planted crash' <<<"$OUT"; then
    echo "  PASS: a crash blocks and carries its traceback"
    PASS=$((PASS + 1))
else
    echo "  FAIL: a crash produced decision=$GOT (a crash must never allow)"
    echo "        out: ${OUT:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 100. CONTROL: the UNMODIFIED hook still allows a clean stop =="
# Without this, case 99 would pass on a hook that blocks unconditionally.
setup
brief_now
hand_now
say "all done"
CRONS='[{"id":"c","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]' check "a clean stop is still allowed" allow ""
