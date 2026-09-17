"""Port of `.ci/scripts/autopilot/linked-sub-prs.sh`.

Turns a console PR body back into the submodule PRs it links, one `<owner>/<repo> <number>` per line. PURE: no network, no git, no `gh`.

WHY IT EXISTS, in the twin's words: `check-submodule-branches.sh` reds the console PR while a LINKED submodule PR carries unresolved review threads, and the autopilot's review machinery only ever saw console's own threads. A round would answer every console finding and still sit red on a gate whose complaint lived in another repository.

THE OTHER HALF OF THE PAIR IS `submodule-prs.sh`, WHICH WRITES WHAT THIS READS. The twin says so ("the same links submodule-prs.sh writes there"), and the coupling is the reason the three accepted spellings below are a CONTRACT and not an implementation detail: `submodule-prs.sh` composes the body block, `check-submodule-branches.sh` decides a body is acceptable, and this script
parses it back. A spelling added to one and not the others is a link that is written and never read, or read and never gated. This port does not touch `submodule-prs.sh`; it records the coupling so a future edit to either one is made knowing the other exists.

THE REPO ALLOWLIST IS THE SECURITY BOUNDARY, and it is `SUB_REPOS` below. A PR body is operator-authored on an armed PR but is still text, and this output decides which repositories the gate will fetch review comments from and hand to a model. Only the four submodules are recognised; a link to anything else, however well-formed, is ignored. The list is held to
`check-submodule-branches.sh`'s own hardcoded map, so a submodule missing there is invisible here too, exactly as the twin intends.

-----------------------------------------------------------------------------
WHAT `grep` DOES THAT A NAIVE PORT WOULD NOT, all four reproduced
-----------------------------------------------------------------------------

1. THE PR NUMBER IS TRUNCATED, NOT REJECTED, AT EIGHT DIGITS. `[0-9]{1,7}`
   matches the first seven digits of `#12345678`, and the second grep then
   reads `1234567` off the end of that match. So an absurd digit run does not
   refuse; it silently becomes a different, plausible PR number. Driven against
   GNU grep 3.12 on 2026-09-10 rather than reasoned about. Preserved here
   because changing it would change which PRs the caller fetches.

2. A BODY CONTAINING A NUL BYTE PRODUCES NOTHING, LOUDLY. GNU grep classifies
   such a file as binary, suppresses every match, writes
   `grep: <path>: binary file matches` to STDERR and still exits 0. The twin's
   `|| true` then swallows nothing (there was no failure), the pipeline yields
   no numbers, and the script exits 0 having reported no links at all. That is
   a silent-empty shape, so the port reproduces both the suppression AND the
   stderr line: a caller that sees no links deserves the one sentence that says
   why. Note the LOCALE dependency, which is the twin's and not this port's: in
   a UTF-8 locale GNU grep also calls a file with an encoding error binary, so
   the same body can yield links under `LC_ALL=C` and none under `en_US.UTF-8`.
   This port implements the `LC_ALL=C` rule (NUL only), which is the locale
   every caller in this tree sets.

3. `sort -un` IS NUMERIC-UNIQUE, SO `#007` AND `#7` ARE ONE PR. They compare
   equal numerically, `-u` keeps the first of the equal run, and the string
   that survives is whichever the sort saw first. `_sort_un` reproduces that
   with a stable sort keyed on the integer value, and the SURVIVING TEXT is
   printed verbatim, leading zeros and all. Driven both ways round on
   2026-09-10: `007\n7` keeps `007`, `7\n007` keeps `7`.

4. THE THREE LINK SPELLINGS ARE MATCHED PER SUBMODULE, IN DECLARATION ORDER,
   and each name gets its own independent dedup. So a body linking `renet#3`
   and `account#3` prints both, while one linking `renet#3` twice prints one.

-----------------------------------------------------------------------------
THE ONE KNOWN DIVERGENCE, PINNED BY A TEST
-----------------------------------------------------------------------------
`--owner` IS INTERPOLATED INTO A REGULAR EXPRESSION, in the twin and therefore here: `re.escape` would be a different program, matching owners the twin does not. An owner carrying an unbalanced bracket is consequently invalid regex syntax, where the twin gets grep's own diagnostic (`grep: Unmatched ( or \\(`, exit 2, four times, all swallowed by `|| true`) and this port gets
Python's. Exit code, stdout and the empty result agree; only the diagnostic text differs, and `test_divergence_an_owner_that_is_not_valid_regex` asserts exactly that so nobody later "fixes" the port into refusing.

Not a security hole in either implementation: an owner that fails to compile matches NOTHING, which is the safe direction, and the allowlist of four names is applied whatever the owner is.

-----------------------------------------------------------------------------
UNREACHABLE CODE IN THE TWIN, REPORTED RATHER THAN COPIED
-----------------------------------------------------------------------------
The twin's inner loop ends `[[ -n "$n" ]] && printf ...`, whose failure would be the `while` loop's exit status and, under `set -e` inside a `for` body, would end the script with 1 before the remaining submodules were scanned. It cannot fire: `sort` only ever emits the non-empty digit runs the second grep produced. Left as a note because the guard reads as though the empty case
were expected, and a future edit that makes it reachable inherits a wrong exit.

K=5 LEDGER: `.ci/shadow/w7p6-linked-sub-prs.observations.jsonl`.
"""

from __future__ import annotations

import re
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "linked-sub-prs.py"

USAGE = "usage: linked-sub-prs.sh --body <file> [--owner <owner>]"

# `SUB_REPOS=(renet account elite homebrew-tap)`. THE ALLOWLIST. Order is
# output order, and it is the order `check-submodule-branches.sh` declares.
SUB_REPOS = ("renet", "account", "elite", "homebrew-tap")

# `${ARG_OWNER:-rediacc}`.
DEFAULT_OWNER = "rediacc"

# The twin's second grep, verbatim: the trailing digit run of a match, capped
# at seven characters because that is what an anchored `[0-9]{1,7}` can span.
TRAILING_NUMBER = re.compile(rb"[0-9]{1,7}$")


def link_pattern(owner: str, name: str) -> bytes:
    """The twin's first grep expression for one submodule, as bytes.

    `(https://github\\.com/)?<owner>/<name>(/pull/|#)[0-9]{1,7}` -- the full
    URL, `owner/repo#N` and `owner/repo/pull/N`. BYTES because grep matches bytes: a PR body is whatever GitHub stored, and a port that decoded it would refuse input the twin passes through.
    """
    return (
        rb"(https://github\.com/)?"
        + owner.encode("utf-8", "surrogateescape")
        + b"/"
        + name.encode("utf-8", "surrogateescape")
        + rb"(/pull/|#)[0-9]{1,7}"
    )


def is_binary(body: bytes) -> bool:
    """GNU grep's binary test under `LC_ALL=C`: a NUL byte anywhere in the file.

    See point 2 of the module docstring for the locale caveat. Deliberately not a heuristic over the first N bytes: grep reads the whole buffer it has, and the twin's bodies are small enough that grep has all of it at once.
    """
    return b"\x00" in body


def _sort_un(numbers: list[bytes]) -> list[bytes]:
    """`LC_ALL=C sort -un`: numeric order, first of each equal run survives.

    Python's `sorted` is stable, so keying on `int` and keeping the first occurrence of each key reproduces GNU sort's `-u` exactly, including the leading-zero case that makes two different STRINGS one PR.
    """
    seen: set[int] = set()
    out: list[bytes] = []
    for value in sorted(numbers, key=int):
        key = int(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def numbers_for(body: bytes, owner: str, name: str) -> list[bytes]:
    """Every PR number this body links for one submodule, sorted and deduped.

    The pipeline, stage for stage: first grep for the link, second grep for the trailing number, `sort -un`. An unparseable owner yields NOTHING (see the divergence note in the module docstring), which is what an invalid regex costs the twin too.
    """
    try:
        pattern = re.compile(link_pattern(owner, name))
    except re.error:
        return []
    found = [TRAILING_NUMBER.search(m.group(0)) for m in pattern.finditer(body)]
    return _sort_un([m.group(0) for m in found if m is not None])


def scan(body: bytes, owner: str, path: str, stderr=None) -> list[bytes]:
    """Every output line, in the twin's order: one submodule at a time.

    `path` and `stderr` exist for the binary-file diagnostic, which names the file exactly as it was given on the command line because grep does.
    """
    stream = sys.stderr if stderr is None else stderr
    binary = is_binary(body)
    lines: list[bytes] = []
    for name in SUB_REPOS:
        matched = numbers_for(body, owner, name)
        if not matched:
            continue
        if binary:
            # grep prints this ONCE PER INVOCATION THAT MATCHED, and the twin invokes grep once per submodule, so a binary body linking three submodules produces three lines. Exit stays 0.
            print("grep: %s: binary file matches" % path, file=stream, flush=True)
            continue
        prefix = ("%s/%s " % (owner, name)).encode("utf-8", "surrogateescape")
        lines.extend(prefix + number for number in matched)
    return lines


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        # parse_args QUIRK 3: `printf -v` refuses a key that is not a valid shell identifier and takes the twin down with exit 2.
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    body_path = args.get("ARG_BODY", "")
    owner = args.get("ARG_OWNER") or DEFAULT_OWNER

    if not body_path:
        log.error(USAGE)
        return 2

    try:
        common.require_file(body_path)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    with open(body_path, "rb") as handle:
        body = handle.read()

    out = sys.stdout.buffer
    for line in scan(body, owner, body_path):
        out.write(line + b"\n")
    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
