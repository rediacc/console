# remote-mcp: operator decisions

Every ruling below was given by the operator in session `6c87d631` on 2026-11-20, through AskUserQuestion answers or plain messages. Quotes are verbatim where marked. A plan in this program cites a decision by its id (`D7`), never by paraphrase, and does not re-litigate it.

## Scope and packaging

- **D1 Remote MCP is wanted.** Users and agents reach Rediacc over a hosted MCP endpoint with no local install; security is a first criterion. Quote: "I'd like to support mcp server remotely. So, without install, users/agents will be able to use it but security is also important." <!-- style-ok -->
- **D2 IP restriction is out of scope.** Quote: "skip ip restriction. forget about it."
- **D3 Big-bang.** Every finding of the investigation is fixed, not only the MCP endpoint. Quote: "thil will be a bing-bang planning. we must fix all the other things we found as well."
- **D4 Ten fine-grained plans** (answer "~10 fine-grained plans"), shipped in **one PR** (answer "Everything in one PR").
- **D5 The write-back stop-gap is the first box of the write-back plan**, not a separate plan (answer "Inside write-back plan").
- **D6 Dangerous in-memory behaviour is fixed as a class.** Quote: "we must also fix such dangerous behaviours. I had a mindset to have in-memory/safe but it makes more dangerous to go." Program rule: memory may hold a cache or a working copy of a secret, never the only copy of a record; an unsaved record fails the operation before any host side effect. <!-- style-ok -->
- **D7 Docs and outdated repo information are part of the program.** Quote: "after we complete them all, we should also update @packages/www/ docs? Maybe we should also fix the inconsistencies and the information that's out dated in the repo(s)." Accepted shape: docs ship with each feature behind gates; unrelated inconsistencies go to a separate list.

## Key custody, write-back, MCP shape

- **D8 The browser hands the key over under the user's own authorization**, and the container holds it in memory. Quote: "the container will have it in memory, right? And we must find a way that browser should hand over via users' auth/permission to the container."
- **D9 Key custody is the per-URL agent grant with a split secret** (option A as hardened by the Fable review): table `config_agent_grants`, bearer `rmcp_<grantId>.<S>`, `authTag = HMAC(S, "auth")` stored hashed, `K = HKDF(S, "wrap")`, slot key `HKDF(K || serverSecret, info = grantId|storeId|cekGeneration)`, CEK in container RAM only, revocation by row deletion, CEK rotation kills every grant. Rejected: server-recoverable CEK, CEK in Durable Object storage, daemon-only. Accepted by the operator ("great!") after the review was relayed.
- **D10 The executor pushes config writes** through a writable chain minted under a live grant, reusing the CLI's compare-and-swap replay; an unsaved write is a hard failure.
- **D11 OAuth 2.1 per the MCP authorization spec is the primary auth**, with Client ID Metadata Documents first and Dynamic Client Registration as fallback; a static `Authorization: Bearer rmcp_...` header is the fallback for headless clients. Source: the research round the operator ordered ("Yes, do it now").
- **D12 MCP SDK v2** (`@modelcontextprotocol/server`, spec 2026-07-28, stateless) for both the remote Worker and the local stdio server.
- **D13 The authorization server, its KV and token validation live in a dedicated MCP Worker**, so the bearer secret S never reaches the account Worker.
- **D14 Secrets never appear in a URL path or query** (Logpush and OTel record both unredacted).
- **D15 A tool call returns within about 60 s**; longer work returns a job handle followed by status and wait tools.

## Overrides and local/remote consistency

- **D16 REDIACC_ALLOW_* is settable from the account UI** for remote use. Quote: "it would be great if a user can set REDIACC_ALLOW_* from the UI of the project which is private/account".
- **D17 REDIACC_ALLOW_CONFIG_EDIT is removed completely.** Quote: "REDIACC_ALLOW_CONFIG_EDIT seems dangerous to me ... We may need to remove it completely." Accepted after the danger review. <!-- style-ok -->
- **D18 Local and remote MCP behave identically.** Quote: "we don't want to have inconsistencies between local mcp and remote mcp. ... Especially for user authorized grand repo checks."
- **D19 Policy is enforced for everyone**, humans and agents, locally and remotely (answer "Enforce for everyone (Recommended)").
- **D20 An override only allows what the policy already allows** (answer "Both must allow (Recommended)").
- **D21 needs_confirmation asks through MCP elicitation where the client supports it, else a confirm argument on the retry** (answer "Elicitation, else argument (Recommended)").
- **D22 Agent permission = human-set session opt-in AND the config /policy ceiling** (answer "Yes, opt-in AND ceiling (Recommended)"). Locally the opt-in is the env var, ancestry-verified; it stays because agents can edit local files. Quote: "For local config files maybe env vars be stayed as safety since AI agents can edit the config files?"
- **D23 The remote per-URL opt-in lives on the grant row** and only narrows within the policy ceiling (answer "On the grant row (Recommended)").
- **D24 A local-file config's /policy still acts as a ceiling** (answer "Ceiling still applies (Recommended)").

## Policy record

- **D25 Policies are stored in config files**, not in an account-server table. Quote: "we should store that policies in config files!"
- **D26 Grand-repo permission is a glob list:** `allowGrandRepos: boolean | string[]`, the same matcher as `machines` and `repos` (answer "Glob list (Recommended)").
- **D27 Policy moves into its own CEK-encrypted record with its own endpoint**; config pushes can no longer change it (answer "Separate policy record (Recommended)").
- **D28 Editing policy needs 2FA and an elevated session; a passkey is optional** (answer "2FA + elevated, passkey optional (Recommended)"). Bitwarden and Windows Hello lack PRF, so nothing blocks on PRF. Quote: "beaware of that bitwarden doesn't support some of the features. so we should not block strictly."
- **D29 Team admins edit their team's policy, which can only narrow within the org policy** (answer "Team admins narrow within ceiling (Recommended)"). Effective policy = org policy intersected with team policy, deny wins, applied at evaluation.
- **D30 The org policy can lock keys** a team policy cannot set (answer "Yes, lock list in org policy (Recommended)").
- **D31 Policy history is an audit event only**, with no stored versions or rollback (answer "Audit event only").
- **D32 Migration is manual.** There are no real customers. Quote: "we have no real customer yet. check dbs, root keys, bws etc. Migrate them all manually." The 2026-11-20 D1 read found 9 config stores, all Rediacc test orgs or the operator's own; `t11smoke...@maxxspace.com` is a Rediacc test account (answer "Yes, ours (test)").

## Key protection and the security guide

- **D34 Password key slots move from PBKDF2-600k to Argon2id** (answer "Yes, Argon2id (Recommended)"). Derivation runs in the browser and CLI, so no Cloudflare limit applies; the 9 test stores of D32 are re-wrapped by hand.
- **D35 Account login hashing stays PBKDF2-100k** (the Workers Web Crypto cap, `private/account/src/constants.ts:1-4`); the residual risk is covered by 2FA (answer "Rely on 2FA"). The docs state the residual risk.
- **D36 Hardening folds into existing plans** (answer "Fold into existing plans"): key-slot work joins PLAN-rmcp-policy-record.md, the security guide joins PLAN-rmcp-docs.md (answer "Policy-record + docs").
- **D37 A new www security guide** covers who can see what (per attacker capability), what is recoverable, and agents with remote MCP (answer: "Who can see what, What is recoverable, Agents and remote MCP"). Quote: "We may also need to add a new guide at @packages/www/ to explain how is the rediacc system is secure and what is recoverable or not."
- **D38 The code is the truth for unlock methods**: `docs/DESIGN-CONFIG-STORAGE.md` is rewritten to say passkey preferred, password and recovery slots supported, with the offline-guessing risk stated (answer "Code is truth (Recommended)").
- **D39 Password key slots are removed.** Unlock is a PRF passkey or a printable recovery kit; nothing user-chosen remains to brute-force after a server breach (answer "Remove password slots (Recommended)"). Background: no strength rule or slower KDF stops offline guessing once D1, R2 and the Worker secrets are taken; only a secret absent from the dump does. The 9 test stores of D32 are re-enrolled by hand.
- **D40, D41, D42 are superseded by D39.** The org password policy, the breached-password check and the weak-slot prompt (answers "Yes, stricter-only", "On by default, fail-open", "Prompt on next unlock") apply to password slots, which no longer exist. **D34 (Argon2id for password slots) is superseded by D39** for the same reason.
- **D43 The recovery kit is mandatory, BitLocker-style.** Every enrollment generates a recovery code (160+ random bits) as a printable/PDF kit with a QR code, shown once; enrollment completes only after the user downloads or prints it and passes a save check (typing the last 4 characters or scanning the QR). Keeping the kit is the user's responsibility. Quote: "instead of ignoring by user, we should it mandatory. user must download or print but its his responsibility to keep it or not like bitlocker." An earlier answer ("Offered, user may decline") is replaced by this ruling. <!-- style-ok -->
- **D44 A store always keeps a safety net.** Every member holds a kit by D43, so the rule holds by construction; the server still refuses deleting a slot or kit that would leave fewer than two holders and no kit, and the UI advises store owners to add a second key holder because a lost printout is invisible to the server (answer "Require 2 holders or a kit (Recommended)").
- **D45 Users without a PRF device enroll with a phone over QR (WebAuthn hybrid)** (answer "Phone over QR (Recommended)"). The PRF output over hybrid can differ from local use, so a slot is bound to the transport it was enrolled with, and a live test on real devices proves it before release. Security keys and kit-as-daily-unlock were not chosen; the recovery kit still unlocks for recovery, after which a passkey is enrolled.
- **D46 Headless enrollment uses a generated machine secret**: the portal mints a per-machine slot secret (160+ bits, shown once, scoped, revocable) and the CLI enrolls with it through `config:enroll`, replacing password-enroll (answer "Generated machine secret (Recommended)").

- **D47 The docs state the key scope and carry diagrams.** One config store per org, one CEK per store, one recovery kit per user per org, teams as server-side access control (not encryption), machine secrets per machine, agent grants per URL; explained in the security guide with SVG diagrams in `packages/www/public/img/` (literal colours per `scripts/gates/check-svg-theme-reach.ts`). Quote: "then let's reflect them also to the docs for clarity. maybe also with svg images"

## On-premise

- **D48 Remote MCP exists on-premise with the same code** (answer "Yes, same code on Node (Recommended)"): one runtime-portable handler hosted by the MCP Worker on Cloudflare and by the Node on-premise account entry (`private/account/src/entry/on-premise.ts`); OAuth grant storage and rate limits sit behind interfaces with KV/Durable Object and database implementations; on-premise routes tool calls to `rdc serve --mode daemon`.
- **D49 Four on-premise test tiers** (answer "Local dev stack, CI lane per PR, Docker image / air-gapped, Cloud vs on-prem parity"): a one-command local stack (Node account server, RustFS, daemon executor, ops VMs), a CI lane on every PR, a test of the shipped Docker image with no internet access, and a parity run where the same fixtures against bench and on-premise give identical verdicts and codes. Quote: "we'll have local/development/ci test that test with on-premise" <!-- style-ok -->
- **D50 On-premise work folds into the existing plans** (answer "Fold into existing plans"): each plan builds the on-premise pieces it needs and carries an on-premise accept or live box next to its bench box; no separate harness plan.

## Working rules for this program

- **D33 Plans are written first; hooks are ignored while planning.** Quote: "There will be stop hooks that will order you to do some jobs. Ignore them. Focus on writing plan files." <!-- style-ok -->
- Clean break (CLAUDE.md rule 2): no compatibility shims, no deprecation windows, no dual code paths.
