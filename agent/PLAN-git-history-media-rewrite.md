# Rewrite git history to drop the migrated media blobs
Status: compacted
Full-Text-Blob: c7246f5aa5ed63e3e3898248401b4c776021c22d
Record-Sig: 5226f19b

## Why
The repository had 5.6 GiB of media blobs in history (98% of total size) that were migrated to R2 and deleted from the working tree in July, but never removed from git history. This inflated the GitHub repository to 5.4 GiB despite HEAD being only 114.8 MB. Additionally, AI authorship signatures needed to be stripped from 73 commits.

## Outcome
Plan is complete and ready for execution. The exact command, proven result (31.7x smaller, down to 182 MiB), comprehensive control checks, and detailed 13-step procedure are documented. A second `--message-callback` was designed to strip 78 AI trailer lines and 16 robot footers without collapsing commits. All preconditions verified as of 2026-08-23 (0 open PRs, 8 branches, 20
tags). Procedure includes pristine mirror, media salvage before rewrite, commit-map preservation, force-push with ruleset bypass, and re-clone instructions.

## Lessons
- The `main^{tree}` control is load-bearing: it caught attempt 1 where `--path-glob '**/*.mp4'` silently deleted 11 live tracked videos. Always re-run controls when widening path selectors, and prefer directory prefixes over extension globs.
- Message callback must return original bytes unchanged when no pattern matches, not normalize all trailing whitespace. Normalizing all 6,177 commit messages caused 93 commits to silently collapse into duplicates. Always keep a media-only baseline run to diff commit counts against.
- The media-only trial run serves as baseline for ALL attribution checks: commit count (6,174), dependabot trailers (175), tree hash, etc. Secondary checks like `git log --all --format= --name-only` cannot see commit-count damage at all.
- `packages/www/public/media/` (40.6 MB) is the only irreversible loss — absent from disk, absent from `HEAD`, absent from all sync scripts. Salvage it before rewriting: `git archive --format=tar <tree-id>` to preserve the single copy that exists.
- Misconceptions addressed: GitHub's size won't drop on push (unreachable objects survive until server GC), CI gains nothing (blob:none already deployed), per-worktree disk is shared one object store (not multiplied), and blobless clone already solves day-to-day cost (54 MB in 11s vs 182 MiB rewrite).

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: ready
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:11:27Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/scripts/housekeeping/cleanup-versions.sh
Gates: none
Why-Source: model
Read-History: `git show c7246f5aa5ed63e3e3898248401b4c776021c22d` recovers the text; `git log --find-object=c7246f5aa5ed63e3e3898248401b4c776021c22d --all` names the commit

## History
- 2026-09-20T18:11:27Z compacted by d778be9d from `ready` (record-sig 5226f19b)
