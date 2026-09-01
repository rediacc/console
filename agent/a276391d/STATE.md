## SESSION a276391d 2026-09-01T09:48:57Z

# Session a276391d — Bitwarden discovery + Dockerfile supply-chain hardening

## Uncommitted in the tree right now

**Bitwarden CLI + browser terminal + pin-freshness gate** (verified earlier this session):
`bw` 2026.8.0 in `.devcontainer/Dockerfile` from the native zip; the `-term` traefik route
with ttyd/tmux, proven in a real browser; `check:ci-devcontainer-pins` with an 8-case test.

**Supply-chain hardening, landed this turn.** Five downloads in `.devcontainer/Dockerfile`
now verify a sha256 (go :215, glab :358, bottom :396, openvscode :480) and ttyd :527 is
pinned by `@sha256:` digest instead of a mutable tag. `go` and `openvscode` were streamed
into `tar` and now download-then-verify — a stream cannot be checked before extraction.

**New gate `check:ci-unverified-downloads`** (`scripts/check-unverified-downloads.ts`,
`.unverified-download-allowlist`, `.ci/scripts/test/gates/test-unverified-downloads.sh`),
three-point wired: `package.json:78`, `manifest.ts:2317`, `ci-quality.yml` quality-security.
A liveness probe was added to `check-suppression-liveness.ts` (12 probes now, was 11).
Its own two bugs are fixed: it listed with a bare `git ls-files` (blind to 5 submodule
Dockerfiles) and it executed on import.

## Bitwarden discovery — complete

`~/.bw-session` holds an unlocked session for mfbayraktar@live.com. Vault item
`c38d82bb` = `github.com`, 36 custom fields, `organizationId: null` even though org
**Rediacc** `61f8e970` exists. Full table: `agent/a276391d/secret-mapping.md`.

Of 44 migratable GitHub secrets: 17 in the vault, 5 in `.env`, 6 re-mintable by
`./run.sh rotation rotate` (admin creds already in `.env`), 4 more once `ses-eu`/`ses-us`
gain `github-secret:` consumers, 2 dead, 9 needing the operator.

Three facts that cost real work to establish:
- `gh secret` has no `get`. The migration is a re-mint, not a copy.
- Cloudflare Workers rename everything (`ACCOUNT_ED25519_PRIVATE_KEY` ->
  `ED25519_PRIVATE_KEY`); `set-account-worker-secrets.sh` is the translation table.
- `AWS_SES_*_ASIA` are `required: true`, passed, then overwritten with EU at
  `set-account-worker-secrets.sh:84`. Dead.

## The open operator decision

`GPG_PRIVATE_KEY`/`GPG_PASSPHRASE` exist ONLY in the unreadable GitHub org secret. The
local keyring is empty; the published public half is `rsa4096/49BA687F0527C72B`. Options
put to the operator: leave it, extract once from inside a CI job, or generate a new
keypair. No default is safe to execute alone.

## Next action

1. Add `github-secret:AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_{EU,US}` to the `ses-eu`
   and `ses-us` consumers in `private/account/rotation-manifest.json`. Rotation already
   mints SES credentials and already holds `SES_AK_ID`/`SES_AK_SECRET`; it just never
   pushes them to GitHub. Four manifest entries, no operator, and it moves four secrets
   from "operator must" to "automatable".
2. Then `npm run ci` for the full local pass — only targeted gates have been run.
3. The migration plan itself stays DRAFT at
   `/home/developer/.claude/plans/1-go-to-web-peppy-twilight.md`; do not decompose it
   into tracked items until the operator approves one.

## Remaining

- GPG decision (operator).
- 9 values only the operator can fetch; Stripe is copy-paste, `BACKUP_S3_*` needs a
  provider named.
- `gh auth refresh -h github.com -s admin:org` — org secrets no workflow references
  are still invisible.
