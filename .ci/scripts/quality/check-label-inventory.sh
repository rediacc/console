#!/bin/bash
# .github/labels.yml and the labels that actually exist on the repo must agree,
# in BOTH directions.
#
# WHY. The sibling gate check-label-references.sh closes the first link of the
# chain: code that names a label -> that label declared in .github/labels.yml.
# It stops there on purpose, because DECLARING is not CREATING. The link that
# was still open is the one that bit: `rollback` was declared and referenced and
# did not exist on the repo, and promote-stable.yml:58 searches
# `label:rollback`. A GitHub search for a label that does not exist returns zero
# PRs -- not an error -- so the promotion block never fired and nothing said so.
# That is SILENT FAIL-OPEN, and it is invisible to every check that reads only
# the tree.
#
# The other direction matters too, for a quieter reason: a label that exists on
# the repo but is declared nowhere is recorded nowhere in the tree, and cannot
# reach the PR label guide (.ci/scripts/ci/label-guide-comment.cjs renders that
# guide from labels.yml), so it is a label people can apply and nobody can look
# up. Note that declaring is not the same as listing: an entry may carry
# `guide: false`, which keeps it out of the PR comment while still satisfying
# THIS gate. That is the intended home for GitHub's stock defaults and
# bot-applied labels -- declared and reconciled, just not advertised.
#
# BLINDNESS IS NOT CLEANLINESS. If the live list cannot be read -- no token, an
# API error, an empty response -- this refuses. An empty label list would
# otherwise make direction (b) vacuously clean and direction (a) fire on
# everything, so "empty" is treated as a failed read, never as a tree state.
#
# CREATE-ON-DEMAND. Exactly one label is legitimately absent until first use:
# report-nightly-status.cjs creates `nightly-red` right before it opens the
# rolling issue, because createIssue with an unknown label fails the whole call.
# It is still declared in labels.yml (the guide must be able to explain it), so
# it would otherwise trip direction (a) forever. The allowlist below forgives
# ABSENCE only; the entry names its creator so a future reader can check the
# claim, and the gate verifies both halves of the entry still exist.
#
# Test seams (so the test never touches the network):
#   LABEL_INVENTORY_LABELS_FILE - the declaration file
#   LABEL_INVENTORY_LIVE_FILE   - newline-separated live label names; when set,
#                                 no `gh` call is made at all
#   LABEL_INVENTORY_PROBE_FILE  - newline-separated names the single-label
#                                 re-read (see VERIFY-AT-READ below) should
#                                 report as existing. A SEPARATE seam from the
#                                 list, because the whole point of the re-read
#                                 is that it can disagree with the list.
#
# Usage: check-label-inventory.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_error / log_info / log_warn and get_repo_root are used throughout this gate
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

LABELS_FILE="${LABEL_INVENTORY_LABELS_FILE:-.github/labels.yml}"

# Anti-vacuity on the declaration side. A parse that yields almost nothing is a
# broken parse (reindent, quoting change, wrong path), and treating it as a
# nearly-empty declaration set would make direction (b) scream about every live
# label while direction (a) stayed silent. Refuse instead.
MIN_DECLARED="${LABEL_INVENTORY_MIN_DECLARED:-5}"

# ---------------------------------------------------------------------------
# Create-on-demand allowlist: "<label>|<script that creates it>".
# Absence is forgiven for these and ONLY these. Keep it this short.
# ---------------------------------------------------------------------------
CREATE_ON_DEMAND=(
    # BLOCKER: report-nightly-status.cjs calls issues.createLabel for nightly-red
    # immediately before opening the rolling issue, because issues.create with an
    # unknown label fails the entire call; the label therefore does not exist
    # until the first red night, and demanding it up front would fail this gate
    # on a repo whose nightly has never gone red.
    "nightly-red|.ci/scripts/ci/report-nightly-status.cjs"
    # BLOCKER: claude-review-gate.sh --apply-labels creates `ci` immediately
    # before its first use, the same pattern and for the same reason: the label
    # is brand new, and declaring it here without creating it would fail
    # direction (a) until some human ran `gh label create`. Creating it up front
    # instead is the ordering trap in reverse -- the applier only reaches main
    # after this file does, so the label would sit live and undeclared for the
    # length of one PR and fail direction (b). Create-on-demand dissolves both
    # halves.
    "ci|.ci/scripts/review/claude-review-gate.sh"
    # BLOCKER: bump-none is in exactly the position `ci` was. The same applier
    # creates it immediately before its first use, and the same ordering trap
    # applies in both directions: declaring it here without creating it fails
    # direction (a) until a human runs `gh label create`, while creating it up
    # front leaves it live and undeclared for the length of one PR and fails
    # direction (b), because the applier only reaches main after this file does.
    "bump-none|.ci/scripts/review/claude-review-gate.sh"
)

[ -f "$LABELS_FILE" ] || {
    log_error "labels file not found: $LABELS_FILE"
    exit 1
}

DECLARED="$(grep -E '^- name:' "$LABELS_FILE" | sed -E 's/^- name:[[:space:]]*//' | sed -E 's/^"(.*)"$/\1/' | sed -E "s/^'(.*)'$/\1/" | sed -E 's/[[:space:]]+$//')"
DECLARED_COUNT=$(printf '%s\n' "$DECLARED" | sed '/^$/d' | wc -l)

if [ "$DECLARED_COUNT" -lt "$MIN_DECLARED" ]; then
    log_error "only $DECLARED_COUNT label(s) parsed from $LABELS_FILE (floor: $MIN_DECLARED). The file carries more than that, so this reader is broken, not the file."
    exit 1
fi

# ---------------------------------------------------------------------------
# GitHub caps label descriptions at 100 characters, and rejects longer ones at
# CREATE time only -- a declaration here can sit over the cap indefinitely and
# then fail whatever finally tries to create/sync it (bump-none did exactly
# this on 2026-08-09: the applier's create call failed live, mid-merge-flow).
# Validate proactively, control-first: a checker that cannot fire is not a
# checker, so prove it fires on a planted 101-char description before reading
# the real file.
# ---------------------------------------------------------------------------
DESC_CAP=100
desc_over_cap() {
    # stdin: the labels-yml text. Prints "name<TAB>length" per offender.
    awk -v cap="$DESC_CAP" '
        /^- name:/ { name = $0; sub(/^- name:[[:space:]]*/, "", name);
                     gsub(/^"|"$/, "", name) }
        /^[[:space:]]+description:/ {
            d = $0; sub(/^[[:space:]]+description:[[:space:]]*/, "", d);
            gsub(/^"|"$/, "", d);
            if (length(d) > cap) printf "%s\t%d\n", name, length(d)
        }'
}
CONTROL=$(printf -- '- name: control-label\n  description: "%s"\n' \
    "$(printf 'x%.0s' $(seq 1 101))" | desc_over_cap)
if [ -z "$CONTROL" ]; then
    log_error "description-cap control did not fire on a planted 101-char description; the checker is broken, refusing to certify anything"
    exit 1
fi
OVER=$(desc_over_cap <"$LABELS_FILE")
if [ -n "$OVER" ]; then
    while IFS=$'\t' read -r lbl len; do
        log_error "label '$lbl' declares a $len-char description; GitHub rejects anything over $DESC_CAP at create time, so this fails exactly when something finally tries to create or sync it. Shorten it in $LABELS_FILE."
    done <<<"$OVER"
    exit 1
fi

# ---------------------------------------------------------------------------
# The live list
# ---------------------------------------------------------------------------
if [ -n "${LABEL_INVENTORY_LIVE_FILE:-}" ]; then
    [ -f "$LABEL_INVENTORY_LIVE_FILE" ] || {
        log_error "LABEL_INVENTORY_LIVE_FILE is set to '$LABEL_INVENTORY_LIVE_FILE' but no such file exists; this gate cannot read the live label list and refuses to pass blind"
        exit 1
    }
    LIVE="$(sed -E 's/[[:space:]]+$//' "$LABEL_INVENTORY_LIVE_FILE" | sed '/^$/d')"
    LIVE_SOURCE="$LABEL_INVENTORY_LIVE_FILE (injected)"
else
    command -v gh >/dev/null 2>&1 || {
        log_error "gh is not installed, so the live label list cannot be read. This gate reconciles the tree against the REAL repo; without that read it asserts nothing and refuses to pass blind."
        exit 1
    }
    if ! LIVE="$(gh api 'repos/{owner}/{repo}/labels' --paginate --jq '.[].name' 2>&1)"; then
        log_error "could not read the live label list from GitHub: ${LIVE}"
        log_error "This gate refuses to pass blind. Authenticate (gh auth login / GH_TOKEN) and re-run."
        exit 1
    fi
    LIVE="$(printf '%s\n' "$LIVE" | sed -E 's/[[:space:]]+$//' | sed '/^$/d')"
    LIVE_SOURCE="GitHub API"
fi

LIVE_COUNT=$(printf '%s\n' "$LIVE" | sed '/^$/d' | wc -l)
if [ "$LIVE_COUNT" -eq 0 ]; then
    log_error "the live label list read from $LIVE_SOURCE is EMPTY. A repo with zero labels is not a state this repo can be in, so this is a failed read, not a clean tree -- and an empty list would make half this gate vacuously green."
    exit 1
fi

# ---------------------------------------------------------------------------
# Allowlist hygiene: a stale entry is a permanent hole, so both halves of every
# entry are re-verified. This is what makes the exemption self-expiring: delete
# report-nightly-status.cjs and the allowlist fails rather than quietly
# forgiving a label nothing creates any more.
# ---------------------------------------------------------------------------
#
# The "still declared" half is scoped to the REAL declaration file: a fixture
# tree legitimately does not carry nightly-red, and the entry must not fail
# every test that drives this gate against a fixture. Same shape as
# check-workflow-gates.sh's SLIM_TIMEOUT_REQUIRE_COVERAGE, and the test drives
# the flag on explicitly so the scoping itself stays covered.
if [ -z "${LABEL_INVENTORY_VERIFY_ALLOWLIST:-}" ]; then
    if [ "$LABELS_FILE" = ".github/labels.yml" ]; then
        LABEL_INVENTORY_VERIFY_ALLOWLIST=true
    else
        LABEL_INVENTORY_VERIFY_ALLOWLIST=false
    fi
fi

ALLOWED=""
for entry in "${CREATE_ON_DEMAND[@]}"; do
    name="${entry%%|*}"
    creator="${entry#*|}"
    if [ "$LABEL_INVENTORY_VERIFY_ALLOWLIST" = "true" ] && ! printf '%s\n' "$DECLARED" | grep -qx "$name"; then
        log_error "create-on-demand allowlist names '$name', which is not declared in $LABELS_FILE. Remove the allowlist entry or declare the label."
        exit 1
    fi
    if [ ! -f "$creator" ]; then
        log_error "create-on-demand allowlist says '$creator' creates '$name', but that file does not exist. The exemption is stale: nothing creates the label any more."
        exit 1
    fi
    if ! grep -q "$name" "$creator"; then
        log_error "create-on-demand allowlist says '$creator' creates '$name', but that file does not mention it. The exemption is stale."
        exit 1
    fi
    ALLOWED="${ALLOWED}${name}"$'\n'
done

# ---------------------------------------------------------------------------
# VERIFY-AT-READ, for direction (a) only.
#
# The list read is a snapshot, and the repo's labels change under it. Observed
# live: a full CI run accused `no-auto-retry` of not existing while it existed
# and watchdog-monitor.cjs:1105 was reading it -- someone was mid-way through
# delete-and-recreate to fix its empty description, and the paginated list came
# back one short. The EMPTY-list guard above does not catch that: a list that is
# merely wrong-by-one passes every guard and then produces this gate's loudest
# possible message, the one about rollback and silent fail-open.
#
# That is worse than a missed finding. A gate that cries wolf that hard on a
# race gets ignored, and then it is worth nothing on the day it is right. So a
# label that LOOKS absent is re-read on its own before it is accused: a 404
# confirms the finding, a 200 means the list was stale and the finding is
# dropped with a note.
#
# Only this direction needs it. An EXTRA name in the list cannot be a
# partial-read artifact -- a stale read loses entries, it does not invent them.
#
# probe_label <name> -> 0 exists, 1 confirmed absent, 2 could not probe.
# In injected mode there is no API to re-read, so the injected list stands as
# its own authority and the probe reports "could not" (which reports the
# finding, preserving the offline test seam). LABEL_INVENTORY_PROBE_FILE
# overrides, which is how the test drives both re-verify outcomes without a
# network.
# ---------------------------------------------------------------------------
url_encode() {
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$1" | jq -sRr @uri
    else
        # Space is the only character in this repo's label names that needs it
        # ('good first issue'); a name with anything more exotic would fail the
        # probe loudly rather than silently, which is the safe direction.
        printf '%s' "${1// /%20}"
    fi
}

probe_label() {
    local name="$1"
    if [ -n "${LABEL_INVENTORY_PROBE_FILE:-}" ]; then
        [ -f "$LABEL_INVENTORY_PROBE_FILE" ] || return 2
        if grep -qxF "$name" "$LABEL_INVENTORY_PROBE_FILE"; then return 0; fi
        return 1
    fi
    [ -n "${LABEL_INVENTORY_LIVE_FILE:-}" ] && return 2
    command -v gh >/dev/null 2>&1 || return 2

    local out rc=0
    out="$(gh api "repos/{owner}/{repo}/labels/$(url_encode "$name")" 2>&1)" || rc=$?
    [ "$rc" -eq 0 ] && return 0
    # Only a 404 CONFIRMS absence. A 403, a 500 or a network error says nothing
    # about the label, and must not be read as agreement with the stale list.
    case "$out" in
        *"HTTP 404"* | *"Not Found"*) return 1 ;;
        *) return 2 ;;
    esac
}

# ---------------------------------------------------------------------------
# (a) declared but absent live
# ---------------------------------------------------------------------------
PROBLEMS=0
while IFS= read -r label; do
    [ -n "$label" ] || continue
    if printf '%s\n' "$LIVE" | grep -qx "$label"; then continue; fi
    if printf '%s\n' "$ALLOWED" | grep -qx "$label"; then
        log_info "'$label' is declared and absent, which is expected: it is created on demand (see the allowlist in this script)."
        continue
    fi

    probe_rc=0
    probe_label "$label" || probe_rc=$?
    if [ "$probe_rc" -eq 0 ]; then
        log_warn "'$label' was missing from the label list but a direct re-read found it. The list read was stale (the repo's labels were being edited mid-run); dropping the finding rather than accusing a live label of deletion."
        continue
    fi

    log_error "label '$label' is declared in $LABELS_FILE but does NOT exist on the repo. Any workflow that searches or filters on it FAILS OPEN -- a search for a nonexistent label returns zero results rather than an error, which is exactly how 'rollback' let stable promotion proceed past a rolled-back PR. Create it: gh label create '$label'"
    PROBLEMS=$((PROBLEMS + 1))
done <<<"$DECLARED"

# ---------------------------------------------------------------------------
# (b) live but undeclared
# ---------------------------------------------------------------------------
while IFS= read -r label; do
    [ -n "$label" ] || continue
    if printf '%s\n' "$DECLARED" | grep -qx "$label"; then continue; fi
    log_error "label '$label' exists on the repo but is declared nowhere in $LABELS_FILE. Nothing in the tree records that it exists, and it cannot reach the PR label guide, so it is a label people can apply and nobody can look up. Declare it (name/color/description, plus 'guide: false' if it should stay off the PR guide) or delete it: gh label delete '$label'"
    PROBLEMS=$((PROBLEMS + 1))
done <<<"$LIVE"

# ---------------------------------------------------------------------------
# (c) present in both, but the DESCRIPTION or COLOR has drifted
# ---------------------------------------------------------------------------
# NAMES WERE NEVER THE WHOLE CONTRACT. This gate reconciled existence in both
# directions and stopped there, so a label could exist, be declared, and still
# tell every human the opposite of the truth.
#
# Measured 2026-08-26: TEN fields had drifted, silently, for an unknown period.
# The one that cost real time: `release` still read "Opt-in: triggers CD
# pipeline on merge to main", while labels.yml says "Historical only: CD reads
# no label, it is dispatched unconditionally". An operator read the live text,
# reasonably concluded that a label controlled releases, and scoped a whole task
# around it. Others: `translation` carried the typo "Missing on wrong
# translation,"; `no-auto-retry` had an EMPTY description and the wrong colour;
# `no-cancel-push` described behaviour it does not have.
#
# The description is documentation that ships to every human who opens the label
# picker, and it was the one part of the label nothing checked.
#
# LIVE_JSON is a SEPARATE read from LIVE (which is names-only, and whose
# fixture seam feeds names-only). When it cannot be obtained this section is
# skipped rather than failing: the name reconciliation above already refuses to
# pass blind on an unreadable API, so a second hard failure here would only turn
# fixture-driven runs red.
LIVE_JSON=""
if [ -n "${LABEL_INVENTORY_LIVE_JSON_FILE:-}" ]; then
    LIVE_JSON="$(cat "$LABEL_INVENTORY_LIVE_JSON_FILE" 2>/dev/null || echo "")"
elif [ "$LIVE_SOURCE" = "GitHub API" ]; then
    LIVE_JSON="$(gh api 'repos/{owner}/{repo}/labels' --paginate 2>/dev/null || echo "")"
fi

if [ -n "$LIVE_JSON" ] && [ "$LABELS_FILE" = ".github/labels.yml" ]; then
    DRIFT="$(
        LIVE_JSON="$LIVE_JSON" LABELS_FILE="$LABELS_FILE" python3 - <<'PY' || true
import json, os, re, sys

try:
    live = {l["name"]: l for l in json.loads(os.environ["LIVE_JSON"])}
except Exception:
    sys.exit(0)

want, cur = {}, None
for line in open(os.environ["LABELS_FILE"], encoding="utf-8"):
    m = re.match(r"^\s*-\s*name:\s*(.+?)\s*$", line)
    if m:
        cur = m.group(1).strip("\"'")
        want[cur] = {}
        continue
    if cur:
        m2 = re.match(r"^\s*(description|color):\s*(.*)$", line)
        if m2:
            want[cur][m2.group(1)] = m2.group(2).strip().strip("\"'")

for name, w in sorted(want.items()):
    l = live.get(name)
    if not l:
        continue  # absence is section (a)'s job, not this one's
    if "description" in w and (l.get("description") or "") != w["description"]:
        print("%s\tdescription\t%s" % (name, (l.get("description") or "<empty>")[:70]))
    if "color" in w and (l.get("color") or "").lower() != w["color"].lower().lstrip("#"):
        print("%s\tcolor\t%s" % (name, l.get("color")))
PY
    )"
    while IFS=$'\t' read -r dname dfield dlive; do
        [ -n "$dname" ] || continue
        log_error "label '$dname' has a drifted $dfield: the repo says '$dlive', $LABELS_FILE says something else. The description is what every human reads in the label picker, so a drifted one is documentation that lies. Push the declared values: gh api --method PATCH repos/{owner}/{repo}/labels/$dname -f $dfield='<value from $LABELS_FILE>'"
        PROBLEMS=$((PROBLEMS + 1))
    done <<<"$DRIFT"
fi

if [ "$PROBLEMS" -gt 0 ]; then
    log_error "$PROBLEMS label inventory mismatch(es) between $LABELS_FILE and the live repo."
    exit 1
fi

log_info "label inventory reconciled: $DECLARED_COUNT declared, $LIVE_COUNT live (source: $LIVE_SOURCE); names, descriptions and colours all agree"
