"""The sentinel-based release-commit contract, ported from the bash library.

PORTED FROM `.ci/scripts/lib/release-state-validator.sh` (496 lines), which still exists, is untouched by this file, and has **11 real sourcers**, re-measured on 2026-09-10 with

    grep -rnP '^\\s*(source|\\.)\\s+.*\\brelease-state-validator\\.sh' .

(`.ci/scripts/quality/check-release-state.sh:23`, `.ci/scripts/deploy/upload-to-r2.sh:258`, `.ci/scripts/deploy/write-release-sentinel.sh:34`, `.ci/scripts/test/assert-r2-sentinel.sh:23`, `.ci/scripts/test/gates/test-release-state-consistency.sh:33`, `.ci/scripts/housekeeping/cleanup-versions.sh:1309`, `.ci/scripts/release/reprobe-r2-sentinel.sh:28`,
`.ci/scripts/release/advance-contract-floor.sh:49`, `scripts/dev/scrub-sentinel.sh:32`, and two heredocs inside `.ci/rediacc_ci/tests/test_quality_release_state.py:148,213`). It is NOT the
"496" in the programme plan, which is this file's LINE COUNT and not its fan-in;
the twin's own "Sourced by:" header at `release-state-validator.sh:19-24` lists only five and is itself four short.

The contract, restated from the twin's header because a port that does not carry the invariant is just a translation:

    Committed(v${V})  <=>  cli/v${V}/.released exists  AND  git tag v${V} exists

Sentinels are written LAST, after every gate has passed. A prefix that is non-empty but missing its sentinel is an orphan from a cancelled run.

--------------------------------------------------------------------------
THE DUPLICATE THAT ALREADY EXISTS, NAMED RATHER THAN LEFT TO BE FOUND
--------------------------------------------------------------------------
`.ci/rediacc_ci/quality/release_state.py` ALREADY carries a port of the ASSERTION half of this library, inlined into one gate because that gate was ported (W7 P2) before the library was. REPOINTING IT IS NOT DONE HERE and is not this module's licence to grant: that gate has its own recorded shadow ledger
(`.ci/shadow/w7p2-release-state.observations.jsonl`, K=5), and a body swap under
a ledger is a separate change with its own evidence. What the two hold, so that whoever collapses them knows exactly what moves:

  * SHARED, and byte-identical in their emitted lines: `pre_contract_floor`,
    `assert_bijection`, `assert_channel_pointer_tagged`, `list_sentinels`,
    `list_git_tags`, plus the `version_key` / `sort_unique_versions` helpers.
  * ONLY HERE, because the gate never needed them and so never ported them:
    `prefix_nonempty`, `binary_count`, `sentinel_exists`,
    `get_sentinel_payload`. Those four are the LIVE PROBES, and they are what
    the six still-unported release-path scripts actually call
    (`upload-to-r2.sh:275,277`, `write-release-sentinel.sh:119,140`,
    `assert-r2-sentinel.sh:60,63`, `reprobe-r2-sentinel.sh:43`,
    `scrub-sentinel.sh:81`, `cleanup-versions.sh:1325,1326,1336`).
  * ONLY THERE: the gate's own driver (`main`, `selftest`, `pointer_version`,
    `_read_pointer`, `_resolve_in_flight`). Those are the GATE, not the library,
    and they do not belong here.

--------------------------------------------------------------------------
WHY THE THREE-STATE PROBES ARE AN ENUM AND NOT AN int
--------------------------------------------------------------------------
This is the one place a faithful port would have introduced a bug the twin does not have, so it is argued rather than asserted.

The twin answers three of its probes with a SHELL exit code: `0` sealed / `1` absent / `2` could not tell. In shell, `0` is TRUE. In Python, `0` is FALSE. Returning the raw code would make

    if sentinel_exists(product, version):   # WRONG, and it reads correctly

mean the exact opposite of `if rsv_sentinel_exists ...` at `upload-to-r2.sh:275`, `reprobe-r2-sentinel.sh:43` and `scrub-sentinel.sh:81`, in the direction that proceeds with an upload over a sealed release. So `Probe` is a plain `enum.Enum` and NOT an `IntEnum`: it has no truth value worth guessing at, `Probe.YES` is not `0`, and a caller must say `is Probe.YES` or ask `.rc` for
the shell code. A test pins that `Probe` is not an `int` subclass, because the day someone "tidies" it into an `IntEnum` is the day the bug lands.

The twin's own reason for the third state, at `release-state-validator.sh:128-132` and `:194-206`, is the anti-vacuity one: "no objects under this version prefix" is the signal for a scrubbed or corrupt release, and reporting it because a credential expired would condemn a healthy release. An unanswered question is not a `no`.

--------------------------------------------------------------------------
DEFECT 1, REPRODUCED NOT FIXED: `log_error` IS NOT DEFINED IN THIS LIBRARY
--------------------------------------------------------------------------
`rsv_prefix_nonempty:145`, `rsv_binary_count:178,187` and `rsv_sentinel_exists:227` all call `log_error`, which the library neither defines nor sources. `release-state-validator.sh` sources NOTHING (its first 31 lines are a re-source guard and two constants), so the symbol resolves only because every production caller happens to source `common.sh` FIRST.

Driven live on 2026-09-10, bash 5.3.9:

    bash -c 'set -euo pipefail
             source .ci/scripts/lib/release-state-validator.sh
             export CLOUDFLARE_R2_ENDPOINT=https://example.invalid \\
                    AWS_ACCESS_KEY_ID=x AWS_SECRET_ACCESS_KEY=y
             rsv_binary_count "cli/v1.0.0/"; echo "rc=$?"'

    release-state-validator.sh: line 178: log_error: command not found

and the `echo "rc=$?"` NEVER RUNS: `command not found` is 127, errexit fires on
it, and the function dies BEFORE its `rm -f "$err"` and before its `return 1`. So on that path the documented three-state contract collapses into a 127 abort plus a leaked `mktemp` file, and the caller is told nothing about R2 at all.

BLAST RADIUS, MEASURED RATHER THAN GUESSED: 1 of the 11 sourcers does not source `common.sh` (`.ci/scripts/test/gates/test-release-state-consistency.sh`, a REGISTERED gate test), and it exercises only the two PURE assertion functions, which contain no `log_error`. So there are ZERO live paths today. It is latent, not exploitable, and it is the same shape as the `service.sh` /
`check_docker` finding from this workstream's first wave. This port defines its own `_log_error` and therefore cannot inherit the defect; a test pins that the twin still has it, so the pin goes red the day the twin is fixed.

--------------------------------------------------------------------------
DEFECT 2, REPRODUCED NOT FIXED: THE ONE PROBE THAT STILL CONFLATES "EMPTY" WITH "UNREACHABLE" IS THE ONE THE BLOCKER GATE'S VERDICT RESTS ON
--------------------------------------------------------------------------
`rsv_list_sentinels:101-112` wraps its whole pipeline in `{ ... } || true`, and
`aws ... 2>/dev/null` inside it. An expired credential, a 5xx and a genuinely empty bucket therefore all produce the same thing: empty stdout, exit 0.

That is precisely what the file spends two long comments refusing for its three siblings. `:128-132`: "This used to end in `|| echo 0`, collapsing 'the prefix is empty' and 'R2 is unreachable' into the same answer. Release-state validation is exactly the place that must not confuse those two". `:194-200`: "a confident 'this release is not sealed' from a probe that never ran ...
this one was the odd one out". The odd one out is now `rsv_list_sentinels`, and it feeds `check-release-state.sh:41`, the BLOCKER drift gate.

WHY IT IS NOT GREEN TODAY, and this is the part worth writing down because it is the difference between "latent" and "live": the RATCHET saves it. With `cli_versions` empty and `.ci/config/release-contract-floor.txt` holding `v1.2.21` (tracked in git, verified present 2026-09-10), `pre_contract_floor` returns the ratchet, every git tag at or above `v1.2.21` becomes `DRIFT <v>: git
tag present, cli sentinel missing`, and the gate goes RED. The gate is protected by a one-line data file, not by the probe.

DELETE OR EMPTY THAT FILE AND THE GATE GOES GREEN ON A DEAD PROBE: floor is "", `assert_bijection` short-circuits to `OK: release-state bijection holds - no cli sentinels yet (contract not in effect)` and returns 0. The port reproduces that short-circuit exactly, because changing it here would make the port disagree with the twin about a verdict; the finding is recorded and pinned
in a test instead.

--------------------------------------------------------------------------
DEFECT 3, REPRODUCED NOT FIXED: A FUNCTION DEFINED INSIDE A FUNCTION IS STILL GLOBAL, AND THIS ONE CLOSES OVER A `local`
--------------------------------------------------------------------------
`rsv_drop_pre_contract` is defined at `release-state-validator.sh:365`, INSIDE `rsv_assert_bijection`, and bash has no nested scope for functions: after the first call to `rsv_assert_bijection` the name is defined globally for the rest of the shell. It reads `$floor`, which is `local` to its DEFINER, so calling it standalone afterwards under `set -u` dies with `floor: unbound
variable`, and calling it under `set +u` silently keeps everything (an empty floor compares before every version). It is also re-parsed on every call.

Nothing calls it, so the impact is a leaked name and a re-parse. Reproduced here as a module-private closure, which is the honest Python spelling of what the bash MEANT, and named so nobody re-exports it.

--------------------------------------------------------------------------
BASH 4.0 IS A PRECONDITION OF THE TWIN, AND HAS NO COUNTERPART HERE
--------------------------------------------------------------------------
`:33-70` refuses to load on bash 3.2 because `declare -A` is a 4.0 feature and its failure on 3.2 is SILENT: both set names stay indexed, every `cli_set["$v"]` subscript is evaluated as arithmetic, and (driven on a real bash 3.2.0 on
2026-09-06, recorded in the twin) a healthy release state reports rc=1 with
EMPTY stdout while a real drift reports rc=1 with empty stdout too. A gate that
cannot say WHICH version drifted is worse than one that did not run.

A Python `dict` is a `dict` on every interpreter this repo supports, so there is nothing to guard. The guard is not dropped silently: a test asserts the twin still carries it, so removing it there is a red here.

--------------------------------------------------------------------------
COMMAND-LINE ENTRY POINT (what a bash caller can reach)
--------------------------------------------------------------------------
    python3 -m rediacc_ci.core.release_state_validator bijection \\
        --cli <file|-> --tags <file|-> [--in-flight vX.Y.Z]
        the DRIFT/OK lines on stdout, exit 0 on bijection and 1 on drift.

    python3 -m rediacc_ci.core.release_state_validator pointer \\
        <channel> <latest> <manifest> --tags <file|-> [--in-flight vX.Y.Z]
        the DRIFT/OK lines on stdout, exit 0 when the pointer is tagged.

    python3 -m rediacc_ci.core.release_state_validator floor --cli <file|->
        the pre-contract floor, or nothing at all when there is none.

    python3 -m rediacc_ci.core.release_state_validator sentinels <product>
    python3 -m rediacc_ci.core.release_state_validator tags
    python3 -m rediacc_ci.core.release_state_validator binary-count <prefix>
    python3 -m rediacc_ci.core.release_state_validator sentinel-exists <p> <v>
    python3 -m rediacc_ci.core.release_state_validator prefix-nonempty <prefix>
    python3 -m rediacc_ci.core.release_state_validator payload <product> <ver>
        the live probes. Each exits with the twin's shell code, so
        `sentinel-exists` is 0 sealed / 1 absent / 2 could not tell.
"""

from __future__ import annotations

import enum
import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import paths

# `RSV_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"` (release-state-validator.sh:72).
DEFAULT_BUCKET = "rediacc-releases"

# `RSV_SENTINEL_KEY=".released"` (:73). The commit marker, written LAST.
SENTINEL_KEY = ".released"

# Strict semver with the `v` prefix, the `grep -E` at :110, :120, :287, :307 and :384. Pre-release tags are deliberately OUTSIDE the contract, so they are filtered rather than judged.
STRICT_SEMVER = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")

# The sed at :109, deliberately LOOSER than STRICT_SEMVER: `v[0-9][0-9.]*`. The grep behind it is what tightens the result, so the two stages stay separate here exactly as they are two stages there. Folding them into one pattern would quietly change which keys are even considered.
SENTINEL_LINE = r"^%s/(v[0-9][0-9.]*)/%s$"

# `.ci/config/release-contract-floor.txt`, relative to the repository root. The monotonic high-water mark; see DEFECT 2 for what it is currently load-bearing
# for.
FLOOR_FILE_REL = ".ci/config/release-contract-floor.txt"

# The two channels, in the twin's loop order (check-release-state.sh:70). Order is observable: each channel emits its own OK or DRIFT line.
CHANNELS = ("edge", "stable")


class Probe(enum.Enum):
    """A three-state probe answer. NOT an `IntEnum`; see the module docstring.

    `.rc` is the shell exit code the twin returns, so a CLI wrapper can hand a bash caller the identical number without anyone re-deriving the mapping.
    """

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"

    @property
    def rc(self) -> int:
        return {Probe.YES: 0, Probe.NO: 1, Probe.UNKNOWN: 2}[self]


def _log_error(message: str) -> None:
    """The twin's `log_error`, which the twin does not define. See DEFECT 1.

    `common.sh`'s `log_error` writes to stderr with a colour prefix when stderr is a tty. The prefix is deliberately NOT reproduced: it is chatter, the differential normalises it away, and a port that invents a colour code the twin might not emit is a port that can never be proven equal.
    """
    print(message, file=sys.stderr)


def bucket(env: dict[str, str] | None = None) -> str:
    """`${RELEASES_BUCKET:-rediacc-releases}`, read at CALL time.

    Read per call rather than frozen at import, because the twin reads it at SOURCE time (`:72`) into a variable every function then interpolates, and a caller that exports `RELEASES_BUCKET` after sourcing gets the OLD value in bash and would get the NEW one from a module constant here. Neither behaviour is better; they just have to be the same, and a function is the only spelling
    a test can pin.
    """
    table = os.environ if env is None else env
    return table.get("RELEASES_BUCKET") or DEFAULT_BUCKET


def version_key(value: str) -> tuple:
    """A `sort -V` key: digit runs as integers, everything else as text.

    Not a general reimplementation of GNU version sort, on purpose. Every value that reaches this function has already passed `STRICT_SEMVER` or is the operator-supplied `$RSV_GRANDFATHER_BEFORE`, and a full reimplementation would be a much larger thing to get wrong for inputs that cannot occur.
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


def records(text: str) -> list[str]:
    """The lines a `while IFS= read -r v` loop would see. Trailing blank dropped.

    A bash here-string ALWAYS appends a newline, so `<<<"$input"` over an empty string yields exactly one empty record, which every loop in the twin then skips with `[[ -z "$v" ]] && continue`. Centralised so the port's loops do not each grow their own guard and drift apart.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _run(argv: list[str], *, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run one external command. A missing binary is a FAILED PROBE, not a crash.

    The twin's callers run `require_cmd aws` up front, so `aws` vanishing mid-run is not a case any of them handle. Returning 127 with the message on stderr keeps that in the "could not tell" bucket, which is the direction this whole library errs in.
    """
    try:
        return subprocess.run(argv, capture_output=True, text=True, check=False, cwd=cwd)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", "%s: command not found\n" % argv[0])


# --------------------------------------------------------------------------- Live probes (AWS + git) ---------------------------------------------------------------------------


def list_sentinels(product: str, endpoint: str | None = None) -> list[str]:
    """Every `.released` sentinel under `<product>/v*/`, semver-sorted.

    `rsv_list_sentinels` (:97-113). Empty stdout when there are none.

    THE AWS_ACCESS_KEY_ID CHECK IS AT CALL TIME, matching the twin's
    `: "${AWS_ACCESS_KEY_ID:?...}"` at :100 and the comment beside it. In bash
    that `:?` EXITS a non-interactive shell; here it raises, because a module that calls `sys.exit` from a library function takes the decision away from the one caller (`cleanup-versions.sh`) that loops over products.

    SEE DEFECT 2: a failed probe is indistinguishable from an empty bucket, and that is carried unchanged rather than improved, because improving it here would make this port disagree with the twin about a live gate's verdict.
    """
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        raise RuntimeError(
            "rsv_list_sentinels: AWS_ACCESS_KEY_ID must be exported "
            "(map it from CLOUDFLARE_R2_ACCESS_KEY_ID)"
        )
    proc = _run(
        [
            "aws",
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket(),
            "--prefix",
            "%s/v" % product,
            "--endpoint-url",
            endpoint or os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
            "--query",
            "Contents[?ends_with(Key, `/%s`)].Key" % SENTINEL_KEY,
            "--output",
            "text",
        ]
    )
    pattern = re.compile(SENTINEL_LINE % (re.escape(product), re.escape(SENTINEL_KEY)))
    found: list[str] = []
    # `tr '\t' '\n'`: `--output text` packs the whole array onto one tab-joined line, so the tab split is not cosmetic, it is what makes there be records.
    for line in records(proc.stdout.replace("\t", "\n")):
        match = pattern.match(line)
        if match and STRICT_SEMVER.match(match.group(1)):
            found.append(match.group(1))
    return sort_unique_versions(found)


def list_git_tags(cwd: str | None = None) -> list[str]:
    """Every strict-semver `v${X}.${Y}.${Z}` tag. `rsv_list_git_tags` (:117-123).

    Pre-release tags are skipped by the same grep the twin uses, and the whole thing is `|| true` there so an empty tag list does not trip pipefail.
    """
    proc = _run(["git", "tag", "-l", "v*"], cwd=cwd)
    return sort_unique_versions(
        [line for line in records(proc.stdout) if STRICT_SEMVER.match(line)]
    )


def prefix_nonempty(prefix: str, endpoint: str | None = None) -> Probe:
    """YES the prefix holds an object, NO it is empty, UNKNOWN it could not tell.

    `rsv_prefix_nonempty` (:133-152). THREE STATES, DELIBERATELY: this used to end in `|| echo 0`, collapsing "the prefix is empty" and "R2 is unreachable" into one answer, and reporting a scrubbed release because a credential expired would condemn a healthy one.
    """
    proc = _run(
        [
            "aws",
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket(),
            "--prefix",
            prefix,
            "--max-items",
            "1",
            "--endpoint-url",
            endpoint or os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
            "--query",
            "KeyCount",
            "--output",
            "text",
        ]
    )
    if proc.returncode != 0:
        _log_error(
            "rsv_prefix_nonempty: list-objects-v2 failed for s3://%s/%s (exit %d)"
            % (bucket(), prefix, proc.returncode)
        )
        _indent_stderr(proc.stderr)
        return Probe.UNKNOWN
    # `[[ "$count" != "0" && "$count" != "None" ]]`. `$(...)` strips trailing
    # newlines, which is what the strip() reproduces; without it every real answer would compare unequal to "0" and the probe would always say YES.
    count = proc.stdout.strip("\n")
    return Probe.YES if count not in ("0", "None") else Probe.NO


def binary_count(prefix: str, endpoint: str | None = None) -> int | None:
    """Objects under `prefix` EXCLUDING the sentinel, or None when unobtainable.

    `rsv_binary_count` (:167-191). Distinguishes a healthy sealed release (sentinel + binaries) from the corrupt "sealed-but-empty" state (sentinel only, binaries scrubbed).

    None RATHER THAN 0 IS THE WHOLE POINT, and the twin says so at :161-166: `|| echo 0` meant an unreachable bucket produced the same "0" as a scrubbed prefix, and 0 is precisely the value callers act on to REFUSE a release.
    """
    proc = _run(
        [
            "aws",
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket(),
            "--prefix",
            prefix,
            "--endpoint-url",
            endpoint or os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
            "--query",
            "length(Contents[?ends_with(Key, `/%s`) == `false`] || `[]`)" % SENTINEL_KEY,
            "--output",
            "text",
        ]
    )
    if proc.returncode != 0:
        _log_error(
            "rsv_binary_count: list-objects-v2 failed for s3://%s/%s (exit %d)"
            % (bucket(), prefix, proc.returncode)
        )
        _indent_stderr(proc.stderr)
        return None
    count = proc.stdout.strip("\n")
    # "None" is how list-objects-v2 spells a genuinely absent prefix.
    if count == "None":
        count = "0"
    if not re.fullmatch(r"[0-9]+", count):
        _log_error(
            "rsv_binary_count: unparseable count '%s' for s3://%s/%s" % (count, bucket(), prefix)
        )
        return None
    return int(count)


def sentinel_exists(product: str, version: str, endpoint: str | None = None) -> Probe:
    """YES sealed, NO genuinely absent, UNKNOWN could not tell.

    `rsv_sentinel_exists` (:207-231). The third state is the point: this used to be a bare `>/dev/null 2>&1`, so expired credentials, a 5xx and a DNS failure all returned the same "absent" as a genuinely missing sentinel, which is a confident answer from a probe that never ran.

    A 404 IS THE ONLY FAILURE THAT MEANS ABSENT. Anything else means the question was not answered, and an unanswered question is not a `no`. The twin decides that by grepping the CAPTURED STDERR for `404|Not Found| NoSuchKey`, case-insensitively, and that text match is reproduced verbatim rather than replaced with an exit-code table: the aws CLI returns 254 for both a 404 and an
    auth failure, so the exit code cannot tell them apart and the message is genuinely the only signal available.
    """
    proc = _run(
        [
            "aws",
            "s3api",
            "head-object",
            "--bucket",
            bucket(),
            "--key",
            "%s/%s/%s" % (product, version, SENTINEL_KEY),
            "--endpoint-url",
            endpoint or os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
        ]
    )
    if proc.returncode == 0:
        return Probe.YES
    if re.search(r"404|Not Found|NoSuchKey", proc.stderr, re.IGNORECASE):
        return Probe.NO
    _log_error(
        "rsv_sentinel_exists: could not determine whether %s/%s/%s exists (exit %d); "
        "this is NOT evidence that it is missing"
        % (product, version, SENTINEL_KEY, proc.returncode)
    )
    _indent_stderr(proc.stderr)
    return Probe.UNKNOWN


def get_sentinel_payload(product: str, version: str, endpoint: str | None = None) -> str:
    """The JSON body of `<product>/<version>/.released`, or "" when absent.

    `rsv_get_sentinel_payload` (:235-240). FAILS OPEN by design (`|| true` plus `2>/dev/null`), so an unreachable bucket and an absent sentinel both yield "". Carried unchanged, and it is the same conflation DEFECT 2 names, in a fourth place: `write-release-sentinel.sh:140` uses this for a READBACK VERIFICATION, so a torn network read there reads as "the sentinel I just wrote is
    not there".
    """
    proc = _run(
        [
            "aws",
            "s3",
            "cp",
            "s3://%s/%s/%s/%s" % (bucket(), product, version, SENTINEL_KEY),
            "-",
            "--endpoint-url",
            endpoint or os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
        ]
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _indent_stderr(text: str) -> None:
    """`[[ -s "$err" ]] && sed 's/^/    /' "$err" >&2`. Nothing for empty text."""
    if not text:
        return
    for line in records(text):
        print("    %s" % line, file=sys.stderr)


# --------------------------------------------------------------------------- Pre-contract floor (where the sentinel contract starts) ---------------------------------------------------------------------------


def pre_contract_floor(
    cli_versions: list[str],
    *,
    root: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """The oldest version still subject to the bijection check.

    `rsv_pre_contract_floor` (:279-320). THREE INPUTS, and the order between them is the design:

      1. OBSERVED   the oldest CLI sentinel in the supplied list.
      2. RATCHET    `.ci/config/release-contract-floor.txt`, a monotonic
                    high-water mark stored in git. It protects the
                    all-sentinels-empty case; see DEFECT 2 for how much weight
                    it is currently carrying.
      3. OVERRIDE   `$RSV_GRANDFATHER_BEFORE` beats both. Tests pin synthetic
                    floors with it; production should never set it.

    Floor = max(observed, ratchet) when both are present, so it only advances.

    THE OVERRIDE IS NOT VALIDATED, matching :281-284: whatever the variable holds is printed straight back, semver or not. That is deliberate on the twin's part (a test pins a synthetic floor with it) and reproducing it means a typo'd override yields a floor that sorts before everything, which silently grandfathers the whole history. Named here rather than fixed.

    WHAT THE RATCHET DOES NOT CATCH, from the twin's own comment at :262-268: the "oldest CLI sentinel was scrubbed in isolation" case. Once observed
    advances past the scrubbed version, max(observed, ratchet) == observed and
    the scrubbed version falls below the floor and is grandfathered.
    """
    table = os.environ if env is None else env
    override = table.get("RSV_GRANDFATHER_BEFORE")
    if override:
        return override

    strict = [v for v in cli_versions if STRICT_SEMVER.match(v)]
    observed = sort_unique_versions(strict)[0] if strict else ""

    floor_file = table.get("RSV_FLOOR_FILE") or ""
    if not floor_file:
        # The twin's candidate list, IN ITS ORDER (:296-304). `$REPO_ROOT` is a shell variable the calling gate assigns; the port uses its own root
        # for that slot, and falls back to the same two relative candidates.
        #
        # The twin's first candidate is `"${REPO_ROOT:-}/.ci/config/..."`, which
        # with REPO_ROOT unset is the ABSOLUTE path `/.ci/config/...` and passes
        # the `-n "$candidate"` test. It fails `-f` on any sane filesystem, so it is a latent oddity rather than a bug; the port simply does not have a way to spell it, since `paths.repo_root()` never yields "".
        for candidate in (
            (root or paths.repo_root()) / FLOOR_FILE_REL,
            paths.ci_dir(root) / "config" / "release-contract-floor.txt",
            pathlib.Path(FLOOR_FILE_REL),
        ):
            if candidate.is_file():
                floor_file = str(candidate)
                break

    ratchet = ""
    if floor_file and pathlib.Path(floor_file).is_file():
        for line in records(pathlib.Path(floor_file).read_text(encoding="utf-8")):
            if STRICT_SEMVER.match(line):
                ratchet = line
                break

    if not observed:
        return ratchet
    if not ratchet:
        return observed
    return max(observed, ratchet, key=version_key)


# ---------------------------------------------------------------------------
# Assertions (pure; no I/O -- feed strings)
# ---------------------------------------------------------------------------


def assert_bijection(
    cli_versions: list[str],
    tag_versions: list[str],
    in_flight: str = "",
    *,
    root: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[list[str], int]:
    """(the lines to print, 0 on bijection / 1 on any drift finding).

    `rsv_assert_bijection` (:341-425). For every strict-semver version seen in either input, require BOTH (committed) or NEITHER (absent).

    RETURNED RATHER THAN PRINTED, so a caller can assert on the decision without capturing a stream. The twin echoes to stdout and returns the same two codes; the CLI below prints them in order and is what the differential runs.

    `in_flight` is the one version this CI run is building, excluded so the gate does not false-positive on its own in-flight release.
    """
    out: list[str] = []
    floor = pre_contract_floor(cli_versions, root=root, env=env)
    if not floor:
        # Neither sentinels nor an override: the contract is not in effect for this state at all (a fresh dev bucket). See DEFECT 2 for the other way to reach this line, which is the one that matters.
        out.append(
            "OK: release-state bijection holds -- no cli sentinels yet (contract not in effect)"
        )
        return out, 0

    def drop_pre_contract(values: list[str]) -> list[str]:
        """`rsv_drop_pre_contract` (:365-378), as a closure. See DEFECT 3.

        Keep v iff v sorts equal-or-after the floor. The twin decides that with `printf '%s\\n%s\\n' "$floor" "$v" | sort -V | head -1`, i.e. it keeps v when the FLOOR is the older of the two. `min(...)` with a stable key returns its first argument on a tie, which is the same thing `head -1` does with `$floor` printed first, so the equality case agrees without
        needing the explicit `[[ "$v" == "$floor" ]]` shortcut the twin has.
        """
        kept: list[str] = []
        for value in values:
            if not value:
                continue
            if value == floor or min(floor, value, key=version_key) == floor:
                kept.append(value)
        return kept

    cli_kept = drop_pre_contract(cli_versions)
    tag_kept = drop_pre_contract(tag_versions)

    cli_set = set(cli_kept)
    tag_set = set(tag_kept)
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
    in_flight: str = "",
) -> tuple[list[str], int]:
    """(the lines to print, 0 when the pointer is consistent and tagged).

    `rsv_assert_channel_pointer_tagged` (:449-496). THE RELATION THE BIJECTION DOES NOT COVER: a `bump-none` merge correctly skips both the sentinel and the tag, so those two stay in step while the channel pointer is advanced anyway. It happened three times (PRs #573, #574, #576, all resolving to 1.3.1) and would have half-applied a production release across eu/us/asia on
    2026-09-01, because promote-stable reads the manifest and then checks out `ref: v<version>`.

    PURE, deliberately, and the twin says why at :440-443: `aws` is not installable on the maintainer's host or in the devbox, so an I/O-coupled assertion here would be untestable locally, which is how a release gate ends up unverified.
    """
    out: list[str] = []
    drift = 0

    # An unreadable pointer is NOT a clean channel. Both files are written seconds apart by the same uploader, so a missing one means the read failed or the write tore; either way the question was not answered.
    if not latest_ver or not manifest_ver:
        out.append(
            "DRIFT %s: could not read the channel pointer (latest='%s' manifest='%s'); "
            "an unreadable pointer is never a pass"
            % (channel, latest_ver or "<empty>", manifest_ver or "<empty>")
        )
        return out, 1

    if latest_ver != manifest_ver:
        out.append(
            "DRIFT %s: latest.json says '%s' but manifest.json says '%s'. They are written "
            "seconds apart, so this is a torn write, and install.sh (latest.json) and the "
            "auto-updater (manifest.json) will disagree." % (channel, latest_ver, manifest_ver)
        )
        drift = 1

    # The in-flight version legitimately has no tag yet: the pointer for release X is written before X's tag is pushed. Excluding it is what makes this relation safe to run on the release path at all.
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


# --------------------------------------------------------------------------- CLI ---------------------------------------------------------------------------


def _read_list(spec: str | None) -> list[str]:
    """A newline list from a file, from `-` for stdin, or from an inline value.

    An ABSENT `--cli`/`--tags` is an EMPTY LIST and not an error, because that is a state the contract has an answer for (a fresh dev bucket). An UNREADABLE file is an error, because that is a question nobody answered.
    """
    if spec is None:
        return []
    if spec == "-":
        return records(sys.stdin.read())
    path = pathlib.Path(spec)
    if path.is_file():
        return records(path.read_text(encoding="utf-8"))
    return records(spec)


def _opt(argv: list[str], name: str) -> str | None:
    index = argv.index(name) if name in argv else -1
    return argv[index + 1] if 0 <= index < len(argv) - 1 else None


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.split("COMMAND-LINE ENTRY POINT")[-1].strip(), file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]
    endpoint = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")

    if verb == "bijection":
        lines, rc = assert_bijection(
            _read_list(_opt(rest, "--cli")),
            _read_list(_opt(rest, "--tags")),
            _opt(rest, "--in-flight") or "",
        )
        for line in lines:
            print(line)
        return rc

    if verb == "pointer":
        positional = [a for a in rest if not a.startswith("--")]
        # The three positionals are consumed BEFORE the flag values, so a `--tags` argument cannot be mistaken for the channel.
        for flag in ("--tags", "--in-flight"):
            value = _opt(rest, flag)
            if value in positional:
                positional.remove(value)
        if len(positional) < 3:
            print("pointer needs <channel> <latest> <manifest>", file=sys.stderr)
            return 2
        lines, rc = assert_channel_pointer_tagged(
            positional[0],
            positional[1],
            positional[2],
            _read_list(_opt(rest, "--tags")),
            _opt(rest, "--in-flight") or "",
        )
        for line in lines:
            print(line)
        return rc

    if verb == "floor":
        floor = pre_contract_floor(_read_list(_opt(rest, "--cli")))
        if floor:
            print(floor)
        return 0

    if verb == "sentinels":
        if not rest:
            print("sentinels needs a product", file=sys.stderr)
            return 2
        for version in list_sentinels(rest[0], endpoint):
            print(version)
        return 0

    if verb == "tags":
        for version in list_git_tags():
            print(version)
        return 0

    if verb == "binary-count":
        if not rest:
            print("binary-count needs a prefix", file=sys.stderr)
            return 2
        count = binary_count(rest[0], endpoint)
        if count is None:
            return 1
        print(count)
        return 0

    if verb == "sentinel-exists":
        if len(rest) < 2:
            print("sentinel-exists needs <product> <version>", file=sys.stderr)
            return 2
        return sentinel_exists(rest[0], rest[1], endpoint).rc

    if verb == "prefix-nonempty":
        if not rest:
            print("prefix-nonempty needs a prefix", file=sys.stderr)
            return 2
        return prefix_nonempty(rest[0], endpoint).rc

    if verb == "payload":
        if len(rest) < 2:
            print("payload needs <product> <version>", file=sys.stderr)
            return 2
        payload = get_sentinel_payload(rest[0], rest[1], endpoint)
        if payload:
            sys.stdout.write(payload)
        return 0

    print("unknown verb: %s" % verb, file=sys.stderr)
    return 2


__all__ = [
    "CHANNELS",
    "DEFAULT_BUCKET",
    "FLOOR_FILE_REL",
    "SENTINEL_KEY",
    "SENTINEL_LINE",
    "STRICT_SEMVER",
    "Probe",
    "assert_bijection",
    "assert_channel_pointer_tagged",
    "binary_count",
    "bucket",
    "get_sentinel_payload",
    "list_git_tags",
    "list_sentinels",
    "pre_contract_floor",
    "prefix_nonempty",
    "records",
    "sentinel_exists",
    "sort_unique_versions",
    "version_key",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
