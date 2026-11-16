# PLAN: the tutorial recorder licenses its repositories through bench and records the real activation

Status: proposed -- converted from console#421 on 2026-11-16 (reshaped: the bypass the issue planned to remove is already gone); awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: no-dep -- PLAN-free-license.md F1 (skip switch removed) and F5 (FREE offer) are ticked, and PLAN-production-key-only.md's single licensed renet is what the bridge builds; no box here waits on their open live boxes
Priority: P2 -- every tutorial that creates or forks a repository cannot be re-recorded today, so any CLI change that touches those casts leaves them stale; the published casts still show the old bypass output
Concurrency: parallel -- the recorder files are disjoint from every live plan; the re-record box needs the ops VM fleet, so it serialises with other fleet users by the fleet lock, not by plan ownership
Owns: agent/plans/PLAN-tutorial-recorder-licence.md, .ci/media/tutorials.sh, .ci/tutorials/lib/tutorial-licence.sh, .ci/rediacc_ci/ops/tutorial_token.py (new), .ci/rediacc_ci/tests/test_ops_tutorial_token.py (new), packages/www/scripts/validate-tutorial-cast-output.js, packages/www/public/assets/tutorials/*.cast, packages/www/public/assets/tutorials/.recording-hashes, packages/www/src/data/tutorial-timeline/**, packages/www/src/data/tutorial-transcripts/**, docs/design/README.md (one line), docs/design/07-examples-and-ci.md (one line)
Live-Proof: bench -- the regenerated timelines and transcripts under packages/www/src/data are the www surface, which bench admits through the www-smoke check
Source: https://github.com/rediacc/console/issues/421

## Ask

The issue asked for tutorial casts that show the real `Activating license... / License activated (Xs)` sequence instead of the `REDIACC_SKIP_MACHINE_ACTIVATION=1` bypass. Since then the bypass was removed and renet enforces licensing in every build, so the question changed shape: the recorder now has to obtain a real licence or it cannot record any tutorial that creates or forks a repository. This plan gives the recorder a real subscription token against bench and re-records the affected casts.

## Context (checked 2026-11-16 against the tree)

1. The bypass is gone: `git grep -n REDIACC_SKIP_MACHINE_ACTIVATION -- ':!agent'` finds only the tombstone entry in `.ci/config/env-manifest.json:1456` (the `shards/tombstone` list) and two stale instructions in `docs/design/README.md:85` and `docs/design/07-examples-and-ci.md:32`, which still tell agents to set it on ops VMs. `isCommunityUsable` no longer exists. The `nolicense` build tag survives only in a drill that builds a pre-isolation renet (`.ci/rediacc_ci/drills/upgrade_converge.py:56-66`) and in a test that refuses it (`.ci/rediacc_ci/tests/test_release_renet_key_gate.py:113`).
2. The tutorial scripts expect a token: `.ci/tutorials/lib/tutorial-licence.sh:20-31` exports `REDIACC_TOKEN` from `REDIACC_TOKEN`, `TUTORIAL_ACCOUNT_TOKEN` or `E2E_ACCOUNT_API_TOKEN`, needs `REDIACC_ACCOUNT_SERVER` beside it, and only WARNS when either is missing ("Every 'rdc repo create' and 'rdc repo fork' will refuse with LICENSE_REQUIRED"). It is sourced by `.ci/tutorials/lib/tutorial-helpers.sh:47-48` and the three stage scripts.
3. The recorder passes neither. `www_tutorials_record` in `.ci/media/tutorials.sh` runs each tutorial on the bridge VM through `_bridge_ssh` with `TUTORIAL_MACHINE_*`, `TUTORIAL_BACKUP_*`, `REDIACC_ALLOW_GRAND_REPO` and `MAX_IDLE_MS` only (`:241-253`). Nothing starts an account backend, opens a tunnel or supplies a server key.
4. The bridge's renet bakes the production licence public key and refuses any other: `.ci/media/bridge.sh:120-140` builds it with `-X ...keys.ProductionPublicKey=$account_key` and runs `rediacc_ci.release.renet_key_gate`, which exits 1 for a binary without the production key.
5. Bench issues licences signed with the production key: bench's account Worker signs through `signer-bench-eu`, whose key is `ACCOUNT_ED25519_PRIVATE_KEY` (`.ci/rediacc_ci/deploy/deploy_signer.py:10`, `:51-52`). A bench licence therefore verifies under the bridge's renet with no build change.
6. A headless bench login exists: `npm run login:bench` (`.ci/rediacc_ci/ops/login_bench.py`) refreshes the bench IP allowlist (`rediacc_ci.ops.bench_access add-current`), logs the `eu-bench` config in with the operator's bench account from the Bitwarden profile, and leaves its token beside that config. Bench blocks every address outside a short WAF list except two health GETs (`.ci/rediacc_ci/ops/bench_access.py` docstring, "WHAT THE RULE BLOCKS").
7. CLI tokens bind to the IP of their first use and a refusal from another IP asks for a TOTP code to move the binding (PLAN-token-ip-rebind.md, ticked). A prompt inside a recording hangs it forever (`.claude/skills/tutorials/SKILL.md:53`), so the bridge must present the same public address the token was bound from, or the token must be first used from the bridge.
8. With no token, the CLI's licence path offers a login or a FREE licence to a human and takes FREE silently only under an agent or `--yes` (`packages/cli/src/services/executor/license-recovery.ts:364`, `isAgentEnvironment` at `packages/cli/src/utils/agent-guard.ts:34-46`). The bridge `rdc` runs under SSH with no agent ancestry, so the expected failure today is a hang at that prompt, not a clean LICENSE_REQUIRED. This is a hypothesis until R1 runs.
9. The published casts still show the bypass shape: `packages/www/public/assets/tutorials/tutorial-create-repo.cast` and `tutorial-branching.cast` print `License activated (0ms)`, last recorded in 062ce6b0a5 (2026-08-20). Fifteen tutorials under `.ci/tutorials/` create or fork a repository.
10. Re-recording changes cast timings, so timelines and transcripts regenerate (`./run.sh www tutorials extract`, `generate`, SKILL.md "The loop"); narration reuse is keyed on `textHash` plus the cached mp3 (`.claude/skills/tutorials/SKILL.md:119`), so unchanged narration needs no GPU run.

## Design

**Decision: a real bench token, not a local backend and not FREE.**
- Bench (chosen). Its licences verify under the bridge's production-key renet (Context 4, 5), it is reachable from the bridge through the host's NAT once the host's address is on the WAF list (Context 6), and the login is already headless. The production licence key never enters a local process.
- Local dev backend (rejected). Its licences would verify only if the local process held the production private key, which this tree keeps inside signer Workers (PLAN-pr-path-ephemeral-credentials.md D4 keeps bench on that key for this reason), or if the bridge renet baked a dev key, which `renet_key_gate` refuses by design (Context 4). It also needs the reverse tunnel and X25519 wiring the issue listed, none of which exists.
- FREE (rejected as the default). The cast would show the FREE warning and signup link on every create, which is the new-user path, not a subscriber's; and it needs `--yes` on every create, which changes the tutorial commands. It stays the fallback if the operator prefers casts that show the free flow (open question).

**Token handling.** `rediacc_ci.ops.tutorial_token` runs `login_bench` when the `eu-bench` token is absent or refused, then writes `REDIACC_TOKEN`, `REDIACC_ACCOUNT_SERVER` (the bench origin) and `TUTORIAL_LICENCE_REQUIRED=1` into a 0600 env file. The recorder copies it to the bridge as `/tmp/rec/.licence.env` (0600), each record command sources it (`set -a; . /tmp/rec/.licence.env; set +a`), and teardown deletes it. The token never appears on an argv, in the log or in a cast. `tutorial-licence.sh` turns its warning into an exit 1 when `TUTORIAL_LICENCE_REQUIRED=1`, so a missing token fails at the first script instead of hanging in a prompt.

**IP binding.** R2 measures the public IPv4 and IPv6 the host and the bridge present. If they match (the libvirt NAT case), the host-minted token works as is. If they differ, `tutorial_token` mints the token from the bridge instead, by running the same headless `rdc subscription login` there with the login values on stdin, so its first use is the bridge's address.

**Leak guard.** `validate-tutorial-cast-output.js` refuses a cast containing the bench origin or a value of the shape the token file holds, so a future change that echoes the env cannot publish it.

**Out of scope.** Publishing the re-rendered videos to R2 is an operator approval (media-pipeline rule); renders and publish follow under OP1. Community-tier limits the issue wanted echoed apply to the tutorial account's plan on bench, which R2 records.

## Boxes

- [ ] R1 [live] Reproduce today's failure on the fleet with one tutorial and no token: `./run.sh www tutorials record tutorial-create-repo --force`. Record whether it hangs at the login/FREE prompt (Context 8) or refuses with LICENSE_REQUIRED, quoting the cast or log line. Accept: the run's exit status and the quoted failing line in the tick evidence.
- [ ] R2 [live] From the provisioned bridge: the public IPv4 and IPv6 it presents against the host's (the address source `bench_access add-current` uses), `curl -s -o /dev/null -w '%{http_code}' <bench origin>/account/api/v1/health` from the bridge, and the `eu-bench` account's plan and machine allowance (`./rdc.sh --config eu-bench subscription status`). Accept: the three results in the tick evidence; the IP comparison picks the token branch in Design.
- [ ] W1 [writer] `rediacc_ci.ops.tutorial_token` (login on demand, the 0600 env file, the bridge-mint branch) with pytest covering: no value on any argv, the file mode, refusal when the login fails, and the bridge branch chosen when the addresses differ. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_ops_tutorial_token.py` rc 0.
- [ ] W2 [writer] Recorder wiring in `.ci/media/tutorials.sh` (copy, source, delete on teardown and on failure) and the hard failure in `tutorial-licence.sh` under `TUTORIAL_LICENCE_REQUIRED=1`. Accept: `npm run check:ci-shell-format` rc 0, `shellcheck .ci/media/tutorials.sh .ci/tutorials/lib/tutorial-licence.sh` rc 0, and `TUTORIAL_LICENCE_REQUIRED=1 bash -c '. .ci/tutorials/lib/tutorial-licence.sh'` exits 1 with no token set.
- [ ] W3 [writer] The leak guard in `validate-tutorial-cast-output.js`, with a selftest fixture holding the bench origin and one holding a token-shaped value, both refused. Accept: `npm run check:ci-tutorial-casts` rc 0.
- [ ] W4 [writer] Rewrite the two stale lines that still instruct `REDIACC_SKIP_MACHINE_ACTIVATION=1` (Context 1). Accept: `git grep -n REDIACC_SKIP_MACHINE_ACTIVATION -- ':!agent' ':!.ci/config/env-manifest.json'` prints nothing.
- [ ] R3 [live] Record `tutorial-create-repo` and `tutorial-forking` with W1-W2 in place. Accept: the record run rc 0, and each cast contains `License activated (` with a non-zero duration and neither the bench origin nor the token (W3's validator passes on them).
- [ ] R4 [live] Re-record the remaining thirteen tutorials that create or fork a repository, then `extract` and `generate`. Accept: `npm run check:ci-tutorial-casts && npm run check:ci-tutorial-parity && npm run check:ci-tutorial-caption-sync` rc 0 and `npm run validate:content-media -w packages/www` rc 0.
- [ ] OP1 [operator] Approve rendering and publishing the re-recorded tutorial videos to R2 (media-pipeline rule: no publish without explicit approval). Accept: the operator's answer quoted in the tick, then `./run.sh www tutorials video` rc 0 and the publish command's rc 0.
- [ ] LP-bench [live] Fresh bench receipt for the regenerated timelines and transcripts.
  Accept: live-proof bench www-smoke

## Risks

- The tutorials consume licence slots on the operator's bench account. R2 records the allowance before R3; if the plan's machine limit is below the two worker VMs a tutorial uses, the fix is a dedicated tutorial account on bench (open question), not a seeded test route, since bench runs without TEST_MODE.
- Bench's WAF entry for the host expires after 7 days (`bench_access` TTL); a long re-record batch that starts near expiry loses bench mid-run. `tutorial_token` re-runs `add-current` through `login_bench` at the start of every batch.
- The token is bound to an IP; an ISP address change mid-batch triggers the TOTP rebind prompt and hangs the recording. Recording is restart-from-zero (`.claude/skills/tutorials/SKILL.md:104`), so the batch re-runs after a fresh `tutorial_token`.
- If R1 shows a hang rather than a refusal, that is itself a CLI finding: an interactive licence prompt with no TTY-independent timeout. It goes to the licensing owner as a separate item, not into this plan's boxes.
