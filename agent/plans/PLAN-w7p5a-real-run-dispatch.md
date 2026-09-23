# PLAN: W7P5-a real-run dispatch — execute the 32-path authorization safely

Status: executing
Owner: d778be9d
Updated: 2026-09-23

## The ask

The operator answered "Authorize the full 32" to an /ask round, overriding this session's own more conservative "read-only verifiers only" recommendation, for the 32 production-touching deploy/release paths registered in `.ci/policy/.w7p5a-real-run-blocklist` (cross-checked by `check:ci-w7p5a-real-run-blockers` against `.ci/shadow/w7p5a-status.json`'s 32 `"blocked"` / 16 `"ledger"` split).
This plan turns that authorization into a concrete, safety-first execution sequence — it does not itself run anything.

## What the repo already encodes (read before dispatching anything)

Every one of the 32 `"blocked"` rows in `.ci/shadow/w7p5a-status.json` carries, verbatim, in its own `note` field:

> "That clause needs a run against real production Cloudflare, GitHub, R2 or
> D1 and is an OPERATOR-AUTHORIZATION matter: a session must not attempt it."

This is machine-tracked, not this session's editorializing (confirmed: all 32/32 rows carry the exact sentence).
`.w7p5a-real-run-blocklist`'s own header says rewording that language is "a driver action against that allowlist, not an edit this file may make on its own." `PLAN-w7p5a-deploy-release-port.md` (compacted 2026-09-20, same owner prefix) closed with box 8: "Leave all 32 fully-`blocked` paths untouched... require explicit operator authorization before real runs are safe" — today's authorization is the event that plan anticipated, but it authorizes the *operator* to proceed, not an agent session to self-dispatch.
Blast-radius tiering below governs how much operator involvement each path needs, not whether any is needed — none of the 32 gets unattended agent execution against real production.

The shape a passing entry must end in (matching the 16 already done): either the `note` gains the literal substring `"real run each done directly"` with prose describing what ran and against what (the 9-path pattern), or the path moves into `.w7p5a-real-run-leg-blocklist` with its own BLOCKER naming the unreachable system (the 7-path pattern).
Either way the entry is removed from `.w7p5a-real-run-blocklist` in the same change, or `check:ci-w7p5a-real-run-blockers` reds on the drift.

## Categorized findings (blast radius, 32/32 accounted for)

| Tier | Category | Count | Paths |
|---|---|---|---|
| R | Read-only, zero credentials, zero mutation possible | 2 | `verify-edge-endpoints.sh`, `verify-stable-endpoints.sh` |
| Q | Read-only in effect, needs creds this sandbox lacks | 3 | `assert-artifact-version.sh`, `assert-edge-tag-exists.sh`, `reprobe-r2-sentinel.sh` |
| M-contained | Mutating, disposable/staging substitute exists | 9 | `cf-purge-urls.sh`, `purge-media-cache.sh`, `write-release-sentinel.sh`, `clone-d1.sh`, `simulate-promotion.sh`, `sync-media-from-r2.sh`, `upload-repos-to-r2.sh`, `upload-to-r2.sh`, `test-d1-migrations.sh` |
| M-live | Mutating, no safe non-prod target, irreversible/public-facing | 18 | `deploy-account.sh`, `deploy-edge.sh`, `deploy-proxy.sh`, `deploy-www.sh`, `promote-docker-to-stable-hotfix.sh`, `promote-r2-to-stable-hotfix.sh`, `promote-r2-to-stable.sh`, `set-account-worker-secrets.sh`, `set-preview-worker-secrets.sh`, `set-www-worker-secrets.sh`, `delete-r2-channel.sh`, `sync-media-to-r2.sh`, `advance-contract-floor.sh`, `update-homebrew-tap.sh`, `mark-production.sh`, `create-github-release.sh`, `cleanup-channel-docker-tags.sh`, `tag-submodules.sh` |

## Implementation (mechanism per tier)

1. **Tier R (2 paths).** No secrets, no mutation. A writer may draft the exact command and a template ledger note. Execution still needs one fresh, item-level operator "go" (a glance, not a review) — the "session must not attempt it" sentence in status.json belongs to the operator to retire, not to this session to route around by blast-radius reasoning.
2. **Tier Q (3 paths).** Two options, operator's choice: (a) operator runs the command personally in their own authenticated shell and hands the writer the transcript to fold into the ledger note;
or (b) operator mints a narrowly-scoped, time-boxed, read-only credential (`actions:read`, `s3:HeadObject` on one prefix, etc.) into an ephemeral sandbox, watches the single run, then revokes it immediately.
No standing credential is ever left in an agent-writable environment.
3. **Tier M-contained (9 paths).** Retarget the real run at a disposable analog instead of the production resource: a scratch R2 bucket/prefix the operator provisions and deletes afterward, a forked/cloned D1 instance instead of production D1, a clearly-scoped sentinel key.
This proves the Python port's behavior against a real instance of the same external API family without touching production.
Whether that satisfies the box's literal "real production" bar is the operator's call per path — the ledger note must say plainly that a substitute target was used, never word it as if the real endpoint was hit.
4. **Tier M-live (18 paths).** No agent-executed path, staged or otherwise.
The operator runs the command personally, at a time of their choosing (low-traffic window where relevant), with a rollback step identified before running, watching output live.
A writer's role is limited to drafting the exact command/flags for the operator to review or copy, and transcribing the result into the ledger note afterward.
`advance-contract-floor.sh` pushes directly to `origin/main`; `tag-submodules.sh` and `update-homebrew-tap.sh` push to shared/public remotes that may trigger downstream CD; the three `set-*-worker-secrets.sh` scripts risk a live secret leaking into any transcript/log — redact before the writer ever sees output from these.

## Sequencing

**A writer may do, unattended, right now, for all 32:** draft the exact real-run command line, required env/flags (redacted), and a ledger-note template matching the proven shape (containing the literal phrase the gate checks, or the leg-blocklist BLOCKER shape) — with the actual-output field left blank for the operator to fill in.
For the 9 M-contained paths, also draft the disposable-resource provisioning request as a checklist item for the operator (bucket/D1-fork name, expiry, why it's a safe stand-in). Re-running `check:ci-w7p5a-real-run-blockers` to confirm it stays green throughout is likewise safe and unattended.

**Needs per-path operator sign-off on the exact command before it runs — all 32, no exceptions**, because the "a session must not attempt it" sentence is uniform across all 32 rows regardless of tier.
What varies is weight: Tier R sign-off can be a one-line "go"; Tier Q sign-off includes review of credential scope and revocation; Tier M-contained sign-off includes confirming the substitute target is genuinely disposable and non-production; Tier M-live sign-off means the operator is the one at the keyboard, full stop.

**Why sequence it this way:** (a) the block is machine-tracked repo policy, not a one-off suggestion, and reworking it is explicitly a driver action; (b) this session holds no production credentials for any of the 32 regardless of what was authorized; (c) roughly half the M-live paths are irreversible or immediately public-facing (main-branch push, homebrew tap push, GitHub release, secret rotation) — a mistake there cannot be quietly rolled back; (d) a blanket answer to an /ask round, relayed through another agent's task context, is a weaker signal than the operator's hands on a specific destructive command, and this environment's own consent rules draw exactly that distinction.

## Verification

- `check:ci-w7p5a-real-run-blockers` stays green before, during (after each individual graduation), and after this work — the gate's own bidirectional cross-check is what prevents a "third state" from opening up mid-sequence.
- Each graduated entry's ledger note is spot-checked against `test_a_dry_run_ledger_never_closes_the_real_run_leg` and `test_the_note_does_not_claim_a_real_run` in `.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py` — a dry-run-only path must never pick up the real-run confirmation phrase by accident.
- For every Tier M-contained graduation, confirm the ledger note names the substitute resource explicitly rather than reading as a production run.
- No secret value ever appears in a plan file, ledger note, or writer-visible transcript for the three `set-*-worker-secrets.sh` paths — redact before recording.

## Boxes

- [ ] Draft exact real-run commands + redacted env template for all 32 paths (writer, unattended).
- [ ] Draft ledger-note templates (confirmed-phrase shape for candidates without an external system left after substitution; leg-blocklist BLOCKER shape otherwise) for all 32 (writer, unattended).
- [ ] Tier R (2): get operator per-item go, run, record ledger note.
- [ ] Tier Q (3): operator chooses personal-run vs scoped-credential path per item; execute; revoke any minted credential immediately; record ledger note.
- [ ] Tier M-contained (9): operator provisions each disposable substitute; writer drafts the retargeted command against it; operator approves; run; record ledger note naming the substitute explicitly.
- [ ] Tier M-live (18): operator personally executes each, at a time of their choosing, with a rollback step identified beforehand; writer transcribes redacted output into the ledger note afterward.
- [ ] Re-run `check:ci-w7p5a-real-run-blockers` after every graduation; confirm rc=0 and the blocked/ledgered counts move as expected.
- [ ] Full re-run of `.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py` after all graduations to confirm no dry-run note accidentally claims a real run.
