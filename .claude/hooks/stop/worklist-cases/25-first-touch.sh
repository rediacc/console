# shellcheck shell=bash
# 25-first-touch.sh -- the onboarding notice, and above all when it stays QUIET.
#
# WHY. The Stop hook already tells a session what to do, but only once it tries to
# stop -- after the work. A fresh or post-compaction session learns the rules by
# hitting that wall: it finishes a job, writes `## Remaining` from memory, and gets
# refused. The operator's words were that such sessions "hit the wall and repeat the
# same mistakes like completing the job without updating the remainings by invoking
# stop hook's commands with specific arguments".
#
# WHAT IS ACTUALLY AT RISK is not the notice firing -- it is the notice firing too
# often. Measured on the transcript corpus: 38 of 41 sessions never edited a file and
# used 6-39 tool calls each. An unconditional first-tool-call notice would have fired
# on all 38 with nothing to say, and a notice that is noise 38 times out of 41 is one
# nobody reads on the other three. So most of the cases below assert SILENCE, and the
# emitting cases exist mainly to prove the silence is a choice rather than a
# permanently broken hook.

echo "== 25. first-touch onboarding notice =="

ONB="$(dirname "$HOOK")/../context/onboard.py"
if [[ ! -f "$ONB" ]]; then
    fail "25: onboard.py missing at $ONB"
    return 0 2>/dev/null || true
fi

FT="$BASE/firsttouch"
rm -rf "$FT"
mkdir -p "$FT"
FT_SID="ffffeeee-1111-2222-3333-444444444444"

ftrun() { # <event-json> <argv...> ; the EVENT IS STDIN
    local ev="$1"
    shift
    # NO </dev/null here, and that is not an oversight. A PostToolUse hook reads
    # its event FROM STDIN, so redirecting it to /dev/null hands the hook an
    # empty event: it then sees no tool_name, correctly concludes this is not an
    # Edit, and stays silent -- which looks exactly like arm (b) being broken.
    # That cost one debugging round here. The `</dev/null` hygiene that other
    # case helpers want applies to helpers that do not READ stdin; this one does.
    printf '%s' "$ev" | env CTX_BAND_STATE_DIR="$FT" \
        CLAUDE_CODE_SESSION_ID="$FT_SID" WORKLIST_SESSION_ID="$FT_SID" \
        CLAUDE_PROJECT_DIR="$BASE/proj" TMPDIR="$BASE/tmp" \
        python3 "$ONB" "$@" 2>&1
}
EV_BASH="{\"session_id\":\"$FT_SID\",\"tool_name\":\"Bash\"}"
EV_EDIT="{\"session_id\":\"$FT_SID\",\"tool_name\":\"Edit\"}"
EV_SUB="{\"session_id\":\"$FT_SID\",\"tool_name\":\"Bash\",\"parent_tool_use_id\":\"toolu_x\"}"

# ---- never armed: a hook that has not been armed says nothing ---------------
OUT=$(ftrun "$EV_BASH")
if [[ -z "$OUT" ]]; then
    pass "25: an unarmed session is silent"
else
    fail "25: spoke without ever being armed: ${OUT:0:120}"
fi

# ---- arm (b): owns nothing, so tool call #1 must be SILENT ------------------
# This is the case that would have nagged 38 of 41 real sessions.
ftrun "$EV_BASH" --arm >/dev/null
for i in 1 2 3 4 5; do
    OUT=$(ftrun "$EV_BASH")
    if [[ -n "$OUT" ]]; then
        fail "25 ARM-B: nagged on non-edit tool call #$i: ${OUT:0:120}"
        break
    fi
done
[[ -z "$OUT" ]] && pass "25 ARM-B: five non-edit tool calls with nothing owned emit nothing"

# ...and the state machine actually moved, rather than the hook being inert.
if grep -q '"await-edit"' "$FT/ffffeeee-onboard.json" 2>/dev/null; then
    pass "25 ARM-B: the marker advanced to await-edit (silence is a decision, not a no-op)"
else
    fail "25 ARM-B: marker never advanced: $(cat "$FT/ffffeeee-onboard.json" 2>/dev/null | tr -d '\n' | cut -c1-120)"
fi

# ---- arm (b) fires on the FIRST edit, once -------------------------------
OUT=$(ftrun "$EV_EDIT")
if grep -q "owns 0 worklist items" <<<"$OUT" && grep -q -- "--tick ffffeeee" <<<"$OUT"; then
    pass "25 ARM-B: the first edit gets the notice, with the prefix pre-substituted"
else
    fail "25 ARM-B: no notice on the first edit: ${OUT:0:160}"
fi
OUT=$(ftrun "$EV_EDIT")
if [[ -z "$OUT" ]]; then
    pass "25 ARM-B: it does not repeat in the same epoch"
else
    fail "25 ARM-B: repeated within one epoch: ${OUT:0:120}"
fi

# ---- a subagent is never told about the store ------------------------------
rm -rf "$FT"
mkdir -p "$FT"
ftrun "$EV_BASH" --arm >/dev/null
OUT=$(ftrun "$EV_SUB")
if [[ -z "$OUT" ]]; then
    pass "25: a subagent call is silent"
else
    fail "25: spoke to a subagent: ${OUT:0:120}"
fi

# ---- CANNOT-SAY IS NOT ZERO, and this one was a real bug -------------------
# `worklist.py --list --open <me>` exits 1 for an EMPTY slice, so keying on the
# exit code alone collapsed "owns nothing" into "cannot say" and arm (b) could
# never fire. The converse matters more: a store that REFUSES to answer (identity
# mismatch) must produce silence, never the confident "you own 0 items" notice.
rm -rf "$FT"
mkdir -p "$FT"
OTHER="aaaabbbb-9999-8888-7777-666666666666"
printf '%s' "$EV_EDIT" | env CTX_BAND_STATE_DIR="$FT" \
    CLAUDE_CODE_SESSION_ID="$OTHER" WORKLIST_SESSION_ID="$OTHER" \
    CLAUDE_PROJECT_DIR="$BASE/proj" TMPDIR="$BASE/tmp" \
    python3 "$ONB" --arm >/dev/null 2>&1
OUT=$(printf '%s' "$EV_EDIT" | env CTX_BAND_STATE_DIR="$FT" \
    CLAUDE_CODE_SESSION_ID="$OTHER" WORKLIST_SESSION_ID="$OTHER" \
    CLAUDE_PROJECT_DIR="$BASE/proj" TMPDIR="$BASE/tmp" \
    python3 "$ONB" 2>&1)
if [[ -z "$OUT" ]]; then
    pass "25 CANNOT-SAY: a store that refuses to answer produces silence, not 'you own nothing'"
else
    fail "25 CANNOT-SAY: asserted an empty slice the store never confirmed: ${OUT:0:140}"
fi

# ---- the off switch --------------------------------------------------------
rm -rf "$FT"
mkdir -p "$FT"
ftrun "$EV_BASH" --arm >/dev/null
OUT=$(printf '%s' "$EV_EDIT" | env CTX_BAND_STATE_DIR="$FT" ONBOARD_NOTICE=off \
    CLAUDE_CODE_SESSION_ID="$FT_SID" WORKLIST_SESSION_ID="$FT_SID" \
    CLAUDE_PROJECT_DIR="$BASE/proj" TMPDIR="$BASE/tmp" python3 "$ONB" 2>&1)
if [[ -z "$OUT" ]]; then
    pass "25: ONBOARD_NOTICE=off silences it"
else
    fail "25: the off switch did not silence it: ${OUT:0:120}"
fi

# ---- it must NEVER break a tool call ---------------------------------------
# A PostToolUse hook that exits non-zero, or writes garbage to stdout, breaks the
# call it is attached to. Both are asserted against a deliberately corrupt marker.
rm -rf "$FT"
mkdir -p "$FT"
printf 'not json at all' >"$FT/ffffeeee-onboard.json"
OUT=$(ftrun "$EV_EDIT")
RC=$?
if [[ "$RC" -eq 0 ]]; then
    pass "25 SAFETY: a corrupt marker still exits 0"
else
    fail "25 SAFETY: exited $RC on a corrupt marker; that breaks the tool call"
fi
if [[ -z "$OUT" ]] || python3 -c "import json,sys; json.loads(sys.stdin.read())" <<<"$OUT" 2>/dev/null; then
    pass "25 SAFETY: stdout is empty or valid JSON, never a stray line"
else
    fail "25 SAFETY: wrote non-JSON to stdout: ${OUT:0:120}"
fi
