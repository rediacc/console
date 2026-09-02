## SESSION legacy 2026-09-02T12:08:16Z (adopted from a pre-section document)

# Session a276391d — state for compaction recovery (rewritten 2026-09-02 ~14:40Z)

## What the manager is doing

Driving three Opus writers on the secret-namespace migration and verifying each against
its ARTIFACTS, not its summary. Standing constraints unchanged: nothing committed, never
print a secret value, `mc_migrate_claude` expires 2026-09-08 and must not enter GitHub,
never `rotation sweep`, copy-not-mint (8ter).

| writer | task id | owns | status |
|---|---|---|---|
| A `a2bc489ded83d4a48` | shadow-run wiring | `.github/workflows/**` | DONE and verified: 61 jobs/20 files, 0 fetch-before-checkout, planted name fires `check:ci-bws-map`, six gates rc=0. Its two found-not-fixed items (composite needs `jq` on ubuntu-slim; `MIN_CALLERS` 0) fixed by the manager. |
| B `ae2be21d745d9eda0` | Worker-side rename + shim deletion | `private/account/**`, `.ci/scripts/{deploy,infra}/**`, `.ci/docker/**`, `.ci/lib/**`, `scripts/dev/deploy-bench.sh`, `run.sh` | RUNNING. Three messages queued to it: deploy-bench inner fallbacks still old names; `run.sh:1512` reads a key absent from `.env`; biome/shfmt red on two of its files; token key is `BWS_ACCESS_TOKEN`. |
| C `aa9f328b299b63c79` | Bitwarden-side rename | `.github/workflows/**` (only `NAME > BWS_X` lines), `.ci/config/bws-secret-map.json`, new `scripts/dev/bws-map-refresh.py` | RUNNING. Downloads pinned bws to scratchpad, renames ci-shared keys in place (UUIDs preserved), regenerates the map, vault `c38d82bb` field names. |

## When B reports — verify, do not believe
- `git diff --stat` its file set; `npm run check:ci-worker-secret-names`; account vitest; tsc/eslint/biome; `check:ci-shell-format`.
- `.env` VALUE column unchanged: sha256 of sorted values before/after (B was told to report it).
- Every `_require_nonempty` label prints the NEW name; `deploy-bench.sh:203-206` inner fallbacks renamed.
- Then rename TRACKED keys in `scripts/check-env-credential-drift.ts:57` (mine) and run `npm run check:env-credential-drift`.
- Then the deferred CI reds that need a quiet tree: `#43e68519` deps upgrade (`npx -y npm@10 install --ignore-scripts` + `install:natives`), `#f25a9501` tutorial-player re-run alone.

## When C reports — verify
- `check:ci-bws-map` 48/20/floor 20; `git diff .github/workflows` shows ONLY `NAME >` left sides; map diff = renames only, same ids; readback names == Part 10 targets; vault leg done or exact error.

## Fixed this span (all uncommitted)
- Full `npm run ci` (task b4dz41z8m): 345 ok / 8 failed. Fixed: 5 untracked gate files STAGED (not committed) so `check:ci-gate-manifest` leaf-tracked passes; knip `bws` ignoreBinaries with BLOCKER; eslint ignores `**/*.tmp/` (guard-mutations sandbox race); `check:i18n` and `lint:unused` share mutex `www-src-probe` (knip refuses an ignore entry for a transient file); duration cache now `{ewma, recent[5]}` and the tier oracle judges the floor (load poisoning). Transient: `check:ci-toolchain-pins` A10 passed on re-run (a writer had a file mid-edit).
- Inventory recorded as Part 12 of the durable plan; Part 10 Bitwarden row corrected to `BWS_ACCESS_TOKEN`; durable checkboxes 51/52/53/58/64 marked done; execution plan's shadow task split into WIRED [x] / SOAK [ ].

## Waits that are conditions, not to-dos
- `[?] d76f8e3d` token for the soak (operator creates a read-only machine account). DEFAULT: do not put `mc_migrate_claude` in GitHub.
- `[?] 4edffafa` 7 mintable gaps. DEFAULT: do not mint.
- GitHub-side rename (`#51bbba34 #3c8d2d34 #119d740a`): sequenced AFTER the cutover by the operator. Next concrete step when a writer slot frees: a dry-run rename script built from Part 12's sed rules.

## SESSION a276391d 2026-09-02T14:12:01Z

## True right now (2026-09-02 ~17:20Z, all uncommitted, branch main)

Secret-namespace migration, manager over Opus writers. Never commit without an ask; never print a secret value; copy, never mint.

- **The operator created the Bitwarden CI token.** A read-only `ci-shared`-scoped machine account, set as a REPOSITORY secret `BWS_ACCESS_TOKEN` in console/account/renet (org-level selected visibility is unavailable on GitHub Free for private repos). Verified: present in all three repos, absent from the org's 45 (nothing shadows it), recorded `via: repo`, `check:ci-secret-reachability` exit 0. The read-WRITE token in `private/account/.env` under the same key is a DIFFERENT credential, expires 2026-09-08, and must never enter GitHub.
- **`ANTHROPIC_API_KEY` is removed from the system** (operator: no pay-as-you-go billing, the key will never exist). Gone: the workflow env line, the `apiKey` branch in `watchdog-monitor.cjs`, three fixture assignments, and the `OPTIONAL` allowlist entry (now `{}`). Watchdog tier 2 authenticates on `CLAUDE_CODE_OAUTH_TOKEN` alone, reachable in all three repos. 45 references, 0 unreachable.
- Writers A-F all DONE and manager-verified: shadow-run in 61 jobs/20 files, Worker-side rename + shim deletion, 22 ci-shared keys renamed in place, workflow env mappings, rotation `bitwarden_secret_names` + shared dkim reconstruction, and a new `check:ci-builder-env-contract` gate.
- `scripts/dev/secret-rename.py` built and DRY-RUN only (1315 replacements / 106 files). The GitHub-side rename waits on the operator's cutover ordering.
- Fixed today in the hooks themselves: the brave-default judge rule was ordering "commit to the open branch", which standing order 1 forbids; `wl_rules.py:136 names_operator_reserved` now drops such an order in both rules that emit one. 263 judge controls pass.
- Account suite 92 files / 1550 tests green. Deps all current.

## Next action

1. ONE full `npm run ci` on a quiet tree, backgrounded, ~16 min, output to `ci.out`/`ci.err` in the scratchpad. Expect green except `check:env-credential-drift` (`ABSENT AWS_SES_ACCESS_KEY_ID`), which belongs to another session's `#2d728f0a`. Fix anything else it finds.
2. The soak on `main` needs a commit and a push, and that is the operator's ask to give. Do not commit unasked.
3. Operator-owned: `[?] 51bbba34/3c8d2d34/119d740a` GitHub-side rename timing (default already executed: dry-run only); `[?] 7bd69fa8` rename `BACKUP_R2_*` to `ACCOUNT_BACKUP_R2_GRANT_*` (default: do it, keep `CLOUDFLARE_R2_BACKUP_*`).
4. Unblocked and offered to the operator: GPG revocation certificate; the 3 unreferenced SMTP org secrets; narrowing the backup R2 credential and revoking its predecessor; narrowing the `gh` token; the `private/growth` + `private/generative` renames.
