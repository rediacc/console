# PLAN: give test_gate_bws_map.py's clean-fixture test a synthetic .env.example

Status: done
First-Seen: 2026-09-23
Owner: d778be9d
Updated: 2026-09-23

## The finding

`.ci/rediacc_ci/tests/gates/test_gate_bws_map.py::test_clean_fixture_passes` fails: `fixture()` (test_gate_bws_map.py:72) never writes `private/account/.env.example` into the synthetic tmp_path tree, but `check_bws_map.py`'s assertion 14 (`check_bws_map.py:728`, `ENV_EXAMPLE = ROOT / "private" / "account" / ".env.example"`) reads it unconditionally.
The 14a/14b/14c cases elsewhere in the same test file pass because they call the internal helper functions directly against synthetic in-memory data, bypassing the fixture entirely -- only the end-to-end `test_clean_fixture_passes` run is affected.

## Design

Add `private/account/.env.example` to `fixture()`, containing exactly the 3 names `fixture()` already homes in `SECRET_MAP`/`EXEMPTIONS` (`ALPHA_TOKEN`, `ORPHAN_TOKEN`, `PREFIX_EU`) as active assignments, padded with 27 more names as **commented-out** assignments (`# PAD_NNN=x`) of `kind: "opt-in"` in a new `env-local-allowlist.json` fixture file -- `check_bws_map.py:833-836` requires an opt-in entry's name to be commented, not active, which sidesteps needing 27 more map/exemption entries.
`MIN_EXAMPLE_NAMES = 30` (`check_bws_map.py:740`) counts active-or-commented names together, so 3 active + 27 commented clears the floor.

## Implementation

1. `write(directory / "private/account/.env.example", ...)`: 3 active lines (`ALPHA_TOKEN=x`, `ORPHAN_TOKEN=x`, `PREFIX_EU=x`) + 27 commented lines (`# BWS_MAP_FIXTURE_PAD_01=x` .. `_27`).
2. `write(directory / ".ci/config/env-local-allowlist.json", ...)`: 27 entries, each `{"kind": "opt-in"}`, one per padding name.
3. Re-run `test_clean_fixture_passes`; confirm `rc=0` and the 14a/14b/14c/floor controls stay green (they must not start firing against the new padding).

## Verification

- `.ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/gates/test_gate_bws_map.py -q` -- full file green, not just the one case.
- Diff the fixture addition against `check_bws_map.py:740`, `:833-836` by hand to confirm the padding shape matches what those lines actually require.

## Boxes

- [x] Add the synthetic `.env.example` (3 active + 27 commented names) to `fixture()`.
- [x] Add the synthetic `env-local-allowlist.json` (27 opt-in entries) to `fixture()`.
- [x] `test_gate_bws_map.py` full file green.
