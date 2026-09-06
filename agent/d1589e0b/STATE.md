## SESSION d1589e0b 2026-09-06T01:42:35Z

# 7 commits on main + gh-removal done in private/account; holding all pushes

## Next action
**Push, in this order, the moment `73c239f60`'s verdict is green** (worker
`bjaaargib`; a 0-byte stream is its shape, it prints only at `--until-final`):
1. Console: 3 commits waiting (STATE, the gh plan, this state).
2. `private/account` branch **`0906-1`** (commit `9656fa711`), then open its PR.
3. **Only then** stage the submodule pointer move and link the account PR in the
   console PR body — `Quality / Submodule Branches` fails on a missing link, and
   a pointer to an unpushed commit is one CI cannot fetch.
4. In that PR's BODY, retract one line of its commit message: it claims "this
   tree's tsconfig includes only src*.ts, so the ENTIRE scripts/rotation program
   is outside its typecheck". **FALSE** — `scripts/tsconfig.json` includes
   `./rotation/**/*.ts` and `npm run typecheck` runs it. Amend is hook-blocked.

**STOP PUSHING until the verdict lands.** Five pushes each superseded the previous
run; each was checked and was a zero-failure supersede, not a watchdog kill.

## What is true right now
`main` = **73c239f60** pushed; console has 3 further commits LOCAL ONLY.
`private/account` on `0906-1` at `9656fa711`, committed, NOT pushed. The console
submodule pointer is moved but **deliberately unstaged**. `ci:quick` **311/311**.

## Landed on main
`5eaa6ae9b` credential gate · `7343ae9dc` shadow retired · `10896546b` GPG armor
fix · `ef31d98b3` token shapes + dead-wiring drain · `8f5f5d5df` breakpoint design
· `dcc4278d6` ci-overhaul docs · `73c239f60` release-key gate.

## The findings that cost the most
1. **The GPG key is two Bitwarden items**; part 1 has no trailing newline, so
   joining WELDS two base64 lines. gpg reads it, Go says `armor invalid`.
   CONFIRMED FIXED (run 34001377608). Gated by `check:ci-release-key-canonical`.
2. **An empty key made the build SKIP signing and exit 0** — green while shipping
   UNSIGNED packages. **`""` reads as "not wanted" is the shape to distrust
   everywhere in this migration.**
3. **131 consumer reads** fetched from Bitwarden AND still read the deleted GitHub
   secret. Org-scope reads **147 -> 4**.
4. **Rotation resurrected 4 deleted org secrets**, pushing without asking whether
   the secret should exist. Fixed in `9656fa711`.

## Local tooling (an earlier STATE.md was wrong)
`bw` and `bws` both on PATH; `~/.bw-session` unlocks the vault. `BWS_ACCESS_TOKEN`
NOT in env. `nfpm` via `.ci/scripts/build/ensure-nfpm.sh`; `createrepo_c`+`rpm`
installed, so `test-linux-packages.sh` runs 21/21. **No shfmt binary**: format via
`npm run check:ci-shell-format`, strip ANSI from its diff, `patch -p0`.
**Count tsc errors with ANSI stripped** — `grep -c 'error TS'` matches nothing
against coloured output and silently reports 0.

## Open
- `[>] #a4a94ba8` CI verdict, leased to `bjaaargib` until 02:43Z.
- `[?] #0ee5912b` **breakpoint secret shape — operator's call.** DEFAULT: drop the
  3 remaining reads. `agent/PLAN-breakpoint-secret-shape.md`. Do NOT build a
  "step-scoped fetch": GITHUB_ENV/GITHUB_OUTPUT are files any step reads.

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates it.
2. **The SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.** Hygiene only.

## Operator caps
Max **3 background workers**. Commit ALL files. Direct-on-main authorised (#dfe46a93).
