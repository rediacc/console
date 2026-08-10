# Traps

Ways a session gets *fooled* — as opposed to ways it gets *blocked*. Each entry
cost real time on a real wave, and each is written so the next reader can
recognise the shape before paying for it again.

Mechanics of a specific subsystem do not belong here. CI behaviour (watchdog
semantics, job-roster growth, run-selection, gate quick-fixes) lives in
[ci-gates.md](ci-gates.md); escape hatches and their `BLOCKER:` reasons live in
[suppressions.md](suppressions.md). This file is about judgement.

---

## A wrong comment is more dangerous than a wrong commit message

A commit message ages into the log. **An in-code comment is what the next person
reads immediately before deciding whether to change the line it describes.**

Found 2026-08-04. A line read `${DRILL_KEEP_WORK:-0}` inside an EXIT trap. It
looked redundant, and a comment was written calling it "dead code and, worse, a
lie". Both the comment and the reasoning behind it were wrong: the default
expansion is cheap insurance that keeps the trap from aborting under `set -u`
if the source-then-init order ever changes. Had that comment shipped, the next
reader would have deleted a defensive line **on the authority of the comment
itself**, and the teardown would have died half-way, stranding a gateway and a
sandbox.

So:

- Overstating in a comment is not a style problem. It is a future defect with a
  delay fuse, and the fuse is lit by someone who trusts you.
- When a line looks redundant, the comment's job is to say *why it is not*, or
  to say plainly that nobody has checked. "This looks removable and is not,
  because X" is worth more than any confident-sounding claim.
- If you catch a wrong comment before it ships, fix it forward as its own
  change. It is cheaper than the incident it prevents.

## A check that cannot fail is not evidence

Before believing a clean result, make the check produce a RED on known-bad input
**through the same path**. An empty result and a skipped result are
indistinguishable from the outside.

Three real examples from one wave, all caught only because a control was run:

- A `git archive` silently extracted nothing, so a `[ a -nt b ]` staleness test
  compared two *absent* files and returned false — which looks exactly like a
  genuine "not stale" answer.
- A deliberately restricted `PATH` also hid `bash` itself, so the command under
  test executed **neither** branch while appearing to run.
- A log-collector script was written to gather diagnostics from a directory that
  the tool being diagnosed **deletes on exit**. It would have collected nothing,
  every time, and reported success.

This applies recursively: to the check, and to the check of the check.

## A ruling from an artifact is a hypothesis, whoever issued it

A briefing, a config file, a diff, or a teammate's message describes what someone
*believed* when they wrote it. When the claim is checkable, check it, then act.

Two from the same wave, in opposite directions:

- A validator's suggestion text read "Sections added (translate and add these)".
  It describes the **English** delta and never inspects the translation at all.
  Taken at face value it would have caused twelve already-correct professional
  translations to be rewritten.
- A colleague's correction invented a failure window ("the trap can fire before
  the variable is set") that could not occur, because the trap is installed
  inside a function called long after the assignment runs. The *conclusion* was
  still right; the *mechanism* was not. Both halves matter, because the next
  decision is made on the mechanism.

Report the refutation with the evidence, and say plainly that the ruling was
wrong. Someone who is only ever agreed with is a single point of failure.

## A version check can disagree with itself about what "installed" means

`scripts/check-deps.ts` runs `npm outdated` **against `node_modules`** at the repo
root, but with `--package-lock-only` for submodule directories. So after editing
`package.json` and regenerating the lockfile, the ROOT check still reports the old
version until you actually install, while CI — which installs from the lockfile —
is already satisfied.

The failure mode is not a red; it is chasing a phantom. You "fix" the gate, it
still complains, and the obvious next move is to assume the fix did not take and
start changing more things. Confirm which source a version check reads before
concluding your change did not land: node_modules, the lockfile, `package.json`,
and the registry can all disagree at the same moment, and each is right about a
different question.

## Some dependencies can only move as a set

`typescript-eslint`, `@typescript-eslint/eslint-plugin` and
`@typescript-eslint/parser` peer-depend on each other at an **exact** version. Any
upgrade that touches one at a time is a hard `ERESOLVE`, so a per-package upgrade
loop can never succeed on them no matter how many times it is run:

```
Conflicting peer dependency: @typescript-eslint/parser@8.66.0
  peer @typescript-eslint/parser@"^8.66.0" from @typescript-eslint/eslint-plugin@8.66.0
```

They need one `package.json` edit covering all three, then a single lockfile
regeneration. The same shape appears in the OpenTelemetry Go modules, which move
as a family of ten. When an automated upgrade reports "some upgrades failed",
check whether the failures are a MUTUALLY-PINNED SET before treating them as
independent problems — and check the tree is still consistent afterwards, since a
half-applied set is worse than none.

## Errors stack: fixing the first one promotes the second

Clearing a build error does not reveal the next one, it *makes the next one
reachable*. A drills leaf failed on a missing `llvm-strip`; with that fixed the
same job failed again, on a different step entirely, for an unrelated reason.
The red looked identical from the run summary both times.

After fixing a blocking error, re-run the thing it was blocking. Clearing the
first error is not progress until you have.

## `npx eslint` cannot be run from inside a package directory

`cd packages/cli && npx eslint src/index.ts` does not lint that package. It dies:

```
Error while loading rule 'i18n-source/interpolation-match': the "localeDir"
option resolves to ".../packages/cli/packages/cli/src/i18n/locales/en", which
is not an existing directory.
```

`eslint.config.js` sets `localeDir` relative to the REPO ROOT, and ESLint
resolves it against the CWD, so entering the package doubles the path. Run
lint from the repo root, always -- there is no per-package invocation.

The rule failing loudly is the correct half and worth preserving: it says in as
many words that *a path that does not exist would make this rule read nothing
and silently report no problems*. That is the vacuity class this file exists
for, caught by a rule author who thought about it. Had it merely resolved to a
missing directory and shrugged, every locale-interpolation check would have
passed on zero files, and the green would have been indistinguishable from a
clean tree.

The trap is not the error. The trap is concluding from it that the package's
lint is broken, and going to fix `eslint.config.js` -- the config is right, the
invocation is wrong.

## A cancelled run is not a passed run, and it is not a failed one either

The watchdog force-cancels a CI run on the first job failure. So a run that died
on an unrelated red looks, through the usual filter, exactly like a run where
everything you cared about passed:

```
gh api .../jobs --paginate --jq '.jobs[]|select(.conclusion=="failure")|.name'
```

Both print nothing new about your job. The run-level conclusion says
`cancelled` in both cases.

**Measured cost, 2026-08-06.** A flaky suite was being tracked across CI rounds
to see whether it recurred. Three consecutive rounds were counted as "did not
recur" when in fact the battery **never executed** — each run was cancelled by an
earlier gate (a dependency red, an embed-pin red, a TypeScript cast). The tally
said one-in-four; the truth was one-in-one, because three of the four rounds had
measured nothing at all. Not-executed is a THIRD state, and collapsing it into
"passed" inflates confidence exactly when evidence is scarcest.

The fix is one line in the watch, and it is worth the noise:

```
gh api .../jobs --paginate --jq '.jobs[]|select(.name=="<your job>")|"job: \(.conclusion)"'
```

Report the job's OWN conclusion, never the run's. Within one round of adding it,
a run that read `cancelled` at run level reported `battery: success` — a real
data point that would otherwise have been discarded.

The same shape hides in `gh pr checks`: `Review Complete` appears there as a
failing job with a `/runs/` URL, but it is a check-run posted by a separate
workflow. Read `.output.summary` on the commit's check-runs to see what it
actually says.


## `git diff <branch>` reads as DELETED for a file the worktree never tracked

When a wave builds its branch with PLUMBING (temp `GIT_INDEX_FILE` + `write-tree` +
`commit-tree` + `update-ref`) so that HEAD can stay put in a checkout shared with
live peer sessions, the branch new files are UNTRACKED relative to HEAD.
`git diff --stat <branch> -- <path>` then compares the branch against the INDEX,
where an untracked file is simply absent, and reports the entire file as deleted.
Observed 2026-08-09 on branch 0809-2: a healthy 462-line `wl_checklist.py` printed
`1 file changed, 462 deletions(-)` while sitting intact on disk, and the reflex read
is that a sub-agent deleted it. Nothing was damaged; the INSTRUMENT was wrong.
Ask the content, not the index:
`git show <branch>:<path> | diff - <path>`, or stage into the temp index and use
`git diff-index --cached --name-status <branch>`. Same class as a failed existence
check with the wrong path: a query that cannot see the thing it is asking about
answers confidently and wrongly.

## Editing a shell script while a background job is RUNNING it

Bash reads a script LAZILY, by byte offset, not into memory. Rewrite the file
while a job is executing it and the interpreter resumes at its old offset inside
the new bytes, so it starts parsing mid-token. The error it prints names a line
that is innocent, and often no longer exists at that number.

Observed 2026-08-09: `test-hooks.sh` was edited (five cases appended, then
`shfmt -w`) while a backgrounded umbrella run was still inside it. That run died
with `line 380: syntax error near unexpected token (` pointing at
`echo "... $n case(s) passed"`, a line that had been valid for months and now
sits at 368. `bash -n` on the file was CLEAN throughout, which is the tell: a
syntax error that the syntax checker cannot reproduce is not in the file, it is
in the READER. Chasing the named line finds nothing wrong, because nothing is.

So: never edit a script a background job is running. Let it finish, or copy the
tree and edit the copy. And when a shell syntax error cites a line that looks
fine, check whether anything rewrote the file mid-run before debugging the line.

## Rerunning Smoke Test Preview trades one failure for another

`gh run rerun --failed` is the standing remedy for a live-state gate, but it is
WRONG for `Smoke Test Preview`, and the two attempts look like contradictory
evidence unless you read both assertion lists.

Observed 2026-08-10 on PR #567, same commit, two attempts:
  attempt 1: license checks PASS, install.ps1 + marketing 404
  attempt 2: install.ps1 + marketing PASS, license checks 403
             "Token is bound to a different IP address"

Neither attempt is the truth about the commit. The 404s are preview propagation,
which time fixes. The 403 is a rerun artifact: the E2E token is bound to the IP
of the runner that minted it, and a rerun lands on a different runner. Each
attempt passes what the other failed, so a FRESH run (new commit, new token) is
the remedy, not another rerun.

The trap for the reader is the job-level conclusion. Both attempts report
`Smoke Test Preview: failure`, so a summary read says "reproduces, therefore
real, therefore mine". It does not reproduce; it fails differently each time.
Read WHICH assertions failed before concluding a red is deterministic.

## A killed command did not run its own cleanup

MECHANIZED: `.claude/hooks/trapguard/dispatch.py::rule_interrupted_cleanup_skipped`
fires on this shape, so you should meet it as an injected warning rather than here.
The entry stays because the remedy is a habit no hook can install for you.

A mutation test neutered a guard in the live tree, ran the suite, and restored it
on the next line:

```
python3 -c 'mutate'; bash test-worklist-v5.sh > mut.log; cp worklist.py.orig worklist.py
```

The suite outlived the 2-minute tool timeout. The whole command took SIGTERM at
`Exit code 143`, and the restore never ran. What came back was:

```
syntax ok
mutated: guard neutered
```

Both lines true, and together they read like a step that finished. The working
tree sat with a disabled guard in it, which is the worst possible state for a
session whose next act is to trust that guard.

The general shape: **an interrupted command's output is a truthful, complete
looking account of the part that ran.** Nothing marks where it stopped. Any
`;`-chained cleanup, restore, `git checkout --`, `rm -rf` of a sandbox, or
`stash pop` is exactly as skippable as the timeout is long, and the risk rises
with how slow the middle step is, which is the same thing that makes the timeout
likely.

The remedy is not "remember to check". It is to **mutate a copy, never the live
tree**: put the sandbox under the scratchpad, mutate there, and let the kill
strand nothing that matters. When the live tree genuinely must change, verify the
restore landed by reading the file back, and never from the command's own output.

## A mutation test needs BOTH directions, or its red proves nothing

The discipline is "plant the defect and watch the check go red". That half is not
enough, and this session paid for the other half within the hour.

Two new suite cases went red under a mutation that disabled the guard they
covered. Signature looked perfect. They were also red on the untouched tree, so
the mutation had demonstrated nothing at all: a case that can never pass goes red
under every mutation, including one that changes nothing.

The cause was `set -uo pipefail` (`test-worklist-v5.sh:5`) plus an assertion
written as `refusing-command | grep -q needle`. The refusal exits 2 by design, and
under `pipefail` a pipeline carries the first non-zero exit rather than grep's, so
the `if` was false while grep was matching perfectly. **Never read an exit code
after a pipe.** Capture first, then match, which is what every other refusal case
in that suite already does:

```bash
OUT="$(cmd 2>&1)"; RC=$?
if [[ "$RC" == "2" ]] && grep -qF needle <<<"$OUT"; then
```

So a mutation run must always be two passes: **red with the defect planted, green
without it**, and the second pass is the one that catches a broken fixture. Run
them in one script so skipping the baseline takes deliberate effort.

A smaller instance rode along in the same script. Its summary line was
`grep '^FAIL' "$log"`, but the suite indents results, so the filter matched nothing
and printed an empty "failures" section under a run that had failed, next to an
exit code saying otherwise. A reporting filter that cannot match reads exactly like
good news.
