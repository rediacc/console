#!/usr/bin/env python3
"""FORWARDER to `.claude/hooks/stop/worklist.py`. See README.md beside this file.

`oracles/pre-ask/block-settled-questions.sh:133` runs `python3
"$(dirname "$0")/../stop/worklist.py" --path` to find the worklist store. It is a
SCRIPT invocation, not an import, so this re-executes the live file with the same
argv rather than importing anything: `runpy` under `__main__` makes the live
module's own entry point run, which is what `--path` needs.
"""

import pathlib
import runpy
import sys

_LIVE_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"
sys.path.insert(0, str(_LIVE_DIR))
runpy.run_path(str(_LIVE_DIR / "worklist.py"), run_name="__main__")
