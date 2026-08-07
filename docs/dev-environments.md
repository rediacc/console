# Development Environments: the Config Universe Model

How to develop and test `rdc` against local, bench, and production account servers
without the environments contaminating each other.

## The model

**One named config = one complete universe.** A config file
(`~/.config/rediacc/<name>.json`) carries everything that defines "who am I and where
do I point":

- `account.accountServer` : the account server URL
- `account.e2ePublicKey` : that server's X25519 tunnel key
- `account.updateChannel`, `account.releasesUrl` : update preferences
- machines, repos, credentials : the infrastructure this universe manages
- its token lives beside it at `api-token-<name>.json`

There is no global `server.json`, no mode env vars, no shared mutable state between
universes. Switching universes is switching configs:

```bash
./rdc.sh repo up app                  # default config 'rediacc' -> production
./rdc.sh --config dev repo up app     # 'dev' config -> local dev gateway
./rdc.sh --config bench repo list     # 'bench' config -> bench.rediacc.com
```

Consequences by construction:

- A dev-mode `subscription login` cannot poison production: it writes only `dev.json`.
- Dev commands cannot touch production machines: the dev config has its own machine list.
- "Where am I connected?" always has one answer: `rdc config current`.

## Local development (`--dev`)

```bash
./run.sh account dev          # start the local account gateway (dynamic port)
./rdc.sh --dev config current # sugar for --config dev, plus freshness check
```

`--dev` (or `RDC_DEV=1`) does exactly three things:

1. Reads `REDIACC_ACCOUNT_SERVER` and `X25519_PUBLIC_KEY` from `private/account/.env`.
   The gateway self-records its URL there on every start (`updateEnvServerUrl` in
   `dev-gateway.ts`), so dynamic ports need no manual handling. Only those two lines
   are read; the file is never `source`d, so server private keys stay out of the CLI
   process environment.
2. Probes the gateway and fails fast with a clear message if it is not running.
3. Seeds or patches `~/.config/rediacc/dev.json` with those two values and runs with
   `REDIACC_CONFIG=dev`.

Everything else (token, machines, channel) lives in `dev.json` like any other config.

## Bench

Bench is just a config:

```bash
./rdc.sh --config bench subscription login --server https://bench.rediacc.com   # once
./rdc.sh --config bench machine status test-1
```

## Production testing from source

Bare `./rdc.sh` behaves like an installed `rdc`: default config, real token, real
servers. That is deliberate. Use it when you want to verify against production;
use `--dev` for everything else.

## How to tell where you are connected

- `rdc config current` : active config name, file path, account server (with the
  winning source labeled: env / config / default), channel (same labeling), token
  state, remote-store status, and encryption mode.
- The `rdc.sh` wrapper banner names the config it runs with.
- `rdc subscription status` names the server it would use even when logged out.

## Licensing across universes on a shared machine

A machine managed by more than one universe (e.g. production and bench both deploying
to the same box) holds one repo-license file **per signing key**:

```
/var/lib/rediacc/license/repos/<repo-guid>/<keyId>.json
```

`keyId` is a 16-hex fingerprint of the signing server's Ed25519 public key. Each
universe's renet build validates only the file its baked key (or a delegation cert
chained to it) can verify; other universes' files are inert. Switching universes
therefore never invalidates licenses: the first operation in a new universe issues
that universe's license once (`missing` -> auto-issue), and both coexist afterwards.

Dev builds of renet are compiled with the `nolicense` tag by default (no enforcement).
To reproduce license-flow bugs locally, rebuild with enforcement:

```bash
ACCOUNT_ED25519_PUBLIC_KEY="<paste the value>" \
RDC_RENET_LICENSE=1 ./rdc.sh --config <name> ...
```

`ACCOUNT_ED25519_PUBLIC_KEY` must match the server that signs the licenses you are
testing against; it is baked in at build time (runtime setting has no effect).

**Paste the value; there is no URL to fetch it from.** This block used to read
`"$(curl -fsS https://www.rediacc.com/api/public/account-key)"`. That endpoint
returns 404 -- verified again 2026-08-05 -- and the account API is not served
from `www.rediacc.com` at all. Because the substitution is not checked, `curl -f`
exits 22 and the variable is assigned the EMPTY string, the build succeeds, and
every prod-signed license then fails as `invalid_signature`: precisely the
symptom this variable exists to prevent. Drop the `-f` and it is worse, since the
404's HTML body gets baked into `keys.ProductionPublicKey` via ldflags.

Never pipe an unchecked HTTP response into this variable. CI does not need to:
`ACCOUNT_ED25519_PUBLIC_KEY` already exists as an organisation secret, so a
workflow references it directly. Locally the value must be pasted -- GitHub
secrets are write-only, so no command can fetch it, and the old one-liner was not
merely pointing at a dead URL but at a shape of solution that cannot exist for a
secret. Same correction as `CLAUDE.md`'s licensing section, which fixed its own
copy on 2026-07-29 while this one was missed.

## Remote config store and offline behavior

A config enrolled in the account config store (`rdc config remote enable`) keeps a
full local **read cache**, encrypted at rest with the same mechanism as any local
config:

- Reads work with the account server down (cache is served with a staleness warning
  on stderr).
- Writes require the server and fail closed with an error naming the server; there is
  no offline write queue. If a command succeeded, the change is on the server.
- Concurrent edits from two machines resolve by pull-replay-repush at the resource
  bucket level.

Team scoping in the store is server-side access control, not cryptographic isolation:
one org-wide CEK wraps every team's configs.

## Troubleshooting

| Symptom | Check |
|---|---|
| "Which server did that hit?" | `rdc config current` (look at the source label) |
| Command against localhost fails | Is the gateway up? `./run.sh account dev`; `--dev` probes and tells you |
| License error after switching universes | Expected once per universe per repo: the first op auto-issues. Persistent `invalid_signature` means a genuinely corrupt file, not a universe mismatch |
| Token missing after upgrade | Tokens are per config now: `api-token-<name>.json`. Re-login or rename the old `api-token.json` |
| Update channel reset to stable | Channel now lives in the config: `rdc update --channel <ch>` re-pins it |
