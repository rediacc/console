# Deleted branch tips, 2026-07-30

Recorded BEFORE deletion so every branch stays recoverable by SHA
(`git branch <name> <sha>`) until git gc prunes unreachable objects.

WHY THIS FILE EXISTS. The obvious safety test is wrong here, and it stays
wrong. At the time of this cleanup the repos SQUASH-merged, so a merged
branch kept no ancestry link to main and `git branch --merged` reported it
as unmerged: that test called all 75 console branches unsafe when 59 had
merged PRs. The authoritative signal is the PR state.

This did NOT stop being true when the repos moved to REBASE-only merging on
2026-07-30. Rebase replays each commit onto main under a NEW sha, so a
merged branch still shares no commit with main and `--merged` still lies.
Only a true merge commit would have preserved ancestry, and that option was
considered and declined.

So the rule is permanent: **to decide whether a branch is merged, ask the
PR, never git ancestry.**

    gh pr list --repo <owner>/<repo> --state merged --limit 300 \
      --json headRefName --jq '.[].headRefName'

`delete_branch_on_merge` is now true on all five repos, which should stop
this backlog rebuilding. It was false on renet, account and homebrew-tap,
and that is exactly why those three accumulated stale remote branches while
console and elite stayed tidy.

## console, local branches (64)

| branch | tip | basis |
|---|---|---|
| `0208-1` | `77caebfdd` | PR merged; content in main |
| `0215-1` | `2a626e418` | PR merged; content in main |
| `0221-1` | `ec954aaa4` | PR merged; content in main |
| `0223-1` | `3a1aaa9e0` | PR merged; content in main |
| `0227-1` | `6162e5fbd` | PR merged; content in main |
| `0323-1` | `de37e5db3` | PR merged; content in main |
| `0329-1` | `3913c08fa` | PR merged; content in main |
| `0335-1` | `09dc65277` | PR merged; content in main |
| `0402-1` | `891b7c840` | PR merged; content in main |
| `0404-2` | `7880baf90` | PR merged; content in main |
| `0408-2` | `f7f6cb4ad` | PR merged; content in main |
| `0410-1` | `359624db7` | PR merged; content in main |
| `0415-1` | `8305e9fe1` | PR merged; content in main |
| `0420-1` | `4cf5267c9` | PR merged; content in main |
| `0421-1` | `3c2168be8` | PR merged; content in main |
| `0422-versioning` | `21f174de4` | PR merged; content in main |
| `0423-1` | `08b855932` | PR merged; content in main |
| `0423-cleanup-monolithic-db-refs` | `14fd5452e` | PR merged; content in main |
| `0423-deploy-edge-tolerant` | `e78f401c8` | PR merged; content in main |
| `0423-drop-config-bucket` | `e7cbd865f` | PR merged; content in main |
| `0423-marketing-drop-account-api` | `b367b751f` | PR merged; content in main |
| `0423-smoke-footer-astro-comments` | `a8993dd2f` | PR merged; content in main |
| `0425-1` | `6a630a365` | PR merged; content in main |
| `0426-1` | `75b45e715` | PR merged; content in main |
| `0426-fork-of-running-and-template-ownership` | `f96a62f33` | PR merged; content in main |
| `0428-1` | `d35d36f57` | PR merged; content in main |
| `0429-1` | `32755f660` | PR merged; content in main |
| `0503-1` | `642742b03` | PR merged; content in main |
| `0503-2` | `8246098cf` | PR merged; content in main |
| `0505-1` | `a7a34f5bf` | PR merged; content in main |
| `0509-1` | `9b617478f` | PR merged; content in main |
| `0511-1` | `11af19a8a` | PR merged; content in main |
| `0511-2` | `face50904` | PR merged; content in main |
| `0525-1` | `d34a281d9` | PR merged; content in main |
| `0529-repodiff-fixes` | `2acd234b1` | PR merged; content in main |
| `0530-1` | `4ee42f0dd` | PR merged; content in main |
| `0610-3` | `d422687ce` | PR merged; content in main |
| `0610-5` | `e358f9f28` | PR merged; content in main |
| `0614-1` | `f944116e3` | PR merged; content in main |
| `0624-1` | `293547217` | PR merged; content in main |
| `0704-2` | `17af2bf0b` | PR merged; content in main |
| `0707-1` | `1c39c43e0` | PR merged; content in main |
| `0718-1` | `eb269c1c1` | PR merged; content in main |
| `0719-1` | `428fb6ac8` | PR merged; content in main |
| `0721-1` | `554312607` | PR merged; content in main |
| `0721-2` | `cb828bfb1` | PR merged; content in main |
| `0722-1` | `0ad77405c` | PR merged; content in main |
| `0726-1` | `da4d2ba46` | PR merged; content in main |
| `0727-1` | `2ae83d874` | PR merged; content in main |
| `0727-2` | `9b9bbe272` | PR merged; content in main |
| `0728-1` | `3e1b6240c` | zero commits outside 0728-2 |
| `0728-2-stale-20260729` | `0e1aa2f44` | zero commits outside 0728-2 |
| `backup/old-local-main` | `bcf0d3a42` | operator-approved; commits exist nowhere else |
| `backup/pre-rebase-pile` | `3392befc3` | operator-approved; commits exist nowhere else |
| `backup/pre-rebase-state` | `378e5af38` | operator-approved; commits exist nowhere else |
| `chore/upgrade-major-deps` | `aeb2bc9a9` | PR merged; content in main |
| `ci/quality-green-20260219` | `8be9cc7af` | PR merged; content in main |
| `feat/devcontainer-desktop` | `569939459` | PR merged; content in main |
| `feat/sentinel-release-contract` | `a91788342` | PR merged; content in main |
| `fix/consolidate-review-gate` | `14ad2764a` | PR merged; content in main |
| `fix/seo-audit-youtube-embed` | `ac0dba1c8` | PR merged; content in main |
| `fix/sql-ha-flaky-and-submodule` | `c98f281d7` | PR merged; content in main |
| `fix/update-apply-race` | `8446bf49e` | PR merged; content in main |
| `refactor/unified-staging-pipeline` | `e4bd521f8` | PR merged; content in main |

## submodule REMOTE branches (GitHub), PR-merged only

| repo | branch | tip | PR |
|---|---|---|---|
| renet | `0624-1` | `813e435` | #84 |
| renet | `0703-2` | `aa8c2b5` | #86 |
| renet | `0704-1` | `3ae3208` | #87 |
| renet | `0704-2` | `5cab62d` | #88 |
| renet | `0707-1` | `3cf6c05` | #89 |
| renet | `0718-1` | `73919c8` | #90 |
| renet | `0719-1` | `1670db5` | #91 |
| renet | `0721-1` | `00d014a` | #92 |
| renet | `0721-2` | `bd2ffcd` | #93 |
| renet | `0722-1` | `d9e8e82` | #94 |
| renet | `0728-2` | `761d9bf` | #95 |
| account | `0624-1` | `cbdcfaf` | #52 |
| account | `0704-1` | `cc68776` | #55 |
| account | `0704-2` | `c146e69` | #56 |
| account | `0707-1` | `a0adf57` | #62 |
| account | `0718-1` | `a47c505` | #63 |
| account | `0719-1` | `d3e286a` | #64 |
| account | `0722-1` | `ddcdf0c` | #66 |
| account | `0722-2` | `bf8f745` | #67 |
| account | `0727-1` | `b9a6d70` | #68 |
| account | `0727-2` | `b0ea51f` | #69 |
