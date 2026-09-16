# PLAN: give private/renet its own pipefail/grep -q gate
Status: draft
Owner: d778be9d
Updated: 2026-09-16

Console's `.ci/scripts/quality/check-pipefail-grep-q.sh` and its port
`.ci/rediacc_ci/quality/pipefail_grep_q.py` cannot reach `private/renet`. The two real
instances of the class found in renet on 2026-09-16 were found BY HAND, not by a gate,
and the next one will be too unless renet gets its own detection. This plan specifies
that gate, the wiring, and the proof it can fire.

The two known sites are already fixed and are NOT work here; they are cited only as the
evidence that the class is live in this submodule:

```
renet commit 2e4a4b4 ("fix(ci): two pipefail/grep -q detectors that could not fail,
measured at 40/40"), on branch 0914-1, riding rediacc/renet PR #111.
```

## 1. What renet's CI actually is (measured, not assumed)

**renet has no PR CI of its own.** Its only workflow is
`private/renet/.github/workflows/claude-review.yml`, a thin caller into console's reusable
review workflow, and its own header says so at
`private/renet/.github/workflows/claude-review.yml:5` -- "This repo has no PR CI of its
own -- its validation runs inside console CI". There is no second workflow file; `find
private/renet/.github -type f` returns that one file.

**renet's gate layer is bash, and it mirrors console's `.ci` layout.**
`private/renet/.ci/ci.sh` has three stages; `run_quality()` at
`private/renet/.ci/ci.sh:22` invokes exactly five scripts, at
`private/renet/.ci/ci.sh:24` through `private/renet/.ci/ci.sh:28`: `format.sh`, `lint.sh`,
`deadcode.sh`, `security.sh`, `i18n.sh`. Every one of them sources
`private/renet/.ci/scripts/lib/common.sh`, which sets `set -euo pipefail` at
`private/renet/.ci/scripts/lib/common.sh:9` and supplies `log_step`/`log_info`/`log_error`
and `require_cmd`.

**Console runs that stage.** `.ci/scripts/private/run-renet.sh:5` registers the gate id
`check:ci-renet`; `package.json:253` binds it to `.ci/scripts/private/run-renet.sh
quality`; `.github/workflows/ci-quality.yml:2291` and
`.github/workflows/ci-quality.yml:2293` run it in the L10 Go lane. So a script added to
`run_quality()` runs in console CI **and** in local `npm run ci` with no workflow edit.

**renet has ZERO shell-script gating today.** No shellcheck, no shfmt, no custom shell
checker -- and it says so in its own tree, at
`private/renet/.ci/scripts/test/run-tests.sh:20`: "renet's CI runs no shellcheck over
.ci/scripts, so this warning was invisible until the console-side battery was pointed at
this file". Console's shellcheck gate (`package.json:230` ->
`.ci/scripts/security/shellcheck.sh`) enumerates its corpus with `git ls-files '*.sh'` at
`.ci/scripts/security/shellcheck.sh:83` plus `--others --exclude-standard` at
`.ci/scripts/security/shellcheck.sh:84`, run at the CONSOLE root -- and `git ls-files
private/renet` in console returns the single gitlink line `private/renet`, not the
submodule's contents. Verified: of the 504 files console's pipefail gate scans, 11 have
"renet" in the path and every one is a console-side `.ci/scripts/**/renet-*.sh`; none is
inside the submodule.

**But the surface is small, and that is the load-bearing number.** `git ls-files '*.sh'`
inside `private/renet` returns **15** files, ~3,400 lines; **11 of the 15 set pipefail**.
The exceptions are `build.sh` (850 lines, no pipefail), `_scripts/verify_translations.sh`,
`scripts/test-repo-integration.sh` (deprecated per its own header) and nothing else. There
is also exactly one `*.bats` file, `private/renet/tests/unit/bash/test_renet.bats`, which
is bash and currently carries neither `pipefail` nor `grep -q`, and zero tracked
extensionless shell scripts (checked by reading the first line of every tracked non-`.sh`,
non-source file).

## 2. What the gate would find in renet TODAY

Measured by importing the SHIPPED console detector
(`.ci/rediacc_ci/quality/pipefail_grep_q.py`, `offenders()`), pointing it at the renet
worktree and monkey-patching `SCALING_PRODUCERS`. No regex was reinvented.

| Producer list | Hits in renet's 15 files |
|---|---|
| console's list verbatim (`.ci/rediacc_ci/quality/pipefail_grep_q.py:339`) | **0** |
| + `tee` | **1** |
| + `tee` + `docker` | **3** |

The three:

- `private/renet/.ci/scripts/quality/i18n.sh:155` --
  `... i18n validate --check-hashes 2>&1 | tee "$WORK/hash-check.log" | grep -q "All
  translations are up-to-date"`. `tee` is a pure pass-through: its output scales exactly
  with its input, and it is the stage `grep -q` SIGPIPEs. The file sets `set -euo pipefail`
  at its line 3, and the test is negated (`if ! ...`), so losing the race reports a stale
  hash manifest against a manifest that is fine -- a false red, in the same mechanism.
- `private/renet/scripts/ci-test.sh:174` and `private/renet/scripts/ci-test.sh:217` --
  `docker version -f '{{.Server.Experimental}}' 2>/dev/null | grep -q "true"`. Bounded
  output today; console's own gate header records the 2026-08-31 measurement where a
  1129-byte `printf` still lost this race in CI, so bounded is rare, not safe.

Two shapes that stay invisible and are stated so the green is not read as more than it is:

- `private/renet/scripts/ci-test.sh:250` -- `"$renet_bin" datastore status --path ... 2>&1
  | grep -q "Mounted: true"`. The producer is a VARIABLE, so no name-based classifier can
  see it. Not worth a rule: a `"\$var" ... | grep -q` rule would flag every remote
  invocation in the tree.
- `private/renet/scripts/test-repo-integration.sh` lines 96-157 hold seven `./renet ... |
  grep -q`, all harmless because that file sets no pipefail (and its own header, lines 3-20,
  declares it deprecated in favour of pytest).

## 3. The Go-embedded-bash half, measured and bounded

renet builds bash as Go strings, so "shell scripts" is not the whole surface. Measured:
13 `... | grep -q` sites across 5 Go files. Exactly ONE execution path in the repo sets
pipefail for remote bash: `buildScript()` at `private/renet/pkg/ssh/streaming.go:179`
writes `set -o pipefail` into every streamed script at
`private/renet/pkg/ssh/streaming.go:183`, and its only caller chain runs through
`private/renet/pkg/functions/executor_ssh.go:235`.

`grep -rn "grep -q" --include=*.go pkg/functions/` returns **nothing**. Every one of the
13 sites executes via `ssh user@host "cmd"` (`sshCommand`, `pkg/infra/ceph/provisioner.go`)
or `exec.Command("bash","-c",...)` (`cmd/renet/ops_host.go`), and neither sets pipefail.
So the class is **not live** in Go today, and it becomes live the moment a `pkg/functions`
command string pipes into `grep -q`. That is a 20-line second detector with a real
coupling behind it, not a speculative one; it is Phase 4 below.

## 4. Decision: a standalone bash gate in renet, not a Go check and not a Python import

**Recommended: port the detector to bash, into
`private/renet/.ci/scripts/quality/pipefail-grep-q.sh`.**

Against a **Go** checker, three costs measured in the renet tree:

1. renet's i18n gate scans every non-test Go file for hardcoded English. Its default
   excludes are at `private/renet/pkg/i18n/extract.go:207` and the only source-file
   exclusion is `*_test.go`. A Go linter's diagnostics are all English prose, so every
   message would need `i18n.T()` wrapping or a baseline entry -- the gate's own error text
   becoming translated UI.
2. renet's deadcode gate is whole-program RTA over `cmd/renet` plus tests
   (`private/renet/.ci/scripts/quality/deadcode.sh`), so the checker needs a reachable
   home. `cmd/` ships it inside the product binary; a test-only package is a directory with
   no non-test Go files.
3. The subject of the check is bash TEXT, and renet's entire gate layer is already
   bash-wrapping-Go-tools (`format.sh`, `lint.sh`, `deadcode.sh`, `security.sh`, `i18n.sh`).
   A Go tool here would be the only one of its kind and would still need a shell wrapper to
   be registered.

Against **importing console's Python module**: renet is required to work standalone.
`private/renet/.ci/scripts/lib/common.sh` is, in its own words, "a standalone copy for when
renet runs outside of console", and `deadcode.sh` re-implements console's BLOCKER validator
with the comment "kept standalone so renet works outside the monorepo". renet's quality
stage requires only `go` and `jq`; adding a `sys.path` reach into `../../.ci` would make
the gate silently skip in exactly the standalone case the rest of the directory is built for.

**The DRY cost is real and is paid deliberately.** Console already keeps a bash/Python twin
pair for this very gate and calls the bash one "the differential twin the port is compared
against". A third implementation drifts unless something holds it; Phase 2's console-side
battery test asserts renet's producer list is a SUPERSET of console's, which makes drift in
the dangerous direction (console widens, renet does not) a red in console CI.

## 5. The design

### 5.1 `private/renet/.ci/scripts/quality/pipefail-grep-q.sh`

Named for its subject like its four siblings (no `check-` prefix: that is console's gate-id
convention, and renet's `.ci` scripts carry no gate headers at all -- verified, `grep -rn
"gate ----" private/renet/.ci/` is empty).

Structure, in order:

1. `source ../lib/common.sh`, then `set +e` with a comment: the gate COUNTS failures and
   reports them all, so errexit (inherited from `common.sh:9`) must be off; `-u` and
   `-o pipefail` stay on. `require_cmd git`.
2. `offenders() { ... }` and `join_logical() { ... }` -- ported from
   `.ci/scripts/quality/check-pipefail-grep-q.sh` (the bash twin, whose `SCALING_PRODUCERS`
   is at `.ci/scripts/quality/check-pipefail-grep-q.sh:191`). Keep the comment stripping
   AND the quoted-span blanking: without the second one the gate flags its own prose, which
   is how console discovered the mention-as-execution class inside the gate written for a
   different class.
3. `SCALING_PRODUCERS` = console's 17, **plus `tee` and `docker`**, with the extras listed
   separately in a `RENET_EXTRA_PRODUCERS` variable so Phase 2's parity assertion can name
   them, and each extra carrying its measured justification (section 2).
4. No `INHERITS_PIPEFAIL_PREFIXES`. Console needs it for exactly one file; in renet,
   `.ci/scripts/lib/common.sh` sets pipefail itself at line 9, so the per-file test already
   answers correctly for every sourced library here. Add the mechanism only if a sourced
   file that does NOT set pipefail ever appears.
5. Corpus: `git -C "$ROOT" ls-files '*.sh' '*.bats'` PLUS `git -C "$ROOT" ls-files --others
   --exclude-standard '*.sh' '*.bats'`, deduplicated -- the untracked half for the same
   reason console's shellcheck takes it at `.ci/scripts/security/shellcheck.sh:84`: a script
   a session has written but not committed is exactly when the check is most useful. `git`
   is REQUIRED, not optional: a `find` fallback would silently redefine the corpus (and pick
   up `build/`, `bin/`), and a gate with two corpora has two verdicts.
6. Controls, run on every invocation (section 6).
7. Anti-vacuity floors, both of them:
   - `scanned -eq 0` -> FAIL ("the enumeration matched nothing, so a green here means
     nothing").
   - zero scanned files carrying pipefail -> FAIL. Console's floor is only the first; renet
     gets the second because 11 of its 15 files set pipefail, so a collapse to zero is a
     broken enumerator, not a clean tree.
8. The fix advice in the failure message, verbatim from console's, including the two
   caveats that cost sites in the 2026-09-16 sweep: keep every grep flag except `-q` (the
   `--` in `grep -- "--- PASS:"` at `private/renet/.ci/scripts/quality/i18n.sh:234` is
   load-bearing), and `[ -n "$(...)" ]` is not equivalent when the pattern can match an
   empty line.
9. A `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]` main guard, matching
   `private/renet/.ci/scripts/quality/deadcode.sh:242`, so the console battery can source
   the file and call `offenders` without running it. `offenders()` must be pure over
   (file, rel) exactly as `evaluate_deadcode` at
   `private/renet/.ci/scripts/quality/deadcode.sh:166` is pure over (dead-list, allowlist).

**The gate must not flag itself.** Its own controls contain the racing shape on purpose.
Console solves this by assembling the fixture at runtime (`GQ="grep -q"`, then a heredoc)
so the file's text never carries the shape contiguously. Port that convention; do NOT add a
self-exemption, which would stop policing the one script most likely to grow this bug next.

### 5.2 Registration

One line, inserted as the FIRST entry of `run_quality()` in `private/renet/.ci/ci.sh`
(before `private/renet/.ci/ci.sh:24`). First because it needs only bash and git and runs in
under a second, so a shell defect is reported before `lint.sh` spends minutes installing
golangci-lint. No workflow edit, no `package.json` edit, no gate header: `check:ci-renet`
already covers the stage.

`private/renet/Makefile` is deliberately untouched. Its `all:` target predates `.ci/` and
already omits every `.ci` script; wiring one gate into it would imply the others are there.

## 6. Tests: what fires on a planted defect, what stays silent on a clean tree

### 6.1 In-script controls (run on every invocation, in renet's own CI, standalone too)

Two MECHANISM controls first -- they ask the operating system, not the regex, and if the
mechanism stops reproducing on the host the gate must say so rather than keep passing:

- an EXTERNAL producer (`grep -v` over a ~300 KB file) piped into `grep -q` must report
  MISSED under pipefail. If it reports MATCHED -> FAIL "the mechanism this gate exists for
  did not reproduce here".
- a BUILTIN producer (`printf` of a ~300 KB payload) must also report MISSED. Different
  kernel path: bash traps SIGPIPE for builtins, so the builtin takes EPIPE from `write(2)`
  and pipefail promotes it. Without this control the `printf`/`echo` half of the producer
  list guards an unconfirmed claim.

Then the detector controls, each asserting one direction:

| Fixture | Expected |
|---|---|
| `set -o pipefail` + local function `\| grep -q` | FLAGGED |
| the same, rewritten as `[ -n "$(producer \| grep ...)" ]` | silent |
| `printf "%s" "$x" \| grep -q y` | FLAGGED |
| `echo "$x" \| grep -q y` | FLAGGED |
| a scaling COMMAND producer (`grep -vE ... \| grep -q`) | FLAGGED |
| the pipeline SPANNING TWO LINES (producer on line 1, `grep -qE` on line 2) | FLAGGED |
| `... \| tee "$f" \| grep -q x` | FLAGGED (the renet extra) |
| `docker ps --format ... \| grep -q x` | FLAGGED (the renet extra) |
| the same shape in a file with NO pipefail | silent |
| the shape written inside a `#` COMMENT | silent |
| the shape inside a single- or double-quoted STRING | silent |

Each control that fails prints `CONTROL DID NOT FIRE: ...` (the detector is blind) or
`GATE IS OVER-BROAD: ...` (the sanctioned fix was flagged) and reds the gate. A control
that cannot be built is a failure, never a skip.

### 6.2 Console-side battery test

`.ci/scripts/test/gates/test-renet-pipefail-grep-q.sh`, modelled line-for-line on
`.ci/scripts/test/gates/test-renet-deadcode.sh`: the same `# ---- gate ----` header shape
(`kind: battery`, `step: Quality-gate unit tests`, `needs: submodules`, `lane:
quality-security`, plus the blocker line those 149 shared-step tests all carry), the same
absent-submodule skip as `.ci/scripts/test/gates/test-renet-deadcode.sh:28`, the same
`source` of the renet script under its main guard as
`.ci/scripts/test/gates/test-renet-deadcode.sh:35`, and the same `mktemp -d` fixture dir as
`.ci/scripts/test/gates/test-renet-deadcode.sh:37` -- fixtures NEVER in the real tree, so
the test needs no `mutex`/`reads` claim in the battery's isolation lock.

It asserts, by calling the sourced `offenders()`:

1. the twelve fixture directions of 6.1, so the renet detector's contract is pinned from
   console too;
2. **producer-list parity**: renet's `SCALING_PRODUCERS` is a SUPERSET of console's, read
   by importing the port rather than re-parsing source --
   `python3 -c "import sys; sys.path.insert(0,'.ci'); from
   rediacc_ci.quality.pipefail_grep_q import SCALING_PRODUCERS; print(' '.join(SCALING_PRODUCERS))"`
   against `.ci/rediacc_ci/quality/pipefail_grep_q.py:339`. Superset, not equality, so renet
   may be AHEAD (it is, by `tee`/`docker` until Phase 3 lands) while a console widening that
   renet has not taken reds here -- the drift direction that costs a missed defect.
3. every extra in `RENET_EXTRA_PRODUCERS` is a real word in the renet list, so the declared
   extras cannot rot into prose.

The test runs in the `quality-security` job, whose checkout sets `submodules: true`, under
the step at `.github/workflows/ci-quality.yml:2196`; the battery globs
`.ci/scripts/test/gates/test-*.sh` (`.ci/rediacc_ci/battery.py:111`), and the entry must
ALSO be declared in `scripts/ci-runner/manifest.ts` (see the existing renet entry at
`scripts/ci-runner/manifest.ts:6832`, projected into
`scripts/ci-runner/gates.lock.json:6753`) and the lock regenerated with `npm run
gen:gates-lock` (`package.json:169`) -- never hand-edited.

### 6.3 Real-tree plant, done once by hand and recorded in the commit

Add `cat "$f" | grep -q NEEDLE` under an existing `set -euo pipefail` in a renet script;
run `.ci/scripts/quality/pipefail-grep-q.sh`; it must exit 1 naming that file and line.
Remove it; the same command must exit 0 and report the scanned count. Paste both outputs
into the commit message. A gate whose red has never been seen is a gate whose red is a
guess.

## 7. Risks

- **The gate reds on install.** By design: `tee` and `docker` in the list mean
  `i18n.sh:155`, `ci-test.sh:174` and `ci-test.sh:217` must be converted in the SAME change.
  A gate landed green by omitting its own findings is a baseline with extra steps.
- **Superset parity couples the two repos.** A console widening now requires a renet commit
  and a pointer bump in the same PR pair. That is the submodule-first flow this repo already
  runs, and the alternative is silent divergence.
- **The per-file pipefail test is wrong in both directions**, unchanged from console: an
  inner `docker run ... bash -c` that sets only `set -e` reads as pipefail-bearing, and a
  sourced file that sets nothing reads as clean. Say so in the green message, as console's
  does, so nobody reads the tick as coverage it does not have.

## Tasks

Phase 1 -- the renet gate (lands in `private/renet`, branch `0914-1`, rides PR #111)

- [ ] Add `private/renet/.ci/scripts/quality/pipefail-grep-q.sh` per section 5.1: sourced
      `common.sh` + `set +e`, `join_logical`/`offenders` ported from the console bash twin,
      `SCALING_PRODUCERS` = console's 17 + `tee` + `docker` (extras named in
      `RENET_EXTRA_PRODUCERS`), corpus `git ls-files` tracked + untracked over `*.sh` and
      `*.bats`, both anti-vacuity floors, `BASH_SOURCE` main guard, fixtures assembled at
      runtime so the file never carries the racing shape contiguously.
- [ ] Add the twelve in-script controls plus the two mechanism controls (section 6.1);
      verify each one FAILS when its assertion is inverted.
- [ ] Register it as the first line of `run_quality()` in `private/renet/.ci/ci.sh`
      (before line 24).
- [ ] Convert the three sites the new list finds: `private/renet/.ci/scripts/quality/i18n.sh:155`
      (keep the `tee` write to `$WORK/hash-check.log` -- the failure branch `cat`s it),
      `private/renet/scripts/ci-test.sh:174`, `private/renet/scripts/ci-test.sh:217`.
      Keep every grep flag except `-q`; verify by RUNNING each file, not by reading it.
- [ ] Real-tree plant proof (section 6.3); paste the red and the green into the commit.

Phase 2 -- console-side battery test

- [ ] Add `.ci/scripts/test/gates/test-renet-pipefail-grep-q.sh` modelled on
      `.ci/scripts/test/gates/test-renet-deadcode.sh`, including the absent-submodule skip
      and mktemp-only fixtures.
- [ ] Add the superset parity assertion against
      `.ci/rediacc_ci/quality/pipefail_grep_q.py:339` by IMPORTING the port, and the
      declared-extras assertion.
- [ ] Add the manifest entry in `scripts/ci-runner/manifest.ts` next to the existing renet
      one, then regenerate with `npm run gen:gates-lock`; do not hand-edit
      `scripts/ci-runner/gates.lock.json`.
- [ ] Run the battery (`npm run check:ci-quality-gates`) and confirm the new test is
      scheduled and green.

Phase 3 -- close the same hole in console, which the measurement exposed

- [ ] Add `tee` and `docker` to `.ci/scripts/quality/check-pipefail-grep-q.sh:191` and
      `.ci/rediacc_ci/quality/pipefail_grep_q.py:339`, with the measured justification in
      both headers.
- [ ] Convert the four console sites that widening surfaces:
      `.ci/lib/account.sh:792`, `.ci/lib/service.sh:152`, `.ci/lib/service.sh:177`
      (all three `docker ps -a --format '{{.Names}}' | grep -q '^name$'` under
      `.ci/lib/`'s inherited pipefail -- losing the race SKIPS a container teardown or
      reports a running container as absent), and
      `.ci/scripts/private/concurrent-fork-isolation-test.sh:258`.
- [ ] Re-run the twin/port differential on both implementations and confirm byte-identical
      streams, per the porting invariant those two files already carry.

Phase 4 -- the Go-embedded-bash detector (coupling verified in section 3)

- [ ] Add a second detector to the renet gate over `pkg/functions/**/*.go`: a Go string
      literal containing `| grep -q`, with `//` comments stripped. Scope is exactly the one
      path proven to run under pipefail -- `private/renet/pkg/functions/executor_ssh.go:235`
      into `buildScript` at `private/renet/pkg/ssh/streaming.go:183`.
- [ ] Give it its own planted-defect control (a fixture Go file carrying the shape in a raw
      string must be FLAGGED; the same line in a `//` comment must be silent) and its own
      corpus floor (zero Go files scanned -> fail). Today it finds zero sites, and the
      control is the only thing that makes that zero mean anything.

Commit / PR

- [ ] Every commit carries `PR-TASK: e87fa3ce` -- this rides console's existing epic
      (the same one the 2026-09-16 widening and the printf/echo sweep rode) even though
      Phases 1 and 4 land inside the submodule. No second PR: the renet change goes onto
      branch `0914-1` / PR #111, and console's pointer bump plus Phases 2-3 go onto the
      open console PR.
- [ ] Submodule PR first, then the console pointer bump, per the repo's stacked-PR order.
