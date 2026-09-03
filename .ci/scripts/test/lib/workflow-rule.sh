#!/bin/bash
# Harness for the rules that live inside .ci/scripts/quality/check-workflows.sh.
#
# WHY IT IS SHARED, and why only between two callers rather than three.
# check-workflows.sh hosts several banned-pattern rules, and each gets its own
# gate test driving it against a fixture tree. The incantation is exact and
# easy to get subtly wrong: WORKFLOW_INLINE_ONLY=1 is what empties GITHUB_YAMLS
# (check-workflows.sh:38-40) so the banned-pattern scans become no-ops and the
# fixture tree is the ONLY thing judged. Without it a test both trips on and
# depends on the real .github state.
#
# test-workflow-contracts.sh looks like it belongs here and does NOT: it drives
# .ci/scripts/security/check-workflow-gates.sh with WORKFLOWS_DIR -- a different
# script, a different variable, no inline-only switch. The five lines rhyme; the
# contract does not. Folding it in would produce a helper with two meanings.
#
# Callers must have sourced test-helpers.sh and set REPO_ROOT first.

WORKFLOW_RULE_CHECK="$REPO_ROOT/.ci/scripts/quality/check-workflows.sh"
LAST_OUT=""

# run_check <fixture-dir> -- drives ONLY the workflow rules against that tree.
run_check() {
    local dir="$1" rc=0
    LAST_OUT="$(CI=true WORKFLOW_INLINE_ONLY=1 WORKFLOW_DIR="$dir" bash "$WORKFLOW_RULE_CHECK" 2>&1)" || rc=$?
    return "$rc"
}
