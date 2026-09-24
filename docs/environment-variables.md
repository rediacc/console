# Environment Variables

Authoritative reference for every environment variable the `rdc` CLI reads, plus the build-time knobs in the wrapper scripts. If a variable is not listed here, the CLI does not read it.

The design rule: **the active config file is the source of truth** for identity and destination (server, keys, channel, machines). Environment variables exist for four narrow jobs: selecting the config, overriding it for one invocation or a CI job, gating agent behavior, and escape hatches. See [dev-environments.md](dev-environments.md) for the config-universe model itself.

## Resolution order

For any value that exists both as a flag, an env var, and a config field:

```
command flag  >  environment variable  >  active config (account.*)  >  shipped default
```

Each level has a distinct owner: this invocation > this shell/CI job > the persisted choice > the product default.

## Where: config selection and connectivity

| Variable | Purpose | Read by |
|---|---|---|
| `REDIACC_CONFIG` | Selects the active config name (`--config` flag wins). Default `rediacc`. | `services/config/config-name.ts` |
| `REDIACC_ACCOUNT_SERVER` | Account-server URL override for this invocation/job. The one connectivity env var. | `services/account/subscription-auth.ts` |
| `REDIACC_UPDATE_CHANNEL` | Release-channel override (config field `account.updateChannel` is the persisted value). | `services/update/updater.ts`, telemetry |
| `XDG_CONFIG_HOME` / `XDG_STATE_HOME` / `XDG_CACHE_HOME` | Standard base-dir overrides. | `packages/shared/src/paths/dirs.ts` |

## Who: credentials (headless / CI)

| Variable | Purpose |
|---|---|
| `REDIACC_TOKEN` | The account api-token, for every flow that needs one: subscription auth, config-store password enrollment, `rdc serve` executor auth. Scopes live inside the token; the server enforces them. Replaces the former `REDIACC_SUBSCRIPTION_TOKEN`, `REDIACC_API_TOKEN`, and `REDIACC_EXECUTOR_TOKEN`. |
| `REDIACC_CONFIG_PASSWORD` | Password-slot secret for headless remote-config unlock. |
| `REDIACC_MASTER_PASSWORD` | Master password for configs encrypted at rest. |

Tokens obtained interactively are stored per config at `<configDir>/api-token-<config>.json`. There is no shared token file.

## Agent gates (ancestry-validated; set them BEFORE starting an agent)

| Variable | Purpose |
|---|---|
| `REDIACC_ALLOW_GRAND_REPO` | Grants grand-repo / direct machine access. |
| `REDIACC_ALLOW_CONFIG_EDIT` | Pointer-glob scope allowing agent config edits. |
| `REDIACC_ALLOW_CLUSTER_OPS` | Gates destructive cluster operations. |
| `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI`, `CURSOR_TRACE_ID` | Agent-environment detection (set by the agent runtime, not by you). |

## Test-infra gates and escape hatches

| Variable | Purpose |
|---|---|
| `REDIACC_SKIP_MACHINE_ACTIVATION` | Skips CLI-side license issuance/recovery. Tutorial/test infra only. |
| `REDIACC_SKIP_FILE_WRITE_GUARD` | Disables the repo-context file-write guard. Tutorial/test infra only. |
| `REDIACC_YES` | Assume-yes prompt bypass (mirror of `--yes`). |
| `REDIACC_NO_DAEMON` | Forces the direct execution path (no executor daemon). |
| `REDIACC_DISABLE_AUTOUPDATE` | Disables the background auto-updater. |
| `REDIACC_UPDATE_INTERVAL_HOURS` | Auto-update check cooldown. |
| `REDIACC_SSH_LINGER_MS` | SSH connection-pool idle linger. |
| `REDIACC_PROVISION_LOCK_TIMEOUT_MS` | Renet provisioning lock timeout. |
| `REDIACC_ALLOW_DOWNGRADE` | Permits renet binary downgrade during provisioning. |
| `REDIACC_ALLOW_DIRTY_RENET` | Permits uploading a dev renet binary built from a source tree with uncommitted or untracked changes. Mutating verbs only; read-only verbs never upload. |
| `REDIACC_SKIP_ROUTER_RESTART` / `REDIACC_SKIP_SETUP_CHECK` | Renet execution skips (advanced). The router-restart skip affects mutating verbs only: read-only verbs never replace renet or restart the router. |
| `REDIACC_DEFAULT_OUTPUT` | Default output format when `--output` is unset. |
| `REDIACC_VSCODE_PATH` | Explicit VS Code executable path. |
| `REDIACC_LANG` | CLI language override. |
| `REDIACC_TELEMETRY_DISABLED` / `REDIACC_TELEMETRY_ENDPOINT` | Telemetry opt-out / dev endpoint. |
| `NO_COLOR` | Disables ANSI color (informal standard; any non-empty value). |

## Debugging

One variable: `REDIACC_DEBUG`.

- `REDIACC_DEBUG=1` or `*`: everything.
- `REDIACC_DEBUG=daemon,renet,timing,otel`: comma-scoped. Scopes: `daemon` (executor
daemon client), `renet` (binary provisioning transfer), `timing` (fork timing chart), `otel` (OpenTelemetry setup).

## Build-time knobs (wrapper scripts only; the CLI never reads these)

| Variable | Purpose |
|---|---|
| `RDC_DEV=1` (or `./rdc.sh --dev`) | Wrapper sugar: seeds/refreshes the `dev` config from the running dev gateway and runs with `REDIACC_CONFIG=dev`. |
| `RDC_RENET_LICENSE=1` | Builds dev renet WITHOUT the `nolicense` tag (license enforcement on). |
| `ACCOUNT_ED25519_PUBLIC_KEY` | Ldflags-injected master key for renet license validation. Build-time only; setting it at runtime has no effect. |

## Test and tooling harnesses (not read by the CLI)

No example env file is tracked; each harness reads these from the environment and falls back to the default shown.

`packages/e2e-tests` (bridge E2E). CI writes them into `packages/e2e-tests/.env` with `PYTHONPATH=.ci python3 -m rediacc_ci.env.create_e2e_env`, which the Playwright configs load:

| Variable | Default | Purpose |
|---|---|---|
| `RENET_BINARY_PATH` | auto-detected | renet binary the suite drives |
| `RENET_DATA_DIR` | CI: from `RUNNER_TEMP`; else `/tmp/renet` when `CI=true` | renet data directory holding the staging SSH keys. Set `~/.renet` locally. |
| `VM_NET_BASE` / `VM_NET_OFFSET` | `192.168.111` / `0` | VM network prefix, and the offset added to a VM id to form its IP |
| `VM_BRIDGE` | `1` | bridge VM id |
| `VM_WORKERS` | `11 12` | worker VM ids, space-separated |
| `VM_CEPH_NODES` | `21 22 23` | Ceph node VM ids, space-separated |
| `BRIDGE_TIMEOUT` | required; `create_e2e_env` writes `120000`, the CI jobs set `240000` | bridge command timeout, ms; must exceed renet's own retry budgets (the RADOS namespace delete retries for 2 minutes). The k8s configs raise it to 360000. |

`packages/www` tutorial audio (`packages/www/scripts/generate-tutorial-audio.ts`, backend in `private/generative`):

| Variable | Purpose |
|---|---|
| `QWEN_TTS_PYTHON_BIN` | Python interpreter for the TTS backend (default `python3`) |
| `QWEN_TTS_MODEL_ID`, `QWEN_TTS_CUSTOM_SPEAKER`, `QWEN_TTS_TUTORIAL_INSTRUCT_PROMPT`, `QWEN_TTS_INSTRUCT_PRESETS_JSON` | model and voice selection, read by `private/generative` |
| `QWEN_TTS_DEVICE`, `QWEN_TTS_DTYPE`, `QWEN_TTS_ATTN_IMPL`, `QWEN_TTS_MAX_CONCURRENCY`, `QWEN_TTS_BATCH_SIZE`, `QWEN_TTS_SAMPLE_RATE_HZ`, `QWEN_TTS_AUDIO_FILTER` | runtime tuning, read by `private/generative` |

## Deleted variables (tombstones)

These names are gone; a CI test (`env-tombstones.test.ts`) fails if they reappear in source. Replacements:

| Deleted | Replacement |
|---|---|
| `REDIACC_ENVIRONMENT` | `VERSION` dev-build sentinel (`isDevBuild()`); as a REMOTE renet env value it still travels, by design |
| `REDIACC_SUBSCRIPTION_TOKEN_FILE` | Per-config token file `api-token-<config>.json` |
| `REDIACC_SUBSCRIPTION_TOKEN`, `REDIACC_API_TOKEN`, `REDIACC_EXECUTOR_TOKEN` | `REDIACC_TOKEN` |
| `X25519_PUBLIC_KEY` (CLI env) | `account.e2ePublicKey` in the config |
| `RDC_BENCH` | `./rdc.sh --config bench` |
| `RDC_UPDATE_CHANNEL` | `REDIACC_UPDATE_CHANNEL` |
| `RDC_DISABLE_AUTOUPDATE` | `REDIACC_DISABLE_AUTOUPDATE` |
| `RDC_UPDATE_INTERVAL_HOURS` | `REDIACC_UPDATE_INTERVAL_HOURS` |
| `RDC_ALLOW_DOWNGRADE` | `REDIACC_ALLOW_DOWNGRADE` |
| `RDC_SKIP_ROUTER_RESTART` / `RDC_SKIP_SETUP_CHECK` | `REDIACC_SKIP_ROUTER_RESTART` / `REDIACC_SKIP_SETUP_CHECK` |
| `RDC_DEBUG_RENET_PROVISION`, `RDC_TIMING_CHART`, `REDIACC_DAEMON_DEBUG`, `DEBUG` | `REDIACC_DEBUG` scopes |
| `REDIACC_NO_COLOR` | `NO_COLOR` |
| `REDIACC_TEAM` / `REDIACC_REGION` | none (config fields; env overrides were unused) |
| `server.json` (file, not env) | `account.*` fields in the active config |
