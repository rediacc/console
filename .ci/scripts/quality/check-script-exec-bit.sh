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
    local root="$1" hit src rest text ref f mode
    (
        cd "$root" || exit 0
        # ANCHORED with a negative lookbehind, which is why this is -P and not -E.
        # An unanchored `\./` also matches the SECOND dot of a `../` reference:
        # `../scripts/lib/foo.sh` yields `./scripts/lib/foo.sh`, a DIFFERENT file.
        #
        # NOT -h: the referencing FILE is load-bearing. `./sibling.sh` means a sibling
        # of the file that says it, not of the repo root. Resolving everything against
        # the root skipped every nested invocation -- which is the pattern used
        # throughout .ci/scripts/, i.e. exactly the class this gate exists for. It
        # checked 9 repo-root scripts and silently passed on the rest. Caught in
        # review on this PR; the earlier two controls both used repo-root references,
        # so they proved detection while overstating coverage.
        # Whole LINES, not just the match, so comment lines can be dropped. A `./x.sh`
        # inside `# Usage: ./x.sh` or `# shellcheck source=./lib/x.sh` is documentation,
        # not an invocation, and both produced false positives the moment the path
        # resolution above started working: one file the Dockerfile chmods itself, one
        # that is SOURCED and therefore needs no exec bit at all.
        git grep -nP '(?<![\w./-])\./[\w./-]+\.sh' -- \
            '*.sh' '*.yml' '*.yaml' '*.json' '*.md' '*.ts' 2>/dev/null |
            while IFS= read -r hit; do
                src="${hit%%:*}"
                rest="${hit#*:}"
                text="${rest#*:}"
                case "$(printf '%s' "$text" | sed 's/^[[:space:]]*//')" in
                    '#'* | '//'* | '*'*) continue ;;
                esac
                ref="$(printf '%s' "$text" | grep -oP '(?<![\w./-])\./[\w./-]+\.sh' | head -1)"
                [ -z "$ref" ] && continue
                # Resolve against the referencing file's own directory, then normalise
                # a leading "./" away. A file at the repo root gives dir ".".
                f="$(dirname "$src")/${ref#./}"
                f="${f#./}"
                echo "$f"
            done |
            sort -u |
            while read -r f; do
                # Only judge paths actually tracked here; a `./x.sh` inside a heredoc
                # meant for another checkout is not ours.
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

# A parent-relative reference must NOT be mistaken for one relative to the referencing
# file. This control is built so the two behaviours produce DIFFERENT path sets, which
# the first version of it did not: it planted `../victim.sh` in the SAME directory as an
# existing `./victim.sh` reference, so both the correct and the broken behaviour deduped
# to {victim.sh} and the assertion could not fail. Caught in review.
#
# Here the decoy lives in a SUBDIRECTORY and is referenced as `../decoy.sh` from a file
# in that same subdirectory. Correct: the reference is skipped and decoy is never
# reported. Broken (unanchored): `./decoy.sh` is extracted and resolved against the
# subdirectory, naming sub/decoy.sh, which IS tracked and IS non-executable, so it is
# reported. The sets differ by exactly one entry.
(
    cd "$control_dir" || exit 1
    mkdir -p sub
    printf '#!/bin/bash\necho decoy\n' >sub/decoy.sh
    chmod 644 sub/decoy.sh
    printf 'run: ../decoy.sh\n' >sub/parentref.yml
    git add -A >/dev/null 2>&1
)
parent_hits=$(scan_repo "$control_dir" | grep -c '^sub/decoy.sh' || true)

control_hits=$(scan_repo "$control_dir" | wc -l)
if [ "$parent_hits" -ne 0 ]; then
    # Single quotes on the lines carrying ../x.sh: backticks inside a double-quoted
    # echo are COMMAND SUBSTITUTION, so the error path would try to execute the very
    # script it is complaining about. shfmt caught that here.
    echo "${RED}REFUSE${OFF}  a ../decoy.sh reference was resolved as if it were"
    echo '        ./decoy.sh relative to the referencing file. Those name DIFFERENT'
    echo '        files. The extraction regex has lost its anchor; see the comment'
    echo '        above this control.'
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
