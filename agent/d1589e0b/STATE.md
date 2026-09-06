## SESSION d1589e0b 2026-09-06T04:20:39Z

# v1.3.9 SHIPPED. Signing research inverted my default — do NOT sign archlinux.

## Next action
**Push `3d718d171`** (one local commit: apk key_name pin + withdrawn archlinux
default). `ci:quick` is 312/312 on it. Then **get account PR #86 merged**
(https://github.com/rediacc/account/pull/86) and only after that bump the console
gitlink for `private/account` off `65820fd74` — a gitlink at an unmerged commit
fails CI at CHECKOUT, not at a gate.

## What is true right now
console `main` = **b0602117e** on origin; local `3d718d171`, 1 ahead, tree clean.
**v1.3.9 shipped** (release run 34009828511 green; tag + GitHub release 04:11:43Z).
`private/account` branch `0906-1` at `9464cce7e` pushed, PR #86 open; the console
submodule sits at the recorded `65820fd74`.

## DO NOT "just sign archlinux" — it breaks users
A planning agent researched this from upstream and it INVERTED the default I had
written. `pacman.conf(5)` defines SigLevel **Optional** — what Arch ships as
`LocalFileSigLevel` — as "An invalid signature is a fatal error, **as is a
signature from a key not in the keyring**." So publishing a detached `.sig` signed
by a key no user holds turns a working `pacman -U` into a HARD FAILURE. The keyring
rollout must land BEFORE the first signed artifact (Arch Linux ARM and Chaotic-AUR
both do it that way). Verified against man.archlinux.org directly, not from the
agent's summary.

nfpm also cannot sign archlinux natively: its `ArchLinux` struct has 4 fields and
no signature; goreleaser/nfpm#628 is open with zero comments, PR #1065 unmerged.

**apk is the opposite** — an unsigned `.apk` already needs `--allow-untrusted`, so
signing is strictly an improvement. Only the KEY is missing. `key_name` is now
PINNED to `releases@rediacc.com` in nfpm.yaml because APKv2 matches the pubkey by
FILENAME, so the maintainer-email default would silently invalidate every deployed
`/etc/apk/keys/*.rsa.pub` on a maintainer edit.

## Two release jobs, not one — a thing I misread
`Tag & Release` (early: artifacts, attestation) is NOT the tagging step;
`Tag & GitHub Release` (late) is. Seeing the first succeed with no tag is normal,
not an anomaly. Trace a dispatched release BY RUN ID: its check-runs are absent
from the branch rollup, a documented false-green.

## Findings worth carrying
1. **`""` READS AS "NOT WANTED".** An empty credential made the build SKIP signing
   and exit 0 — green while shipping UNSIGNED packages.
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
`breakpoint.yml` is VENDORED — edit `.ci/breakpoint/workflow/`, then
`.ci/breakpoint/scripts/check-breakpoint-drift.sh --write`.

## Open — the operator's
- `[?] #b822a33c` DEFAULT: leave BOTH unsigned, on evidence not inertia. Minting
  the apk RSA key needs BWS_ACCESS_TOKEN and is the single remaining step there.

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates it.
2. **The SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.** Hygiene only.
