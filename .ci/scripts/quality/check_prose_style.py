#!/usr/bin/env python3
"""Run `rediacc_ci.quality.prose_style` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/prose_style.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import prose_style

if __name__ == "__main__":
    _gate_args.parse(
        "check_prose_style.py",
        sys.argv[1:],
        switches=(
            "--selftest",
            "-h",
            "--help",
            "--write",
            "--diff",
            "--write-baseline",
            "--accept-new",
            "--json",
            "--drain",
        ),
        valued=("--scope",),
        positional="<subcommand|path>",
    )
    raise SystemExit(prose_style.main(sys.argv[1:]))
