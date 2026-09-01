# Secret coverage map — Bitwarden vault vs GitHub Actions vs private/account/.env

NAMES ONLY. No secret value has been read, printed, or stored here.
Generated 2026-09-01 from: bw item c38d82bb (36 custom fields), gh secret list,
grep of secrets.* across .github/workflows + .github/actions, and .env key names.

## Counts
- 44 migratable GitHub secrets (45 referenced minus auto-provided GITHUB_TOKEN)
- 17 covered by the vault, including 2 cross-name aliases
- 5 covered only by an exact .env key name
- 22 with no readable source anywhere

## Aliases (vault field name -> GitHub secret name)
- rediacc-ci-cd.2026-02-01.private-key.pem=APP_PRIVATE_KEY
- DOCKERHUB_TOKEN_GITHUB=DOCKERHUB_TOKEN

## No readable source anywhere — must be re-minted, not copied
- ANTHROPIC_API_KEY
- AWS_SES_ACCESS_KEY_ID_ASIA
- AWS_SES_ACCESS_KEY_ID_EU
- AWS_SES_ACCESS_KEY_ID_US
- AWS_SES_SECRET_ACCESS_KEY_ASIA
- AWS_SES_SECRET_ACCESS_KEY_EU
- AWS_SES_SECRET_ACCESS_KEY_US
- BACKUP_S3_ACCESS_KEY_ID
- BACKUP_S3_BUCKET
- BACKUP_S3_ENDPOINT
- BACKUP_S3_SECRET_ACCESS_KEY
- CLOUDFLARE_API_TOKEN
- DOCKERHUB_USERNAME
- GPG_PASSPHRASE
- GPG_PRIVATE_KEY
- OTLP_CLIENT_CREDENTIALS_ASIA
- OTLP_CLIENT_CREDENTIALS_EU
- OTLP_CLIENT_CREDENTIALS_US
- STRIPE_SECRET_KEY_ASIA
- STRIPE_SECRET_KEY_EU
- STRIPE_SECRET_KEY_US
- STRIPE_WEBHOOK_SECRET_ASIA

## Vault fields no workflow references
- AUTOPILOT_APP_ID
- AWS_SES_HOST
- AWS_SES_REGION
- DOCKERHUB_TOKEN_GITHUB
- OTLP_AUTH_PASSWORD
- OTLP_AUTH_TOKEN=USER:PASS
- OTLP_AUTH_USERNAME
- R2_TOKEN_AUTH_API
- SMTP_FROM
- SMTP_HOST
- SMTP_PASS
- SMTP_PORT
- SMTP_USER
- STRIPE_PUBLISHABLE_KEY
- STRIPE_SANDBOX_PUBLISHABLE_KEY
- STRIPE_SANDBOX_WEBHOOK_SECRET_ID
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- STRIPE_WEBHOOK_SECRET_ID
- rediacc-ci-cd-client-secret
- rediacc-ci-cd.2026-02-01.private-key.pem

## The rename layer (why exact matching undercounts)

Cloudflare Workers hold the same credentials under SHORT names; GitHub Actions uses
prefixed and region-suffixed names. `.ci/scripts/deploy/set-account-worker-secrets.sh`
is the translation table. The vault mixes BOTH conventions, which is why a name-equality
diff missed real matches.

| GitHub Actions secret | Cloudflare Worker secret | in vault as |
|---|---|---|
| ACCOUNT_ED25519_PRIVATE_KEY | ED25519_PRIVATE_KEY | ACCOUNT_ED25519_PRIVATE_KEY |
| ACCOUNT_X25519_PRIVATE_KEY | X25519_PRIVATE_KEY | ACCOUNT_X25519_PRIVATE_KEY |
| ACCOUNT_JWT_SECRET | JWT_SECRET | ACCOUNT_JWT_SECRET |
| ACCOUNT_SERVER_API_KEY | API_KEY | ACCOUNT_SERVER_API_KEY |
| STRIPE_SECRET_KEY_{EU,US,ASIA} | STRIPE_SECRET_KEY | STRIPE_SECRET_KEY (1 of 3) |
| STRIPE_WEBHOOK_SECRET_{EU,US,ASIA} | STRIPE_WEBHOOK_SECRET | _EU, _US, and unsuffixed |
| AWS_SES_ACCESS_KEY_ID_{EU,US} | AWS_SES_ACCESS_KEY_ID | not present |
| OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA} | OTLP_CLIENT_CREDENTIALS | OTLP_AUTH_{USERNAME,PASSWORD,TOKEN} |
| BACKUP_S3_* | BACKUP_S3_* | not present |

`private/account/.env` uses the WORKER names, confirming it is one single-region instance
of the same shape rather than a mirror of the CI side.

## DEFECT: two org secrets are set, passed, and then discarded

`set-account-worker-secrets.sh:79-87` reads `SES_KEY_ASIA`/`SES_SECRET_ASIA` and then
overwrites both with the EU values:

    # Asia uses EU SES while ap-northeast-1 production access is pending
    if [[ "$SUFFIX" == "ASIA" ]]; then
        SECRET_SES_ACCESS_KEY_ID="${SES_KEY_EU:-}"

Yet `cd-deploy-account.yml:59,61` declares AWS_SES_ACCESS_KEY_ID_ASIA and
AWS_SES_SECRET_ACCESS_KEY_ASIA as `required: true`, and `:285,288` pass them.
So both org secrets are dead weight today, and the rotation manifest still carries a
`ses-asia` slug rotating a credential production ignores.

## Recoverability — what you can re-mint, and what you cannot

Blast radius grounded in: `CLAUDE.md:569` (ED25519 public key compiled into every shipped
renet via ldflags -> `keys.ProductionPublicKey`), `docs/PLAN-multi-region.md:236-239`
(ED25519 = subscription/license signing, same across regions; JWT = session tokens;
SERVER_API_KEY = admin API), `docs/SECURITY-CONFIG-STORAGE.md:37,65,130` (X25519 = CEK
member-key distribution), `docs/code-signing-guide.md:558-560` (GPG, no backup, revocation
cert unticked).

### D. DEAD — do not migrate (2)
AWS_SES_ACCESS_KEY_ID_ASIA, AWS_SES_SECRET_ACCESS_KEY_ASIA
  -> declared required, passed, then overwritten with EU (set-account-worker-secrets.sh:84).

### C. IRRECOVERABLE if lost — regenerating is customer-visible (4)
ACCOUNT_ED25519_PRIVATE_KEY  IN VAULT  public half is compiled into every shipped renet
ACCOUNT_ED25519_PUBLIC_KEY   IN VAULT  binary; regenerating invalidates every issued licence
GPG_PRIVATE_KEY              NOWHERE   signs the apt/yum repos; users pin the public key
GPG_PASSPHRASE               NOWHERE   and NO revocation certificate exists

### B. Regenerable, real but bounded blast radius (4)
ACCOUNT_X25519_PRIVATE_KEY   IN VAULT  breaks config-storage CEK member-key distribution
ACCOUNT_X25519_PUBLIC_KEY    IN VAULT
ACCOUNT_JWT_SECRET           IN VAULT  every session invalidated; users log in again
ACCOUNT_SERVER_API_KEY       IN VAULT  update admin consumers

### A. Safe to re-mint from a console you can log into (33)
Cloudflare: CLOUDFLARE_API_TOKEN, R2_{ACCESS_KEY_ID,SECRET_ACCESS_KEY,ENDPOINT},
            R2_MEDIA_*(vault), TURNSTILE_SECRET_KEY, BREAKPOINT_TUNNEL_TOKEN(vault)
AWS IAM:    AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_{EU,US}, BACKUP_S3_*
Stripe:     STRIPE_SECRET_KEY_{EU,US,ASIA}, STRIPE_SANDBOX_SECRET_KEY(vault),
            STRIPE_WEBHOOK_SECRET_{EU,US,ASIA}, STRIPE_SANDBOX_WEBHOOK_SECRET(vault)
GitHub App: APP_PRIVATE_KEY(vault), AUTOPILOT_PRIVATE_KEY(vault) - generate new, revoke old
Other:      DOCKERHUB_{TOKEN,USERNAME}, ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN,
            OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}

### E. Never migrate (1)
GITHUB_TOKEN - auto-provided per job.
