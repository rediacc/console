## SESSION d1589e0b 2026-09-06T04:02:33Z

# main GREEN at 14f8f5af5; edge release in flight for v1.3.9. 2 commits held local.

## Next action
**Push the 2 local commits once release run 34009828511 finishes** (worker
`brns4laag` traces it BY RUN ID -- a dispatched run's check-runs are absent from
the branch rollup, a documented false-green, so never judge it from `--ref main`).
Holding only so a second release does not queue behind this one.

Then **get account PR #86 merged** (https://github.com/rediacc/account/pull/86)
and only after that bump the console gitlink for `private/account` off
`65820fd74`. A gitlink at an unmerged commit fails CI at CHECKOUT, not at a gate.

## What is true right now
console `main` = **14f8f5af5** on origin and **GREEN** ("every context succeeded
or was skipped"); local is `0590b2b7a`, 2 ahead. `ci:quick` **312/312**.
Release `34009828511` is `in_progress` in `Tag & Release`. **v1.3.8 is still the
latest tag** -- v1.3.9 has NOT shipped yet.

`private/account`: branch `0906-1` at `9464cce7e` pushed, PR #86 open; the console
submodule is checked out at the recorded `65820fd74`.

## Two of four package formats ship UNSIGNED, and neither is a config omission
- **apk**: `APK_RSA_PRIVATE_KEY` is set by nothing here and is absent from
  `.ci/config/bws-secret-map.json`. nfpm.yaml's apk `signature` block reads
  `${NFPM_APK_KEY_FILE}`, populated only when that var is non-empty -- which is
  what made apk LOOK covered. My required-signing guard for apk BLOCKED v1.3.9
  (run 34003316362) and is reverted.
- **archlinux**: nfpm CANNOT sign it. Adding `archlinux.signature.key_file` fails
  at config load with `field signature not found in type nfpm.ArchLinux`
  (measured 2026-09-06). Signing needs a detached `.sig` made OUTSIDE nfpm.

Both are declared exemptions in `check-release-signing-coverage.sh`, which refuses
an exemption naming a format that IS guarded or one the builder does not accept.

## Gates added this session
`check:ci-tracked-credentials` (53 controls; bound to `wl_store.py::_SECRET_SHAPES`
so the detector cannot drift narrower than the redactor again -- it covered 4 of 7
for months) · `check:ci-release-key-canonical` (9) ·
`check:ci-release-signing-coverage` · plus a 4th arm on
`check-workflow-gates.sh` CHECK 2 (a callee DECLARING a secret nothing reads --
57 such had accumulated).

## Findings worth carrying
1. **`""` READS AS "NOT WANTED".** An empty credential made the build SKIP signing
   and exit 0 -- green while shipping UNSIGNED packages.
2. **The GPG key is TWO Bitwarden items**; part 1 lacks a trailing newline, so
   joining WELDS two base64 lines. gpg reads it, Go says `armor invalid`.
3. **131 consumer reads** fetched from Bitwarden AND still read the deleted GitHub
   secret. Org-scope reads **147 -> 1**.
4. **Rotation resurrected 4 deleted org secrets.** PR #86 fixes that.
5. **Comments count as reads.** `secrets.AWS_SES_*_EU` in prose registered a
   secret named `AWS_SES_`.

## Local tooling
`bw`+`bws` on PATH; `~/.bw-session` unlocks the vault; `BWS_ACCESS_TOKEN` NOT in
env. `nfpm` via `.ci/scripts/build/ensure-nfpm.sh`; `createrepo_c`+`rpm` installed
so `test-linux-packages.sh` runs 21/21. **No shfmt binary**: format via
`npm run check:ci-shell-format`, strip ANSI, `patch -p0`. **Strip ANSI before
counting tsc errors.** `check:format` reaches INTO private/account.
`breakpoint.yml` is VENDORED -- edit `.ci/breakpoint/workflow/`, then
`.ci/breakpoint/scripts/check-breakpoint-drift.sh --write`.

## Open — the operator's
- `[?] #b822a33c` **sign apk + archlinux, or accept unsigned?** DEFAULT now
  EXECUTES: detach-sign archlinux with RELEASE_GPG in build-pkg-repo.sh and
  publish the `.sig`, leaving apk unsigned until a key exists.

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates it.
2. **The SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.** Hygiene only.
