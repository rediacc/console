"""`rediacc_ci.quality.silent_failure_patterns` against the twin's awk program.

WHY A DIFFERENTIAL. This gate's whole behaviour is five awk regexes and one skip-the-next-line state machine, and two independent bugs in exactly that layer kept it matching NOTHING for months (a repo root resolved to `.ci`, and `-v` escape processing that turned the guard pattern into an ERE with empty alternations). A table of expected strings would be a table of what the PORT
does, asserted against itself. Running the real awk and comparing is the only form that can fail for the right reason.

The whole gate is covered by `.ci/shadow/w7p2-silent-failures.observations.jsonl`
over five distinct trees; this file covers the scanner in isolation.
"""

import pathlib

import pytest

from rediacc_ci.quality import silent_failure_patterns as mod
from rediacc_ci.tests import differential as diff

STRICT = "#!/bin/bash\nset -euo pipefail\n"

# The awk program from the twin, with the -v values substituted exactly as the twin passes them. Nothing else is changed.
AWK = r"""
awk -v file="F" \
    -v pipe_head='(aws s3 ls|aws s3api list-objects-v2 +--query|find [^|]|grep [^|]+)' \
    -v sink='[|] *(wc -l|head|tail|awk|jq)' \
    -v guard='[|][|] *(true|echo|return|exit|continue|:)' \
    -v redact_sink='2>&1 *[|] *grep -v' '
    BEGIN { strict = 0; skip_next = 0 }
    /^set [+\-]e/ {
        if ($0 ~ /pipefail/) {
            if ($0 ~ /set -/) strict = 1
            else if ($0 ~ /set \+/) strict = 0
        }
    }
    /# *silent-failure-ok/ { skip_next = 1; next }
    /^[[:space:]]*$/ || /^[[:space:]]*#/ { next }
    {
        if (skip_next) { skip_next = 0; next }
        if (!strict) next
        if ($0 ~ pipe_head && $0 ~ sink) {
            if ($0 !~ guard &&
                $0 !~ /^[[:space:]]*(if|elif|while|until) /) {
                printf "%s:%d: %s\n", file, NR, $0
            }
        }
        if ($0 ~ redact_sink && $0 !~ guard &&
            $0 !~ /^[[:space:]]*(if|elif|while|until) /) {
            printf "%s:%d: %s (redaction-filter sink: capture to a file, redact after, test the head'"'"'s own rc)\n", file, NR, $0
        }
    }
' body.sh
"""

# Every shape the scanner has to get right. The comment names the property.
BODIES = [
    "n=$(aws s3 ls s3://b/p | wc -l)\n",  # class 1, the founding case
    "find . -name x | head -1\n",  # find into head
    "grep foo f | awk '{print}'\n",  # grep into awk
    "aws s3api list-objects-v2  --query 'x' | jq .\n",  # the spaced --query form
    "n=$(find . | wc -l || true)\n",  # guarded
    "n=$(find . | wc -l || echo 0)\n",  # guarded with a value
    "if find . | wc -l; then :; fi\n",  # a condition head is exempt
    "while find . | head -1; do :; done\n",  # so is a while head
    "find . -name x\n",  # a head with no sink
    "cat f | wc -l\n",  # a sink with no risky head
    "# find . | wc -l\n",  # a comment
    "\n\n",  # blank lines
    "wrangler d1 export 2>&1 | grep -v secret\n",  # class 2
    "wrangler export 2>&1 | grep -v secret || true\n",  # class 2, guarded
    "cat f | grep -v secret\n",  # grep -v without the 2>&1
    "# silent-failure-ok: reason\nfind . | wc -l\n",  # waived
    "# silent-failure-ok: r\nfind . | wc -l\nfind . | head -1\n",  # one line only
    "find . | wc -l\nset +euo pipefail\nfind . | head -1\n",  # strict toggled off
    "  find . | wc -l\n",  # indented, still a finding
    "n=$(find . | wc -l)  # trailing comment\n",  # a trailing comment is not a comment line
]


@pytest.mark.parametrize("body", BODIES)
def test_scanner_matches_awk(tmp_path: pathlib.Path, body: str) -> None:
    (tmp_path / "body.sh").write_text(STRICT + body, encoding="utf-8")
    code, out, err = diff.bash_streams(AWK, cwd=str(tmp_path))
    assert code == 0, err
    expected = [line for line in out.split("\n") if line != ""]
    assert mod.scan_text(STRICT + body, "F") == expected


# The file-level pre-filter is a SEPARATE test from the per-line tracker, and the twin's own asymmetry between them is the reason.
PREFILTER = [
    "set -euo pipefail",
    "set -eo pipefail",
    "set -e pipefail",
    "set -euo",
    "set -e",  # no trailing space: does NOT qualify
    "set +euo pipefail",
    "  set -euo pipefail",  # indented: the grep is anchored
    "echo hi",
    "",
]


@pytest.mark.parametrize("line", PREFILTER)
def test_prefilter_matches_grep(tmp_path: pathlib.Path, line: str) -> None:
    (tmp_path / "f.sh").write_text(line + "\n", encoding="utf-8")
    script = r"""grep -qE '^set [+\-]([euo]*pipefail|euo +pipefail|e |eu |eo |euo)' f.sh"""
    code, _out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    assert mod.file_is_strict(line + "\n") is (code == 0)


def test_the_inherited_missing_floor_is_pinned(tmp_path: pathlib.Path) -> None:
    """A corpus that collapsed to zero files yields NO findings, and that is a defect.

    The twin has no anti-vacuity floor: `find` matching nothing produces "No unguarded pipefail-risk pipelines found" and exit 0. The port preserves that because a port that changes the verdict is not a port. This assertion pins the CURRENT answer so the day the twin grows a floor, this file goes red and names the module that has to follow it.
    """
    assert mod.collect(tmp_path) == []
