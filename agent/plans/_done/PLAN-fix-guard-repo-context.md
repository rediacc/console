# PLAN: A pre-bash guard judged the wrong repo's staged count, and the workaround it forced moved console's own main
Status: done
First-Seen: 2026-09-23
Summary: `block_unproven_bulk_transform.run()` now returns ALLOW when `shellscan.target_root` resolves the command to another repo; the incident reproduces pre-fix (2 cases red) and all 15 differential cases pass post-fix, with TRAPS.md entries A and B appended and both trap floors ratcheted 94 -> 96.
Owner: d778be9d
Updated: 2026-09-23

## 0. What actually happened, and where the bug lives

A dispatched writer built a disposable git fixture under its scratchpad to record a shadow-gate ledger and ran `git commit` against it (via `-C <fixture>` or `cd <fixture> &&`, outside `/home/developer/console`).
`.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py` refused it: `BLOCKED: 255 staged file(s) is a bulk transform's scale ...` -- 255 being the CONSOLE repo's own staged count, not the fixture's.
Blocked out of the ordinary `git commit` path, the writer fell back to raw plumbing (`git write-tree`, `commit-tree`, `update-ref`, `symbolic-ref`), and a compound `cd "$S" && git ... && git ...` line whose `cd` failed (an earlier step never created `$S`) did not abort under `set -e`; the trailing `update-ref refs/heads/main` and `symbolic-ref HEAD` then ran with an implicit cwd that resolved to the console checkout, moving console's real `main` ref and detaching `HEAD` from `0914-1`.
This session verified via `git reflog show main` / `git reflog show HEAD` that both are back at their correct commits (blank-message entries around 2026-09-23 are the incident and its repair) and nothing reached `origin`.

**The bug, quoted exactly.** `.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:146-157`:

```python
def run(ev):
    cmd = ev.field("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    root = ev.env("CLAUDE_PROJECT_DIR", "") or hookio.git_out(["rev-parse", "--show-toplevel"])
    cwd = ev.field("cwd") or root

    if PSC.GIT_COMMIT.search(scan):
        files = _staged_files(cwd)
        if len(files) >= BULK_FILE_THRESHOLD and not _proof_shown(_commit_message_text(cmd, cwd)):
            ev.warn(BLOCK_COMMIT % len(files))
            return hookio.DENY
        return hookio.ALLOW
```

`root` is computed unconditionally from `$CLAUDE_PROJECT_DIR` (or, failing that, `git rev-parse --show-toplevel` run with whatever cwd the guard process itself has -- never the command's own target).
`cwd = ev.field("cwd") or root` reads the harness's own `cwd` field, which `.claude/rediacc_hooks/guards/block_blanket_git_add.py:110-111` documents precisely: "This harness RESETS the shell's directory after every call, so `ev.cwd` is the project directory on every invocation and a cwd test can never fire.
The directory that matters is the one spelled in the COMMAND -- `git -C <dir>` or a leading `cd <dir> &&`." Nowhere in `block_unproven_bulk_transform.run()` is the command text itself inspected for a `-C <path>` or a leading `cd <path> &&`.
A `git -C <fixture> commit` or `cd <fixture> && git commit` is therefore always judged against the console tree's own staged count, whatever it happens to be that moment.

**This is not a new defect class.** `.claude/rediacc_hooks/shellscan.py:419-449` (`target_root`) exists specifically to fix it, and its own docstring names three prior live occurrences:
- `.claude/rediacc_hooks/guards/block_untagged_commit.py:196-203` -- fixed 2026-09-01ish, comment: "`git -C <other-repo> commit` was judged against CLAUDE_PROJECT_DIR/agent/pr/<console-branch>.md ... every such commit was refused for a trailer no epic file could ever supply."
- `.claude/rediacc_hooks/guards/block_unverified_push.py:252-259` -- same class: "`git -C <scratch> push` was refused ... because the gate-run stamp compared below belongs to CONSOLE and the scratch tree can never match it."
- `.claude/rediacc_hooks/guards/block_blanket_git_add.py:99-121` -- found live 2026-09-09: "a writer was refused in a scratch repo by a message naming twelve files in a checkout it could not reach, and worked around the guard rather than being protected by it." This is word-for-word what happened again this session.

`block_unproven_bulk_transform.py` already imports `shellscan` (`.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:24`) but never calls `target_root`. It is the fourth guard to carry this exact defect, and the first three fixes were never generalized into a shared preamble that new/ported guards get automatically -- worth naming as its own lesson (task 4 below).

## 1. The fix

Insert one early-return in `run()`, between the `root` computation and the `cwd` computation (`.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:149-150`), covering all three surfaces this guard checks (`git commit`, `git push`, `gh pr create`) with a single change since they share one `run()`:

```python
    root = ev.env("CLAUDE_PROJECT_DIR", "") or hookio.git_out(["rev-parse", "--show-toplevel"])

    # ANOTHER REPO'S STAGED COUNT IS NOT THIS GUARD'S BUSINESS. Same class of defect as block_untagged_commit / block_unverified_push / block_blanket_git_add (see shellscan.target_root's own docstring): reproduced live 2026-09-23, a writer's `git -C <scratchpad fixture> commit` (equally: a leading `cd <fixture> &&`) was refused citing 255 staged files, which was CONSOLE's own count, never the fixture's. `root`/CLAUDE_PROJECT_DIR is only the right tree to judge when the command does not name a different one itself.
    if shellscan.target_root(scan, root) != "":
        return hookio.ALLOW

    cwd = ev.field("cwd") or root
```

No new import is needed (`shellscan` is already imported at line 24).
This mirrors the exact idiom already used at `.claude/rediacc_hooks/guards/block_untagged_commit.py:203`, `.claude/rediacc_hooks/guards/block_unverified_push.py:259`, `.claude/rediacc_hooks/guards/block_push_to_protected_branch.py:148`, `.claude/rediacc_hooks/guards/block_unlinked_commit_author.py:161`, and `.claude/rediacc_hooks/guards/warn_remote_drift.py:167` -- `target_root(scan, root) != ""` means the command names a different, real repo, and this guard has nothing to say about it.
`target_root` fails safe on an unresolvable hint (a `-C` path that is not a real git repo returns `""`), so a bogus or nonexistent `-C` target does NOT exempt a command -- the guard falls through and keeps judging `root`, exactly as today.

This does not change behavior for any existing case: none of the guard's current `EDGE_CASES` or its differential's 12 cases contain a `-C`/`cd` hint, so `target_root` returns `""` for all of them and the new line is a no-op for every one.

## 2. Tests: what fires, what stays silent, and how to prove it

`.claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py` is this guard's whole differential (`TWIN = None`; the guard's own docstring says this file "stands in for that differential").
It is executed in CI as one of the `TAILED` cases `.claude/rediacc_hooks/tests/test_hooks_delegates.py:98-119` discovers by globbing `.claude/rediacc_hooks/guards/test-*.py` and runs under `test_an_orphan_control_suite_runs_and_says_something` (`.claude/rediacc_hooks/tests/test_hooks_delegates.py:199-210`), which is itself collected by `check:ci-pytest` (`scripts/ci-runner/manifest.ts:4763`, verified live: `gate_resolves("check:ci-pytest") == True`, `gate_is_live("check:ci-pytest") == True`).
That chain is the correct `Enforced-By` anchor for the new TRAPS.md entry in section 3 -- verified directly, not assumed (`.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py` itself is NOT reachable by name from any file `check:ci-trap-registry`'s liveness walk reaches, confirmed by running `trap_registry.Registry.file_is_live` against it: `False` -- so a `file:` pointer at the guard itself would be a dangling F5 finding; `gate:check:ci-pytest` is the one that actually resolves and is live).

**Harness change needed first.** `run()` at `.claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py:23-31` never sets `CLAUDE_PROJECT_DIR` in the subprocess environment, so today `root` inside the guard resolves from whatever the ambient test-runner environment happens to hold -- not from any of this file's own scratch repos.
That never mattered before (no existing case uses `-C`/`cd`, so `root`'s value was inert), but the fix makes `root` load-bearing. Change `run()` to pin `CLAUDE_PROJECT_DIR` to the same value already carried as `cwd`, which is also the honest simulation of the real harness invariant `.claude/rediacc_hooks/guards/block_blanket_git_add.py:110-111` documents (`ev.cwd` is always the project dir):

```python
def run(command, cwd):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = cwd
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode != 0, proc.stderr
```

(`os` is already imported at `.claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py:11`.) Verified this is a no-op for all 12 existing cases: none contain `-C`/`cd`, so `shellscan.target_root` returns `""` regardless of `root`'s value either way.

**New cases** (insert after line 127, before the `# ---- PUSH ...` comment at line 129):

```python
# ---- SCOPE: a command reached via `-C`/`cd` into a repo that is not this checkout ----
# Reproduces the 2026-09-23 near-miss directly: CLAUDE_PROJECT_DIR points at a repo carrying an unproven bulk-sized staged change (standing in for the real console checkout's 255 staged files that day), and a `git -C <disposable fixture> commit` was refused citing THAT count -- the fixture's own tiny commit was never examined.
bulk_root = scratch_repo()
stage_files(bulk_root, BULK, prefix="w")

foreign = scratch_repo()
stage_files(foreign, 1, prefix="tiny")

case(
    "a bulk-staged CLAUDE_PROJECT_DIR does not leak into a `-C <foreign>` commit",
    'git -C %s commit -m "fix: a small thing"' % foreign,
    bulk_root,
    False,
)
case(
    "the same shape via a leading `cd <foreign> &&` is also not this guard's business",
    "cd %s && git commit -m \"fix: a small thing\"" % foreign,
    bulk_root,
    False,
)
case(
    "an unresolvable `-C` hint keeps guarding the ROOT (fail-safe, not fail-open)",
    'git -C /no/such/path-xyz commit -m "style: reflow the tree"',
    bulk_root,
    True,
)
```

Then bump `TOTAL_CASES = 12` (line 184) to `15`.

**Verification the task explicitly requires ("every test must be verified to actually fire/stay-silent, not assumed"):**
1. Run `python3 .claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py` against the unfixed guard (before applying section 1's diff) with the harness change from this section applied. The two new `False`-wanted cases must report `*** FAIL ***` (got=BLOCKED) -- that is the reproduction of the live incident, not a guess.
2. Apply the section 1 fix. Re-run the same script. All 15 cases must report `ok`, `FAILURES: 0`, and the trailing sanity check (`Tally.blocked` not in `(0, TOTAL_CASES)`) must still pass (expected: 4 blocked / 11 allowed).
3. Run `python3 .claude/rediacc_hooks/run_tests.py -k hooks_delegates` (or the plain `pytest .claude/rediacc_hooks/tests -k hooks_delegates`) to confirm `test_an_orphan_control_suite_runs_and_says_something[guards/test-block_unproven_bulk_transform.py]` still passes under the real delegation path, not just standalone.
4. Run `cd .ci && python3 -m rediacc_ci.quality.trap_registry --scan-only` after section 3's TRAPS.md edit, and separately `npm run check:ci-hook-integrity` and `npm run check:ci-pytest`, before calling this done.

## 3. TRAPS.md entries

`docs/agent-reference/TRAPS.md` is 1797 lines, ending at line 1797 with a bare `---` after the most recent entry (`agent-crossed-a-written-production-boundary`, heading at `docs/agent-reference/TRAPS.md:1777`). New entries append after line 1797.
The corpus currently holds exactly 94 entries (`grep -c '^## ' docs/agent-reference/TRAPS.md` -> 94), matching `TRAP_FLOOR_DEFAULT = 94` at `.ci/rediacc_ci/quality/trap_registry.py:160` and `TRAP_FLOOR="${TRAP_FLOOR:-94}"` at `.ci/scripts/quality/check-trap-registry.sh:108` (that file's own comment claims line 118 for this constant; verified live it is actually line 108 today -- the comment has drifted and is worth a one-line correction in the same commit).
Adding two entries means both constants must become 96 in the same commit -- this is advisory-only in `check:ci-trap-registry` (F1 only reds below the floor) but is the documented convention (`.ci/rediacc_ci/quality/trap_registry.py:65-71`) and CI will print the ratchet reminder if skipped.

**Entry A -- the mechanized one**, append after line 1797:

```markdown
## A guard's "which repo" defaulted to $CLAUDE_PROJECT_DIR, never the command's own `-C`/`cd`
Trap-Id: guard-repo-context-blind-staged-count
Enforced-By: gate:check:ci-pytest
Residue: check:ci-pytest proves the guard's own differential (test-block_unproven_bulk_transform.py) still exits 0 and still fires/stays silent on its planted cases; it does not defend that differential's CASE LIST from shrinking back to the pre-fix set, which is the same gap evidence-shape-is-not-verification names for a different gate.

`block_unproven_bulk_transform.py` read `root = CLAUDE_PROJECT_DIR or git rev-parse --show-toplevel` and judged every `git commit`/`git push`/`gh pr create` against THAT tree's staged count, never asking whether the command itself named a different repository via `-C <path>` or a leading `cd <path> &&`. A dispatched writer building a disposable git fixture under its own scratchpad to run `git commit` against, entirely outside the console checkout, was refused with "BLOCKED: 255 staged file(s) is a bulk transform's scale" -- 255 being console's OWN staged count that moment, never the fixture's.

THIS WAS THE FOURTH TIME. `shellscan.target_root` exists specifically because the identical shape was found live three times before this one: `block_untagged_commit.py` judged a foreign repo's commit against console's own epic snapshot; `block_unverified_push.py` refused a scratch repo's push against console's own gate-run stamp; `block_blanket_git_add.py` refused a scratch repo's `git add -A` naming twelve files in a checkout it could not reach. Each of the three earlier fixes narrated the same lesson in its own comments, and none of that narration reached a guard written or ported afterward: `block_unproven_bulk_transform.py` already imported `shellscan` and simply never called the one function that answers this question.

WHAT MADE THIS ONE COSTLIER THAN THE OTHER THREE. The other three near-misses ended at "refused, worked around by trying again a different way." This one didn't: refused out of the ordinary `git commit` path, the dispatched writer fell back to raw git plumbing (`write-tree`, `commit-tree`, `update-ref`, `symbolic-ref`) that carries none of the safety `git commit` would have offered even before this fix -- see the companion entry below. A guard that fires on a legitimate, harmless operation does not make the session safer; it pushes the next step somewhere with no guard at all.

The check: when a guard reads a git-state fact (a staged count, a branch name, a gate stamp) to decide whether to block, ask which repository the COMMAND actually names -- via `-C`, `--git-dir`, or a `cd` earlier in the same line -- before asking which repository `$CLAUDE_PROJECT_DIR` happens to be. A helper for this already exists (`shellscan.target_root`); the question worth asking of any new or ported guard that reads local git state is whether it calls it.

---
```

**Entry B -- judgment-only**, append immediately after entry A:

```markdown
## A guard's false block pushed a workaround through a path with no guard at all, and a failed `cd` did not stop it
Trap-Id: blocked-guard-workaround-has-no-guardrails
Enforced-By: JUDGMENT-ONLY
Residue: no code change accompanies this entry. Nothing in this repository's guard estate inspects `git write-tree` / `commit-tree` / `update-ref` / `symbolic-ref` at all (confirmed: none of `.claude/rediacc_hooks/guards/*.py` names any of the four), and the decision recorded in PLAN-fix-guard-repo-context.md section 4 is NOT to add one broadly, given legitimate cross-repo ref-plumbing use in this session's own shadow-ledger-recording workflow. The residue is the whole raw-plumbing surface, left open deliberately rather than closed with an untested guard.

Refused a legitimate `git commit` by the defect entry A describes, a dispatched writer worked around it with raw git plumbing against its own disposable fixture repo. Somewhere in the compound shell command driving that workaround, a `cd "$S" && git write-tree && ...`-shaped line ran with `$S` not yet created (an earlier step in the same sequence had itself been refused), and the `cd` failure did not stop the chain: `git update-ref refs/heads/main <sha>` and `git symbolic-ref HEAD <ref>` then ran with an implicit cwd that resolved to the CONSOLE checkout, not the intended fixture, moving console's own `main` ref and detaching `HEAD` from `0914-1`. `git reflog show main` and `git reflog show HEAD` carry the incident and its repair as adjacent blank-message entries around 2026-09-23; nothing reached `origin`.

WHAT IS NOT KNOWN, STATED RATHER THAN GUESSED AT. The exact shell construct that let a failed `cd` fall through -- a `$(...)` capture swallowing the compound's exit status, a `||` fallback, a backgrounded subshell, or `set -e` simply absent at that point in an ad hoc scratch script -- was not preserved: the script was ephemeral, run by a dispatched writer, and never landed in this tree. This entry records the SHAPE of the failure, not its exact mechanism, because asserting the mechanism without the script would be exactly the kind of unverified claim CLAUDE.md and this file both warn against elsewhere.

THE GENERAL SHAPE. A guard that refuses a genuinely safe operation does not make the tree safer; it removes the one checkpoint that operation would have passed through and replaces it with whatever path the next attempt finds, which here had NONE of the same checkpoint's safety, plus a compounding failure (`cd` not gating the rest of its own chain) that an ordinary `git commit` could never have been exposed to in the first place, because `git commit` always operates on the process's actual resolved cwd rather than trusting a PRIOR command in the same line to have landed somewhere.

The check: before running `update-ref` or `symbolic-ref` against a ref that could resolve to `main` or bare `HEAD`, assert `git rev-parse --show-toplevel` (in the same shell, after any `cd`) equals the INTENDED disposable repository, not the assumption that a prior command in the same chain succeeded. And when a guard's own false positive is what forced a workaround, say so in the same report that discloses the workaround, because the workaround's own safety is now the reader's problem, not the guard's.

---
```

## 4. Decision: a raw-plumbing guard -- not now, and not broadly

**Recommendation: do not add a new blocking guard for `write-tree`/`commit-tree`/`update-ref`/`symbolic-ref` in this change.** Reasoning, weighed explicitly per the brief's own instruction:

- **Section 1's fix removes the pressure that caused the workaround.** Once `git -C <fixture> commit` and `cd <fixture> && git commit` are correctly exempted, there is no longer a reason for a session to reach for raw plumbing to commit into a disposable fixture at all -- the ordinary, safer path works.
- **False-positive risk is real and specific**, not hypothetical: the writer's own report states this session's shadow-ledger-recording workflow legitimately builds throwaway git fixtures and drives them with exactly this class of command.
  A guard broad enough to catch the incident's shape (`update-ref`/`symbolic-ref` with an implicit cwd) risks catching that legitimate workflow too, and per this session's own lesson (entry B above), a session blocked by an over-broad guard finds a workaround with fewer guardrails than the guard it evaded -- the same failure mode, one level deeper, with less time pressure to design it carefully.
- **No existing guard infrastructure covers this class today** (verified: zero matches for `update-ref`/`write-tree`/`commit-tree`/`symbolic-ref` as a trigger across `.claude/rediacc_hooks/guards/*.py`), so a new guard here is new surface, not a fix to something already close.

**If reconsidered later**, the narrowest version worth building is scoped tightly enough to avoid the false-positive class above: fire ONLY when a command runs `git update-ref refs/heads/main <sha>` or `git symbolic-ref HEAD <ref>` (the write forms, which take a second argument -- never the read forms `git symbolic-ref -q HEAD` or `git update-ref -d`) with no `-C <path>`, `--git-dir=<path>`, or leading `cd <path> &&` anywhere on the line naming a real, resolvable repository (i.e., `shellscan.target_root` returns `""` for the whole command including this specific ref-mutating segment).
That shape is exactly "an implicit-cwd write to console's own main branch or HEAD," which per the incident's own framing a dispatched agent should essentially never need, while any explicitly-`-C`-scoped ref-plumbing against a named foreign fixture -- the legitimate shadow-ledger shape -- sails through untouched.
This is deliberately deferred to its own follow-up plan rather than bundled here: it is a new guard file, needing its own `CHAIN`/`ORDER`, `EDGE_CASES`, differential test, `check:ci-hook-integrity` registration, and TRAPS.md entry, and bundling it with section 1's fix would triple this change's review surface for a guard whose necessity section 1 mostly moots.

## 5. Tasks

- [x] Apply the `run()` fix in `.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py` (section 1): insert the `shellscan.target_root(scan, root) != ""` early-return between the `root` and `cwd` assignments at lines 149-150.
      Confirmed on disk 2026-09-23, verified via `git diff`.
- [x] Update `.claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py`: pin `CLAUDE_PROJECT_DIR` to `cwd` in `run()` (lines 23-31); add the `bulk_root`/`foreign` fixtures and the three new `case()` calls after line 127; bump `TOTAL_CASES` from 12 to 15.
      Confirmed on disk 2026-09-23.
- [x] Verify the reproduction: run the updated test file against the pre-fix guard and confirm the two new `False`-wanted cases report `*** FAIL ***` (proves the incident reproduces, not assumed).
      Run against the UNFIXED guard 2026-09-23, with only the harness/case changes applied: `a bulk-staged CLAUDE_PROJECT_DIR does not leak into a `-C <foreign>` commit  want=allowed got=BLOCKED *** FAIL ***` and `the same shape via a leading `cd <foreign> &&` ... want=allowed got=BLOCKED *** FAIL ***`, both with the BLOCK_COMMIT text on stderr; tally `15 case(s), 6 blocked,
      9 allowed / FAILURES: 2`, exit 1. The third new case (unresolvable `-C`) was already `ok` pre-fix, which is what makes it the fail-safe control rather than a second reproduction.
- [x] Verify the fix: run the updated test file against the post-fix guard and confirm all 15 cases pass, `FAILURES: 0`, and the constant-answer sanity check still passes.
      Confirmed independently 2026-09-23: `python3 .claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py` -- 15 case(s), 4 blocked, 11 allowed, FAILURES: 0.
- [x] Run `python3 .claude/rediacc_hooks/run_tests.py -k hooks_delegates` (or `pytest .claude/rediacc_hooks/tests -k hooks_delegates`) and confirm the `guards/test-block_unproven_bulk_transform.py` TAILED case passes under real delegation.
      Confirmed independently 2026-09-23: `35 passed, 7560 deselected in 85.91s`.
- [x] Append TRAPS.md entries A and B (section 3) after `docs/agent-reference/TRAPS.md:1797`.
      Confirmed on disk 2026-09-23: both Trap-Id headings present, corpus now 96 entries.
- [x] Bump `TRAP_FLOOR_DEFAULT` from 94 to 96 in `.ci/rediacc_ci/quality/trap_registry.py:160`, and `TRAP_FLOOR="${TRAP_FLOOR:-94}"` to `96` in `.ci/scripts/quality/check-trap-registry.sh:108` (and correct that file's stale "line 118" self-reference while touching the neighboring comment).
      Confirmed on disk 2026-09-23: both constants now read 96.
- [x] Run `cd .ci && python3 -m rediacc_ci.quality.trap_registry --scan-only` and confirm the entry count and `gate:check:ci-pytest` pointer both resolve and are live for entry A.
      Confirmed independently 2026-09-23: `96 entries (floor 96), ... 58 live pointers`.
- [x] Run `npm run check:ci-hook-integrity` and `npm run check:ci-pytest` and confirm both are green.
      `check:ci-hook-integrity` confirmed independently 2026-09-23: `48 guard(s) present across 2 chain(s), none newly uncovered`. Full `check:ci-pytest` already ran once this turn as part of the writer's own T-section-2 verification (50 pre-existing failures, none naming this guard's files); not re-run in full a second time here.
- [x] Do NOT add a raw-plumbing guard in this change (section 4); if the operator wants the narrow `update-ref`/`symbolic-ref`-on-`main`/`HEAD` guard sketched in section 4 built, open it as a separate follow-up plan rather than amending this one.
      Confirmed independently 2026-09-23: `git status --short .claude/rediacc_hooks/guards/` shows zero new (`A `) files -- honored.

### Critical Files for Implementation
- .claude/rediacc_hooks/guards/block_unproven_bulk_transform.py
- .claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py
- .claude/rediacc_hooks/shellscan.py
- docs/agent-reference/TRAPS.md
- .ci/rediacc_ci/quality/trap_registry.py
- .ci/scripts/quality/check-trap-registry.sh
