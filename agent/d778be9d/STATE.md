## SESSION d778be9d 2026-11-09T08:44:55Z

Branch 1104-1, nothing pushed. First ci:quick (G7 operator go, 2026-11-09) ended rc 1 with 35 reds; all drained by lease writers and landed. CB1-CB6 of plan-compaction-bindings ticked (CB4/CB5 9ea58bd900); bindings gate rc 0. Enterprise N4 D1 D2 A2 ticked; C2 verbs landed 50a40f8370 (partial). Review backlog #5bcea441 split into slices under /tmp/review-backlog; verdicts saved in /tmp/review-backlog/verdicts/{agent,ci-b}.txt, review-mark pass still owed for them and for the hooks/docs slice (37 VERDICT lines in its report). Operator rulings 2026-11-09 (AskUserQuestion): idle-writer fix = ceiling fix + IDLE CAPACITY block, block naming boxes (no auto-spawn), [writer]-tagged boxes only, per-box Depends-on when stated.

## Big pieces
PLAN-enterprise-isolation (S2 C1 C2 K2 writers live), PLAN-website-routing-and-mail (live runner), PLAN-product-domain-rename (all live boxes wait on a VERIFIED vm:check), PLAN-idle-writer-capacity (being written and built).

## Delegated
- a8e078f3534a83f2d #ab943efa website live runner (adds redirect test; uncommitted edits in apply_cf_redirect_rules.py, its test, the website plan).
- a685271cff7685843 #623937fa S2 signer (lease). ac8bf5f3257a7343e #f5dae46d C1 + lab.py + control_db.py (lease). a316129993a8aa9a6 #872e789f K2 ring runner (lease). a46ff53d3cac141b1 #827e8676 C2 live adapters (lease).
- ad0edc32f2b2c76c0 #6f93ebee product backlog, afd2abf4d6c7718f4 #00244be0 ci-a backlog (leases).
- a63ff2fa63b1dcd83 #52a36392 idle-writer-capacity plan + hook code (main checkout, no commit).

## Owed ticks
CB7 9cd30874 move half (needs a terminal bound plan); C2 2706988f after adapters; enterprise C1/S2/K2 after landing.

## Next action
1. When the website runner reports: commit its plan lines, the redirect fix and test, then land /tmp/cibpicks-rest.txt (8 CI-b picks from b702260890) one by one, then commit the C1 note in PLAN-enterprise-isolation.md (uncommitted) with the plan renders.
2. Land each lease writer as it reports (./run.sh worktree land <id>, cherry-pick -x one by one), rerun its accept, tick with the landed sha, gc the tree.
3. Review-mark every VERDICT line in /tmp/review-backlog/verdicts/*.txt (fixed needs the landed sha), then worklist.py --review-commit.
4. Then #caa837d4: second ci:quick, ops up --basic, vm:check fleet run 17, one push (submodules first), PRs.
