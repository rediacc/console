# PLAN: a fast loop -- incremental pre-push receipt, commit reminder, one pre-push per push, no push into a running CI run

Status: approved -- operator 2026-10-06 (/ask 13:57Z, "Yes, implement it as written"): ships on 1006-2 / PR #597 under its Operational-Reason, because the loop's speed blocks everything after it. PLAN-ci-consolidation.md stays on the next branch.
Owner: d778be9d
First-Seen: 2026-10-06
Depends-On: no-dep -- supersedes PLAN-commit-as-you-go.md (its open T6 moves here; D0-D10 ticked as superseded) and PLAN-uncommitted-work-exposure-check.md (all seven boxes move here)
Priority: P0 -- operator 2026-10-06: "the loop is too slow. Fix it NOW, on 1006-2 / PR #597".
Concurrency: parallel -- writers are disjoint by file (section 6); the lead owns the shared integration files
Owns: scripts/ci-runner/input-hash.ts, scripts/ci-runner/run.ts, .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py, .claude/rediacc_hooks/tests/goldens/**, .ci/policy/carry-exempt.json, .ci/rediacc_ci/tests/gates/test_gate_incremental_receipt.py, .claude/hooks/stop/*.py, .claude/hooks/post-tool/**, .claude/hooks/post-bash/**, .claude/rediacc_hooks/lifecycle.py, .claude/settings.json, .claude/rediacc_hooks/plan_gate.py, .claude/rediacc_hooks/tests/test_wl_*.py, agent/plans/QUEUE.md, CLAUDE.md, .claude/commands/pr-merge.md, .claude/agents/pr-babysitter.md, docs/agent-reference/ci-gates.md
Worklist: #eaf3d3f1

## Why (measured on 1006-2, 2026-10-06)

- A commit costs seconds, plus 6-12 s for the gen-docs pre-commit.
- Every non-record commit voids the whole pre-push receipt: about 350 gates, about 15 minutes.
- Every push restarts Console CI: about 45 minutes.
- Three receipts this session never led to a push: df0b7b23d, 61a914c5e, and the run on 0ce704575 stopped partway.

## Settling the two older plans

- PLAN-commit-as-you-go.md: T0-T5 and T7-T11 landed; D0-D10 ticked as superseded (PR #590 merged 0923-1 on 2026-09-30, 49e61a1a5). T6 moves here unchanged: its first bullet is live (`worklist.py --tick` refuses with `no-commit-ref`, .claude/hooks/stop/worklist.py:1231), its second is Part 2, its third is the stand-down keep-list question settled in the notes below. The plan then moves to `_done/`.
- PLAN-uncommitted-work-exposure-check.md: its design (a transcript cursor attributing dirty files to this session) is Part 2's engine, so all seven boxes move here unchanged with notes, and the plan moves to `_removed/` (reason: boxes moved into this plan).

## Part 1: incremental receipt (design: opus Plan agent, 2026-10-06)

Today `scripts/ci-runner/run.ts` writes `.ci/cache/prepush-receipt.json` (Receipt :2292-2371, minted :3060-3110) and `block_unverified_push.py` (`run()` :1144-1286) accepts it only for the pushed tree or a record-only `advance_chain` (:930).

- `inputHash(g) = sha256(SCHEMA=2 | defHash | filesHash | saltHash | needs hashes)`.
  - defHash: the gate's lock entry as canonical JSON plus its npm script closure, so a changed gate re-runs.
  - filesHash: sorted `<mode> <oid>\t<path>` lines from one `git ls-tree -r HEAD^{tree}` over the gate's `paths`, its `leafClosure(leaves)` and the global inputs (every package-lock.json, uv.lock, .devcontainer/toolchain.env, pyproject.toml, scripts/ci-runner/**). A glob into a submodule resolves to its gitlink.
  - saltHash: node and python versions, platform, toolchain.env; carrying requires an equal salt.
  - null (always runs) when the gate declares no `paths`, its leaf closure hit the cap, a `needs` node is null, it has an `env` entry, or it is listed in `.ci/policy/carry-exempt.json` with a reason.
- Incremental mode only in a disposable clone (`isDisposableClone`, scripts/ci-runner/run.ts:592), so the tree is the bytes.
- Receipt v2: per gate `inputHash, defHash, filesHash, inputs, verdict (ok|fail|blocked|deferred|ciOnly), exitCode, findings, judgedTree, carriedFrom`. A carried entry keeps its verdict and findings; `failed`/`exitCode` are computed over fresh and carried entries together, so a carried red stays red and still clears carried-reds.json by exact key. Every receipt is archived as `receipts/<headTree>.json`.
- Guard v2: every `gate:true` non-slow id has an entry; each carried entry's defHash and filesHash are recomputed at the pushed tree and must match, and the archived origin receipt must agree; the fail set must equal `failed`. A v1 receipt is refused (clean break, operator constraint).
- Measured ceiling: 45 of 351 gates declare `paths` (2324 of 6325 gate-seconds), so most gates still re-run; the gain grows as gates declare inputs.

## Hash contract (frozen 2026-10-06; TS in input-hash.ts and Python in the guard implement exactly this)

- `canon(x)`: JSON with object keys sorted at every depth, separators `,` and `:` with no spaces, non-ASCII left as UTF-8 (TS `JSON.stringify` of a key-sorted copy; Python `json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`). Lock entries hold only strings, booleans, integers, arrays and objects; a float in a lock entry makes the gate non-carriable.
- `sha(s)`: lowercase hex sha256 of the UTF-8 bytes.
- `defHash = sha("def\n" + canon(lockEntry) + "\n" + canon(scripts))`, where `scripts` maps each npm script name in the gate's script closure to its text in the root package.json at the judged tree. The receipt records the names in `inputs.scripts`.
- Input files: every tracked path at the judged tree (from `git ls-tree -r --full-tree <tree>`, so gitlinks appear as `160000 commit <oid>`) that matches one of `inputs.globs` or equals one of `inputs.files`. `inputs.globs` is the gate's `paths` plus the global inputs; `inputs.files` is the leaf closure, resolved by the runner. Glob grammar: `**` matches any run of characters including `/`, `*` matches any run without `/`, every other character is literal; a lock `paths` entry containing `?`, `[` or `{` makes the gate non-carriable. A glob naming a directory that is a gitlink matches that gitlink entry.
- `filesHash = sha("files\n" + join(sorted lines))`, each line `"<mode> <oid>\t<path>\n"`, sorted by path bytes.
- `saltHash = sha("salt\n" + node --version + "\n" + python3 --version + "\n" + platform + "\n" + arch + "\n" + <bytes of .devcontainer/toolchain.env at the judged tree>)`; carrying needs the prior receipt's saltHash equal.
- `inputHash = sha("input\n" + defHash + "\n" + filesHash + "\n" + saltHash + "\n" + join(sorted needs inputHashes, "\n"))`; null when the gate is not carriable (no `paths`, an `env` entry, listed in `.ci/policy/carry-exempt.json`, a null `needs` hash, a leaf closure at its cap, or a forbidden glob character).
- Global inputs: `**/package-lock.json`, `**/uv.lock`, `.devcontainer/toolchain.env`, `pyproject.toml`, `scripts/ci-runner/**`.

## Parts 2-4: advisories, never blocks

- Part 2, commit reminder: when this session has uncommitted edits in its own paths (Part 2 engine: the transcript cursor below) and no commit for `commit_remind_min` minutes (QUEUE.md `## Settings`, default 15), the Stop hook and a PostToolUse member say to commit the verified unit.
- Part 3, one pre-push per push: on a `ci:quick` / pre-push command the post-bash hook advises waiting until a push is due (a milestone, a fix for a red, or a stop with unpushed commits); when the receipt's tree is N code commits behind HEAD (record-only commits excluded, the guard's record policy), the Stop hook says so in one line.
- Part 4, no push into a running run: when the PR's run on the pushed head is in progress and not red (the cached `wl_ci.ci_trouble` read, no extra GitHub call), the post-bash hook on `git push` and the Stop hook advise holding local commits; a red with a fix in hand pushes at once. Nothing refuses a push.

## Tasks

- [x] T6 [B] Worklist changes:
  - The tick arm requires `commit:<sha>` or `nocommit:<reason>` (section 3.4).
  - Re-scope PLAN-uncommitted-work-exposure-check.md's `V_UNCOMMITTED_RISK` from "informational" to a push to commit.
  - Add its key to Y's focus keep-list and to `wl_roster.CAP_WAIT_KEEPS`.
    > 2026-10-06 note: first bullet already live (.claude/hooks/stop/worklist.py:1231 `no-commit-ref`); second bullet is Part 2 as an advisory per the operator; third bullet: the advisory key joins `wl_standdown.FOCUS_ADVISORY_KEYS`, not `CORE` or `CAP_WAIT_KEEPS`, because a reminder never blocks. Ticked when F6 lands.
    (ticked) 2026-10-06T15:07:12Z by d778be9d: commit:390bcbccc no-commit-ref live; commit-remind advisory landed; keys in FOCUS_ADVISORY_KEYS
- [x] Add `wl_uncommitted.py` beside `wl_admit.py`/`wl_bgsweep.py`: the transcript-cursor reader (bounded catch-up per section 1), the `uc_files` union (write-once `first_seen_epoch` per path), the throttled `git status --porcelain` intersection (section 5), and the age/volume trigger evaluation (section 4).
    > 2026-10-06 note: the transcript cursor and `uc_files` stay; the trigger becomes Part 2's 'no commit for `commit_remind_min` minutes' (F5), not age 120 / count 15.
    (ticked) 2026-10-06T15:06:57Z by d778be9d: commit:390bcbccc test_wl_commit_remind.py 28 passed
- [x] Add `V_UNCOMMITTED_RISK` to `worklist_messages.py`: names the count and oldest age of this-session's-own still-dirty files (capped list + remainder count) and pushes the session to commit each verified unit by path, or to tick with `nocommit:<reason>` (Re-scope).
    > 2026-10-06 note: operator 2026-10-06: a REMINDER, never a block. The text pushes to commit the verified unit; it is advisory (`vadd(..., False)` or `outq_add`), so the Re-scope's 'blocking check' is overruled.
    (ticked) 2026-10-06T15:06:58Z by d778be9d: commit:390bcbccc N_COMMIT_REMIND in worklist_messages.py; message catalogue test passes
- [x] Wire into `wl_checks.py` (after the `poll_fast_path` exit, alongside the other per-stop fact-gatherers near `docs_drift`'s call site) as `vadd("uncommitted-risk", True, ...)`, wrapped in the same `try/except Exception` every sibling detector uses, and add `"uncommitted-risk"` to `wl_standdown.CORE` in the same change (Re-scope).
    > 2026-10-06 note: wired as an advisory, so `uncommitted-risk` does NOT join `wl_standdown.CORE` (CORE keys block); it joins `FOCUS_ADVISORY_KEYS` so focus mode releases it.
    (ticked) 2026-10-06T15:06:59Z by d778be9d: commit:390bcbccc advisory only, test_wl_commit_remind.py proves stops still allow
- [x] New env-tunable constants: `WORKLIST_UNCOMMITTED_AGE_MIN` (120), `WORKLIST_UNCOMMITTED_COUNT_MIN` (15), `WORKLIST_UNCOMMITTED_CHECK_MIN` (10).
    > 2026-10-06 note: superseded by F5: one QUEUE.md `## Settings` key `commit_remind_min` (default 15) replaces the three env constants; the git-status throttle keeps a fixed 10-minute floor in code.
    (ticked) 2026-10-06T15:07:01Z by d778be9d: commit:302091dce commit:390bcbccc commit_remind_min replaces the env constants
- [x] Test file (`test-uncommitted.py`): synthetic transcript fixtures for the cursor; a fake `git status --porcelain` intersection test proving a peer's dirty file is never reported; the age/volume trigger boundary cases; the throttle (assert via a monkeypatched/counting `subprocess.run`); and a grep-based control asserting the new module's source contains none of `add\b|commit\b|stash\s+(push|pop|apply|...)|restore\b|checkout\s+--|clean\b|reset\b` as a live-executed `git` argument.
    > 2026-10-06 note: unchanged; the test file is `.claude/rediacc_hooks/tests/test_wl_commit_remind.py` (pytest lane, check:ci-pytest) instead of a standalone test-*.py.
    (ticked) 2026-10-06T15:07:02Z by d778be9d: commit:390bcbccc test_wl_commit_remind.py 28 passed
- [x] File, separately and out of this plan's scope, a narrow finding against `.claude/oracles/pre-bash/block-destructive-git-restore.sh`'s `STASH_VERB` regex: `git stash create` does not mutate the working tree or index and arguably should not share a blocklist entry with the mutating stash verbs.
    > 2026-10-06 note: kept as written: a separate narrow finding, added to the worklist when this box is worked.
    (ticked) 2026-10-06T15:07:04Z by d778be9d: nocommit:research filed as worklist #fa9bb664 against .claude/rediacc_hooks/guards/block_destructive_git_restore.py:47
- [x] Run the new test file plus the full `wl_checks`/`wl_store` suite; confirm no regression.
    > 2026-10-06 note: unchanged.
    (ticked) 2026-10-06T15:07:05Z by d778be9d: commit:390bcbccc 169 passed; stop control scripts all pass
- [x] F1 [U1] `scripts/ci-runner/input-hash.ts` (new): canonicalDef, resolveInputs, filesHash, inputHash with needs recursion, isCarriable, planCarry, inputHashSelftest, and a `--print-corpus` CLI for the parity test.
    (ticked) 2026-10-06T14:30:09Z by d778be9d: commit:8779b09d7 input-hash.ts --selftest exit 0, --print-corpus HEAD 364 entries, tsc exit 0
- [x] F2 [U2] `scripts/ci-runner/run.ts`: receipt v2, carry before buildGraph, merged failed/exitCode, the receipt archive, the disposable-clone precondition, and selftests INCREMENTAL-PROOF-1 (one-file change re-runs only affected gates), INCREMENTAL-PROOF-2 (planted change to a carried gate's input forces its re-run), INCREMENTAL-PROOF-3 (planted red stays red when carried), plus controls (no-paths gate always runs, changed `run` re-runs, salt mismatch runs all).
    (ticked) 2026-10-06T14:32:29Z by d778be9d: commit:3cab21d70 check:ci-runner-selftest 206 assertions ok, tsc exit 0, biome clean
- [x] F3 [U3] `block_unverified_push.py` v2_verdict with fixtures push-v2-carried-ok, push-v2-carried-stale-input, push-v2-carried-red, a planted DEFECT, its test-*.py cases and a re-frozen golden.
    (ticked) 2026-10-06T14:36:52Z by d778be9d: commit:6b3146dce test-block_unverified_push.py rc 0 (126 cases), differential 1503 passed, golden drift 3 passed
- [x] F4 [U4] `.ci/policy/carry-exempt.json` (network, time, history and cache-reading gates, each with a reason of at least 80 characters) and `.ci/rediacc_ci/tests/gates/test_gate_incremental_receipt.py`: TS `--print-corpus` equals the guard's Python hashing on one corpus, no lock `paths` entry contains `?`, every exempt id exists.
    (ticked) 2026-10-06T14:36:53Z by d778be9d: commit:8779b09d7 commit:6b3146dce test_gate_incremental_receipt.py 21 passed; check:ci-policy-inventory rc 0
- [x] F5 QUEUE.md `## Settings` key `commit_remind_min` (integer, default 15): wl_planqueue INT_KEYS/SETTINGS_KEYS/Settings, plan_gate `_default_settings`, the QUEUE.md doc bullet, CLAUDE.md's key list, `--queue-set` usage text, test_wl_queue_settings.py cases.
    (ticked) 2026-10-06T14:30:11Z by d778be9d: commit:302091dce test_wl_queue_settings.py and siblings 180 passed; --queue-set prints commit_remind_min: 15
- [x] F6 Part 2 wiring: the Stop advisory and a post-tool member (`.claude/hooks/post-tool/commit_remind.py`) reading the same state; lifecycle.py PATTERNS row and settings.json together.
    (ticked) 2026-10-06T15:07:06Z by d778be9d: commit:390bcbccc test_wl_commit_remind.py, test_settings_collapse.py, test_hooks_wiring.py pass
- [x] F7 Part 3: post-bash member advising against a receipt before a push is due, and the Stop line "receipt is N code commits behind HEAD".
    (ticked) 2026-10-06T15:07:08Z by d778be9d: commit:390bcbccc test_wl_loopspeed.py 31 passed; live note seen on the prepush call
- [x] F8 Part 4: post-bash member on `git push` and a Stop line, from the cached PR CI state, advising to hold commits while the run is in progress and not red.
    (ticked) 2026-10-06T15:07:09Z by d778be9d: commit:390bcbccc test_wl_loopspeed.py ci-hold cases pass
- [x] F9 Docs: .claude/commands/pr-merge.md, .claude/agents/pr-babysitter.md, docs/agent-reference/ci-gates.md; `npx tsx scripts/gen/gen-docs.ts --write`.
    (ticked) 2026-10-06T15:07:10Z by d778be9d: commit:bb047b33a prose and citation gates rc 0
- [ ] F10 Live proof on 1006-2: after one one-file commit, the receipt re-runs only the gates whose inputs that file reaches, and `git push` passes block_unverified_push on carried entries.

## Writers (sonnet, at most 4, disjoint)

- U1: scripts/ci-runner/input-hash.ts. U2 (after U1's API is frozen): scripts/ci-runner/run.ts. U3: the guard, its test-*.py and golden. U4: carry-exempt.json and the parity test.
- The lead does F5-F9 (the shared Stop-hook files, lifecycle.py and settings.json move together) and F10.
- No continue-on-error, no suppressions, no compatibility fallbacks: the guard reads only a v2 receipt, and a v1 receipt is refused with the command that writes a v2 one.
