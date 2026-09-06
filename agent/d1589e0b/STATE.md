## SESSION d1589e0b 2026-09-06T02:43:24Z

# 3 greens on main, v1.3.8 shipped signed, org-scope reads 147 -> 1. 3 commits held.

## Next action
**Push the 3 local commits once `fcdc96aaa` returns a verdict** (worker
`b9ozv973f` is tracing it; a 0-byte stream is its shape, it prints only at
`--until-final`). Holding only to avoid superseding that run — five earlier pushes
each did, and every one had to be checked as a zero-failure supersede rather than
a watchdog kill.

Then: **get account PR #86 reviewed and merged**
(https://github.com/rediacc/account/pull/86), and only after it merges bump the
console gitlink for `private/account` off `65820fd74`. A gitlink pointing at an
unmerged commit fails CI at CHECKOUT, not at a gate.

## What is true right now
console `main` = **fcdc96aaa** on origin; local is **8dd0e29bd**, 3 ahead.
`ci:quick` **312/312**. Three consecutive greens: `10896546b`, `dcc4278d6`,
`73c239f60` (all 0 failed / 0 cancelled jobs). **v1.3.8 released from
`73c239f60`** — the first release since the org-secret deletion whose packages are
actually signed.

`private/account`: branch `0906-1` at `9464cce7e` pushed, **PR #86 open**; the
console worktree submodule is checked out at the recorded `65820fd74`.

## The 3 unpushed commits
- `9d167f96d` breakpoint: dropped its 3 empty org-secret reads (the `[?]` DEFAULT).
  **Org-scope reads 147 -> 1**; the survivor is watchdog-monitor's
  CLOUDFLARE_API_TOKEN, which cannot take a fetch ahead of its monitor step.
- `8dd0e29bd` credential gate widened: it covered 4 of the 7 shapes in
  `wl_store.py::_SECRET_SHAPES`, whose own comment says they "must never reach a
  TRACKED file". Added `github_pat_`, `whsec_`, `sk-`, `sk_(live|test)_`.
- `984efbe3a` STATE.

## Four gates now, and what each is for
`check:ci-tracked-credentials` (44 controls, 4 fixtures baselined) ·
`check:ci-release-key-canonical` (9) · `check:ci-release-signing-coverage` (every
package format must refuse to ship unsigned or carry a reasoned exemption) ·
plus `check:ci-secret-scope` freezing the last org-scope read.

## The findings worth carrying
1. **`""` READS AS "NOT WANTED".** An empty credential made the build SKIP signing
   and exit 0 — green while shipping UNSIGNED deb/rpm, then apk identically.
2. **The GPG key is stored as TWO Bitwarden items**; part 1 has no trailing
   newline, so joining WELDS two base64 lines. gpg reads it, Go says
   `armor invalid`.
3. **131 consumer reads** fetched from Bitwarden AND still read the deleted GitHub
   secret, so deploys authenticated as nobody while looking healthy.
4. **Rotation resurrected 4 deleted org secrets.** PR #86 fixes that.
5. **Comments count as reads.** Writing `secrets.AWS_SES_*_EU` in an explanation
   registered a new secret named `AWS_SES_`. Name secrets without the prefix.

## Local tooling
`bw`+`bws` on PATH; `~/.bw-session` unlocks the vault; `BWS_ACCESS_TOKEN` NOT in
env. `nfpm` via `.ci/scripts/build/ensure-nfpm.sh`; `createrepo_c`+`rpm` installed
so `test-linux-packages.sh` runs 21/21. **No shfmt binary**: format via
`npm run check:ci-shell-format`, strip ANSI from its diff, `patch -p0`.
**Strip ANSI before counting tsc errors.** Console's `check:format` reaches INTO
private/account. `breakpoint.yml` is VENDORED — edit
`.ci/breakpoint/workflow/`, then `.ci/breakpoint/scripts/check-breakpoint-drift.sh --write`.

## Open — the operator's
- `[?] #b822a33c` **sign archlinux, or accept unsigned?** No `signature` block in
  nfpm.yaml, never had one. DEFAULT: leave unsigned, frozen visibly by the gate.

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates it.
2. **The SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.** Hygiene only.
