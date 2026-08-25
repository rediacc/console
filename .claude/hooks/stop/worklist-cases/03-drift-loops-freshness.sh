#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Design-doc drift, loop-death and its opt-out, PR/branch freshness, item state words, and STATE.md staleness windows.

echo "== 31. design-doc DRIFT blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
mkdir -p "$BASE/proj/docs/ci-overhaul"
echo "# design" >"$BASE/proj/docs/ci-overhaul/README.md"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    mkdir -p .ci
    git add -A >/dev/null 2>&1
    git commit -qm docs 2>/dev/null
    for i in $(seq 1 12); do
        echo "$i" >".ci/f$i.sh"
        git add -A >/dev/null 2>&1
        git commit -qm "code $i" 2>/dev/null
    done
) >/dev/null 2>&1
check "12 code commits with untouched docs block" block "design docs have DRIFTED"

echo "== 32. no drift once the docs move with the code =="
(
    cd "$BASE/proj" || exit
    echo "# updated" >>docs/ci-overhaul/README.md
    git add -A >/dev/null 2>&1
    git commit -qm "docs refresh" 2>/dev/null
) >/dev/null 2>&1
check "docs updated after the code clears the drift" allow ""

echo "== 33. SessionStart hands the design docs to a new session =="
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" python3 "$HOOK" --session-start 2>/dev/null)"
if grep -qF "READ ALL OF THEM" <<<"$out" && grep -qF "docs/ci-overhaul/README.md" <<<"$out"; then
    echo "  PASS: SessionStart lists the docs and demands they be read"
    PASS=$((PASS + 1))
else
    echo "  FAIL: SessionStart did not surface the docs: ${out:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 34. a LOOP THAT DIED blocks (had crons, now none) =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
run >/dev/null
CRONS='[]'
check "losing the last cron blocks" block "WORK LOOP DIED"

echo "== 35. a session that NEVER had a cron is not nagged =="
setup
brief_now
hand_now
say "answer

## Remaining
- #7 thing (pending)"
task 7 pending "thing"
# No cron ever, but a running background agent, so the v8 idle check stays
# quiet and this case keeps pinning ONLY the loop-died non-fire.
CRONS='[]'
BG='[{"status":"running","description":"agent"}]'
check "no cron ever means no complaint" allow ""

echo "== 34b. DECLARING the loop finished clears it, and STAYS cleared =="
# V_LOOP_DIED offers two exits: recreate the cron, or say the loop is
# deliberately finished. The second one did not exist -- cron_memory never read
# the message -- so a session that retired its cron on purpose and said so was
# blocked on every stop after, with no wording that could satisfy it. The final
# assert is the one that matters: the declaration must FORGET the high-water
# mark, not skip a single stop, or the block returns next stop forever.
setup
brief_now
hand_now
task 7 pending "thing"
# A live background agent, exactly as case 35 does. Without it the repeated
# stops in this case trip the idle check and the 3-identical-stops check, and
# the assertion then fails on THEIR reasons while V_LOOP_DIED is already clear
# -- a confound that made this very case red on its first run.
BG='[{"status":"running","description":"agent"}]'
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null
CRONS='[]'
# CONTROL first: the SAME world without the declaration must still block, or
# the case proves nothing about the declaration.
check "CONTROL: no declaration, the dead loop still blocks" block "WORK LOOP DIED"
say 'The campaign is done, so the loop is deliberately finished and I retired the cron.

## Remaining
- #7 thing (pending)'
check "declaring the loop deliberately finished clears it" allow ""
check "and it STAYS cleared on the next stop" allow ""

echo "== 34c. CONTROL: merely QUOTING the instruction does NOT opt out =="
# This is an opt-out, so it must survive being written about: every message
# that discusses this check quotes its own instruction text back. Stripping
# quoted and backticked spans before matching is what keeps that honest.
setup
brief_now
hand_now
task 7 pending "thing"
BG='[{"status":"running","description":"agent"}]'
CRONS='[{"id":"bbb","schedule":"17 * * * *"},{"id":"p","schedule":"*/5 * * * *"}]'
say "answer

## Remaining
- #7 thing (pending)"
run >/dev/null
CRONS='[]'
say 'The hook says to recreate it or "say out loud in your message that the loop is deliberately finished", and `the loop is deliberately finished` is the phrase it wants.

## Remaining
- #7 thing (pending)'
check "a quoted/backticked mention does NOT switch the check off" block "WORK LOOP DIED"

echo "== 36. a STALE LOCAL branch sharing the publish name blocks =="
setup
brief_now
hand_now
task 7 pending "thing"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    echo a >a.txt
    git add -A
    git commit -qm base
    git branch -f pub HEAD
    echo b >b.txt
    git add -A
    git commit -qm newer
    git update-ref refs/remotes/origin/pub "$(git rev-parse HEAD)"
) >/dev/null 2>&1
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "is a trap for whoever checks it out" <<<"$out"; then
    echo "  PASS: a stale local branch sharing the publish name blocks"
    PASS=$((PASS + 1))
else
    echo "  FAIL: stale local branch not detected: ${out:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 37. PR-freshness: a push after the last body edit blocks =="
setup
brief_now
hand_now
task 7 pending "thing"
(
    cd "$BASE/proj" || exit
    git init -q 2>/dev/null
    git config user.email t@t
    git config user.name t
    git remote add origin https://github.com/fake/repo.git 2>/dev/null
    echo a >a.txt
    git add -A
    git commit -qm base
    git update-ref refs/remotes/origin/pub "$(git rev-parse HEAD)"
) >/dev/null 2>&1
# A gh shim that answers the GraphQL read with a body edited in 1970, i.e. long
# before any commit. The gate under test is the real one.
cat >"$BASE/binonly/gh" <<'SHIM'
#!/bin/bash
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":9,"lastEditedAt":"1970-01-01T00:00:00Z","updatedAt":"1970-01-01T00:00:00Z"}]}}}}'
SHIM
chmod +x "$BASE/binonly/gh"
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
        WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off \
        GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" <<<"$out"; then
    echo "  PASS: pushing after the body edit blocks before CI can waste a round"
    PASS=$((PASS + 1))
else
    echo "  FAIL: stale PR body not detected: ${out:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 38. PR-freshness: a body edited AFTER the tip passes =="
cat >"$BASE/binonly/gh" <<'SHIM'
#!/bin/bash
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":9,"lastEditedAt":"2999-01-01T00:00:00Z","updatedAt":"2999-01-01T00:00:00Z"}]}}}}'
SHIM
chmod +x "$BASE/binonly/gh"
out="$(printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"x\\n\\n## Remaining\\n- #7 thing (pending)","session_crons":[]}' "$SID" "$BASE/proj" |
    PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
        WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_PUBLISH_REF=pub WORKLIST_JUDGE=off \
        GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>/dev/null)"
if grep -qF "PUSHED AFTER" <<<"$out"; then
    echo "  FAIL: a fresh body must not block: ${out:0:200}"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: a body newer than the tip does not block"
    PASS=$((PASS + 1))
fi
rm -f "$BASE/binonly/gh"

echo "== 39. an item listed with NO state word blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | me |"
task 7 pending "thing"
check "a stateless remaining item blocks" block "listed without a STATE"

echo "== 40. saying 'ongoing' while the app says pending blocks =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | ongoing, me |"
task 7 pending "thing"
check "message and task list must agree" block "DISAGREES with the task list"

echo "== 41. 'ongoing' matches an in_progress task =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | ongoing, me |"
task 7 in_progress "thing"
check "an in_progress task labelled ongoing is fine" allow ""

echo "== 41b. literal 'in_progress' (underscore) is recognized as the state word, even with a later 'pending' in the same line =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | **in_progress** | demo done; another observation still pending -- blocked on X |"
task 7 in_progress "thing"
check "in_progress spelled with an underscore is not skipped in favour of a later 'pending'" allow ""

echo "== 42. a 'found, not fixed' list blocks: fix it or track it =="
setup
brief_now
hand_now
say "answer

Found, not fixed: CLAUDE.md points at a dead endpoint.

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "reporting instead of fixing blocks" block "CLAUDE.md's rule is to FIX"

echo "== 43b. MENTIONING the phrase mid-sentence must NOT block =="
setup
brief_now
hand_now
say "answer

The hook now blocks on a found, not fixed list, and I described that as
\"Found, not fixed\" is now a blocking phrase.

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "describing the check does not trip it" allow ""

echo "== 43. the same message without that phrase passes =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "no found-not-fixed list, no complaint" allow ""

echo "== 44. a STATE.md just over the limit is STALE (the limit is load-bearing) =="
# NOTE: 44 and 45 are ONE indivisible fixture; 45 has no setup of its own and
# re-stamps the section 44 planted. Do not reorder or insert a setup between
# them.
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
# Age it past the default without touching the clock. AGE COMES FROM THE
# SECTION'S HEADING STAMP since 2026-08-09, not from the file's mtime, so this
# re-stamps the section rather than touching the file: mtime is per FILE while
# the obligation is per SESSION, and a peer's write used to reset everyone's
# clock. `touch -d` here would silently exercise the unstamped fallback instead
# of the rule under test.
# The limit is 15 minutes, and the pair BRACKETS it: 16 must block, 14 must
# not. A single far-past fixture would keep passing if the constant were
# raised to an hour by accident. The world has moved since hand_now banked the
# signature (task 7 landed after), so world-keyed staleness is armed.
age_state deadbeef 16
check "a 16-minute-old STATE.md blocks at the 15-minute limit" block "STATE.md is stale"

echo "== 45. and one just inside it does not =="
age_state deadbeef 14
check "a 14-minute-old STATE.md is inside the 15-minute limit" allow ""

echo "== 44b. staleness is PER SESSION: one session's write cannot silence another =="
# THE OTHER HALF OF THE 2026-08-09 INCIDENT, and the half that made the first
# half inevitable. Age used to come from the file's MTIME, which is per FILE,
# while the recorded signature is per SESSION. So a peer's write reset
# everyone's clock: session B's 30-minute-stale document read "ok" the instant
# session A wrote, and -- worse than a skipped stop -- wl_checks then banked
# A's world signature as B's own, so B adopted a document describing A's world
# as its own recovery artifact. Reproduced against the real function before the
# fix: ('stale', 30) became ('ok', 0) purely because A wrote.
#
# A mutation that reverts the age source to p.stat().st_mtime must turn this
# case red.
setup
brief_now
brief_other cafe1234
hand_now # A = deadbeef, stamped now
B_BODY='Session B is holding the canary campaign: attempt 6 is in flight behind watch id 9be21c, five flags are flipped, and v1.2.24 is released. None of this is session A material and none of it may be silenced by session A writing.

## Next action
Read attempt 6 to completion and record the flag states before touching anything.'
state_as cafe1234 "$B_BODY"
age_state cafe1234 30 # B is stale; A is not. A's write above is the "peer write".
# B needs work of its OWN outstanding, because the STATE.md violation only
# fires when something remains for that session: the tasks in the fixture dir
# are keyed to `deadbeef`, so without this B has an empty plate and the case
# would pass vacuously by never reaching the check under test.
as_peer cafe1234 reqcli --add cafe1234 "B's own open item" >/dev/null
task 7 pending "thing"
newturn
say "answer

## Remaining
- #7 thing (pending)"
B_SIG_BEFORE="$(python3 -c "
import json, pathlib
p = pathlib.Path('${WL%.md}.state-cafe1234.json')
print(json.loads(p.read_text()).get('state_sig', '') if p.exists() else '')")"
# FOCUS=off for B's two stops. B legitimately has TWO violations (its open item
# and its stale section) and the focus mechanism surfaces one, so a focused run
# would assert the needle's absence for a reason that has nothing to do with
# the rule under test -- and the anti-vacuity control below would then pass on
# a hook that never computed staleness at all.
export WORKLIST_FOCUS=off
check_as cafe1234 "44b FIRE: the STALE session B is nagged" block "STATE.md is stale"
unset WORKLIST_FOCUS
check "44b: session A, fresh, is NOT nagged by B's staleness" allow ""
# THE BANKING HALF, which is worse than the skipped stop it hid behind. On a
# "stale" verdict nothing may be banked, or the next stop would compare against
# a signature recorded DURING the block and clear itself. Under the mtime bug B
# got an "ok" verdict off A's write and banked A's world as its own.
B_SIG_AFTER="$(python3 -c "
import json, pathlib
p = pathlib.Path('${WL%.md}.state-cafe1234.json')
print(json.loads(p.read_text()).get('state_sig', '') if p.exists() else '')")"
if [[ -n "$B_SIG_BEFORE" && "$B_SIG_BEFORE" == "$B_SIG_AFTER" ]]; then
    pass "44b: B's banked signature is untouched by its stale block and by A's stop"
else
    fail "44b: B's signature moved during the block ('${B_SIG_BEFORE:0:12}' -> '${B_SIG_AFTER:0:12}')"
fi
# ANTI-VACUITY. Re-stamp B fresh: the nag must go away. Without this the case
# would pass on a hook that simply blocks every peer for every reason.
age_state cafe1234 1
export WORKLIST_FOCUS=off
OUT="$(run_as cafe1234)"
unset WORKLIST_FOCUS
# The second half of the anti-vacuity: B must still be SPEAKING (it still owns
# an open item), so the missing needle is the staleness verdict changing rather
# than the hook having gone quiet.
if ! grep -qF "STATE.md is stale" <<<"$OUT" && grep -qF "OPEN worklist item" <<<"$OUT"; then
    pass "44b ANTI-VACUITY: a freshly stamped section B is no longer nagged"
else
    fail "44b ANTI-VACUITY: B is nagged even when fresh, or went silent: ${OUT:0:220}"
fi

echo "== 44c. a FUTURE heading stamp cannot buy permanent freshness =="
# FOUND ON THE LIVE DOCUMENT, not imagined: driving this code against the real
# main-branch STATE.md for the first time showed a peer's hand-written heading
# stamped 101 minutes AHEAD -- almost certainly local time written with a Z. A
# trusted future stamp makes that section permanently fresh, which is worse
# than the unstamped fallback it would otherwise have taken, because the entire
# point of per-section staleness is that a section cannot dodge its own clock.
# A future stamp is therefore treated exactly like an unparseable one.
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
age_state deadbeef -60                                         # stamped an hour AHEAD
touch -d '40 minutes ago' "$BASE/proj/agent/deadbeef/STATE.md" # the honest age
check "44c FIRE: a future-stamped section falls back to mtime and goes stale" block "STATE.md is stale"
# CONTROL 1: a stamp inside the tolerated skew is still TRUSTED, so this is a
# rule about wrong clocks rather than a blanket distrust of the future.
age_state deadbeef -2
check "44c CONTROL: a stamp 2 minutes ahead is inside the skew and stays fresh" allow ""
# CONTROL 2: and the fallback is really the mtime, not a hardcoded stale. Same
# future stamp, fresh file: allowed.
age_state deadbeef -60
touch -d '1 minute ago' "$BASE/proj/agent/deadbeef/STATE.md"
task 8 pending "moved"
newturn
say "answer

## Remaining
| #7 | thing | pending, me |
| #8 | moved | pending, me |"
check "44c CONTROL: the untrusted stamp falls back to mtime, which here is fresh" allow ""
