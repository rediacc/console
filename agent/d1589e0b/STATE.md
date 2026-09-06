## SESSION d1589e0b 2026-09-06T01:57:33Z

# main GREEN; gh-removal done in private/account; 5 console commits held back

## Next action
**Push, in this order.** Nothing below is blocked on anyone; it is sequenced
because a console gitlink pointing at an unpushed submodule commit fails CI at
CHECKOUT, not at a gate.
1. Console `main`: 5 commits waiting locally.
2. `private/account` branch **`0906-1`**, head **`9464cce7e`** (3 commits), then
   open its PR.
3. **Only then** `git add private/account` in console and link that PR in the
   console body — `Quality / Submodule Branches` fails on a missing link.
4. In that PR's BODY, retract one line of commit `9656fa711`'s message: it claims
   "this tree's tsconfig includes only src*.ts, so the ENTIRE scripts/rotation
   program is outside its typecheck". **FALSE** — `scripts/tsconfig.json` includes
   `./rotation/**/*.ts` and `npm run typecheck` runs it. Amend is hook-blocked.

**SUBMODULE POINTER: keep the move, do NOT stage it before step 2.** It is
unstaged on purpose; stage by explicit path only, never `git add -A`. Do NOT
restore it either: `65820fd74` predates the rotation fix, so a restore re-arms the
bug that resurrected 4 deleted org secrets. Peer session 74de73ca raised this and
was answered (#cda3bb87).

## What is true right now
`main` = `73c239f60` pushed and **GREEN**: run 34001377608 on `10896546b`
completed success, 0 failed jobs, 0 cancelled, CI Complete=success. Console has 5
further commits LOCAL ONLY. `ci:quick` **311/311**.

## Landed on main
credential gate · shadow retired · GPG armor fix · token shapes + dead-wiring
drain · breakpoint design note · ci-overhaul docs · release-key gate.

## The findings that cost the most
1. **The GPG key is two Bitwarden items**; part 1 has no trailing newline, so
   joining WELDS two base64 lines. gpg reads it, Go says `armor invalid`. Fixed
   and gated (`check:ci-release-key-canonical`, 9 controls).
2. **An empty credential made the build SKIP signing and exit 0** — green while
   shipping UNSIGNED packages. Fixed for deb/rpm, then the class sweep found the
   same shape one branch over in **apk** and fixed that too (6 controls now).
   **`""` reads as "not wanted" is the shape to distrust everywhere here.**
3. **131 consumer reads** fetched from Bitwarden AND still read the deleted GitHub
   secret. Org-scope reads **147 -> 4**.
4. **Rotation resurrected 4 deleted org secrets**, pushing without asking whether
   the secret should exist. Fixed in `9656fa711`.

## Local tooling (an earlier STATE.md was wrong)
`bw`+`bws` on PATH; `~/.bw-session` unlocks the vault; `BWS_ACCESS_TOKEN` NOT in
env. `nfpm` via `.ci/scripts/build/ensure-nfpm.sh`; `createrepo_c`+`rpm` installed
so `test-linux-packages.sh` runs 21/21. **No shfmt binary**: format via
`npm run check:ci-shell-format`, strip ANSI from its diff, `patch -p0`.
**Strip ANSI before counting tsc errors** — `grep -c 'error TS'` silently reports
0 against coloured output. Console's `check:format` reaches INTO private/account.

## Open
- `[?] #0ee5912b` **breakpoint secret shape — operator's call.** DEFAULT: drop the
  3 remaining reads. `agent/PLAN-breakpoint-secret-shape.md`. Do NOT build a
  "step-scoped fetch": GITHUB_ENV/GITHUB_OUTPUT are files any step reads.

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates it.
2. **The SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.** Hygiene only.

## Operator caps
Max 3 background workers. Commit ALL files. Direct-on-main authorised (#dfe46a93).
