# PLAN: the printf/echo half of the pipefail/grep -q class
Status: compacted
First-Seen: 2026-09-20
Owner: d778be9d
Full-Text-Blob: b78238643fecdaf894630b6245b3dc7244a1ccff
Record-Sig: 5197a6c5

## Why
The pipefail/grep-q safety gate had been widened to catch 16 scaling commands but explicitly deferred printf and echo as untriaged and unbounded. The operator overruled that deferral and required the remaining class to be closed before shipping.

## Outcome
Completed 2026-09-16 under [unresolved] (commits d67415782, 763425f52, 511765538 in console; submodule renet PR #111). Converted 11 sites across 8 files in console + 2 sites across 2 files in private/renet. Both shell and Python twins verified byte-identical; selftest floor bumped from 18 to 26 controls; all touched files' tests passed 0→0; shadow ledger re-asserted; corpus
pathspecs widened from 478 to 504 files.

## Lessons
- Measured payload ceiling: race between 32–48 KB, not hypothetical. Confirmed via 40 trials per size on this host; below this, loss is rare but real (1129-byte printf lost once in CI 2026-08-31).
- Silent-miss cases (loss stops detecting but returns success) were real and local: .ci/lib/devbox.sh:1082 watching for git dubious-ownership and renet i18n test output. Both would have shipped undetected.
- Gate cannot see inherited pipefail across file boundaries (sourced libraries inherit from sourcer). Built INHERITS_PIPEFAIL_PREFIXES mechanism into both twins to cover .ci/lib/**.
- Corpus external to pathspecs caught two bugs: .ci/lib/ is sourced by live code, .devcontainer/start-kvm.sh offends even the old rule. Widening cost was cheap: 26 files for exactly 2 findings.
- Byte-identical gate twins are a real constraint: four inverted controls plus green-banner text on both sides, shfmt baseline on both, shadow ledger re-key before finish, or else divergence is silent.

## Boxes
- [x] Re-derive the 11-site list by importing `rediacc_ci.quality.pipefail_grep_q` and substituting `SCALING_PRODUCERS`; confirm it matches §1 exactly before touching anything. If it does not, this plan is stale — say so, do not adjust the code to fit it
    (record) sig=f2775b0e done=94f9e2e21
- [x] Add `printf` and `echo` to `SCALING_PRODUCERS` in BOTH `.ci/scripts/quality/check-pipefail-grep-q.sh:120` and `.ci/rediacc_ci/quality/pipefail_grep_q.py:241`, keeping the sorted spelling byte-equal
    (record) sig=43a64fc3 done=94f9e2e21
- [x] Widen the pathspecs in BOTH twins to add `:(glob).ci/lib/**/*.sh`, `:(glob).devcontainer/**/*.sh`, `:(glob).ci/media/**/*.sh` — ONE line each, as `check:ci-pathspec-scope` requires, and byte-equal across the twins
    (record) sig=fe98f8bf done=94f9e2e21
- [x] Add `INHERITS_PIPEFAIL_PREFIXES` (`.ci/lib/`) to both twins so a sourced library is treated as pipefail-bearing
    (record) sig=29621864 done=94f9e2e21
- [x] Rewrite the FOUR inverted controls (twin :266-273, port `main()` :468-472, port `selftest()` :588-592, pytest `a-bounded-builtin-producer`) so each now asserts that a builtin producer IS flagged, with its mirror
    (record) sig=e4666161 done=94f9e2e21
- [x] Rewrite the green-banner blind-spot paragraph in both twins; it currently says the opposite of what will be true
    (record) sig=15933b53 done=94f9e2e21
- [x] Record the `.claude/oracles/**` exclusion and its reason (frozen twins, README.md:49-54, live code is Python) in the gate header, so the next sweep does not re-derive it
    (record) sig=9f7c0b08 done=94f9e2e21
- [x] Record the per-FILE pipefail limitation in the header, citing `.ci/scripts/test/test-install-methods.sh:1129` as the live false positive and `.ci/lib/devbox.sh:1082` as the live false negative
    (record) sig=bc30c6ec done=94f9e2e21
- [x] NEW CONTROL, both twins + port selftest: a BUILTIN producer (`printf`) piped into `grep -q` under pipefail is detected. Mirror: the command-substitution form of the same is not
    (record) sig=e221a74d done=94f9e2e21
- [x] NEW CONTROL, both twins + port selftest: `echo` likewise, with its mirror
    (record) sig=38755a03 done=94f9e2e21
- [x] NEW MECHANISM CONTROL, run for real in a bash child like the existing one at twin :224-244 / port `mechanism_output()`: a **builtin** producer over a ~300 KB payload reports MISSED. The existing control proves SIGPIPE kills an EXTERNAL producer; it does NOT prove the builtin EPIPE path, and without this the two new controls guard a claim nothing on the host has confirmed. Assemble the fixture at runtime, per the existing convention, so the file's own text never carries the racing shape contiguously
    (record) sig=61ca1ffc done=94f9e2e21
- [x] NEW CONTROL: a file under `.ci/lib/` with no `set -o pipefail` of its own IS scanned; mirror, a file elsewhere with no pipefail is not
    (record) sig=9aff61e7 done=94f9e2e21
- [x] Bump `Controls("pipefail-grep-q", floor=18)` in `selftest()` to the new count (21 pass today)
    (record) sig=a9832229 done=94f9e2e21
- [x] Convert `.ci/scripts/test/gates/test-shadow-gate.sh:217` and `:357`
    (record) sig=858c5f97 done=94f9e2e21
- [x] Convert `.ci/scripts/test/proxies/proxy-go-unit.sh:124` — `grep -qx` becomes `grep -Fx`, inside the loop
    (record) sig=21ee2737 done=94f9e2e21
- [x] Convert `.ci/scripts/test/gates/test-media-shims.sh:119` and `:121`, preserving the `||` / `&&` line continuations
    (record) sig=1b4ab335 done=94f9e2e21
- [x] Convert `.ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh:105`, preserving `&& old=0 || old=1`. This line is a deliberate CONTROL proving the old container idiom accepts a longer version; the conversion must not change what it proves
    (record) sig=3093b1de done=94f9e2e21
- [x] Convert `.ci/scripts/test/test-install-methods.sh:1129` AND record in place that the inner `bash -c` shell sets `set -e` only, so this is a defensive conversion, not a bug fix
    (record) sig=ea27bbe1 done=94f9e2e21
- [x] Convert `.ci/lib/devbox.sh:1082` — the real one. `$out` is unbounded and the loss is silent
    (record) sig=90ca5c01 done=94f9e2e21
- [x] Convert `.devcontainer/start-kvm.sh:216` — pre-existing offender under the CURRENT rule, unlocked by the corpus widening
    (record) sig=a2aa105c done=94f9e2e21
- [x] Convert `private/renet/.ci/scripts/quality/i18n.sh:229` (keep the `--`) and `private/renet/scripts/ci-test.sh:515`, on the renet submodule's own branch, submodule-first per the PR convention
    (record) sig=d8f636c2 done=94f9e2e21
- [x] `bash -n` every touched shell file; `npm run check:ci-shell-format` (shfmt) and `npm run check:ci-shell-lint` (shellcheck) clean
    (record) sig=a4c1ff44 done=94f9e2e21
- [x] `npm run check:ci-pipefail-grep-q` exits 0 with the new control count and a scanned count of 478+26
    (record) sig=6497d4f3 done=94f9e2e21
- [x] Run BOTH twins and capture stdout and stderr SEPARATELY; assert byte-identical on both streams (`bash .ci/scripts/quality/check-pipefail-grep-q.sh` vs `PYTHONPATH=.ci python3 -m rediacc_ci.quality.pipefail_grep_q`)
    (record) sig=1cb3b673 done=94f9e2e21
- [x] `python3 -m rediacc_ci.quality.pipefail_grep_q --selftest` — all controls green, count above the bumped floor
    (record) sig=5c2fe67f done=94f9e2e21
- [x] `pytest .ci/rediacc_ci/tests/test_quality_pipefail_grep_q.py` green, including the rewritten parametrized case
    (record) sig=476ab2f6 done=94f9e2e21
- [x] Re-assert the shadow ledger after this BEHAVIOUR change: `npx tsx scripts/lib/shadow-gate.ts --pair w7p2-pipefail-grepq --assert --k 5`. Precedent: the `:(glob)` corpus fix re-keyed the ledger for exactly this reason
    (record) sig=d288cb32 done=94f9e2e21
- [x] Drive the gate RED on purpose: plant one `printf "$x" | grep -q y` under pipefail at a path the pathspecs really match (`scripts/dev/`, NOT `scripts/` depth 1 — the documented trap) and confirm both twins name it, then remove it
    (record) sig=26469fef done=94f9e2e21
- [x] Run each converted file's own test for real and compare exit codes against a pre-conversion run: `test-shadow-gate.sh`, `test-media-shims.sh`, `test-installmethods-linuxpkg-idiom.sh`, `proxy-go-unit.sh`
    (record) sig=e158c7ba done=94f9e2e21
- [x] Re-run `.ci/scripts/quality/check-control-vacuity.sh` at least 10 times and confirm a stable count every time — it is the control this class already corrupted once
    (record) sig=22187554 done=94f9e2e21
- [x] `ruff check` and `ruff format` on the two touched Python files
    (record) sig=beaf467f done=94f9e2e21
- [x] Update `scripts/ci-runner/gates.lock.json` — the entry's `paths` are `pathsOrigin: declared` and list `.ci/scripts/**`, `scripts/**`, `.claude/hooks/**`; the three new corpus roots must be added or the gate stops being triggered by edits to them
    (record) sig=692fe229 done=94f9e2e21
- [x] Commit under `PR-TASK: e87fa3ce`; submodule PR first, then the console pointer bump
    (record) sig=4f7cfee9 done=94f9e2e21

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:41:49Z
Boxes: 33 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/scripts/test/gates/test-run-sh.sh, .ci/scripts/test/test-linux-packages.sh, .ci/scripts/test/gates/test-verify-version.sh, .ci/scripts/housekeeping/cleanup-versions.sh, .ci/scripts/quality/check-label-references.sh, .ci/lib/devbox.sh, private/renet/scripts/ci-test.sh, private/renet/.ci/scripts/quality/i18n.sh, .ci/scripts/test/gates/test-shadow-gate.sh, .ci/scripts/test/proxies/proxy-go-unit.sh, .ci/scripts/test/gates/test-media-shims.sh, .ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh, .ci/scripts/test/test-install-methods.sh, .devcontainer/start-kvm.sh, .ci/scripts/test/lib/test-helpers.sh, .ci/scripts/quality/check-pipefail-grep-q.sh, .ci/rediacc_ci/quality/pipefail_grep_q.py, .ci/rediacc_ci/tests/test_quality_pipefail_grep_q.py, .claude/oracles/README.md, .ci/lib/local-common.sh
Gates: check:ci-pathspec-scope, check:ci-pipefail-grep-q, check:ci-plan-boxes, check:ci-shell-format, check:ci-shell-lint
Why-Source: model
Read-History: `git show b78238643fecdaf894630b6245b3dc7244a1ccff` recovers the text; `git log --find-object=b78238643fecdaf894630b6245b3dc7244a1ccff --all` names the commit

## History
- 2026-09-20T16:41:49Z compacted by d778be9d from `done` (record-sig 5197a6c5)
