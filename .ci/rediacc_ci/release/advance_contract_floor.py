#!/usr/bin/env python3
"""Port of `.ci/scripts/release/advance-contract-floor.sh`.

Advances the release-contract-floor RATCHET to the oldest cli `.released` sentinel on R2, and writes the new value into the tracked file in the working tree. It never commits and never pushes: a local release cannot push `main`, so the changed file rides the next PR as an ordinary commit.

Usage: advance_contract_floor.py (no arguments; everything comes from the environment, exactly as the workflow block that used to hold this code did)

WHY A RATCHET AT ALL. The release-state bijection gate
(`Committed(v) <=> sentinel AND tag`) excludes tags older than the oldest
`.released` sentinel on R2, because pre-contract releases never had one. That floor is DATA-DERIVED, so an accidental scrub of every cli sentinel would drop the floor to nothing and silently turn the gate into a no-op. Recording the observed floor in a committed file gives the gate a high-water mark that a scrub cannot walk backwards.

MONOTONIC, AND THAT IS THE WHOLE SAFETY PROPERTY. It writes only when the observed oldest sentinel is STRICTLY NEWER than what the file already holds, so a retry or a no-op run leaves the tree clean and skips the commit entirely. `decide()` below is that rule as a pure function, so a test can drive every ordering without R2, a git remote, or a filesystem.

NO GIT. The tests put a recording fake `git` on a scratch PATH and assert that it saw no call at all, on an advance and on a no-op. The fixture root is a temporary directory, never this checkout.

`rsv_list_sentinels` IS NOT RE-PORTED. `core.release_state_validator.list_sentinels` already is that function, including its `tr '\\t' '\\n'` split (the aws `--output text` packing that makes there be records at all) and its two-stage sed-then-grep filter. Re-deriving it here would be a second answer to a question that has one. Two spellings differ and neither is reachable from
this caller:

  * `RSV_BUCKET` is captured at SOURCE time from `${RELEASES_BUCKET:-...}`,
    while `release_state_validator.bucket()` reads it per call. Nothing between
    the two points changes the variable.
  * The twin pipes `rsv_list_sentinels cli | sort -uV | head -1`, re-sorting an
    already-`sort -uV`-ed list. `list_sentinels` returns that same sorted unique
    list, so `[0]` is the same element.

THE DEFECT THIS PORT REPRODUCES, AND IT IS THE VACUITY CLASS.
`rsv_list_sentinels` swallows aws's stderr (`2>/dev/null`) and wraps its whole
pipeline in `{ ... } || true`, so A FAILED PROBE IS INDISTINGUISHABLE FROM AN
EMPTY BUCKET. Driven against the real twin on 2026-09-13 with an `aws` that exits 255: stdout is

    ::notice::no cli sentinels on R2; skipping ratchet advance

and the exit code is 0. So expired credentials, a DNS fault and a genuinely scrubbed bucket all read as a green no-op on the script whose entire reason for existing is to defend against a scrub. It is reproduced rather than repaired because the acceptance rule for this wave is agreement with the live twin, and `release_state_validator.py` already records the same defect at the
library level (its DEFECT 2). `PROBE_FAILURE_READS_AS_EMPTY_BUCKET` names it and the differential pins it in both directions.

TWO DIVERGENCES, BOTH IN REFUSAL TEXT NOBODY PARSES, plus one deliberate change (no git, so `GIT_BOT_NAME` / `GIT_BOT_EMAIL` are no longer demanded):

  1. The five `${VAR:?msg}` refusals are BASH diagnostics carrying the twin's
     own path and LINE NUMBER (`...advance-contract-floor.sh: line 38:
     CLOUDFLARE_R2_ACCESS_KEY_ID: advance-contract-floor.sh:
     CLOUDFLARE_R2_ACCESS_KEY_ID must be set`). Reproducing a line number would
     pin this port to the twin's layout, so it prints
     `rediacc_ci.release.advance_contract_floor: <VAR> must be set`. Same stream, same exit 1,
     same order. Identical ruling to `release/tag_submodules.py`.
  2. `${VAR:?}` fires on set-but-EMPTY as well as unset, and so does this.

K=5 LEDGER: `.ci/shadow/w7p6-advance-contract-floor.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

from rediacc_ci import log
from rediacc_ci.core import awscli
from rediacc_ci.core import release_state_validator as rsv

SELF = "rediacc_ci.release.advance_contract_floor"

# `.ci/config/release-contract-floor.txt`, relative to the repository root (:50). Spelled here rather than imported from `release_state_validator` (which carries the same path as `FLOOR_FILE_REL`) because the twin spells it locally too, and the two files agreeing is a fact a test should be able to assert rather than a fact the code assumes.
FLOOR_FILE = ".ci/config/release-contract-floor.txt"

# `grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' "$FLOOR_FILE" | head -1` (:55). Strict: a comment, a blank line or a prerelease in the file is simply not the floor, and the result is the SAME as an absent file -- see `<unset>` below.
FLOOR_LINE_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")

# `${current:-v0.0.0}` (:61-62) and `${current:-<unset>}` (:63, :66). Two
# different defaults for the same empty value: one for the comparison, one for the message. Kept apart because they are.
NO_FLOOR_COMPARES_AS = "v0.0.0"
NO_FLOOR_READS_AS = "<unset>"

# The product prefix the ratchet is derived from (:56). Only `cli` sentinels count; the floor is about the CLI release contract.
PRODUCT = "cli"

# The R2 environment the twin demands, IN ITS ORDER (:38-40); its two git-identity variables went with the commit. Order is observable: only the first missing one is ever named.
REQUIRED_ENV = (
    "CLOUDFLARE_R2_ACCESS_KEY_ID",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
    "CLOUDFLARE_R2_ENDPOINT",
)

# The defect named in the module docstring, as a constant so a test can assert it by name instead of restating the sentence.
PROBE_FAILURE_READS_AS_EMPTY_BUCKET = True


def console_root() -> pathlib.Path:
    """`cd "$(get_repo_root)"` (:44), from this file's own location.

    `get_repo_root` derives from COMMON.SH's location (`.ci/scripts/lib/../../..`), not from the caller's. This module sits at `<root>/.ci/rediacc_ci/release/`, one level deeper than the twin, so `parents[3]` lands on the same directory.

    `rediacc_ci.paths.repo_root()` is deliberately not used: it honours `$REDIACC_CI_ROOT` and neither the twin nor common.sh honours anything, so a fixture that moved one and not the other would diverge for a reason that has nothing to do with this script.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def read_floor(text: str) -> str:
    """The committed floor, or `""`. `grep -E ... | head -1` (:55).

    An absent file, an empty file, a file of comments and a file whose only version is a prerelease all answer the same way, and the twin then prints `<unset>` for all four. Pure so the four can be driven without a tree.
    """
    for line in text.split("\n"):
        if FLOOR_LINE_RE.match(line):
            return line
    return ""


def newer_of(left: str, right: str) -> str:
    """`printf '%s\\n%s\\n' "$a" "$b" | sort -V | tail -1` (:61).

    `sort -V` then `tail -1` is "the larger under version order", and on a tie the two strings are equal anyway so which copy survives cannot be observed. `rsv.version_key` is the `sort -V` key this repo already uses; both inputs here are strict semver or the `v0.0.0` literal.
    """
    return right if rsv.version_key(right) > rsv.version_key(left) else left


def decide(current: str, oldest: str) -> tuple[bool, str]:
    """The ratchet rule (:57-66). Returns `(should_advance, message)`.

    THE WHOLE SAFETY PROPERTY IS HERE, so it is a pure function rather than four branches tangled with I/O:

      no observed sentinel  -> never advance, and say so with the ::notice::
                               that this run saw nothing. (Which, per the
                               module docstring, is ALSO what a failed probe
                               looks like.)
      observed <= current   -> never advance. The ratchet only goes up, which
                               is what a scrub cannot walk backwards.
      observed >  current   -> advance.

    `current` is compared as `v0.0.0` when empty and PRINTED as `<unset>`, which is the twin using two different defaults for one value.
    """
    if not oldest:
        return False, "::notice::no cli sentinels on R2; skipping ratchet advance"
    compare_to = current or NO_FLOOR_COMPARES_AS
    shown = current or NO_FLOOR_READS_AS
    if newer_of(compare_to, oldest) == compare_to:
        return False, "::notice::ratchet already at %s (>= observed %s); no change" % (
            shown,
            oldest,
        )
    return True, "::notice::advancing ratchet %s -> %s" % (shown, oldest)


def _require_aws() -> bool:
    """`require_cmd aws`, resolved through `core.awscli`, with the same one-line refusal."""
    try:
        awscli.require()
    except awscli.AwsCliMissingError as exc:
        log.error(str(exc))
        return False
    return True


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments and ignores anything it is given

    if not _require_aws():
        return 1

    for name in REQUIRED_ENV:
        if not os.environ.get(name):
            # DIVERGENCE 1: bash prints its own path and line number here.
            print("%s: %s must be set" % (SELF, name), file=sys.stderr, flush=True)
            return 1

    root = console_root()

    # :46-48. The aws CLI reads AWS_*; the workflow passes CLOUDFLARE_R2_*.
    os.environ["AWS_ACCESS_KEY_ID"] = os.environ["CLOUDFLARE_R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
    os.environ["AWS_DEFAULT_REGION"] = "auto"

    floor_path = root / FLOOR_FILE
    if not floor_path.is_file():
        # STDOUT, and exit 0. A missing floor file is not an error: the ratchet simply has nothing to compare against yet.
        print("::warning::%s not present; skipping ratchet advance" % FLOOR_FILE, flush=True)
        return 0

    current = read_floor(floor_path.read_text(encoding="utf-8"))
    sentinels = rsv.list_sentinels(PRODUCT)
    oldest = sentinels[0] if sentinels else ""

    advance, message = decide(current, oldest)
    print(message, flush=True)
    if not advance:
        return 0

    floor_path.write_text(oldest + "\n", encoding="utf-8")
    print(
        "::notice::wrote %s in the working tree; commit it with the next PR" % FLOOR_FILE,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
