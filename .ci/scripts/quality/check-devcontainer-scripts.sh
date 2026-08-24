#!/usr/bin/env bash
# Gate: the .devcontainer bootstrap scripts must REPORT failures, not swallow them.
#
# Why this exists. `.devcontainer/init-submodules.sh` used to run
#     git submodule update --init --recursive "$sub" 2>/dev/null
# and print "✗ $sub (no access, skipping)" for every non-zero exit, then
# `exit 0` regardless. A session lost real time to that: the token was valid and
# the failure was a stale credential helper, but the script reported the same
# sentence it prints for a permission denial, a DNS outage and a force-pushed
# submodule pointer, and the actual git error was discarded. The fix was by
# hand, and nothing stopped it coming back -- no existing gate reads shell
# stderr semantics.
#
# Three assertions, each with its own CONTROL. A control-first gate proves it
# can fail before it is allowed to pass: every assertion below is re-run against
# a deliberately broken copy of the script, and if the broken copy passes, this
# gate fails itself rather than reporting green.
#
#   A. No primary operation discards its stderr.
#   B. init-submodules.sh surfaces the real git error and exits non-zero.
#   C. start-vscode.sh --background/--stop signal the process GROUP.
#
# Assertion C guards a bug this gate's own session shipped and then caught by
# running it: `bin/openvscode-server` is a wrapper whose node CHILD holds the
# port, so signalling the launched pid printed "stopped" while the listener
# survived, and the next start died with "port already in use".
#
# Hermetic: no network, no docker, no submodule access. Runs in ~2 seconds.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DC="$ROOT/.devcontainer"
INIT="$DC/init-submodules.sh"
VSCODE="$DC/start-vscode.sh"

RED=''; GREEN=''; NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; NC=$'\033[0m'; fi

fail_count=0
fail() { echo "${RED}FAIL${NC} $*" >&2; fail_count=$((fail_count + 1)); }
pass() { echo "${GREEN}ok${NC}   $*"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------------------
# A. stderr suppression on a PRIMARY operation.
#
# Not a blanket ban on 2>/dev/null: probing for a pid, a command or a config
# value legitimately discards noise, and a gate that forbids those gets
# suppressed itself within a week. What must never be silenced is the command
# whose failure the script then reports on.
# ---------------------------------------------------------------------------
# Deliberately narrow: the command whose failure the script REPORTS ON. A probe
# (`command -v x 2>/dev/null`, `kill -0`, `ps`) is not a primary operation, and a
# gate that forbids those gets suppressed within a week.
PRIMARY_OPS='git (clone|fetch|pull|submodule update|submodule add)|curl [^|]*(-o |-O |--output)|^[[:space:]]*tar |npm (ci|install)'
SUPPRESSORS='2>/dev/null|2> */dev/null|2>&-|>[[:space:]]*/dev/null[[:space:]]+2>&1|&>[[:space:]]*/dev/null'

scan_suppression() { # scan_suppression <file> -> prints offending lines
  grep -nE "$PRIMARY_OPS" "$1" 2>/dev/null \
    | grep -vE '^[0-9]+:[[:space:]]*#' \
    | grep -E "$SUPPRESSORS" || true
}

assert_a() {
  local rc=0 f offenders
  for f in "$DC"/*.sh; do
    offenders="$(scan_suppression "$f")"
    if [ -n "$offenders" ]; then
      fail "A: $(basename "$f") discards stderr of a primary operation:"
      printf '       %s\n' "$offenders" >&2
      rc=1
    fi
  done
  return $rc
}

# ---------------------------------------------------------------------------
# B. Real failure -> real error text + non-zero exit.
#
# Uses a scratch superproject whose submodule URL is an unreachable local path,
# so the assertion needs neither the network nor credentials.
# ---------------------------------------------------------------------------
build_scratch_super() { # build_scratch_super <dir>
  local d="$1"
  mkdir -p "$d"
  git -C "$d" init -q .
  git -C "$d" config user.email gate@example.invalid
  git -C "$d" config user.name gate
  printf '[submodule "vendor/absent"]\n\tpath = vendor/absent\n\turl = file://%s/definitely-not-a-repo.git\n' "$d" \
    > "$d/.gitmodules"
  git -C "$d" update-index --add \
    --cacheinfo 160000,0000000000000000000000000000000000000001,vendor/absent
  git -C "$d" add .gitmodules
  git -C "$d" commit -qm scratch
}

run_init_against_scratch() { # run_init_against_scratch <script> -> "<exit>\n<output>"
  local script="$1" d out rc
  d="$TMP/super.$RANDOM"
  build_scratch_super "$d" >/dev/null 2>&1
  out="$(cd "$d" && NO_COLOR=1 GIT_TERMINAL_PROMPT=0 \
          env -u GITHUB_TOKEN -u GH_TOKEN -u PAT \
          bash "$script" vendor/absent 2>&1)"
  rc=$?
  printf '%s\n%s' "$rc" "$out"
}

assert_b() { # assert_b <script-under-test>
  local script="$1" res rc out
  res="$(run_init_against_scratch "$script")"
  rc="${res%%$'\n'*}"
  out="${res#*$'\n'}"

  if [ "$rc" = 0 ]; then
    fail "B: $(basename "$script") exited 0 on an unreachable submodule; a failed init must be visible to the caller"
    return 1
  fi
  # The load-bearing part: git's own words, not a paraphrase of them.
  if ! printf '%s' "$out" | grep -qiE "does not (appear to be|exist)|repository .* not found|fatal:"; then
    fail "B: $(basename "$script") never printed git's actual error. Output was:"
    printf '%s\n' "$out" | sed 's/^/       /' >&2
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# C. Process-group lifecycle in start-vscode.sh.
# ---------------------------------------------------------------------------
assert_c() { # assert_c <script>
  local script="$1" rc=0
  if ! grep -qE '^[[:space:]]*setsid ' "$script"; then
    fail "C: $(basename "$script") starts the background server without setsid; --stop cannot then reach the node child that owns the port"
    rc=1
  fi
  if ! grep -qE 'kill -(TERM|9) -- "?-\$' "$script"; then
    fail "C: $(basename "$script") never signals a process group on stop; killing the wrapper pid leaves the listener alive"
    rc=1
  fi
  return $rc
}

# ---------------------------------------------------------------------------
# Controls: each assertion must FAIL on a script mutated to reintroduce the bug.
# ---------------------------------------------------------------------------
mutate() { # mutate <src> <dst> <sed-expr...>
  local src="$1" dst="$2"; shift 2
  cp "$src" "$dst"
  local e
  for e in "$@"; do sed -i "$e" "$dst"; done
}

control_must_fail() { # control_must_fail <label> <fn> <arg>
  local label="$1" fn="$2" arg="$3" out
  out="$( { "$fn" "$arg"; echo "rc=$?"; } 2>&1 )"
  case "$out" in
    *"rc=0"*)
      echo "${RED}CONTROL DID NOT FIRE${NC}: $label" >&2
      echo "  The planted defect passed. This gate cannot detect the regression it claims to guard," >&2
      echo "  so it is failing itself rather than reporting a green it did not earn." >&2
      return 1 ;;
    *) return 0 ;;
  esac
}

echo "check-devcontainer-scripts: stderr visibility and lifecycle invariants"

[ -f "$INIT" ]   || { fail "missing $INIT"; }
[ -f "$VSCODE" ] || { fail "missing $VSCODE"; }
[ "$fail_count" -eq 0 ] || exit 1

for f in "$DC"/*.sh; do
  bash -n "$f" || fail "syntax error in $(basename "$f")"
done
[ "$fail_count" -eq 0 ] && pass "every .devcontainer/*.sh parses"

assert_a && pass "no primary operation discards its stderr"
assert_b "$INIT" && pass "init-submodules.sh surfaces git's real error and exits non-zero"
assert_c "$VSCODE" && pass "start-vscode.sh uses a process group for start/stop"

# --- controls --------------------------------------------------------------
control_fails=0

# A-control: reintroduce the exact suppression the old script had.
# The planted marker is checked for explicitly, so a refactor that moves the
# target line makes this control VACUOUS (and fails the gate) rather than
# silently mutating nothing and calling it a pass.
mutate "$INIT" "$TMP/a-broken.sh" \
  's@^\(  *\){ GIT_TERMINAL_PROMPT=0 git .*$@\1git submodule update --init --recursive "$sub" 2>/dev/null ### PLANTED@'
if ! grep -q '# PLANTED' "$TMP/a-broken.sh"; then
  echo "${RED}CONTROL IS VACUOUS${NC}: A — the mutation did not apply, so nothing was planted." >&2
  echo "  The line it targets in init-submodules.sh has changed; update this control." >&2
  control_fails=1
elif [ -z "$(scan_suppression "$TMP/a-broken.sh")" ]; then
  echo "${RED}CONTROL DID NOT FIRE${NC}: A (stderr suppression)" >&2
  echo "  A copy of init-submodules.sh with 2>/dev/null on the submodule update was NOT flagged." >&2
  control_fails=1
fi

# B-control: the old behavior -- swallow the git error and always exit 0.
mutate "$INIT" "$TMP/b-broken.sh" \
  's#^  err="$(attempt false "$sub")"#  err="(no access, skipping)"; attempt false "$sub" >/dev/null 2>\&1#' \
  's#^  exit 1$#  exit 0#'
if ! grep -q 'no access, skipping' "$TMP/b-broken.sh"; then
  echo "${RED}CONTROL IS VACUOUS${NC}: B — the mutation did not apply, so nothing was planted." >&2
  control_fails=1
else
  control_must_fail "B (real git error must surface)" assert_b "$TMP/b-broken.sh" || control_fails=1
fi

# C-control: a copy of start-vscode.sh with the process-group handling removed.
mutate "$VSCODE" "$TMP/c-broken.sh" \
  's#^\([[:space:]]*\)setsid nohup #\1nohup #' \
  's#kill -TERM -- "-$pgid"#kill -TERM "$pid"#' \
  's#kill -9 -- "-$pgid"#kill -9 "$pid"#'
if grep -qE '^[[:space:]]*setsid ' "$TMP/c-broken.sh" || grep -qE 'kill -(TERM|9) -- "?-\$' "$TMP/c-broken.sh"; then
  echo "${RED}CONTROL IS VACUOUS${NC}: C — the mutation did not apply, so nothing was planted." >&2
  control_fails=1
else
  control_must_fail "C (process-group lifecycle)" assert_c "$TMP/c-broken.sh" || control_fails=1
fi

if [ "$control_fails" -ne 0 ]; then
  exit 1
fi
pass "controls fired: each assertion rejects a copy carrying the original defect"

if [ "$fail_count" -ne 0 ]; then
  echo "" >&2
  echo "${RED}$fail_count assertion(s) failed.${NC} Rerun: npm run check:ci-devcontainer-scripts" >&2
  exit 1
fi
echo "${GREEN}All devcontainer script invariants hold.${NC}"
