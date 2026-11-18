## SESSION d778be9d 2026-11-18T02:59:45Z

# STATE d778be9d (1104-1, PR #605)

## Next action
1. When ci:quick brulq44rm ends: read `grep -E '^ci:quick: (RED|GREEN)' .ci/cache/pause/d778be9d/ciquick-23.log`. Only check:ci-ops-health may be red (carried in .ci/config/carried-reds.json). Fix any other red (writer in a lease, then land).
2. Green: `worklist.py --review-commit d778be9d`; if the receipt tree moved, rerun ci:quick (record-only commits re-run only readers). Then `npm run vm:check -- --changed` (account phase needed for the release), then push: `TURBO_PUSH_REASON='red-fix: PR #605 reds fixed on the branch' git push origin 1104-1` (push private/account and private/renet first if the guard names them).
3. After the push: land lease commit 3b5e8f1619 (review-mark matcher fix, agent-ab968b4b663b066e1), then `worklist.py --review-mark d778be9d 61111ad2.2 fixed <deb42fb9 landed sha 254cc18e or deb42fb9a0> --test .ci/rediacc_ci/tests/gates/test_gate_plan_folders.py`; land the W2.2 re-trace writer's commits when it reports.
4. Release: `REDIACC_TRANSCRIPT_PATH=<this transcript> RELEASE_ASKED=ASKED:2026-11-17T03:32Z npm run release:local -- --channel edge --workers-only --branch-release --regions eu,us,asia --dry-run`, then the real run; then `bws_env exec --profile root-grants -- python3 -m rediacc_ci.ops.root_grants --apply --target edge-eu|edge-us|edge-asia` (#cd796a07).
5. `./rdc.sh ops up` when the host is free, check `./rdc.sh --config eu-bench machine health l1vm`, then drop the ops-health carry (#0e8e0e55).
6. Live runners after the release: bench (#400ae5ea #719d19c6 #864b6bca #edac9b6d), hostinger (#36ffb824 #6d5593e9 #3fb4edcc), A1a 695c3218 preview (#ab9c68b1).

## Delegated
- brulq44rm (shell): ci:quick-23 on head 5cd87bed; accept: only ops-health red.
- a9b3fe3924c2f83b2 (writer, lease): #f0da7369 W2.2 782a0661 re-trace, owns scripts/ci-runner/manifest*, gates.lock.json, doc-registry.md; niced; accept: whole-tree count <=80 or committed partial with reasons, path-trace and run.ts selftests rc 0.
- agent-ab968b4b663b066e1 (finished lease): 3b5e8f1619 ready to land after the push.

## Big pieces
- PR #605 push, then edge release eu,us,asia and edge root grants.

## Owed ticks
- PLAN-ciquick-cpu 51ceeb4f, 824b964d live-owed; W2.2 782a0661 with the re-trace. PLAN-enterprise-isolation a8892e0c live-owed.

## Parked
- none (l1vm default executed; re-key tracked #0e8e0e55).
