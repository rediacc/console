# Cloudflare inventory findings (2026-11-26 ~09:40Z, read-only)

Live listing: profile cf-usage-report (read token), full JSON under /tmp/cf-inventory/. Not listable with that token: account API tokens (403 9109), Hyperdrive, Vectorize, AI Gateway (403 10000), R2 fedramp; R2 eu listing capped at 20 (GraphQL shows more).

| Type | Total | Declared or permanent | Leftover |
|---|---|---|---|
| Workers | 55 | 18 (account/proxy eu-us-asia, signer x3, www, mta-sts-policy, ops-health, bench set) | 36 account-/proxy-proof-* (18 labels, 11-15/16, no domain); 2 acme (enterprise) |
| Container apps | 23 | 6 (proxy-* and proxy-bench-* orgexecutor) | 16 proxy-proof-*-orgexecutor (bill continuously); 1 acme |
| DO namespaces | 20 | 19 | 1 proxy-proof-proxy-a_ExecutorCapacity |
| R2 buckets | 38+ visible | ~15 (backups/configs per region and bench, media, releases, rediacc-public-data) | 27 eu + 4 default proof-* (mostly empty); acme 2; rediacc-backups-probe; legacy? rediacc-backups-eu (450.7 GB), rediacc-configs-eu, edge-rediacc-configs-eu; rediacc-www-media (8.4 GB, looks like a copy of media) |
| D1 | 35 | 15 | 15 account-proof-*; 3 *-bench-*-j (11-23, 12 KB); acme |
| Queues | 46 | 12 | 34 proof-* backup-replicate (+dlq); acme 2 |
| KV | 2 | enterprise-lookup | pr-605-enterprise-lookup (PR closed) |
| Turnstile | 2 | both | - |
| DNS rediacc.io | 122 | - | test names (*.leak-attacker/leak-victim/cleanup-test.hostinger), maybe hermes/demo-* |

Existing tooling: housekeeping/cf_leftovers.py (nightly 03:00 report only, name-in-wrangler/regions.json test, no reason or deadline, masks company names, no KV/AE/versions/DNS/tokens); cleanup_versions.py (nightly reaper: pr-/pv- Workers, account-pr-* D1, rediacc-console-pr-* Turnstile, releases-bucket R2 prefixes); ops-cleanup-preview.yml and ops-cleanup-r2-staging.yml (PR close; wrangler delete failures swallowed with || true); cf_retire.py (manual, rename retired set, keeps proof-loss and rediacc-public-data); cleanup_stale_d1.py (migration-test-* D1); breakpoint reaper (tunnels, Access apps). No declared inventory, no deadlines, no gate comparing the account to a declaration. Enterprise proofs (./run.sh enterprise proof, lab.ensure_company) have no removal path in CI (lifecycle.remove refuses under GITHUB_ACTIONS). Enterprise names must not appear in tracked files (enterprise_leak.py). Signer Workers are rendered from a template into a gitignored dir, so cf_leftovers likely reports them as leftovers. Gate patterns available: local-only live gate with exit 77 when no token (bws_map_live), nightly live step (region_consistency --live), carried reds with per-finding keys.

## Old buckets (investigation 2026-11-26 ~10:05Z, read-only; recommendation per bucket, nothing deleted)
- rediacc-configs-eu (53 objects): fully covered by configs-eu (verified copy, plan L8 2026-11-10): delete, optional small archive first.
- edge-rediacc-configs-eu (54 objects, last write 10-28): edge-tenant blobs for the 9 edge users whose D1 is being archived (rename plan L11): archive, then delete.
- rediacc-www-media (8,422 objects): fully covered by media (0 keys only in www-media); a cf_retire delete on 11-13 stopped on an HTTP 429: delete (re-run cf_retire with backoff).
- rediacc-backups-eu (450.7 GB, hostinger only, last write 11-11): holds pre-11-10 restore points; keep until rename plan L10 (verify, restore test, nightly on backups-eu) is ticked, then delete (L11).
