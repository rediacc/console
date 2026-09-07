# The retired bash guards, kept as the differential's oracle

These 46 files are NOT hooks. Nothing registers them, nothing runs them as
guards, and `.claude/settings.json` does not name one of them. They are the bash
originals that `.claude/rediacc_hooks/guards/*.py` were ported from, moved here
by the W5 P7 cutover on 2026-09-06 from `.claude/hooks/{pre-bash,pre-edit,pre-ask}/`.

## Why they are kept rather than deleted

`tests/test_guards_differential.py` runs every port and its bash original over
the same 5,844 events and compares the exit code, stdout and stderr byte for
byte. That is 5,844 of the suite's 8,467 cases, and it is the only thing in the
tree that proves a port answers what its twin answered. Deleting the twins in the
change that made the ports live would have retired that proof in the same breath
as the thing it proves, which is the failure the whole cutover was built to
avoid.

The same files also carry the comment archaeology the port is judged against:
`COMMENT_RATIO_FLOOR` compares each port's comment bytes to its original's, and
the `ARCHAEOLOGY` extractor requires every date, issue number and run id in the
original to survive somewhere in the port. Both read these files.

## Why they sit at `.claude/oracles/` and not inside the package

DEPTH, and it was measured rather than reasoned. Roughly a third of these guards
derive the repository root from their OWN location -- `"$(dirname
"${BASH_SOURCE[0]}")/../../.."` -- and say why in as many words:
block-adhoc-sanctioned.sh's header records that using `CLAUDE_PROJECT_DIR`
instead made it fail open in CI, where that variable is unset. A guard three
levels under the root must stay three levels under the root, or it computes a
root that is wrong by exactly one directory and answers differently.

The first cut of this tree put them at `.claude/rediacc_hooks/oracles/`, one
level deeper, and the differential reported 30 divergences across five guards on
the first run: block-inline-python.sh looked for its checker at
`/home/developer/console/.claude/.ci/scripts/quality/`, and
block-agent-browser-repo-output.sh stopped recognising a path inside the repo.
Every one of those was the ORACLE being wrong, not the port. `.claude/oracles/`
restores the depth exactly.

## Why they had to leave `.claude/hooks/`

`.ci/scripts/quality/check_hooks_resolvable.py` asserts that every `block-*.sh`
and `warn-*.sh` under `.claude/hooks/{pre-bash,pre-edit,post-bash}` is named by a
command in `settings.json`, and it is right to: "A guard nobody calls is worse
than no guard: it reads as coverage." After the collapse nothing names them, so
staying there would have been exactly the hazard that gate exists for.

## What may and may not be done to them

They are FROZEN. Do not fix a bug here; fix it in the port and let the
differential report the divergence, which is what it is for. Do not add a file
here that never was a registered guard. The one file that is not an original is
`pre-bash/lib/command-scan.sh`, which forwards to the live library and says so.
