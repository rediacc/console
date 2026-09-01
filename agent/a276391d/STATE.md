## SESSION a276391d 2026-09-01T11:00:32Z

# Session a276391d — Bitwarden SM migration, proven live

## ACT FIRST: leaked credential

`AUTOPILOT_PRIVATE_KEY` was printed IN FULL into this transcript — `bws secret create`
treats a value starting with `-----` as a flag and echoed the whole value. Fixed with `--`
before the positionals; exposure stands. Rotate via GitHub → Developer settings → GitHub
Apps → autopilot app → Private keys → new, revoke old; then update org secret, vault field
and SM secret. Tracked `[?] #76f6f55e`.

## Migration DONE — 39 secrets in `ci-shared`

Org **Rediacc** `61f8e970`, SM enabled. Project `ci-shared` =
`2b5e33f9-b5ae-4ecc-972d-b36f00b0f86a`. Token in `private/account/.env` as
`mc_migrate_claude` (**7-day validity**, read-write). 36 vault fields (round-trip verified,
0 missing) + 3 minted R2 backup credentials.

It REPAIRED two keys in flight: both PEMs were corrupt in the vault differently —
`rediacc-ci-cd…pem` by **spaces**, `AUTOPILOT_PRIVATE_KEY` by **literal `\n`**. Neither
parsed as stored; both parse from SM. **SM holds a more correct copy than the vault.**

## ED25519 — PROVEN production

Streamed released `s3://rediacc-releases/cli/stable/rdc-linux-x64` (503 MB): vault
`ACCOUNT_ED25519_PUBLIC_KEY` appears **6×**, dev key **0×** (control). That binary carries
`keys.ProductionPublicKey` from `build-renet.sh:201`. Fingerprint `fb37f1ae16f8b7c0`.
Corroborated: vault X25519 == `rediacc.json` `account.e2ePublicKey` (`edge-eu.rediacc.com`).
**renet has ZERO X25519 refs** — X25519 is the CLI config key, ED25519 the licence key.

## Cloudflare

`CF_EMAIL`+`CF_GLOBAL_API_KEY` in `.env` work against account
`fa51e4a18d553c30e1633288e9733d04`. Minted `backup-s3-20260901T103133Z` (account-scoped R2
write, matching the 3 existing R2 tokens); derived S3 creds verified live. **The OLD backup
credential is still active and unidentified.**

## Reusable

```
export BWS_ACCESS_TOKEN="$(grep -m1 '^mc_migrate_claude=' private/account/.env | cut -d= -f2-)"
docker run --rm -e BWS_ACCESS_TOKEN \
  ghcr.io/bitwarden/bws@sha256:3927158c53ac5a17d6cbe59fc3e1353e426f168bf246dbfe3668f6de5eaa107f \
  secret list 2b5e33f9-b5ae-4ecc-972d-b36f00b0f86a -o json
```
`~/.bw-session` = unlocked PM session; `bw` at `~/.local/bin/bw`.

## Also landed (uncommitted except commit 3dffe820f)

5 Dockerfile downloads sha256-verified + ttyd by digest; gate
`check:ci-unverified-downloads`; 2 workflow fixes (`cd-stage.yml` piped nfpm into `sudo
tar` while sibling `ci.yml:810` verified; `ci-build-renet.yml` pulled golangci-lint from
`master`). **Do not commit `scripts/ci-runner/manifest.ts` wholesale** — peer f88f9be7 has
a hunk there.

## Next action

1. Migrate the 5 `.env`-sourced secrets into `ci-shared` (`R2_ACCESS_KEY_ID`,
   `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`, `CLAUDE_CODE_OAUTH_TOKEN`,
   `TURNSTILE_SECRET_KEY`). No operator needed; token live 7 days.
2. Fold in the backup-storage sub-agent's verdict on `BACKUP_S3_BUCKET` (single value
   shared by all regions, yet buckets are region-suffixed and **no `rediacc-backups-eu`
   exists**; operator thinks it is an untested new feature).
3. Then the 16 rotation-backed secrets via `./run.sh rotation rotate <slug>`.

## Remaining

- `[?] #76f6f55e` rotate the leaked AUTOPILOT_PRIVATE_KEY — operator only.
- GPG regeneration + the revocation cert `docs/code-signing-guide.md:559` leaves unticked.
- `BACKUP_S3_BUCKET` value; repoint the org secret at the new R2 credential, revoke the old.
- `gh auth refresh -h github.com -s admin:org`.
