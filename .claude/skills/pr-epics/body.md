# body: the managed block in the PR description

    .ci/scripts/pr/sync-epic-block.sh <pr> <branch>

Reads `agent/pr/<branch>.md` and rebuilds the block between

    <!-- worklist-epics:begin -->
    <!-- worklist-epics:end -->

`scripts/check-pr-epic-block.ts` fails when the block is missing or does not
match the snapshot, so a stale publish is a red gate by design.

## Rebuilt, never appended

The idiom is the one from `.ci/scripts/autopilot/submodule-prs.sh`, exact-line
equality with the markers alone on their own lines:

    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip   { print }

Strip then append. Appending grows a duplicate block on every push instead of
updating one.

## The marker pair must stay distinct

Three writers already append blocks at the end of a body: `refresh-pr-body.sh`'s
`pushed-head`, `submodule-prs.sh`'s `autopilot-submodule-prs`, and humans.
`submodule-prs.sh` warns in its own header that sharing markers with
`refresh-pr-body.sh` is fatal, because that hook rewrites the **whole** body on
every push. So the epic block must tolerate being relocated to the end, and must
never reuse another writer's markers. Human prose between blocks survives all
three; that is part of what the test asserts.

## Item text can break the block

An item whose own text contains `-->` would close the block early and truncate
everything after it in the PR body. This is not hypothetical: the worklist item
for this very feature contains both delimiters, because it describes them.
`wl_epic.neutralize()` inserts a zero-width space into `<!--` and `-->` before
rendering. Do not bypass it, and do not "clean up" the odd-looking replacement.

## Do not hand-edit the block

`.claude/hooks/pre-bash/block-raw-pr-body-edit.sh` refuses a `gh pr edit --body`
that would write the markers directly. Regenerate from the snapshot instead: a
hand-written block is one the gate will diff against the store and reject, and
the round trip is slower than republishing.
