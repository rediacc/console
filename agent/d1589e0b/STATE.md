## SESSION d1589e0b 2026-09-06T06:02:36Z

# NOT ON MAIN. This checkout is on tooling-transformation-w0 with 5 of my commits.

## Next action
**Rebase this branch onto origin/main and push, the moment the tree is clean.**
`git rev-list --left-right --count origin/main...HEAD` reads **behind 2 / ahead 5**,
so HEAD is NOT a fast-forward -- `git push origin HEAD:main` would be refused and
must not be forced. Rebase needs a clean tree, and four paths in it belong to
session 8f55d4f0 (lint-scope widening). Do NOT commit, stash or revert them.

## READ THIS FIRST: the branch is not main and nobody here created it
`git branch --show-current` = **tooling-transformation-w0**. It exists ONLY locally
(`git ls-remote origin tooling-transformation-w0` is empty). It appeared under this
worktree mid-session; peer 74de73ca confirms it is not theirs either. It holds
exactly 5 commits above origin/main, all mine:
`376d107c8` `8780020c8` `20a605908` `c7e3a8aed` `7a770d098`.

**My `c6d3af163` IS already on origin/main** even though every push I attempted was
refused, so something else pushed it. Verify what is on main before assuming a
commit is unpushed; I got this wrong and reported "6 parked" when it was 5.

## Who owns the dirty tree
- `.ci/scripts/test/smoke-test-preview.ts`, `package.json`,
  `workers/account/src/index.ts`, `workers/proxy/src/index.ts` -> **8f55d4f0**,
  lint-scope widening, mid control-proof. Leave alone; it settles itself.
- `scripts/gate-bind.ts` -> **74de73ca**, their fix for the `check:ci-gate-bind`
  ENOENT crash I reported (it enumerated via `git ls-files` then read the WORKTREE;
  a deletion batch made those disagree). I told them to land it on this branch
  (`#18064e7b`); carry it along on the rebase.

## What shipped
**v1.3.9 released** and signed. Org-scope reads **147 -> 1**. Gates added:
`check:ci-tracked-credentials` (53 controls, bound to `wl_store.py::_SECRET_SHAPES`
so the detector cannot drift narrower than the redactor), `check:ci-release-key-canonical`
(12), `check:ci-release-signing-coverage`, plus a 4th arm on check-workflow-gates
CHECK 2 (a callee DECLARING a secret nothing reads -- 57 had accumulated).

## DO NOT "just sign archlinux" — it breaks users
`pacman.conf(5)` SigLevel **Optional**, which Arch ships as `LocalFileSigLevel`, is
"An invalid signature is a fatal error, **as is a signature from a key not in the
keyring**." A `.sig` from a key no user holds turns a working `pacman -U` into a
HARD FAILURE; the keyring rollout lands FIRST. nfpm cannot sign archlinux natively
either (goreleaser/nfpm#628 open, PR #1065 unmerged). Reason is now in nfpm.yaml
where the fix would be attempted.

**apk is PREPARED, not deferred**: signing is conditional on `NFPM_APK_KEY_FILE`,
`key_name` PINNED to `releases@rediacc.com` (APKv2 matches the pubkey by FILENAME),
and both paths are proven every run. Only the RSA key is missing.

## Findings worth carrying
1. **`""` READS AS "NOT WANTED"** -- an empty credential made the build SKIP
   signing and exit 0, green while shipping UNSIGNED packages.
2. **The GPG key is TWO Bitwarden items**; part 1 lacks a trailing newline, so
   joining WELDS two base64 lines. The build repairs it in flight and now SAYS so
   (exit 10) instead of papering over it forever.
3. **Comments count as reads**: `secrets.AWS_SES_*_EU` in prose registered a
   secret named `AWS_SES_`.
4. **Two release jobs**: `Tag & Release` is NOT the tagging step; `Tag & GitHub
   Release` is. Trace a dispatched release BY RUN ID.

## Open — the operator's
- `[?] #b822a33c` DEFAULT: leave BOTH formats unsigned, on evidence not inertia.

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** Gates the apk key AND fixing the
   welded GPG value at source.
2. **Account PR #86** unmerged; console gitlink stays at `65820fd74`.
