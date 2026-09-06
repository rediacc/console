## SESSION d1589e0b 2026-09-06T00:26:58Z

# Shadow retired; main's next red was the GPG key, root-caused and fixed

## Next action
**Push `f7094150b` (needs a fresh `ci:quick` on the committed tree), then watch
main.** After that, three operator rulings from /ask are owed, in this order:
1. **Add `ghp_`/`xox*` to `check:ci-tracked-credentials`**, baselining the one
   synthetic fixture (`.claude/hooks/stop/worklist-cases/26-migrate.sh` plants
   `ghp_` + the literal alphabet). The gate's header currently justifies leaving
   them out with a reason that no longer holds — correct it.
2. **Remove the 65 dead `secrets:` passthroughs** + matching `workflow_call`
   declarations (25 cd-v2, 25 promote-stable, 15 ci.yml). Finishes "no GitHub
   secrets at all" and is what lets `github-secret-preimage.json` be deleted.
   `retire-shadowed-secrets.py --apply` does it BUT strips declarations whose
   consumers still read them — actionlint catches that; check every run.
3. **breakpoint.yml: build the step-scoped fetch shape.** Its 3 reads resolve
   EMPTY today. Fetch into ONE step's own env, never GITHUB_ENV, because a later
   step hands a human a shell.

## What is true right now
`main` = **7343ae9dc** pushed; **`f7094150b` is committed locally and NOT pushed**.
Operator confirms GitHub org secrets are now empty except one.

**main's CI on 7343ae9dc is RED** at `Stage Artifacts / Build Linux packages`.
Root cause found and fixed, not guessed:
- A GPG private key does not fit one Bitwarden field, so it is stored as TWO
  items (`gpg-private.asc - 1` / `- 2`). Part 1 has **no trailing newline** and
  part 2 has no armor header, so concatenating them **welds** part 1's last
  base64 line onto part 2's first.
- gpg reads that fine (the fingerprint check passes); Go's decoder answers
  `openpgp: invalid data: armor invalid`. Reproduced verbatim against
  x/crypto v0.56.0 with a throwaway key. Joining with a newline is accepted.
- Fix: `build-linux-pkg.sh` re-exports through gpg before nfpm sees it.
  Passphrase protection VERIFIED to survive.
- **The previous green was worse than the red:** that step read the deleted org
  secret, got `""`, and an empty key made the build SKIP signing and exit 0 —
  shipping unsigned packages. `RELEASE_SIGNING_REQUIRED=1` now makes that fatal.
- 3 new controls in `test-linux-packages.sh`, all against real nfpm output. 21/21.

## Local tooling notes (STATE.md previously said otherwise — it was wrong)
`bw` AND `bws` are both on PATH. `~/.bw-session` unlocks the personal vault;
`BWS_ACCESS_TOKEN` is NOT in env, so Secrets Manager is unreadable here.
`nfpm` installs via `.ci/scripts/build/ensure-nfpm.sh` (prints its bin dir).
`createrepo_c` and `rpm` are now installed, so `test-linux-packages.sh` runs 21/21.

## Owed, operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** No `bws` verb rotates a machine
   token. Update `.ci/config/bws-token-expiry.json`.
2. **The stored SM value for `RELEASE_GPG_PRIVATE_KEY` is still welded.**
   Re-join the two halves WITH a newline. Needs BWS_ACCESS_TOKEN. The build no
   longer cares, so this is hygiene, not an outage.
3. **The `gh`-removal plan** is still owed by me.

## Operator caps
Max **3 background workers**. "Commit ALL files, not just your changes."
Fixing DIRECTLY ON MAIN is authorised (order #dfe46a93).
