#!/usr/bin/env python3
"""Control harness for block_user_only_command_shell_write: the shell half of "no command or skill is user-only".

The cases and the runner live in `test-block_user_only_command.py` beside this file, so the two halves are judged by one set of rules; this file runs the shell cases through dispatch.py in both directions, then plants the guard's DEFECT and requires the run to fail.

    test-block_user_only_command_shell_write.py
"""

import importlib.util
import pathlib
import sys

SHARED = pathlib.Path(__file__).resolve().with_name("test-block_user_only_command.py")


def _shared():
    spec = importlib.util.spec_from_file_location("user_only_harness", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % SHARED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    sys.exit(_shared().main(("block_user_only_command_shell_write",)))
