---
name: config-universe
description: The rdc config model: each named config is a self-contained universe (account server + E2E key + machines + repos + its own api-token file), the v3 schema and its state mirror, config selection and auto-creation semantics, encrypted config storage with CEK key slots (passkey PRF, master password, recovery code), transfer/sync with the offline read cache, and every config-related trap paid for in live sessions. Use for work on config schema/resolution, config storage or enrollment, multi-config isolation, or diagnosing "Decryption failed", "already exists", enrollment 403s, or WebCrypto OperationError surfaces.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You own the config domain. A config is not a settings file; it is a UNIVERSE, and most
config bugs come from code or people forgetting that.

## The model

- One flat JSON per config at `~/.config/rediacc/<name>.json` (default name rediacc),
  schemaVersion 3, carrying: `account.*` (accountServer URL + e2ePublicKey), machines,
  repos, datastores, clusters, credentials, defaults, an immutable `id`, and a
  monotonically bumped `version`. Its api-token lives BESIDE it as
  `api-token-<name>.json`. There is no server.json and no shared token: switching
  configs switches server, keys, fleet, and identity all at once.
- Selection: `--config <name>` beats `REDIACC_CONFIG` beats the default.
  `rdc config current` shows the active one and each value's source label.
  `./rdc.sh --dev` seeds/patches `dev.json` and runs with REDIACC_CONFIG=dev; bare
  `./rdc.sh` is the production default config.
- Schema source: packages/shared/src/config-schema/schemas.ts (records for machines
  :472, datastores :473, clusters :479; ClusterConfig carries controlNode). The state
  mirror (state-schema.ts: state.datastores/machines/clusters) is HOST-LOCAL and NEVER
  enters the remote config blob; keep that property when adding fields.
- Every RdcConfigSchema leaf needs a sensitivity.ts entry or check:ci-schema-coverage
  fails closed: that gate exists because v3 resource families once silently escaped
  encryption/commitment.
- Writes are versioned and produce `<name>.json.bak` (the previous content). A .bak
  whose version is exactly one behind is normal write behavior, not corruption; two
  quick versions (bare create then a patch) are the signature of auto-create followed
  by a heal.

## Auto-creation and its trap

The CLI AUTO-CREATES the active config on startup of ANY command when it does not
exist: default config on first use (never tell users to init it), and equally the
config named by REDIACC_CONFIG. THE TRAP: exporting REDIACC_CONFIG=<name> before an
explicit `rdc config init <name>` makes init die with "already exists", because some
earlier invocation (even a wrapper preflight like `rdc ops status`) auto-created it;
worse, the bare auto-created config has no accountServer, so the key-discovery heal
syncs the PRODUCTION server's E2E key into it. Order: init with the explicit name
FIRST, export REDIACC_CONFIG after. `config init <name> --server <url>` syncs that
server's e2ePublicKey at init (unreachable server = warning, healed on first
successful request). Config names must be treated as data: isolation is proven by
md5-ing config A before/after operations on config B (the universe drill does this).

## Encrypted config storage (the remote store)

- Zero-knowledge: blobs encrypted client-side; ONE org-wide CEK encrypts every team's
  configs; team scoping is server-side ACL, not crypto. Metadata in D1/SQLite, blobs
  in R2/RustFS.
- CEK is wrapped LUKS-style in per-(store,user,method) key slots: passkey_prf (PRF
  salt constant must be identical at every ceremony), master_password (PBKDF2 600k),
  recovery_code (RC1- + Crockford base32). Every slot yields a 32-byte slotSecret;
  wrapping key = derive(slotSecret, serverSecret): the server holds only half.
  Rotation bumps cekGeneration; stale slots report errorCode stale-slot, and recovery
  codes never survive rotation.
- Enable from CLI: `rdc config remote enable` (portal handoff; seeds the store from
  local on first enable: expect a "store was empty, pushed v1"-class message) or
  `--password` for the headless path (api-token needs the config:enroll scope; the
  enrolling member is the token's creator). Sync is implicit; reads fall back to an
  encrypted-at-rest local cache when the server is down WITH a staleness warning on
  stderr (stdout stays clean); writes FAIL CLOSED offline.
- Write conflicts converge by pull-at-read; a concurrent second seed at the same
  version is a 409 replay, test-pinned.

## Diagnosing the known failure surfaces

- "Decryption failed" on the first tunnelled call: the config's e2ePublicKey does not
  match the server (classically: a config whose key was never synced, or synced from
  the wrong server). Any later successful command heals it; `rdc config current`
  forces the heal.
- Enrollment 403s carry a coded message since 2026-08: passkey-required, IP-bound
  token (api-tokens BIND TO THE CLIENT IP ON FIRST USE: never let curl be the first
  user of a token the CLI will use: tunnel vs direct present different IPs), missing
  config:enroll scope, teamless/orgless token. Unknown 403s quote the server
  verbatim.
- WebCrypto unwrap/decrypt failures are now classified: HMAC failure = the blob was
  sealed under a DIFFERENT CEK than the slot holds (store/config identity mismatch:
  message names configId+storeId; typical when enrolling a fresh device against a
  store already holding another config, or a stale portal handoff tab); post-HMAC
  failure = session layer, retryable. If you ever see a raw "operation-specific
  reason" error, a classification seam was bypassed: fix the seam, not the message.
- Non-TTY stdout auto-selects JSON output (a piped/scripted rdc measures the machine
  surface): pin REDIACC_DEFAULT_OUTPUT=table when asserting human output, and note
  empty LISTS emit an empty JSON envelope while table mode prints a stderr hint with
  EMPTY stdout.

## Testing this domain

- `./run.sh drill universe` (headless): source labels, isolation md5s, env
  precedence, per-config tokens. `./run.sh drill transfer` (needs
  ./run.sh account dev): seed-on-enable, offline cache + stderr warning, fail-closed
  writes, second-device password+TOTP enrollment. Both have --selftest and
  --keep-work.
- Unit/integration precedents: config-remote.test.ts (seed races, 409 replay),
  remote-config-adapter.real-crypto.test.ts (real-crypto mismatch cases),
  test-mode-gating.test.ts (the /test/* harness). Use a throwaway XDG_CONFIG_HOME for
  any live-CLI test; on WSL remember `machine add` also writes an SSH alias into the
  WINDOWS home (getSSHHome precedence is deliberate for VS Code Remote SSH: the
  message prints the real path).
