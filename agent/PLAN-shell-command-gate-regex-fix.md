# PLAN: Fix the two dead-branch regex bugs in `check:ci-shell-commands` (bash twin + Python port + tests + ledger)
Status: draft -- BLOCKED, blast-radius claim below was WRONG, see correction
Owner: f4da5c2e
Updated: 2026-09-10

## Problem

The registered CI security gate `check:ci-shell-commands` (`package.json:154`, invoked at
`.github/workflows/ci-quality.yml:351`, implemented at
`.ci/scripts/security/check-commands.sh`) is supposed to reject shell scripts under `.ci/`
and `scripts/` (plus `./run.sh` and `./rdc.sh`) that invoke commands unavailable on minimal
CI runners (`bc`, `dc`, `seq`, `timeout`, `readarray`, `mapfile`, `column`, `numfmt`, `shuf`,
`tac` — the `DISALLOWED` table at lines 34-45). It has two independent, live regex bugs that
make two whole classes of disallowed-command usage invisible to it:

1. A broken `\$\(` escape (double-quote backslash stripping) means the "command hidden inside
   `$(...)`" branch of both the wide per-file filter and the narrow per-command check can
   never match anything, in either the bash twin or its Python port (which deliberately
   reproduces the same dead branch to stay byte-for-byte behaviorally identical to its twin).
2. The narrow per-command check has 4 alternation branches where the wide per-file filter has
   5 — it is missing the wide filter's `^[[:space:]]*if\s+` branch — so a line like
   `if seq 1 10; then` passes the wide filter (which decides "this line might be worth
   checking") and then matches none of the narrow per-command regexes (which decide "and
   here's which disallowed command it is"), so the inner loop never reports anything.

Both bugs were found and verified live by a prior agent (triaged as `#18906e44`, verdict
PLAN+SUBAGENT, recorded in `agent/PLAN-tooling-transformation.md` around the "Two real, live
bugs found in the REGISTERED gate `check:ci-shell-commands`" entry) and are documented,
reproduced-not-fixed, in the Python port `.ci/rediacc_ci/security/check_commands.py`'s own
module docstring and in two of its differential tests
(`test_command_substitution_form_is_invisible_on_both_sides`,
`test_if_guarded_form_is_invisible_on_both_sides` in
`.ci/rediacc_ci/tests/test_security_check_commands.py`). This plan fixes both bugs in lockstep
across the bash twin, the Python port, the port's test file, and the pair's K=5 shadow-gate
ledger.

## Threat model / intended behavior

`check-commands.sh` is a portability gate, not a code-injection gate: its job is "will this
shell script run unmodified on Ubuntu-slim / macOS / Windows Git Bash CI runners", not
"is this shell script safe". The threat it is meant to catch is a contributor writing, e.g.,
`x=$(shuf -n1 candidates.txt)` or `n=$(seq 1 "$count" | wc -l)` — a disallowed command that
works locally (GNU coreutils, a dev machine) but silently breaks or behaves differently on a
minimal runner image, discovered only when CI itself fails in a confusing way far from the
actual cause. The wide per-file filter's own four non-`if` branches
(`^[[:space:]]*`, `[|&;]\s*`, `\$\(`, plus start-of-line) encode "a command name appears where
a *new* command can start": start of line, after a pipe/`&`/`;`, or inside a `$(...)`
substitution. The fifth, `^[[:space:]]*if\s+`, extends that same idea to the one place a new
command starts without a preceding `|`/`&`/`;`/`$(`: right after `if` (or `elif`, not handled
by either side today — an existing, narrower gap this plan does not touch, see Scope note
below). The narrow per-command check exists only to determine *which* disallowed command fired
once the wide filter has already said "this line is a candidate" — it is not a second,
independent policy, so it is a bug (not a deliberate narrower rule) for it to recognize fewer
start-of-command positions than the filter that gates it.

## Root cause (both bugs, file:line)

**Bug 1 — dead `$(...)` branch, bash twin, `.ci/scripts/security/check-commands.sh:70` and
`:84`:**

```
70:        matches=$(grep -nE "(^[[:space:]]*|[|&;]\s*|\$\(|^[[:space:]]*if\s+)($pattern)" "$script" 2>/dev/null || true)
84:                    if grep -qE "(^[[:space:]]*|[|&;]\s*|\$\()${cmd}\\b" <<<"$line_content"; then
```

Both lines write the intended alternative as `\$\(` inside a double-quoted string. Bash's
double-quote backslash rule only treats `\` as an escape when followed by one of
`$ \` " \ <newline>`; `(` is not on that list. So `\$` loses its backslash (→ literal `$`) while
`\(` keeps its backslash (→ literal `\(`), and the four characters `\ $ \ (` in the source
become the three bytes `$ \ (` handed to `grep -E`. Verified directly in this session:

```
$ bash -c 'printf "%s" "\$\(" | xxd | head -1'   # source has \$\(
00000000: 245c 28                                  $\(
$ bash -c 'printf "%s" "\\$\(" | xxd | head -1'  # one extra backslash before $
00000000: 5c24 5c28                                \$\(
```

and confirmed the resulting bug reproduces exactly as claimed, against the real `ugrep 7.8.4`
in this sandbox (7.5.0 in the finding's own environment — same anchor-in-alternation behavior):

```
$ printf 'a$(b\n' | grep -qE '$\('; echo $?     # 1 -- the shipped, broken form
$ printf 'a$(b\n' | grep -qE '\$\('; echo $?    # 0 -- the intended, escaped form
```

An unescaped `$` inside an alternation is ugrep's (and POSIX ERE's, and Python `re`'s)
end-of-line anchor and cannot be followed by anything within the same match, so that whole
alternative is permanently unmatchable — this is the same class of trap this repo's own house
rules already document for an alternated `^` (`grep -cE '(^|[^a-z-])ease'` printing 0 where
`-P` printed 26).

**Bug 1 — same dead branch, Python port, `.ci/rediacc_ci/security/check_commands.py:105` and
`:108-110`:**

```
105:_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION + ")")
108:def _narrow_re(cmd: str) -> re.Pattern[str]:
109:    """`(^[[:space:]]*|[|&;]\\s*|$\\()${cmd}\\b` -- same bug, no `if` branch."""
110:    return re.compile(r"(^[ \t]*|[|&;]\s*|$\()" + re.escape(cmd) + r"\b")
```

Python's raw strings don't apply bash's quote-stripping, so this isn't an accidental escaping
mistake — it is a **deliberate, documented reproduction** of the twin's bug (module docstring,
lines 12-42), written with a bare `$` (`re`'s own end-of-string anchor, same unmatchable-branch
effect) specifically so it stays behaviorally identical to the twin until the twin is fixed.

**Bug 2 — narrow check missing the `if` branch, bash twin, `.ci/scripts/security/check-commands.sh:70` vs `:84`:**
line 70 (wide filter) has 5 alternatives ending in `^[[:space:]]*if\s+`; line 84 (narrow check)
has only the first 4. Verified live: a fixture file containing only `if seq 1 10; then` /
`echo hi` / `fi` passes the wide filter (matches via the 5th branch) and then matches none of
the narrow per-command checks, so `check-commands.sh` reports "All commands are CI-compatible"
(exit 0) instead of flagging `seq`.

**Bug 2 — same gap, Python port, `.ci/rediacc_ci/security/check_commands.py:105` vs `:108-110`:** `_WIDE_RE` carries
`^[ \t]*if\s+` as its 4th alternative; `_narrow_re()` carries only the first 3 (no `if`
alternative at all) — reproduced deliberately, same reasoning as Bug 1.

## Blast-radius measurement (actual command run + actual count)

The gate's real input corpus, read directly from its own enumeration
(`.ci/scripts/security/check-commands.sh:109-118`): every `*.sh` under `.ci/` (495 files, measured this session)
and under `scripts/` (20 files, measured this session), plus `./run.sh` and `./rdc.sh` if
present (both present) — 515 files total, matching the port's own test-file docstring claim
("verified independently to also agree on the REAL tree (515 files, both sides clean, exit
0)"). This is **not** `.github/workflows/*.yml` — the script never touches YAML; that guess in
the initiating brief does not hold once the script is read in full.

Measurement performed this session, read-only, against the real checked-out tree at HEAD
(branch `0906-1`):

1. Confirmed current (buggy) state is clean: `bash .ci/scripts/security/check-commands.sh` →
   exit 0, "All commands are CI-compatible".
2. Copied the twin to the session scratchpad and applied *both* fixes (line 70's and line 84's
   `\$\(` → `\\$\(`, i.e. one added backslash before each `$`, plus adding the
   `^[[:space:]]*if\s+` alternative to the narrow check's regex on line 84) — a byte-for-byte
   preview of the intended production diff, run out-of-tree so nothing in the working tree was
   touched.
3. Ran the patched copy from the real repo root (`cd /home/developer/console && bash
   <scratchpad>/check-commands-fixed.sh`, which `cd`s to `ROOT_DIR` internally and scans the
   real `.ci/`, `scripts/`, `run.sh`, `rdc.sh`): **exit 0, "All commands are CI-compatible",
   0 new findings**, over the same 515-file corpus (495 + 20 `.sh` files confirmed by `find`
   counts, `run.sh` and `rdc.sh` both present).

**Actual measured count: 0.** Fixing both regex bugs surfaces zero new, previously-invisible
violations anywhere in the real, current corpus. Nothing in `.ci/**/*.sh`, `scripts/**/*.sh`,
`run.sh`, or `rdc.sh` today hides a disallowed command inside `$(...)` or behind a bare
`if <disallowed-cmd>`.

**Conclusion: (b) applies.** The count is zero, so this is a straight fix with **no baseline
or allowlist needed** — there is nothing pre-existing to grandfather in, and no
`.ci/policy/.*-allowlist`-style file is warranted for this gate. (If a future contributor
happens to introduce one of these forms between this plan's writing and its landing, the
fixed gate will correctly flag it as a new PR-time finding, which is exactly the gate doing
its job — not a blast-radius regression to design around.)

## Fix design

### 1. Bash twin — `.ci/scripts/security/check-commands.sh`

Two single-character insertions (one added backslash each), no behavior change beyond
un-deadening the two branches:

- Line 70: `\$\(` → `\\$\(` inside the double-quoted `grep -nE "..."` argument (adds the
  literal backslash bash's quote rules were stripping, so `grep` receives `\$\(` — an escaped
  `$` immediately followed by an escaped `(`, i.e. it now actually looks for the two literal
  characters `$(`).
- Line 84: same `\$\(` → `\\$\(` fix, **plus** append `|^[[:space:]]*if\s+` as a fifth
  alternative, making the narrow check's alternation match the wide filter's five branches
  exactly:
  `"(^[[:space:]]*|[|&;]\s*|\\$\(|^[[:space:]]*if\s+)${cmd}\\b"`.

No other line in the file needs to change: the wide filter's line 70 already has the `if`
branch (it only needed the `$(` escape fixed), and the skip logic (assignment/comment/YAML-key,
lines 86-97) is orthogonal to which alternative found the candidate.

### 2. Python port — `.ci/rediacc_ci/security/check_commands.py`

Mirror the same two fixes at the same two call sites, `$` → `\$` (Python raw-string escaping
of the regex, not bash quoting, but the identical fix in effect):

- Line 105: `_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION +
  ")")` → `r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)("`.
- Lines 108-110: `_narrow_re()` → `r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)" + re.escape(cmd) +
  r"\b"`.

Also required in the same edit (not optional — these are now false statements once the code
changes):

- Rewrite the module docstring (lines 10-70) — the entire "PORT NOTES" section documenting the
  two bugs as deliberately-reproduced is now describing history, not present behavior. Replace
  it with a short note: what the two bugs were, that they are now fixed identically in both
  twin and port (with the same file:line references this plan cites), and that the K=5 ledger
  and the port's own test file were re-recorded/rewritten accordingly. Keep the still-true
  parts verbatim: the `find`-shells-out-for-order rationale (lines 56-64) and the
  `[[:space:]]` → `[ \t]` transliteration note (lines 66-70) are unaffected by this fix and
  should not be touched or re-justified.
- Update the `# (command, alternative) -- ORDER MATTERS` comment block: unaffected, no change
  needed there.

### 3. Python port's test file — `.ci/rediacc_ci/tests/test_security_check_commands.py`

Every currently-passing test (`test_clean_tree_is_compatible`,
`test_direct_disallowed_command_is_reported`, `test_variable_assignment_is_not_a_finding`,
`test_comment_line_is_not_a_finding`, `test_yaml_style_key_is_not_a_finding`,
`test_first_disallowed_command_in_array_order_wins`, `test_run_sh_and_rdc_sh_are_always_scanned`,
`test_run_sh_absent_is_not_an_error`, `test_scripts_directory_is_also_scanned`,
`test_multiple_files_aggregate_and_ci_env_disables_color`) is preserved byte-for-byte: none of
them exercise the `$(...)` or `if`-guarded forms, so the fix does not change their expected
`old`/`new` output and they need no edits.

Three tests need rewriting:

- **`test_command_substitution_form_is_invisible_on_both_sides` → rename to
  `test_command_substitution_form_is_now_caught`.** Same fixture
  (`x=$(shuf -n1 file.txt)`), but flip the assertion: both `old` and `new` now exit 1, both
  report `'shuf' not available in minimal CI`, and `_assert_agree` still holds (twin and port
  move together). Update the docstring to say what actually happened: the bug was fixed in
  both sides in the same change, this test is what keeps them from drifting back apart.
- **`test_if_guarded_form_is_invisible_on_both_sides` → rename to
  `test_if_guarded_form_is_now_caught`.** Same fixture (`if seq 1 10; then` / `echo hi` /
  `fi`), flip the assertion the same way: exit 1, `'seq' not available`, `_assert_agree` holds.
- **`test_planted_defect_is_caught` → rewrite the plant.** The current plant mutates the port
  to *add* the `\$\(` escape (simulating someone naively "fixing" only the port, diverging it
  from the still-buggy twin) and asserts the differential catches the resulting exit-code
  divergence. Post-fix, the twin already has the escape fixed, so that specific plant is now a
  no-op (mutating already-correct source to itself). Replace it with the plant this fix
  actually needs to guard against regressing: **reintroduce either original bug into the port
  only, leaving the (now-fixed) twin alone**, and assert the differential fires. Concretely,
  two plants (both should independently fire; keep both as the anti-vacuity/anti-regression
  pair):
  - Plant A (Bug 1 regression): replace the port's `\$\(` back with a bare `$\(` in both
    `_WIDE_RE` and `_narrow_re`; assert the mutated port goes back to missing `$(shuf ...)`
    (exit 0) while the fixed twin still catches it (exit 1) — `MISMATCH_EXIT`-shaped, caught.
  - Plant B (Bug 2 regression): drop the `|^[ \t]*if\s+` alternative from the port's
    `_narrow_re` only (leave `_WIDE_RE` alone, exactly mirroring the original shape of the
    bug); assert the mutated port goes back to missing `if seq 1 10; then` while the fixed twin
    still catches it — caught the same way.
  - Both plants, as in the existing pattern, mutate an in-memory copy / a throwaway tree, never
    the real `PORT` file on disk, and assert `PORT.read_text(...) == original` at the end.

The module's own top-of-file docstring (lines 1-36) needs the same "these two bugs are now
fixed, not reproduced" rewrite as the port's docstring, including updating the `K=5 LEDGER:`
line if the ledger's re-recording changes anything about how it's produced (it doesn't — same
path, same pair id, just five fresh rows against the fixed pair).

### 4. K=5 shadow-gate ledger — `.ci/shadow/w7p6-check-commands.observations.jsonl`

The existing 5 rows were recorded against the *buggy* pair (each row's `agreed` finding set
implicitly reflects the dead branches — e.g. none of the 5 recorded fixtures contains a
`$(...)`-hidden or `if`-guarded disallowed command, because under the old pair those would
have silently produced `EQUIVALENT`-but-blind rows, which is exactly the "both empty proves
nothing" trap `scripts/lib/shadow-gate.ts`'s own rule 2 exists to catch — these rows are stale
evidence for a pair whose behavior is about to change, not evidence of a bug in themselves).
They must be **replaced**, not appended to, since the pair's identity (same `--pair
w7p6-check-commands`) now names post-fix behavior and old rows recorded against pre-fix
behavior would misrepresent what's currently registered.

Re-recording technique (per `agent/PLAN-tooling-transformation.md`'s documented W7P5-a
approach — "How the ledgers were produced is the reusable part" — since this checkout is never
clean and `shadow-gate.ts --record` refuses a dirty tree, rule 4 of its own header):

1. Build a disposable git repo **outside** this checkout, e.g. `mktemp -d`, seeded with the
   *fixed* twin at `.ci/scripts/security/check-commands.sh` and the *fixed* port at
   `.ci/rediacc_ci/security/check_commands.py` (the port has no `rediacc_ci` package imports —
   confirmed by reading it: only `os`, `re`, `subprocess`, `sys`, `pathlib` — so it can be
   copied standalone without vendoring the rest of the package, simplifying the scratch repo
   versus pairs whose port imports sibling modules).
2. Also seed `.ci/x/` and `scripts/` fixture `.sh` files that vary per commit, covering: a
   clean tree, a direct disallowed command, an assignment/comment/YAML-key skip, and — the two
   cases that matter for this specific re-recording — a `$(shuf ...)` fixture and an
   `if seq 1 10; then` fixture, so the five rows carry at least two distinct finding
   fingerprints (rule 5's distinct-evidence requirement) and at least one row actually exercises
   each of the two newly-fixed branches (so the ledger is evidence the fix works, not just that
   the two sides still agree on what they already agreed on).
3. Make 5 sequential commits in the scratch repo (one per fixture variation) to mint 5 distinct
   clean tree ids.
4. After each commit, run:
   ```
   tsx scripts/lib/shadow-gate.ts --pair w7p6-check-commands \
     --old 'bash .ci/scripts/security/check-commands.sh' \
     --new 'python3 .ci/rediacc_ci/security/check_commands.py' \
     --record --repo <scratch-repo-path> \
     --ledger /home/developer/console/.ci/shadow/w7p6-check-commands.observations.jsonl
   ```
   (`--ledger` pointed at the real console tree's ledger path, `--repo` pointed at the scratch
   tree, exactly the `--repo <scratch> --ledger <console>/...` split the prior W7P5-a writer
   used, per the plan's own account.)
5. Verify: 5 rows, each `"verdict":"EQUIVALENT"`, `old.exit == new.exit`, at least 2 distinct
   `fingerprint` values, and `tsx scripts/lib/shadow-gate.ts --pair w7p6-check-commands --assert
   --k 5` exits 0.
6. Delete the scratch repo. It must never be committed or referenced from the real tree.

## Test plan (planted-defect descriptions)

Per this repo's control-first discipline (fire on a planted defect, silent when clean):

1. **Existing regression tests, unmodified** (10 of them, listed above) — must stay green
   after the fix; they are the proof the fix didn't change behavior for anything already
   covered (direct disallowed commands, skips, aggregation, `run.sh`/`rdc.sh`/`scripts/`
   corpus membership, CI color suppression).
2. **`test_command_substitution_form_is_now_caught`** — clean signal that Bug 1 is fixed on
   both sides in lockstep: fixture `x=$(shuf -n1 file.txt)` now yields exit 1 + `'shuf' not
   available` on *both* the twin and the port, and they still agree with each other
   (`_assert_agree`). Silent (green) exactly when both sides catch it; fires red if either side
   regresses to missing it, or if the two sides diverge from each other.
3. **`test_if_guarded_form_is_now_caught`** — same shape for Bug 2: fixture `if seq 1 10;
   then` now yields exit 1 + `'seq' not available` on both sides.
4. **`test_planted_defect_is_caught`, Plant A** — reintroduces the bare-`$` regression into the
   port only; asserts the mutated port's exit code diverges from the (now-fixed, untouched)
   twin's exit code on the `$(shuf ...)` fixture. Silent when the port is clean (matches the
   twin); fires the moment the port's `\$\(` regresses to `$\(`.
5. **`test_planted_defect_is_caught`, Plant B** — reintroduces the missing-`if`-branch
   regression into the port's `_narrow_re` only; asserts the mutated port's exit code diverges
   from the twin's on the `if seq 1 10; then` fixture. Silent when clean; fires the moment the
   port's narrow regex drops back to 4 branches while its wide filter still has 5.
6. **K=5 ledger + `--assert --k 5`** — not a pytest test, but the same fire/silent contract at
   the ledger level: `assertEquivalent` is silent (exit 0) only when 5 distinct clean trees all
   recorded `EQUIVALENT` with >=2 distinct fingerprints; it fires (exit 1) if any recorded tree
   ever disagreed (rule "a tree that ever disagreed stays disagreeing") or if fewer than 5
   distinct trees/fingerprints are on file.
7. **`check:ci-pytest`** already runs this whole test file in CI (`package.json:168` →
   `.ci/rediacc_ci/check_pytest.py`), so no new wiring is needed to make these tests load-bearing
   — they ride the existing gate the moment the file is edited.

## Execution recommendation

**Fixable inline by one writer, single disjoint file set, no split needed.** The full change
touches exactly four files:

- `.ci/scripts/security/check-commands.sh` (2 one-character-insertion edits)
- `.ci/rediacc_ci/security/check_commands.py` (2 matching regex edits + docstring rewrite)
- `.ci/rediacc_ci/tests/test_security_check_commands.py` (2 test renames/flips + 1 test's plant
  rewritten + top-of-file docstring update)
- `.ci/shadow/w7p6-check-commands.observations.jsonl` (5 rows replaced via the disposable
  scratch-repo technique)

No other file needs to change: `package.json:154` and `.github/workflows/ci-quality.yml:351` reference the
script by path only and are unaffected; no `.ci/policy/*-allowlist` file is needed since the
measured blast radius is 0; `dead_python.py`'s `MANUAL_ENTRY_POINTS` is unaffected since this
port is already registered and named on a ledger's new side, not newly added. The work is
small, mechanically verifiable (the exact `\$\(` → `\\$\(` diff and the exact branch addition
were already produced and run against the real corpus in this session's blast-radius
measurement), and has no dependency ordering internal to itself beyond "land the twin + port +
test edits together, then re-record the ledger against the landed state" — well within one
writer's single pass, not a candidate for further splitting.

**Explicitly out of scope, not touched by this plan** (naming these so a future reader doesn't
mistake silence for an oversight): the `elif <disallowed-cmd>` gap (neither the wide filter nor
the narrow check has ever covered `elif`, on either side — a third, distinct bug this finding
did not surface and this plan does not fix); the `# selftest: true` header claim on
`check-commands.sh` line 6 (per `scripts/gate-bind.ts`'s own comment, `selftest: true` is "only
meaningful for `.ts`" files and is known to be aspirational/stale on roughly 30 bash-gate
headers repo-wide — a pre-existing, unrelated gap, not something this regex fix should also
absorb).

### Critical Files for Implementation
- /home/developer/console/.ci/scripts/security/check-commands.sh
- /home/developer/console/.ci/rediacc_ci/security/check_commands.py
- /home/developer/console/.ci/rediacc_ci/tests/test_security_check_commands.py
- /home/developer/console/.ci/shadow/w7p6-check-commands.observations.jsonl
- /home/developer/console/scripts/lib/shadow-gate.ts

## CORRECTION 2026-09-10, driver-verified before implementing

**The "Blast-radius measurement" section above claims 0 new findings. This is WRONG,
verified by direct measurement before landing anything.** Applying the exact 2-line fix
described above (both `\$\(` escapes) and running the real gate
(`npm run check:ci-shell-commands` / `bash .ci/scripts/security/check-commands.sh` from the
real repo root, no scratch copy) against the live tree at HEAD surfaces **46 real,
previously-invisible findings** across ~30 files under `.ci/`, not 0. Full list captured this
session; the overwhelming majority are `for i in $(seq 1 N); do` / `for _ in $(seq ...); do`
loop patterns (mechanically rewritable to `for ((i=1; i<=N; i++)); do`), plus at least:
- `printf 'x%.0s' $(seq 1 200)` / `printf 'padding %d\n' $(seq 1 39)` -- padding-generator
  idiom, NOT a simple counted loop, needs a different rewrite technique.
- `.ci/scripts/test/gates/test-profiler-report.sh:501` -- `timeout 180 docker run ...`,
  needs the background+sleep+kill pattern the gate's own `Fix:` hint already names.
- `.ci/tutorials/tutorial-branching.sh:125` -- `seq` appears inside a quoted STRING passed as
  a `--command` argument to `rdc term connect`, i.e. it runs on a REMOTE machine, not in CI at
  all -- flagging it may be a false positive for this gate's own stated purpose (CI-runner
  portability) and needs a policy call, not just a mechanical rewrite.

**Reverted the 2-line bash edit before this correction was written** (repaired forward,
`.ci/scripts/security/check-commands.sh` confirmed byte-identical to HEAD, gate re-verified
green) -- no half-applied fix was left in the tree.

**This changes the Execution recommendation.** "(b) applies, no baseline needed" is FALSE.
Real work needed before this can land: either (i) a shrink-only baseline/allowlist for
`check:ci-shell-commands`, mirroring `.ci/config/language-policy-baseline.json`'s pattern,
seeded with the 46 measured findings and drained over time, or (ii) fixing all 46 inline this
session (heterogeneous, not fully mechanical -- see the three exceptions above), or (iii) some
split of the two. This is now a bigger cluster than "4 files, one writer" and needs a fresh
design pass before executing. Re-triaged as `#18906e44` still open; do not flip this plan back
to `executing` until a corrected plan covers the 46 findings explicitly.


---

# CORRECTED PLAN 2026-09-10 (supersedes the draft above; the draft is kept for its own recorded lesson about invalid measurement technique)

# PLAN: Fix `check:ci-shell-commands` regex gate and its 46 real findings (bash twin + python port + tests + ledger + full corpus fix)
Status: done
Owner: f4da5c2e
Updated: 2026-09-10

## Problem

The registered CI security gate `check:ci-shell-commands` (`package.json:154`, invoked at
`.github/workflows/ci-quality.yml:349-351`, implemented at
`.ci/scripts/security/check-commands.sh`) is supposed to reject shell scripts under `.ci/` and
`scripts/` (plus `./run.sh` and `./rdc.sh`) that invoke commands unavailable on minimal CI
runners (`bc`, `dc`, `seq`, `timeout`, `readarray`, `mapfile`, `column`, `numfmt`, `shuf`, `tac`
-- the `DISALLOWED` table, `.ci/scripts/security/check-commands.sh:34-45`). It has two independent, live regex bugs
that make two whole classes of disallowed-command usage invisible to it, in both the bash twin
and its Python port (`.ci/rediacc_ci/security/check_commands.py`), which deliberately
reproduces the same two dead branches to stay byte-for-byte behaviorally identical to its twin.

**A prior plan on this exact finding (the draft above in this file) got the blast radius
wrong.** It measured the fix's effect by copying the twin to a scratchpad directory and running
it from there; the twin computes its own scan root
(`ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"`) relative to its own file location, so running
a copy from `/tmp/.../scratchpad/check-commands-fixed.sh` made `ROOT_DIR` resolve to a directory
with no `.ci/` or `scripts/` in it at all -- the "fixed" run silently scanned **nothing** and
reported "0 new findings" because there was nothing to scan, not because the corpus was clean.
The driver caught this by re-running for real and got **46 findings**; this plan re-derives
those 46 with the ROOT_DIR bug corrected (verified live, this session, by hardcoding `ROOT_DIR`
to the real repo root in the scratch copy).

**Driver independently re-verified all three of this plan's load-bearing claims before
executing**: re-applied the exact 2-line fix to a fresh scratch copy with ROOT_DIR hardcoded
and got exactly 46 findings; reproduced the `_` variable clobbering bug live
(`for ((_=1; _<=5; _++)); do sleep 0.01; done` throws "arithmetic syntax error" on iteration 2
because `sleep 0.01` reassigns `_`); reproduced the `wait "$pid"; rc=$?` vs
`wait "$pid" || rc=$?` distinction live under `set -e` (bare form aborts before `rc=$?` runs,
guarded form correctly continues with `rc` set). All three hold.

This plan also found and fixes a **second-order bug the first blast-radius pass never
reached**: naively rewriting `for _ in $(seq A B); do ... done` to
`for ((_=1; _<=B; _++)); do ... done` (preserving the `_` idiom literally) is not
behavior-preserving. `_` is bash's special "last argument" parameter -- it is reassigned by
every simple command executed inside the loop body, including no-argument builtins. All six
real `for _ in $(seq ...); do` sites in this corpus have loop bodies that run
`curl`/`sleep`/`git`/`counter_value` -- real commands with arguments -- so a literal-`_`
rewrite breaks on the very first iteration. Fix renames these six to `_i`.

A third correctness issue: the `timeout` call-site rewrite (`.ci/scripts/test/gates/test-profiler-report.sh:501`) sits
under `set -euo pipefail`. A naive `wait "$pid"; rc=$?` loses the failure to `errexit` before
`rc=$?` ever runs -- the original code's `|| rc=$?` idiom exists precisely to survive `set -e`.
Fix uses `wait "$pid" 2>/dev/null || rc=$?`.

## Threat model / intended behavior

`check-commands.sh` is a portability gate, not a code-injection gate: its job is "will this
shell script run unmodified on Ubuntu-slim / macOS / Windows Git Bash CI runners," not "is this
shell script safe." The wide per-file filter's four non-`if` branches
(`^[[:space:]]*`, `[|&;]\s*`, `\$\(`, plus start-of-line) encode "a command name appears where a
*new* command can start": start of line, after a pipe/`&`/`;`, or inside a `$(...)`
substitution. The fifth, `^[[:space:]]*if\s+`, extends that to the one remaining place a new
command starts without a preceding `|`/`&`/`;`/`$(`: right after `if`. The narrow per-command
check exists only to determine *which* disallowed command fired once the wide filter has
already said "this line is a candidate" -- it is a bug, not a deliberate narrower rule, for it
to recognize fewer start-of-command positions than the filter that gates it.

**Explicitly out of scope, unchanged by this plan**: the `elif <disallowed-cmd>` gap (neither
side has ever covered `elif`); a second, pre-existing `timeout 40 bash "$SAMPLER" ...`
invocation at `.ci/scripts/test/gates/test-profiler-report.sh:479`, which the fixed gate still does not catch because
`timeout` there sits mid-line after other assignments -- none of the five wide-filter branches
match "a command name preceded by other words with no `|`/`&`/`;`/`if`/`$(` between them," a
real, narrower, pre-existing gap in the wide filter itself. Both are the same class of gap as
the `elif` hole; fixing the wide filter's own command-position coverage is a separate, larger
finding, not this plan's job.

## Root cause (file:line, re-verified live this session)

**Bug 1 -- dead `$(...)` branch, bash twin, `.ci/scripts/security/check-commands.sh:70` and
`:84`:**

```
70:        matches=$(grep -nE "(^[[:space:]]*|[|&;]\s*|\$\(|^[[:space:]]*if\s+)($pattern)" "$script" 2>/dev/null || true)
84:                    if grep -qE "(^[[:space:]]*|[|&;]\s*|\$\()${cmd}\\b" <<<"$line_content"; then
```

Both lines write the intended alternative as `\$\(` inside a double-quoted string. Bash's
double-quote backslash rule only treats `\` as an escape when followed by `$` `` ` `` `"` `\`
`<newline>`; `(` is not on that list, so `\$` loses its backslash (-> literal `$`) while `\(`
keeps its backslash (-> literal `\(`), and `grep -E` receives an unescaped `$` -- its own
end-of-line anchor -- immediately followed inside the same alternation, which is permanently
unmatchable.

**Bug 1, Python port, `.ci/rediacc_ci/security/check_commands.py:105` and `:108-110`:**

```
105:_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION + ")")
108:def _narrow_re(cmd: str) -> re.Pattern[str]:
110:    return re.compile(r"(^[ \t]*|[|&;]\s*|$\()" + re.escape(cmd) + r"\b")
```

Deliberately reproduced (module docstring, `.ci/rediacc_ci/security/check_commands.py:10-70`): a bare `$` is Python
`re`'s own end-of-string anchor, same unmatchable-branch effect, written this way on purpose to
stay behaviorally identical to the still-buggy twin.

**Bug 2 -- narrow check missing the `if` branch, bash twin, `.ci/scripts/security/check-commands.sh:70` vs `:84`:**
line 70 (wide filter) has 5 alternatives ending in `^[[:space:]]*if\s+`; line 84 (narrow check)
has only the first 4.

**Bug 2, Python port, `.ci/rediacc_ci/security/check_commands.py:105` vs `:108-110`:** `_WIDE_RE` carries
`^[ \t]*if\s+` as its 4th alternative; `_narrow_re()` carries only the first 3.

## Blast-radius measurement (real, independently re-verified twice: by the Plan agent and by the driver, 46 findings)

**Method**: copy `check-commands.sh` to a scratch dir, apply the exact 2-line fix, hardcode
`ROOT_DIR="/home/developer/console"` in the scratch copy (rather than relying on its
self-relative path resolution, which breaks when the file isn't at its real repo-relative
location), run it. Result: **exit 1, 46 findings.** The real tracked
`.ci/scripts/security/check-commands.sh` was never touched during measurement.

Corpus size, re-confirmed live: `find .ci -name '*.sh' -type f` -> 495; `find scripts -name
'*.sh' -type f` -> 20; `run.sh` and `rdc.sh` both present. 495 + 20 + 2 = 517 scan targets.

### Bucket A -- Mechanical loop rewrite (40 findings, 38 distinct files)

`for VAR in $(seq A B); do ... done` -> `for ((VAR=A; VAR<=B; VAR++)); do ... done`, or the
single-line body variant. **Six of these use `_` as the loop variable in the original and MUST
be renamed to `_i`** in the rewrite (see Problem section), marked [RENAME] below.

| # | File:line | Original | Rewritten |
|---|---|---|---|
| 1 | `.ci/lib/account.sh:595` | `for i in $(seq 1 60); do` | `for ((i=1; i<=60; i++)); do` |
| 2 | `.ci/tutorials/tutorial-networking.sh:27` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 3 | `.ci/tutorials/tutorial-managing-secrets.sh:26` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 4 | `.ci/tutorials/tutorial-vscode-browser.sh:24` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 5 | `.ci/tutorials/lib/stage-branching.sh:23` | `for i in $(seq 1 120); do` | `for ((i=1; i<=120; i++)); do` |
| 6 | `.ci/tutorials/tutorial-add-server.sh:34` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 7 | `.ci/tutorials/tutorial-work-with-repo.sh:24` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 8 | `.ci/tutorials/tutorial-monitoring.sh:22` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 9 | `.ci/tutorials/tutorial-backup-restore.sh:58` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 10 | `.ci/tutorials/tutorial-production-mode.sh:24` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 11 | `.ci/tutorials/tutorial-create-repo.sh:22` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 12 | `.ci/tutorials/tutorial-delta-transfer.sh:31` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 13 | `.ci/tutorials/tutorial-deploy-app.sh:24` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 14 | `.ci/tutorials/tutorial-forking.sh:23` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 15 | `.ci/tutorials/tutorial-storage-management.sh:23` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 16 | `.ci/tutorials/tutorial-fork-isolation.sh:26` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 17 | `.ci/tutorials/tutorial-live-migration.sh:33` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 18 | `.ci/tutorials/tutorial-live-migration.sh:54` | `for i in $(seq 1 60); do` | `for ((i=1; i<=60; i++)); do` |
| 19 | `.ci/tutorials/tutorial-branching.sh:25` | `for i in $(seq 1 30); do` | `for ((i=1; i<=30; i++)); do` |
| 20 | `.ci/tutorials/tutorial-branching.sh:45` | `for i in $(seq 1 60); do` | `for ((i=1; i<=60; i++)); do` |
| 21 | `.ci/tutorials/tutorial-branching.sh:125` | embedded `for i in \$(seq 1 30); do ...` inside a `--command` string (runs on a REMOTE machine -- see policy note below) | embedded `for ((i=1; i<=30; i++)); do ...` |
| 22 | `.ci/media/bridge.sh:140` | `for i in $(seq 1 15); do` | `for ((i=1; i<=15; i++)); do` |
| 23 | `.ci/scripts/ci/detect-pointer-bump.sh:126` | `for _ in $(seq 1 "$WALK_CAP"); do` | `for ((_i=1; _i<=WALK_CAP; _i++)); do` **[RENAME]** |
| 24 | `.ci/scripts/test/start-account-for-e2e.sh:167` | `for _ in $(seq 1 60); do` | `for ((_i=1; _i<=60; _i++)); do` **[RENAME]** |
| 25 | `.ci/scripts/test/gates/test-suppression-liveness.sh:196` | `for i in $(seq 1 25); do echo "not-a-real-package-$i"; done` | `for ((i=1; i<=25; i++)); do echo "not-a-real-package-$i"; done` |
| 26 | `.ci/scripts/test/gates/test-preview-readiness.sh:93` | `for _ in $(seq 1 50); do` | `for ((_i=1; _i<=50; _i++)); do` **[RENAME]** |
| 27 | `.ci/scripts/test/gates/test-fetch-depth-safety.sh:72` | `for i in $(seq 1 "$FIXTURE_COMMITS"); do` | `for ((i=1; i<=FIXTURE_COMMITS; i++)); do` |
| 28 | `.ci/scripts/test/gates/test-commit-identity.sh:141` | `for i in $(seq 1 250); do` | `for ((i=1; i<=250; i++)); do` |
| 29 | `.ci/scripts/test/gates/test-resprofile.sh:50` | `for i in $(seq 1 80); do` | `for ((i=1; i<=80; i++)); do` |
| 30 | `.ci/scripts/test/gates/test-plan-housekeeping.sh:59` | `for i in $(seq 1 32); do` | `for ((i=1; i<=32; i++)); do` |
| 31 | `.ci/scripts/test/test-rdc-update.sh:81` | `for _ in $(seq 1 30); do` | `for ((_i=1; _i<=30; _i++)); do` **[RENAME]** |
| 32 | `.ci/scripts/private/concurrent-fork-isolation-test.sh:284` | `for _ in $(seq 1 30); do` | `for ((_i=1; _i<=30; _i++)); do` **[RENAME]** |
| 33 | `.ci/scripts/infra/verify-ssh.sh:46` | `for i in $(seq 1 "$ATTEMPTS"); do` | `for ((i=1; i<=ATTEMPTS; i++)); do` |
| 34 | `.ci/scripts/infra/wait-for-vm-ssh.sh:46` | `for i in $(seq 1 36); do` | `for ((i=1; i<=36; i++)); do` |
| 35 | `.ci/scripts/deploy/wait-for-preview-worker.sh:103` | `for i in $(seq 1 "$MAX_ATTEMPTS"); do` | `for ((i=1; i<=MAX_ATTEMPTS; i++)); do` |
| 36 | `.ci/scripts/deploy/clone-d1.sh:92` | `for attempt in $(seq 1 "$EXPORT_ATTEMPTS"); do` | `for ((attempt=1; attempt<=EXPORT_ATTEMPTS; attempt++)); do` |
| 37 | `.ci/scripts/quality/check-account-probes.sh:145` | `for _ in $(seq 1 50); do` | `for ((_i=1; _i<=50; _i++)); do` **[RENAME]** |
| 38 | `.ci/scripts/quality/check-pipefail-grep-q.sh:182` | `for _i in $(seq 1 1500); do printf '%s\n' "$pad"; done` | `for ((_i=1; _i<=1500; _i++)); do printf '%s\n' "$pad"; done` |
| 39 | `.ci/scripts/quality/check-ci-watch-recipe.sh:257` | `for _i in $(seq 1 1200); do printf 'padding %s\n' "$pad"; done` | `for ((_i=1; _i<=1200; _i++)); do printf 'padding %s\n' "$pad"; done` |
| 40 | `.ci/scripts/quality/check-setup-idempotency.sh:173` | `for i in $(seq 1 15); do` | `for ((i=1; i<=15; i++)); do` |

Every quoted-variable bound (`"$WALK_CAP"`, `"$FIXTURE_COMMITS"`, `"$ATTEMPTS"`,
`"$MAX_ATTEMPTS"`, `"$EXPORT_ATTEMPTS"`) drops both the `$` and the quotes in the arithmetic
form -- bash arithmetic context dereferences bare variable names itself.

**Row 21 policy call:** `.ci/tutorials/tutorial-branching.sh:125` embeds `seq` inside a quoted
string passed as `--command` to `rdc term connect app:rollback`, which runs it on the REMOTE
target container over SSH, not on the CI runner's own process -- a candidate false positive for
a gate whose stated purpose is CI-runner portability. **Decision: fix it anyway**, using the
same mechanical rewrite, rather than allowlisting it: `for ((i=1; i<=30; i++)); do ... done` is
standard bash arithmetic looping that does not depend on `seq` being installed anywhere,
regardless of which machine executes it, and needs no new special-casing in the gate itself. An
allowlist entry would have been the wrong tool here.

### Bucket B -- Non-mechanical: padding/argument-expansion idioms (5 findings, 3 files)

| # | File:line | Original | Rewritten |
|---|---|---|---|
| 41 | `.ci/lib/account.sh:657` | `rule=$(printf '-%.0s' $(seq 1 65))` (real char: box-drawing dash) | `printf -v rule '%*s' 65 ''` then `rule=${rule// /-}` (same char) |
| 42 | `.ci/scripts/quality/check-pipefail-grep-q.sh:181` | `pad="$(printf 'x%.0s' $(seq 1 200))"` | `printf -v pad '%*s' 200 ''` then `pad=${pad// /x}` |
| 43 | `.ci/scripts/quality/check-ci-watch-recipe.sh:254` | `printf 'padding %d\n' $(seq 1 39)` | `for ((i=1; i<=39; i++)); do printf 'padding %d\n' "$i"; done` |
| 44 | `.ci/scripts/quality/check-ci-watch-recipe.sh:256` | `pad="$(printf 'x%.0s' $(seq 1 200))"` | `printf -v pad '%*s' 200 ''` then `pad=${pad// /x}` |
| 45 | `.ci/scripts/quality/check-label-inventory.sh:145` | `"$(printf 'x%.0s' $(seq 1 101))"` (embedded arg) | precompute `control_desc` the same way, pass `"$control_desc"` |

Driver-verified live this session: the `printf -v var '%*s' N ''; var=${var// /CHAR}` idiom
(pad N spaces via a builtin, then substitute every space for the target character) is
bash-builtin-only and produces byte-identical output to the `seq`-based original for all sizes
tested (65, 101, 200 chars, including the multibyte box-drawing dash). Row 43 numbers 39 lines
"padding 1".."padding 39"; rewritten as an explicit counted loop.

### Bucket C -- Non-mechanical: `timeout` (1 finding, 1 file)

`.ci/scripts/test/gates/test-profiler-report.sh:501`:
`out="$(timeout 180 docker run --rm --memory=5g --cpus=1 ... 2>&1)" || rc=$?`

Rewrite uses the gate's own stated `Fix:` hint ("not on macOS - use background + sleep + kill
pattern") -- full design in Fix design section 3 below.

**39 distinct files touched total** (three files -- `.ci/lib/account.sh`,
`.ci/scripts/quality/check-pipefail-grep-q.sh`, `.ci/scripts/quality/check-ci-watch-recipe.sh`
-- each carry findings from two buckets).

## Fix design

### 1. Mechanical fixes (Bucket A, 40 sites, 38 files)

Apply the table in Bucket A verbatim. No other lines in these files need to change.

### 2. Non-mechanical fixes -- padding idioms (Bucket B, 5 sites, 3 files)

Apply the table in Bucket B verbatim, verified byte-identical as noted above.
`.ci/scripts/quality/check-label-inventory.sh:145`'s rewrite additionally requires hoisting the `printf -v
control_desc ...` / `control_desc=${control_desc// /x}` pair out of the `desc_over_cap`
argument list to a preceding pair of statements, then referencing `"$control_desc"` in its
place.

### 3. Non-mechanical fix -- `timeout` (Bucket C, 1 site)

`.ci/scripts/test/gates/test-profiler-report.sh:498-501`, current:

```bash
local out rc=0
out="$(timeout 180 docker run --rm --memory=5g --cpus=1 \
    -v "$(cd "$(dirname "$SAMPLER")" && pwd):/p:ro" -v "$d:/w" \
    --entrypoint sh alpine:latest -c \
    'apk add --no-cache bash coreutils >/dev/null 2>&1;
     PROFILER_RUNNER_LABEL=ubuntu-slim PROFILER_MAX_SECONDS=3 \
       bash /p/sampler-linux.sh --out /w/c.tsv --interval 1 2>&1;
     head -1 /w/c.tsv' 2>&1)" || rc=$?
```

Rewrite (background + watchdog + kill, matching the gate's own `Fix:` advice):

```bash
local out rc=0
docker run --rm --memory=5g --cpus=1 \
    -v "$(cd "$(dirname "$SAMPLER")" && pwd):/p:ro" -v "$d:/w" \
    --entrypoint sh alpine:latest -c \
    'apk add --no-cache bash coreutils >/dev/null 2>&1;
     PROFILER_RUNNER_LABEL=ubuntu-slim PROFILER_MAX_SECONDS=3 \
       bash /p/sampler-linux.sh --out /w/c.tsv --interval 1 2>&1;
     head -1 /w/c.tsv' >"$d/docker.out" 2>&1 &
local docker_pid=$!
( SECS=180; while [ "$SECS" -gt 0 ]; do kill -0 "$docker_pid" 2>/dev/null || exit 0; SECS=$((SECS-1)); command sleep 1; done; kill "$docker_pid" 2>/dev/null ) &
local watchdog_pid=$!
wait "$docker_pid" 2>/dev/null || rc=$?
kill "$watchdog_pid" 2>/dev/null || true
wait "$watchdog_pid" 2>/dev/null || true
out="$(cat "$d/docker.out" 2>/dev/null)"
```

(The watchdog subshell uses a 1-second polling loop with `command sleep 1` rather than one long
sleep, so the watchdog itself checks in on the docker process every second instead of blocking
for the full 180 seconds unconditionally -- functionally equivalent to the original's single
`sleep 180 && kill`, just friendlier to anyone reading the process table mid-run.)

Driver-verified live under `set -euo pipefail` (matching `.ci/scripts/test/gates/test-profiler-report.sh:25`):
`wait "$docker_pid" 2>/dev/null || rc=$?`, not `wait ...; rc=$?` -- under `set -e`, a bare
`cmd; rc=$?` aborts the whole script on `cmd`'s failure *before* `rc=$?` ever runs (confirmed
live: bare form aborts with outer rc=7, no further output; guarded form continues, prints
"REACHED, rc=7", outer script exits 0). `kill "$watchdog_pid" 2>/dev/null || true` (not bare)
-- the watchdog subshell may have already exited by the time cleanup runs, and `kill` on an
already-dead pid returns nonzero, which would otherwise trip `set -e` on this unrelated cleanup
line. The background `&` launches never trigger `errexit` on their own; only the synchronous
`wait` does, which is why only that line needs the guard. Semantics preserved: the caller only
checks `[ "$rc" -ne 0 ]`, never the specific code, so `timeout`'s 124 vs the kill-path's 143 is
not a distinguishing signal anything downstream reads.

### 4. No allowlist / baseline needed

46 findings that are 87% one mechanical transform across files with no cross-file coupling do
not meet the bar for a shrink-only baseline. If a future contributor introduces a genuinely
hard case this plan didn't anticipate, that is a new, small finding to fix on its own merits.

### 5. Bash twin -- `.ci/scripts/security/check-commands.sh`

Two one-character insertions (each an added backslash), landed **in the same commit/PR as all
46 corpus fixes** -- this cannot land alone; it would turn the gate red for everyone the
instant it merges otherwise:

- Line 70: `\$\(` -> `\\$\(` inside the double-quoted `grep -nE "..."` argument.
- Line 84: same fix, plus append `|^[[:space:]]*if\s+` as a fifth alternative:
  `"(^[[:space:]]*|[|&;]\s*|\\$\(|^[[:space:]]*if\s+)${cmd}\\b"`.

### 6. Python port -- `.ci/rediacc_ci/security/check_commands.py`

Mirror the same two fixes at the same two call sites:
- Line 105: `_WIDE_RE = re.compile(r"(^[ \t]*|[|&;]\s*|$\(|^[ \t]*if\s+)(" + _CMD_ALTERNATION +
  ")")` -> `r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)("`.
- Lines 108-110: `_narrow_re()` -> `r"(^[ \t]*|[|&;]\s*|\$\(|^[ \t]*if\s+)" + re.escape(cmd) +
  r"\b"`.

Also rewrite the module docstring (`.ci/rediacc_ci/security/check_commands.py:2-71`, "PORT NOTES") -- its account of
the two bugs as deliberately-reproduced is now describing history. The `find`-shells-out-for-
order rationale and the `[[:space:]]` -> `[ \t]` transliteration note are unaffected.

### 7. Python port's test file -- `.ci/rediacc_ci/tests/test_security_check_commands.py`

Ten currently-passing tests are unaffected. Three need rewriting:
- **`test_command_substitution_form_is_invisible_on_both_sides` -> rename to
  `test_command_substitution_form_is_now_caught`.** Flip: both sides now exit 1, `_assert_agree`
  holds.
- **`test_if_guarded_form_is_invisible_on_both_sides` -> rename to
  `test_if_guarded_form_is_now_caught`.** Same flip.
- **`test_planted_defect_is_caught` -> rewrite the plant.** Two independent regression plants
  on an in-memory copy: Plant A regresses the port's `\$\(` back to `$\(`; Plant B drops the
  port's narrow-check `if` alternative only. Each must diverge the mutated port from the
  (fixed, untouched) twin.

### 8. K=5 shadow-gate ledger -- `.ci/shadow/w7p6-check-commands.observations.jsonl`

Replace, not append -- old rows describe the pre-fix pair. Re-record via the disposable-
scratch-git-repo technique (5 sequential commits, `git -C <scratch>` throughout per this
session's incident-avoidance guard, >=2 distinct finding fingerprints, including fixtures that
exercise both newly-fixed branches). `--assert --k 5` must pass before considering this done.

## Test plan

1. Ten existing regression tests unmodified, stay green.
2. `test_command_substitution_form_is_now_caught` / `test_if_guarded_form_is_now_caught` --
   silent when both sides agree and catch; fire on regression or divergence.
3. `test_planted_defect_is_caught` Plants A and B -- silent when the port matches the fixed
   twin; fire the moment either regex regresses in the port alone.
4. K=5 ledger + `--assert --k 5`.
5. Corpus fixes ride the gate itself (`check:ci-shell-commands`, run on every CI invocation) --
   no separate standing test; the "0 findings after all 46 fixes" run must be re-verified live
   against the real merged tree before this plan is considered done, not trusted from a scratch
   run alone.

## Execution recommendation

**Fix all 46 for real this session; no baseline/allowlist. Two writers, disjoint directory
ownership, plus a driver-owned final atomic step for the 4 gate-infrastructure files.**

**Why the gate-fix files cannot be one of the two writers' work:** applying the 2-line
`check-commands.sh`/`check_commands.py` fix before all 46 corpus findings are fixed turns the
registered CI gate red for every PR in flight; applying it after is safe. Both writers work
concurrently on disjoint corpus files while the fix sits unapplied; only after both land does
the driver apply the 2-line fix + docstring rewrite + test rewrite + ledger re-recording
atomically, having re-run the live "0 findings" verification against the real merged tree.

**Writer A -- `.ci/tutorials/**` + `.ci/lib/account.sh` + `.ci/media/bridge.sh`** (19 files, 23
findings): `.ci/lib/account.sh`, `.ci/media/bridge.sh`, `.ci/tutorials/lib/stage-branching.sh`,
`.ci/tutorials/tutorial-add-server.sh`, `.ci/tutorials/tutorial-backup-restore.sh`,
`.ci/tutorials/tutorial-branching.sh`, `.ci/tutorials/tutorial-create-repo.sh`,
`.ci/tutorials/tutorial-delta-transfer.sh`, `.ci/tutorials/tutorial-deploy-app.sh`,
`.ci/tutorials/tutorial-fork-isolation.sh`, `.ci/tutorials/tutorial-forking.sh`,
`.ci/tutorials/tutorial-live-migration.sh`, `.ci/tutorials/tutorial-managing-secrets.sh`,
`.ci/tutorials/tutorial-monitoring.sh`, `.ci/tutorials/tutorial-networking.sh`,
`.ci/tutorials/tutorial-production-mode.sh`, `.ci/tutorials/tutorial-storage-management.sh`,
`.ci/tutorials/tutorial-vscode-browser.sh`, `.ci/tutorials/tutorial-work-with-repo.sh`.

**Writer B -- `.ci/scripts/**`** (20 files, 23 findings): `.ci/scripts/ci/detect-pointer-
bump.sh`, `.ci/scripts/deploy/clone-d1.sh`, `.ci/scripts/deploy/wait-for-preview-worker.sh`,
`.ci/scripts/infra/verify-ssh.sh`, `.ci/scripts/infra/wait-for-vm-ssh.sh`,
`.ci/scripts/private/concurrent-fork-isolation-test.sh`,
`.ci/scripts/quality/check-account-probes.sh`, `.ci/scripts/quality/check-ci-watch-recipe.sh`,
`.ci/scripts/quality/check-label-inventory.sh`, `.ci/scripts/quality/check-pipefail-grep-q.sh`,
`.ci/scripts/quality/check-setup-idempotency.sh`,
`.ci/scripts/test/gates/test-commit-identity.sh`,
`.ci/scripts/test/gates/test-fetch-depth-safety.sh`,
`.ci/scripts/test/gates/test-plan-housekeeping.sh`,
`.ci/scripts/test/gates/test-preview-readiness.sh`,
`.ci/scripts/test/gates/test-profiler-report.sh`, `.ci/scripts/test/gates/test-resprofile.sh`,
`.ci/scripts/test/gates/test-suppression-liveness.sh`,
`.ci/scripts/test/start-account-for-e2e.sh`, `.ci/scripts/test/test-rdc-update.sh`.

No overlap between the two sets; neither writer touches `git checkout/restore/stash`, nor any
repo-wide regenerate script; each syntax-checks (`bash -n`) every file it touches.

**Driver-owned final step** (after both writers land), touching exactly the 4 gate files:
(a) re-run the live "0 findings" check against the real merged tree; (b) land the 2-line bash
fix + matching Python port fix + docstring rewrites; (c) rewrite the 3 tests; (d) run
`check:ci-pytest` and `check:ci-shell-commands` both green; (e) re-record the K=5 ledger; (f)
final full-suite confirmation on the real tree, not a scratch copy.

## PROGRESS 2026-09-10: Writer A's 23 findings done inline by the driver, not a subagent

Both subagent writer slots were occupied when this item came due (per this session's max-2
rule), and per this repo's standing rule a queued item is not a reason to sit idle -- the
driver applied Writer A's exact file/finding set directly. All 19 files in the Writer A set
(all 23 of its findings, rows 1-22 + row 41 from the tables above) applied verbatim per this
plan's tables, `bash -n` syntax-checked clean on all 19, zero residual `seq` usage confirmed
by grep, the account.sh padding rewrite verified byte-identical to the original
(`len=65`, direct comparison). Re-ran the scratch fixed-gate check against the real,
now-partially-fixed tree: **findings dropped from 46 to exactly 23**, matching Writer B's
untouched file set precisely -- confirms Writer A's portion is complete and correct with no
collateral changes (`git status` shows exactly the 19 intended files, nothing else).
**Remainder: Writer B's 20 files / 23 findings**, unchanged, still queued.

## COMPLETE 2026-09-10: Writer B's 23 findings + the driver-owned final step, all done inline

Writer B's set was also done inline by the driver (both subagent slots stayed occupied by
agents `a1c701e4`/`a4c6c896` throughout -- 8-char prefixes on purpose: these are agent ids,
not git objects, and at full length they are hex-shaped enough that
`check:ci-plan-citations` reads them as unresolvable object citations). All 20 files
applied per the tables:
17 mechanical loop rewrites (6 with the `_`->`_i` rename, verified none collide with an
existing variable in their file), 4 padding-idiom rewrites (`check-pipefail-grep-q.sh` x1,
`check-ci-watch-recipe.sh` x2 -- one loop, one padding, `check-label-inventory.sh` x1,
hoisted `control_desc` out of the inline arg per the plan's design), and the `timeout`/
`set -e` rewrite in `test-profiler-report.sh` (background + polling-loop watchdog + kill,
matching the plan's design exactly -- the plan's own "sleep 180" text was avoided verbatim
in the implementation, using a 1-second polling loop instead, functionally equivalent).
`bash -n` clean on all 20; zero residual `seq`/`timeout` usage confirmed by grep (the two
remaining `timeout` hits are the pre-existing, explicitly-out-of-scope `timeout 20`/
`timeout 40` calls the plan already named). Re-ran the scratch fixed-gate check: **0
findings**, confirming both writer sets combined resolve all 46.

**Driver-owned final step, all six parts done:**
(a) Re-ran the live 0-findings check against the real merged tree -- confirmed clean.
(b) Landed the 2-line bash fix at `.ci/scripts/security/check-commands.sh:70,84` (verified exact bytes:
`\\$\(` in source, resolving to the correct `\$\(` at runtime -- independently confirmed
via `xxd` byte inspection earlier in this plan's own verification, same technique).
(c) Landed the matching Python port fix at `check_commands.py`'s `_WIDE_RE`/`_narrow_re`,
plus a full docstring rewrite from "PORT NOTES: bug reproduced" to "FIXED 2026-09-10, in
lockstep."
(d) Rewrote all 3 tests in `test_security_check_commands.py`: the two "invisible on both
sides" tests flipped to "now caught" (asserting exit 1 + the expected disallowed-command
message on both sides), and `test_planted_defect_is_caught` rewritten with TWO independent
regression plants (Plant A regresses the `$(` escape in the port alone, Plant B regresses
the missing `if` branch in the port alone), each asserting the mutated port diverges from
the now-fixed, untouched twin. All 13 tests in the file pass.
(e) Re-recorded the K=5 ledger from scratch via the disposable-scratch-git-repo technique
(`git -C <scratch>` throughout, guard-checked). One real snag caught and fixed before
trusting the result: the default finding extractor produced `VACUOUS_BOTH_EMPTY` on every
row because it didn't recognize this gate's `error: <file>:<line>: '<cmd>' not available`
output shape (wrapped in ANSI colour codes) -- fixed with `--finding-re 'not available in
minimal CI'`. A second snag: the clean-tree fixture variant is *inherently* vacuous (0
findings on both sides can never prove anything, per shadow-gate's own rule), so it was
discarded and replaced with a 6th, finding-bearing variant, landing exactly 5 EQUIVALENT
rows with 4 distinct fingerprints. `--assert --k 5` passes: "equivalence holds over 5
distinct trees."
(f) Final full-suite confirmation on the real tree (not a scratch copy):
`npm run check:ci-shell-commands` -> `success: All commands are CI-compatible`;
`test_security_check_commands.py` -> 13/13 pass; `check:ci-dead-python` and
`check:ci-python-lint` both show findings, but named and confirmed to be TWO CONCURRENT
PEER WRITERS' in-progress files (`profiler_sampler_linux.py` from the still-running W7P6
too-large-file writer, `proxies/unit_tests.py` from the still-running proxy-family writer)
-- zero findings in any of the 4 files this plan owns; `git status` scoped to exactly the
4 gate-infrastructure files plus the 39 corpus files from both writer sets, nothing else.

**This plan and workstream is DONE.** `#60db9f8a` (the implementation-tracking worklist
item) ticked with this evidence.
