## SESSION d1589e0b 2026-09-06T01:14:41Z

# 7 commits on main; GPG weld fixed + GATED; org-scope reads 147 -> 4

## Next action
**Read the verdict for `73c239f60`.** Worker `bjaaargib` runs
`ci-trace.py --wait --until-final --ref main` and prints ONLY at the end, so a
0-byte stream is health, not a stall. Then watch the **edge release** the merge
dispatches — a SEPARATE run; watching CI is not watching the release.

**STOP PUSHING until that verdict lands.** Five pushes in a row each superseded
the previous run (`7343ae9dc`, `10896546b`, `872ac70b4`, `dcc4278d6`). Each was
checked and was a ZERO-FAILURE supersede, not a watchdog kill — but on a red,
read the JOB's own conclusion, never the run rollup: cancelled and green look
identical in `gh run list`.

## What is true right now
`main` = **73c239f60**, tree clean, `ci:quick` **311/311** on the pushed tree.
Operator confirms GitHub org secrets are empty except one.

Landed, oldest first: `5eaa6ae9b` credential gate · `7343ae9dc` shadow retired ·
`10896546b` GPG armor fix · `ef31d98b3` token shapes + dead-wiring drain ·
`8f5f5d5df` breakpoint design note · `dcc4278d6` ci-overhaul docs ·
`73c239f60` release-key gate.

Two gates added: **`check:ci-tracked-credentials`** (AWS ids, PEM bodies,
`ghp_`/`xox` tokens; 3 fixtures baselined) and **`check:ci-release-key-canonical`**
(9 controls, throwaway key). Both are in `npm run ci`.

## The three findings that cost the most
1. **The GPG key is stored as TWO Bitwarden items** (`gpg-private.asc - 1`/`- 2`).
   Part 1 has NO trailing newline, so joining them WELDS two base64 lines. gpg
   reads it (the fingerprint check ticks); Go answers `armor invalid`. Reproduced
   verbatim against x/crypto v0.56.0. CONFIRMED FIXED: `Build Linux packages`
   step = success on run 34001377608.
2. **An empty key made the build SKIP signing and exit 0** — green while shipping
   UNSIGNED packages. `RELEASE_SIGNING_REQUIRED=1` makes it fatal. **`""` reads as
   "not wanted" is the shape to distrust everywhere in this migration.**
3. **131 consumer reads** were fetching from Bitwarden AND still reading the
   deleted GitHub secret, so deploys authenticated as nobody while looking
   healthy. Org-scope reads **147 -> 4**.

## Local tooling (an earlier STATE.md was WRONG about this)
`bw` and `bws` are BOTH on PATH; `~/.bw-session` unlocks the personal vault.
`BWS_ACCESS_TOKEN` is NOT in env, so Secrets Manager is unreadable here.
`nfpm` via `.ci/scripts/build/ensure-nfpm.sh`; `createrepo_c` + `rpm` installed,
so `test-linux-packages.sh` runs **21/21**. Passwordless sudo works for apt.
**No shfmt binary on this host** — to format, run `npm run check:ci-shell-format`,
strip ANSI from its diff and `patch -p0`.

## Open
- `[>] #a4a94ba8` CI verdict, leased to `bjaaargib` until 02:43Z.
- `[?] #0ee5912b` **breakpoint secret shape — operator's call.** DEFAULT (fires
  ~02:00Z): drop the 3 remaining reads. See
  `agent/PLAN-breakpoint-secret-shape.md`. Do NOT build a "step-scoped fetch":
  GITHUB_ENV and GITHUB_OUTPUT are files any step reads, so it isolates nothing
  from the debug shell.

## Operator-only, still owed
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates a machine
   token. Update `.ci/config/bws-token-expiry.json`.
2. **The SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.** Re-join the
   halves WITH a newline. Hygiene only — the build canonicalises it and
   `check:ci-release-key-canonical` proves that repair keeps working.

## Owed by me
The **`gh`-removal plan**, not started. Stripping `githubSecretNames` from
`rotation-manifest.json` + `scripts/rotation/lib/config.ts` breaks 4 tests in
`rotation-bitwarden-names.test.ts`; `cf-breakpoint` must KEEP its `gh` path.

## Operator caps
Max **3 background workers**. "Commit ALL files, not just your changes."
Fixing DIRECTLY ON MAIN is authorised (order #dfe46a93).
