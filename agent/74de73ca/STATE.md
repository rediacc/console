## SESSION 74de73ca 2026-09-03T11:28:38Z

Branch `0903-1`, PR #585. NOTHING IS COMMITTED. New files are `git add`-ed only so
manifest leaf checks resolve — do not read that as intent to commit. 4 commits are
unpushed (tip `2099135c0`); the operator pushes, always.

## Verified green right now

`ci:quick` **292/292 exit 0** with the profiler on by default · hook battery
**PASS=2043 FAIL=0** · worklist suite 889/0 · account suite 1670/0.

## What this session built

**www bundle budget** — `scripts/check-client-bundle-budget.ts` splits eager from
deferred (eager 455,632 B under the 500,000 B budget; deferred 122,110 B under a
150,000 B ceiling). Honest because the deferral is real: `SPSolutionVideo.astro`
server-renders a poster and `tutorial-video-hydrate.ts` builds the player on click.

**Worklist lineage** — `--adopt` proves a compaction chain from harness evidence
(`wl_lineage.py`, case 24). **Onboarding notice** — `onboard.py`, case 25.

**Resource profiling, live on this machine.** Read
`agent/PLAN-shell-resource-profiling.md` first; its "Landed" section is authoritative.
`wl_resprofile.py` (exit recorder, armed from `wl_core`), `wl_ressample.py` (forkless
/proc tree sampler, attached per gate at `exec.ts:82`, 500 ms, `CI_PROFILE=off`),
`wl_profile.py` (E1/E4/E5/E6, D1 dilation, D2 self-scan, Wilson admission, `--rank`),
`check_resprofile.py` + `test-resprofile.sh`. Bash via `bashcov-sup`
(`.devcontainer/bashcov-sup.c`, host build by `ensure_bashcov_sup`,
`.claude/hooks/profile/bash_env.sh`, `env.BASH_ENV` in **user-scope**
`~/.claude/settings.json` — `.claude/settings.local.json` is TRACKED, never put a
machine path there). Corpus: `~/.claude/resprofile/home-developer-console/<day>/`,
14-day raw retention, `RANK.md`. Baseline deliberately **unseeded**.

Also: 62 inline shadow-compare bodies extracted to `.ci/scripts/ci/shadow-compare.sh`
(`check:ci-workflows` caps inline logic at 8 lines, no baseline).

## Next action

1. **`[?] #13d281a2` is the only open item.** `scripts/dev/derive-shadow-pass-list.sh`
   is built and verified; after a push + one green cycle run
   `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1` and execute exactly the
   `gh secret delete` lines it prints. Today it yields 4: `ACCOUNT_ED25519_PUBLIC_KEY`,
   `APP_PRIVATE_KEY`, `CLOUDFLARE_API_TOKEN`, `DOCKERHUB_TOKEN`. It refuses if no
   passing compare exists and skips any org name shadowed by a repo-level twin.
2. Seed the profiling baseline only after several days of real quiet runs:
   `check_resprofile.py --seed <run-dir>`. Never from one machine's first run.
3. Two live facts a fresh session will otherwise rediscover: `bws` lives at
   `$CLAUDE_JOB_DIR/tmp/bws` and needs `--color no` (its default `--color auto` wraps
   `-o json` in ANSI); the Bitwarden token in `private/account/.env` **expires
   2026-09-08**.
4. Do NOT delete Stripe endpoint `we_1TPL2sAuCbjrUVmcH7FpQAq0` — it is the www
   deploy's own (`resolve-www-deploy-target.sh:42`) and `webhook-verify.ts:53-55`
   recreates it with a fresh signing secret.
