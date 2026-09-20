#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# An ADOPTED plan is an order: its untracked boxes block in the mission tier, while a plan the session merely owns stays an advisory.

echo "== 227. an ADOPTED plan with untracked boxes BLOCKS; an owned one does not =="
setup
say "answer

## Remaining
- nothing"
brief_now
hand_now
mkdir -p "$BASE/proj/agent"
_pad="Context paragraph that exists only so this fixture clears the minimum plan length and is read at all by the plan parser. "
cat >"$BASE/proj/agent/PLAN-adopted.md" <<MD
# PLAN: adopted work
Status: ready
Owner: deadbeef (adopted from cafe1234 2026-09-20)
Updated: 2026-09-20

$_pad$_pad$_pad

## Tasks

- [ ] Rewrite the alpha subsystem onto the shared helper in one commit
- [ ] Regenerate the beta baseline with the audited token
- [ ] Delete the gamma shim once nothing imports it
MD
check "227: an adopted plan's untracked boxes are ordered" block "WAS ADOPTED BY THIS SESSION"

echo "== 227b. CONTROL: the same plan merely OWNED is only an advisory, never a block =="
setup
say "answer

## Remaining
- nothing"
brief_now
hand_now
mkdir -p "$BASE/proj/agent"
cat >"$BASE/proj/agent/PLAN-owned.md" <<MD
# PLAN: owned work
Status: ready
Owner: deadbeef
Updated: 2026-09-20

$_pad$_pad$_pad

## Tasks

- [ ] Rewrite the alpha subsystem onto the shared helper in one commit
- [ ] Regenerate the beta baseline with the audited token
- [ ] Delete the gamma shim once nothing imports it
MD
check "227b: an owned, not adopted, plan does not block" allow ""
