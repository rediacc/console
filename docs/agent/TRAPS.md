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
