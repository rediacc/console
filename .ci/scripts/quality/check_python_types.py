#!/usr/bin/env python3
"""Entry point for the Python type-check gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.python_types`, which pytest and this file's own `--selftest` import directly.

WHY AN ENTRY POINT AT ALL, in `check_npmrc.py`'s two measured words: a port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the `_cipath` import below), and `python3 -m rediacc_ci.quality.python_types` works but is the wrong registration, because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

`derivedId` (`gate-header.ts:260`) strips the `check_` prefix and maps `_` to `-`, so this basename derives `check:ci-python-types`, which is the manifest id.

`needs: python-mypy` IS AN ACQUIRABLE NEED, not a placement constraint: `lanes.ts` lists it in ACQUIRABLE and `gate-bind.ts` writes the pip install into the emitted step ahead of this command.
That is the same shape `needs: python-yaml` already has, and it exists because `laneCapabilities` reads what a lane OFFERS from workflow structure and cannot see a `pip install` inside another step's run block.

NO TWIN. This gate was written in Python; there is no bash original to be differential against, which is why no `DRIVEN` table appears here and why `.ci/shadow/` holds no ledger for it.

---- gate ----
step: Python types (mypy)
needs: python-mypy
lane: quality-static
selftest: true
why: ruff does no type inference at all, so the Python half of `tsc --noEmit` did not exist; shrink-only over a frozen baseline of the 935 findings that were already there
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import python_types

if __name__ == "__main__":
    raise SystemExit(python_types.main(sys.argv[1:]))
