# Review drain (#5da4f55e), phase-1 results

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

Reconsider (marked not-a-bug, likely real): 031d303c.4 NET_ADMIN with host network lets a container alter host netfilter; re-open with a fix (refuse NET_ADMIN when the network mode is host) or a written risk acceptance.

Undecided: 0c001709.2 (SFTP_DENIAL couldn't alternative, needs a live sftp run), 385cae47.1 and 3ff6cae1.1 (plan ticks before a post-merge outcome).

## Records 8-b (agent a690d5422a578f1f6): 8 fixed elsewhere, 46 not-a-bug, 53 needs fix, 1 undecided (8d692e44.1 shard table vs ci-quality.yml:1389)

Needs fix, console:
- hooks: 81765f94.1 (wl_planrec.py:1999 _PREFLIGHT_ERRORS), 81765f94.2 (worklist_messages.py:2794 plan-boxes in printed commit), 81765f94.3 (pr-merge.md:344 and pr-babysit.md:118 preflight subject), 8b10b204.1 (wl_bgsweep.py:405 long_work), 8b10b204.4 (wl_bgsweep.py:276 _BODY_OK redirect), 87264541.3, .4, .5 (runningscript.py cwd None test, target required, expanduser), a2e29702.2 (block_commit_of_live_writer_file.py:238 nested-repo ancestor)
- .ci drills/deploy/core/tests: 93157dbc.1, .3, .4 (drills/lib.py account stop checks + tests), 930f0082.2 (observability_volume.py:395), a392e3ee.1, .2, .3 (test_gate_watchdog_budget.py), accb48d9.1-.8 (upgrade_converge.py and vm_check.py --only, teardown, 0600, json, test-only helpers), b4c1a83b.1, .2 (drills/license.py), b506cc5c.1, .2 (core/account.py doc, test wait), b7d7bdfe.1, .2, .3 (deploy_proxy.py isfinite, DoH log, unused import)
- other: 82a27dd6.3 (workers/proxy wrangler.toml deploy order comment), 8b10b204.2 (.ci/bootstrap.sh:461), 8d692e44.2 (check-gate-mutations.ts:17), b8fa5ef7.1, .2 (cli backup.ts ownStreamOf), bd376292.1, .2, .3 (loopback.test.ts, repo-output-parity.test.ts)

Needs fix, private/account: 95fe3003.1, .2, .3 (rotation rotate.ts recovery text), 9fb73f07.1, .2 (request.ts markServiceBindingEnv, ip-binding test), bfb48c99.1 (proxy-cli-token 429 test)

Needs fix, private/renet: 83482aba.1, .2 (dockerproxy admit wording, DOCKERD_SANDBOX.md:185), 8572c230.1, .2, .5 (setup_command.go CRIU OBS probe), 862270d5.1 (collabora control asserts MKNOD), 86a60ad0.2 (exec_sessions.go wording), 8e0f5798.1 (policy_test.go split), 985b4c06.1 (hostconfig_test.go policyReadHostConfigFields any HostConfig param)

## Records 4-7, c-f: agents ad249592b7caf44e5, ae6970a1d7a80141f still running
