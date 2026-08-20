#!/bin/bash
# Every shell script INVOKED as `./path.sh` must be committed executable.
#
# WHY THIS EXISTS. A script invoked as `./x.sh` without mode 100755 does not
# fail like a bug. It fails with exit 126 and one line on stderr, before any
# of its own output exists. A driver loop that prints a header per iteration
# and then counts headers therefore reports a full, healthy run: N iterations
# attempted, N headers printed, zero work done. That is not hypothetical --
# it happened in this repo on 2026-08-20, where 36 pipeline combinations
# "ran" in under a second and the header count read exactly like success.
#
# The lesson generalises past the missing mode bit: an instrument that counts
# ATTEMPTS cannot distinguish them from COMPLETIONS. This gate closes the
# cheap half of that (the mode bit is mechanically checkable); the expensive
# half is a discipline, which is why the failure above is quoted here rather
# than summarised.
#
# It reads the GIT INDEX mode, not the filesystem, because the index is what
# CI checks out. A locally chmod'ed file that was committed 100644 is still
# broken for everybody else, and a filesystem check would call it clean.
#
# CONTROL-FIRST: the detector is run against a planted non-executable script
# BEFORE the real scan. If the control cannot fire, the gate refuses (exit 2)
# rather than reporting a clean tree it never actually inspected.
set -uo pipefail

RED=$'\033[31m'
GREEN=$'\033[32m'
YEL=$'\033[33m'
OFF=$'\033[0m'

# Collect `./something.sh` references out of the given files, then report any
# whose git index mode is not 100755. Echoes one offender per line.
scan_repo() {
    local root="$1" ref f mode
    (
        cd "$root" || exit 0
        # ANCHORED with a negative lookbehind, which is why this is -P and not -E.
        # An unanchored `\./` also matches the SECOND dot of a `../` reference: the
        # text `../scripts/lib/foo.sh` yields `./scripts/lib/foo.sh`, which strips to
        # a repo-root path that is a DIFFERENT FILE from the one referenced. That is
        # both a false positive on the wrong file and no coverage of the right one.
        # The same hole swallows `somepath./bar.sh`. Caught in review on this PR.
        git grep -hoP '(?<![\w./-])\./[\w./-]+\.sh' -- \
            '*.sh' '*.yml' '*.yaml' '*.json' '*.md' '*.ts' 2>/dev/null |
            sort -u |
            while read -r ref; do
                f="${ref#./}"
                # Only judge paths that are actually tracked here; a `./x.sh`
                # inside a heredoc for some other checkout is not ours.
                mode=$(git ls-files -s -- "$f" 2>/dev/null | awk '{print $1}')
                [ -z "$mode" ] && continue
                [ "$mode" = "100755" ] && continue
                echo "$f (mode $mode)"
            done
    )
}

# ---- CONTROL: prove the detector can fail before trusting it to pass -------
control_dir=$(mktemp -d)
trap 'rm -rf "$control_dir"' EXIT
(
    cd "$control_dir" || exit 1
    git init -q .
    printf '#!/bin/bash\necho hi\n' >victim.sh
    chmod 644 victim.sh
    printf 'run: ./victim.sh\n' >caller.yml
    git add -A >/dev/null 2>&1
) || {
    echo "${RED}REFUSE${OFF}  could not build the control fixture"
    exit 2
}

# A parent-relative reference must NOT be mistaken for a repo-root one. Planted as its
# own control because the unanchored version passed every other check in this file while
# silently checking the wrong file: `../victim.sh` is not `./victim.sh`.
(
    cd "$control_dir" || exit 1
    printf 'source ../victim.sh\n' > parentref.yml
    git add -A >/dev/null 2>&1
)
parent_hits=$(scan_repo "$control_dir" | grep -c '^victim.sh' || true)

control_hits=$(scan_repo "$control_dir" | wc -l)
if [ "$parent_hits" -ne 1 ]; then
    echo "${RED}REFUSE${OFF}  the parent-relative control is wrong: adding a `../victim.sh`"
    echo "        reference changed the reported count. A `../x.sh` reference must be"
    echo "        ignored, not silently read as the repo-root `x.sh`, which is a"
    echo "        different file."
    exit 2
fi

if [ "$control_hits" -lt 1 ]; then
    echo "${RED}REFUSE${OFF}  the control did not fire: a planted non-executable"
    echo "        ./victim.sh referenced from caller.yml was NOT reported."
    echo "        A clean result from this gate would be meaningless, so it"
    echo "        refuses instead of printing one."
    exit 2
fi

# A second control: the SAME fixture, made executable, must go quiet. Without
# this, a detector that flags every script would also "pass" the check above.
(cd "$control_dir" && chmod 755 victim.sh && git add -A >/dev/null 2>&1)
control_clean=$(scan_repo "$control_dir" | wc -l)
if [ "$control_clean" -ne 0 ]; then
    echo "${RED}REFUSE${OFF}  the negative control fired: an EXECUTABLE script was"
    echo "        still reported. The detector flags everything, so a hit means"
    echo "        nothing."
    exit 2
fi

# ---- the real scan --------------------------------------------------------
offenders=$(scan_repo "$(git rev-parse --show-toplevel)")

if [ -n "$offenders" ]; then
    count=$(printf '%s\n' "$offenders" | wc -l)
    echo "${RED}✗${OFF} $count script(s) are invoked as ./path.sh but committed NON-executable:"
    echo ""
    printf '%s\n' "$offenders" | sed 's/^/    /'
    echo ""
    echo "  These fail at runtime with exit 126 BEFORE producing any output, so a"
    echo "  caller that counts output lines sees a healthy run that did nothing."
    echo ""
    echo "  Fix:  git update-index --chmod=+x <path>"
    exit 1
fi

echo "${GREEN}✓${OFF} every ./path.sh reference resolves to a committed-executable script"
echo "  ${YEL}controls:${OFF} a planted non-executable script IS reported, and the same"
echo "  script made executable is NOT, so this green distinguishes the two."
