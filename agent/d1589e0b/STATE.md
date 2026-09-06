## SESSION d1589e0b 2026-09-06T00:49:58Z

# 4 commits on main; GPG armor weld fixed and CONFIRMED; org-scope reads 147 -> 4

## Next action
**Read the verdict for `872ac70b4`.** Worker `bl8c32yl3` runs
`ci-trace.py --wait --until-final --ref main` and prints ONLY at the end, so a
0-byte stream is health, not a stall. Then watch the **edge release** the merge
dispatches — that is a SEPARATE run; watching CI is not watching the release.
On a red, read the JOB's own conclusion, never the run rollup: a cancelled run
and a green one look identical in `gh run list`.

Three pushes landed in quick succession, so the runs on `10896546b` and
`7343ae9dc` were SUPERSEDED. Only `872ac70b4` counts. Do not re-dispatch anything
on the strength of an older run's absence.

## What is true right now
`main` = **872ac70b4**, tree clean, `ci:quick` **310/310** on the pushed tree.
Operator confirms GitHub org secrets are empty except one.

Landed this round (oldest first): `5eaa6ae9b` credential gate ·
`7343ae9dc` shadow retired · `10896546b` GPG armor fix · `ef31d98b3` token shapes
+ dead-wiring drain · `8f5f5d5df` breakpoint design note · `872ac70b4` plan-box
ledger.

**The GPG fix is CONFIRMED, not assumed:** `Build Linux packages` step =
`success` on run 34001377608, the exact step that had failed.

## The two findings that cost the most
1. **The GPG key is stored as TWO Bitwarden items** (`gpg-private.asc - 1`/`- 2`).
   Part 1 has NO trailing newline and part 2 has no armor header, so joining them
   WELDS two base64 lines. gpg reads it (the fingerprint check ticks); Go answers
   `openpgp: invalid data: armor invalid`. Reproduced verbatim against
   x/crypto v0.56.0. `build-linux-pkg.sh` now re-exports through gpg;
   passphrase protection verified to survive.
2. **An empty key made the build SKIP signing and exit 0** — green while shipping
   UNSIGNED packages. `RELEASE_SIGNING_REQUIRED=1` on cd-stage makes that fatal.
   This is the shape to distrust everywhere: `""` reads as "not wanted".

## Local tooling (earlier STATE.md was WRONG about this)
`bw` and `bws` are BOTH on PATH. `~/.bw-session` unlocks the personal vault.
`BWS_ACCESS_TOKEN` is NOT in env, so Secrets Manager is unreadable here.
`nfpm` via `.ci/scripts/build/ensure-nfpm.sh` (prints its bin dir); `createrepo_c`
and `rpm` now installed, so `test-linux-packages.sh` runs **21/21**.
Passwordless sudo works for apt.

## Open
- `[>] #a4a94ba8` CI verdict, leased to `bl8c32yl3` until 02:18Z.
- `[?] #0ee5912b` **breakpoint secret shape — operator's call.** DEFAULT (fires
  ~02:00Z): drop the 3 remaining reads. Design + the one-run experiment that
  settles the alternative: `agent/PLAN-breakpoint-secret-shape.md`. Do NOT build
  a "step-scoped fetch": GITHUB_ENV and GITHUB_OUTPUT are files any step reads,
  so it isolates nothing from the debug shell.

## Operator-only, still owed
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates a machine
   token. Update `.ci/config/bws-token-expiry.json`.
2. **The SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.** Re-join the
   halves WITH a newline. Hygiene only — the build canonicalises it now.

## Owed by me
The **`gh`-removal plan**, not started. Stripping `githubSecretNames` from
`rotation-manifest.json` + `scripts/rotation/lib/config.ts` breaks 4 tests in
`rotation-bitwarden-names.test.ts`; `cf-breakpoint` must KEEP its `gh` path.

## Operator caps
Max **3 background workers**. "Commit ALL files, not just your changes."
Fixing DIRECTLY ON MAIN is authorised (order #dfe46a93).
