#!/usr/bin/env bash
# Hand the reviewer one epic's context, so it does not have to go investigating.
#
# WHY THIS EXISTS. The review is budgeted in turns, and every turn spent
# rediscovering what a change was FOR is a turn not spent reading the change. All
# of that context is already written down and already in the checkout: the epic
# section names the work, the worklist items carry their own tick evidence, and a
# plan file carries the reasoning. This collects it in one read.
#
# IT IS A SHELL SCRIPT, NOT AN AGENT, and that is not a style preference. The
# review action passes --disallowed-tools Task,Agent, added after a PR spawned
# three background review agents, ran out of turns, and posted a placeholder
# instead of a review. Anything this tool needs to do must be doable in one Bash
# call.
#
# READ-ONLY, and it never touches the network. Everything it prints comes from
# the PR checkout, so it cannot fail in a way that costs a turn to diagnose.
set -euo pipefail

usage() {
    cat >&2 <<'MSG'
usage: epic-context.sh <epic-id> [branch]

Prints one epic's title, its worklist items with evidence, any plan file they
reference, and the commits carrying its PR-TASK trailer.
MSG
    exit 2
}

[[ $# -lt 1 ]] && usage
EPIC="$1"
REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH="${2:-$(git branch --show-current)}"
SNAP="$REPO_ROOT/agent/pr/${BRANCH//\//-}.md"

if [[ ! -f "$SNAP" ]]; then
    echo "no snapshot at agent/pr/${BRANCH//\//-}.md; cannot describe $EPIC" >&2
    exit 1
fi

echo "=============================================================="
echo "EPIC $EPIC   (branch $BRANCH)"
echo "=============================================================="
echo

# Print the heading plus everything until the next level-3 heading.
awk -v id="$EPIC" '
    /^### / { insection = 0 }
    /^### / { pending = $0; next }
    $0 ~ ("PR-TASK: " id) { if (pending != "") { print pending; print "" } insection = 1 }
    insection { print }
' "$SNAP"

echo
echo "-------- plan files referenced by this epic ------------------"
# A worklist item may carry a planfid: token naming an approved design. Those
# files are tracked, so the reviewer can read the reasoning rather than infer it.
PLANS="$(awk -v id="$EPIC" '
    /^### / { insection = 0 }
    $0 ~ ("PR-TASK: " id) { insection = 1 }
    insection { print }
' "$SNAP" | grep -oE 'agent/PLAN-[A-Za-z0-9._-]+\.md' | sort -u || true)"
if [[ -z "$PLANS" ]]; then
    echo "(none referenced)"
else
    for f in $PLANS; do
        if [[ -f "$REPO_ROOT/$f" ]]; then
            echo "--- $f (first 40 lines) ---"
            head -40 "$REPO_ROOT/$f"
        else
            echo "--- $f: referenced but NOT in this checkout ---"
        fi
    done
fi

echo
echo "-------- commits carrying PR-TASK: $EPIC ---------------------"
BASE="${PR_BASE_REF:-origin/main}"
if git rev-parse --verify --quiet "$BASE" >/dev/null; then
    COUNT="$(git log "$BASE..HEAD" --no-merges --grep="^PR-TASK: $EPIC" --format='%H' | wc -l)"
    if [[ "$COUNT" -eq 0 ]]; then
        # Say so rather than printing nothing: an empty list and a broken range
        # look identical, and one of them means the review has no scope at all.
        echo "NO COMMITS carry this trailer in $BASE..HEAD."
        echo "Either the epic has not been worked yet, or its commits are untagged,"
        echo "in which case check:ci-pr-task-trailers is the gate that will say so."
    else
        git log "$BASE..HEAD" --no-merges --grep="^PR-TASK: $EPIC" \
            --format='%h %s' | sed 's/^/  /'
        echo
        echo "  files touched:"
        git log "$BASE..HEAD" --no-merges --grep="^PR-TASK: $EPIC" --format='%H' |
            while read -r sha; do git show --name-only --format= "$sha"; done |
            sort -u | sed 's/^/    /'
    fi
else
    echo "base ref $BASE is not resolvable in this checkout; commit list skipped"
fi
