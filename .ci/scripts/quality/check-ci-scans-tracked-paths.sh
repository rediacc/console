#!/usr/bin/env bash
# CI CANNOT EXECUTE WHAT GIT DOES NOT TRACK.
#
# A GitHub runner checks out tracked files only. So a workflow step or a CI shell script
# that RUNS something under a gitignored path invokes a file that is not there: it errors,
# or worse, exits 0 having done nothing and reports coverage that cannot exist.
#
# This is not hypothetical. Over five stops on 2026-08-28 a stop-hook judge repeatedly
# instructed this session to wire `private/growth/.ci/checks/check-no-direct-query.sh`
# into `ci-quality.yml`. `private/growth` is a SEPARATE repository, ignored at
# `.gitignore:69`, with zero tracked files in console. Each time, the reason it could not
# work had to be re-derived by hand.
#
# `scripts/check-gate-manifest.ts` closed one door: a manifest LEAF git does not track is
# now refused. This closes the other: a workflow `run:` line, or a `.ci/scripts` command,
# that reaches into an ignored path.
#
# PROSE IS NOT EXECUTION, and that distinction is the whole difficulty. Comments and error
# messages naming `private/growth` are CORRECT and common: `check-translation-hashes.ts`
# tells a human which pipeline regenerates a file, `ci-quality.yml` explains why a
# provenance file is committed. Flagging those would make the gate noise, it would be
# silenced, and it would then guard nothing. Only command positions are examined.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SELF="check-ci-scans-tracked-paths.sh"

# The ignored roots, ASKED OF GIT rather than hardcoded: a new ignored directory is
# covered the day it appears, and a path that stops being ignored stops being flagged.
ignored_roots() {
    local d
    for d in "$1"/*/ "$1"/*/*/; do
        [ -d "$d" ] || continue
        d="${d%/}"
        git -C "$1" check-ignore -q "$d" 2>/dev/null && printf '%s\n' "${d#"$1"/}"
    done
}

scan() {
    local root="$1" hits=0 roots pat f n line stripped
    roots=$(ignored_roots "$root")
    [ -z "$roots" ] && return 0
    # ONE grep over each surface, not one pass per ignored root. The nested form was
    # O(roots x files x lines) in pure bash and did not finish in two minutes on this repo.
    pat=$(printf '%s\n' "$roots" | sed 's/[].[^$*\/]/\\&/g' | paste -sd'|')

    while IFS=: read -r f n line; do
        [ -n "$f" ] || continue
        case "$(basename "$f")" in "$SELF") continue ;; esac
        stripped="${line#"${line%%[![:space:]]*}"}"
        case "$stripped" in '#'*) continue ;; esac

        # BOTH conditions, and dropping either one makes this gate noise. Without the
        # command-position test, a YAML artifact `path:` list entry like
        # `private/bin/renet-linux-*` reads as an executable. Without the executable test,
        # a tracked script writing its OUTPUT to `./private/bin` reads as running from it.
        case "$stripped" in
            run:* | -\ run:* | bash\ * | sh\ * | ./* | source\ * | .\ * | \
                npm\ * | npx\ * | node\ * | python3\ * | tsx\ *) ;;
            *) continue ;;
        esac

        # THE EXECUTABLE, not the line. `ci-build-renet.yml:199` runs a TRACKED script and
        # merely writes its output to `./private/bin`, which is ignored; flagging that would
        # be noise, and a noisy gate gets silenced. Only the thing being RUN matters, so
        # strip the command keyword and test the token immediately after it.
        exe="$stripped"
        exe="${exe#- }"
        exe="${exe#run: }"
        case "$exe" in
            bash\ * | sh\ * | source\ * | node\ * | python3\ * | tsx\ *) exe="${exe#* }" ;;
            npx\ *)
                exe="${exe#npx }"
                exe="${exe#* }"
                ;;
            npm\ *) continue ;; # an npm key, resolved by package.json, not a path
        esac
        exe="${exe%% *}"
        printf '%s' "$exe" | grep -qE "^\.?/?($pat)/" || continue

        printf '  %s:%s executes a gitignored path\n    %s\n' "${f#"$root"/}" "$n" "$stripped"
        hits=$((hits + 1))
    done < <(grep -rnE "$pat" \
        "$root/.github/workflows" "$root/.ci/scripts" \
        --include='*.yml' --include='*.sh' 2>/dev/null | sort)
    return "$hits"
}

# --- controls first. A gate nobody has watched fail is not a gate. -------------------
CTL=$(mktemp -d)
trap 'rm -rf "$CTL"' EXIT
mkdir -p "$CTL/.github/workflows" "$CTL/.ci/scripts" "$CTL/ignoredir"
git -C "$CTL" init -q 2>/dev/null
printf 'ignoredir/\n' >"$CTL/.gitignore"
: >"$CTL/ignoredir/thing.sh"

printf '%s\n' 'jobs:' '  x:' '    steps:' \
    '      # ignoredir/thing.sh is explained here, which is PROSE' \
    '      - run: bash ignoredir/thing.sh' >"$CTL/.github/workflows/w.yml"
printf '%s\n' '#!/usr/bin/env bash' \
    '# see ignoredir/thing.sh for why' \
    'bash ignoredir/thing.sh' >"$CTL/.ci/scripts/s.sh"

# ONE scan, capturing BOTH the output and the status. This used to be two calls
# -- an `if scan ... >/dev/null` for the status, then `found=$(scan ... || true)`
# for the text -- and the second discarded the status and stderr, which
# gate-test:swallowed-failures flags: a scan that DIED produces the same empty
# value as a scan that found nothing, and the control would then pass for the
# wrong reason. Here the non-zero IS the expected answer, so it is captured and
# asserted rather than swallowed.
scan_rc=0
found=$(scan "$CTL") || scan_rc=$?
if [ "$scan_rc" -eq 0 ]; then
    echo "CONTROL FAILED: an executed ignored path was NOT reported." >&2
    exit 1
fi
if [ "$(printf '%s' "$found" | grep -c 'executes a gitignored path')" -ne 2 ]; then
    echo "CONTROL FAILED: expected exactly 2 findings (one per surface), got:" >&2
    printf '%s\n' "$found" >&2
    exit 1
fi
if printf '%s' "$found" | grep -q '# '; then
    echo "CONTROL FAILED: a COMMENT was reported as execution." >&2
    exit 1
fi
echo "  PASS  control: an executed ignored path is reported, on both surfaces"
echo "  PASS  control: a comment naming the same path is NOT reported"

# --- the real tree ------------------------------------------------------------------
if out=$(scan "$ROOT"); then
    echo "✓ Nothing CI executes reaches into a gitignored path."
    exit 0
fi
echo "✗ CI would execute a path git does not track:" >&2
printf '%s\n' "$out" >&2
cat >&2 <<'MSG'

A runner checks out tracked files only, so that step runs against a file that is not
there. Move the check into the repo that owns the code and run it from that repo's own
hooks, the way private/growth/.ci/checks/ does, or vendor the file into console.

Naming such a path in a COMMENT or an error message is fine and this gate ignores it.
MSG
exit 1
