# PLAN: gh Swallow-Failure Sweep Across `.ci/scripts` — Registered-Gate False-Green Risks

Status: done
Owner: f4da5c2e
Updated: 2026-09-10

Sections: Problem, Full verified instance list, Fix design per REGISTERED-GATE instance (literal diffs), Test plan, Execution recommendation.

## Tasks

- [x] Fix instance #2 (.ci/scripts/quality/check-pr-description.sh:59-62 + .ci/rediacc_ci/quality/pr_description.py:287-291): a swallowed LATEST_COMMIT_TIME fetch failure now escalates (exit 1 / return 1), not warn-and-skip
- [x] Fix instance #8 (check-submodule-branches.sh get_console_pr_body + submodule_branches.py console_pr_body): now routes through gh_retry/gh_probe, distinguishes fetch-failed from empty-body, escalates on failure
- [x] Fix instance #9 (.ci/scripts/quality/check-label-inventory.sh:346-351 + .ci/rediacc_ci/quality/label_inventory.py:602-621): a failed live-label API fetch now refuses the drift comparison instead of silently reporting "all agree"
- [x] Fix instances #11/#12 (.ci/scripts/release/mark-production.sh:102-110): a failed tag object-type/deref lookup now aborts instead of silently moving the production tag to the wrong object
- [x] Add/extend tests for all four fixes: pr_description 2 differential cases flipped/added (14/14 pass), a new console_pr_body gh-stub test pair (35/35 pass total), a label-inventory GitHub-API-branch test (20/20 pass), two mark-production gate-test cases (7/7 pass)
- [x] Sweep and classify every gh-swallow instance across .ci/scripts (30 verified, 4 registered-gate/production-correctness fixes identified, rest confirmed already-safe or genuine best-effort housekeeping)

## COMPLETE 2026-09-10: all 4 fixes done inline by the driver

Both writer slots stayed occupied the whole time this plan was queued, and per this
session's standing lesson (paid for twice already on check-commands.sh) "queued" is not a
reason to sit idle -- the driver implemented all 4 fixes directly. Every fix landed in BOTH
the bash twin and the live Python port (per the plan's own headline finding: 3 of 4 named
gates are actually Python-live now), plus a matching test change. `bash -n` clean on all 5
touched bash files; `python3 -m ast` clean on all 6 touched Python files.

**Full verification**: `check:ci-language-policy` unaffected (509, 0 added -- edits only, no
new/deleted bash file); `check:ci-python-lint` and `check:ci-dead-python` show zero findings
in any of the 6 Python files touched; the full pytest suites for all three touched test
files pass (14/14 pr_description, 20/20 label_inventory, 35/35 submodule_branches); the
bash-side `test-mark-production.sh` battery passes 7/7 including the 2 new anti-regression
cases. **The live registered gate itself was re-run against the real tree, not just the
fixture harness**: `npm run check:ci-label-inventory` -> `✓ label inventory reconciled: 29
declared, 29 live (source: GitHub API); names, descriptions and colours all agree` --
confirms the fix does not break the real, authenticated `gh` path in this environment.
`git status` scoped to exactly the 11 intended files, nothing else.

**One implementation deviation from the plan's literal diff, noted for the record**: the
`console_pr_body` Python fix uses `gh_probe(False, ..., [..., "--jq", ".body // empty"])`
directly (matching the bash twin's own `gh_retry ... --jq '.body // empty'` call exactly)
rather than the plan's suggested manual `json.loads(...).get("body")` parsing -- simpler and
more faithful to the twin's actual behavior, verified equivalent. Also added `.rstrip("\n")`
on the `gh_probe` output (not in the plan's diff) since `gh_probe` doesn't strip trailing
newlines the way bash's `$(...)` command substitution does, matching this file's own
established convention (`.strip()` used at 4 other call sites in the same module).

---

## 0. Headline finding that reframes the whole sweep

**The four "registered gate" bash files named in the task background are NOT the live gates anymore.** As of the 2026-09-08 "W7 P4" cutover, all four have been ported to Python and the bash files are retained only as **differential twins** (compared against the port via `scripts/lib/shadow-gate.ts`, never executed as the real gate):

| Bash twin (grep hit here) | Live registered gate (the code that actually runs in CI) | How it's wired |
|---|---|---|
| `.ci/scripts/quality/check-pr-description.sh` | `.ci/rediacc_ci/quality/pr_description.py` (entry: `check_pr_description.py`) | hand-registered directly in `.github/workflows/ci-quality.yml` (`quality-static` job), exempted from `check:ci-parity` via `.ci/policy/.ci-parity-exempt` |
| `.ci/scripts/quality/check-commit-identity.sh` | `.ci/rediacc_ci/quality/commit_identity.py` (entry: `check_commit_identity.py`) | run from CI similarly |
| `.ci/scripts/quality/check-submodule-branches.sh` | `.ci/rediacc_ci/quality/submodule_branches.py` (entry: `check_submodule_branches.py`) | `.github/workflows/ci-quality.yml` job "Submodule Branches", step "Validate submodule branches" runs `check_submodule_branches.py` directly |
| `.ci/scripts/quality/check-label-inventory.sh` | `.ci/rediacc_ci/quality/label_inventory.py` (entry: `check_label_inventory.py`) | `manifest.ts` id `check:ci-label-inventory` -> `npm run check:ci-label-inventory` -> this file |

Each port was built to be **byte-for-byte behaviourally equivalent** to its bash twin (verified with `shadow-gate.ts --assert`), and in three of the four cases the swallow found by the grep sweep **was carried over faithfully into the live Python gate**, because "port it exactly, fix it later" was the explicit invariant (`INVARIANT 5`, stated in every port's docstring: the twin is not edited in the change that ports it).

Consequence for this plan: fixing only the bash twin is cosmetic. Every REGISTERED-GATE fix below must land in **both** the twin (to keep the differential comparison meaningful and per invariant-5-compatible sequencing) **and** the live Python module (to actually change gate behaviour), plus whatever test exists on each side.

I also found the check-swallowed-failures.sh / `check_swallowed_failures.py` gate itself — the automated scanner that is supposed to catch exactly this defect class — was **only first registered and run in CI on 2026-09-08**, and its `DEFAULT_SCAN_DIRS` is `(".ci/scripts/quality", ".ci/scripts/security", ".ci/scripts/lib")`. It does **not** scan `.ci/scripts/housekeeping` or `.ci/scripts/release` at all, and even inside `.ci/scripts/quality` its heuristic has real, demonstrated blind spots (documented in section 1).

---

## 1. Problem

`gh` calls of the shape `gh (api|pr|run|release|workflow) ... 2>/dev/null || echo <default>` (or `|| true`) turn a `gh` failure (rate limit, expired token, network blip) into a value indistinguishable from "nothing to report." Earlier this session four such call sites in `.ci/scripts/lib/common.sh` (`review_report_count`, `review_attempt_states`, `review_spent_attempt_count`, `review_spend_total`) were fixed by routing through the file's own `gh_retry` helper, because they fed a merge-blocking check (`review-status.yml`) and a swallow there once made a capped PR permanently unmergeable (PR #553, 2026-08-07).

A stop-hook judge required the same sweep repo-wide. Re-running and hand-verifying the grep (not trusting the background bullet list) found:

- The pattern the background text estimated at "~18" for `cleanup-versions.sh` is actually **21** once multi-line `gh ... \` continuations (which the single-line grep misses) are included.
- One of the four "registered" quality gates listed (`check-commit-identity.sh`) has **zero** real false-green risk on inspection — both its swallow sites are provably fail-closed by an adjacent anti-vacuity check.
- One instance the background list didn't even mention — `check-pr-description.sh` line 56-57, a `gh pr view ... \` continuation the naive single-line grep cannot see — **is** a real false-green risk, and it is reproduced in the live Python gate.
- The two `mark-production.sh` instances are not part of any manifest-registered CI gate, but are a **worse-than-housekeeping** correctness bug: a swallowed second `gh api` call can silently move the `production` tag to point at the wrong git object type. I flag and fix this too, outside the strict "registered gate" bucket, because leaving it unfixed on the grounds of "not technically a gate" would miss the actual worst finding in the sweep.

---

## 2. Full verified instance list

Legend: **H** = HOUSEKEEPING/BEST-EFFORT (leave as is), **G** = REGISTERED-GATE FALSE-GREEN RISK (fix), **S** = ALREADY SAFE, mis-flagged (leave as is, direction verified), **P** = PRODUCTION-CORRECTNESS risk outside the gate manifest (fix, treated like G).

### 2.1 `.ci/scripts/quality/check-pr-description.sh` (twin) / `.ci/rediacc_ci/quality/pr_description.py` (live gate)

| # | Bash twin | Python live gate | Default on failure | Class | Reasoning |
|---|---|---|---|---|---|
| 1 | `.ci/scripts/quality/check-pr-description.sh:38` `PR_DATA=$(gh pr view "$PR_NUMBER" --json commits,body,title 2>/dev/null \|\| echo "{}")` | `.ci/rediacc_ci/quality/pr_description.py:252-254` `if code != 0: pr_data = "{}"` | `"{}"` | **S** | Immediately checked: `if [[ "$PR_DATA" == "{}" ]]; then log_error "Could not fetch PR data"; exit 1; fi` (bash 40-41) / `if pr_data == "{}": log.error(...); return 1` (py 256-258). `--json commits,body,title` can never legitimately return the literal string `{}`, so the sentinel is unambiguous and always escalates. Confirmed fail-closed.|
| 2 | `.ci/scripts/quality/check-pr-description.sh:56-57` (multi-line — **missed by the single-line grep**): `LATEST_COMMIT_TIME=$(gh pr view "$PR_NUMBER" --json commits \`⏎`    --jq '.commits \| sort_by(.committedDate) \| last \| .committedDate' 2>/dev/null \|\| echo "")` | `.ci/rediacc_ci/quality/pr_description.py:275-291`, `if code != 0: latest_commit_time = ""` then `if not latest_commit_time: log.warn(...); return 0` | `""` | **G** | By the time this runs, `COMMIT_COUNT >= MIN_COMMITS(3)` is already confirmed (checked at bash:49 / py:271), so `.commits\|sort_by(...)\|last\|.committedDate` over a non-empty, already-proven->=3-element array **cannot legitimately be empty**. An empty result here can only mean the `gh pr view` call itself failed. Both sides currently treat that identically to "PR too fresh to care about" and **exit 0 / return 0** ("skipping check") — this IS the false-green: an API blip makes the freshness gate silently pass instead of refusing to certify. Confirmed live via a differential test edit (`check_swallowed_failures.py`'s own heuristic misses this too — see §2.5). |
| 3 | `.ci/scripts/quality/check-pr-description.sh:86` `gh api graphql ... 2>/dev/null \| jq -r ...` (no `\|\|`, unguarded) | `pr_description.py` graphql block | n/a — not this class | **S** | Deliberately unguarded: a failing `gh api graphql` here kills the whole script under `set -euo pipefail` (bash) / returns 1 (py `if code != 0: return 1`). This is the *opposite* failure mode of a swallow — it is loud, not silent. Pinned by the port's own test (`test_a_failing_graphql_read_kills_both_sides_silently`). Not a finding. |

### 2.2 `.ci/scripts/quality/check-commit-identity.sh` (twin) / `.ci/rediacc_ci/quality/commit_identity.py` (live gate)

| # | Location | Default on failure | Class | Reasoning |
|---|---|---|---|---|
| 4 | bash:79 `me="$(gh api user --jq '{login,id}' 2>/dev/null)" \|\| { echo "✗ cannot read..."; exit 1; }` / py `refresh_identity`: `if code != 0: print(...); return 1` | n/a (no default; exits) | **S** | Already fails closed with `exit 1` / `return 1`. Not a swallow at all — the grep matched the trailing `)" \|\|` shape but the RHS is a hard failure block, not a default value. |
| 5 | bash:100 `emails="$(gh api user/emails --jq '.[].email' 2>/dev/null \| valid_emails \|\| true)"` / py: `_code, raw = gh_plain(...); emails = valid_emails(raw)` (no explicit `\|\| true` in py, same net effect) | empty `emails` | **S** | Feeds a two-stage fallback (retry via `commits?per_page=100` paginate) then an explicit **ANTI-VACUITY** check: `if [[ -z "${emails//[[:space:]]/}" ]]; then echo "✗ derived NO valid email addresses..."; exit 1; fi` (bash 111-116) / `if not emails: print(...); return 1` (py). Any combination of primary-fetch failure + secondary-fetch failure still lands on this hard refusal. This function is also only reachable via `--refresh` (an operator/maintenance action), never on the automatic per-PR verdict path. Confirmed fail-closed by design, and explicitly documented as such in the code ("ANTI-VACUITY").|
| 6 | bash `judge_pr()` (the actual per-PR verdict path), lines ~145-149: `payload="$(gh_retry "commit list for ${label}#${pr}" -- api ... )" \|\| probe_failed` | n/a | **S** | This is the ACTUAL merge-blocking path (not `--refresh`). Already routed through `gh_retry` + `probe_failed` (hard exit 1, "Failing closed rather than reporting clean"). This is the target idiom the other three gates need to match — it's already correct here. |

**Verdict for check-commit-identity.sh: no fix needed.** Both grep hits are in the maintenance-only `--refresh` path and both are already fail-closed by an anti-vacuity check; the live per-PR verdict path was already fixed to this same standard before this sweep started.

### 2.3 `.ci/scripts/quality/check-submodule-branches.sh` (twin) / `.ci/rediacc_ci/quality/submodule_branches.py` (live gate)

| # | Location | Default on failure | Class | Reasoning |
|---|---|---|---|---|
| 7 | bash:216 `get_pr_for_branch()`: `gh pr list ... --jq '.[0] // empty \| ...' 2>/dev/null \|\| echo ""` / py `.ci/rediacc_ci/quality/submodule_branches.py:408-438` `get_pr_for_branch()`, `if proc.returncode != 0: return ""` | `""` | **S** | Verified by tracing the caller (bash ~487-497 / py ~744-757): `pr_info=""` -> the code asks `branch_has_merged_pr()` next, which is **already** routed through `gh_retry`/`gh_probe` and fails closed to "NOT merged" on any error (bash 224-233, explicitly commented "A failed probe used to become 0... The direction is safe... but it is still a guess presented as a fact"). Worst case of a total `gh` outage: both calls fail -> the gate reports `✗ no open PR found for branch X` and increments `errors` -> the **whole gate fails (exit 1)**, not passes. The Python port's docstring for this function independently confirms this same conclusion in its own words: "the one place it does NOT fail closed [on its own]... the caller's next move is to ask whether a MERGED PR exists, which is the louder question anyway." Confirmed fail-closed at the system level; no fix needed. |
| 8 | bash:254 `get_console_pr_body()`: `gh pr view "$pr_number" --json body --jq '.body // empty' 2>/dev/null \|\| echo ""` / py `.ci/rediacc_ci/quality/submodule_branches.py:470-484` `console_pr_body()`, `if proc.returncode != 0: return ""` | `""` | **G** | Caller (bash 452-453/502, py 702-703/744) guards the call on `PR_NUMBER` set and `gh` present, then only runs the "is the submodule PR linked in the console PR body" check **when the body is non-empty**: `if [[ -n "$console_pr_body" ]] && ! pr_is_linked ...`. A `gh pr view` failure produces the exact same `""` as "the console PR genuinely has an empty description," and in **both** cases the link-check is silently skipped — no warning, no error, `errors` unchanged. A transient failure to fetch the **console** PR's own body therefore silently disables the one check that would have caught an unlinked submodule PR, on a PR that otherwise has a normal (linked) description. This is the same defect class as the already-fixed `common.sh` review-budget bug: failure indistinguishable from "nothing to check." |

### 2.4 `.ci/scripts/quality/check-label-inventory.sh` (twin) / `.ci/rediacc_ci/quality/label_inventory.py` (live gate, registered as `check:ci-label-inventory`)

| # | Location | Default on failure | Class | Reasoning |
|---|---|---|---|---|
| 9 | bash:347 `LIVE_JSON="$(gh api 'repos/{owner}/{repo}/labels' --paginate 2>/dev/null \|\| echo "")"` (inside `elif [ "$LIVE_SOURCE" = "GitHub API" ]`) / py `.ci/rediacc_ci/quality/label_inventory.py:602-609` `elif live_source == "GitHub API": proc = subprocess.run(...); live_json = proc.stdout if proc.returncode == 0 else ""` | `""` | **G** | Downstream: `if [ -n "$LIVE_JSON" ] ...` / `if live_json and ...:` — an empty `LIVE_JSON` from a failed `gh api` call **silently skips the entire description/colour drift comparison** (direction "(c)") rather than failing. The gate still reports "names, descriptions and colours all agree" even though colours/descriptions were never actually compared. The in-code comment justifying this ("a second hard failure here would only turn fixture-driven runs red") does **not hold under the current test suite**: I traced `LIVE_SOURCE`/`live_source` and confirmed it is set to `"GitHub API"` **only** when neither `LABEL_INVENTORY_LIVE_FILE`/`LIVE_FILE_ENV` is set — and **every** case in `.ci/scripts/test/gates/test-label-inventory.sh` and `.ci/rediacc_ci/tests/test_quality_label_inventory.py` sets `LABEL_INVENTORY_LIVE_FILE` (or the JSON fixture directly), so this `elif` branch is **never exercised by any existing test** — hardening it cannot turn a fixture-driven test red because no fixture-driven test reaches it. This also means there is currently **zero test coverage**, positive or negative, of the real `gh`-backed drift fetch. The sibling names-only fetch two sections above (bash:173-177 / py:489-505) already does exactly the fix this needs — same file, same gate, already correct for one of its two live reads and not the other. |

### 2.5 A gap in the swallow-scanner itself, found while tracing #2

`check_swallowed_failures.py` / `check-swallowed-failures.sh` classify a captured probe as safe once *anything* matching `ESCALATE_RE` (which includes `log_warn`) appears in the branch guarding the empty case — **even if that same branch also does `exit 0` / `return 0` right after the warning**. That is exactly instance #2's shape: `log_warn "..."; exit 0`. The scanner sees `log_warn` and stops looking, so it never flags this site, and the live tree currently self-reports "0 findings" despite carrying this real defect. This is not something this plan proposes to fix (the swallow-scanner is out of this sweep's declared scope and is itself a registered, tested gate with its own change-control), but it explains why re-deriving the list by hand (rather than trusting `check-swallowed-failures.sh`'s own "OK" verdict) was necessary, and it should be called out to whoever owns that scanner next.

### 2.6 `.ci/scripts/release/mark-production.sh` (not a manifest-registered gate — a release/production-tagging script, run from `promote-stable.yml`)

| # | Line | Code | Default | Class | Reasoning |
|---|---|---|---|---|---|
| 10 | 88 (context) | `if ! sha="$(gh api "repos/$REPO/git/ref/tags/$VERSION" --jq '.object.sha' 2>&1)"; then log_error ...; exit 1; fi` | n/a | **S** | Already fail-closed; establishes the idiom the two lines below should match. |
| 11 | 102 | `obj_type="$(gh api "repos/$REPO/git/ref/tags/$VERSION" --jq '.object.type' 2>/dev/null \|\| echo "")"` | `""` | **P** | This re-queries the **same** ref just fetched successfully at line 88, only to read `.object.type` this time. If this second call fails (a rate-limit hit between the two calls, for example), `obj_type=""`, and `if [[ "$obj_type" == "tag" ]]` is false — the script proceeds as if the ref points directly at a commit. If the real tag is annotated (points at a tag object, not a commit), the script then moves the mutable `production` tag ref to point at a **tag object** instead of a commit, silently, and still prints `mark-production: moved the 'production' tag to $VERSION ($sha)` as if it succeeded. `git show production` would then show the annotation instead of the code, exactly the failure mode the file's own header describes as the reason the second marker exists. Not merge-blocking, but arguably the highest-severity finding in this sweep: it corrupts a human-facing "what is actually live" pointer, silently, in the release path. |
| 12 | 104 | `sha="$(gh api "repos/$REPO/git/tags/$sha" --jq '.object.sha' 2>/dev/null \|\| echo "$sha")"` | `"$sha"` (the un-dereferenced **tag-object** sha) | **P** | Only reached when `obj_type == "tag"`, i.e. exactly the case that needs dereferencing. If *this* call fails, `sha` is left as the tag-object sha (not the commit sha) and the script proceeds to move `production` to point at it — same corruption as #11, reached via a different failure point. |

### 2.7 `.ci/scripts/release/resolve-ci-run.sh` (not a manifest-registered gate — feeds `cd-v2.yml`'s deployment/tag pipeline)

| # | Line | Code | Default | Class | Reasoning |
|---|---|---|---|---|---|
| 13 | 61 | `run_json="$(gh api "repos/.../actions/runs/${CI_RUN_ID}" 2>/dev/null \|\| echo '{}')"` | `{}` | **S** | All four fields subsequently `jq -r`'d out of `run_json` (`head_branch`, `conclusion`, `status`, `name`) come back as empty strings from `{}`. The validation that follows checks `run_branch != "main"` and `run_workflow != "Console CI"` — both trip on empty strings, setting `failed=true` and hitting `exit 1` ("ci_run_id validation failed — refusing to dispatch"). Confirmed fail-closed: a `gh` failure here makes dispatch validation refuse, not pass. |
| 14 | 92 | `CI_SHA=$(gh api "repos/.../actions/runs/${CI_RUN_ID}" --jq '.head_sha' 2>/dev/null \|\| echo "${GITHUB_SHA:-}")` | `"$GITHUB_SHA"` | **P** (documented, but silent) | The script's own header lists `GITHUB_SHA — fallback head sha when the run lookup fails` as a *documented, intentional* fallback, not an oversight — so this is not the same "nobody thought about it" defect as the rest of the sweep. However, the fallback fires with **zero log line**: nothing distinguishes "resolved via the API" from "guessed from `$GITHUB_SHA`" in the workflow log, and `$GITHUB_SHA` is not provably the same commit as the resolved `CI_RUN_ID` (it's the SHA of *this* workflow's own trigger, which can differ from the CI run being published from, especially on the manual-dispatch path). No other script cross-checks `CI_SHA` afterwards (`assert-artifact-version.sh` checks *version*, not *sha*). Recommend a one-line `log_warn`/`::warning::` when this fallback fires (observability only) rather than a hard fail, since forcing CD to abort on this specific fallback is a larger behavioural change than this sweep should make unilaterally. Not required for this plan's scope; noted for a follow-up. |

### 2.8 `.ci/scripts/ci/cancel-older-runs.sh`

| # | Line | Code | Class | Reasoning |
|---|---|---|---|---|
| 15 | 98 | `RUNS_JSON=$(gh api "...runs?status=in_progress..." 2>/dev/null) \|\| { log_warn "Failed to list workflow runs - retrying..."; sleep "$POLL_INTERVAL"; continue; }` | **S** | Not a default-value swallow at all — the `\|\|` branch is a retry-loop `continue`, and the loop has its own `TIMEOUT`/`ELAPSED` exit. A `gh` failure here delays cancellation and logs a warning every attempt; it never fabricates a "0 older runs" answer. Correctly excluded from the defect class. |

### 2.9 HOUSEKEEPING/BEST-EFFORT — `.ci/scripts/housekeeping/cleanup-versions.sh` (runs from `housekeeping.yml`, a nightly job, not merge-blocking, not a manifest gate)

All 21 verified `gh`-swallow sites below sit inside per-item loops over hundreds of tags/releases/packages/deployments/branches/runs/artifacts/caches. In every case, "this one lookup failed" degrades to "skip/keep this one item, keep going" — never to "report the whole nightly sweep succeeded when it silently did nothing" (the two calls that *could* have that shape, lines 547 and 967, are separately verified ALREADY SAFE below). A wrong skip here is corrected on the next nightly run; it does not corrupt a merge decision, a production pointer, or a deployment. Leave as is.

| Line(s) | What it guards | Default | Why leaving it is fine |
|---|---|---|---|
| 277 | best-effort tag-ref cleanup *after* the release delete already succeeded | `true` (ignore) | Explicitly commented "Best-effort tag cleanup (may already be gone)" — the release, the thing that matters, is already confirmed deleted by this point. |
| 307, 321, 333, 340, 342 | Phase 2 (git tags): list tags / resolve ref / tag date / deref sha / commit date, per repo | `""` / `"$obj_sha"` | A failed read for one repo/tag just means that tag isn't considered for deletion this run (fails the retention-age comparison harmlessly) — under-deletes, never over-deletes. |
| 422 | Phase 3 (GHCR packages): one page of one package's versions | `""` | One missing page -> fewer versions considered this run -> under-deletes for that package; retried next night. |
| 557 | Phase 4 (deployments): fetch all deployments for a repo | `"[]"` | Empty list -> 0 deployments processed for that repo this run -> under-deletes; the *decision* input (`open_prs`, line 547) that could cause a wrong *deletion* is separately hardened (see below). |
| 775, 800, 891, 1078, 1272 | Phase 4/9 (environments, PR-state lookups used to decide "keep vs eligible-for-cleanup") | `"[]"` / `"UNKNOWN"` | `"UNKNOWN"` state is never treated as "safe to delete" anywhere it's checked (only `"MERGED"`/`"CLOSED"` triggers deletion eligibility) — fails toward "keep," the safe direction. |
| 1311 | Phase 6-ish (git tags via API, piped through `grep` before the `\|\| true`) | `true` | Feeds a semver-tag census used for retention math; an empty read under-counts and the phase does less work, not more. |
| 1579, 1604, 1615 | Phase 9 (stale branches): branch list / open-PR count / last-commit date, per repo | `""` / `"0"` / `""` | Same skip-one-branch shape; `"0"` open-PRs on a failed read *could* in principle be wrong-direction (falsely says "no open PR blocks deleting this branch"), but it is paired with the last-commit-date check immediately after, which also fails safe to `""` -> unparseable -> treated as "can't prove staleness" downstream. Net effect on a read failure is under-deletion, not over-deletion, given the surrounding age-gate logic in this loop. |
| 1678, 1720, 1839, 1919 | Phase 10-12 (workflow runs / artifacts / actions cache): list active workflows, list runs per workflow, list artifacts, list caches | `"[]"` | Missing-line-continuation instances the single-line grep didn't see. Same shape as the rest of this file: an empty page means fewer candidates considered for deletion this run. |

Two calls in this same file were checked closely because their *shape* looks like the risky "whole-phase vacuous success" pattern, and both are verified **ALREADY SAFE**, not part of this bucket by accident:

- **Line 547** `if ! open_prs="$(gh pr list ... 2>/dev/null)"; then open_prs_ok=false; log_warn "Could not list open PRs; pr-* deployments fall back to keep-$keep_per_env"; fi` — explicit check, explicit warning, explicit conservative fallback (keep more, not less). **S**.
- **Line 967** `if ! open_prs="$(gh pr list ... 2>/dev/null)"; then log_warn "Could not list open PRs; pr-* deployments fall back to keep-$keep_per_env"; return 0; fi` — same pattern; a companion call at this same phase (Cloudflare Workers cleanup) explicitly **skips the entire phase** (`return 0`) rather than deleting on incomplete data, with a comment saying exactly that. **S**.

Also confirmed **not part of this defect class at all** (already an explicit `if/then/else` with a `log_warn`, not a `\|\|`-default swallow): lines 373, 616, 1759, 1875, 1970 (the four "delete-with-retry" call sites — `if retry_with_backoff 3 2 gh api -X DELETE ...; then ... else log_warn "Failed to delete ..."; fi`).

### 2.10 HOUSEKEEPING/BEST-EFFORT — `.ci/scripts/housekeeping/cleanup-pr-environments.sh` (runs from `cleanup-preview.yml`)

| Line | Code | Default | Class | Reasoning |
|---|---|---|---|---|
| 61 | `state="$(gh pr view "$num" ... 2>/dev/null \|\| echo UNKNOWN)"` | `UNKNOWN` | H | Traced the consumer: `if [[ "$state" == "OPEN" ]]` — `UNKNOWN` never matches `OPEN`, so it falls through to the deployment-count check rather than being treated as "definitely closed, safe to delete." Combined with line 68's failure mode (below), the worst case is "skip this environment," never "delete it wrongly." |
| 68 | `n_dep="$(gh api ".../deployments?environment=$env..." --jq 'length' 2>/dev/null \|\| echo unknown)"` | `unknown` | H | Consumer: `if [[ "$n_dep" != "0" ]]; then log_warn "SKIP ... still holds $n_dep deployment record(s)"; skipped++; continue; fi` — the string `unknown` is not `"0"`, so a failed read causes a **skip**, not a deletion. Fail-conservative by construction. |
| 48-49 (no `\|\|` at all — found while re-deriving the list, not in the original grep hit set) | `envs="$(gh api ".../environments" --paginate --jq '...' 2>/dev/null \| grep ... \| sort ...)"`; `if [[ -z "$envs" ]]; then log_info "No pr-N environments found"; exit 0; fi` | (empty pipeline output) | H, flagged as the weakest instance in this bucket | A total `gh api` failure here is indistinguishable from "genuinely zero pr-N environments exist right now" — the *whole* cleanup phase reports success and does nothing, with no warning that it couldn't read anything. Worst outcome is a skipped nightly run (self-heals next run), not a wrong deletion or a corrupted merge/production decision, so it stays HOUSEKEEPING — but unlike the other lines in this file it is not already reasoned-through in a comment. Non-blocking follow-up suggestion (not part of this plan's required fixes): add an explicit `gh api ... ; rc=$?` check before the pipe so a real failure logs `log_warn "could not read environments list ($rc); skipping this run"` instead of `log_info "No pr-N environments found"`. |

### 2.11 HOUSEKEEPING/BEST-EFFORT — `.ci/scripts/housekeeping/retry-failed-runs.sh` (runs from `housekeeping.yml`)

| Line | Code | Default | Class | Reasoning |
|---|---|---|---|---|
| 91 | `LIVE_HEADS="$(gh api ".../branches?per_page=100" --paginate ... 2>/dev/null \|\| true)"` | empty | **S** | Explicitly commented "Fail CLOSED: if this cannot be read we cannot tell superseded from current, and retrying a superseded run is the expensive mistake," and immediately checked: `if [[ -z "$LIVE_HEADS" ]]; then log_warn "could not list branch tips; skipping rather than retrying on incomplete data"; exit 0; fi`. This is a positive precedent already living in this same file — good evidence the desired idiom (warn + skip-the-whole-run rather than guess) is already known and used here. |
| 98 | `RUNS="$(gh api ".../actions/runs?status=failure..." --jq '[...]' 2>/dev/null \|\| echo '[]')"` | `[]` | H | If this fails, the loop over `$RUNS` (line ~153) simply finds zero failed runs to retry and the job reports "retried 0 of 0" — under-acts, doesn't over-act (nothing gets wrongly retried or wrongly skipped-forever; a still-failing run reappears in tomorrow's query). Same non-blocking follow-up suggestion as §2.10's `envs` case: a `log_warn` when this specific fetch's exit code is nonzero would make the difference between "nothing to retry" and "couldn't check" visible in the log, but it is not required by this plan's scope. |

---

## 3. Fix design for the REGISTERED-GATE (and production-correctness) instances

Style note: every fix below matches an idiom **already present in the same file** (bash: `gh_retry`/explicit `if ! x=$(...); then log_error; exit 1; fi`; Python: the sibling `gh_probe`/explicit `if proc.returncode != 0: log.error(...); return 1` already used elsewhere in the same module). No new helper is introduced anywhere.

### 3.1 `check-pr-description.sh` + `pr_description.py` — LATEST_COMMIT_TIME (instance #2)

**Bash twin**, `.ci/scripts/quality/check-pr-description.sh` (lines 55-62 today):

```diff
 # Get latest commit time
 LATEST_COMMIT_TIME=$(gh pr view "$PR_NUMBER" --json commits \
     --jq '.commits | sort_by(.committedDate) | last | .committedDate' 2>/dev/null || echo "")

 if [[ -z "$LATEST_COMMIT_TIME" ]]; then
-    log_warn "Could not get latest commit time - skipping check"
-    exit 0
+    log_error "Could not fetch the latest commit time for PR #$PR_NUMBER (gh call failed or returned nothing); cannot verify description freshness"
+    exit 1
 fi
```

The swallow (`|| echo ""`) is deliberately **kept** — it already matches this file's own idiom two sections above for `PR_DATA` (fetch into a sentinel, then check the sentinel explicitly), and `""` cannot be produced legitimately here (§2.1 reasoning: `COMMIT_COUNT >= 3` is already proven). Only the consequence of hitting the sentinel changes, from "warn and pass" to "error and fail."

**Live gate**, `.ci/rediacc_ci/quality/pr_description.py` (lines 287-291 today):

```diff
     if code != 0:
         latest_commit_time = ""
     if not latest_commit_time:
-        log.warn("Could not get latest commit time - skipping check")
-        return 0
+        log.error(
+            "Could not fetch the latest commit time for PR #%s (gh call failed or returned "
+            "nothing); cannot verify description freshness" % pr_number
+        )
+        return 1

     owner = repository.split("/", 1)[0]
```

### 3.2 `check-submodule-branches.sh` + `submodule_branches.py` — console_pr_body (instance #8)

**Bash twin**, `.ci/scripts/quality/check-submodule-branches.sh`. Route through the file's existing `gh_retry` (already imported via `source common.sh`, already used two functions above for `branch_has_merged_pr`):

```diff
 # Get console PR description
 get_console_pr_body() {
     local pr_number="${PR_NUMBER:-}"

     if [[ -z "$pr_number" ]]; then
         return 0
     fi

     if ! command -v gh &>/dev/null; then
         return 0
     fi

-    gh pr view "$pr_number" --json body --jq '.body // empty' 2>/dev/null || echo ""
+    gh_retry "console PR body for #${pr_number}" -- pr view "$pr_number" --json body --jq '.body // empty'
 }
```

Caller (lines 452-453 and 500-508 today) must now distinguish "could not fetch" from "fetched, empty":

```diff
     # Get console PR body for linking check (only in CI with PR context)
+    local console_pr_body_ok=true
     if [[ -n "${PR_NUMBER:-}" ]] && command -v gh &>/dev/null; then
-        console_pr_body="$(get_console_pr_body)"
+        if ! console_pr_body="$(get_console_pr_body)"; then
+            console_pr_body_ok=false
+            log_warn "could not fetch console PR #${PR_NUMBER} description after retries; cannot verify submodule PR links there this run"
+        fi
     fi
```

```diff
                     else
                         submodule_pr_number="${pr_info%%|*}"
                         submodule_pr_url="${pr_info##*|}"

-                        if [[ -n "$console_pr_body" ]] && ! pr_is_linked "$submodule_pr_url" "$console_pr_body"; then
+                        if [[ "$console_pr_body_ok" == "false" ]]; then
+                            log_error "✗ $sm_path: could not fetch console PR description; cannot certify $submodule_pr_url is linked there"
+                            errors=$((errors + 1))
+                        elif [[ -n "$console_pr_body" ]] && ! pr_is_linked "$submodule_pr_url" "$console_pr_body"; then
                             log_error "✗ $sm_path: PR $submodule_pr_url not linked in console PR description"
                             log_error "  AI FIX: Edit console PR description to include: $submodule_pr_url"
                             errors=$((errors + 1))
                         else
                             log_info "✓ $sm_path: PR $submodule_pr_url is linked"
                         fi
```

**Live gate**, `.ci/rediacc_ci/quality/submodule_branches.py`. Mirror `branch_has_merged_pr`'s existing `gh_probe` idiom exactly:

```diff
-def console_pr_body(env: dict[str, str] | None = None) -> str:
-    """The console PR description, or "" when there is no PR context."""
+def console_pr_body(env: dict[str, str] | None = None) -> tuple[bool, str]:
+    """(ok, body). ok=False means the fetch failed, not that the body is empty."""
     environ = os.environ if env is None else env
     pr_number = environ.get("PR_NUMBER", "")
     if not pr_number:
-        return ""
+        return True, ""
     if not have_gh():
-        return ""
-    proc = _run(["gh", "pr", "view", pr_number, "--json", "body"])
-    if proc.returncode != 0:
-        return ""
+        return True, ""
+    ok, out = gh_probe(False, "console PR body for #%s" % pr_number, ["pr", "view", pr_number, "--json", "body"])
+    if not ok:
+        return False, ""
     try:
-        return str(json.loads(proc.stdout or "{}").get("body") or "")
+        return True, str(json.loads(out or "{}").get("body") or "")
     except ValueError:
-        return ""
+        return False, ""
```

Caller in `main()`:

```diff
     pr_number = os.environ.get("PR_NUMBER", "")
+    pr_body_ok = True
     if pr_number and have_gh():
-        pr_body = console_pr_body()
+        pr_body_ok, pr_body = console_pr_body()
+        if not pr_body_ok:
+            log.warn(
+                "could not fetch console PR #%s description after retries; cannot verify "
+                "submodule PR links there this run" % pr_number
+            )
```

```diff
-        if pr_body and not pr_is_linked(sub_pr_url, pr_body):
+        if not pr_body_ok:
+            log.error(
+                "✗ %s: could not fetch console PR description; cannot certify %s is linked there"
+                % (sm_path, sub_pr_url)
+            )
+            errors += 1
+        elif pr_body and not pr_is_linked(sub_pr_url, pr_body):
             log.error("✗ %s: PR %s not linked in console PR description" % (sm_path, sub_pr_url))
             log.error("  AI FIX: Edit console PR description to include: %s" % sub_pr_url)
             errors += 1
         else:
             log.info("✓ %s: PR %s is linked" % (sm_path, sub_pr_url))
```

### 3.3 `check-label-inventory.sh` + `label_inventory.py` — LIVE_JSON drift fetch (instance #9)

**Bash twin**, `.ci/scripts/quality/check-label-inventory.sh` (lines 343-348 today). Match the sibling names-only fetch's own idiom (bash 173-177) exactly:

```diff
 LIVE_JSON=""
 if [ -n "${LABEL_INVENTORY_LIVE_JSON_FILE:-}" ]; then
     LIVE_JSON="$(cat "$LABEL_INVENTORY_LIVE_JSON_FILE" 2>/dev/null || echo "")"
 elif [ "$LIVE_SOURCE" = "GitHub API" ]; then
-    LIVE_JSON="$(gh api 'repos/{owner}/{repo}/labels' --paginate 2>/dev/null || echo "")"
+    if ! LIVE_JSON="$(gh api 'repos/{owner}/{repo}/labels' --paginate 2>&1)"; then
+        log_error "could not read the live label list (with descriptions/colours) from GitHub: ${LIVE_JSON}"
+        log_error "This gate refuses to pass blind on the drift comparison. Authenticate (gh auth login / GH_TOKEN) and re-run."
+        exit 1
+    fi
 fi
```

**Live gate**, `.ci/rediacc_ci/quality/label_inventory.py` (lines 602-609 today). Match the sibling names-only fetch's own idiom (py 489-505) exactly:

```diff
     elif live_source == "GitHub API":
         proc = subprocess.run(
             ["gh", "api", "repos/{owner}/{repo}/labels", "--paginate"],
             capture_output=True,
             text=True,
             check=False,
         )
-        live_json = proc.stdout if proc.returncode == 0 else ""
+        if proc.returncode != 0:
+            log.error(
+                "could not read the live label list (with descriptions/colours) from GitHub: %s"
+                % (proc.stdout + proc.stderr).rstrip("\n")
+            )
+            log.error(
+                "This gate refuses to pass blind on the drift comparison. Authenticate "
+                "(gh auth login / GH_TOKEN) and re-run."
+            )
+            return 1
+        live_json = proc.stdout
```

The stale in-file comment above this block ("a second hard failure here would only turn fixture-driven runs red") should be replaced with a short note recording why that concern doesn't hold (traced: `live_source == "GitHub API"` only when no fixture env var is set; no existing test takes that path) — otherwise a future reader hits the same false worry.

### 3.4 `mark-production.sh` — production-tag object-type/deref (instances #11, #12)

```diff
 # An ANNOTATED tag points at a tag object, not a commit. Deref it, or
 # `production` would point at a tag object and `git show production` would give
 # the annotation rather than the code.
-obj_type="$(gh api "repos/$REPO/git/ref/tags/$VERSION" --jq '.object.type' 2>/dev/null || echo "")"
+if ! obj_type="$(gh api "repos/$REPO/git/ref/tags/$VERSION" --jq '.object.type' 2>&1)"; then
+    log_error "mark-production: could not resolve $VERSION's object type: $obj_type"
+    exit 1
+fi
 if [[ "$obj_type" == "tag" ]]; then
-    sha="$(gh api "repos/$REPO/git/tags/$sha" --jq '.object.sha' 2>/dev/null || echo "$sha")"
+    if ! sha="$(gh api "repos/$REPO/git/tags/$sha" --jq '.object.sha' 2>&1)"; then
+        log_error "mark-production: could not dereference the annotated tag object for $VERSION: $sha"
+        exit 1
+    fi
 fi
```

This matches the file's own established idiom exactly (line 88, three lines above the first hunk: `if ! sha="$(gh api ... 2>&1)"; then log_error ...; exit 1; fi`).

---

## 4. Test plan

### 4.1 `check-pr-description.sh` / `pr_description.py`

`.ci/rediacc_ci/tests/test_quality_pr_description.py` already has a differential `GH_STUB` harness (fake `gh` script on `PATH`, fixture files under `fxdata/`) and, critically, **already contains a test that currently pins the vulnerable behaviour**:

```python
(
    "an empty commit-time read skips rather than guessing",
    {"pr-view.json": pr_view(6), "latest-commit.txt": "", "graphql.json": graphql("2026-09-06T10:00:00Z")},
    0,
),
```

Fix: after landing §3.1, this expectation flips from `0` to `1`. Rename for accuracy and add a sibling case that omits `latest-commit.txt` entirely (so the stub's `exit 1` fires — a real `gh` failure, not just an empty-but-successful read):

```python
(
    "an empty commit-time read is a failure, not a skip",
    {"pr-view.json": pr_view(6), "latest-commit.txt": "", "graphql.json": graphql("2026-09-06T10:00:00Z")},
    1,   # was 0
),
(
    "an unfetchable commit-time read is a failure, not a skip",
    {"pr-view.json": pr_view(6), "graphql.json": graphql("2026-09-06T10:00:00Z")},  # no latest-commit.txt at all
    1,
),
```

Both flow through `test_differential`, which already asserts byte-identical stdout/stderr and exit code between the bash twin and the Python port — this is the existing harness's proof that the fix landed symmetrically on both sides, no new infrastructure needed.

### 4.2 `check-submodule-branches.sh` / `submodule_branches.py`

There is currently **no executable test at all** for `console_pr_body`'s `gh`-calling behaviour on either side — `test_quality_submodule_branches.py`'s own docstring says so explicitly ("The gh call sites cannot be exercised locally... covered end to end by [a one-time shadow-gate ledger]"). This sweep needs to add one, following the closest existing convention (`GH_STUB` from `test_quality_pr_description.py`):

- **Python**: add a small stub-`gh`-on-`PATH` test to `test_quality_submodule_branches.py` (or a new `test_gate_submodule_branches_gh.py` if the existing file's pure-function focus argues for separation) that:
  1. builds a temp dir with a `gh` script that exits 1 for `pr view <n> --json body` (matching the fake-gh convention already used elsewhere),
  2. calls `mod.console_pr_body(env={"PR_NUMBER": "1"})` directly with that `PATH`,
  3. asserts it returns `(False, "")`, not `(True, "")`.
- **Bash**: add an equivalent case sourcing `check-submodule-branches.sh` with the same failing `gh` stub on `PATH`, calling `get_console_pr_body` directly, and asserting a nonzero return code (there is no `test-submodule-branches.sh` under `.ci/scripts/test/gates/` today; this can be a small new script there, or — preferably, to avoid growing the "148 gate tests" battery for a function with no independent CI wiring — a `bats`-free inline test function added under the existing Python test file that shells out to `bash -c 'source check-submodule-branches.sh; get_console_pr_body'` the same way `test_low_effort_normalisation_matches_the_shell` already shells out to a bash one-liner in that same file).
- A third assertion (unit-level, no `gh` involved): with the fixed `main()` wiring, feed `pr_body_ok=False` synthetically (or drive it through the stub end to end) and assert `errors` is incremented and the gate's exit code is 1 — i.e., a failed console-PR-body fetch now shows up as a **gate failure**, not a silently-skipped check.

### 4.3 `check-label-inventory.sh` / `label_inventory.py`

Neither `test-label-inventory.sh` nor `test_quality_label_inventory.py` currently exercises the `LIVE_SOURCE == "GitHub API"` / `live_source == "GitHub API"` branch at all (every existing case injects `LABEL_INVENTORY_LIVE_FILE`). Add, on both sides:

- A case with **no** `LABEL_INVENTORY_LIVE_FILE` and **no** `LABEL_INVENTORY_LIVE_JSON_FILE` set, and a fake `gh` on `PATH` that succeeds for the names-only call (`--jq '.[].name'`) but fails for the paginated full-object call used by the drift section. Assert the gate now exits 1 with a message containing "refuses to pass blind on the drift comparison," rather than the previous "reconciled... all agree" success message.
- Keep the existing fixture-only drift tests (`LABEL_INVENTORY_LIVE_JSON_FILE` set) unchanged — they never touched the `gh api` path and are not the surface this fix hardens.

### 4.4 `mark-production.sh`

`.ci/scripts/test/gates/test-mark-production.sh` already exists (registered as `gate-test:mark-production` in `manifest.ts`). Read its current `gh` stub convention and add two cases:

1. `gh api .../git/ref/tags/$VERSION --jq '.object.type'` fails (nonzero exit) -> assert the script now exits nonzero with a message naming "could not resolve $VERSION's object type," rather than silently proceeding to move the `production` tag.
2. `.object.type` succeeds and returns `tag`, but the follow-up `gh api .../git/tags/$sha --jq '.object.sha'` fails -> assert the script exits nonzero naming "could not dereference the annotated tag object," rather than moving `production` to the un-dereferenced tag-object sha.

---

## 5. Execution recommendation

**Two writers, disjoint files, no `git checkout/restore/stash`, no repo-wide regenerate script in either prompt.**

**Writer A — the three registered-gate false-green fixes + their tests** (this is the load-bearing half of the sweep; every file here is either a live CI gate or its differential twin/test):

- `.ci/scripts/quality/check-pr-description.sh`
- `.ci/rediacc_ci/quality/pr_description.py`
- `.ci/rediacc_ci/tests/test_quality_pr_description.py`
- `.ci/scripts/quality/check-submodule-branches.sh`
- `.ci/rediacc_ci/quality/submodule_branches.py`
- `.ci/rediacc_ci/tests/test_quality_submodule_branches.py`
- `.ci/scripts/quality/check-label-inventory.sh`
- `.ci/rediacc_ci/quality/label_inventory.py`
- `.ci/rediacc_ci/tests/test_quality_label_inventory.py`

Sequencing note for Writer A: land each pair (twin + port + test) as its own commit/step rather than all three gates in one lump, since each is an independent differential proof — mixing them raises the odds a break in one masks a break in another when `shadow-gate.ts` or the pytest suite reports a single red.

**Writer B — the production-correctness bonus fix + its test** (small, fully independent from Writer A's files, no shared imports):

- `.ci/scripts/release/mark-production.sh`
- `.ci/scripts/test/gates/test-mark-production.sh`

**No writer needed for the housekeeping files** (`cleanup-versions.sh`, `cleanup-pr-environments.sh`, `retry-failed-runs.sh`) or for `check-commit-identity.sh` — this plan document *is* the record that they were considered and deliberately left as-is, satisfying the "so a future reader sees they were considered and deliberately not changed, not missed" requirement without spending a writer's turn on a no-op diff. `resolve-ci-run.sh`'s documented-but-silent `$GITHUB_SHA` fallback (§2.7 instance #14) is likewise left out of the writers' scope — it's a genuine, if minor, observability gap, but treating it as a hard-fail is a CD-behaviour change this plan should flag rather than make unilaterally.

Why not fold Writer B into Writer A: `mark-production.sh` shares no source file, no test harness convention (bash-only `gate-test:` battery vs. Writer A's pytest differential harness), and no manifest wiring with the three quality gates — a genuine second, fully disjoint stream of work, which is what the "max 2 writers, disjoint file sets" rule is for. Why not split Writer A further into 3: the three gates share one recurring risk (each fix must land symmetrically in a twin/port pair or the differential/shadow-gate proof breaks), and that risk is best managed by one person landing all three sequentially with the same mental model, not three independent writers who could each get the twin/port symmetry subtly wrong in a different way.

### Critical Files for Implementation

- /home/developer/console/.ci/scripts/quality/check-pr-description.sh
- /home/developer/console/.ci/rediacc_ci/quality/pr_description.py
- /home/developer/console/.ci/scripts/quality/check-submodule-branches.sh
- /home/developer/console/.ci/rediacc_ci/quality/submodule_branches.py
- /home/developer/console/.ci/scripts/quality/check-label-inventory.sh
- /home/developer/console/.ci/rediacc_ci/quality/label_inventory.py
- /home/developer/console/.ci/scripts/release/mark-production.sh
- /home/developer/console/.ci/rediacc_ci/tests/test_quality_pr_description.py
</content>
