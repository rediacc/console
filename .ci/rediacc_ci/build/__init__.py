"""Ported build tooling (`.ci/scripts/build/`).

Not a quality gate: `canonicalise_gpg_key` is a helper the release build shells
out to, invoked both from `build-linux-pkg.sh` (production) and from
`rediacc_ci.quality.release_key_canonical`'s own controls (which drive the
BASH twin as a subprocess to prove the twin still repairs the defect shape --
see that module's docstring). The bash twin is NOT deleted (W7 phase-6
decision, same as `quality/`): both copies live side by side until a
differential ledger over K distinct trees exists, per
`scripts/lib/shadow-gate.ts`.
"""

__all__: list[str] = []
