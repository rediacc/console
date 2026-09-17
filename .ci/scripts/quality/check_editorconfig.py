#!/usr/bin/env python3
"""Entry point for the ported EditorConfig gate. Logic is in the package.

THIS ENTRY POINT IS DELIBERATELY HEADERLESS, and that is a carried property rather than an omission. `.ci/scripts/quality/check-editorconfig.sh` has NO `---- gate ----` block at all: an awk range over the twin returns ZERO lines and `bind()` on it returns null. A headerless twin gets a headerless entry point, because inventing a header here would be a new declaration and not a
moved one.

WHY THE TWIN HAS NO HEADER IS ALSO ON THE RECORD, which is what makes the absence safe to preserve. `scripts/gate-bind.ts:167` names this exact file as one of the two known reasons `--extract` refuses to write a header: the gate enumerates with `--recurse-submodules`, so `inferredNeeds` resolves
`{submodules}`, and its registered lane does not check submodules out. A header
written here would not bind, and the binder says so rather than writing one. Confirmed on this tree: `inferredNeeds` on the twin returns `[submodules]` while `bind()` returns null, so the need is inferred and never resolved.

THAT ASYMMETRY DOES NOT MOVE WITH THE FILE, and it is worth saying which way it goes. `inferredNeeds` on THIS entry point returns `[]`, because the only mention of submodules in it is inside a docstring and `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both files nonetheless bind to null, so the resolved need set is identical (there is none) and the
registration is unaffected in either direction.

Contract section 5d still puts the entry point here, and the two measured reasons in `check_npmrc.py` still apply: a port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.editorconfig` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7).

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-editorconfig.sh   -> exit 0
    .ci/scripts/quality/check_editorconfig.py   -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 277 bytes, sha256 7ac7bc44787c114e...

NO NORMALISATION WAS APPLIED and none was needed. The twin was first run TWICE
against an unchanged tree to establish byte-stability against itself; it is
stable on both streams despite being a 26-second whole-repository sweep.

DRIVEN RED AS WELL, and the plant had to go in the REAL TREE because this gate's root is script-location-derived with no override: `get_repo_root` (`.ci/scripts/lib/common.sh:205`) walks up three levels from the library's own directory and honours no environment variable, so a fixture root would move the port and not the twin. The plant is therefore a single CRLF-terminated line
appended to a tracked file, and the file chosen is one this batch owns (`.ci/scripts/quality/check_shell_size.py`) rather than a neighbour's.

THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN: the gate scans git-TRACKED files only, so `git ls-files --error-unmatch` was used to confirm the plant site is tracked, and a `grep -c` for a carriage return confirmed the CR is really in the bytes. A plant in an untracked file would have fired nothing and said nothing about the gate.

    both sides -> exit 1, stdout BYTE-IDENTICAL (43 bytes), stderr
    BYTE-IDENTICAL (388 bytes, sha256 14bf31eab11bd79d...):

    Files with CRLF line endings (1):
    Found 1 editorconfig violation(s)

The plant was reverted from a `cp` backup, verified back at its pre-plant sha256
with `sha256sum -c`, and `git status --porcelain` diffed against its pre-plant
capture with no difference.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-editorconfig.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import editorconfig

if __name__ == "__main__":
    raise SystemExit(editorconfig.main(sys.argv[1:]))
