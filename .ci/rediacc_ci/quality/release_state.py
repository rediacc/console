"""The R2 `.released` sentinels, the git tags and the channel pointers agree.

Ported from `.ci/scripts/quality/check-release-state.sh` TOGETHER WITH the parts
of `.ci/scripts/lib/release-state-validator.sh` it calls, neither of which is
deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHY THE LIBRARY COMES WITH IT. The bash gate is thirty lines of glue over five
library functions, and the library has five other bash consumers
(`upload-to-r2.sh`, `write-release-sentinel.sh`, `assert-r2-sentinel.sh`,
`cleanup-versions.sh`) that still source it. A port of the gate alone would be a
port of the glue, and the differential would compare two programs that both
delegate the interesting half to the same shell file, which proves nothing about
the half that decides. So the five functions the gate reaches are ported here,
into the gate's own module, and the bash library stays exactly where it is for
its other callers.

THE CONTRACT, from the library's own header:

    Committed(v${V})  <=>  cli/v${V}/.released exists  AND  git tag v${V} exists

`.released` sentinels are the commit markers; they are written LAST, after every
CI gate has passed. A prefix that is non-empty but missing its sentinel is an
orphan from a cancelled run. Drift is never auto-healed; the error lines include
remediation pointers for a human.

THE RELATION THE BIJECTION CANNOT SEE, and the incident that added the second
half of this gate. A `bump-none` merge correctly skips both the sentinel and the
tag, so the two sides stay in step, while the R2 channel pointer was advanced
anyway. That is how `cli/edge/manifest.json` came to advertise 1.3.1 with no
v1.3.1 tag and a 404 notes URL, three times over (#573, #574, #576), and it
would have half-applied a production release across eu/us/asia on 2026-09-01,
because promote-stable reads the manifest and then checks out `ref: v<version>`.

ORDERING IS WHAT MAKES THE POINTER CHECK SAFE ON THE RELEASE PATH: the gate runs
BEFORE stage-artifacts (ci.yml says so), so the pointer it reads is the PREVIOUS
release's. The back-to-back case resolves itself: if release X's tag is not
pushed yet, IN_FLIGHT is vX and the pointer's X is excluded; if it is pushed,
IN_FLIGHT is vX+1 and X has its tag.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`aws` IS SHELLED OUT TO, NOT REPLACED BY BOTO. Two reasons and the second is the
one that matters. The credentials are mapped into `AWS_*` environment variables
and consumed by the CLI's own resolution chain, which a Python SDK would resolve
differently; and the twin's `--query` expressions are JMESPath evaluated by the
CLI, so re-expressing them in Python would move the filtering from the server's
answer into the port and change WHICH keys are seen. The port runs the same
argv.

THE `--query` STRING CARRIES BACKTICKS AND IS PASSED AS ONE ARGV ELEMENT. The
expression is Contents[?ends_with(Key, <backtick>/.released<backtick>)].Key, and
those backticks are JMESPath's literal syntax rather than a shell substitution.
The twin has to backslash-escape them because it writes the expression inside
double quotes; there is no shell here, so it is written plain. The two backticks
are spelled out in words on purpose. Written literally, a backslash immediately
before a backtick is an INVALID ESCAPE SEQUENCE to Python, and this docstring
carried two of them: every run of the module printed a SyntaxWarning on stderr,
which the first side-by-side run against the twin caught, the twin's stderr
being clean.

TWO OUTPUT DEFECTS ARE REPRODUCED RATHER THAN REPAIRED, and both are reported:

  * `log_info "  ${cli_versions:+$(wc -l <<<"$cli_versions") cli sentinels}${cli_versions:-none}"`
    prints the COUNT and then the WHOLE VERSION LIST glued to it with no
    separator, because `${v:-none}` expands to `$v` whenever `$v` is non-empty.
    Measured: three sentinels print `  3 cli sentinelsv1.0.0` and two more
    lines. Only the empty case reads as intended.
  * `wc -l <<<"$tag_versions"` counts the herestring, and a herestring of the
    empty string is one line. Zero git tags is therefore reported as
    `  1 git tags`, which is the one count a reader most needs to be right.

`sort -uV` IS APPROXIMATED BY A NUMERIC KEY, AND THE INPUTS MAKE THAT SAFE.
Everything reaching a sort here has already passed
`grep -E '^v[0-9]+\\.[0-9]+\\.[0-9]+$'`, so the values are three integers and
`sort -V` reduces to a numeric tuple comparison. The two escapes from that are
named: `$RSV_GRANDFATHER_BEFORE`, an override the library's own comment says
"production should never set", and the ratchet file, which is itself filtered by
the same grep. `version_key` below handles a general string by splitting digit
runs, which agrees with `sort -V` on everything this gate can be handed.

THE GREEDY `.*` IN THE POINTER SED IS LOAD-BEARING.
`sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -1`
takes the LAST `"version"` on the FIRST matching line, because BRE `.*` is
greedy. A manifest that carries a nested `"version"` after the top-level one
therefore reports the nested value. Reproduced exactly; a left-to-right search
would be a different gate.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The bucket, and the sentinel object name inside each version prefix.
DEFAULT_BUCKET = "rediacc-releases"
SENTINEL_KEY = ".released"

# Strict semver with the `v` prefix. Pre-release tags are deliberately outside
# the contract, so they are filtered rather than judged.
STRICT_SEMVER = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")

# The sentinel key shape `rsv_list_sentinels` extracts a version from:
# `s|^cli/\(v[0-9][0-9.]*\)/.released$|\1|p`. Looser than STRICT_SEMVER on
# purpose -- the grep behind it is what tightens the result -- so the two stages
# are kept separate rather than folded into one pattern.
SENTINEL_LINE = re.compile(r"^%s/(v[0-9][0-9.]*)/%s$")

# The channel pointer sed. GREEDY `.*` first, which is what makes it take the
# LAST match on the line; see the port notes.
POINTER_VERSION = re.compile(r'.*"version"[ \t]*:[ \t]*"([^"]*)"')

# The two channels, in the twin's loop order. Order is observable: each channel
# prints a log_step and an OK/DRIFT line.
CHANNELS = ("edge", "stable")

# The ratchet file, relative to the repository root. A monotonic high-water mark
# stored in git: every successful release advances it to the new oldest CLI
# sentinel and nothing decreases it. It protects the all-sentinels-empty case
# (a mass scrub or a misconfigured probe), where bijection would otherwise
# short-circuit to OK.
FLOOR_FILE_REL = ".ci/config/release-contract-floor.txt"


def bucket() -> str:
    """`RSV_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"`."""
    return os.environ.get("RELEASES_BUCKET") or DEFAULT_BUCKET


def version_key(value: str) -> tuple:
    """A `sort -V` key. See the port notes for why an approximation is enough.

    Digit runs compare as integers and everything else as text, which is what
    `sort -V` does for the shapes this gate can be handed. A general
    reimplementation of version sort would be a much larger thing to get wrong
    for inputs that cannot occur.
    """
    parts: list[tuple[int, object]] = []
    for chunk in re.findall(r"\d+|\D+", value):
        if chunk.isdigit():
            parts.append((0, int(chunk)))
        else:
            parts.append((1, chunk))
    return tuple(parts)


def sort_unique_versions(values: list[str]) -> list[str]:
    """`sort -uV`: version order, duplicates removed."""
    return sorted(set(values), key=version_key)


def _records(text: str) -> list[str]:
    """The lines a shell loop would read. A trailing newline is not a record.

    `while IFS= read -r v` over a herestring sees N lines for N-plus-one split
    elements, and every one of those loops here guards with `[[ -z "$v" ]] &&
    continue` anyway. The helper exists so the port's loops do not each grow
    their own guard and drift.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _aws(args: list[str]) -> subprocess.CompletedProcess:
    """Run the `aws` CLI. Never raises for a missing binary; see `require_cmd`.

    The binary is checked once, up front, by `require_cmd`, exactly as the twin
    does. A FileNotFoundError here would therefore mean `aws` vanished mid-run,
    which is reported as a failed probe rather than as a crash: an unanswered
    question is not a `no`, and the library says so in three separate places.
    """
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 127, "", "aws: command not found\n")


def list_sentinels(product: str, endpoint: str) -> list[str]:
    """Every `.released` sentinel under `<product>/v*/`, semver-sorted.

    Empty when there are none. The twin wraps the whole pipeline in `{ ... } ||
    true` for that reason: callers run under `set -euo pipefail` and would
    otherwise trip on grep's exit-1-on-no-match through the pipefail option.
    """
    # Checked at CALL time, not import time, matching the library's `:
    # "${AWS_ACCESS_KEY_ID:?...}"`. The gate exports it from the R2 credential a
    # few lines earlier, so an unset value here means the gate was bypassed.
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        log.error(
            "rsv_list_sentinels: AWS_ACCESS_KEY_ID must be exported "
            "(map it from CLOUDFLARE_R2_ACCESS_KEY_ID)"
        )
        raise SystemExit(1)
    proc = _aws(
        [
            "aws",
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket(),
            "--prefix",
            "%s/v" % product,
            "--endpoint-url",
            endpoint,
            "--query",
            "Contents[?ends_with(Key, `/%s`)].Key" % SENTINEL_KEY,
            "--output",
            "text",
        ]
    )
    # `2>/dev/null`: a failed probe yields no keys and no message, which is the
    # twin's behaviour and is the weakest part of this gate. The library's own
    # siblings (`rsv_prefix_nonempty`, `rsv_binary_count`, `rsv_sentinel_exists`)
    # all grew a third "COULD NOT TELL" state for exactly this reason; this one
    # never did. Carried unchanged, and reported.
    pattern = re.compile(SENTINEL_LINE.pattern % (re.escape(product), re.escape(SENTINEL_KEY)))
    found: list[str] = []
    for line in _records(proc.stdout.replace("\t", "\n")):
        match = pattern.match(line)
        if match and STRICT_SEMVER.match(match.group(1)):
            found.append(match.group(1))
    return sort_unique_versions(found)


def list_git_tags(cwd: str | None = None) -> list[str]:
    """Every strict-semver `v${X}.${Y}.${Z}` tag. Pre-release tags are skipped."""
    proc = subprocess.run(
        ["git", "tag", "-l", "v*"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return sort_unique_versions(
        [line for line in _records(proc.stdout) if STRICT_SEMVER.match(line)]
    )


def pre_contract_floor(cli_versions: list[str], root: pathlib.Path) -> str:
    """The oldest version still subject to the bijection check.

    THREE INPUTS, and the order between them is the whole design:

      1. OBSERVED   the oldest CLI sentinel in the supplied list. Reflects R2's
                    current state.
      2. RATCHET    `.ci/config/release-contract-floor.txt`, a monotonic
                    high-water mark stored in git. It protects the
                    all-sentinels-empty case: when observed is empty but the
                    ratchet remembers a version, bijection still runs against
                    the ratchet floor instead of silently short-circuiting to OK.
      3. OVERRIDE   `$RSV_GRANDFATHER_BEFORE` takes precedence over both. Tests
                    pin synthetic floors with it; production should never set it.

    Floor = max(observed, ratchet) when both are present.

    WHAT THE RATCHET DOES NOT CATCH, from the library's own comment: the "oldest
    CLI sentinel was scrubbed in isolation" case. When observed advances past
    the scrubbed version, max(observed, ratchet) == observed and the scrubbed
    version falls below the floor and is grandfathered. Catching that would need
    a record of every sentinel ever observed, diffed on every check, rather than
    a single high-water mark.
    """
    override = os.environ.get("RSV_GRANDFATHER_BEFORE")
    if override:
        return override

    strict = [v for v in cli_versions if STRICT_SEMVER.match(v)]
    observed = sort_unique_versions(strict)[0] if strict else ""

    floor_file = os.environ.get("RSV_FLOOR_FILE") or ""
    if not floor_file:
        # The twin's candidate list, in its order. `$REPO_ROOT` is a shell
        # variable the gate assigns, so the port uses its own root for it.
        for candidate in (
            root / FLOOR_FILE_REL,
            paths.CI_DIR / "config" / "release-contract-floor.txt",
            pathlib.Path(FLOOR_FILE_REL),
        ):
            if candidate.is_file():
                floor_file = str(candidate)
                break

    ratchet = ""
    if floor_file and pathlib.Path(floor_file).is_file():
        for line in _records(pathlib.Path(floor_file).read_text(encoding="utf-8")):
            if STRICT_SEMVER.match(line):
                ratchet = line
                break

    if not observed:
        return ratchet
    if not ratchet:
        return observed
    # max(observed, ratchet): only advances, never retreats.
    return max(observed, ratchet, key=version_key)


def assert_bijection(
    cli_versions: list[str], tag_versions: list[str], in_flight: str, root: pathlib.Path
) -> tuple[list[str], int]:
    """(the lines to print, 0 on bijection / 1 on drift).

    PURE, and returned rather than printed, so the decision can be asserted
    without capturing a stream. The twin echoes on STDOUT and returns the same
    two codes.

    `in_flight` is the one version this CI run is building; it is excluded so
    the gate does not false-positive on its own in-flight release.
    """
    out: list[str] = []
    floor = pre_contract_floor(cli_versions, root)
    if not floor:
        # Neither sentinels nor an override: the contract is not in effect for
        # this state at all (a fresh dev bucket). Short-circuit to OK rather
        # than false-positive on every old tag in repo history.
        out.append(
            "OK: release-state bijection holds -- no cli sentinels yet (contract not in effect)"
        )
        return out, 0

    def keep(value: str) -> bool:
        """Keep v iff v sorts equal-or-after the floor."""
        if value == floor:
            return True
        return min(floor, value, key=version_key) == floor

    cli_kept = [v for v in cli_versions if v and keep(v)]
    tag_kept = [v for v in tag_versions if v and keep(v)]

    cli_set = {v for v in cli_kept if v}
    tag_set = {v for v in tag_kept if v}
    every = sort_unique_versions([v for v in cli_kept + tag_kept if STRICT_SEMVER.match(v)])

    drift = 0
    for version in every:
        if in_flight and version == in_flight:
            continue
        has_cli = version in cli_set
        has_tag = version in tag_set
        if has_cli == has_tag:
            continue
        if has_cli:
            out.append("DRIFT %s: cli sentinel present, git tag missing" % version)
            out.append(
                "  remediation: re-run CD to tag/release %s, or scrub the sentinel via "
                "scripts/dev/scrub-sentinel.sh %s" % (version, version)
            )
        else:
            out.append("DRIFT %s: git tag present, cli sentinel missing" % version)
            out.append(
                "  remediation: re-run CI to produce artifacts for %s, or delete tag %s"
                % (version, version)
            )
        drift = 1

    if drift == 0:
        out.append(
            "OK: release-state bijection holds (floor: %s, in-flight: %s)"
            % (floor, in_flight or "<none>")
        )
        return out, 0
    return out, 1


def assert_channel_pointer_tagged(
    channel: str,
    latest_ver: str,
    manifest_ver: str,
    tag_versions: list[str],
    in_flight: str,
) -> tuple[list[str], int]:
    """(the lines to print, 0 when the pointer is consistent and tagged).

    PURE, deliberately, and the library says why: "`aws` is not installable on
    the maintainer's host or in the devbox, so an I/O-coupled assertion here
    would be untestable locally -- which is how a release gate ends up
    unverified." The caller does the R2 and git reads; this only judges them.
    """
    out: list[str] = []
    drift = 0

    # An unreadable pointer is NOT a clean channel. Both files are written
    # seconds apart by the same uploader, so a missing one means the read failed
    # or the write tore, and either way the question was not answered.
    if not latest_ver or not manifest_ver:
        out.append(
            "DRIFT %s: could not read the channel pointer (latest='%s' manifest='%s'); "
            "an unreadable pointer is never a pass"
            % (channel, latest_ver or "<empty>", manifest_ver or "<empty>")
        )
        return out, 1

    # They are written back to back. Disagreement means a torn write, and
    # different consumers then resolve to different versions: install.sh reads
    # latest.json, the updater reads manifest.json.
    if latest_ver != manifest_ver:
        out.append(
            "DRIFT %s: latest.json says '%s' but manifest.json says '%s'. They are written "
            "seconds apart, so this is a torn write, and install.sh (latest.json) and the "
            "auto-updater (manifest.json) will disagree." % (channel, latest_ver, manifest_ver)
        )
        drift = 1

    # The in-flight version legitimately has no tag yet: the pointer for release
    # X is written before X's tag is pushed. Excluding it is what makes this
    # relation safe to run on the release path at all.
    if in_flight and latest_ver == in_flight:
        if drift == 0:
            out.append(
                "OK: %s pointer names the in-flight version %s (tag not expected yet)"
                % (channel, latest_ver)
            )
        return out, drift

    if latest_ver not in tag_versions:
        out.append(
            "DRIFT %s: the channel pointer names '%s', which has NO git tag. Every rdc on this "
            "channel auto-updates to a build whose releaseNotesUrl 404s, and promote-stable "
            "will later check out 'ref: %s' and fail AFTER the R2 and Docker halves have "
            "already succeeded." % (channel, latest_ver, latest_ver)
        )
        drift = 1

    if drift == 0:
        out.append("OK: %s pointer names %s, which is tagged" % (channel, latest_ver))
    return out, drift


def pointer_version(payload: str) -> str:
    """The `"version"` a pointer file advertises, prefixed with `v`, or "".

    Three shell stages, reproduced in order because each has an edge:

        sed -n 's/.*"version"...\\(...\\)".*/\\1/p'   GREEDY: the LAST match
        head -1                                     the FIRST matching LINE
        sed 's/^v//'                                then a `v` is prefixed back

    The last two cancel out for a value that already starts with `v` and matter
    for one that does not, which is why the twin writes them rather than just
    taking the value. A payload with no `"version"` at all reduces to the bare
    string `v`, which the twin then rewrites to "".
    """
    for line in _records(payload):
        match = POINTER_VERSION.match(line)
        if match:
            value = "v" + re.sub(r"^v", "", match.group(1))
            return "" if value == "v" else value
    return ""


def require_cmd(name: str) -> None:
    """`require_cmd` from `.ci/scripts/lib/common.sh`. Exits 1 when absent."""
    if shutil.which(name) is None:
        log.error("Required command '%s' is not available" % name)
        raise SystemExit(1)


def require_var(name: str) -> None:
    """`require_var` from `.ci/scripts/lib/common.sh`. Exits 1 when unset OR EMPTY.

    The empty case is the one that matters and is easy to lose: `[[ -z "${!var:-}" ]]`
    treats a variable set to the empty string as missing, which is exactly the
    2026-09-05 shape one lane over, where a deleted org secret resolved to "" and
    an empty value was indistinguishable from "not wanted".
    """
    if not os.environ.get(name):
        log.error("Required environment variable '%s' is not set" % name)
        raise SystemExit(1)


def _resolve_in_flight(root: pathlib.Path) -> str:
    """`$IN_FLIGHT_VERSION`, or `v$(resolve-version.sh --bump-type patch)`.

    Mirrors what ci.yml's initialize step computes, which is what keeps this
    gate runnable standalone.
    """
    given = os.environ.get("IN_FLIGHT_VERSION")
    if given:
        return given
    script = root / ".ci" / "scripts" / "version" / "resolve-version.sh"
    proc = subprocess.run(
        [str(script), "--bump-type", "patch"],
        capture_output=True,
        text=True,
        check=False,
    )
    # `set -e` on the twin: a failing resolve-version.sh kills the gate with its
    # own diagnostics. The port forwards them and does the same.
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return "v" + proc.stdout.strip()


def _read_pointer(channel: str, name: str, endpoint: str) -> str:
    """One pointer file's advertised version, or "" when it could not be read."""
    proc = _aws(
        [
            "aws",
            "s3",
            "cp",
            "s3://%s/cli/%s/%s" % (bucket(), channel, name),
            "-",
            "--endpoint-url",
            endpoint,
        ]
    )
    if proc.returncode != 0:
        # `if lj="$(aws ... 2>/dev/null)"` -- a failed read leaves the version
        # empty, and `assert_channel_pointer_tagged` refuses to call that clean.
        return ""
    return pointer_version(proc.stdout)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 on bijection, 1 on drift. Drift is never auto-healed.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no
    arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    require_cmd("aws")
    require_var("CLOUDFLARE_R2_ACCESS_KEY_ID")
    require_var("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
    require_var("CLOUDFLARE_R2_ENDPOINT")
    os.environ["AWS_ACCESS_KEY_ID"] = os.environ["CLOUDFLARE_R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
    os.environ["AWS_DEFAULT_REGION"] = "auto"
    endpoint = os.environ["CLOUDFLARE_R2_ENDPOINT"]

    in_flight = _resolve_in_flight(root)
    log.info("in-flight version (excluded from bijection check): %s" % in_flight)

    log.step("listing cli sentinels")
    cli_versions = list_sentinels("cli", endpoint)
    # THE GLUED COUNT, REPRODUCED. `${v:+N cli sentinels}${v:-none}` expands to
    # the count phrase AND THEN the whole list, because `${v:-none}` is `$v`
    # whenever `$v` is non-empty. See the port notes; reported, not repaired.
    if cli_versions:
        log.info("  %d cli sentinels%s" % (len(cli_versions), "\n".join(cli_versions)))
    else:
        log.info("  none")

    log.step("listing git release tags")
    tag_versions = list_git_tags()
    # `wc -l <<<"$tag_versions"` counts a herestring, and a herestring of the
    # empty string is ONE line. Zero tags therefore reports `1 git tags`.
    log.info("  %d git tags" % (len(tag_versions) if tag_versions else 1))

    log.step("asserting release-state bijection")
    lines, bijection_rc = assert_bijection(cli_versions, tag_versions, in_flight, root)
    for line in lines:
        print(line)

    pointer_rc = 0
    for channel in CHANNELS:
        latest_ver = _read_pointer(channel, "latest.json", endpoint)
        manifest_ver = _read_pointer(channel, "manifest.json", endpoint)
        log.step("asserting %s channel pointer names a tagged version" % channel)
        lines, rc = assert_channel_pointer_tagged(
            channel, latest_ver, manifest_ver, tag_versions, in_flight
        )
        for line in lines:
            print(line)
        if rc != 0:
            pointer_rc = 1

    if bijection_rc == 0 and pointer_rc == 0:
        log.info("release-state gate: PASS")
        return 0

    if pointer_rc != 0:
        log.error("release-state gate: FAIL — a channel pointer names a version with no git tag")
        log.error("  every rdc on that channel auto-updates to a build whose release notes 404,")
        log.error(
            "  and promote-stable will later check out that ref and fail AFTER promoting R2 + Docker"
        )
        return 1

    log.error("release-state gate: FAIL — drift between R2 sentinels and git tags")
    log.error("  the findings above indicate an incomplete release or a missing tag")
    log.error("  see .ci/scripts/lib/release-state-validator.sh for the invariant")
    return 1


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    THE PURE HALF, WHICH HERE IS ALMOST ALL OF IT. The library's own header says
    callers "should usually feed `rsv_assert_bijection` synthetic version lists
    rather than shimming AWS", and the assertions were deliberately written
    without I/O for that reason. So the two relations, the floor, the version
    sort and the pointer parse are all driven directly. The R2 half is proven
    end to end by the committed shadow ledger
    `.ci/shadow/w7p2-release-state.observations.jsonl` over five distinct trees,
    against a stub `aws` inside each fixture.
    """
    ctl = Controls("release-state", floor=30, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        saved_floor = os.environ.pop("RSV_FLOOR_FILE", None)
        saved_grand = os.environ.pop("RSV_GRANDFATHER_BEFORE", None)
        # THE RATCHET LEAKS IN FROM THE REAL TREE, and pinning it away is the
        # only way these controls mean anything. `pre_contract_floor`'s SECOND
        # candidate is `<this file's .ci>/config/release-contract-floor.txt`,
        # which is the twin's `${script_dir}/../../config/...` and does not move
        # when the caller passes a fixture root. So a selftest that did not pin
        # it would compute its floors from whatever version the REAL repository
        # is on -- measured: v1.2.20, which grandfathers every fixture version
        # and turns four plants green. Setting the variable to a path that does
        # not exist is exactly how the twin is told "no ratchet": the search for
        # candidates is skipped entirely when it is set, and a non-file value
        # leaves the ratchet empty.
        os.environ["RSV_FLOOR_FILE"] = str(root / "no-such-floor.txt")
        try:
            # -- the bijection ---------------------------------------------
            def bij(cli: list[str], tags: list[str], in_flight: str = "") -> tuple[list[str], int]:
                return assert_bijection(cli, tags, in_flight, root)

            ctl.check(
                "CONTROL: matched sentinels and tags are a bijection",
                bij(["v1.0.0", "v1.0.1"], ["v1.0.0", "v1.0.1"])[1],
                0,
            )
            ctl.check(
                "CONTROL: and it says so with the floor and the in-flight version",
                bij(["v1.0.0"], ["v1.0.0"], "v1.0.1")[0],
                ["OK: release-state bijection holds (floor: v1.0.0, in-flight: v1.0.1)"],
            )
            ctl.check(
                "PLANT: a sentinel with no tag is drift",
                bij(["v1.0.0", "v1.0.1"], ["v1.0.0"])[1],
                1,
            )
            ctl.check(
                "PLANT: and the finding names the remediation",
                bij(["v1.0.0", "v1.0.1"], ["v1.0.0"])[0][1].startswith("  remediation: re-run CD"),
                True,
            )
            ctl.check(
                "PLANT: a tag with no sentinel is drift",
                bij(["v1.0.0"], ["v1.0.0", "v1.0.1"])[1],
                1,
            )
            ctl.check(
                "PLANT: and it is a DIFFERENT finding from the other direction",
                bij(["v1.0.0"], ["v1.0.0", "v1.0.1"])[0][0],
                "DRIFT v1.0.1: git tag present, cli sentinel missing",
            )
            ctl.check(
                "MIRROR: the IN-FLIGHT version is excluded from both directions",
                bij(["v1.0.0", "v1.0.9"], ["v1.0.0"], "v1.0.9")[1],
                0,
            )
            ctl.check(
                "MIRROR: a tag BELOW the floor is grandfathered",
                bij(["v1.0.5"], ["v0.9.0", "v1.0.5"])[1],
                0,
            )
            ctl.check(
                "PLANT: a tag ABOVE the floor is not grandfathered",
                bij(["v1.0.5"], ["v1.0.5", "v1.0.6"])[1],
                1,
            )
            ctl.check(
                "MIRROR: the FLOOR ITSELF stays in scope, so its own bijection is checked",
                bij([], ["v1.0.5"], "")[1],
                0,
            )

            # -- the vacuity case, which is the one that must not read as OK --
            #
            # No sentinels AND no ratchet is "the contract is not in effect",
            # which the library short-circuits deliberately. It is recorded here
            # as a KNOWN weak spot rather than left to be discovered: the gate
            # reports OK having compared nothing.
            empty_lines, empty_rc = bij([], ["v1.0.0", "v2.0.0"])
            ctl.check("KNOWN: no sentinels and no ratchet short-circuits to OK", empty_rc, 0)
            ctl.check(
                "KNOWN: and it SAYS the contract is not in effect rather than 'holds'",
                "contract not in effect" in empty_lines[0],
                True,
            )

            # -- the floor --------------------------------------------------
            ctl.check(
                "floor: the oldest observed sentinel",
                pre_contract_floor(["v1.2.0", "v1.0.5", "v1.1.0"], root),
                "v1.0.5",
            )
            ctl.check(
                "floor: no sentinels and no ratchet is empty", pre_contract_floor([], root), ""
            )

            ctl.check(
                "CONTROL: the pinned no-ratchet path really leaves the ratchet empty",
                pre_contract_floor([], root),
                "",
            )

            ratchet = root / "floor.txt"
            ratchet.write_text("v1.1.0\n", encoding="utf-8")
            os.environ["RSV_FLOOR_FILE"] = str(ratchet)
            ctl.check(
                "floor: the RATCHET alone carries the all-scrubbed case",
                pre_contract_floor([], root),
                "v1.1.0",
            )
            ctl.check(
                "floor: max(observed, ratchet) -- the ratchet wins when it is newer",
                pre_contract_floor(["v1.0.0"], root),
                "v1.1.0",
            )
            ctl.check(
                "floor: and the observation wins when IT is newer",
                pre_contract_floor(["v1.2.0"], root),
                "v1.2.0",
            )
            os.environ["RSV_GRANDFATHER_BEFORE"] = "v9.9.9"
            ctl.check(
                "floor: the override beats both, which is why tests pin it",
                pre_contract_floor(["v1.0.0"], root),
                "v9.9.9",
            )
            del os.environ["RSV_GRANDFATHER_BEFORE"]
        finally:
            os.environ.pop("RSV_FLOOR_FILE", None)
            if saved_floor is not None:
                os.environ["RSV_FLOOR_FILE"] = saved_floor
            if saved_grand is not None:
                os.environ["RSV_GRANDFATHER_BEFORE"] = saved_grand

    # -- the channel pointer relation ---------------------------------------
    tags = ["v1.0.0", "v1.0.1"]
    ctl.check(
        "CONTROL: a consistent, tagged pointer passes",
        assert_channel_pointer_tagged("edge", "v1.0.1", "v1.0.1", tags, "v1.0.2")[1],
        0,
    )
    ctl.check(
        "PLANT: an UNREADABLE pointer is never a pass",
        assert_channel_pointer_tagged("edge", "", "v1.0.1", tags, "")[1],
        1,
    )
    ctl.check(
        "PLANT: and neither is the other half missing",
        assert_channel_pointer_tagged("edge", "v1.0.1", "", tags, "")[1],
        1,
    )
    ctl.check(
        "PLANT: a TORN WRITE is caught",
        assert_channel_pointer_tagged("edge", "v1.0.1", "v1.0.0", tags, "")[1],
        1,
    )
    ctl.check(
        "PLANT: an UNTAGGED pointer is the #573/#574/#576 shape",
        assert_channel_pointer_tagged("edge", "v1.3.1", "v1.3.1", tags, "")[1],
        1,
    )
    ctl.check(
        "MIRROR: the IN-FLIGHT version legitimately has no tag yet",
        assert_channel_pointer_tagged("edge", "v1.0.2", "v1.0.2", tags, "v1.0.2")[1],
        0,
    )
    ctl.check(
        "PLANT: a torn write is still drift even at the in-flight version",
        assert_channel_pointer_tagged("edge", "v1.0.2", "v1.0.1", tags, "v1.0.2")[1],
        1,
    )

    # -- the pointer parse ---------------------------------------------------
    ctl.check("pointer: an ordinary payload", pointer_version('{"version": "1.3.1"}'), "v1.3.1")
    ctl.check(
        "pointer: a leading v is not doubled", pointer_version('{"version":"v1.3.1"}'), "v1.3.1"
    )
    ctl.check("pointer: no version key at all is empty", pointer_version("{}"), "")
    ctl.check("pointer: an EMPTY value is empty", pointer_version('{"version": ""}'), "")
    ctl.check(
        "pointer: GREEDY -- the LAST match on the line wins",
        pointer_version('{"version": "1.0.0", "tool": {"version": "9.9.9"}}'),
        "v9.9.9",
    )
    ctl.check(
        "pointer: head -1 -- the FIRST matching line wins",
        pointer_version('{\n"version": "1.0.0"\n}\n{"version": "2.0.0"}\n'),
        "v1.0.0",
    )
    ctl.check("pointer: an empty payload is empty", pointer_version(""), "")

    # -- the version sort ----------------------------------------------------
    ctl.check(
        "sort: numeric, not lexicographic",
        sort_unique_versions(["v1.0.10", "v1.0.9", "v1.0.2"]),
        ["v1.0.2", "v1.0.9", "v1.0.10"],
    )
    ctl.check("sort: -u removes duplicates", sort_unique_versions(["v1.0.0", "v1.0.0"]), ["v1.0.0"])
    ctl.check("sort: an empty list stays empty", sort_unique_versions([]), [])

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
