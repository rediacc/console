# Review drain (#5da4f55e), phase-1 results (complete for all record prefixes)

Phase 1 triages open per-commit review findings on 1023-1 by record sha prefix; phase 2 fixes the needs-fix lines below with writers grouped by file (lead commits, then `--review-mark <id> fixed <sha>`).

## Records 0-3 (agent a2ccdee7e56e799a0): 3 fixed elsewhere, 59 not-a-bug, 52 needs fix, 3 undecided

Needs fix, console:
- ci_workflow_invariants.py: 0dff0e7c.1 (:1701 same-line pipefail), 0dff0e7c.2 (:1535 here-string), 0dff0e7c.3 (:1937 analyse_dispatch raise)
- drills/vm_check.py: 0c001709.1, 0c001709.3, 0c001709.4 (V1.2 NOT_VISIBLE, test helper, bounded SFTP_DENIAL)
- deploy/deploy_proxy.py: 2f2fd3ad.1 (top-level key allowlist, account_id), 2f2fd3ad.2 (services names)
- quality/proxy_image_smoke.py: 3182e020.1 (SIGTERM test), 3182e020.2 (ignore second SIGTERM)
- quality/proxy_wrangler_dev_e2e.py + workers/proxy/wrangler.dev.toml: 3c5f450a.1, .3, .4, .6
- .github/workflows/ci-build-renet.yml:529 04da9474.1 (!cancelled()); .ci/docker/web/Dockerfile:42 343e21c7.1; .devcontainer/Dockerfile:670 + ci-quality.yml:1816 343e21c7.2 (agent-browser pins)
- packages/cli: 0b78361a.2 (converge.ts:164 CliExitError), 0b78361a.3 (cli.json:643 --policy always), 276c1edc.1 (restore without --as test), 276c1edc.2 (unused _source), 17c55af8.1 (proxy-token test argv), 3431ed6e.1 (survivors ENOENT only), 3bc245d0.1, 3bc245d0.2 (remote-parents.ts probe throw, '..')
- packages/www: 04847f53.1, 04847f53.2 (ffmpeg-video.ts stale png, test), 093711b4.1 (config-storage.md:91), 38c05385.1, 38c05385.2 (cast-patterns.js)
- docs/DESIGN-CONFIG-STORAGE.md: 093711b4.2 (:976), 093711b4.3 (:435)
- hooks: 0a5aafab.2 (wl_plandeps.py:93 comment), 2d4c5df5.1 (wl_planconc.py:645 live_plans)
- plans: 0ecf4d60.1, 0ecf4d60.2, 3d8f323e.1 (PLAN-plan-preflight PF5/PF6/item 4), 0fcbb8c5.2, 0fcbb8c5.3 (PLAN-sync-remote-file-ownership T2/T3 evidence), 1f109103.1 (PLAN-agent-tree-lifecycle Depends-On)

Needs fix, private/renet: 031d303c.3 and 3c3e1f59.1 (policy.go:696 NamesDaemonSocket per-network socket names and whole-variable sources), 3c3e1f59.2 (resolverRunDirs test), 3c3e1f59.3 (DOCKERD_SANDBOX.md:136), 14b63a4a.1 (etcReadOnlyView symlink escape), 230dea55.1 (kube_join.go:87 comment)

Needs fix, private/account: 10f0fc6a.1, .5 (rate-limit.ts doc placement), 10f0fc6a.4 (request.ts getClientIp doc), 10f0fc6a.6 (ip-binding test assertion), 2cf33743.1 (usePickerOptions marker)

Needs fix (reopened from not-a-bug): 031d303c.4 NET_ADMIN with host network lets a container alter host netfilter; re-open with a fix (refuse NET_ADMIN when the network mode is host) or a written risk acceptance.

Undecided: 0c001709.2 (waits on a live sftp run to confirm whether the "couldn't" alternative of the SFTP_DENIAL pattern also matches local-file errors), 385cae47.1 and 3ff6cae1.1 (plan ticks before a post-merge outcome).

## Records 8-b (agent a690d5422a578f1f6): 8 fixed elsewhere, 46 not-a-bug, 53 needs fix, 1 undecided (8d692e44.1 shard table vs ci-quality.yml:1389)

Needs fix, console:
- hooks: 81765f94.1 (wl_planrec.py:1999 _PREFLIGHT_ERRORS), 81765f94.2 (worklist_messages.py:2794 plan-boxes in printed commit), 81765f94.3 (pr-merge.md:344 and pr-babysit.md:118 preflight subject), 8b10b204.1 (wl_bgsweep.py:405 long_work), 8b10b204.4 (wl_bgsweep.py:276 _BODY_OK redirect), 87264541.3, .4, .5 (runningscript.py cwd None test, target required, expanduser), a2e29702.2 (block_commit_of_live_writer_file.py:238 nested-repo ancestor)
- .ci drills/deploy/core/tests: 93157dbc.1, .3, .4 (drills/lib.py account stop checks + tests), 930f0082.2 (observability_volume.py:395), a392e3ee.1, .2, .3 (test_gate_watchdog_budget.py), accb48d9.1-.8 (upgrade_converge.py and vm_check.py --only, teardown, 0600, json, test-only helpers), b4c1a83b.1, .2 (drills/license.py), b506cc5c.1, .2 (core/account.py doc, test wait), b7d7bdfe.1, .2, .3 (deploy_proxy.py isfinite, DoH log, unused import)
- other: 82a27dd6.3 (workers/proxy wrangler.toml deploy order comment), 8b10b204.2 (.ci/bootstrap.sh:461), 8d692e44.2 (check-gate-mutations.ts:17), b8fa5ef7.1, .2 (cli backup.ts ownStreamOf), bd376292.1, .2, .3 (loopback.test.ts, repo-output-parity.test.ts)

Needs fix, private/account: 95fe3003.1, .2, .3 (rotation rotate.ts recovery text), 9fb73f07.1, .2 (request.ts markServiceBindingEnv, ip-binding test), bfb48c99.1 (proxy-cli-token 429 test)

Needs fix, private/renet: 83482aba.1, .2 (dockerproxy admit wording, DOCKERD_SANDBOX.md:185), 8572c230.1, .2, .5 (setup_command.go CRIU OBS probe), 862270d5.1 (collabora control asserts MKNOD), 86a60ad0.2 (exec_sessions.go wording), 8e0f5798.1 (policy_test.go split), 985b4c06.1 (hostconfig_test.go policyReadHostConfigFields any HostConfig param)

## Records 4-7 (agent ad249592b7caf44e5): 5 fixed elsewhere, 72 not-a-bug, 65 needs fix, 2 undecided (4a685cd8.3 deadcode allowlist, 4c48edcb.2 inode reuse)

Needs fix, console: bws_env.py 42112172.1 (load([]) lists the whole map, real bug); telemetry_delivery.py 65bfe8b4.1-.3; cf_notifications.py + test 5c376038.1-.3; ci_workflow_invariants.py + test 6e99b67e.2, .3; test_drills_vm_check_trigger.py 470cafcf.1, .2; test_core_account.py 70ac084b.1-.3; check_plan_citations.py 74f38613.1, .2; wl_roster.py 43119d35.2, .3, 4a39d8be.1; wl_review.py 79cf9eed.1, .2; wl_prreview.py + test 79cf9eed.3, .6; wl_planconc/wl_planorder tests 483392a8.2, .3; test_catalog_template_policy.py 7bf4900c.1-.3; check-e2e-skip-hygiene.ts 4754890b.2-.5; packages/cli 47a277ef.1-.3 (telemetry-disabled container serve), 59a7c2d6.1; packages/e2e-tests 6d882060.1, 7eb8b114.1-.3; packages/www translations 4b1dcc90.1-.3, 7a4e982a.1 (12 locales + search index); docs/observability 5c9faef8.1-.4; plans 49a2b0f2.1, 4b9703f4.1
Needs fix, private/renet: manager.go 4c48edcb.1; policy.go 55462194.3, .4; dockergrant/grant.go 54244f1a.1, .4; daemon_dockerproxy_exec.go 54244f1a.2, .5; daemon_grant.go 54244f1a.3; root_errors_test.go 766799c0.3; runtime_converge(_test).go 7ab695c0.2, .4; router driver_test 50cf10a0.1; mount_sandbox_linux.go 61d01f10.2; systemd_test.go 766799c0.2
Needs fix, private/account: cloudflare.ts:96 7e94701b.1; plus an uncovered cleanup: rotate.ts and deactivate.ts docstrings say secrets.env where the code uses observability/.env (no review id covers it; phase 2 fixes it without a `--review-mark`)

## Records c-f (agent ae6970a1d7a80141f): 4 fixed elsewhere, about 95 not-a-bug, 69 needs fix, 0 undecided

Needs fix, console: drills/converge_preflight.py de355ba7.1-.3 (U2.5 denial text, report parser, whole-token match); ops/r2_lifecycle.py d945e387.2; ops/cf_usage_report.py d945e387.3; wl_planpreflight.py d74ca431.1; check-backup-protocol-conformance.ts d22373e7.2; cli renet-execution.ts d64e28ca.1, eb0dd0e0.1, .2; housekeeping/cf_leftovers.py ce7bd2c4.1-.4; plans c0364b61.1-.3, cc581e80.3, e53e0fcd.1-.3, f68c4aa8.1, .2, f170830a.1, .2 (RC ebpf accept and DR pytest evidence); block_roundlog_truncate.py cc262a7c.1; scripts/lib/pins ran-line.ts e57fde7e.1-.4; docs/design e6b725bf.1, .2; packages/www translations e920872b.1-.3 (12 locales); plan-investigation ledger ecbb046f.1-.3; check-account-no-node-env-routes.ts f7ab147f.2; shadow-gate.ts f7ab147f.1; drills/tenant_isolation.py f791208c.1; core/devbox.py pin f72b3c0f.1; wl_ruling.py f8840f98.1; obs-ceph-autobump.yml f8d18480.3; wrangler.eu.toml fa7742a0.1, .3
Needs fix, private/account: docs/runtime/environment.md c185e931.3; routes/proxy.ts c185e931.4; backup-gc.service.ts c8bdea60.1 (missing manifest object stalls prune); rotation check.ts/credentials.ts ca11f82b.1, .2; env.ts efed7589.4
Needs fix, private/renet: pkg/prune + repo_cgroups cb23ce4c.1-.3; dockerproxy/proxy.go cef804ea.3 (Accept loop exits on transient errors, real); DOCKERD_SANDBOX.md e73fde84.2; datastore README e73fde84.3; chunkstore uploader.go eabae1be.2 (crash after commit resumes under a refused id, real); ops_selftest.go ef2503c5.1; compose exec_scratch_unix.go f1cd6664.1; certexport discover.go fb99c9cd.2 (stopped repos invisible to the ownership check, security, priority), cert_export.go fb99c9cd.3

Already done in this session: f7ab147f.3 (three gates were vacuous, fixed 07e56c446), fb99c9cd.1 (main.go registration, 1454b8c).

## Phase 2

Writers take disjoint groups: (1) private/renet, (2) private/account, (3) console .ci + scripts + hooks, (4) console packages + docs + plans + translations; the lead commits each group and marks findings fixed with the sha.

## Complexity and who designs/implements (open work, 2026-10-24 ~19:30Z)
- Converge P3/P1/P4/P5 (#3eabcddc): complicated; designed by the plan file (written by an Opus plan writer), implemented by Opus writer a5a99906e77033f93.
- Renet i18n wrap of 80 strings (#ded06481): simple, mechanical; Sonnet writer afcff9126e0c7fbb6 stages keys, lead merges the catalogs after #3eabcddc.
- Review drain phase 2 groups 1-4 (#6dd33cfe, #e0c35276, #3c24567c, #ff383059): mostly simple, finding-by-finding; designed by phase-1 triage, implemented by Sonnet writers a3b4a86d855d9dfbe, ade294ad83feaac48, a7a5a0a2f4018d6be, a5d613445bb088382. Complicated ones (fb99c9cd.2 cert-export stopped repos, eabae1be.2 uploader crash resume, cef804ea.3 Accept loop, 031d303c.4 NET_ADMIN with host network) get an Opus Plan agent before any fix if the group writer reports them deferred.
- V1 then H1-H5 (#0787c7df, #d0928775): sequential operations, lead runs them (operator ruling ASKED:2026-10-24T19:40Z).
