# PLAN: a stopped bench signer keeps its caller's binding, and the signer proofs never leave bench signing down
Status: executing
Owner: d778be9d
Updated: 2026-11-12
Priority: P1 -- each run of `enterprise proof signer --bench` (V1) or region-loss (V2) leaves bench signing down (SIGNER_UNAVAILABLE) until a full deploy_bench, measured 2026-11-12
Depends-On: no-dep -- builds on landed code
Concurrency: parallel -- disjoint from every other plan except PLAN-enterprise-isolation.md (executing), which also owns deploy_signer.py and proof.py; one writer takes both files
Owns: agent/plans/PLAN-signer-bench-stop-binding-reattach.md, .ci/rediacc_ci/deploy/deploy_signer.py, .ci/rediacc_ci/enterprise/proof.py, .ci/rediacc_ci/tests/test_deploy_signer_lab.py, .ci/rediacc_ci/tests/test_enterprise_proof.py
Live-Proof: bench -- `./run.sh enterprise proof signer --bench`, then `region-loss --bench`, each rc 0, then account-smoke shows account-bench still issuing
First-Seen: 2026-11-12

## Context
- `stop_signer` deletes the signer Worker (`.ci/rediacc_ci/deploy/deploy_signer.py`, `wrangler delete --name <signer> --force`) and `start_signer` runs `deploy` again, recreating a Worker of the same name. account-bench's LICENSE_SIGNER binding does not reattach to it: only deploy_bench, which redeploys account-bench, restores signing (three live runs on 2026-11-12, each followed by a deploy_bench).
- `cut_region`/`restore_region` go through the same stop and start, so V2 carries the same defect.
- `verb_signer` (`.ci/rediacc_ci/enterprise/proof.py`) judges the stopped and restarted states on one call each, so a call made while Cloudflare still propagates is misjudged: right after the delete, "a stopped signer is named" read `admitted`.
- A signer without its private key already refuses with the named code: `signingKey` rejects `SIGNER_KEY_UNSET` (workers/signer/src/index.ts:49), `guarded` turns it into SIGNER_UNAVAILABLE (workers/signer/src/index.ts:86-95), and the caller maps any failed RPC to SIGNER_UNAVAILABLE (private/account/src/services/signer-client.ts:97).

## Design
Stop by deleting the key secret, settle each judged state with bounded polling, and restore signing in a finally that checks it.
- Stop = `wrangler secret delete ACCOUNT_ED25519_PRIVATE_KEY --name <signer>` with "y\n" on stdin (.ci/rediacc_ci/ops/deploy_bench.py:819-824), then a `secret_names(signer)` read-back that must no longer list the key, or LabError. The Worker and its binding stay. Start = the existing `deploy`, which pushes both keys with `secret bulk` and confirms both names. The precondition that every name the redeploy needs is bound stays. No Worker change.
- Rejected: redeploying every caller in start_signer. deploy_bench has no narrow caller redeploy (its `_deploy` builds the portal, migrates, rotates and pushes secrets), a bare `wrangler deploy` would ship the local checkout over whatever bench runs, and it keeps the delete that breaks the binding.
- `settle(probe, done, *, timeout=SETTLE_S=90, interval=5)` in proof.py retries until `done(answer)` and returns the last answer; its sleep and clock are module seams. The stopped claim waits for SIGNER_UNAVAILABLE; "current licence works" is read once the stop has settled.
- `_restore(lab, p, signer, caller)` runs in the finally of verb_signer and verb_region_loss: start_signer, settle until issuance is admitted, one more start_signer and settle on failure; the claim "<caller>: bench signing is restored" then holds or breaks, a broken one naming `deploy_signer --target bench-<r>`. It replaces the issues-after-restart and renews-after-restore single calls.

## Tasks
- [ ] F1 [writer] deploy_signer: stop_signer deletes the private-key secret instead of the Worker, `_wrangler` takes `stdin`, a read-back still listing the key raises LabError; the module and stop_signer docstrings say so.
  Owns: .ci/rediacc_ci/deploy/deploy_signer.py, .ci/rediacc_ci/tests/test_deploy_signer_lab.py
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_deploy_signer_lab.py -q` rc 0. The stop test asserts the argv `secret delete ACCOUNT_ED25519_PRIVATE_KEY --name signer-bench-eu` with stdin "y\n" and that no call carries `--force` or `delete --name` (fires with the old argv planted back); a FakeRun whose secret list still names the key fires LabError "still holds". Control: the precondition, non-bench refusal and start_signer tests pass unchanged.
- [ ] F2 [writer] proof: the `settle` helper, settled stop and restart claims, and `_restore` in both finally blocks.
  Owns: .ci/rediacc_ci/enterprise/proof.py, .ci/rediacc_ci/tests/test_enterprise_proof.py
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_enterprise_proof.py -q` rc 0. FakeLab gains `lag` (issue calls still answering the old state after a stop or start) and `restart_breaks` (start leaves the signer refusing): lag=3 passes rc 0 for signer and region-loss while planted single-shot judging fires; restart_breaks gives rc 1 with "bench signing is restored" broken, naming `deploy_signer --target`, and start_signer called twice; lag beyond SETTLE_S breaks the stopped claim naming the 90 s wait. Control: a clean FakeLab passes rc 0 and the existing tests stay green. No test sleeps.
- [ ] LP-bench [live] Under the deploy-bench, deploy-workers and deploy-signer profiles, `./run.sh enterprise proof signer --bench` then `region-loss --bench`, each rc 0 with no deploy_bench between them, then the receipt.
  Accept: live-proof bench account-smoke
