## SESSION d778be9d 2026-10-28T06:11:56Z

# STATE d778be9d (1023-1), 2026-10-28T06:30Z

Branch 1023-1 unpushed, no PR yet; turbo on, writer_cap 15. Commit by path, PR-TASK 9f92c43e, writers never commit, submodules first then pointer.

## Big pieces
- PLAN-tested-on-bench: V1 ba86b0dec, V3 0e5d2c31e, V4 5c1c9ab2a+fc6c2cebb; V2 code efed615f0, box open until vm:check VERIFIED; V5-V10 next (V10 ledger integrity added).
- PLAN-per-flavor-renet-binary-paths: promoted 5e7a31f04 (finding #950036d0); P1-P8 after vm:check.
- PLAN-executor-durable-object-policy: code boxes ticked; oom-heavy 4ab1a0517; live L0-L7 next.
- PLAN-proxy-cd-six-targets + multi-org: edge eu/asia E1 rc=0; edge-us org B SYN never reaches hostinger (placement hypothesis).
- PLAN-backup-program: N4 superseded by N4b (open); rest ops-VM/hostinger/post-merge.

## Landed this context
- spend-guard T5 (3d4a25e3a), T2 superseded by T2b, T2b ticked (account bda6641, b36dce16d).
- review backlog 109 -> 55 open: c7233ce09, 2ec734dea, c27ca1ebe (account 6422de7, elite fb856fe).
- proxy wrangler-dev e2e rc=0 after a docker restart restored docker0.

## Delegated / running
- vm:check bg bnba282xs (#ddada06a): the V2 proof; A2.3 ok this run. No ./rdc.sh beside it.

## Next action
1. Settle the remaining agent-doc review findings now (commit the plan text fixes and this STATE), then the cli (6), renet (1) and vm_check (1) findings once vm:check ends.
2. On vm:check VERIFIED: tick V2 (sig 2e5d99e8); on NOT_VERIFIED read the failing row.
3. PLAN-per-flavor-renet-binary-paths: P1 (renet build.sh, submodule commit then pointer) alone, then P2-P7 writers with disjoint Owns, P8 vm:check under a plain ./rdc.sh loop (#efd16d49).
4. edge-us: provision org C (new DO id) and run 27-90 as C (#0579bfae).
5. tested-on-bench V5 after V2+V4 (owns_surfaces helper first, #fab8e4e7), then V6, V7 census, V10. Ticks: --plan-investigate then --plan-tick; pointers are console commits or file:line, never submodule shas.
6. Then ci:quick, backup push (TURBO_PUSH_REASON backup), PR with Operational-Reason, babysit.
- Deferred #5a45d485 (stable probe login; DEFAULT yes for probe orgs, only when ML5 runs under RELEASE_ASKED).
