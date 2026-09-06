## SESSION d1589e0b 2026-09-06T06:25:18Z

# NOT ON MAIN. Branch tooling-transformation-w0, 10 commits, push blocked by a peer.

## Next action
**Rebase onto origin/main and push, once the tree is clean.** `git rev-list
--left-right --count origin/main...HEAD` reads **behind 2 / ahead 10**, so HEAD is
NOT a fast-forward; do not force. Rebase needs a clean tree and four paths belong
to session 8f55d4f0 (lint-scope widening). Do NOT commit, stash or revert them.
Broadcast `#f2134ed1` is with them; a waiter is running.

## READ FIRST: the branch is not main and nobody here made it
`git branch --show-current` = **tooling-transformation-w0**, local only
(`git ls-remote origin tooling-transformation-w0` is empty). It appeared mid-session;
74de73ca confirms it is not theirs. **My `c6d3af163` is already ON origin/main even
though every push I attempted was refused** — verify what is on main rather than
inferring it from a push result. I got that wrong once.

Also uncommitted here: `scripts/gate-bind.ts`, 74de73ca's fix for the
`check:ci-gate-bind` ENOENT crash I reported (it enumerated via `git ls-files` then
read the WORKTREE). I asked them to land it on this branch (`#18064e7b`); carry it.

## What shipped
**v1.3.8 and v1.3.9 released, signed.** Org-scope reads **147 -> 1**.
`ci:quick` **313/313**.

Gates added: `check:ci-tracked-credentials` (53 controls, bound to
`wl_store.py::_SECRET_SHAPES` so the detector cannot drift narrower than the
redactor) · `check:ci-release-key-canonical` (12) ·
`check:ci-release-signing-coverage` · `check:ci-staging-tag-guard` · a 4th arm on
check-workflow-gates CHECK 2 (a callee DECLARING a secret nothing reads; 57 had
accumulated). Shared tally at `.ci/scripts/lib/gate-controls.sh`.

## DO NOT "just sign archlinux" — it breaks users
`pacman.conf(5)` SigLevel **Optional**, what Arch ships as `LocalFileSigLevel`, is
"An invalid signature is a fatal error, **as is a signature from a key not in the
keyring**." A `.sig` from a key no user holds turns a working `pacman -U` into a
HARD FAILURE; the keyring rollout lands FIRST. nfpm cannot sign archlinux at all
(`field signature not found in type nfpm.ArchLinux`; upstream #628 open, PR #1065
unmerged). Reason recorded in `.ci/config/nfpm.yaml` where the fix is attempted.

**apk is PREPARED**: conditional on `NFPM_APK_KEY_FILE`, `key_name` PINNED to
`releases@rediacc.com` (APKv2 matches the pubkey by FILENAME), both paths gated in
`test-linux-packages.sh` (21/21). Only the RSA key is missing — operator-only,
`door:operator-only`, deliberately not minted by an agent on a shared worktree.

## Findings worth carrying
1. **`""` READS AS "NOT WANTED"** — an empty credential made the build SKIP signing
   and exit 0, green while shipping UNSIGNED packages.
2. **The GPG key is TWO Bitwarden items**; part 1 lacks a trailing newline, so
   joining WELDS two base64 lines. The build repairs it in flight and now SAYS so
   (exit 10) instead of papering over it forever.
3. **Comments count as reads**: `secrets.AWS_SES_*_EU` in prose registered a
   secret named `AWS_SES_`.
4. **Two release jobs**: `Tag & Release` is NOT the tagging step; `Tag & GitHub
   Release` is. Trace a dispatched release BY RUN ID.
5. **Channel-tag cleanup can never succeed** — `cleanup-staging.sh` guards to
   `staging-*` by design and CHANNEL is `edge`/`stable`. It blamed a token scope
   for a design guard. Now gated by `check:ci-staging-tag-guard`.

## Local tooling
`bw`+`bws` on PATH; `~/.bw-session` unlocks the vault; `BWS_ACCESS_TOKEN` NOT in
env. `nfpm` via `.ci/scripts/build/ensure-nfpm.sh`; `createrepo_c`+`rpm` installed.
**No shfmt binary**: format via `npm run check:ci-shell-format`, strip ANSI,
`patch -p0`. **Strip ANSI before counting tsc errors.**

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** Gates the apk key AND fixing the
   welded GPG value at source.
2. **Account PR #86** unmerged; console gitlink stays at `65820fd74`.
