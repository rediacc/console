# PLAN: commits must be attributable to a GitHub account
Status: draft
Owner: 74de73ca
Updated: 2026-09-03

Scope: a local guard that refuses a `git commit` whose author email GitHub does not
link to an account, and a CI gate that refuses a PR containing such a commit.
Designed 2026-09-03 by a Plan agent whose API results were measured, not recalled;
the principal spot-checked the load-bearing ones before writing this.

## 0. The measurement

Two emails, one display name (`Muhammed Fatih Bayraktar`):

| where | `mfbayraktar@live.com` | `muhammed@rediacc.com` | bot |
|---|---|---|---|
| console `main..HEAD` (pre-rewrite) | 11 | 30 | — |
| console `main` (last 30) | 28 | 0 | 2 |
| `private/account` PR #85 | 2 | 7 | — |
| `private/renet` PR #110 | 0 | 2 | — |
| `private/elite` PR #16 | 0 | 1 | — |

`muhammed@rediacc.com` is not linked to the GitHub account, so those commits render
with a bare name, no avatar, no profile link, and no contribution credit.

**The git config is NOT the cause, and that decides the design.** This checkout has no
local `user.email`; `git config --show-origin --get-all user.email` names exactly one
source, `file:/home/developer/.gitconfig mfbayraktar@live.com`, and all four
submodules resolve the same. So the 30 bad commits came from an OVERRIDE at commit
time -- `-c user.email=`, `--author=`, `GIT_AUTHOR_EMAIL`/`EMAIL`, or a different HOME
-- not from a misconfigured machine. A guard that only read `git config` would have
watched all 30 go past. Author and committer moved together (`%ae|%ce` identical on
all 30), so both fields are judged.

## 1. The oracle: GitHub's own per-commit attribution

`gh api repos/{owner}/{repo}/pulls/{n}/commits --paginate` returns, per commit, the
raw header (`.commit.author.email`) AND the account GitHub resolved it to (`.author`,
`null` when unlinked). Measured on rediacc/console#585:

    30  .author = null                 muhammed@rediacc.com
    11  .author.login = mfbayraktar    mfbayraktar@live.com

**The rule is therefore: `.author` and `.committer` must both be non-null** -- not
"the email is in a list". That is the point of using `gh` as the base: the gate asks
the same question GitHub answers on the commit page, so it cannot drift from what the
operator sees, and it needs no edit when an address is linked or retired. Bots pass
for free (`github-actions[bot]` resolves, `type = Bot`), which is why main's two bot
commits need no special case.

### Rejected, with the reason

- **`gh api user/emails`** -- the ideal oracle and NOT AVAILABLE. Measured here it
  returns 404 with gh's own hint that it needs the `user` scope; this token carries
  `admin:org, gist, repo, workflow`. In CI it is worse: `.github/actions/app-token`
  mints an INSTALLATION token with no user identity at all, so it can never work
  there. Using it would tie the oracle to a scope one machine holds.
- **`search/commits?q=…author-email:`** -- works but is index-backed and lags, so a
  newly linked address reads as unattributed and a red would be indistinguishable
  from a real one. Kept only in the error text as a manual check.
- **A hardcoded `mfbayraktar@live.com`** -- encodes today's answer to a question
  GitHub will answer differently tomorrow.
- **"the dominant author of the last 200 commits"**, which `.ci/lib/setup.sh`'s
  `setup_git_identity` already uses to PROPOSE an identity. Fine as a suggestion,
  wrong as an oracle: it ratifies whatever the history contains. Had it been the gate
  tonight, it would have been reading a history 73% defective on this branch.

### Failure modes: the gate REFUSES, never passes

The convention is paid for: `check-claude-attribution.sh`'s `probe_failed` exists
because five API calls each ended in `|| echo ""`, so a rate limit produced an empty
commit list, zero iterations, and "No Claude attribution found - OK" over nothing
inspected. `gh` absent, unauthenticated, rate-limited, offline, an EMPTY commit list
(every PR has >= 1 commit, so empty is a failed read), or a PR over the 250-commit
page cap -- all exit 1 naming the condition. On success it prints the number of
commits inspected and the distinct `login <email>` pairs cleared, so a collapse to
zero is visible rather than inferred from silence.

## 2. Placement: guard PRIMARY, CI gate BACKSTOP

CI is a late catch -- the commit exists and the fix is a rewrite plus a force push
across four repos, which is exactly what tonight cost. The guard refuses first. The
gate covers what the guard cannot see: a commit made in another terminal, by a
non-hook-bearing tool, or on another machine.

### The operator suggested extending `block-commit-meta.sh`. Use a SIBLING instead.

The steer's substance is kept -- same trigger point, same refuse-before-it-happens,
`.claude/hooks/pre-bash/`. Three mechanical facts argue against putting it in that
particular file:

1. **The triggers differ.** `block-commit-meta.sh` fires on `git (commit|tag)` AND
   `gh pr (create|edit)`, because its subject is message TEXT and all three author
   text. The author rule is `git commit` ONLY: `gh pr edit` has no author email, and
   `git tag -m` writes a tagger. Merging means the file's first act is a wide trigger
   and the new rule's first act is re-narrowing it.
2. **The inputs differ, and that file's narrowness is load-bearing.** It reads ONLY
   `$CMD` and deliberately does not source `lib/command-scan.sh`. Its header records
   three false positives, each from reading too much, and one where it blocked its own
   audit (`grep -rn 'co-authored-by' docs/`). The author rule must read the filesystem
   and needs `hook_target_root` for submodule commits. Introducing that into a phrase
   check with that error history risks a guard that is currently correct.
3. **One rule per file IS the convention at this trigger point** -- five guards
   already intercept `git commit` in separate files, and `check-hook-integrity.sh`
   models coverage PER FILE (each `block-*.sh` needs a block case and an allow case).
   Merged, the two rules' cases become indistinguishable to that gate, so one could
   lose a direction while the file still reported two.

The cost of a sibling is three mechanical edits, each enforced by an existing gate
that names the omission. The donor to copy is `block-untagged-commit.sh`, whose
commit-position regex and foreign-repo handling are exactly what this needs.

## 3. The guard: `.claude/hooks/pre-bash/block-unlinked-commit-author.sh`

**The asymmetry that makes this cheap:** the author identity is not in the command
text. It comes from git's ident resolution at commit time, so this guard does not
pattern-match prose, and the false-positive class `block-commit-meta.sh` paid for
three times cannot arise -- a command that merely MENTIONS an address is not a
`git commit` and is never scanned. That is a control case, not a hope.

**Trigger.** `hook_scan_target` (strips heredoc bodies and quoted spans, expands
`sh -c`), then the commit-at-a-command-position regex from
`block-untagged-commit.sh`. No `tag`, no `gh pr`.

**Which repo is judged.** `hook_target_root`: empty -> the project root; under the
root (the submodules) -> that submodule, which DIFFERS from
`block-untagged-commit.sh`'s blanket foreign-root exit because three submodules carry
this exact defect; a real git repo outside the root -> exit 0, since their identity
rules are not this repo's business.

**How the effective email is obtained.** `git var GIT_AUTHOR_IDENT` implements git's
whole precedence chain except `--author=`. Measured: plain -> `mfbayraktar@live.com`;
`-c user.email=x@y.z` -> `x@y.z`; `GIT_AUTHOR_EMAIL=env@e.e` -> `env@e.e`. So the
guard does not reimplement precedence. It collects `-c user.email=` and inline env
assignments from the RAW command BEFORE the `commit` verb (structural: git requires
`-c` first, which keeps a `-m` body out of the parse), collects `--author=` from the
scan target only, then resolves once through `git var`. If `git var` fails at all,
exit 2 with the two `git config --global` lines -- that commit would otherwise be
attributed to a guessed `user@hostname`, the same defect in a worse costume.

**The allowed set.** The guard must be offline, so it reads a committed,
GitHub-derived cache at `.ci/config/commit-identity.json` (`COMMIT_IDENTITY_FILE`
overrides it for tests). Allowed = its `emails`, plus the structural
`<id>+<login>@users.noreply.github.com` and `<login>@users.noreply.github.com` forms,
plus any `*[bot]@users.noreply.github.com`.

**The file is never hand-authored.** `check-commit-identity.sh --refresh` derives it:
`gh api user` for `{login, id}`, then emails from `user/emails` if the scope exists
and otherwise -- the path that works here -- from `repos/<repo>/commits` keeping every
`.commit.author.email` whose `.author.login` matches. It refuses to write an empty
`emails` array.

**Why it is not a suppression** and carries no `BLOCKER:` entry: the CI gate never
consults it to PASS a commit; the verdict is GitHub's `.author`. The gate makes two
LIVE assertions about the file instead -- a listed email that GitHub refuses on a
judged commit is a hard fail naming the file, and an attributed email the file does
not know is a hard fail naming `--refresh`. So it cannot suppress a finding, only lag
one, and the second assertion closes the lag without a date-triggered chore.

## 4. The CI gate: `.ci/scripts/quality/check-commit-identity.sh`

Judged set = the PR's commits over the API, as `check-claude-attribution.sh` already
does. **Why the API and not `git log main..HEAD`:** this repo's CI checkouts are
shallow, and `check-plan-housekeeping.sh` is the record of what that costs -- three
iterations, because `--is-shallow-repository` is not even the right test. The PR
commits endpoint is authoritative regardless of what the runner cloned, so this gate
has NO shallow branch at all, which is the strongest possible handling.

**Submodules are in scope.** `check-submodule-branches.sh` already resolves, per
submodule, the repo name, whether the pointer differs from `origin/main`, and the open
PR for the branch. Reuse that, then judge each submodule PR the same way. Measured
with the current credential, so the cross-repo reads work.

**Where it runs:** `ci-quality.yml` job `quality-submodule-branches`, which is the
only job already holding all three prerequisites -- the app token scoped across the
submodule repos, `submodules: true`, and a `pull_request` trigger. `pull_request`
only. NAMED BLIND SPOT: a commit pushed straight to main is not judged; every path to
main goes through a PR, direct pushes are separately forbidden, and CD's bot commits
attribute correctly. A push-range mode is deferred deliberately -- it needs
before/after threaded through `workflow_call`, and a force-push sha of all zeros has
no honest answer.

**Wiring deviates from three-point on purpose:** it needs a live PR and a cross-repo
token, so like its five siblings it is CI-only -- invoked by path, declared in
`.ci-parity-exempt` with a `BLOCKER:` line. The GATE TEST gets full three-point
treatment.

## 5. Proof

Controls built BY CONSTRUCTION (fixtures written literally), so rewording production
text cannot void them.

**Guard, in `test-hooks.sh`** -- six BLOCK cases, one per override path proved real in
section 0 (repo config, `-c user.email=`, `GIT_AUTHOR_EMAIL=`, `--author=`, a
submodule path, a missing cache), and five ALLOW cases without which over-blocking is
undetectable. The one that matters most is the false-positive control:
`git commit -m "fix: drop bad@example.com from docs"` must be ALLOWED. That is
`block-commit-meta.sh`'s lesson pinned as a test.

**Gate, in `.ci/scripts/test/gates/test-commit-identity.sh`** -- a fake `gh` on PATH
serving fixture JSON (the `test-review-status.sh` pattern), ten fixtures: a null
author fails; all-attributed passes; a `github-actions[bot]` commit passes, proving
main's bot commits stay legal; a null committer fails; an EMPTY array fails; `gh`
non-zero fails; over 250 commits fails; both cache assertions fail; and a submodule
fan-out where console is clean but `rediacc/account` is not.

**The live planted defect needs no planting.** Before tonight's rewrite, PR #585
carried 30 unattributed commits and account/renet/elite carried 7/2/1. The gate must
exit 1 naming them against the pre-rewrite tips (kept in `refs/original/`), and exit 0
after. That before/after belongs in the gate's header with the run ids.

## 6. What this does not see

- a commit made outside a hooked session and never pushed through a PR;
- a direct push to `main` (deferred, section 4);
- an override arriving through a mechanism no command text reveals;
- a cache entry that has silently stopped attributing and that nobody uses;
- co-author trailers -- only author and committer headers are judged.
  `Co-Authored-By` is `block-commit-meta.sh`'s subject and stays there.

## 7. Tasks

- [ ] Write `.ci/scripts/quality/check-commit-identity.sh` (verdict + `--refresh`)
- [ ] Generate `.ci/config/commit-identity.json`; confirm it derives the address with no `user` scope
- [ ] Write `.ci/scripts/test/gates/test-commit-identity.sh` with the ten fixtures; watch them fail before the gate is finished
- [ ] Register `gate-test:commit-identity` in `scripts/ci-runner/manifest.ts`
- [ ] Add the `ci-only` BLOCKER entry to `.ci-parity-exempt`; run `check:ci-parity`
- [ ] Add the workflow step to `quality-submodule-branches`
- [ ] Run the gate against the PRE-REWRITE tips in `refs/original/`; record the exit-1 output in the gate header
- [ ] Write `.claude/hooks/pre-bash/block-unlinked-commit-author.sh`
- [ ] Register it in `.claude/settings.json` and `scripts/data/hook-inventory-baseline.json`
- [ ] Add the eleven cases to `.claude/hooks/test-hooks.sh`
- [ ] Run `check:ci-hook-integrity` -- guard present, both directions covered
- [ ] Re-run the gate after the rewrite; confirm exit 0 on all four repos
- [ ] `check_plan_boxes.py --update` and commit the ledger
