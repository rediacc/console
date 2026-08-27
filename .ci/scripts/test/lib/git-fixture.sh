#!/usr/bin/env bash
# Build throwaway git repos that halt a rebase on a CHOSEN kind of conflict.
#
# WHY THIS EXISTS. agent/PLAN-resumable-rebase-executor.md's step 2 needs
# controls that drive a REAL rebase, and this repo had no git fixture harness at
# all -- which is why `wl_git.py`'s conflict work could only ever be tested as
# pure functions over hand-written stage tables. A pure-function control proves
# the classifier's ARITHMETIC; only a real halt proves it reads what git
# actually writes into .git/rebase-merge and the index.
#
# The three kinds are not invented. They are the taxonomy measured across two
# real rebases of branch 0826-3 on 2026-08-26/27, where ten conflicts split one
# gitlink / six registry unions / two genuine judgement calls.
#
# EVERY FIXTURE IS SELF-CONTAINED AND DISPOSABLE: its own mktemp dir, its own
# git identity, no reach into the caller's repo and no network. The submodule
# kind uses a LOCAL path with protocol.file.allow, so nothing clones.
#
# Usage:
#   source .ci/scripts/test/lib/git-fixture.sh
#   dir="$(git_fixture_rebase registry)"   # or: judgement | gitlink
#   ...drive `git -C "$dir" rebase main` and inspect the halt...
#   git_fixture_cleanup "$dir"

# git_fixture_rebase <kind> -> prints the repo path, already HALTED mid-rebase
#
# The caller gets a repo whose `feature` branch is mid-rebase onto `main` with
# the requested conflict unresolved. Returns non-zero if the rebase did NOT
# halt, because a fixture that silently applied cleanly would make every
# assertion below it vacuous.
git_fixture_rebase() {
    local kind="${1:?kind required: registry|judgement|gitlink}"
    local root
    root="$(mktemp -d)" || return 1
    local r="$root/r"

    git init -q -b main "$r" || return 1
    git -C "$r" config user.email fixture@example.invalid
    git -C "$r" config user.name 'git-fixture'

    case "$kind" in
        gitlink)
            local sub="$root/sub"
            git init -q -b main "$sub"
            git -C "$sub" config user.email fixture@example.invalid
            git -C "$sub" config user.name 'git-fixture'
            echo base >"$sub/f.txt"
            git -C "$sub" add -- f.txt
            git -C "$sub" commit -qm base
            git -C "$r" -c protocol.file.allow=always submodule add -q "$sub" sub >/dev/null 2>&1
            git -C "$r" add -- .gitmodules sub
            git -C "$r" commit -qm base
            # THE TWO SUBMODULE COMMITS MUST DIVERGE, and the first draft of this
            # fixture got it wrong in a way worth recording: both were made on
            # sub's main, so `theirs` DESCENDED from `mine`, git took the
            # descendant, and the rebase applied cleanly. The anti-vacuity check
            # below caught it -- a fixture that does not halt proves nothing.
            #
            # So each side gets its own branch off the SAME base, which is what
            # a real diverged gitlink looks like: neither an ancestor of the
            # other, exactly the case resolve_gitlink_target refuses to guess.
            git -C "$r" checkout -qb feature
            git -C "$r/sub" checkout -qb feature-side
            (cd "$r/sub" && echo mine >f.txt && git commit -qam mine)
            git -C "$r" add -- sub && git -C "$r" commit -qm 'feature moves the pointer'
            git -C "$r" checkout -q main
            git -C "$r/sub" checkout -q main
            (cd "$r/sub" && echo theirs >f.txt && git commit -qam theirs)
            git -C "$r" add -- sub && git -C "$r" commit -qm 'main moves the pointer'
            ;;
        gitlink-rebased)
            # THE RESOLVABLE CASE, and the one that actually occurs. `gitlink`
            # above models genuine divergence, which resolve_gitlink_target
            # REFUSES by design. The real flow rebases the submodule FIRST, so
            # its HEAD contains both sides and is in NEITHER conflict stage --
            # which is the insight that whole oracle is built on. Without this
            # fixture the only gitlink control proves the refusal and never the
            # resolution.
            local sub2="$root/sub"
            git init -q -b main "$sub2"
            git -C "$sub2" config user.email fixture@example.invalid
            git -C "$sub2" config user.name 'git-fixture'
            echo base >"$sub2/f.txt"
            git -C "$sub2" add -- f.txt
            git -C "$sub2" commit -qm base
            git -C "$r" -c protocol.file.allow=always submodule add -q "$sub2" sub >/dev/null 2>&1
            git -C "$r" add -- .gitmodules sub
            git -C "$r" commit -qm base
            # DIFFERENT FILES per side, deliberately: the submodule's OWN rebase
            # has to SUCCEED here. The first draft had both sides editing f.txt,
            # so the sub rebase conflicted too, silently did nothing under
            # `|| true`, and the fixture produced the diverged case again --
            # indistinguishable from the `gitlink` kind it exists to contrast.
            git -C "$r" checkout -qb feature
            git -C "$r/sub" checkout -qb feature-side
            (cd "$r/sub" && echo mine >mine.txt && git add -- mine.txt && git commit -qm mine)
            git -C "$r" add -- sub && git -C "$r" commit -qm 'feature moves the pointer'
            git -C "$r" checkout -q main
            git -C "$r/sub" checkout -q main
            (cd "$r/sub" && echo theirs >theirs.txt && git add -- theirs.txt && git commit -qm theirs)
            git -C "$r" add -- sub && git -C "$r" commit -qm 'main moves the pointer'
            # Rebase the submodule onto its own main, exactly as branch-rebase
            # step 2 does. Its tip then contains BOTH sides and is in neither
            # conflict stage, which is the case the oracle is built for.
            git -C "$r/sub" checkout -q feature-side
            git -C "$r/sub" rebase main >/dev/null 2>&1 ||
                {
                    echo "git_fixture_rebase: sub rebase must succeed for this kind" >&2
                    rm -rf "$root"
                    return 4
                }
            ;;
        mixed)
            # A gitlink AND a file conflict in one halt. This is what the
            # all-or-nothing guard exists for: resolving only the gitlink leaves
            # a half-resolved index that reads as nearly done, and the next
            # --continue then fails for a reason that no longer names the
            # submodule. Hand-crafting an unmerged index entry to fake this was
            # tried first and produced "cache entry has null sha1"; a real
            # fixture is both easier and honest.
            local sub3="$root/sub"
            git init -q -b main "$sub3"
            git -C "$sub3" config user.email fixture@example.invalid
            git -C "$sub3" config user.name 'git-fixture'
            echo base >"$sub3/f.txt"
            git -C "$sub3" add -- f.txt && git -C "$sub3" commit -qm base
            git -C "$r" -c protocol.file.allow=always submodule add -q "$sub3" sub >/dev/null 2>&1
            printf 'shared\n' >"$r/code.sh"
            git -C "$r" add -- .gitmodules sub code.sh && git -C "$r" commit -qm base
            git -C "$r" checkout -qb feature
            git -C "$r/sub" checkout -qb feature-side
            (cd "$r/sub" && echo mine >mine.txt && git add -- mine.txt && git commit -qm mine)
            printf 'shared\nmine\n' >"$r/code.sh"
            git -C "$r" add -- sub code.sh && git -C "$r" commit -qm 'feature: pointer and code'
            git -C "$r" checkout -q main
            git -C "$r/sub" checkout -q main
            (cd "$r/sub" && echo theirs >theirs.txt && git add -- theirs.txt && git commit -qm theirs)
            printf 'shared\ntheirs\n' >"$r/code.sh"
            git -C "$r" add -- sub code.sh && git -C "$r" commit -qm 'main: pointer and code'
            git -C "$r/sub" checkout -q feature-side
            git -C "$r/sub" rebase main >/dev/null 2>&1 || true
            ;;
        registry)
            printf '{"entries":[{"id":"a"}]}\n' >"$r/reg.json"
            git -C "$r" add -- reg.json
            git -C "$r" commit -qm base
            git -C "$r" checkout -qb feature
            printf '{"entries":[{"id":"a"},{"id":"mine"}]}\n' >"$r/reg.json"
            git -C "$r" add -- reg.json && git -C "$r" commit -qm 'feature adds an entry'
            git -C "$r" checkout -q main
            printf '{"entries":[{"id":"a"},{"id":"theirs"}]}\n' >"$r/reg.json"
            git -C "$r" add -- reg.json && git -C "$r" commit -qm 'main adds an entry'
            ;;
        judgement)
            printf 'shared\n' >"$r/code.sh"
            git -C "$r" add -- code.sh
            git -C "$r" commit -qm base
            git -C "$r" checkout -qb feature
            printf 'shared\nmine\n' >"$r/code.sh"
            git -C "$r" add -- code.sh && git -C "$r" commit -qm 'feature rewrites it'
            git -C "$r" checkout -q main
            printf 'shared\ntheirs\n' >"$r/code.sh"
            git -C "$r" add -- code.sh && git -C "$r" commit -qm 'main rewrites it'
            ;;
        *)
            echo "git_fixture_rebase: unknown kind '$kind'" >&2
            rm -rf "$root"
            return 2
            ;;
    esac

    git -C "$r" checkout -q feature
    if git -C "$r" rebase main >/dev/null 2>&1; then
        # ANTI-VACUITY. A fixture meant to halt that applies cleanly would make
        # every assertion the caller writes below it pass over nothing.
        echo "git_fixture_rebase: '$kind' did NOT halt; the fixture proves nothing" >&2
        rm -rf "$root"
        return 3
    fi
    printf '%s\n' "$r"
}

git_fixture_cleanup() {
    local r="${1:-}"
    # The fixture root is the PARENT of the repo (it also holds the submodule
    # origin), so remove that. Guarded against a caller passing something else.
    case "$r" in
        /tmp/* | /var/folders/*) rm -rf "$(dirname "$r")" ;;
        *)
            echo "git_fixture_cleanup: refusing to remove '$r'" >&2
            return 1
            ;;
    esac
}
