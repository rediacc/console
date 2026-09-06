Status: draft
Owner: 8f55d4f0
Date: 2026-09-06
Supersedes: `.ci/config/bws-token-expiry.json` and its reader entirely, and the
`docs/ci-overhaul/08-driver-contract.md:92` row that assigns that file to W0/W8.
Scope: design. Every measurement below was read-only. No value of any secret was
read, printed or written. The `bws` error strings were measured with deliberately
bogus tokens, never with the live one.

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

ALL THREE FAILURES ARE EXIT 1, and so is a network fault. The design must not
depend on separating them by exit code, and must not assume the string measured
against a NONEXISTENT client id is what an EXPIRED one produces. We have never
seen an expired token's message and will not burn the live one to see it.

## The design in one paragraph

Any non-zero exit from `bws` emits one notice, held in exactly one file, read by
every entry point. The notice names the rotation script and tells an AI session
what its part is and what its part is NOT. The operator runs the script in their
own terminal; it takes the value from a TTY with echo off, proves it works against
the live store BEFORE writing it anywhere, then writes it to
`private/account/.env` and to the GitHub repo secret of every repo that already
holds one. Nothing predicts expiry, nothing records a date.

## Tasks

### Part A: the notice, one text and five emitters
- [ ] A1. Create `.ci/config/bws-rotation-notice.txt` with the Part F text. One file so five emitters cannot drift. Control: a gate asserting it is non-empty and names `scripts/dev/bws-rotate.sh`; negative, a fixture with the path misspelled must FAIL.
- [ ] A2. Emit from `.ci/lib/bws-env.sh`, replacing the two lines at :65-66 that name the expiry file. Classify stderr: `Missing access token` is wiring, not rotation, and prints NO notice; the other measured strings and ANY other non-zero print it. Default is on. Control: four cases in `test-bws-env.sh` using the existing `BWS_BIN` fake, plus two negatives (success prints nothing, missing-token prints nothing).
- [ ] A3. Emit from `scripts/dev/bws-map-refresh.py:159`. ONE shared classifier, not two: a fixture list of the four measured stderr strings, fed to both implementations, diffed. Control: change one branch in one implementation, the gate must red.
- [ ] A4. Emit from `.github/actions/bws-secrets/action.yml` after :208-211 with `if: failure()`, through `::error::`. NOT OPTIONAL: it is the mitigation for what Part C gives up, because CD is where an unpredicted death costs most. Control: a dispatch run with a bogus token input; negative, the real token produces no annotation.
- [ ] A5. Add `rule_bws_auth_failure` to `.claude/hooks/trapguard/dispatch.py` RULES (:513-519). This is the ring that catches a session typing `bws` directly, bypassing A2 and A3. Control: one case per string, plus three negatives.
- [ ] A6. Point `private/account/scripts/rotation/lib/credentials.ts:151-168` at the notice as a POINTER, not a copy: the submodule can be checked out standalone and a relative read would resolve to nothing. A dangling pointer is honest; a silent empty string is not.
- [ ] A7. One heading in `docs/agent-reference/TRAPS.md`. Its floor is 75 and it sits at 75, so adding is safe and deleting is not.

### Part B: the rotation script
- [ ] B1. `scripts/dev/bws-rotate.sh`, input path only. TTY prompt with echo off; refuse non-TTY stdin with exit 2. NEVER argv. The non-TTY refusal is the mechanism that keeps the value out of an AI session: a Bash tool call has no TTY, so an agent physically cannot feed it.
- [ ] B2. Validation gate, nothing written until four pass: shape, live probe returning >= 40 in-project secrets, a client-id fingerprint that DIFFERS from the installed one, and never printing any of it. THIS IS THE ANTI-invalid_signature CLAUSE INVERTED: the bug this repo shipped was an unchecked HTTP response becoming a credential; here the unchecked thing would be an unverified paste becoming the credential for five repos at once. A short listing is the exact analogue of the silent 404.
- [ ] B3. Propagation, refresh-only, targets DERIVED from `.gitmodules` at run time so a fifth submodule needs no edit. A repo without the secret is REPORTED by name, never silently created. Value reaches `gh` on stdin.
- [ ] B4. All-or-nothing, then a post-write verdict that states its own limit: a GitHub secret cannot be read back, so `updated_at` proves a write happened, not that the right value landed.
- [ ] B5. Register `gate-test:bws-rotate` in the manifest. A test nobody runs is not a control.

### Part C: deleting the expiry file
- [ ] C1. `git rm .ci/config/bws-token-expiry.json`. No CI gate reads it. Control: the grep returns zero after, and returns two hits today, so the check is not vacuous.
- [ ] C2. Delete `warn_if_token_expiring()` and its call site. MOVE, do not delete, `_live_client_fingerprint()`: B2 needs that computation, and it is the one piece of that file binding a claim to the live token rather than to a hand-written date.
- [ ] C3. Fix two stale citations. `docs/ci-overhaul/08-driver-contract.md:92` is a LIVE coordination contract and is edited. `09-env-residue.md` is a dated measurement record and is APPENDED to, not rewritten: editing a historical measurement to match a later decision is how a corpus stops being evidence.
- [ ] C4. State the loss in the commit message. This box exists because honest accounting is the thing most likely to be skipped.

WHAT IS LOST, HONESTLY. The file bought up to five days' notice before the sole
CI/CD credential died. But it was delivered by exactly one reader that a human
runs by hand occasionally. It never warned CI, never warned `bws_env_load`, never
warned a deploy, and no gate read it. So what goes is a rare, best-effort,
hand-maintained notice that could not stop anything.

WHAT REPLACES IT: nothing in this repo, deliberately. Expiry is a property of the
machine account, visible only in the web vault. Any in-repo replacement is the
same second source of truth under a new name.

WHAT THE TRADE ACTUALLY IS: a scheduled outage that arrives silently becomes an
unscheduled one that arrives with its own diagnosis and a one-command fix. The
part that gets worse is CD. A4 is the mitigation, which is why A4 is not optional.

### Part D: submodule propagation
Measured: `private/account` and `private/renet` hold the secret (set 2026-09-02)
but NOTHING in those repos reads it today; `private/elite` and
`private/homebrew-tap` hold none, and homebrew-tap has no `.github/` at all.
`private/account/.env` is the local root every console-side path reads.
- [ ] D1. Refresh-only propagation with a named report for the rest. Automatic adoption would push a live credential into two repos with no consumer, which is the opposite of what a rotation is for. Control: five faked repos, exactly three written and two named; then fake elite into holding one and it must be written, proving the rule is derived from live state and not a hardcoded list.
- [ ] D2. The two dormant secrets are a DECISION for the operator, not a change to make: keep them current, or delete them as least-privilege. Recorded because a script that silently keeps two unused credentials alive is a fact someone should have chosen.

### Part E: how a session that has never seen this finds the procedure
Four rings, each independently sufficient: the failing command prints it (A2/A3);
a raw `bws` typed by the session is caught by trapguard and injected as context
(A5, and this is the ring that literally answers the question); CI prints it as an
annotation (A4); the corpus carries it (A7). Ring 2's stated limit: trapguard runs
only in a Claude Code session in this repo.

### Part F: the notice text
Held in `.ci/config/bws-rotation-notice.txt`. It must say, in this order: what
happened and that expired/revoked/deleted/network all look identical from here;
that NOBODY can mint from here because `bws 2.1.0` has no such verb; that an AI
session's whole part is to tell the operator and stop; explicitly DO NOT ask for
the token in the conversation, DO NOT put it in a tracked file, DO NOT offer to
run the script; and what the script does, so the operator knows what they are
agreeing to.

## Sequencing
A1 first. A2 and A3 together, sharing one classifier. A4 in parallel. B1 to B4
strictly in order, each a refusal the next depends on. C only after A2, or
`bws-env.sh` names a file that no longer exists. D1 is inside B3.

## What this design does NOT cover
- Minting. Web-vault only; every part of this plan is downstream of a value the operator already holds.
- Advance warning of any kind. Deliberately.
- The read/write token split from `agent/PLAN-env-to-bitwarden.md:225-226`.
- Rotating anything else; downstream secrets belong to `private/account/scripts/rotation/`.
- Revoking the old token. A revoke reminder firing before propagation is verified is worse than none. OPEN QUESTION for the operator: should it print one after B4 passes?
- Proving the right value landed in a GitHub secret. Unreadable by design; the next CI run is the only end-to-end proof.
- The exact stderr of a genuinely EXPIRED token. `invalid_client` is an informed guess from a nonexistent client id. Nothing depends on it. OPEN BOX: record the real string at the next real expiry.
- A CI gate catching a stale repo secret. A gate cannot read a secret's value, so it could only check a date, which is the instrument this plan removes.
