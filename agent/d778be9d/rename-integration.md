# Rename batch integration list (2026-11-08)

The product-domain rename lands as ONE batch: W3 removes EDGE_ORIGIN and the edge hosts, so nothing lands alone. Website W2/W5 consume the same names and land in the same batch. Order: submodule commits first, then console picks, then the edits below, then regenerate, then gates once, then W11.

## Lease commits to land

| Box | Lease | Commits |
|---|---|---|
| rename W3 58b6398f | agent-aa25dd4994ff76966 | b04309503c |
| rename W4 9b7cf5fc | agent-a794f16dcdde7fd8e | f53c8bfc65; account 98329c9 |
| rename W6 f6e0cfd1, W7 f70ece24 | agent-af7ce4ba85f3bdc11 | 7cf1a1e1a3, aafa930f00 |
| rename W8 e6d20a1c, W9 63337671 | agent-af9cfe648a8f5cf89 | account 1538619, 81fa7d4 |
| rename W10 c418d185 | agent-a4c47819a5fdb8a6e | c13d23017d |
| rename W12 1e8a7bfc | agent-a33aa73a42ee91fd6 | 6efd68a6cf; account 27a1a42 |
| rename W2+W5, W13 | running | - |
| website W2 35ec72c0 | agent-a55d2bb79742406c8 | 634929306f |
| website W5 34398e26 | agent-a919de92f47b9b8c0 | b81cbf4a43 |
| website W4 83842948 | agent-aac6a997ad1a616f1 | c69b28b08a, 9171872cb9 |
| enterprise N1/N3 | agent-ad01491f3840ac926 | account bae8eab; console files staged, need gen-docs then commit (msg /tmp/m/n13-msg.txt) |

## Edits outside every writer's Owns

1. .ci/rediacc_ci/well_known.py: drop EDGE_ORIGIN and PROXY_EDGE_{EU,US,ASIA}_HOST; add `PRODUCT_DOMAIN: str = _get("WK_PRODUCT_DOMAIN")` after APEX_DOMAIN (W5 writer owns it; confirm in its report).
2. region_consistency_offline.py:125 `local_push.profile_name(self.region)`, delete PUSHER_CHANNEL (:45); DERIVED_NAMES drops BACKUP_BUCKET_STABLE/EDGE; region_consistency_controls.py profile plants (:105, :202-227) to account-secrets-<region>.
3. release/local.py ~884: drop `"--target", "edge"` from the account-secrets step; block_unasked_release.py and its test (:625-647) use --target.
4. portal_captcha.py:196, deploy_account.py:112,121, test_ops_portal_captcha.py:130,153, .claude/skills/deploy/SKILL.md:70: account-secrets-<region>.
5. backup_credential_isolation.py: drop edge from PROFILE_CENSUS, ENVS, SLUGS, EDGE_IF, :390 edgeBackupR2; then delete backup-push-edge profile and _EDGE backup names from secret-supply.json; cf-r2-backup-edge out of private/account/src/types/rotation-manifest.ts:393.
6. packages/shared/src/regions/index.ts: drop edgeDomain from RegionInfo and the map (shared build TS2345); workers/ops-health/src/targets.ts:181 (W13 may cover).
7. private/account/web/src/pages/Subscription.tsx: drop isEdge (:102, :284, :315, :390 block, :401, :614); its test subscription-free-license-card.test.tsx (:13, :26, :82, :123); initial-subscription.ts can drop the _environment parameters; edgeBadge keys unused in web locales.
8. private/account tests reading deleted edge tomls: cron-wiring.test.ts:30-32, observability-export-wiring.test.ts:21-23,37-39,64, executor-mode-wiring.test.ts:35-37, config-blob-migration.test.ts:95-107,136; private/account/wrangler.toml comment.
9. probe-s3-delete-semantics.ts done by W8; backup_cutover_preflight.py:167 and start_backup_plane.py:249 to is_production_bucket (W5 writer owns; confirm).
10. test_deploy_deploy_proxy.py:1486-1501 inversion (W5 writer owns; confirm); deploy_proxy.py:22 comment.
11. dev Worker names in wrangler.dev.toml unchanged; proxy_wrangler_dev_e2e.py:88,99,700 and test_ops_service_bindings_audit.py:110 hardcode them (decide: keep).
12. packages/www/vitest.config.ts include `src/**/__tests__/**/*.test.{ts,tsx}`; public/styles/main.css rules .region-picker-countdown/.region-picker-actions/.region-picker-lookup (+ .form-label, .form-error, .btn--ghost exist?).
13. www: pricing edgeChannel keys in en.json + 12 locales and .edge-channel-* CSS (pricing-page.css:621-650) are dead; W2 files' WK_EDGE_ORIGIN uses are fixed in W2's commit (verify).
14. docs: cloudflare-spend.md:72 PROTECTED_PATTERNS, account docs/secrets/rotation.md:117-118, workflow-name sweep after W13; observability docs follow the Alloy config.
15. Proxy ENVIRONMENT now "edge" for shared proxies (W3/W4 decision, picks the CLI update channel).

## Regenerate, after the picks and edits

- `npx tsx scripts/gen/gen-docs.ts --write`
- `npm run i18n:generate-hashes`; `npx tsx packages/www/scripts/generate-client-i18n.ts`
- search index (`check:ci-search-index` names its generator)
- cli contract if shared schemas moved; `check:ci-python-env-registry -- --write-baseline --allow-new .ci/rediacc_ci/ops/r2_bucket_copy.py:CLOUDFLARE_R2_ENDPOINT`
- `cd packages/shared && npm run build`

## Live steps the batch needs

- Create queues backup-replicate-{eu,us,asia,bench} and their -dlq (8).
- L4: mint an R2 backup pair scoped to backups-<r> and rebind it.
- Then W11 (tests and retired terms, byte-identical transform proof).
