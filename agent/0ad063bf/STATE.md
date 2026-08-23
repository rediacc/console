## SESSION 0ad063bf 2026-08-23T16:18:27Z

## Where things stand

**The git-history rewrite is LIVE and VERIFIED on origin.** The wave is complete
and entirely uncommitted. Three items wait on the operator; one is with a
teammate.

## The rewrite landed

    main   b75c44d581 -> 4674ddd666   (forced, 7 branches pruned, 20 tags)
    size   5.64 GiB -> 182 MiB pack; a fresh blobless clone is 49 MB in 10.08 s

**The control that makes it mean something:** a fresh blobless clone of the
rewritten remote yields `HEAD^{tree}` = `444e9c09092a80bbb7defa6eea122e0de28a89eb`,
byte-identical to what GitHub served before. Ruleset `12344707` was never
disabled - it carries an admin bypass and GitHub reported
`Bypassed rule violations`, so the one unbounded-risk step never happened.

Issue #532 CLOSED. v1.2.27 R2 orphan scrubbed. Both writer agents finished with
their gates green: `test-hooks.sh` PASS=1175 FAIL=0 (includes
`test-worklist-v5.sh` 781 cases), plus `test-dispatch-release.sh` and the new
`test-housekeeping-phases.sh`, which I re-ran MYSELF rather than trusting the
report.

## Irreplaceable artifacts, all outside /tmp - DO NOT DELETE

- `~/console-prerewrite-mirror.git` (5.7G) - the complete rollback path until
  GitHub's gc runs, and the last copy of the old history afterwards.
- `~/console-public-media-salvage.tar` (22M, 138 files) - existed nowhere else.
- `~/commit-map-20260823.txt` (6178 lines) - translates any pre-rewrite SHA.

## THE ONE COMMAND the operator must run, from ~/monorepo/console

    git diff HEAD > ~/wave-0ad063bf.patch && \
    git ls-files --others --exclude-standard -z | tar --null -czf ~/wave-0ad063bf-untracked.tgz -T - && \
    git clone --filter=blob:none --recurse-submodules https://github.com/rediacc/console.git ~/console && \
    cd ~/console && \
    git apply ~/wave-0ad063bf.patch && \
    tar -xzf ~/wave-0ad063bf-untracked.tgz && \
    git remote add gitlab https://gitlab.rediacc.io/rediacc-org/github/console.git && \
    echo "OK: $(git status --short | wc -l) files carried" && git status --short

PROVEN, not assumed: `git apply --check` against a fresh clone of the rewritten
remote returns exit 0 over 22 files / 1782 lines. It applies because the rewrite
left the tree byte-identical. The bundle deliberately carries a PEER session's
`agent/a68f3ab4/EXPLORE-home.md` - `.claude/agents/pr-babysitter.md:95` is
explicit that ALL means all and an ownership note does not carve files out of a
snapshot. This checkout can never push again; do not push from it.

## Next action

1. `#80c0dcef` - leased to `phase3-release`: the `cat-file -e` fix at
   `.ci/scripts/release/resolve-backfill-commit.sh:60`. I had deferred it and
   REVERSED that: my reason was "adjacent to something risky", which the
   fix-in-session rule names specifically as not a door, and the agent had
   already built the three fixtures.
2. `#0ac15b7d` `[?]` idle-hook build - operator approved it for this wave and
   said "start when I come back". It edits the Stop hook's own liveness path and
   adds a BLOCKING rung, so a wrong verdict pins a session with no way out.
3. `#5d3c4ca0` `[?]` the checkout move above, then `/pr-babysit` (in-session is
   the default since 2026-08-05) produces the PRs.
4. `#ebe8b570` `[?]` gitlab mirror - operator said "later, not now".
