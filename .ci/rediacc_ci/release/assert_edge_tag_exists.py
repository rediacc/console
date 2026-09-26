#!/usr/bin/env python3
"""Port of `.ci/scripts/release/assert-edge-tag-exists.sh`.

Asserts that the version an R2 channel pointer advertises is a version that REALLY EXISTS, before `promote-stable.yml` writes anything. On 2026-08-24 `cli/edge/manifest.json` advertised 1.3.1 while no `v1.3.1` tag, no GitHub Release and no `cli/v1.3.1/.released` existed, and promote-stable would have copied those bytes to stable and to the `:stable` Docker tag FIRST and only then
failed on `ref: v1.3.1`, leaving a half-applied release across three regions.

Usage: assert_edge_tag_exists.py --version 1.3.0 (or a bare `v1.3.0`)

THREE INDEPENDENT ORACLES, AND THE PORT KEEPS THEM INDEPENDENT. `gh api repos/<repo>/git/ref/tags/<tag>` answers for the git tag, `gh release view` answers for the Release, and `aws s3api head-object` answers for the R2 sentinel. Each has its own failure mode and its own probe function, and all three run even after one of them has already failed (`judge ... || true`), so one run
names every missing piece rather than the first one.

"COULD NOT TELL" IS A FAILURE, NOT A PASS, and that is the whole design. A 404 CONFIRMS absence; a 403, a 5xx, a DNS failure or `NoCredentials` mean the check did NOT RUN. `FAILED` and `COULD_NOT_TELL` are tracked separately here exactly as they are there, because the two states need OPPOSITE advice: the twin's own comment records the cost of conflating them, when a NoCredentials
failure printed "cut the release, then Backfill Release Sentinel" at an operator whose sentinel was already fine.

THE THREE PROBE VERDICTS ARE STRINGS, NOT AN ENUM, and `judge()` still carries the twin's unreachable `*)` INTERNAL arm. `core.release_state_validator.Probe` exists and is deliberately NOT used: it collapses to three states with no detail, and the detail (`unknown:<one-line of the tool's own output>`) is the only thing that tells an operator WHICH way the probe failed. Reproducing
the string protocol is also what keeps the INTERNAL arm reachable-in-principle, so a future edit that invents a fourth verdict is reported rather than silently treated as a pass.

`one_line()` KEEPS ITS TRAILING SPACE, AND THAT IS NOT AN OVERSIGHT. The twin is `tr '\\n' ' ' | sed 's/ */ /g'` fed by a here-string, and a bash here-string ALWAYS appends a newline, so the final newline becomes a space that no later step removes (command substitution strips newlines, not spaces). Driven against the real twin on 2026-09-13: the COULD NOT TELL line ends `...not
accessible by integration ` with a space before the newline. A port that tidied that away would be byte-different on every could-not-tell line, which is the branch this whole script exists for.

`aws` READS `AWS_*` AND THE WORKFLOW PASSES `CLOUDFLARE_R2_*`. The twin bridges the two names at :90-91 and its comment records what happened when it did not: `head-object` died on NoCredentials, the sentinel probe answered `unknown`, and promote-stable failed all 7 runs from 2026-08-27 onward, never once green. The export is reproduced here, into `os.environ`, before any probe
runs.

FOUR DIVERGENCES, ALL IN REFUSAL TEXT NOBODY PARSES, NONE IN A VERDICT:

  1. `${CLOUDFLARE_R2_ENDPOINT:?...}` is a BASH diagnostic carrying the twin's
     own path and LINE NUMBER:
     `.ci/scripts/release/assert-edge-tag-exists.sh: line 82: CLOUDFLARE_R2_ENDPOINT:
      assert-edge-tag-exists.sh: CLOUDFLARE_R2_ENDPOINT must be set`
     Reproducing a line number would pin this port to the twin's current
     layout, so it prints `assert-edge-tag-exists.py: <VAR> must be set`
     instead. Same stream, same exit 1, same position in the sequence. This is
     the same ruling `release/tag_submodules.py` and `infra/verify_ssh.py`
     already made for their `${VAR:?msg}` twins.
  2. The `--help` line interpolates `$0`, and the two files cannot share a
     name. The rest of the text is identical, and it goes to STDOUT with exit 0
     in both.
  3. Every self-naming message says `assert-edge-tag-exists.sh` because the
     twin's literals say so. Kept verbatim rather than "corrected" to `.py`:
     these are the bytes the differential compares, and the twin is the live
     script.
  4. common.sh's loggers use `echo -e`, which interprets backslash escapes IN
     THE MESSAGE, and the COULD NOT TELL line interpolates the tool's own
     output into that message. `rediacc_ci.log` formats the message as data
     (see its module docstring). A `gh` error containing a literal backslash-n
     therefore prints a newline through the twin and two characters here. The
     differential asserts BOTH directions so nobody "fixes" it later.

DEFECT IN THE TWIN, REPRODUCED AND REPORTED RATHER THAN FIXED (the acceptance rule for this wave is agreement with the live script):

  `assert-edge-tag-exists.sh --version` WITH NO VALUE EXITS 1 IN TOTAL SILENCE.
  The arm is `VERSION="${2:-}"; shift 2`, and with only one argument left
  `shift 2` fails; `set -e` -- switched on by common.sh:11, which this script
  sources despite its own `set -uo pipefail` -- kills the run THERE, before the
  `if [[ -z "$VERSION" ]]` that was written to handle exactly this. Driven
  2026-09-13: zero bytes on stdout, zero on stderr, exit 1. That is
  indistinguishable from a probe genuinely refusing to promote, on a script
  whose entire job is to be a loud no-op. `SHIFT2_UNDERFLOW_IS_SILENT_EXIT_1`
  below names it, `main()` reproduces it, and the differential pins it.

K=5 LEDGER: `.ci/shadow/w7p6-assert-edge-tag-exists.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from rediacc_ci import log

SELF = "assert-edge-tag-exists.py"

# The name the twin's own messages carry. NOT `SELF`: these strings are compared byte-for-byte against the live script, which is the `.sh`.
TWIN = "assert-edge-tag-exists.sh"

# `^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$` (:74). LOOSER than the strict semver every sibling uses: a prerelease or build suffix is accepted here, because a channel pointer may legitimately advertise one and the question is whether it EXISTS, not whether it is promotable.
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$")

# `${GITHUB_REPOSITORY:-rediacc/console}` (:92) and
# `${RELEASES_BUCKET:-rediacc-releases}` (:93). `:-` fires on unset OR empty.
DEFAULT_REPO = "rediacc/console"
DEFAULT_BUCKET = "rediacc-releases"

# The three environment variables `${VAR:?...}` demands, IN THE TWIN'S ORDER
# (:82-84). Order is observable: only the first missing one is ever named.
REQUIRED_ENV = (
    "CLOUDFLARE_R2_ENDPOINT",
    "CLOUDFLARE_R2_ACCESS_KEY_ID",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
)

# The `grep -qE` that decides "provably absent" versus "could not tell", one per probe. Each is the twin's pattern verbatim.
#
# `probe_gh_release`'s pattern carries `release not found|^release not found`, where the second alternative is subsumed by the first and matches nothing the first does not. Kept as written: it is dead in the twin too, and rewriting it here would be the port quietly disagreeing about what the twin tests.
GH_API_ABSENT = re.compile(r"HTTP 404|Not Found")
GH_RELEASE_ABSENT = re.compile(r"HTTP 404|Not Found|release not found|^release not found")
R2_ABSENT = re.compile(r"\(404\)|Not Found|NoSuchKey")

# The three verdicts a probe may answer with. `unknown` carries a detail after the colon; the other two are bare.
PRESENT = "present"
ABSENT = "absent"
UNKNOWN_PREFIX = "unknown:"

# The defect named in the module docstring, as a constant so a test can assert against the twin's behaviour BY NAME rather than by repeating the sentence.
SHIFT2_UNDERFLOW_IS_SILENT_EXIT_1 = True


def one_line(text: str) -> str:
    """`tr '\\n' ' ' | sed 's/ */ /g'` fed by `<<<"$out"` (:99).

    THE TRAILING SPACE IS PART OF THE ANSWER. The here-string appends a newline that `tr` turns into a space; `sed` collapses runs of spaces to one, and command substitution strips trailing NEWLINES, not spaces. So every `unknown:` detail ends with exactly one space, including the empty case, where the answer is a single space and nothing else.

    `s/ */ /g` is "one space then zero or more" -- i.e. any run of one or more spaces -- so a single space is rewritten to itself and nothing changes.
    """
    return re.sub(r" +", " ", (text + "\n").replace("\n", " "))


def unknown(detail: str) -> str:
    """`printf 'unknown:%s\\n' "$(one_line <<<"$out")"`, minus the newline that command substitution would strip anyway."""
    return UNKNOWN_PREFIX + one_line(detail)


def is_unknown(state: str) -> bool:
    return state.startswith(UNKNOWN_PREFIX)


def _capture_merged(argv: list[str]) -> tuple[int, str]:
    """`out="$(cmd 2>&1)"`: both streams into one string, trailing newlines gone.

    A missing binary cannot happen after `require_cmd`, but a traceback here would read as a crash rather than a probe result, so it is folded into the shell's own 127.
    """
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False
        )
    except FileNotFoundError:
        return 127, "%s: command not found" % argv[0]
    return proc.returncode, proc.stdout.rstrip("\n")


def probe_gh_api(path: str) -> str:
    """`probe_gh_api` (:101-113). present | absent | unknown:<detail>."""
    rc, out = _capture_merged(["gh", "api", path])
    if rc == 0:
        return PRESENT
    if GH_API_ABSENT.search(out):
        return ABSENT
    return unknown(out)


def probe_gh_release(tag: str) -> str:
    """`probe_gh_release` (:115-127)."""
    rc, out = _capture_merged(["gh", "release", "view", tag, "--json", "tagName"])
    if rc == 0:
        return PRESENT
    if GH_RELEASE_ABSENT.search(out):
        return ABSENT
    return unknown(out)


def probe_r2_sentinel(key: str, bucket: str, endpoint: str) -> str:
    """`probe_r2_sentinel` (:134-149).

    THIS DELIBERATELY DOES NOT REUSE `rsv_sentinel_exists` -- nor its port, `core.release_state_validator.sentinel_exists`. The twin says why at
    :129-133: that helper collapses EVERY failure, expired credentials, a 5xx, a
    DNS fault, into "the sentinel does not exist", which is the exact opposite of rule 2. It can only ever answer present/absent, never "could not tell".
    """
    rc, out = _capture_merged(
        [
            "aws",
            "s3api",
            "head-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--endpoint-url",
            endpoint,
        ]
    )
    if rc == 0:
        return PRESENT
    if R2_ABSENT.search(out):
        return ABSENT
    return unknown(out)


class Verdicts:
    """`FAILED` and `COULD_NOT_TELL`, tracked separately (:151-157).

    Two counters rather than one because the two states need OPPOSITE remediation advice, and the twin's comment records what conflating them cost: an operator was told to cut a release and backfill a sentinel that was already fine, because a credentials failure had been filed as an absence.
    """

    def __init__(self) -> None:
        self.failed = False
        self.could_not_tell = False

    def judge(self, what: str, state: str) -> bool:
        """`judge` (:158-188). True when the thing is present.

        Every caller is `judge ... || true`, so the return value is advisory and the counters are the real output. All three probes run regardless, which is what lets one run name every missing piece.
        """
        if state == PRESENT:
            log.info("OK      %s" % what)
            return True
        if state == ABSENT:
            log.error(
                "MISSING %s -- the channel pointer advertises a version that does not exist" % what
            )
            self.failed = True
            return False
        if is_unknown(state):
            log.error(
                "COULD NOT TELL %s -- the probe did not reach a verdict: %s"
                % (what, state[len(UNKNOWN_PREFIX) :])
            )
            log.error(
                "  A check that did not run must not read as a pass. Treating it as a failure."
            )
            self.failed = True
            self.could_not_tell = True
            return False
        # UNREACHABLE from the three probes, and kept anyway. A fourth verdict invented by a later edit must be REPORTED, not folded into a pass: this is the arm that makes an unclassifiable answer loud.
        log.error("INTERNAL %s: unclassifiable probe result '%s' for %s" % (TWIN, state, what))
        self.failed = True
        return False


def _require_cmd(cmd: str) -> bool:
    """`require_cmd` (common.sh:141-147), inline so the message is this file's.

    `core.common.require_cmd` raises; this script's twin exits, and folding a raise into the two-line main() below would put a try/except around the whole body for a branch that prints one line.
    """
    if shutil.which(cmd) is not None:
        return True
    log.error("Required command '%s' is not available" % cmd)
    return False


def parse_argv(argv: list[str]) -> tuple[str | None, int | None, str | None]:
    """The twin's `while [[ $# -gt 0 ]]` loop (:47-66).

    Returns `(version, exit_code, stdout_text)`. Exactly one of `version` and `exit_code` is meaningful; `stdout_text` is the `--help` output.

    FOUR ARMS, and the third and fourth are easy to get backwards:

      `--version`  takes the NEXT token, even when that token starts with a
                   dash, and even when it is empty. With NO next token at all,
                   `shift 2` underflows and `set -e` kills the script in
                   silence -- see the module docstring. Signalled here as exit
                   1 with nothing printed.
      `-h|--help`  prints usage to STDOUT and exits 0.
      `-*`         anything else beginning with a dash, including a bare `-`
                   and including `--version=1.3.0` (the `=` form is NOT
                   supported by this loop), is an unknown option.
      `*`          a positional. The LAST one wins; earlier ones are
                   overwritten without comment.
    """
    version = ""
    i = 0
    while i < len(argv):
        word = argv[i]
        if word == "--version":
            if i + 2 > len(argv):
                # `shift 2` with one argument left. Exit 1, zero output.
                return None, 1, None
            version = argv[i + 1]
            i += 2
        elif word in ("-h", "--help"):
            return (
                None,
                0,
                "Usage: %s --version VERSION      (VERSION may be 1.3.0 or v1.3.0)" % sys.argv[0],
            )
        elif word.startswith("-"):
            log.error("%s: unknown option: %s" % (TWIN, word))
            return None, 1, None
        else:
            version = word
            i += 1
    return version, None, None


def main(argv: list[str]) -> int:
    version, code, help_text = parse_argv(argv)
    version = version or ""
    if help_text is not None:
        print(help_text)
    if code is not None:
        return code

    if not version:
        log.error("%s: a version is required (--version 1.3.0)" % TWIN)
        return 1

    # `VERSION="${VERSION#v}"`: strips exactly ONE leading `v`, so `vv1.3.0`
    # keeps one and is then rejected by the pattern below.
    version = version.removeprefix("v")
    if not VERSION_RE.match(version):
        log.error("%s: '%s' is not a semver version" % (TWIN, version))
        return 1
    tag = "v" + version

    if not _require_cmd("gh"):
        return 1
    if not _require_cmd("aws"):
        return 1

    for name in REQUIRED_ENV:
        if not os.environ.get(name):
            # DIVERGENCE 1: bash prints its own path and line number here.
            print("%s: %s must be set" % (SELF, name), file=sys.stderr, flush=True)
            return 1

    # :90-91. The aws CLI reads AWS_*; the workflow passes CLOUDFLARE_R2_*. Without this bridge `head-object` dies on NoCredentials and the sentinel probe answers `unknown` -- which is what broke promote-stable for 7 runs.
    os.environ["AWS_ACCESS_KEY_ID"] = os.environ["CLOUDFLARE_R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
    endpoint = os.environ["CLOUDFLARE_R2_ENDPOINT"]

    repo = os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO
    bucket = os.environ.get("RELEASES_BUCKET") or DEFAULT_BUCKET

    log.step("Asserting %s really exists before any promotion write" % tag)

    v = Verdicts()
    v.judge("git tag %s (%s)" % (tag, repo), probe_gh_api("repos/%s/git/ref/tags/%s" % (repo, tag)))
    v.judge("GitHub Release %s" % tag, probe_gh_release(tag))
    v.judge(
        "R2 sentinel s3://%s/cli/%s/.released" % (bucket, tag),
        probe_r2_sentinel("cli/%s/.released" % tag, bucket, endpoint),
    )

    if v.failed:
        log.error("")
        log.error("REFUSING TO PROMOTE %s." % tag)
        if v.could_not_tell:
            log.error("  At least one probe COULD NOT REACH A VERDICT (see COULD NOT TELL above).")
            log.error(
                "  This says nothing about whether %s is published -- it says the check" % tag
            )
            log.error("  did not run. Do NOT cut a release and do NOT backfill a sentinel on the")
            log.error("  strength of this; fix the probe first, then re-run.")
            log.error("  'NoCredentials' means the aws CLI got no AWS_ACCESS_KEY_ID: check that")
            log.error(
                "  the calling workflow passes CLOUDFLARE_R2_ACCESS_KEY_ID / "
                "CLOUDFLARE_R2_SECRET_ACCESS_KEY in."
            )
        else:
            log.error("  The edge channel pointer names a version that is not fully published.")
            log.error("  Promoting it would copy unreleased bytes to stable and then fail on")
            log.error("  'ref: %s' halfway through, leaving a half-applied release." % tag)
            log.error("  Remediate first: cut the release for %s (Release workflow), then" % tag)
            log.error("  seal it (Backfill Release Sentinel), then re-run this promotion.")
        return 1

    log.info("All three exist: git tag, GitHub Release, and R2 sentinel for %s." % tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
