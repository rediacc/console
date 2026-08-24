#!/usr/bin/env bash
# Gate: the machine-setup path must stay idempotent, guarded, and honest.
#
# Four invariants, each paid for by a defect found while building this feature:
#
#   A. Every mutating step is GUARDED, so a second `./run.sh setup` is a no-op.
#   B. `./run.sh setup --check` reports and mutates nothing.
#   C. Port derivation is deterministic and per-worktree distinct, so a devbox
#      URL survives a reboot and two worktrees never collide.
#   D. A build helper never reports success from a file that already existed.
#      `ensure_renet_built` used to run `(cd renet && ./build.sh dev)` without
#      checking its exit code and then test only `[[ -f $renet_bin ]]`. A failed
#      rebuild left the PREVIOUS binary in place, so the function reported
#      success and wrote a content stamp for sources it had not built -- and the
#      stamp matched forever after, making the failure unrepeatable. Observed
#      live: asset staging aborted and the run still printed EXIT=0.
#
# Control-first: every assertion is re-run against a copy carrying the original
# defect, with a vacuity check that the mutation applied. A control that does not
# fire fails this gate rather than letting it report a green it did not earn.
#
# Hermetic: no docker, no network, no package installs.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LIB="$ROOT/.ci/lib"

RED=''
GREEN=''
NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    NC=$'\033[0m'
fi

fails=0
fail() {
    echo "${RED}FAIL${NC} $*" >&2
    fails=$((fails + 1))
}
pass() { echo "${GREEN}ok${NC}   $*"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------------------
# A. Mutating steps are guarded.
# ---------------------------------------------------------------------------
# Each entry: <function>|<mutating pattern>|<guard that must appear in it>
assert_guarded() { # assert_guarded <file> <function> <mutation-regex> <guard-regex>
    local file="$1" fn="$2" mutation="$3" guard="$4" body
    body="$(awk -v f="$fn" '$0 ~ "^"f"\\(\\) \\{" {inside=1} inside {print} inside && /^}/ {exit}' "$file")"
    if [ -z "$body" ]; then
        fail "A: no function $fn in $(basename "$file")"
        return 1
    fi
    if ! printf '%s' "$body" | grep -qE "$mutation"; then
        return 0 # nothing mutating here
    fi
    if ! printf '%s' "$body" | grep -qE "$guard"; then
        fail "A: $fn mutates ($mutation) with no guard matching /$guard/"
        return 1
    fi
    return 0
}

check_a() {
    local rc=0
    # Installing Go must be skipped when a good enough Go is present.
    assert_guarded "$LIB/local-common.sh" ensure_go_installed \
        'tar -C /usr/local|curl -fL' '_version_gte|command -v go' || rc=1
    # Installing Docker must be skipped when docker already works.
    assert_guarded "$LIB/local-common.sh" ensure_docker_installed \
        'install-docker|ensure_go_installed' 'docker version' || rc=1
    # Host tools must be skipped when already present.
    assert_guarded "$LIB/local-common.sh" ensure_host_tools \
        'apt-get install' 'command -v' || rc=1
    # Creating the container must be skipped when one already runs.
    assert_guarded "$LIB/devbox.sh" devbox_up \
        'docker run|\$d run' 'devbox_container_running|devbox_container_id' || rc=1
    # Pulling the image must be skipped when it is present.
    assert_guarded "$LIB/devbox.sh" devbox_ensure_image \
        'pull' 'devbox_image_present' || rc=1
    return $rc
}

# ---------------------------------------------------------------------------
# B. `setup --check` changes nothing.
# ---------------------------------------------------------------------------
check_b() {
    local out rc before after
    before="$(cd "$ROOT" && git status --porcelain 2>/dev/null | sort)"
    out="$(cd "$ROOT" && NO_COLOR=1 ./run.sh setup --check 2>&1)"
    rc=$?
    after="$(cd "$ROOT" && git status --porcelain 2>/dev/null | sort)"

    if [ "$before" != "$after" ]; then
        fail "B: setup --check changed the working tree"
        diff <(printf '%s' "$before") <(printf '%s' "$after") >&2 || true
        return 1
    fi
    # It must actually REPORT, not just exit quietly: a check that prints
    # nothing is indistinguishable from a check that did not run.
    local row
    for row in node docker image devbox 'port block'; do
        if ! printf '%s' "$out" | grep -qi "$row"; then
            fail "B: setup --check never mentioned '$row'"
            return 1
        fi
    done
    # rc is 0 (nothing to do) or 1 (work pending); anything else is a crash.
    if [ "$rc" -gt 1 ]; then
        fail "B: setup --check exited $rc"
        printf '%s\n' "$out" | sed 's/^/       /' >&2
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# C. Port derivation.
# ---------------------------------------------------------------------------
# shellcheck disable=SC2120  # called with an argument by the control below
check_c() { # check_c <find-port.sh path>
    local fp="${1:-$LIB/find-port.sh}"
    local a1 b1 i sample
    # shellcheck source=/dev/null
    a1="$(bash -c "source '$fp'; derive_slot /home/x/console 100")"
    b1="$(bash -c "source '$fp'; derive_slot /home/x/console/.worktrees/0824-1 100")"

    if [ -z "$a1" ]; then
        fail "C: derive_slot produced nothing"
        return 1
    fi

    # FIVE samples, not two. The control for this assertion plants $RANDOM, and
    # $RANDOM % 100 repeats itself about 1% of the time -- so a two-sample
    # comparison let the planted defect pass at that rate and the gate reported
    # "CONTROL DID NOT FIRE" at random. Five agreeing samples drops that to ~1e-8
    # while costing microseconds. A flaky control is worse than no control: it
    # teaches the reader to re-run until green.
    for ((i = 0; i < 4; i++)); do
        sample="$(bash -c "source '$fp'; derive_slot /home/x/console 100")"
        if [ "$sample" != "$a1" ]; then
            fail "C: derive_slot is not deterministic ($a1 then $sample)"
            return 1
        fi
    done
    if [ "$a1" = "$b1" ]; then
        fail "C: two different worktrees derived the same slot ($a1)"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# D. Build helpers check exit codes, not just file existence.
# ---------------------------------------------------------------------------
# shellcheck disable=SC2120  # called with an argument by the control below
check_d() { # check_d <local-common.sh path>
    local f="${1:-$LIB/local-common.sh}" body
    body="$(awk '/^ensure_renet_built\(\) \{/{inside=1} inside{print} inside&&/^}/{exit}' "$f")"
    if [ -z "$body" ]; then
        fail "D: ensure_renet_built not found in $(basename "$f")"
        return 1
    fi
    if ! printf '%s' "$body" | grep -qE 'if ! \(cd "\$renet_dir" && \./build\.sh dev\)|build\.sh dev\) \|\||\|\| \{[[:space:]]*$'; then
        fail "D: ensure_renet_built runs build.sh without checking its exit code"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# E. A status label must never contradict its HTTP code.
#
# `devbox status` probes each proxy route and prints a word next to the code.
# "OK (404)" shipped for one commit: Drizzle Studio answers 404 at / by design,
# so calling that success is tempting -- and it would then hide a genuine 404 on
# any other route behind the same label. Reachability is not success. Static
# shell checks cannot see this: "OK" and "404" are both valid text.
# ---------------------------------------------------------------------------
SUCCESS_WORDS='\b(ok|OK|healthy|success|succeeded|fine|good|ready)\b'

# shellcheck disable=SC2120  # called with an argument by the control below
check_e() { # check_e <devbox.sh path>
    local lib="${1:-$LIB/devbox.sh}" out code

    if ! bash -c "source '$lib' 2>/dev/null; declare -f devbox_route_label >/dev/null"; then
        fail "E: devbox_route_label is missing from $(basename "$lib"); the label logic must stay testable"
        return 1
    fi

    # Any 4xx/5xx must NOT be described with a success word.
    for code in 400 404 418 500 502 503; do
        out="$(bash -c "source '$lib' 2>/dev/null; devbox_route_label $code 'hint'" 2>/dev/null)"
        if [ -z "$out" ]; then
            fail "E: devbox_route_label produced nothing for $code"
            return 1
        fi
        if printf '%s' "$out" | grep -qE "$SUCCESS_WORDS"; then
            fail "E: HTTP $code is labelled with a success word: \"$out\""
            return 1
        fi
    done

    # A 502 must name the actual cause rather than a bare failure.
    out="$(bash -c "source '$lib' 2>/dev/null; devbox_route_label 502 'run account dev'" 2>/dev/null)"
    if ! printf '%s' "$out" | grep -qi "no backend"; then
        fail "E: a 502 must say no backend is listening, got: \"$out\""
        return 1
    fi

    # 2xx/3xx must still be reported as reachable.
    for code in 200 301; do
        out="$(bash -c "source '$lib' 2>/dev/null; devbox_route_label $code" 2>/dev/null)"
        if ! printf '%s' "$out" | grep -qi "live"; then
            fail "E: HTTP $code should be reported live, got: \"$out\""
            return 1
        fi
    done
    return 0
}

# ---------------------------------------------------------------------------
# F. A path-scoped redirect must also be method-scoped.
#
# Paid for on 2026-08-24: a router matching Host(...) && Path(`/`) redirected the
# devbox database route's root to a hosted UI. Drizzle Studio's API endpoint IS
# `POST /`, so that rule 307'd the API itself and the UI spun in a retry loop --
# invisible to every static check because the labels are just strings, and
# invisible to a GET-only probe because GET was the half that worked.
#
# The redirect has since been removed, so this assertion guards the CLASS, not
# the instance: if anyone adds a redirect on a Path rule again, it must carry a
# Method(...) so non-GET verbs keep reaching the backend.
# ---------------------------------------------------------------------------
# shellcheck disable=SC2120  # called with an argument by the control below
check_f() { # check_f <devbox.sh path>
    local lib="${1:-$LIB/devbox.sh}" router rule

    # Every router that carries a redirect middleware.
    while IFS= read -r router; do
        [ -n "$router" ] || continue
        rule="$(grep -F "routers.\${slug}-${router}.rule=" "$lib" 2>/dev/null | head -1)"
        if [ -z "$rule" ]; then
            fail "F: redirect middleware '${router}' has no matching router rule in $(basename "$lib")"
            return 1
        fi
        case "$rule" in
            *"Path("*)
                if ! printf '%s' "$rule" | grep -q 'Method('; then
                    fail "F: router '${router}' redirects a Path without scoping the Method; a non-GET request to that path (an API endpoint) would be redirected instead of served"
                    printf '       %s\n' "$rule" >&2
                    return 1
                fi
                ;;
        esac
    done < <(grep -oE 'middlewares\.\$\{slug\}-[a-z-]+\.redirectregex' "$lib" 2>/dev/null |
        sed -E 's/middlewares\.\$\{slug\}-//; s/\.redirectregex//' | sort -u)
    return 0
}

# ---------------------------------------------------------------------------
# G. setup() must initialise submodules BEFORE any phase that reads one.
#
# Paid for on 2026-08-24: setup() never initialised submodules at all, while
# CONTRIBUTING.md's quickstart is `git clone && ./run.sh setup` and its table
# claimed setup did it. The docker phase reads private/renet/go.mod to choose the
# Go version, so on a genuinely fresh clone setup died with "Cannot determine the
# required Go version" -- a message that names neither submodules nor the file.
#
# ORDER is the invariant, not mere presence: an init call placed after the phase
# that reads a submodule path fixes nothing, and reads as correct in a diff.
# ---------------------------------------------------------------------------
# shellcheck disable=SC2120  # called with an argument by the control below
check_g() { # check_g <run.sh path>
    local runsh="${1:-$ROOT/run.sh}" body init_line reader_line

    # COMMENTS STRIPPED, and that is load-bearing. The first version matched
    # "private/renet/go.mod" inside the comment that explains the ordering and
    # concluded the real, correctly-ordered code was broken. Same family as the
    # gate that matched "binary" against a PATH: judge the code, not the prose
    # describing it.
    body="$(awk '/^setup\(\) \{/{inside=1} inside{print} inside&&/^}/{exit}' "$runsh" |
        sed 's/[[:space:]]*#.*$//')"
    if [ -z "$body" ]; then
        fail "G: no setup() function in $(basename "$runsh")"
        return 1
    fi

    init_line="$(printf '%s\n' "$body" | grep -nE 'init-submodules\.sh|git submodule (update|init)' | head -1 | cut -d: -f1)"
    if [ -z "$init_line" ]; then
        fail "G: setup() never initialises submodules. A fresh clone then fails in the docker phase, which reads private/renet/go.mod, with a message that never mentions submodules."
        return 1
    fi

    # The first phase that depends on a submodule path being present.
    reader_line="$(printf '%s\n' "$body" | grep -nE 'ensure_docker_installed|private/renet|private/account' | head -1 | cut -d: -f1)"
    if [ -n "$reader_line" ] && [ "$init_line" -gt "$reader_line" ]; then
        fail "G: setup() initialises submodules AFTER the first phase that reads one (init at body line $init_line, reader at $reader_line). Order is the invariant; a late init reads as correct in a diff and fixes nothing."
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
control_fails=0
control() { # control <label> <fn> <arg> ; the fn MUST fail on the mutated input
    local label="$1" fn="$2" arg="$3" out
    out="$({
        "$fn" "$arg"
        echo "rc=$?"
    } 2>&1)"
    case "$out" in
        *"rc=0"*)
            echo "${RED}CONTROL DID NOT FIRE${NC}: $label -- the planted defect passed." >&2
            control_fails=1
            ;;
    esac
}

echo "check-setup-idempotency: guards, report-only check, port derivation, exit-code honesty"

check_a && pass "every mutating setup step is guarded"
check_b && pass "setup --check reports and mutates nothing"
check_c && pass "port derivation is deterministic and per-worktree distinct"
check_d && pass "ensure_renet_built checks the build's exit code"
check_e && pass "no status label contradicts its HTTP code"
check_f && pass "no path-scoped redirect leaves its method unscoped"
check_g && pass "setup initialises submodules before any phase that reads one"

# C-control: a random slot must be rejected.
sed 's/digest="$(printf .*$/digest=$RANDOM/' "$LIB/find-port.sh" >"$TMP/fp-broken.sh"
if ! grep -q 'digest=$RANDOM' "$TMP/fp-broken.sh"; then
    echo "${RED}CONTROL IS VACUOUS${NC}: C -- mutation did not apply." >&2
    control_fails=1
else
    control "C (deterministic ports)" check_c "$TMP/fp-broken.sh"
fi

# D-control: restore the unchecked invocation.
sed 's|if ! (cd "$renet_dir" && ./build.sh dev); then|(cd "$renet_dir" \&\& ./build.sh dev); if false; then|' \
    "$LIB/local-common.sh" >"$TMP/lc-broken.sh"
if ! grep -q 'if false; then' "$TMP/lc-broken.sh"; then
    echo "${RED}CONTROL IS VACUOUS${NC}: D -- mutation did not apply." >&2
    control_fails=1
else
    control "D (build exit code)" check_d "$TMP/lc-broken.sh"
fi

# E-control: restore the "OK (404)" wording.
sed 's|echo "live (HTTP $code)"|echo "OK ($code)"|' "$LIB/devbox.sh" >"$TMP/devbox-broken.sh"
if ! grep -q 'echo "OK ($code)"' "$TMP/devbox-broken.sh"; then
    echo "${RED}CONTROL IS VACUOUS${NC}: E -- mutation did not apply." >&2
    control_fails=1
else
    control "E (label vs code)" check_e "$TMP/devbox-broken.sh"
fi

# F-control: plant the exact defect -- a redirect router on Path(`/`) with no
# Method. The current tree has no redirect at all, so without this control the
# assertion would be vacuously green.
{
    cat "$LIB/devbox.sh"
    cat <<'PLANTED'
_planted_devbox_redirect() {
    docker run \
        --label "traefik.http.routers.${slug}-dbui.rule=Host(\`x\`) && Path(\`/\`)" \
        --label "traefik.http.middlewares.${slug}-dbui.redirectregex.regex=.*"
}
PLANTED
} >"$TMP/devbox-redirect.sh"
if ! grep -q 'dbui.redirectregex' "$TMP/devbox-redirect.sh"; then
    echo "${RED}CONTROL IS VACUOUS${NC}: F -- the planted redirect was not written." >&2
    control_fails=1
else
    control "F (path redirect without method)" check_f "$TMP/devbox-redirect.sh"
fi

# G-control: two plants, because presence and ORDER are different defects and a
# check that only notices absence would pass the one that actually shipped later.
sed '/init-submodules\.sh/d' "$ROOT/run.sh" >"$TMP/run-noinit.sh"
if grep -q 'init-submodules' "$TMP/run-noinit.sh"; then
    echo "${RED}CONTROL IS VACUOUS${NC}: G(absent) -- the init call was not removed." >&2
    control_fails=1
else
    control "G (submodule init absent)" check_g "$TMP/run-noinit.sh"
fi

# Move the init AFTER the docker phase: present, but useless.
awk '
    /init-submodules\.sh/ { next }
    { print }
    /if ! ensure_docker_installed; then/ { print "        bash \"$ROOT_DIR/.devcontainer/init-submodules.sh\" --quiet || true" }
' "$ROOT/run.sh" >"$TMP/run-lateinit.sh"
if ! grep -q 'init-submodules' "$TMP/run-lateinit.sh"; then
    echo "${RED}CONTROL IS VACUOUS${NC}: G(order) -- the moved init did not land." >&2
    control_fails=1
else
    control "G (submodule init after the reader)" check_g "$TMP/run-lateinit.sh"
fi

[ "$control_fails" -eq 0 ] && pass "controls fired: each assertion rejects the original defect"
[ "$control_fails" -ne 0 ] && exit 1

if [ "$fails" -ne 0 ]; then
    echo "" >&2
    echo "${RED}$fails assertion(s) failed.${NC} Rerun: npm run check:ci-setup-idempotency" >&2
    exit 1
fi
echo "${GREEN}Setup path invariants hold.${NC}"
