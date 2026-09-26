#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/set-image-tags.sh` (37 lines).

Derive the base image tag into `$GITHUB_ENV`, then override the two per-image tags with the values the `initialize` job resolved, appending the `-amd64` suffix the fast single-arch build publishes. The twin's header owns the why; it is not restated here.

SOLE IMPLEMENTATION. The bash twin is deleted; `.github/workflows/ci.yml:1113` runs this module, and the twin's observable behaviour is frozen in `.ci/rediacc_ci/tests/goldens/set-image-tags/`.

Ledger: `.ci/shadow/w7p6-set-image-tags.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-set-image-tags --assert --k 5`).

-----------------------------------------------------------------------------
THE SIBLING IS CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
The twin was the one live caller of `derive-image-tag.sh`, and the whole of its first half was that call with two arms, so the two were retired together. `rediacc_ci.ci.derive_image_tag` is
already ported and already carries its own K=5 ledger
(`.ci/shadow/w7p6-derive-image-tag.observations.jsonl`), so this module invokes that module rather than re-deriving anything: a second implementation of the
`--sort=-v:refname` ladder is exactly the divergence the campaign exists to
avoid.

IN PROCESS, NOT AS A SUBPROCESS, and the two observable consequences are stated rather than discovered:

  * `main()` returns a status where the twin's `set -e` would kill the script,
    so the caller returns it unchanged and the trailing `log_info` is skipped on
    both sides.
  * The two diagnostics `derive_image_tag` prints with `sys.argv[0]` in them --
    the missing `--version` value, and a tag build with `GITHUB_REF_NAME` unset
    -- now carry THIS module's name where the twin carried the sibling's path.
    The first is unreachable from here (the argument is always supplied with a
    value). The second is reachable, and the differential normalises the program
    name exactly as `test_ci_derive_image_tag.py` already does for the same
    reason.

-----------------------------------------------------------------------------
DEFECT E -- WITH `$GITHUB_ENV` UNSET, THE SCRIPT REPORTS SUCCESS HAVING SET
NOTHING
-----------------------------------------------------------------------------
    $ IMAGE_TAG=v1.2.3 WEB_TAG=web-abc RENET_TAG=renet-abc \\
        python3 -m rediacc_ci.ci.set_image_tags
    ⚠ GITHUB_ENV not set, skipping --env-file
    v1.2.3
    ✓ Image tags set (web=web-abc renet=renet-abc)
    exit=0

The last line is a claim, and in this run it is false: no tag was set anywhere. The one warning comes from the SIBLING, is about the sibling's own half of the work, and says nothing about the two overrides this script exists to write. The same shape as `generate_tag`'s DEFECT G, one script further down the chain. Reproduced, not repaired: `.ci/scripts/ci/` is not this writer's to
change. `GITHUB_ENV_IS_SILENTLY_OPTIONAL` names it so a test can assert it by name.

-----------------------------------------------------------------------------
DEFECT F -- THE SUCCESS LINE REPORTS THE INPUTS, NOT WHAT WAS WRITTEN
-----------------------------------------------------------------------------
`log_info "Image tags set (web=${WEB_TAG:-<derived>} ...)"` prints the value it
was GIVEN, without the `-amd64` suffix it just appended to the file. So the file
says `WEB_TAG=web-abc-amd64` and the log says `web=web-abc`, and the two
disagree about the one fact the step exists to establish. Byte-for-byte reproduced.

-----------------------------------------------------------------------------
`[[ -n ... ]] && echo` IS NOT A `set -e` HAZARD HERE, AND IT IS WORTH SAYING WHY
-----------------------------------------------------------------------------
An `A && B` list whose A fails does not trip `set -e`, because A is not the last command of the list. It would be a hazard if the list were the last command of the script or of a function, where its status becomes the caller's; here `log_info` follows it, so an empty `WEB_TAG` skips the write and the script continues. Driven, both arms.
"""

from __future__ import annotations

import os
import sys

from rediacc_ci import log
from rediacc_ci.ci import derive_image_tag
from rediacc_ci.core import common

#: `echo "WEB_TAG=${WEB_TAG}-amd64" >>"$GITHUB_ENV"` and the RENET line under it.
#: Bash names these when the append fails, so they are observable output.
WEB_TAG_LINE = 33
RENET_TAG_LINE = 34

#: The suffix the fast single-arch build publishes (twin :30-31).
ARCH_SUFFIX = "-amd64"

#: DEFECT E, named so a test can assert it by name rather than by message text.
GITHUB_ENV_IS_SILENTLY_OPTIONAL = "GITHUB_ENV"

#: The two names overridden here, in the twin's order. A TABLE FOR READERS AND
#: TESTS, deliberately NOT a loop the code below runs: the twin is two literal
#: lines, and reading the environment through a loop variable would make every
#: read of it opaque to `check:ci-python-env-registry`, which records the
#: EXPRESSION rather than the name when the key is not a literal.
OVERRIDES = (("WEB_TAG", WEB_TAG_LINE), ("RENET_TAG", RENET_TAG_LINE))

#: `${WEB_TAG:-<derived>}` (twin :37).
DERIVED_PLACEHOLDER = "<derived>"


def derive_argv(image_tag: str) -> list[str]:
    """The two arms of twin :24-28, as the argv `derive_image_tag` receives.

    Pure, and exported, because the whole of the first half of this script is the choice between these two lists and it is worth testing without a
    subprocess. Note that `[[ -n "${IMAGE_TAG:-}" ]]` treats UNSET and EMPTY
    alike: both fall to the auto-derive arm.
    """
    if image_tag:
        return ["--version", image_tag, "--env-file"]
    return ["--env-file"]


def append_override(name: str, value: str, github_env: str, line: int) -> None:
    """One `echo "<name>=<value>-amd64" >>"$GITHUB_ENV"`.

    A failing append is `set -e` with bash's own message naming the file and the line, not a traceback.
    """
    try:
        with open(github_env, "a", encoding="utf-8") as handle:
            handle.write("%s=%s%s\n" % (name, value, ARCH_SUFFIX))
    except OSError as err:
        sys.stderr.write("%s: line %d: %s: %s\n" % (sys.argv[0], line, github_env, err.strerror))
        sys.stderr.flush()
        raise SystemExit(1) from err


def main(argv: list[str]) -> int:
    del argv  # The twin reads no arguments; everything arrives through the env.

    os.chdir(common.repo_root())

    status = derive_image_tag.main(derive_argv(os.environ.get("IMAGE_TAG", "")))
    if status != 0:
        # `set -e` on the sibling. The twin prints nothing further, and neither does this: the sibling has already said what went wrong.
        return status

    github_env = os.environ.get("GITHUB_ENV", "")
    if github_env:
        # Twin :33-34, one statement each, in that order.
        if os.environ.get("WEB_TAG", ""):
            append_override("WEB_TAG", os.environ.get("WEB_TAG", ""), github_env, WEB_TAG_LINE)
        if os.environ.get("RENET_TAG", ""):
            append_override(
                "RENET_TAG", os.environ.get("RENET_TAG", ""), github_env, RENET_TAG_LINE
            )

    log.info(
        "Image tags set (web=%s renet=%s)"
        % (
            os.environ.get("WEB_TAG", "") or DERIVED_PLACEHOLDER,
            os.environ.get("RENET_TAG", "") or DERIVED_PLACEHOLDER,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
