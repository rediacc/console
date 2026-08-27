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

A smaller instance rode along in the same script, and it recurred **twice**, which
is the part worth remembering. The failures filter was `grep '^FAIL'` while the
suite indents its results, so it matched nothing and printed an empty "failures"
section under a run that had failed, next to an exit code saying otherwise. That
one got fixed to `^ *FAIL`, and fixing it felt like handling the class.

It was not. The SUMMARY filter in the same script was `grep -E '^(passed|failed)='`,
and the suite's totals line is indented too (`  passed=669 failed=0`), so it also
matched nothing. Confirmed by measurement, not memory: `^(passed|failed)=` matches
zero, `^ *passed=` matches. Every "totals" read that night came back empty and got
worked around rather than fixed, because the obvious instance had already been
dealt with. **Fixing the first instance of a class is what stops you looking for
the second.** It took an independent reviewer to find it.

## Session liveness is judged by the harness task list, never by the agent roster

After a Claude Code process restart, `ListAgents` shows zero subagents even while
the writers it spawned are alive and editing; the reports directory being empty
proves nothing either, because agents that report at completion have no output
stream at all until they finish. Both signals read as "everyone is dead" while
the OS-verifiable harness task list still carries the running ids. A lead trusted
the roster once (2026-08-10, backup-storage wave 0), declared two live writers
dead, and relaunched duplicates into their exclusive file sets; only a
stop-the-line by one duplicate prevented two writers interleaving in one package.

The invariant, enforced by `worklist.py`/`wl_liveness.py`: every `- [>]` lease
declares a `worker:<id>` that must verify against the harness's running
background task ids. The hook refuses text-only refreshes of a lease whose
worker is gone, and the lease-warning path prints the current live ids, which is
also the sanctioned way to discover them.

**That printed list is not a roster of live workers, and reading it as one is
the trap inside the trap.** It is the harness's LAST WORD, and an entry stays in
it after its task's process has died. On 2026-08-15 a session leased a
just-launched agent, was warned its id was unknown, read the accompanying list
literally, concluded a worker on it was therefore alive, and came one command
away from pointing a second writer at that dead worker's files. The list now
annotates each id with minutes since its output stream last grew
(`worklist.py:660`), so the dead entry renders as `bnkrmw2mt (55m)` rather than
as a bare id indistinguishable from a healthy one. Probe the OUTPUT STREAM, which
no self-report can fake; never the roster. There is deliberately no repository
CI gate for this class: the worklist store is per-machine session state that CI
runners do not have.

Two instruments that lie during exactly this diagnosis, both measured: this
box's `/usr/bin/find` is bfs 4.1.1, which REJECTS relative `-newermt` forms
(`'-40 minutes'`, `'10 minutes ago'`) with exit 1, so under `2>/dev/null` a
"what changed recently" sweep returns empty and reads as no activity; use
absolute ISO timestamps or `stat -c '%y'` on the candidate files. And
`grep -c $'\x00'` is not a NUL detector: bash strips the NUL from `$'\x00'`,
the empty pattern matches every line, and the output is the file's line count
regardless of content. Probe liveness with mtimes you computed yourself, and
plant a control before trusting any zero.

## A mutation proof run in place poisons everyone else's measurements

Proving a test can fail means breaking the code on purpose, and the obvious way
to do it is to edit the file, run the suite, and edit it back. In a shared
checkout that is a two-minute window in which the tree is knowingly wrong, and
nothing announces it. On 2026-08-14 a writer proved its isolation test this way
while a verifier was measuring the same tree; the verifier copied the live
service file mid-window and found the deliberately unscoped query in it. Anything
anyone ran in that window measured a broken tree, and the next session to see the
red would have had no way to know why. Worse, a checkpoint or a commit taken in
that window captures the mutation as if it were the work.

The house rule, which costs nothing: mutate a COPY, never the shared tree.
`rsync` the package to a scratchpad, symlink `node_modules` back so workspace
imports still resolve, and run the suite in the copy. Zero-writes stays literally
true, the re-cut-from-live rule is satisfied, and a verifier can work while a
writer is live without either racing the other. Re-cut immediately before each
round: a cut that symlinks a live sibling package still drifts when that sibling
is rebuilt, which is the same staleness the rule exists to prevent.

If an in-place mutation is genuinely unavoidable, say so out loud BEFORE running
it, keep the window to a single command, and re-verify the restore byte-for-byte
(`diff -q` against a pre-mutation copy, not against memory) rather than trusting
that the edit-back was exact.

## "Clean vs HEAD" is the wrong baseline in a tree that was already dirty

The forbidden-command rule (never `git checkout` / `restore` / `stash` / `clean`)
is stated elsewhere. This entry is about why an agent that breaks it BELIEVES IT
SUCCEEDED, which is what makes the damage silent.

2026-08-14: a locale writer ran a script that incidentally touched
`packages/www/src/i18n/translations/.translation-hashes.json`, a file outside its
task. Wanting to leave no trace, it ran `git checkout --` on that one file, then
checked `git status`, saw the file clean, and reported "touched then restored, net
no-op". Every word of that was sincere and the conclusion was wrong.

The file had been dirty BEFORE the session started: another session had left
`sourceCommit 1ebd8aff` uncommitted in it. `git checkout --` does not undo YOUR
change to a file. It discards ALL uncommitted changes to it. So the command
reset past the prior state to HEAD, destroying the other session's value, and the
resulting file looked *cleaner* than correct.

That is the trap: **after an unwanted edit, "clean vs HEAD" is not the target.
The target is "identical to what was there before I arrived."** Those two are the
same thing only in a tree with no uncommitted work, which is never true here.

- The correct repair is forward: edit the value back, or leave it and say so. Both
  keep every other change in the file.
- The only reason this was recoverable is that the session checkpoints include
  UNTRACKED and pre-existing dirty state, so the original byte could be read out
  of the session-start patch. A checkpoint that only captures your own work cannot
  answer "what was here before".
- Damage was one metadata field. That was luck, not care: the same command on a
  locale file mid-edit deletes a peer's work with nothing to reconstruct from.

The tell, for a reviewer: a report that says "restored, no-op" and cites a clean
`git status` as the proof. Ask what the file looked like BEFORE, and whether
anyone checked.

## A green task notification can be reporting the shell, not the gate

A backgrounded `npm run check:lint` completed with **"exit code 0"** in its task
notification while the gate itself was failing with 17 errors. Nothing was
broken. The command was:

```
npm run --silent check:lint > /tmp/checklint.log 2>&1; echo "check:lint exit=$?"
```

A `;` list exits with the status of its LAST command, and `echo` always
succeeds. So the wrapper honestly reported success for the shell invocation,
which is not what anyone reads it as. The real status existed only as text
inside the log, in the line the `echo` had written.

This is the same defect as a gate that prints its failure and exits 0, moved one
layer out. The layers that can each swallow a status independently:

- `cmd | grep ...` reports **grep's** status, and `grep` exits 1 on "no lines
  matched", which is the normal outcome when a build is clean. `echo "exit=$?"`
  after a pipe is therefore almost always measuring the wrong thing.
- `cmd; echo ...` reports the echo.
- `( cd x && cmd )` reports the subshell, including a failed `cd`.
- A task notification reports the whole invocation, whatever shape it had.

Habits that survive all four: put the command last, or capture with
`cmd; rc=$?; ...; exit $rc`, or use `${PIPESTATUS[0]}` and say out loud which
element you read. When a summary and a log disagree, the log is the artifact and
the summary is a claim about it.

## A tool that cannot answer may report "nothing to do" in valid JSON

`check:deps` answered **exit 0** and **exit 1** two minutes apart with no
intervening change. The green run was not noise, and calling it a fluke was
wrong: the gate fails OPEN whenever it cannot reach the npm registry, and it had
just been run after several `npm install`s.

Proven in one command:

```
npm_config_registry=http://127.0.0.1:9/ npx tsx scripts/check-deps.ts
→ "All dependencies are up-to-date", exit 0
```

The mechanism is worth knowing precisely, because "handle the error" does not
cover it. `npm outdated --json` does **not** fail loudly on an unreachable
registry. It prints a well-formed object:

```json
{"error":{"code":"ECONNREFUSED","summary":"request to .../typescript failed", ...}}
```

That parses. It contains no outdated packages. So every downstream reader
concludes there is no work, and the gate emits the **strongest claim it has** —
everything is current — from **zero information**. Three separate `return {}`
branches in the reader turned every other failure (no stdout, unparseable
stdout, a throw with an empty payload) into the same false green.

The general shape, which is not specific to npm:

- **An empty result and an unobtained result are different facts**, and most
  tools flatten them into the same value. Ask which one you are holding.
- **Valid output is not a successful query.** A schema check passes on
  `{"error": ...}`. Check for the tool's own failure envelope before trusting a
  parse.
- **The most confident assertion is the one to distrust.** "Everything is
  up-to-date", "no vulnerabilities", "no dead code" are all reachable by a check
  that ran nothing.
- **Exit codes are the tool's opinion, not the truth.** Here npm exited 1 while
  handing back a parseable body; elsewhere it exits 0 having learned nothing.

The fix that holds: make the unobtained case throw, and add a control that forces
each failure shape and asserts the gate goes red **with the matching message** —
`check:deps` now runs `--selftest` before every real run, covering both an empty
probe and the error-envelope, and refusing a green that says "up-to-date". A
control that only tests the shape you happened to hit is half a control: the
empty-probe case was written first and would never have caught the
error-envelope case, which is the one that actually shipped.

## `--force` may force the wrong half

Bumping the embedded rsync pin 3.4.4 → 3.5.0 meant editing
`private/renet/embed-assets.lock.json` and both `ARG RSYNC_VERSION` /
`ARG RSYNC_SHA256` stages in the Dockerfile, then restaging:

```
./build.sh embed_assets --force     # exit 0
```

Green. The freshness gate went green. The credits gate went green. And the
staged asset was **still 3.4.4**, same bytes, same August mtime:

```
zstd -dc pkg/embed/assets/amd64/base/rsync-linux-amd64.zst > /tmp/r && /tmp/r --version
→ rsync  version 3.4.4
```

`embed_assets` builds the Docker image only `if ! docker image inspect
rediacc/renet:latest`. The image already existed, so `--force` forced
**re-extraction from the stale image**, not a rebuild. A Dockerfile `ARG` change
is invisible to it by construction. The rebuild is a separate verb,
`./build.sh docker_image`.

Two things generalise:

- **A flag's name is a promise about scope, and scope is where it lies.**
  `--force` here means "re-extract even if the receipt looks current", not
  "rebuild what the extract comes from". Read what the flag actually guards
  before treating it as a big hammer.
- **Every gate in the chain confirmed the pin, and no gate looked at the
  payload.** Freshness compares the pin to upstream. Credits compare the ARG to
  the lockfile to the generated attribution. All three agreed, and all three were
  reading the same declaration rather than the artifact it describes. The only
  check that caught it decompressed the binary and ran `--version`.

When a version bump touches something that gets *built* rather than downloaded,
the acceptance test is the built thing answering its own version, never the
manifest that requested it.

**This one is now an instrument, not just a lesson.**
`check:ci-embed-asset-versions` (`scripts/check-embed-asset-versions.ts`,
reachable from `npm run ci`) decompresses every staged asset and asks the binary
its own version, executing it when the architecture matches the host and reading
its string table when it does not. It is the only embed gate that opens the box.
Three things keep it honest: it declares a MISMATCH only when a binary states a
DIFFERENT version, never merely when it fails to state ours (the CSI sidecars
ship with no version compiled in and would otherwise be red forever); it names
every asset it could not probe instead of quietly counting it as fine; and a
decay guard fails the run if rsync, criu or rclone ever come back unprobed,
because a check that stops checking is how this class returns.


## A gate that lints "the important directories" is silent about everything else

A shell file added at `.claude/lib/` passed BOTH shell gates on 2026-08-15 while
carrying a blatant SC2086. Not a missed error: a **green tick over a file neither
gate had opened**. `shellcheck.sh` and `shfmt.sh` each walked four hardcoded
roots (`.ci`, `.claude/hooks`, `run.sh`, `scripts/`), and a path outside them
produced no error, no warning, and no mention. The omission is invisible by
construction, which is what separates this from an ordinary bug: the output of a
gate that skipped your file is byte-identical to the output of a gate that read
it and approved.

The instinct on discovering it is to widen the glob to cover your own file. That
instinct is the second half of the trap. Widening to `.claude/**` would have
fixed the one file in hand and left thirteen others unscanned, among them
`packages/www/public/install.sh` -- the PUBLIC installer users pipe into bash --
and `rdc.sh`. Measure the whole uncovered set before choosing the fix; the
instance you tripped over is rarely the worst one in it.

`shellcheck.sh` now enumerates from `git ls-files '*.sh'` (417 files), because a
list of roots needs maintenance and an enumerator does not: a new script is
covered the moment it is tracked. It also REFUSES an empty file list, since a
gate that lints nothing exits 0 exactly like a gate that lints everything.

**The general rule: before trusting a gate's green, ask which files it actually
opened, and prove it by planting a violation in the file you care about.** Any
gate that names its inputs by directory, extension, or allowlist can be silently
scoped away from the code you are changing. Note also that a correctness gate and
a formatting gate deserve different answers here -- `shfmt` was deliberately NOT
widened past `.claude`, because enumerating everything would demand reformatting
eleven untouched files including deployed repository templates: churn, with no
defect found. That asymmetry is documented in `shfmt.sh` so a later reader does
not "fix" it.

## A Python gate that runs green on your machine and dies on the runner

`check_workflow_submodule_deps.py` imported PyYAML, passed every local run, and
died on the runner with `ModuleNotFoundError: No module named 'yaml'`. The
module was in the author's environment and not on a clean Ubuntu runner, and
nothing compared what a script imports against what its job installs.

The tell is that **it never failed anywhere the author could see it**, which is
the same shape as two other traps this repo has paid for: a suite case that
silently no-opped under `GITHUB_ACTIONS`, and a gate registered in the manifest
against a workflow step that did not exist. All three passed where they were run
and meant nothing where they mattered.

**This one is now a gate rather than a paragraph**: `check:ci-python-gate-deps`
reads the imports of every `.py` a workflow step runs, drops stdlib and
first-party modules, and requires a `pip install` in the same job to name what
is left. Verified by replaying the real defect, which it reports as
`check_workflow_submodule_deps.py imports 'yaml' and no pip install in this job
names it`.

The reason it is a gate and not this paragraph: the stop-hook suite's own
`setup()` carried a comment recording that 30 cases were once lost to an
inherited `GITHUB_ACTIONS`, and a new call site was still added without the pin.
A document an agent can skip is not a control.

**It does not follow imports transitively.** A gate that grows a helper module
with its own third-party import is one hop outside what this sees.

## A green `packages/www` build can render the PREVIOUS version of a page

Observed 2026-08-16 on `docs/en/backup-restore.md`, with timestamps:

- source last written 08:06:08
- `.astro/data-store.json` refreshed 08:06:12, carrying the NEW text
- `dist/en/docs/backup-restore/index.html` written 08:09:51, carrying the OLD headings
- build completed 08:10:19, **exit 0**

The built HTML contained a section id (`two-backup-paths`) that exists nowhere in
the source tree. A second build, with no source change, produced the correct
page.

So the build succeeding is NOT evidence that the build built what you wrote. The
content layer's cache can serve a stale entry while everything downstream reports
success, and an agent that trusts the exit code will report a page as shipped
when it has not.

**What to do instead: grep the BUILT HTML for a phrase you just wrote.** If it is
missing, build again. This is the same rule as everywhere else in this file --
check the artifact, not the report of the artifact -- and it costs one grep.

<!-- MERGED 2026-08-16 from the gitignored .agent/TRAPS.md, which the stop hook
     read while THIS file reached nobody programmatically. The two corpora had
     drifted ~90% apart: 18 headings there, 22 here, 3 shared. Everything below
     this line came from that file and would have been lost when it went away. -->

## The review tooling comes from `main`, the workflow comes from the PR

A workflow step may only call `claude-review-gate.sh` arms that **already exist
on main**. `claude-review-reusable.yml` checks the review scripts out with
`ref: main, path: .review-scripts`, deliberately, so PR-authored review scripts
can never execute. The workflow file itself comes from the PR.

Cost: run `30552035566`. A step called a `--record-invocation` arm added on the
branch; `git show origin/main:...claude-review-gate.sh | grep -c record-invocation`
returns 0, so the step failed instantly and took the review job red.

Corollary: a new script arm is unusable until merged. Inline it in the workflow
(under `check-workflows.sh`'s 8-logic-line cap) or wait for the merge.

## `.ci/breakpoint/` is VENDORED into other repos

`check-breakpoint-drift.sh` fails on ANY local edit, correctly, and there is no
exemption list. Do not edit it to change CI behaviour.

Cost: one round. Editing `test-breakpoint-lifecycle.sh` failed the gate with
`25 files verified, 0 accepted divergences`.

Instead: tune from the CALL SITE. `start-tunnel.sh:44` reads
`CONNECT_TIMEOUT="${ARG_CONNECT_TIMEOUT:-90}"` from the environment, so setting
`ARG_CONNECT_TIMEOUT` in `ci.yml` costs zero drift. Measured: env set resolves
180, unset resolves 90.

## GitHub matrix fail-fast beats the `no-cancel-failure` label

The label cannot reach it. Matrix fail-fast cancels every sibling before the
watchdog is ever consulted, so on a branch being driven to green each round
surfaces one failure instead of the whole surface.

`ci-build-docker.yml` and `ci-build-renet.yml` set `fail-fast: false`;
`ci-build-cli.yml` and `ci-ops-test.yml` did not until 2026-07-30.

Related limit on the same label: it cannot make a DOWNSTREAM job run.
`validate-install`, `validate-promote`, `deploy-preview` and
`smoke-test-preview` all hang off `stage-artifacts.result == 'success'`, so a red
build still leaves that whole half `skipped`. The label buys enumeration of the
PARALLEL surface, not the SERIAL one.

## A step with no status function is skipped when an earlier step fails

Implicit `success()`. This is how a review that burned its full turn budget
recorded nothing: the marker step was skipped, the cap counts posted reports, so
a spent pass counted as zero and the same SHA would be re-reviewed at full price
forever.

Cost: run `30552035566`, `"subtype": "error_max_turns"`, zero bot comments on the
PR, no marker. Predicted in advance by the S-2 spike for a budget halt; it
arrived via `max_turns` instead.

Rule of thumb: if a step is an ACCOUNTING RECORD, it needs `always()`. If it
POSTS something the model produced, leave it on implicit `success()` -- with no
output there is nothing to post and it only adds a way to fail the job.

## A cache key must cover every input BAKED INTO the artifact

`generate-tag.sh`'s closure hashes git OIDs at HEAD, documented as being "immune
to the in-job version bump that dirties package.json". That immunity is right for
a dirty working file and exactly wrong for the released version: a git TAG is not
a path, so no `CLOSURE_PATHS` entry could ever cover it, and the key went
insensitive to the one input the image is stamped with.

Cost: two full rounds. Runs `30534726467` and `30542942037`,
`Version mismatch: expected '1.2.13', got '1.2.12'`, deterministic and
self-perpetuating because cutting a tag does not move the closure.

## `git branch --merged` always lies here

All five repos are rebase-merge only, so a merged branch shares no commit with
`main`. The ancestry test called all 75 console local branches unsafe to delete
when 59 had merged PRs. Ask the PR, never ancestry.

## A gate can pass on the exact body it was written to reject

`wait-for-preview-worker.sh` waited for a "usable body" and its own comment said
a 200 carrying no keys must fail. The guard was `grep -q '"keys"'`, but
`app.ts:154-173` declares `const keys = []` and always returns
`c.json({ e2e: { keys } })`, so `"keys"` is present even when empty.

Measured both ways: the old grep ACCEPTS `{"e2e":{"keys":[]}}`. Grep for a field
that only exists inside a populated entry (`publicKeySpki`), not for the
container.

## Read stdout and stderr SEPARATELY, and never `2>/dev/null`

Cost: at least three rounds this program. `gh run view --log-failed` is
run-scoped even with `--job` and says so on stderr; a plan writer wrapped in
`2>/dev/null || true` made a crash indistinguishable from "no plan was due"; and
`grep -i FAIL` matched the word "fail" inside PASSING lines, making a mutation
probe look inconclusive.

Use `gh api repos/OWNER/REPO/actions/jobs/<id>/logs` for a single job's log.

## A helper defined below its first use is a SILENT no-op

`pass`/`fail` sat at line 2462 of `test-worklist-v5.sh` while cases above called
them. The suite reported `253 passed, 0 failed` while three assertions emitted
`pass: command not found` to stderr and counted nothing.

Only visible because stderr was read separately. Define helpers at the top.

## A watch verdict is not evidence

This whole class is why `.ci/scripts/ci/ci-trace.py` exists and why ad-hoc watch
commands are now refused by `block-adhoc-sanctioned.sh`: the script keys on the
PR head and reads `statusCheckRollup`, so a superseded run and a watchdog rerun
are not mishandled, they are unrepresentable.

Hand-rolled terminal-state watches have understated failures (reporting one failed job when
the API showed the run cancelled with more), and `gh run watch` has dropped
silently on terminal runs 4 times out of 4. Always re-read the Jobs API before
acting on a verdict, and never treat a still-growing run as final -- one went
42 -> 48 jobs while being read.

## A background agent goes idle WITHOUT sending its report

Observed three times in one session: `skipplan`, `greenblock`, `stopplan`. Each
finished real work and then emitted only an `idle_notification`. The findings sat
unread in the agent's own transcript, in one case for hours, while this session
reported the work as still in flight.

The report is NOT delivered automatically. You must ask for it with
`SendMessage` to the agent by name, and the ask should enumerate exactly what you
want, because a re-asked agent will otherwise summarise rather than send the
artifact.

Cost of not noticing: `skipplan`'s completed work was committed and pushed by a
sweep before its report arrived, so it was verified against its gates rather than
against its reasoning, which is the wrong order.

Corollary: never write "agent is still running" in a status table on the strength
of no message arriving. Check, or say you have not checked.

## A blanket `git add -A` sweep imports other sessions' half-landed work

The standing rule to commit and push everything every round is what keeps a
shared tree clean, but it also picks up WIP that was never meant to be committed,
and that WIP can red your branch.

Measured 2026-07-30: sweep `cefa43ca7` picked up another session's
`check-solution-video-engine.ts` mid-campaign. It is wired into `npm run ci`, is
absent from `origin/main`, and failed `273 of 273` on every run of branch 0730-2
(run 30554973713, job 90913300683). Its owner's answer when asked: drop it, it
was never meant to be committed yet, and `273/273 unknown` is CORRECT output
because no manifest entry carries the field until the publish writes it.

So: when a sweep-imported file reds the branch, ASK THE OWNER via
`worklist.py --ask` before touching it. Do not weaken another session's gate to
get your own branch green, and do not assume a red gate is a broken gate. Removing
it needs EVERY site at once (script, `package.json` ci chain, workflow step) or it
stays red.

## A failed existence check with the WRONG PATH proves nothing

`git show origin/main:<path>` exiting nonzero means "not at THAT path", not
"not on main". Cost: `18-dual-group-migrate.test.ts` was reported absent from
main and "arrived via a blanket sweep, unattributed" for hours, by two
independent checks (an audit agent and this session), both probing
`tests/18-dual-group-migrate.test.ts` when the file lives at
`tests/migrate/18-dual-group-migrate.test.ts` and landed in merged PR #520.

Verify existence with the path from `find`/`git ls-files`, never a remembered
one. And when a zero-skip gate fires, read the line ABOVE the skip first: a
serial suite skips the rest after a failure, so the skip is usually the
symptom and the failure one line up is the story (run 30554973713: test 4
"migrate cutover" failed, test 5 skipped as fallout).

## Harness task output streams live under <tmp>/claude-<uid>/, not <tmp>/

Any hook code deriving a background task's output path must include the
claude-<uid> segment: the real layout is
<tmp>/claude-<uid>/<munged-cwd>/<session-id>/tasks/<task-id>.output, where
munged-cwd is the cwd with every non-alphanumeric character replaced by '-'.
A derivation that starts at bare gettempdir() resolves to a path that never
exists, and the failure is SILENT (stat fails, the worker reads as "no
output stream yet"). Found on the v15 check-in's first live firing; the
end-to-end regression case is 163e in test-worklist-v5.sh, which drives the
real derivation against a fixture TMPDIR with no env override.

## A Python step's imports must be stdlib or installed IN THAT JOB

A gate imported PyYAML, passed every local run, and died on the runner with
`ModuleNotFoundError: No module named 'yaml'`. The module was in the author's
environment; a clean Ubuntu runner has no PyYAML.

The tell is that it **never failed anywhere the author could see it**. That is
the same shape as two other traps paid for the same night: a suite case that
silently no-opped under `GITHUB_ACTIONS`, and a gate registered in the manifest
against a workflow step that did not exist. All three passed where they were run
and meant nothing where they mattered. "Reachable from `npm run ci`" and "runs
in CI" are different claims and neither implies the other.

Install pinned, in the job, and assert the version on the next line so a failed
install surfaces as itself rather than as an import error further down:

    python3 -m pip install --user --disable-pip-version-check "PyYAML==6.0.2"
    python3 -c "import yaml; print('PyYAML', yaml.__version__)"

This is now enforced by `check:ci-python-gate-deps`, which reads the imports of
every `.py` a workflow step runs and requires a `pip install` in the same job to
name what is not stdlib or first-party. It covers itself. It does NOT follow
imports transitively, so a gate that grows a helper with its own third-party
import is one hop outside what it sees.

## A gate failure the serial rerun cannot reproduce is a CONCURRENCY artifact, not a flake

`npm run ci` runs its gates ~8.7x parallel. Something in that pool rewrites
tracked source files in place while other gates are reading them, so a reader
can catch a half-written file. The 2026-08-17 battery failed
`gate-test:claude-hooks` with

    .claude/hooks/test-hooks.sh: line 545: syntax error near unexpected token `fi'

for a file that parses clean and scores 884/0 exit 0 when run directly, twice.

Diagnose it by MTIME, not by re-reading the file, because by the time you look
the file is whole again:

    find .claude .ci scripts packages -type f \
      -newermt '<battery start>' ! -newermt '<battery end>' \
      -not -path '*/node_modules/*' -printf '%TH:%TM:%TS %p\n' | sort

A tracked file whose mtime lands inside the window while `git status` reports it
UNMODIFIED is the signature: something rewrote it with identical content. Do not
"fix" the file. Rerun the gate serially on a quiet tree; if it passes, the
failure was the race, and the real defect is the writer.

THE 2026-08-17 CASE, SOLVED, because the answer generalises. The writer was
`.ci/scripts/test/gates/test-generate-tag-inputs.sh:289` and `:311`, which
overwrite the REAL `resolve-version.sh` with a stub and `cp` it back a second
later (`generate-tag.sh` runs via `cd "$REPO_ROOT"` and offers no fixture seam).
No literal path appears at either write site -- both go through a `$real`
variable -- so every grep for the filename missed them. It was classified T
("isolated by construction") rather than W in `run-all.sh` on the strength of
its own comment claiming it "cannot disturb a shared tree": true of the tag
namespace it avoids, false of the working tree it overwrites. A comment
asserting safety is not evidence of safety, and here it actively caused the
misclassification.

TWO WAYS THIS MISLEADS THE INVESTIGATOR. First, a process snapshot taken when
the mtime moves shows the SURVIVORS, not the culprit: poll-then-`ps` misses a
child that has already exited, and reproducing "the three gates that were
running" proved nothing because none of them was the writer. Second, and more
embarrassing, A CONCURRENT AGENT EDITING FILES PRODUCES THE IDENTICAL SIGNATURE.
Two of the three "victims" in this case were a peer session's own whole-file
rewrites, each followed immediately by `bash -n` and a suite run -- the same
write-execute shape, landing in the same window. Before hunting a gate, ask who
else is working in the tree.

Two ways this bites the reader rather than the writer. First, `| head` on the
`find` output hides the decisive hit, because the interesting file is usually
LAST in a sorted-ascending list dominated by `node_modules` churn -- this is the
truncated-instrument trap wearing a timestamp. Second, the innocent explanation
is genuinely common: build artifacts, generated search indexes and
`.tsbuildinfo` legitimately move. Filter those out before concluding anything.

## A dangerous line in a gate is not a fired line

`.ci/scripts/quality/check-branch.sh:84-88` runs `git rebase origin/main` and
`git checkout <sha>` against the LIVE working tree. In a shared checkout holding
300+ uncommitted files from several sessions that reads like a catastrophe, and
it is a real latent hazard -- but it is guarded: the script exits at line 62
when the branch is not behind the base, which is the normal case.

Before attributing an observed effect to scary-looking code, prove the code RAN.
`git rev-list --left-right --count origin/main...HEAD` answers the guard's own
question, and `git reflog` shows whether a rebase actually happened. Blaming the
alarming line without that check produces a confident, wrong root cause and
leaves the real writer unfound.

## Some dependencies can only move as a SET, and the second half looks like a network step

`.ci/scripts/private/license-mint/` is a standalone Go module that pulls renet in
through `replace github.com/rediacc/renet => ../../../../private/renet`. That
makes renet's dependency graph part of its own, so bumping a dependency in
`private/renet/go.mod` and stopping there leaves license-mint pinning the old
version. `go build` then refuses with:

    go: updates to go.mod needed; to update it:
            go mod tidy

Two things make this one worth a trap entry rather than a footnote. It surfaces
LATE -- `Tests + Infra / License Enforcement`, roughly 25 minutes into CI, past
every quality lane -- and it READS AS INFRASTRUCTURE: the job announces
"Building license-mint" and then prints a wall of `go: downloading ...` lines,
one of which is the OLD version. The instinct is to blame a slow or flaky proxy.
From renet's side there is nothing to see at all; the bump looks complete and
self-contained, because the coupling lives entirely in the other module.

`check:ci-go-module-sync` now enforces it, and it DISCOVERS the modules rather
than naming them, so a second module that replaces renet is covered the day it
is added. It also fails when it finds ZERO, because a discovery gate that finds
nothing has verified nothing rather than passed.

The general shape, which outlives this one file: when a change is correct in the
module you edited and the build still fails elsewhere, ask what else declares a
`replace` onto it. `grep -rl "replace github.com/rediacc/renet" --include=go.mod .`
answers it in one command, and the fix is `go mod tidy` in each result.

## Widening a deletion prefix by one directory can delete a LIVE file while removing zero bytes

`git filter-repo --path packages/www/public/assets/videos --invert-paths` looks
like a harmless generalisation of `--path packages/www/public/assets/videos/solutions`.
It is one directory shorter, it covers the intended subtree, and it reads as
tidier. It is not a generalisation. A path-selection argument under
`--invert-paths` is a DELETION LIST, and widening a deletion list is never free.

The parent directory carried **0.00 MB across 0 blobs** of history, so the wider
prefix removed nothing extra from the pack -- and destroyed
`packages/www/public/assets/videos/user-guide/.gitkeep`, the ONE tracked file in
that tree. `git ls-files packages/www/public/assets/videos/` returns exactly one
path, and that path was it. The command exited 0, the resulting pack size was
right, and every progress line looked identical to the correct run. Nothing in
the tool's own output distinguished the two.

What caught it was the tree-identity control, not the reading:
`git rev-parse main^{tree}` must print `444e9c09092a80bbb7defa6eea122e0de28a89eb`
on the pristine clone and on the rewritten one. It did not. Naming the casualty
then took one line: `comm -23` on two `git ls-tree -r main --name-only`
listings.

The rule that generalises: before adding or widening a prefix in a deletion
list, run `git ls-files -- <prefix>` and read what is inside it, and re-run the
tree-identity control after **every** change to the list. "It only adds an empty
parent" is a claim about history size, and history size is not what a deletion
list deletes.

## A destructive transform needs a BASELINE run to diff against, not just an invariant to assert

A `--message-callback` for `git filter-repo` ended in an unconditional
`return message.rstrip() + b'\n'`. The intent was to strip AI-attribution
trailers from the 73 commit messages that carried them. What it actually did was
normalize trailing whitespace on **all 6,177** commit messages, because the
non-matching path fell through to the same return.

Git is content-addressed. Commit messages that had differed only in trailing
whitespace became byte-identical, and the commits COLLAPSED into single objects.
**93 commits disappeared, and 96 legitimate co-author trailers went with them.**

What did NOT catch it is the whole point of this entry. Nothing errored; the run
exited 0. `git count-objects -vH` reported a `size-pack` inside the expected
range. And the tree-identity control from the entry above -- the one that had
already proved itself by firing on a real casualty -- **PASSED**, because
`main^{tree}` is a property of the FINAL tree and says nothing whatever about
how many commits produced it. A control that has fired once is not thereby a
control for the next class of damage.

What caught it was a SECOND run to diff against: the media-only variant, with no
message callback at all. 6,174 commits against 6,081. Then tracing one named
victim through both: "Add captcha key" appeared twice before the rewrite and
once after.

Two rules come out of it. First, a callback must return the ORIGINAL BYTES when
nothing matched -- an unconditional normalisation at the end of a matcher is a
transform applied to the whole corpus wearing the costume of a filter. Second,
when a transform can delete, run the narrower variant too and DIFF THE COUNTS,
because the damage you did not anticipate is by construction the class your
invariant does not cover.

## A `pgrep -f <pattern>` guard inside a shell whose own command line contains that pattern waits forever

A background waiter written as

    until [ -f .../trial3.git/filter-repo/commit-map ] \
       && ! pgrep -f 'filter-repo.*trial3' >/dev/null; do sleep 8; done

ran for **317 minutes** after both of its conditions were factually satisfied. The
file had existed since 13:15 and no `filter-repo` process had run for hours.

`pgrep -f` matches against full command lines, and the *waiting shell's own*
command line contains the literal string `filter-repo.*trial3`, because the
pattern is part of the command being run. So `pgrep` always finds at least one
match -- itself -- the negation is permanently false, and the loop cannot exit.
Adding a second process (the `pgrep` in a later diagnostic) simply made it two.

Nothing looked wrong from outside. The Stop hook's own liveness check reported it
as `silent but its OS process is VERIFIED ALIVE (a loop that prints only at the
end is healthy)`, which is a correct reading of a loop that is genuinely running
and genuinely printing nothing. A stuck-forever loop and a patiently-waiting loop
are indistinguishable by liveness alone; only the exit CONDITION distinguishes
them, and nothing was checking it.

Two rules. First, never put a string in a `pgrep -f` pattern that also appears in
the command running it -- use `pgrep -f '[f]ilter-repo.*trial3'`, or match on a
pid file, or check the artifact instead of the process. Second, a waiter whose
condition has become true and which is still running is not "still working", it
is WEDGED; when a wait outlives the thing it waits for by an order of magnitude,
evaluate the condition by hand rather than trusting that it must still be false.

## A `cp -rs` mirror is a live handle on the real tree for every file you did not de-symlink

`cp -rs` populates a mirror with SYMLINKS back to the originals, which is exactly
what makes it a cheap way to build an isolation harness for mutation testing. It
is also why writing into that mirror edits the REAL FILE unless you replaced the
symlink first.

Live case, 2026-08-23: an agent building a mutation harness de-symlinked the
script under test but not the gate that exercised it, and a scripted edit to the
runner block followed the symlink and rewrote the real
`.ci/scripts/test/gates/test-backfill-commit-resolve.sh` in the working tree. It
surfaced one run later as `line 285: CASE: unbound variable`. The file was
untracked, so there was nothing to restore from; it had to be repaired forward.

Two things make this worth an entry rather than a shrug. First, the earlier
mutation sweeps in the same session were safe **by luck of habit, not by design**
-- the agent happened only to write to the file it had copied. Second, the damage
was silent at write time and only became visible on the next execution, so a
sweep that finished without re-running the gate would have shipped a corrupted
file as a passing one.

The rule: de-symlink EVERY file you intend to write, not just the one under test,
and verify the mirror with `find <mirror> -type l` before mutating anything. When
you do repair such a file, assert the repair mechanically -- the same session
proved its runner whole by checking that the set of declared `test_*` functions
equals the set invoked, which is a check that cannot be satisfied by eyeballing.

## A sandbox built by symlinking a repo can lose git entirely, and every verifying check then answers "no evidence"

The safe way to prove a control can FAIL is to mutate a copy rather than the
live tree, so a killed command cannot strand the mutation. Building that copy by
symlinking the repo and replacing one file is the obvious construction. In this
checkout it silently destroys git.

`.git` is not always a directory. In a SUBMODULE or worktree checkout it is a
small regular FILE containing a `gitdir:` line pointing elsewhere, often by a
RELATIVE path. This was found in a checkout where `.git` was 32 bytes reading
`gitdir: ../.git/modules/console`, because `console` was a submodule of a
monorepo. A standalone clone of the same repo has a real `.git` directory and
does NOT reproduce it, which is what makes this easy to dismiss as fixed.
Symlink that file into a sandbox and the RELATIVE path no longer resolves:

    $ git -C <sandbox> rev-parse --verify --quiet 444e9c09...^{object}
    fatal: not a git repository: <sandbox>/../.git/modules/console    # rc=128

Every git-verifying assertion in that sandbox now answers False. Paid for on
2026-08-23 while proving case `96b`, the control for `completion_evidence`, which
git-verifies hex candidates: the contaminated run reported `passed=781 failed=1`
with `96b` failing on `regression-real-sha-at-position-6 (got False)` -- which is
**byte-for-byte the result the genuine mutation produces**. Same case, same
count, same assertion. There is nothing in the output to tell the two apart, so
it would have shipped as proof that a fix worked.

What caught it was the fixture asserting its OWN premise. The case emits
`fixture-sha-actually-resolves` before anything depends on that SHA, and it
failed too -- an outcome the code under test cannot possibly cause. A precheck
that can only fail environmentally is how a contaminated run confesses.

Three rules. Write `.git` as a real file holding the ABSOLUTE gitdir. Run the
sandbox UNMUTATED first and require it to reproduce the live result exactly
(782/0 here) before mutating anything, because a sandbox is an instrument and an
unproven instrument yields unproven verdicts. And have every fixture assert its
own premises, so a broken world reds differently from a broken subject.

Contamination is SCOPED, so do not discard neighbouring results reflexively: the
sibling case `153f` ran in the same broken sandbox and its RED stood, because it
only parses a markdown file and never calls git. Ask what the case depends on.

## A detector can match its own prose

**A gate that greps for a dangerous construct will eventually match text that
merely LOOKS like that construct** — and it will name a file that is doing
nothing wrong. Three instances now, all on this repo's own gates:

- **`check-toolchain-pins.sh` A6** ("does this gate invoke a pinned tool?")
  flagged `check-shell-size.sh`. Its only matches were two `echo` lines
  *printing* the `# shellcheck extended-analysis=false` directive the gate tells
  you to add. It never invokes shellcheck.
- **`check-control-vacuity.sh`** ("does this control prove its plant landed?")
  flagged `check-devbox-exec.sh` and `check-shell-size.sh`. Their `sed` calls
  were `s/^/.../` — one indenting a message for display, one generating a fixture
  from `seq`. Neither mutates a copy of the subject, so neither has a plant that
  could fail to land.
- **`check-swallowed-failures.sh`** (2026-08-27), fired on
  `check-label-inventory.sh`'s label-drift capture — a capture that DOES check
  its own exit status (`|| drift_rc=$?` then `if [ "$drift_rc" -ne 0 ]`), the
  exact remedy the gate's own message recommends. The scanner folds a whole
  `VAR="$( <multi-line command> )"` into ONE logical line before matching
  `swallow_re` against it, so a COMMENT inside that same capture — explaining a
  *prior, already-fixed* incident by quoting its literal shape (`` `|| true` ``,
  `` `|| echo ""` ``) — made the current, correct capture match the pattern for
  the defect it was explaining. The fix text became indistinguishable from the
  bug it described.

A6 already stripped comments for exactly this reason ("judge the code, not the
words describing it"). **The lesson is that comments are not the only place prose
hides**: an echoed string is prose, a formatting pipe is not a mutation, a
generated fixture is not a copy of the source, and a comment inside a folded
multi-line capture is still inside the text the scanner matches against.

**Why it fools you rather than blocking you:** the gate is red, the finding names
a real file and a real line, and the fastest way to green is to do what it says.
All three could have been "satisfied" — by exempting the file, by cargo-culting a
proof-of-plant assertion into a display pipe, or by adding a waiver comment
excusing a capture that was never broken. Any of those would have gone green
while making the gate say something false, and left the detector wrong for the
next author.

**The check to run:** before satisfying a detector, ask whether the matched line
actually DOES the dangerous thing, or merely contains its shape. If a gate you
write greps for a construct, test it against its own documentation and its own
output strings. When writing a comment that explains a bug BY QUOTING its exact
syntax (`|| true`, `sys.exit(0)`, etc.), inside or near code a swallowed-failure
or a similar shape-matching scanner also reads, paraphrase the shape instead of
quoting it verbatim — "a no-op fallback", not `` `|| true` ``.

Operator ruling 2026-08-26 said revisit a meta-gate once a third instance
appeared; it has. Still not written here — each instance so far needed a
different, specific fix (strip comments, require a real mutation, paraphrase
instead of quote), so a single meta-gate would need to generalize across three
unrelated scanners rather than add one shared rule. Worth a session picking this
up deliberately rather than folding it into an unrelated fix.

## A gate green in CI can be red on every developer machine, because glibc collates by locale and codepoint order does not

`test-scope-gate-outputs.sh` compares a shell `sort` of the real scope engine's
output against a list ordered by node's `Array.prototype.sort()` (UTF-16 code
unit order). It was green on `ubuntu-latest` for 26 days and red on this session's
very first local run of it.

`en_US.UTF-8` glibc collation ignores `=` and `_` at the primary level, so
`run_e2e_k8s_ceph=false` collates as `rune2ek8scephfalse` and sorts BEFORE
`run_e2e_k8s=false` — while node's code-unit order puts the shorter prefix
first. Same 17 keys on both sides, transposed order, and the diff read like a
missing key (`run_e2e_k8s_multinode`) rather than what it actually was. CI never
saw it because `ubuntu-latest`'s runner environment collates by codepoint, so
the two orderings happen to agree there.

**Why it fools you rather than blocking you:** the failure output names a
specific key and looks exactly like "the scope engine forgot this job" — a
production-code bug in `scope-map.cjs`, the file that decides which CI jobs run.
Reading the diff, not the mechanism, sends you straight at the wrong file.
Confirmed: `scope-map.cjs` and `scope-shadow.sh` were both correct and
untouched; the entire defect was one bare `sort` in the test.

**The check to run:** when two lists built by DIFFERENT sorters (shell `sort`
vs. node/jq/python `.sort()`/a hand-written literal) are compared, and only ONE
locale reproduces a failure, suspect collation before suspecting either list's
content. `LC_ALL=C sort` fixes it: `locale -a` on this host confirms both
`C.utf8` and `en_US.utf8` exist, so the comparison is trivial —
`LC_ALL=en_US.UTF-8 bash <test>` vs `LC_ALL=C bash <test>` on the SAME
unmodified file. If only the first fails, the bug is collation, not content.

See `.ci/scripts/test/gates/test-scope-gate-outputs.sh:254` for the fixed
instance and `agent/PLAN-scope-gate-sort-collation.md` for the full trace.
