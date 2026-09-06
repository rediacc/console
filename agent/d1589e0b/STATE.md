## SESSION d1589e0b 2026-09-06T03:01:09Z

# main red was MY apk guard; fixed and pushed. 2 of 4 formats ship unsigned.

## Next action
**Read the verdict for `14f8f5af5`** (worker `b4am8d033`; a 0-byte stream is its
shape, it prints only at `--until-final`). That push fixes a red I caused, and
v1.3.9 was mid-release when the guard stopped it — confirm the release COMPLETES,
not just that CI is green. The release is a SEPARATE run.

Then **get account PR #86 merged** (https://github.com/rediacc/account/pull/86)
and only after that bump the console gitlink for `private/account` off
`65820fd74`. A gitlink at an unmerged commit fails CI at CHECKOUT, not at a gate.

## What just went wrong — the most useful thing here
Run 34003316362 on `fcdc96aaa` failed at `Build Linux packages` with MY error:
`RELEASE_SIGNING_REQUIRED=1 but APK_RSA_PRIVATE_KEY is empty or unset`. The guard
worked; writing it was the mistake. A class sweep found apk using the same
`[[ -n "${VAR:-}" ]]` shape as the GPG key and I made it required WITHOUT checking
a key existed. **It does not**: APK_RSA_PRIVATE_KEY is set by nothing here and is
absent from `.ci/config/bws-secret-map.json`. nfpm.yaml's apk `signature` block
reads `${NFPM_APK_KEY_FILE}`, populated only when that var is non-empty — which is
what made apk LOOK covered when it never was.

**Two of four formats ship unsigned: apk AND archlinux**, both now declared
exemptions in `check-release-signing-coverage.sh`. deb and rpm keep the
requirement; they have a real key fetched from Bitwarden.

## What is true right now
console `main` = **14f8f5af5**, pushed, local == origin, clean, `ci:quick`
**312/312**. `private/account` branch `0906-1` at `9464cce7e` pushed, PR #86 open;
the console submodule sits at the recorded `65820fd74`.

Greens: `10896546b`, `dcc4278d6`, `73c239f60` (0 failed / 0 cancelled each).
**v1.3.8 released from `73c239f60`** — first release since the org-secret deletion
whose packages are actually signed. v1.3.9 was interrupted by my guard.

## Gates added this session
`check:ci-tracked-credentials` (53 controls; now bound to
`wl_store.py::_SECRET_SHAPES` so the detector cannot drift narrower than the
redactor again — it covered 4 of 7 for months) · `check:ci-release-key-canonical`
(9) · `check:ci-release-signing-coverage` · `check:ci-secret-scope`.

## Findings worth carrying
1. **`""` READS AS "NOT WANTED".** An empty credential made the build SKIP signing
   and exit 0 — green while shipping UNSIGNED packages.
2. **The GPG key is TWO Bitwarden items**; part 1 lacks a trailing newline, so
   joining WELDS two base64 lines. gpg reads it, Go says `armor invalid`.
3. **131 consumer reads** fetched from Bitwarden AND still read the deleted GitHub
   secret. Org-scope reads **147 -> 1**.
4. **Rotation resurrected 4 deleted org secrets.** PR #86 fixes that.
5. **Comments count as reads.** `secrets.AWS_SES_*_EU` in prose registered a secret
   named `AWS_SES_`.

## Local tooling
`bw`+`bws` on PATH; `~/.bw-session` unlocks the vault; `BWS_ACCESS_TOKEN` NOT in
env. `nfpm` via `.ci/scripts/build/ensure-nfpm.sh`; `createrepo_c`+`rpm` installed
so `test-linux-packages.sh` runs 21/21. **No shfmt binary**: format via
`npm run check:ci-shell-format`, strip ANSI, `patch -p0`. **Strip ANSI before
counting tsc errors.** `check:format` reaches INTO private/account.
`breakpoint.yml` is VENDORED — edit `.ci/breakpoint/workflow/`, then
`.ci/breakpoint/scripts/check-breakpoint-drift.sh --write`.

## Open — the operator's
- `[?] #b822a33c` **sign apk + archlinux, or accept both unsigned?** DEFAULT: leave
  both unsigned, frozen by the coverage gate. Minting an apk RSA key is theirs.

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates it.
2. **The SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.** Hygiene only.
