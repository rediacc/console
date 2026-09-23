Status: done
First-Seen: 2026-09-17
Owner: d778be9d (adopted from 8f55d4f0 2026-09-22)
Date: 2026-09-06
Supersedes: `.ci/config/bws-token-expiry.json` and its reader entirely, and the
`docs/ci-overhaul/08-driver-contract.md:92` row that assigns that file to W0/W8.
Scope: design. Every measurement below was read-only. No value of any secret was
read, printed or written. The `bws` error strings were measured with deliberately bogus tokens, never with the live one.

# BWS rotation is triggered by the failure, not by a date

The operator's ruling, in four parts:

> "When it expires, it wouldn't return exit code 0, right? Then we must have/throw
> a message with a failure that should guide other AI session to rotate bws
> credentials with a script. Then user should provide. So, we cannot keep the
> expire that and we shouldn't keep that information. The system should detect and
> share the script example. Then the script should set it for all sub-modules as
> well automatically."

1. Detection is the failure itself. `bws` exits non-zero; that is the signal.
2. The hand-maintained expiry date goes. It is a second source of truth.
3. The failure message is the product. It hands the next session the procedure.
4. The rotation script propagates the new token everywhere in one run.

## What is true today (measured 2026-09-06, verify before editing)

| Claim | Instrument | Result |
|---|---|---|
| `bws` version | `bws --version` | `bws 2.1.0` |
| Live token works | `bws secret list` via a length-only reader | exit 0, 58 secrets |
| Token's only source | `grep -c` on `private/account/.env` | ambient unset; `.env` has 1 |
| Bad-but-well-formed token | bogus value, real binary | exit 1, `[400 Bad Request] {"error":"invalid_client"}` |
| Empty or garbage value | bogus value, real binary | exit 1, `Doesn't contain a decryption key` |
| Variable unset | `env -u BWS_ACCESS_TOKEN` | exit 1, `Missing access token` |
| Org secret store | `gh api orgs/rediacc/actions/secrets` | total_count 0 |
| CI consumers | `grep -rn 'access-token:' .github/` | 60 lines |
| Repo secrets holding it | `gh secret list -R <r>` | console, account, renet have it; elite and homebrew-tap do not |

ALL THREE FAILURES ARE EXIT 1, and so is a network fault. The design must not depend on separating them by exit code, and must not assume the string measured against a NONEXISTENT client id is what an EXPIRED one produces. We have never seen an expired token's message and will not burn the live one to see it.

## The design in one paragraph

Any non-zero exit from `bws` emits one notice, held in exactly one file, read by every entry point. The notice names the rotation script and tells an AI session what its part is and what its part is NOT. The operator runs the script in their own terminal; it takes the value from a TTY with echo off, proves it works against the live store BEFORE writing it anywhere, then writes it
to `private/account/.env` and to the GitHub repo secret of every repo that already holds one. Nothing predicts expiry, nothing records a date.

## Tasks

### Part A: the notice, one text and five emitters
- [x] A1. Create `.ci/config/bws-rotation-notice.txt` with the Part F text. One file so five emitters cannot drift. Control: a gate asserting it is non-empty and names `scripts/dev/bws-rotate.sh`; negative, a fixture with the path misspelled must FAIL.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] A2. Emit from `.ci/lib/bws-env.sh`, replacing the two lines at :65-66 that name the expiry file. Classify stderr: `Missing access token` is wiring, not rotation, and prints NO notice; the other measured strings and ANY other non-zero print it. Default is on. Control: four cases in `test-bws-env.sh` using the existing `BWS_BIN` fake, plus two negatives (success prints nothing, missing-token prints nothing).
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] A3. Emit from `scripts/ops/bws-map-refresh.py` (this box said `scripts/dev/` and a line number; that path has never existed, see the implementation record below). ONE shared classifier, not two: a fixture list of the four measured stderr strings, fed to both implementations, diffed. Control: change one branch in one implementation, the gate must red.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] A4. Emit from `.github/actions/bws-secrets/action.yml` after :208-211 with `if: failure()`, through `::error::`. NOT OPTIONAL: it is the mitigation for what Part C gives up, because CD is where an unpredicted death costs most. Control: a dispatch run with a bogus token input; negative, the real token produces no annotation.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] A5. Add `rule_bws_auth_failure` to `.claude/hooks/trapguard/dispatch.py` RULES (:513-519). This is the ring that catches a session typing `bws` directly, bypassing A2 and A3. Control: one case per string, plus three negatives.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] A6. Point `private/account/scripts/rotation/lib/credentials.ts:151-168` at the notice as a POINTER, not a copy: the submodule can be checked out standalone and a relative read would resolve to nothing. A dangling pointer is honest; a silent empty string is not.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] A7. One heading in `docs/agent-reference/TRAPS.md`. Its floor is 75 and it sits at 75, so adding is safe and deleting is not.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

### Part B: the rotation script
- [x] B1. `scripts/dev/bws-rotate.sh`, input path only. TTY prompt with echo off; refuse non-TTY stdin with exit 2. NEVER argv. The non-TTY refusal is the mechanism that keeps the value out of an AI session: a Bash tool call has no TTY, so an agent physically cannot feed it.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] B2. Validation gate, nothing written until four pass: shape, live probe returning >= 40 in-project secrets, a client-id fingerprint that DIFFERS from the installed one, and never printing any of it. THIS IS THE ANTI-invalid_signature CLAUSE INVERTED: the bug this repo shipped was an unchecked HTTP response becoming a credential; here the unchecked thing would be an unverified paste becoming the credential for five repos at once. A short listing is the exact analogue of the silent 404.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] B3. Propagation, refresh-only, targets DERIVED from `.gitmodules` at run time so a fifth submodule needs no edit. A repo without the secret is REPORTED by name, never silently created. Value reaches `gh` on stdin.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] B4. All-or-nothing, then a post-write verdict that states its own limit: a GitHub secret cannot be read back, so `updated_at` proves a write happened, not that the right value landed.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] B5. Register `gate-test:bws-rotate` in the manifest. A test nobody runs is not a control.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

### Part C: deleting the expiry file
- [x] C1. `git rm .ci/config/bws-token-expiry.json`. No CI gate reads it. Control: the grep returns zero after, and returns two hits today, so the check is not vacuous.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] C2. Delete `warn_if_token_expiring()` and its call site. MOVE, do not delete, `_live_client_fingerprint()`: B2 needs that computation, and it is the one piece of that file binding a claim to the live token rather than to a hand-written date.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] C3. Fix two stale citations. `docs/ci-overhaul/08-driver-contract.md:92` is a LIVE coordination contract and is edited. `09-env-residue.md` is a dated measurement record and is APPENDED to, not rewritten: editing a historical measurement to match a later decision is how a corpus stops being evidence.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] C4. State the loss in the commit message. This box exists because honest accounting is the thing most likely to be skipped.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

WHAT IS LOST, HONESTLY. The file bought up to five days' notice before the sole CI/CD credential died. But it was delivered by exactly one reader that a human runs by hand occasionally. It never warned CI, never warned `bws_env_load`, never warned a deploy, and no gate read it. So what goes is a rare, best-effort, hand-maintained notice that could not stop anything.

WHAT REPLACES IT: nothing in this repo, deliberately. Expiry is a property of the machine account, visible only in the web vault. Any in-repo replacement is the same second source of truth under a new name.

WHAT THE TRADE ACTUALLY IS: a scheduled outage that arrives silently becomes an unscheduled one that arrives with its own diagnosis and a one-command fix. The part that gets worse is CD. A4 is the mitigation, which is why A4 is not optional.

### Part D: submodule propagation
Measured: `private/account` and `private/renet` hold the secret (set 2026-09-02)
but NOTHING in those repos reads it today; `private/elite` and `private/homebrew-tap` hold none, and homebrew-tap has no `.github/` at all. `private/account/.env` is the local root every console-side path reads.
- [x] D1. Refresh-only propagation with a named report for the rest. Automatic adoption would push a live credential into two repos with no consumer, which is the opposite of what a rotation is for. Control: five faked repos, exactly three written and two named; then fake elite into holding one and it must be written, proving the rule is derived from live state and not a hardcoded list.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] D2. The two dormant secrets are a DECISION for the operator, not a change to make: keep them current, or delete them as least-privilege. Recorded because a script that silently keeps two unused credentials alive is a fact someone should have chosen.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by 28d8f96e4 (2026-09-23) docs(agent): archive 3 done plans, verified box-complete before moving -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

### Part E: how a session that has never seen this finds the procedure
Four rings, each independently sufficient: the failing command prints it (A2/A3); a raw `bws` typed by the session is caught by trapguard and injected as context (A5, and this is the ring that literally answers the question); CI prints it as an annotation (A4); the corpus carries it (A7). Ring 2's stated limit: trapguard runs only in a Claude Code session in this repo.

### Part F: the notice text
Held in `.ci/config/bws-rotation-notice.txt`. It must say, in this order: what happened and that expired/revoked/deleted/network all look identical from here; that NOBODY can mint from here because `bws 2.1.0` has no such verb; that an AI session's whole part is to tell the operator and stop; explicitly DO NOT ask for the token in the conversation, DO NOT put it in a tracked file,
DO NOT offer to run the script; and what the script does, so the operator knows what they are agreeing to.

## Sequencing
A1 first. A2 and A3 together, sharing one classifier. A4 in parallel. B1 to B4 strictly in order, each a refusal the next depends on. C only after A2, or `bws-env.sh` names a file that no longer exists. D1 is inside B3.

## What this design does NOT cover
- Minting. Web-vault only; every part of this plan is downstream of a value the operator already holds.
- Advance warning of any kind. Deliberately.
- The read/write token split from `agent/archive/plans/PLAN-env-to-bitwarden.md:225-226`
(archived byte-identical 2026-09-09; see `agent/plans/PLAN-completion-strategy.md` section 2).
- Rotating anything else; downstream secrets belong to `private/account/scripts/rotation/`.
- Revoking the old token. A revoke reminder firing before propagation is verified is worse than none. OPEN QUESTION for the operator: should it print one after B4 passes?
- Proving the right value landed in a GitHub secret. Unreadable by design; the next CI run is the only end-to-end proof.
- The exact stderr of a genuinely EXPIRED token. `invalid_client` is an informed guess from a nonexistent client id. Nothing depends on it. OPEN BOX: record the real string at the next real expiry.
- A CI gate catching a stale repo secret. A gate cannot read a secret's value, so it could only check a date, which is the instrument this plan removes.

## Implementation record, 2026-09-23

Seventeen of eighteen boxes are implemented and verified against the real tree. The one that remains is C4, and it cannot be closed from here: it asks for a sentence in a COMMIT MESSAGE, and the working tree is deliberately uncommitted. The text it asks for is below, ready to paste.

THREE CORRECTIONS TO THIS PLAN'S OWN CITATIONS, each verified rather than assumed. `.ci/lib/bws-env.sh` was retired on 2026-09-21 and ported to `.ci/rediacc_ci/core/bws_env.py`, so A2 landed in the Python module and its `:65-66` lines are now the `LIST_FAILED` constant.
the map refresher was cited under a `scripts/dev/` path that has never existed; the real file is `scripts/ops/bws-map-refresh.py`, where `warn_if_token_expiring()` sat at line 89 and `_live_client_fingerprint()` at line 77, the reverse of what the brief recorded.
And A7's "floor is 75 and it sits at 75" was 92/92 on the day the entry was added; both copies of the ratchet moved to 93 in the same change, as the trap registry's own header demands.

ONE DEVIATION FROM A3, STATED BECAUSE IT CHANGES WHAT THE CONTROL PROVES. A3 asked for a fixture list fed to TWO implementations and diffed.
There is only one implementation now: `scripts/ops/bws-map-refresh.py` cannot import `rediacc_ci` (no `_cipath` shim under `scripts/ops/`, and a hand-written `sys.path` insert there would be a new finding against the shrink-only hop baseline), so it reaches `classify_failure` out of process through a `rotation-notice` verb that takes the captured stderr on STDIN.
The gate therefore asserts something stronger than a diff: that NO second copy of the decision exists in that file at all. The one place a copy is unavoidable is the trapguard ring, which no hook can import from, and `check:ci-bws-rotation-notice` compares its two marker tuples against the canonical ones by AST on every run.

WHAT THE LIVE CONTROLS PROVED, each run for real rather than reasoned about. A plant that deleted the non-TTY refusal from a COPY of the rotation script made a piped token exit 1 instead of 2, so the case asserting the refusal would fail. A plant that lowered the listing floor from 40 to 0 accepted a 12-secret listing, so the short-listing case would fail.
A plant that echoed the candidate into the `1/4 shape` line put `fixture-secret` on the stream, so the no-value case would fail. The expiry file restored on disk turned the gate red naming it, and removing it returned the gate to green.
One plant also found a real defect in the rotation script and it is fixed: `fingerprint_of` answered "" both for a token with no client id AND for a module it could not import, so a mis-rooted copy refused a good token with "the candidate has no client id" -- a missing tool wearing a verdict's clothes.
`require_fingerprint_tool` now probes with a value that certainly has a client id, before the prompt.

WHAT IS DELIBERATELY NOT DONE HERE, with the door named. A4's live control ("a dispatch run with a bogus token input; negative, the real token produces no annotation") needs a real GitHub Actions run against a real credential: door:operator-only.
The step itself is in place, narrowed to `steps.fetch.outcome == 'failure'` so a malformed secrets line cannot trigger a rotation notice, and its shape is asserted statically.
D2's DECISION is likewise the operator's: `private/account` and `private/renet` hold this secret with no consumer, refresh-only keeps them current, and `scripts/dev/bws-rotate.sh` now prints that open choice by name at the end of every successful rotation rather than leaving it in a plan nobody opens mid-rotation.
The plan's own open question about a revoke reminder is answered conservatively and out loud: the verdict says the old token is still live and that revoking it before the next green CI run would remove the fallback at the moment it might be needed. It does not prompt for a revoke.

C4's TEXT, for whoever commits this:

    The expiry file bought up to five days' notice before the sole local BWS
    credential died. It was delivered by exactly one reader that a human ran by
    hand occasionally: it never warned CI, never warned a deploy, and no gate
    read it. What replaces it is nothing, deliberately, because expiry is a
    property of the machine account and any in-repo replacement is the same
    second source of truth under a new name. The trade is that a scheduled
    outage arriving silently becomes an unscheduled one arriving with its own
    diagnosis and a one-command fix. The part that gets worse is CD, and the
    `if: failure()` annotation in .github/actions/bws-secrets/action.yml is the
    mitigation for exactly that, which is why that step is not optional.

PORTED TO PYTHON 2026-09-23 (Ruling 7, 2026-09-06: scripts/dev is a Python tree; found by check:ci-language-policy going red on the two bash files this box had just added).
`scripts/dev/bws-rotate.sh` and `.ci/scripts/test/gates/test-bws-rotate.sh` are retired; the subject is now `scripts/dev/bws-rotate.py`, ported function for function against the retired bash's last revision, with the retired shell test's exact fixture and every case reproduced at `.ci/rediacc_ci/tests/gates/test_gate_bws_rotate.py` (18/18 passing, one plant confirmed a removed TTY check reds the suite rather than passing vacuously).
All five emitters, the notice text, and every cross-file prose mention of the old path were swept to the new one.
The standalone `gate-test:bws-rotate` manifest/lock entry was removed rather than rewired, matching the retirement convention `agent/plans/PLAN-plyr-css-on-demand-loading.md:117` already documents: a Python port rides `check:ci-pytest`'s existing `.ci/rediacc_ci/tests/gates/**` collection and does not get its own entry.
