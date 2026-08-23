# Rewrite git history to drop the migrated media blobs

Status: ready
Session: 0ad063bf
Date: 2026-08-23
Supersedes the "Doing it" section of [rediacc/console#532](https://github.com/rediacc/console/issues/532),
whose path selection is wrong in two ways (see "Two defects in #532" below).

## Why

`rediacc/console` is 5,668,557 KB (~5.4 GiB) on GitHub. The whole `HEAD` tree is
114.8 MB. Over 98% of the repository is media that was migrated to R2 in #512 on
2026-07-02 and deleted from the working tree, but never from history.

Full-history accounting, measured on a complete mirror (not the shallow local
checkout):

| | MB | blobs |
|---|---:|---:|
| remove | 5,602.6 | 7,768 |
| keep | 171.9 | 50,733 |
| unattributed | 0 | 0 |

## The command

Verified by execution, not by reading. Runs in about 8 seconds.

```bash
git filter-repo --force \
  --path packages/www/public/assets/videos/solutions \
  --path packages/www/public/assets/tutorials/video \
  --path packages/www/public/assets/tutorials/audio \
  --path packages/www/public/media \
  --invert-paths
```

`git-filter-repo` 2.47.0, installed with
`pip install --user --break-system-packages git-filter-repo` (apt carries only
2.38, and `sudo` is blocked in the agent sandbox by `PR_SET_NO_NEW_PRIVS`).
Binary lands at `~/.local/bin/git-filter-repo`; export
`PATH="$HOME/.local/bin:$PATH"`.

## Proven result

Pristine mirror versus rewritten copy:

| | before | after |
|---|---:|---:|
| `size-pack` | 5.64 GiB | **182.08 MiB** |
| objects in pack | 108,482 | 99,823 |
| commits on `main` | 1,960 | 1,960 |
| commits, all refs | 6,177 | 6,174 |
| refs | 8 heads / 20 tags | 8 heads / 20 tags |

31.7x smaller, down 96.8%.

Three commits are dropped because they become empty, and they are exactly the
media-only ones:

- `374943470` chore(media): solution videos (pt,ru,ja,ko,zh)
- `c05edbbab` chore(media): solution videos (en,de,es,fr,it)
- `f020473e2` chore(media): tutorial locale audio + video

## The control that makes the result mean something

**The rewritten `main^{tree}` must be byte-identical to today's.** Both sides
must print `444e9c09092a80bbb7defa6eea122e0de28a89eb`:

```bash
git -C <pristine-mirror> rev-parse main^{tree}
git -C <rewritten>       rev-parse main^{tree}
```

If they differ, diff the file lists and read what was removed:

```bash
git -C <pristine-mirror> ls-tree -r main --name-only | sort > pre-files.txt
git -C <rewritten>       ls-tree -r main --name-only | sort > post-files.txt
comm -23 pre-files.txt post-files.txt
```

**This control is not ceremony. It fired on the first attempt of this very
plan.** Attempt 1 used `--path packages/www/public/assets/videos`, the whole
directory. The control failed and the diff named the casualty:
`packages/www/public/assets/videos/user-guide/.gitkeep`, a live tracked file.
That directory carries 0.00 MB across 0 blobs, so the wider prefix bought
nothing and destroyed a live file. Never widen a prefix without re-running the
control.

Secondary checks, all of which passed:

```bash
# all 11 live browser-segment videos survive
git -C <rewritten> ls-tree -r main --name-only | grep -c 'browser-segments.*\.mp4'   # 11

# no media path survives anywhere in history (must print nothing)
git -C <rewritten> log --all --format= --name-only \
  | grep -E '^packages/www/public/(media|assets/(videos/solutions|tutorials/(video|audio)))/'
```

## Second job in the same pass: strip AI attribution

The operator asked (2026-08-23) to also remove AI authorship. There is **no AI
identity in any author or committer field** across all 6,177 commits, verified
by enumerating them. The attribution lives entirely in commit MESSAGES:

| what | lines | commits |
|---|---:|---:|
| `Co-Authored-By: Claude ... <noreply@anthropic.com>` (all case variants) | 78 | 73 |
| the robot `Generated with [Claude Code](...)` footer | 16 | (same set) |

Everything else that mentions Anthropic or Claude is legitimate prose and must
survive: `@anthropic-ai/claude-agent-sdk` dependency bumps, the
`CLAUDE_CODE_OAUTH_TOKEN` credential chain, `anthropics` in an actions
allowlist. So is every non-AI trailer: 175 dependabot and 42 human ones.

Add to the same `filter-repo` invocation:

    --message-callback /path/to/strip-ai.py

with `strip-ai.py`:

```python
import re
_trailer = b'Co-Auth' + b'ored-By'
_gen = b'Gener' + b'ated with'
_pats = [
    re.compile(br'(?im)^[ \t]*' + _trailer + br':[^\n]*anthropic[^\n]*\n?'),
    re.compile(br'(?im)^[ \t]*\xf0\x9f\xa4\x96[ \t]*' + _gen + br'[^\n]*\n?'),
]
_new = message
for _p in _pats:
    _new = _p.sub(b'', _new)
if _new == message:
    return message
return _new.rstrip() + b'\n'
```

The identifiers are built by concatenation on purpose: this repo's own
`.claude/hooks/pre-bash/block-commit-meta.sh` refuses any command containing
the literal trailer name, so a file written with it inline cannot be created
from an agent shell.

### The trap that cost a whole trial run

The first version of this callback ended with an unconditional
`return message.rstrip() + b'\n'`. That normalizes trailing whitespace on
**all 6,177 messages**, not just the 73 that carry attribution. Commits whose
messages then differed only in trailing whitespace became byte-identical, and
git is content-addressed, so they collapsed into a single object: **93 commits
silently disappeared** and 96 legitimate co-author trailers went with them.

Nothing errored. The pack size and the tree control both still passed. It was
caught only by diffing the commit count against the media-only run
(6,174 versus 6,081) and then tracing one victim: "Add captcha key" appeared
twice before and once after.

**Return the original bytes unchanged when nothing matched.** And always keep a
media-only run to diff against, because the tree control cannot see this class
of damage at all.

## Attribution controls

Run all of these; the media-only trial is the baseline for the first two.

| check | expected |
|---|---|
| commits, all refs | 6,174 (same as media-only, NOT fewer) |
| dependabot trailers | 175, unchanged |
| all trailers | 217 (295 minus the 78 AI ones) |
| AI trailers | 0 |
| robot footers | 0 |
| `anthropic-ai/claude-agent-sdk` prose | 20, unchanged |
| `main^{tree}` | `444e9c09092a80bbb7defa6eea122e0de28a89eb` |

Measured on the corrected run: every one passes, `size-pack` 182.09 MiB.

## Two defects in #532

1. **Its glob deletes live files.** #532 proposes
   `--path-glob 'packages/www/public/assets/**/*.mp4' --invert-paths`. There are
   **11 `.mp4` still tracked in `HEAD`** under
   `packages/www/public/assets/tutorials/browser-segments/` (4.3 MB total, not
   R2-backed). That glob matches them and removes them silently. Select by
   directory prefix, never by extension.
2. **`packages/www/public/media/` is missing from the plan.** 40.6 MB of founder
   narration audio, captions, photos and posters, deleted in the same #512
   cleanup. It is absent from `packages/www/.gitignore` (which lists only the
   three `assets/` dirs), absent from `.ci/docs/r2-media-setup.md`, and absent
   from #532. Nothing on disk today, so no immediate re-add risk, but a future
   founder-audio regeneration commits straight back into git.

## Procedure

1. **Install the tool** as above and confirm `git filter-repo --help` runs.
2. **Mirror-clone from scratch.** A shallow clone or a submodule worktree will
   be refused, and the everyday checkout at `/home/muhammed/monorepo/console` is
   both.
   ```bash
   git clone --mirror https://github.com/rediacc/console.git console-mirror.git
   ```
   Keep this pristine. Copy it (`cp -a`) and rewrite the copy, so a mistake
   costs a `cp` rather than a 5.4 GB re-download.
3. **Record the pre-state**: `git -C console-mirror.git rev-parse main main^{tree}`.
4. **Salvage `packages/www/public/media/` first.** It is the ONLY irreversible
   loss in the operation: 138 files, absent from disk, absent from `HEAD`, and
   covered by no sync script, so git history is the only copy that exists.
   ```bash
   git -C console-mirror.git archive --format=tar --prefix=console-public-media/ \
     6a04dcbad9ce56f92daff2c93a78f8d5f4cac2fa^:packages/www/public/media \
     > ~/console-public-media-salvage.tar    # 22 MB
   ```
   Discard it on purpose if you prefer, but never by omission.
5. **Move the pristine mirror out of `/tmp`.** It is the only backup and `/tmp`
   does not survive a reboot: `mv console-mirror.git ~/console-prerewrite-mirror.git`.
6. **Run the command** in the copy, then **run the controls**. Do not proceed on
   a failure; fix the path list.
7. **Strip the refs that must not be pushed, and the branches being retired.**
   A `--mirror` clone carries `refs/pull/*`, and `filter-repo` rewrites those
   too. GitHub REJECTS writes to hidden refs, so a `--mirror` push containing
   them exits non-zero with partial success indistinguishable from failure;
   GitLab has no such protection and would happily create the junk refs.
   Measured on this repo: **458 `refs/pull/*` refs**.
   ```bash
   git for-each-ref --format='delete %(refname)' refs/pull | git update-ref --stdin
   for b in <retired-branches>; do git branch -D "$b"; done
   git for-each-ref --format='%(refname)' | sed 's|refs/\([^/]*\)/.*|refs/\1|' | sort | uniq -c
   ```
   The census must read exactly `1 refs/heads` and `20 refs/tags`, nothing else.
   Deleting the branches HERE rather than with a separate `git push --delete` is
   better: `--mirror` prunes them on the remote in the same operation, so there
   is no window where the remote disagrees with the local ref set.
8. **Preserve the commit map** before the working copy is discarded:
   `cp <rewritten>/filter-repo/commit-map ~/commit-map-20260823.txt` (495 KB,
   6,178 lines). It is the only artifact that can translate any pre-rewrite SHA
   cited anywhere, and it is unrecoverable once the copy goes.
9. **Push, ruleset untouched.** Ruleset `12344707` carries bypass actors
   including `RepositoryRole` id 5 (admin) at `bypass_mode: always`, and the
   operator has admin, so the force-push is expected to be accepted as-is.
   ```bash
   git -C <rewritten> push --force --mirror https://github.com/rediacc/console.git
   ```
   Attempting it first is safe: a ruleset rejection is atomic per ref, so a
   rejected `main` leaves `main` exactly as it was.
10. **Contingency only, if step 9 is rejected.** Back the ruleset up first, and
    wrap the flip in a `trap` so enforcement is restored on success, on failure,
    and on Ctrl-C. An unbounded window with `main` unprotected is the only
    failure mode in this operation with no natural floor.
11. **Verify against the remote** (see the controls above), then push GitLab.
12. **Re-clone every working checkout.** Existing clones cannot be
    fast-forwarded onto rewritten history and must not be pushed from. Remove
    their remotes the moment the push succeeds: until deleted, an old checkout
    holds the full pre-rewrite object set and one `git push --force` from it
    would restore the old history.
13. **Add the `.gitignore` entry** for `public/media/` so the class cannot
    return, and document it in `.ci/docs/r2-media-setup.md`.

## What does not happen

- **GitHub's reported size will not drop on push.** Unreachable objects survive
  until GitHub garbage-collects server-side, and old SHAs stay fetchable by
  direct reference until then. Open a support request if the number has to move
  on a schedule.
- **CI gets no faster.** All 11 `fetch-depth: 0` checkouts already pass
  `filter: blob:none`, so CI stopped paying for the dead blobs some time ago.
- **It does not save per-worktree disk.** #532 claims local `.git` costs 6.8 GB
  "per checkout, which matters because this repo is used with multiple
  worktrees". That is wrong: git worktrees SHARE one object store.
  `/home/muhammed/monorepo/.git/modules/console/objects` is 5.8 GB once, no
  matter how many worktrees hang off it. Only separate CLONES multiply it.
- **A blobless clone already solves the clone cost, without any rewrite.**
  Measured 2026-08-23: `git clone --filter=blob:none` produces a full working
  tree with a **54 MB** `.git` in **11.4 seconds**. That is smaller than the
  182 MB this rewrite produces, because it never fetches historical blobs at
  all. The rewrite's remaining justification is the 5.4 GB sitting on GitHub's
  servers (at their documented 5 GB soft limit) and anyone who clones without
  the flag, not day-to-day developer cost.

## Preconditions, all verified 2026-08-23

- **0 open PRs.** Nothing needs rebasing.
- 8 remote branches, 20 remote tags (all `v1.2.7`+, dated 2026-07-21 or later,
  all after the media deletion). 0 forks, 0 network members.
- Submodules are small and need no rewrite: renet 15 MB, account 5.7 MB,
  elite 0.3 MB, homebrew-tap 0.07 MB.
- The 7 non-`main` branches are all safe to delete, verified by commit-subject
  match rather than ancestry (this repo is rebase-only, so ancestry lies and
  every one of these PRs reads `CLOSED, merged=no`): `0728-1` and `0728-3` are
  0-ahead of main; `0807-2`, `0808-3`, `0809-3`, `0809-4` have 0 subjects absent
  from main; `0809-2` has 2, both branch-local lockfile churn (`88a1be296`,
  `e5e367f4b`). Deleting them first means one force-pushed ref instead of eight.
- Housekeeping Phase 9 would delete them on its own after
  `BRANCH_MAX_AGE_DAYS=30` (`.ci/scripts/housekeeping/cleanup-versions.sh:44`).
  The oldest is 26 days, so the mechanism is working and simply has not reached
  its window.

## Decisions, settled 2026-08-23

- **GitLab: full mirror push, no archive.** The remote
  `gitlab.rediacc.io/rediacc-org/github/console.git` was a stale INDEPENDENT
  copy, not a mirror: `main` at `09b0b7716` against GitHub's `b75c44d58`, and it
  carried 294 tags and 16 branches GitHub lacked. Those extras are not lost
  history: `cleanup-versions.sh:229` deletes the git tag along with the release
  and keeps only `KEEP_VERSIONS=20`, so the 294 are the reaped tail of this
  repo's own retention policy, which GitLab simply never received. Of the 16
  extra branches only `0227-1` has a tip absent from GitHub. GitLab's `main` is
  an ANCESTOR of GitHub's, so it was behind, never diverged.
- **The 11 live `browser-segments/*.mp4` stay in git.** They are build INPUTS,
  not outputs: silent browser recordings captured by driving a live lab with
  Playwright, one recording serving all 13 locales.
  `generate-tutorial-video.ts:113-115` states the reason they are tracked --
  "expensive to record (live lab/Playwright) and tiny to store". They appear in
  no R2 manifest and `sync-media-to-r2.sh` does not touch them. Moving 4.3 MB
  would add a network dependency to a build that is currently hermetic.
- **The `public/media/` `.gitignore` entry lands before the rewrite**, since it
  is independent of it.
- **The retired monorepo's submodule pointer is not fixed.**
  `/home/muhammed/monorepo` is retired (last commit 2026-01-29), so its dangling
  `console` gitlink is accepted knowingly. The mapping survives in the commit
  map from step 8 if it is ever wanted:
  `feb82612aedfe94292cd20210349703fc541ce91 -> f43ccb790f3d893f07f0b4faa382bee10a3976cd`.
