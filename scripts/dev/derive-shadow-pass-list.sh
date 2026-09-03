#!/usr/bin/env bash
# Derive the org secrets whose Bitwarden twin has PASSED a value-for-value compare,
# from real CI run output, and print the exact `gh secret delete` commands.
#
# WHY A SCRIPT. The standing rule is that a fallback may only be destroyed after
# something has compared it to its replacement VALUE BY VALUE. The only place both
# values exist at once is the shadow compare step in CI, and its verdict lives in run
# logs that expire. Deriving the list by hand is how a wrong number gets trusted: the
# "42 agree" figure this migration ran on came from run 33691632299, which was
# CANCELLED and whose logs no longer return a single verdict line.
#
# It prints commands; it does not run them. Deleting a secret is irreversible and is
# the operator's to execute.
#
# Usage:
#   scripts/dev/derive-shadow-pass-list.sh [--branch <branch>] [--runs <n>]
set -uo pipefail
BRANCH="${BRANCH:-$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo main)}"
RUNS=6
while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --runs)
            RUNS="$2"
            shift 2
            ;;
        *)
            echo "unknown arg: $1" >&2
            exit 2
            ;;
    esac
done
command -v gh >/dev/null || {
    echo "gh is required" >&2
    exit 2
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "# deriving from branch $BRANCH, up to $RUNS run(s) per shadow-carrying workflow" >&2

# Every workflow that actually carries a compare step, from the tree rather than memory.
# while-read, not mapfile: bash 4+ only, and check:ci-shell-commands bans it because
# the minimal CI image does not carry it.
WFS=()
while IFS= read -r _wf; do
    [[ -n "$_wf" ]] && WFS+=("$_wf")
done < <(grep -l "Compare shadow secrets against GitHub" .github/workflows/*.yml | xargs -n1 basename)
echo "# ${#WFS[@]} shadow-carrying workflow(s)" >&2

# JOB conclusion, not RUN conclusion. A run cancelled by the watchdog can still
# contain jobs that ran their compare step and printed a verdict -- run 33718710855 is
# exactly that shape: conclusion=cancelled, six `shadow ... match` lines. Filtering on
# the run threw all of them away. The converse still holds and is why this is not a
# relaxation: a job whose OWN conclusion is cancelled or failed did not report, and its
# absence of a verdict must never read as a pass.
for wf in "${WFS[@]}"; do
    while read -r id; do
        [[ -z "$id" ]] && continue
        # Only jobs that themselves succeeded; their step output is trustworthy.
        ok_jobs="$(gh run view "$id" --json jobs \
            -q '[.jobs[]|select(.conclusion=="success")|.name]|length' 2>/dev/null || echo 0)"
        [[ "${ok_jobs:-0}" -eq 0 ]] && continue
        gh run view "$id" --log 2>/dev/null |
            grep -oE 'shadow [A-Z0-9_]+ (match|MISMATCH|EMPTY)' >>"$WORK/verdicts.txt" || true
    done < <(gh run list --workflow="$wf" --branch "$BRANCH" --limit "$RUNS" \
        --json databaseId -q '.[].databaseId' 2>/dev/null)
done

sort -u "$WORK/verdicts.txt" 2>/dev/null >"$WORK/u.txt" || : >"$WORK/u.txt"
awk '{print $2, $3}' "$WORK/u.txt" | sort -u >"$WORK/pairs.txt"

# A name is deletable only if it has at least one `match` and NO mismatch/empty anywhere.
awk '$2=="match"{ok[$1]=1} $2!="match"{bad[$1]=1} END{for(n in ok) if(!(n in bad)) print n}' \
    "$WORK/pairs.txt" | sort >"$WORK/pass.txt"
awk '$2!="match"{print $1}' "$WORK/pairs.txt" | sort -u >"$WORK/fail.txt"

echo "# verdicts seen: $(wc -l <"$WORK/pairs.txt"), clean-pass names: $(wc -l <"$WORK/pass.txt"), names with a non-match: $(wc -l <"$WORK/fail.txt")" >&2
if [[ ! -s "$WORK/pass.txt" ]]; then
    echo "REFUSING: no passing compare found on $BRANCH. Push and let CI run; a cancelled run reports nothing." >&2
    exit 1
fi

# Map each SHADOW name to the GITHUB secret the compare actually read, from the
# GH_<shadow>: ${{ secrets.<github> }} lines -- the two differ wherever the migration
# renamed something, and deleting by the shadow name would delete the wrong secret.
python3 - "$WORK/pass.txt" <<'PY'
import re, pathlib, subprocess, sys, json
passed = {l.strip() for l in open(sys.argv[1]) if l.strip()}
gh_of = {}
for f in pathlib.Path('.github/workflows').glob('*.yml'):
    for m in re.finditer(r'GH_([A-Z0-9_]+):\s*\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}', f.read_text()):
        gh_of.setdefault(m.group(1), set()).add(m.group(2))
org = set(json.loads(subprocess.run(
    ["gh", "api", "orgs/rediacc/actions/secrets", "--paginate", "-q", "[.secrets[].name]"],
    capture_output=True, text=True, check=True).stdout))
repo = set(json.loads(subprocess.run(
    ["gh", "api", "repos/rediacc/console/actions/secrets", "--paginate", "-q", "[.secrets[].name]"],
    capture_output=True, text=True, check=True).stdout))
print("# %d org secret(s), %d repo-level" % (len(org), len(repo)), file=sys.stderr)
out, skipped = [], []
for shadow in sorted(passed):
    names = gh_of.get(shadow, set())
    if len(names) != 1:
        skipped.append((shadow, "reads %d github name(s): %s" % (len(names), sorted(names) or "none")))
        continue
    gh = next(iter(names))
    if gh not in org:
        skipped.append((shadow, "%s is not an org secret" % gh)); continue
    if gh in repo:
        # A repo-level twin SHADOWS the org one, so the compare tested the repo copy and
        # the org copy has never been compared. This is exactly how CLAUDE_CODE_OAUTH_TOKEN
        # looked, and deleting on that evidence would destroy an unverified value.
        skipped.append((shadow, "%s also exists REPO-level, which shadows the org copy; the compare tested the repo one" % gh)); continue
    out.append(gh)
for name in out:
    print("gh secret delete %s --org rediacc" % name)
for s, why in skipped:
    print("# SKIP %s: %s" % (s, why), file=sys.stderr)
print("# %d deletable, %d skipped" % (len(out), len(skipped)), file=sys.stderr)
PY
