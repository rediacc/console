## SESSION d778be9d 2026-10-29T08:04:35Z

# STATE d778be9d (2026-10-29 ~08:05Z), branch 1023-1, unpushed

## Big pieces
- PLAN-backup-program: hostinger to R2 at 100 Mbps. Q5-Q7, Q9, demo-heartbeat done; R2 rediacc-backups-eu 1530 objects / 6.40 GB = backup usage.
- PLAN-production-key-only (promoted #32, b333f6454): K1-K5 writing.
- PLAN-org-executor-connect-timeout-relocate: E9 rerun with the probe (5bce4385a).

## Facts to keep
- Every ./rdc.sh against eu-remote runs under `bws_env exec --profile deploy-proxy` until K3/K4 land, or renet is rebuilt with the DEV key (prod key fingerprint by sha256 56721e1a; licence id fb37f1ae16f8b7c0).
- stable EU account fdb7d553 -> ce7596d0 (prev a1476077). Bandwidth cap fixed: renet 985f4c7/9f559ae/e44441a/6bfd187, CLI 2bc0ae0a3/1c1d16d8a/0dc9406a3/1aa703549.
- Region gate 581206c7b; bench legacy secrets archived+deleted (317baa02b).

## Delegated
- afc71e7f084a62df5 #863660ef: real-R2 restore on a fork of demo-heartbeat, then repos one by one at 100Mbps (never hermes), records in PLAN-backup-program live lines. Accept: per-repo rc/bytes/rate/load + R2 count.
- af001bc0771a80a28 #9345ff86 K1 (worktree, /tmp/pko-k1.diff); afca779a3b51f72c8 #01f7a601 K2 (/tmp/pko-k2.diff); a42da48975b57eba5 #0ca3d823 K3 (/tmp/pko-k3.diff); a3c38bcf36f5f3d18 #3d8a94ca K4 (/tmp/pko-k4-console.diff, -renet.diff). Accept: each box's tests rc 0 on the main tree after patch.
- K5 docs done in place (#39de9f5d), commit with K1-K4 after `check_prose_style.py check --drain`.

## Next action
1. As each K diff lands: apply only after the cutover agent's rdc.sh runs end (they touch bws_env/local_common/build.sh), rerun the box tests, commit (renet first, then pointer), tick the box with the tool's own sig.
2. Then L1 bws park (six *_DEV -> __*), K6 gate + map refresh.
3. Cutover: after the one-by-one seed, set nightly-hot bandwidthLimit 100Mbps, bind (Q10), Q11 at 100Mbps; rewrite Q11 text with measured rates (about 10 MB/s).
4. S6 #53b05748 fires 2026-10-31T07:07Z.
