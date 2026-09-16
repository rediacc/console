# PLAN: the printf/echo half of the pipefail/grep -q class

Status: draft
Owner: <implementing session>
Updated: 2026-09-16

Successor to the 2026-09-16 widening in `3a7c1bcda`, which added 16 scaling
COMMAND producers and `join_logical()`/`logical_lines()` to
`.ci/scripts/quality/check-pipefail-grep-q.sh` and its port
`.ci/rediacc_ci/quality/pipefail_grep_q.py`, and converted 21 sites across 14
files. Both files' headers state, in as many words, that `printf`/`echo` are
"deliberately absent ... NOT proven safe ... a separate, larger, still-untriaged
class". The operator has overruled that deferral. This plan closes it.

Whoever implements this commits under `PR-TASK: e87fa3ce` (the same epic the
widening rode) and does not open a second PR.

## 1. The count is 11, not ~33, and the sweep's shape is the opposite of the estimate

Measured, not estimated. Every number below came from running the SHIPPED
`logical_lines()` from `.ci/rediacc_ci/quality/pipefail_grep_q.py` with
`SCALING_PRODUCERS` monkey-patched to include `printf` and `echo`, over
`git ls-files`. No regex was reinvented.

| Population | Sites | Files | Verdict |
|---|---|---|---|
| gate's current corpus (478 files), pipefail set | **7** | 5 | convert |
| `.ci/lib/**` — outside the corpus, inherits pipefail from its sourcer | **1** | 1 | convert + widen corpus |
| `.devcontainer/**` — outside the corpus, offends under the CURRENT rule already | **1** | 1 | convert + widen corpus |
| `private/renet` submodule (not reachable by console `git ls-files`) | **2** | 2 | convert, mirror the gate |
| `.claude/oracles/**`, pipefail set | 8 | 2 | **out of scope — FROZEN** |
| any tracked shell file with printf/echo→`grep -q` but NO pipefail | 89 | ~50 | **not a defect** |

**Total to convert: 11 sites across 8 files.**

The ~33 estimate and the 11-file same-line sweep were wrong in both directions:

- **Over**-counted, because the same-line sweep did not strip comments and string
  literals. `.ci/scripts/test/gates/test-run-sh.sh:77`, `.ci/scripts/test/test-linux-packages.sh:49`,
  `.ci/scripts/test/gates/test-verify-version.sh:17`, `.ci/scripts/housekeeping/cleanup-versions.sh:1488` and four hits in
  `check-pipefail-grep-q.sh` itself are PROSE describing the bug;
  `.ci/scripts/quality/check-label-references.sh:159` is a fixture inside a single-quoted string.
  The gate's existing `strip_code()` already rejects all nine — the
  mention-as-execution class its header documents.
- **Under**-counted, because it did not join multi-line pipelines (the
  `check-control-vacuity.sh` lesson) and, more importantly, because it only
  looked where the gate already looks. Three of the eleven sites are outside the
  corpus entirely.

### Enumeration methodology (reuse, do not rebuild)

Do not write a new scanner. The three primitives already exist and are tested:
`rediacc_ci.quality.pipefail_grep_q.logical_lines()`, `.strip_code()`, and
`.offenders_in()`. Enumerate by importing the module and substituting
`SCALING_PRODUCERS`; that is exactly how the numbers above were produced, and it
guarantees the sweep and the gate cannot disagree.

Three corpora must be swept, because the gate's pathspecs cover only the first:

1. `git ls-files ':(glob).ci/scripts/**/*.sh' ':(glob)scripts/**/*.sh' ':(glob).claude/hooks/**/*.sh'`
2. every other tracked file that is a shell file by extension OR shebang
3. each submodule's own `git ls-files` (`private/renet`, `private/homebrew-tap`,
   `private/elite`, `private/account`) — only `renet` has hits, verified.

## 2. The safety criterion, measured on this host

The header's claim ("a bounded producer is less likely to lose the race, never
immune") is true but not actionable. It was made actionable by measurement.

`bash -c 'set -uo pipefail; if printf "%s" "$s" | grep -q NEEDLE; ...'` with
NEEDLE on line 1, 40 trials per size, this host, 2026-09-16:

| payload | printf MISSED | echo MISSED |
|---|---|---|
| 1,219 B | 0/40 | 0/40 |
| 8,289 B | 0/40 | 0/40 |
| 16,470 B | 0/40 | — |
| 32,832 B | 0/40 | — |
| 49,194 B | **32/40** | — |
| 61,516 B | **40/40** | — |
| 65,556 B | **39/40** | **40/40** |
| 300,078 B | **40/40** | — |

So the shell BUILTINS reproduce the class, and the knee is between 32 KB and
48 KB — below the nominal 64 KB pipe buffer, because grep exits after its first
read. This also re-confirms the header's 2026-08-31 datum from the other side:
a 1,129-byte `printf` is 0/80 here and still lost the race once in CI under
load, so sub-knee is *rare*, not *safe*.

### The classifier, two axes, applied per site

**Axis A — can the payload reach ~32 KB?** UNBOUNDED if it interpolates captured
command output, a file's contents, a heredoc, or is emitted in a loop; BOUNDED if
it is a fixed format string plus short scalars, or a value a preceding assertion
has already capped.

**Axis B — what does losing the race cost?** If a MATCH is what the code is
hunting for, losing it is a **SILENT MISS** — the detector stops detecting and
still prints a tick. That is precisely the `check-control-vacuity.sh` damage. If
a match is the EXPECTED normal path, losing it is a **SPURIOUS RED** — loud,
costly, but self-announcing.

The eleven sites, read individually:

| Site | Payload | A | B |
|---|---|---|---|
| `.ci/lib/devbox.sh:1082` | `$out` = `git status --porcelain` of the worktree | UNBOUNDED | **SILENT MISS** — `devbox_identity_ok` stops seeing "dubious ownership" and returns success |
| `private/renet/scripts/ci-test.sh:515` | `$test_output` = full go test output (echoed in full 9 lines above) | UNBOUNDED | **SILENT MISS** — strict mode stops failing on skipped tests |
| `private/renet/.ci/scripts/quality/i18n.sh:229` | `$quality_out` = `go test -v ./pkg/i18n/`, in a loop over 8 test names | UNBOUNDED | spurious red ("these tests never reported PASS", `exit 1`) |
| `.ci/scripts/test/gates/test-shadow-gate.sh:217` | `$SG_ERR` = a mutated comparator's whole stderr | UNBOUNDED | spurious red |
| `.ci/scripts/test/gates/test-shadow-gate.sh:357` | `$SG_OUT` = shadow-gate's whole stdout | UNBOUNDED | spurious red |
| `.ci/scripts/test/proxies/proxy-go-unit.sh:124` | `$EXCLUDED_DIRS` = `grep -rl \| xargs dirname \| sort -u` over `pkg/`, re-emitted inside a `while read` loop | CORPUS-SCALING | spurious red (a root-only package stops being excluded) |
| `.ci/scripts/test/gates/test-media-shims.sh:121` | `$code` | BOUNDED (≤4 lines, see below) | **SILENT MISS** — the "a shim that reads argv" detector |
| `.ci/scripts/test/gates/test-media-shims.sh:119` | `$code` | BOUNDED | spurious red |
| `.ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh:105` | one `printf` format + `$TEST_VERSION` | BOUNDED (~25 B) | spurious red |
| `.ci/scripts/test/test-install-methods.sh:1129` | `$script` = curl of install.sh, **17,088 B today** | UNBOUNDED-ish | **not actually live — see §5** |
| `.devcontainer/start-kvm.sh:216` | `id -G \| tr` | bounded | not printf/echo; offends the CURRENT rule |

`$code` at `.ci/scripts/test/gates/test-media-shims.sh:119/121` is provably bounded: the immediately
preceding `[ "$lines" -le 4 ] || log_fail ...`, and `log_fail` in
`.ci/scripts/test/lib/test-helpers.sh:24` **exits 1**. So control flow cannot
reach the two pipelines with more than 4 lines in `$code`.

## 3. The fix, and the three edge cases the existing header does not state

Same drop-in as the 16-command sweep:

    [ -n "$(producer | grep -E '<pattern>')" ]

`printf`/`echo` need no different treatment — the failure mode differs in
mechanism (a builtin takes EPIPE and returns non-zero; an external producer is
SIGPIPE'd to 141) but is identical in effect under `pipefail`. Three caveats
must be respected per site and are worth adding to the gate header:

1. **Keep every grep flag except `-q`.** `.ci/scripts/test/proxies/proxy-go-unit.sh:124` is `grep -qx`
   (→ `grep -Fx`), `private/renet/.ci/scripts/quality/i18n.sh:229` is `grep -q --` (the `--` is load-bearing:
   the pattern starts `--- PASS:`). The header's `grep -E` spelling is an
   example, not the rule.
2. **`[ -n "$(...)" ]` is NOT equivalent when the pattern can match an empty
   line.** Command substitution strips the output, so a matched empty line reads
   as no match. Checked against all 11 patterns: none can match empty. Record the
   check; do not assume it for the next sweep.
3. **`set -e` behaviour is unchanged** because the converted test sits in the
   same position in the same `&&`/`||` list (`media-shims:119/121`,
   `installmethods-linuxpkg-idiom:105` all end in `|| log_fail` / `&& log_fail` /
   `&& old=0 || old=1`). Verify by running the files, not by reading them.

No `printf -v`, no `echo -n`, no side-effect-only printf appears among the 11.

## 4. Gate change, parity, and what inverts

The gate change is one line in each twin — `printf` and `echo` join
`SCALING_PRODUCERS` — but it **inverts four existing controls that assert the
opposite**, and every one must be rewritten in the same commit or the change is
incoherent:

- `.ci/scripts/quality/check-pipefail-grep-q.sh:266-273` — `control: a bounded
  producer (printf, not a local function) is not flagged`
- `.ci/rediacc_ci/quality/pipefail_grep_q.py:468-472` — the same control in
  `main()`, which must stay **byte-identical** to the twin's output
- `.ci/rediacc_ci/quality/pipefail_grep_q.py:588-592` — `MIRROR: a bounded
  builtin producer is not flagged` in `selftest()`
- `.ci/rediacc_ci/tests/test_quality_pipefail_grep_q.py:158-162` — the
  `id="a-bounded-builtin-producer"` parametrized case expecting 0 hits

Plus the green-banner text in both twins ("A bounded producer (printf, echo) is
untriaged, not cleared: a 1129-byte printf raced on 2026-08-31"), which becomes
false and must change identically on both sides.

**Python-port parity: yes, the port models the concept directly.**
`SCALING_PRODUCERS` is a tuple at `.ci/rediacc_ci/quality/pipefail_grep_q.py:241`, `logical_lines()` is
the port of `join_logical()`, and the shadow ledger compares the two verdicts
byte for byte. A one-sided edit is a false divergence.

**Do the swept files have their own twins?** Two do, and both are the reason to
LEAVE them alone: `.claude/oracles/pre-edit/block-compacted-plan-edit.sh` (7
sites) and `.claude/oracles/pre-bash/block-unlinked-commit-author.sh` (1) are the
FROZEN bash originals for `.claude/rediacc_hooks/guards/block_compacted_plan_edit.py`
and `block_unlinked_commit_author.py`. `.claude/oracles/README.md:49-54`: "They
are FROZEN. Do not fix a bug here; fix it in the port." Nothing registers them;
the live code is Python and has no pipe. They are correctly excluded from the
corpus and stay excluded. **State this in the gate header**, or the next sweep
re-discovers 47 files and 104 sites and has to re-derive why they do not count.

`private/renet` has no copy of this gate (`find private/renet -name '*pipefail*'`
is empty), so the console gate cannot reach its two sites and neither can
anything else. Mirroring the gate into renet is a real option but is a second
PR's worth of work; this plan converts the two sites and files the gate-mirror as
the follow-on.

## 5. `.ci/scripts/test/test-install-methods.sh:1129` is a FALSE POSITIVE, and it is the honest one

The widened gate flags it because the OUTER file sets `set -euo pipefail` at
line 29. The line itself lives inside a `docker run ... bash -c "..."` heredoc
whose inner shell sets **`set -e` only** (line 1057, and the same at 800, 886,
925, 965, 1010, 1097). Without `pipefail` the pipeline reports grep's status and
the match stands: there is no bug at that line.

Convert it anyway — it costs nothing, it is defensively correct if anyone ever
adds `-o pipefail` to those container scripts, and the alternative (an allowlist
entry) would be a suppression, which this repo forbids. **But record the reason
in place**, because a future reader diffing the file will otherwise conclude the
gate proved something it did not. This is also the honest disclosure the gate
header owes: its pipefail test is per-FILE and cannot see an inner shell's
options, in either direction.

## 6. Corpus: widen it, because it is where one of the two silent-miss bugs lives

`.ci/lib/devbox.sh:1082` is the strongest single finding in this plan and the
gate cannot see it for TWO independent reasons: `.ci/lib/**` is not in the
pathspecs, and the file does not set `pipefail` itself. It inherits it — sourced
by `scripts/dev/worktree.sh` (`set -euo pipefail`, line 12) and by
`.ci/lib/local-common.sh:937,983`, which is sourced by `rdc.sh` (`set -euo
pipefail`, line 11). It is a live, user-facing detector whose loss is silent.

Measured cost of widening: adding `:(glob).ci/lib/**/*.sh`,
`:(glob).devcontainer/**/*.sh` and `:(glob).ci/media/**/*.sh` brings in 26 files
and produces exactly **2** findings — the two already listed. Cheap.

The sourced-library inheritance is a separate rule change. Measured over every
tracked shell file that lacks its own `pipefail` and is sourced by one that has
it: **exactly 1 site in the whole repo**, `.ci/lib/devbox.sh:1082`. Building a
source-graph analyser for one site is not proportionate. Recommendation: widen
the pathspecs, add a short `INHERITS_PIPEFAIL_PREFIXES = (".ci/lib/",)` treated
as pipefail-bearing (one constant, one `or`, mirrored in both twins, one control
each side), and note the general limitation in the header.

## Tasks

- [ ] Re-derive the 11-site list by importing `rediacc_ci.quality.pipefail_grep_q` and substituting `SCALING_PRODUCERS`; confirm it matches §1 exactly before touching anything. If it does not, this plan is stale — say so, do not adjust the code to fit it
- [ ] Add `printf` and `echo` to `SCALING_PRODUCERS` in BOTH `.ci/scripts/quality/check-pipefail-grep-q.sh:120` and `.ci/rediacc_ci/quality/pipefail_grep_q.py:241`, keeping the sorted spelling byte-equal
- [ ] Widen the pathspecs in BOTH twins to add `:(glob).ci/lib/**/*.sh`, `:(glob).devcontainer/**/*.sh`, `:(glob).ci/media/**/*.sh` — ONE line each, as `check:ci-pathspec-scope` requires, and byte-equal across the twins
- [ ] Add `INHERITS_PIPEFAIL_PREFIXES` (`.ci/lib/`) to both twins so a sourced library is treated as pipefail-bearing
- [ ] Rewrite the FOUR inverted controls (twin :266-273, port `main()` :468-472, port `selftest()` :588-592, pytest `a-bounded-builtin-producer`) so each now asserts that a builtin producer IS flagged, with its mirror
- [ ] Rewrite the green-banner blind-spot paragraph in both twins; it currently says the opposite of what will be true
- [ ] Record the `.claude/oracles/**` exclusion and its reason (frozen twins, README.md:49-54, live code is Python) in the gate header, so the next sweep does not re-derive it
- [ ] Record the per-FILE pipefail limitation in the header, citing `.ci/scripts/test/test-install-methods.sh:1129` as the live false positive and `.ci/lib/devbox.sh:1082` as the live false negative
- [ ] NEW CONTROL, both twins + port selftest: a BUILTIN producer (`printf`) piped into `grep -q` under pipefail is detected. Mirror: the command-substitution form of the same is not
- [ ] NEW CONTROL, both twins + port selftest: `echo` likewise, with its mirror
- [ ] NEW MECHANISM CONTROL, run for real in a bash child like the existing one at twin :224-244 / port `mechanism_output()`: a **builtin** producer over a ~300 KB payload reports MISSED. The existing control proves SIGPIPE kills an EXTERNAL producer; it does NOT prove the builtin EPIPE path, and without this the two new controls guard a claim nothing on the host has confirmed. Assemble the fixture at runtime, per the existing convention, so the file's own text never carries the racing shape contiguously
- [ ] NEW CONTROL: a file under `.ci/lib/` with no `set -o pipefail` of its own IS scanned; mirror, a file elsewhere with no pipefail is not
- [ ] Bump `Controls("pipefail-grep-q", floor=18)` in `selftest()` to the new count (21 pass today)
- [ ] Convert `.ci/scripts/test/gates/test-shadow-gate.sh:217` and `:357`
- [ ] Convert `.ci/scripts/test/proxies/proxy-go-unit.sh:124` — `grep -qx` becomes `grep -Fx`, inside the loop
- [ ] Convert `.ci/scripts/test/gates/test-media-shims.sh:119` and `:121`, preserving the `||` / `&&` line continuations
- [ ] Convert `.ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh:105`, preserving `&& old=0 || old=1`. This line is a deliberate CONTROL proving the old container idiom accepts a longer version; the conversion must not change what it proves
- [ ] Convert `.ci/scripts/test/test-install-methods.sh:1129` AND record in place that the inner `bash -c` shell sets `set -e` only, so this is a defensive conversion, not a bug fix
- [ ] Convert `.ci/lib/devbox.sh:1082` — the real one. `$out` is unbounded and the loss is silent
- [ ] Convert `.devcontainer/start-kvm.sh:216` — pre-existing offender under the CURRENT rule, unlocked by the corpus widening
- [ ] Convert `private/renet/.ci/scripts/quality/i18n.sh:229` (keep the `--`) and `private/renet/scripts/ci-test.sh:515`, on the renet submodule's own branch, submodule-first per the PR convention
- [ ] `bash -n` every touched shell file; `npm run check:ci-shell-format` (shfmt) and `npm run check:ci-shell-lint` (shellcheck) clean
- [ ] `npm run check:ci-pipefail-grep-q` exits 0 with the new control count and a scanned count of 478+26
- [ ] Run BOTH twins and capture stdout and stderr SEPARATELY; assert byte-identical on both streams (`bash .ci/scripts/quality/check-pipefail-grep-q.sh` vs `PYTHONPATH=.ci python3 -m rediacc_ci.quality.pipefail_grep_q`)
- [ ] `python3 -m rediacc_ci.quality.pipefail_grep_q --selftest` — all controls green, count above the bumped floor
- [ ] `pytest .ci/rediacc_ci/tests/test_quality_pipefail_grep_q.py` green, including the rewritten parametrized case
- [ ] Re-assert the shadow ledger after this BEHAVIOUR change: `npx tsx scripts/lib/shadow-gate.ts --pair w7p2-pipefail-grepq --assert --k 5`. Precedent: the `:(glob)` corpus fix re-keyed the ledger for exactly this reason
- [ ] Drive the gate RED on purpose: plant one `printf "$x" | grep -q y` under pipefail at a path the pathspecs really match (`scripts/dev/`, NOT `scripts/` depth 1 — the documented trap) and confirm both twins name it, then remove it
- [ ] Run each converted file's own test for real and compare exit codes against a pre-conversion run: `test-shadow-gate.sh`, `test-media-shims.sh`, `test-installmethods-linuxpkg-idiom.sh`, `proxy-go-unit.sh`
- [ ] Re-run `.ci/scripts/quality/check-control-vacuity.sh` at least 10 times and confirm a stable count every time — it is the control this class already corrupted once
- [ ] `ruff check` and `ruff format` on the two touched Python files
- [ ] Update `scripts/ci-runner/gates.lock.json` — the entry's `paths` are `pathsOrigin: declared` and list `.ci/scripts/**`, `scripts/**`, `.claude/hooks/**`; the three new corpus roots must be added or the gate stops being triggered by edits to them
- [ ] Commit under `PR-TASK: e87fa3ce`; submodule PR first, then the console pointer bump

## Remaining

- [ ] FOLLOW-ON, not this PR: `private/renet` has no copy of this gate, so its two sites had no gate and its next one will have none either. Mirroring the gate into renet is its own change.
