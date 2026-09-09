Status: partially implemented 2026-09-02 (D3, the ban, and the docs box; D2 and D4 remain)
Owner: 74de73ca

# Branch-aware workflows: 18 of 18 call sites already are

Designed 2026-09-02 by a Plan agent, docs-verified, and written up here because that agent
had no write tool. Every GitHub claim below was quoted from the page named, not recalled.

## The headline, before anything else

The operator's ask: *"workflows! We usually have to merge them each time. Can't we have
current branch aware workflows? So, we can test our changes in PR?"*

**The premise does not describe this repo.** Measured: all **18** job-level workflow calls in
`.github/workflows/` use the local `./` form; there are **zero** cross-repo workflow calls and
**zero** floating action refs (all 329 third-party `uses:` are 40-char SHA-pinned). GitHub
documents the local form as resolving to the caller's commit:

> "When you reference a reusable workflow in the same repository using `./` (without
> `{owner}/{repo}` and `@{ref}`), the called workflow is from the same commit as the caller
> workflow." — *Reuse workflows*

**So `ci.yml`'s entire closure already runs the PR's own YAML on every PR.** Console's
workflow graph is 100% branch-aware today.

## What actually forces merge-first — four different things, none of them the ref

1. **Triggers that read the default branch BY DESIGN.** `workflow_run` (4 workflows) and
   `pull_request_target` (1). They hold secrets while a PR's code is in play, so
   default-branch resolution is the security property, not a defect.
2. **One deliberate pin**: `claude-review-reusable.yml:172-177` checks the review *scripts*
   out of `console@main`. Its own comment records run `30317293249`, where a PR reviewed
   itself using its own review logic — the hole that pin closes.
3. **`ci.yml:193-199`** actively refuses `workflow_dispatch` on any ref but main, so the
   nightly rehearsal stays schedule-equivalent by construction.
4. **Two external callers** in `private/account` and `private/renet` pinned `@main`.

## The measurement that justifies acting at all

**434 commits touched `.github/workflows/` since 2025-10-11.** Fix-forward — a `fix`/`revert`
landing within 24h of the previous commit to the same file, the signature of "merged it,
watched it break, merged again" — is **140 of 538 file-touches across the eight main
workflows, 26%**.

| file | commits | fix-forward | rate |
|---|---|---|---|
| `claude-review-reusable.yml` | 18 | 11 | **61%** |
| `cd-v2.yml` | 98 | 41 | **42%** |
| `ci.yml` | 153 | 38 | 25% |
| `ci-quality.yml` | 155 | 33 | 21% |

**The distribution is the tell.** The two worst files are exactly the two whose testable path
is blocked; the two exercised on every PR sit at 25%/21%, which is ordinary defect residue
rather than a merge-to-test tax.

**And a local measurement would have missed all of it**: `git log -- .github/workflows` returns
**5** commits here, because `.git/shallow` caps the clone at 50. Anyone measuring this locally
concludes the problem does not exist.

**The capability is already there and has never been used.** 429 non-main `workflow_dispatch`
runs exist, and of 40 sampled, **zero** carried a workflow file that differed from main's.

## Design — no new machinery

- **D1 (zero changes, unblocks 7 of 18):** `gh workflow run <file> --ref <branch>` runs the
  branch's copy. The subtlety worth writing down: dispatch *acceptance* is decided from the
  DEFAULT branch's copy, while the version that *runs* comes from the ref. So adding a
  `workflow_dispatch:` trigger costs one unavoidable merge, once per workflow — never per
  change. This repo discovered both halves twice already (run `30588087212`, and
  `dispatch-watchdog.sh:122-138`) and never generalised it.
- **D2:** a `dry_run` input on `cd-v2.yml`/`promote-stable.yml`, threaded into the deploy
  callees, gating exactly the write calls. **Stated hazard:** a dry run that skips different
  steps than the real run asserts the dry run — so its control plants a defect in a
  non-write step and requires the dry path to still execute it.
- **D3 (highest value):** an external-caller registry plus a fourth check in
  `check-workflow-gates.sh`. That gate's CHECK 2 enforces caller/callee contracts in both
  directions but `:62` scopes it to `.github/workflows` only, so **it cannot see the only two
  callers that can suffer the breakage it exists to prevent**. The workaround is already in
  the tree: `BWS_ACCESS_TOKEN` is `required: false` and the shadow steps are repo-guarded
  precisely because those two would break on a required secret they do not pass.
- **D4 (needs a ruling):** a `scripts_ref` on the reviewer, gated to `workflow_dispatch`
  (which already requires write access) AND to `github.repository == 'rediacc/console'`, so
  the automatic paths a PR author can trigger keep the hard `main` pin.
- **D5:** leave `workflow_run`, `pull_request_target` and the rehearsal guard alone.

## Rejected

`uses: ...@${{ github.ref }}` — **invalid**: "You cannot use contexts or expressions in this
keyword". It fails as a startup error with zero jobs and no log, which is the shape the ask
implies and the one thing that definitively cannot work. A thin dispatcher — relocates the
pin rather than removing it, and the input surface is what actually broke the callers.
Vendoring the reviewer into both repos — contradicts its stated purpose of having exactly one
copy, and `.ci/breakpoint/`'s machinery shows what keeping copies honest costs. An ungated
`scripts_ref` — restores run `30317293249` exactly. Adopting `act` — cannot reproduce these
runners, and would validate the one layer already covered.

**Cheaper than any of it, for the external callers:** the `@ref` is a branch name, and any
branch name works. A throwaway PR in `rediacc/account` pinned at `@<console-branch>` exercises
the reusable end-to-end before console merges anything.

## The security boundary, said out loud

**The trust boundary here is already "write access to `rediacc/console`."** Anyone with write
access can open a PR editing `ci-quality.yml` and CI runs their version with the full secret
set. D1 and D2 add **no** new exposure — same boundary, different door. Fork PRs stay outside
it and fail closed (`ci.yml:243-247`). D4 is the only genuine widening, and only for a
dispatcher who could push that logic to main anyway.

Also: checkout v7 now refuses fork-PR code under `pull_request_target`/`workflow_run` unless
`allow-unsafe-pr-checkout` is passed (enforced 2026-07-20). That flag belongs in
`check-workflows.sh`'s banned-pattern list so it can never appear unreviewed.

## Controls

Six static gates, each with a planted defect and a stated blind spot: the external-caller
contract; registry completeness (grep `private/*/.github/` and require every hit registered);
all console workflow calls stay `./`; the tooling-pin invariant on every non-dispatch path;
`dry_run` completeness in BOTH directions (no write step unguarded, no read-only step
guarded); and the banned `allow-unsafe-pr-checkout`. Anti-vacuity is mandatory — an empty
registry or a zero-match scan must FAIL, a class this repo has been bitten by twice.

## The three decisions that are the operator's

1. **Does `scripts_ref` ship at all?** It makes the 61% file testable pre-merge, at the cost
   of letting a write-access dispatcher point the reviewer's own logic at an unmerged branch —
   in the one job that reads attacker-authored text with egress tools.
2. **Is a `dry_run` CD path trustworthy enough to be the thing you test?** A dry run is still
   not a deploy.
3. **For the external callers: scratch-branch pin as required procedure, or accept brief
   breakage?** Already ruled acceptable; D3 turns the breakage into a gate finding either way.

## Status

- [x] Document the `--ref` semantics with both doc citations and both run ids (zero code)
      -> docs/agent-reference/ci-gates.md, new "Dispatching a workflow on a branch" section.
      D1's claim is CONFIRMED, and `claude-review.yml:27-35` was wrong. No single GitHub page
      says it, which is why the tree disagreed with itself; it is the conjunction of the
      concepts page ("Each workflow run will use the version of the workflow that is present
      in the associated commit SHA or Git ref of the event") with the events table, which
      gives workflow_dispatch a GITHUB_REF of "Branch or tag that received dispatch". Both
      re-fetched 2026-09-02. The same rule explains workflow_run and pull_request_target:
      their GITHUB_REF *is* the default branch, so it is one rule, not three.
- [x] D3: external-caller registry + CHECK 4, proven red-then-green offline
      -> .github/external-callers.yml + check-workflow-gates.sh:423; 11 new both-way cases
      in test-workflow-contracts.sh (22/22 pass), 8 planted defects each caught and restored.
- [x] Ban `allow-unsafe-pr-checkout` in check-workflows.sh
      -> check-workflows.sh banned-pattern list; planted a checkout step carrying the flag,
      gate went red naming the line, removed it, green again.
- [ ] D2: `dry_run` through the CD callees, validated by dispatching it on a branch
      OPERATOR-GATED: its stated validation is a real dispatch on a pushed branch, which is
      outward-facing. The code could be written blind, but the plan's own control (a dry run
      that skips different steps than the real run asserts the dry run) is only provable by
      that dispatch, so writing it unvalidated would be the exact defect it guards against.
- [ ] D4: gated `scripts_ref` — ONLY after an operator ruling, landed alone
