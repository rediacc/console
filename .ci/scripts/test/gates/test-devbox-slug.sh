#!/usr/bin/env bash
# Controls for the devbox HOSTNAME: the branch-derived slug, its drift against a
# running container, and the route label that reports it.
#
# WHY THIS EXISTS. The slug is not decoration. It is the Host header, it names
# the traefik ROUTERS (`traefik.http.routers.${slug}-code`), and it is baked into
# the container at `docker run` while the rest of the world recomputes it live.
# Every failure in this area presents as a CONFIDENT WRONG ANSWER rather than an
# error: a drifted hostname makes traefik answer 404 for an unmatched Host, and
# the pre-change catch-all printed that as "live (HTTP 404)" -- three live rows
# whose URLs all 404 in a browser. A detached HEAD under `rev-parse --abbrev-ref`
# yields the literal string HEAD, which sanitises to the perfectly VALID hostname
# `head.localhost`, so every detached worktree on the machine converges on one
# name and one router. Neither is visible to a smoke test; both are visible here.
#
# HOW. Function bodies are sed-lifted out of .ci/lib/devbox.sh (the pattern
# test-devbox-probes.sh established) so this cannot drift from the real code, and
# every control is built BY CONSTRUCTION -- a variant function written into a
# temp file and sourced -- never by substituting a live source line, which is the
# vacuity shape check-control-vacuity.sh:44-77 exists to stop.
#
# BLIND SPOTS, stated so a green here is not read as more than it is:
#   1. It never starts a container, a proxy or traefik. That the LABELS this
#      library writes produce the routers traefik actually builds is assumed, not
#      proven; only the string that goes into them is checked.
#   2. `feat/x` and `feat-x` still collapse to ONE hostname. That collision is
#      asserted below as DELIBERATE, not fixed -- two branches whose names differ
#      only by a separator share a URL, and only the collision refusal in
#      devbox_up stands between that and two silently duplicated routers.
#   3. It exercises the pure functions. devbox_up's rehost path and
#      devbox_status's probe loop are read by grep-control here, not executed.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LIB="$ROOT/.ci/lib/devbox.sh"
# shellcheck source=../lib/test-helpers.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/test-helpers.sh"

fails=0
count=0
ok() {
    count=$((count + 1))
    log_pass "$1"
}
no() {
    count=$((count + 1))
    fails=$((fails + 1))
    log_error "$1"
}

[[ -f "$LIB" ]] || log_fail "subject under test is missing: $LIB"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Lift the PURE functions. No git, no docker, no filesystem in any of them, so
# they are hermetic by construction.
eval "$(sed -n '/^devbox_slugify() {/,/^}/p' "$LIB")"
eval "$(sed -n '/^devbox_slug_drift() {/,/^}/p' "$LIB")"
eval "$(sed -n '/^devbox_route_label() {/,/^}/p' "$LIB")"
eval "$(sed -n '/^devbox_state_get() {/,/^}/p' "$LIB")"
for fn in devbox_slugify devbox_slug_drift devbox_route_label devbox_state_get; do
    declare -F "$fn" >/dev/null || log_fail "LIFT FAILED: $fn was not extracted from $LIB -- every assertion below would be vacuous"
done

# =============================================================================
# 1. devbox_slugify -- the pure rule
# =============================================================================
# input <TAB> expected. A 90-char name is included because the truncation to 40
# can land ON a dash, and a trailing dash is not a legal DNS label.
HOSTNAME_RE='^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'
LONG='feature/an-extremely-long-branch-name-that-nobody-would-ever-type-but-git-happily-accepts-x'
slug_rows() {
    printf '%s\t%s\n' 'feat/x' 'feat-x'
    printf '%s\t%s\n' 'feat//x' 'feat-x'
    printf '%s\t%s\n' 'Feature/ABC-123' 'feature-abc-123'
    printf '%s\t%s\n' '--lead-and-trail--' 'lead-and-trail'
    printf '%s\t%s\n' '0826-2' '0826-2'
    printf '%s\t%s\n' 'feat/über' 'feat-ber'
    printf '%s\t%s\n' '' ''
    printf '%s\t%s\n' '///' ''
    printf '%s\t%s\n' "$LONG" 'feature-an-extremely-long-branch-name-th'
}

log_test "devbox_slugify: the branch-name-to-hostname rule"
while IFS=$'\t' read -r in want; do
    got="$(devbox_slugify "$in")"
    if [[ "$got" == "$want" ]]; then
        ok "slugify: '$in' -> '$got'"
    else
        no "slugify: '$in' gave '$got', expected '$want'"
    fi
    if [[ -n "$got" ]] && ! [[ "$got" =~ $HOSTNAME_RE ]]; then
        no "slugify: '$got' is not a legal DNS label (from '$in')"
    fi
    if ((${#got} > 40)); then
        no "slugify: '$in' produced ${#got} chars; the cap is 40"
    fi
done < <(slug_rows)

# CONTROL, by construction: the pre-change rule did not COLLAPSE runs of dashes.
# Write that rule as its own function and require the feat//x row to go RED.
cat >"$TMP/nocollapse.sh" <<'PLANT'
devbox_slugify_planted() {
    local s
    s="$(LC_ALL=C printf '%s' "${1:-}" |
        LC_ALL=C tr '[:upper:]' '[:lower:]' |
        LC_ALL=C sed 's/[^a-z0-9-]/-/g; s/^-*//; s/-*$//')"
    LC_ALL=C printf '%s\n' "${s:0:40}" | LC_ALL=C sed 's/^-*//; s/-*$//'
}
PLANT
# shellcheck source=/dev/null
source "$TMP/nocollapse.sh"
declare -F devbox_slugify_planted >/dev/null || log_fail "CONTROL COULD NOT PLANT: the un-collapsed variant did not load"
planted="$(devbox_slugify_planted 'feat//x')"
if [[ "$planted" == 'feat-x' ]]; then
    no "CONTROL DID NOT FIRE: the un-collapsed rule also produced 'feat-x', so the collapse row proves nothing"
else
    ok "CONTROL: without the collapse rule 'feat//x' gives '$planted' -- the row would go red"
fi

# =============================================================================
# 2. The deliberate collision
# =============================================================================
# feat/x and feat-x are DIFFERENT branches that share ONE hostname. Assert the
# inputs differ FIRST: if a refactor ever made them equal, comparing the outputs
# alone would pass while proving nothing.
log_test "devbox_slugify: the separator collision is deliberate, not accidental"
a='feat/x'
b='feat-x'
if [[ "$a" == "$b" ]]; then
    no "the two collision inputs are identical; this assertion is vacuous"
elif [[ "$(devbox_slugify "$a")" == "$(devbox_slugify "$b")" ]]; then
    ok "collision: distinct branches '$a' and '$b' share hostname '$(devbox_slugify "$a")' (known; devbox_up must refuse the duplicate)"
else
    no "collision: '$a' and '$b' no longer collide -- deliberate? then update this test and the refusal path in devbox_up"
fi

# =============================================================================
# 3. devbox_branch on a DETACHED HEAD
# =============================================================================
# The whole point of symbolic-ref. Build a real repo, detach it, and require the
# slug to fall back to the worktree basename rather than to `head`.
log_test "devbox_branch: a detached HEAD yields no branch, so no shared 'head' hostname"
REPO="$TMP/0826-2"
mkdir -p "$REPO"
(
    cd "$REPO" || exit 1
    git init -q -b main .
    git -c user.email=t@t -c user.name=t commit -q --allow-empty -m x
) >/dev/null 2>&1

devbox_worktree() { printf '%s\n' "$REPO"; }
eval "$(sed -n '/^devbox_branch() {/,/^}/p' "$LIB")"
eval "$(sed -n '/^devbox_slug_basename() {/,/^}/p' "$LIB")"
eval "$(sed -n '/^devbox_slug() {/,/^}/p' "$LIB")"
unset DEVBOX_SLUG
for fn in devbox_branch devbox_slug devbox_slug_basename; do
    declare -F "$fn" >/dev/null || log_fail "LIFT FAILED: $fn was not extracted from $LIB"
done

if [[ "$(devbox_branch)" == "main" ]]; then
    ok "branch: an attached HEAD reports 'main'"
else
    no "branch: an attached HEAD reported '$(devbox_branch)', expected 'main'"
fi
if [[ "$(devbox_slug)" == "main" ]]; then
    ok "slug: on a branch, the hostname is the branch"
else
    no "slug: on a branch, expected 'main', got '$(devbox_slug)'"
fi

git -C "$REPO" checkout -q --detach HEAD >/dev/null 2>&1
if [[ -z "$(devbox_branch)" ]]; then
    ok "branch: a detached HEAD reports EMPTY, not the literal 'HEAD'"
else
    no "branch: a detached HEAD reported '$(devbox_branch)' -- every detached worktree would share that hostname"
fi
if [[ "$(devbox_slug)" == "0826-2" ]]; then
    ok "slug: detached falls back to the worktree basename ('0826-2'), which is unique per checkout"
else
    no "slug: detached gave '$(devbox_slug)', expected the basename '0826-2'"
fi

# CONTROL, by construction: the abbrev-ref form the rest of the repo uses.
cat >"$TMP/abbrev.sh" <<'PLANT'
devbox_branch_planted() {
    git -C "$(devbox_worktree)" rev-parse --abbrev-ref HEAD 2>/dev/null || true
}
PLANT
# shellcheck source=/dev/null
source "$TMP/abbrev.sh"
declare -F devbox_branch_planted >/dev/null || log_fail "CONTROL COULD NOT PLANT: the abbrev-ref variant did not load"
planted="$(devbox_slugify "$(devbox_branch_planted)")"
if [[ "$planted" == "head" ]]; then
    ok "CONTROL: --abbrev-ref on a detached HEAD gives the hostname 'head' -- the detached row would go red"
else
    no "CONTROL DID NOT FIRE: --abbrev-ref gave '$planted', so the detached assertion proves nothing"
fi

# The manual escape hatch still works, and is still sanitised.
DEVBOX_SLUG='My Box/2' devbox_slug >"$TMP/override" 2>/dev/null
if [[ "$(cat "$TMP/override")" == "my-box-2" ]]; then
    ok "slug: DEVBOX_SLUG overrides the branch and is sanitised ('My Box/2' -> 'my-box-2')"
else
    no "slug: DEVBOX_SLUG override gave '$(cat "$TMP/override")', expected 'my-box-2'"
fi

# =============================================================================
# 4. Identity and ports must NOT depend on the branch
# =============================================================================
# A branch is renamed; a path is not. If either of these ever consults the slug,
# a rename orphans the container or shuffles its port block.
log_test "identity and ports stay path-derived"
body_of() { sed -n "/^$1() {/,/^}/p" "$LIB"; }
BRANCH_RE='devbox_branch|devbox_slug|slug|branch|symbolic-ref|abbrev-ref'
for fn in devbox_container_id devbox_base_port; do
    body="$(body_of "$fn")"
    if [[ -z "$body" ]]; then
        no "$fn: could not be located in $LIB -- this grep-control is vacuous"
        continue
    fi
    if printf '%s' "$body" | grep -vE '^[[:space:]]*#' | grep -qE "$BRANCH_RE"; then
        no "$fn: references the branch/slug; identity and ports must survive a rename"
    else
        ok "$fn: no branch or slug reference ($(printf '%s' "$body" | wc -l | tr -d ' ') lines scanned)"
    fi
done

# CONTROL, by construction: a body that DOES consult the slug must be caught.
cat >"$TMP/tainted.sh" <<'PLANT'
devbox_container_id_planted() {
    local d
    d="$(devbox_docker)"
    $d ps -aq --filter "label=slug=$(devbox_slug)" | head -1
}
PLANT
if sed -n '/^devbox_container_id_planted() {/,/^}/p' "$TMP/tainted.sh" |
    grep -vE '^[[:space:]]*#' | grep -qE "$BRANCH_RE"; then
    ok "CONTROL: a container lookup keyed on the slug is detected"
else
    no "CONTROL DID NOT FIRE: a slug-keyed container lookup went undetected"
fi

# =============================================================================
# 5. Drift: recorded vs baked vs wanted
# =============================================================================
log_test "devbox_slug_drift: a stale hostname is REPORTED, never printed as a URL"
if [[ -z "$(devbox_slug_drift alpha alpha alpha)" ]]; then
    ok "drift: three agreeing names report nothing"
else
    no "drift: agreeing names produced a report: $(devbox_slug_drift alpha alpha alpha)"
fi
out="$(devbox_slug_drift beta alpha alpha)"
if [[ "$out" == *"container serves alpha"* && "$out" == *"would use beta"* ]]; then
    ok "drift: a renamed branch is reported (\"$out\")"
else
    no "drift: a renamed branch produced \"$out\""
fi

# The recorded key comes from the state file through the REAL accessor, not a
# hand-rolled parser: this change added a key to a format that already had two
# readers, and a third would be the bug.
DEVBOX_STATE_FILE="$TMP/.devbox-state"
cat >"$DEVBOX_STATE_FILE" <<'STATE'
# Generated by ./run.sh setup - do not edit
worktree=/home/x/console
container=rediacc-devbox-7-console
base_port=17000
slug=stale-name
STATE
recorded="$(devbox_state_get slug)"
if [[ "$recorded" == "stale-name" ]]; then
    ok "state: devbox_state_get reads the new slug= key ('$recorded')"
else
    no "state: devbox_state_get slug gave '$recorded', expected 'stale-name'"
fi
out="$(devbox_slug_drift alpha alpha "$recorded")"
if [[ "$out" == *"records stale-name"* ]]; then
    ok "drift: a state file disagreeing with the container is reported (\"$out\")"
else
    no "drift: a stale state file produced \"$out\""
fi

# CONTROL, by construction: a drift function that reports nothing.
cat >"$TMP/silent.sh" <<'PLANT'
devbox_slug_drift_planted() { return 0; }
PLANT
# shellcheck source=/dev/null
source "$TMP/silent.sh"
if [[ -z "$(devbox_slug_drift_planted beta alpha stale-name)" ]]; then
    ok "CONTROL: a silent drift function reports nothing -- the two drift rows would go red"
else
    no "CONTROL DID NOT FIRE: the silent variant still produced output"
fi

# =============================================================================
# 6. devbox_route_label: traefik's 404 is not "live"
# =============================================================================
log_test "devbox_route_label: an unmatched Host must never be labelled live"
label="$(devbox_route_label 404 '' no)"
if [[ "$label" == *"no such router"* && "$label" != *"live"* ]]; then
    ok "route: 404 with no router says \"$label\""
else
    no "route: 404 with no router said \"$label\" -- the browser would show a 404 for a 'live' row"
fi
label="$(devbox_route_label 404 '' yes)"
if [[ "$label" == *"live"* ]]; then
    ok "route: 404 from a router that DOES exist is the backend's own not-found (\"$label\")"
else
    no "route: 404 behind a real router said \"$label\""
fi
label="$(devbox_route_label 404 '')"
if [[ "$label" != *"live"* ]]; then
    ok "route: 404 with no caller claim refuses to claim live (\"$label\")"
else
    no "route: an unqualified 404 claimed \"$label\""
fi
for row in "000::proxy unreachable" "502:run account dev:no backend" "200::live" "301::live"; do
    IFS=: read -r code hint want <<<"$row"
    label="$(devbox_route_label "$code" "$hint")"
    if [[ "$label" == *"$want"* ]]; then
        ok "route: HTTP $code -> \"$label\""
    else
        no "route: HTTP $code said \"$label\", expected it to contain '$want'"
    fi
done

# CONTROL, by construction: the pre-change catch-all.
cat >"$TMP/oldlabel.sh" <<'PLANT'
devbox_route_label_planted() {
    local code="$1" hint="${2:-}"
    case "$code" in
        000) echo "proxy unreachable" ;;
        502) echo "no backend yet${hint:+ -- $hint}" ;;
        *) echo "live (HTTP $code)" ;;
    esac
}
PLANT
# shellcheck source=/dev/null
source "$TMP/oldlabel.sh"
planted="$(devbox_route_label_planted 404 '' no)"
if [[ "$planted" == *"live"* ]]; then
    ok "CONTROL: the old catch-all calls an unmatched Host \"$planted\" -- the 404 row would go red"
else
    no "CONTROL DID NOT FIRE: the old catch-all did not produce a 'live' 404"
fi

# =============================================================================
echo
if [[ "$fails" -eq 0 ]]; then
    log_pass "devbox hostname: $count control(s) passed"
    echo "  Blind spots: no traefik and no container are started, so the LABELS are"
    echo "  never proven to become routers; 'feat/x' and 'feat-x' still share one"
    echo "  hostname by design; devbox_up's rehost path and devbox_status's probe"
    echo "  loop are grep-read here, not executed."
    exit 0
fi
log_error "devbox hostname: $fails of $count control(s) failed"
exit 1
