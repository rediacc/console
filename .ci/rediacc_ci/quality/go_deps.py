"""Go direct dependencies must be up to date across every Go submodule.

Ported from `.ci/scripts/quality/check-go-deps.sh`, which is NOT deleted; see
`rediacc_ci.quality.__init__` for why both copies live until W7 phase 5.

-----------------------------------------------------------------------------
THE TWIN'S ARCHAEOLOGY, CARRIED. Everything down to PORT NOTES is the bash
file's own prose, transliterated rather than summarised.
-----------------------------------------------------------------------------

WHY THIS MATTERS. `govulncheck` only catches registered CVEs. A package can be
multiple minor versions behind (with a security fix in between) before the vuln
is registered. This check enforces freshness proactively, catching stale deps
before they become a security issue.

Usage:
  python3 -m rediacc_ci.quality.go_deps

Exit codes:
  0 - All direct Go deps are up-to-date (or blocked/major only)
  1 - Outdated minor/patch deps found

THE BLOCKLIST is loaded through the shared BLOCKER-aware parser, and the gate
fails loudly if any entry lacks a substantive `# BLOCKER: <reason>` annotation.
The three libraries the twin sources carry their own BLOCKER lines, which are
the reason each is there and are carried here:

  * `blocker-validator.sh` -- shared BLOCKER parser plus quality validator, used
    by every suppression gate.
  * `age-check.sh` -- age-based rot detection for blocklist entries; forces
    yearly re-review.
  * `release-age.sh` -- shared daily-batch freshness rule; defers just-published
    module updates like the npm gates.

A FAILED PROBE IS NOT "NOTHING IS OUTDATED". The module probe used to read
`go list ... 2>/dev/null | jq ... 2>/dev/null || true`, so any failure of either
command produced an empty result set, which is byte-identical to a clean tree:
the gate printed "All Go direct dependencies are up-to-date" and exited 0.
Observed 2026-07-27: a local run reported all-clean while CI failed on the same
commit, because `go list` was exiting 1 (go.mod requires go >= 1.25 and the
toolchain on PATH was 1.24). The gate was not disagreeing with CI, it was
silently reporting nothing at all.

So the probe's exit status is now load-bearing, and a failure is reported to the
caller through a SENTINEL LINE rather than swallowed. In the twin the sentinel
(not a bare `exit 1`) is required because the probe runs inside a process
substitution, where an exit would be invisible to the caller. That constraint is
gone in Python and the sentinel is kept anyway: it is the wire format the
aggregation loop parses, and changing it would change what the gate prints.

AN EMPTY MODULE LIST means the probe returned nothing usable. `go list -m` on a
real module always emits at least the main module, so zero is broken, not clean.

THE FRESHNESS DEFERRAL holds a just-published update until the next UTC day
after it ages 24h. An unparseable timestamp used to vanish into `|| echo ""`.
The direction is safe (no deferral is applied, so the module is still reported
as outdated and the gate stays red rather than going quiet), but silence still
hides a real breakage: if the upstream timestamp format ever changed, EVERY
module would silently lose its minimum-release-age deferral and the gate would
start demanding bumps it should be holding back. So it warns on stderr, which
does not disturb the machine-readable records the probe writes to stdout.

A PROBE THAT COULD NOT RUN IS A HARD FAILURE, checked BEFORE the all-good path.
Reporting "up-to-date" on the strength of a command that errored is the exact
defect that guard replaces. One broken submodule still lets the others be
checked, and the run then fails loudly at the end; it is never treated as
up-to-date.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

ZERO GO SUBMODULES EXITS 0, AND THAT IS THE TWIN'S BEHAVIOUR, NOT A CHOICE MADE
HERE. `log_info "No Go submodules found to check"; exit 0` is a vacuity hole: a
`private/` that lost its submodules, or a checkout where `git submodule update
--init` was never run, reports a clean bill of health having probed nothing.
This port reproduces it EXACTLY, because a port that fixes a bug changes the
verdict and the differential would rule MISMATCH on the tree that proves the fix
right. It is reported as a defect in the twin, and whoever retires the twin owns
the fix. The `--selftest` below pins the current behaviour with a control that
NAMES it as a hole, so the day it is closed the control fails and says why.

`jq` BECOMES `json`, IN TWO PLACES, AND THE ERROR PATH IS KEPT. The twin runs
`jq -rs 'length'` and then `jq -rs '.[] | select(...) | "..."'`, and reports a
failure of the second as `__PROBE_FAILED__ jq failed to parse go-list output`.
Python parses the same concatenated JSON stream itself, and a stream it cannot
read produces the same sentinel with the same prefix, so the aggregation and the
message a developer reads are unchanged. `-s` (slurp) over a stream of
back-to-back objects is what `go list -json` emits; the reader below implements
exactly that and nothing more general.

THE TIMESTAMP IS STILL PARSED BY `date -u -d`, DELIBERATELY. Python's
`datetime.fromisoformat` accepts a different set of strings from GNU date, and
this value comes from `go list`'s `.Update.Time`, i.e. from a tool this repo
does not control. A port that parsed it differently would defer a module the
twin demands, or demand one the twin defers, on some future Go release and
nowhere in any fixture. Shelling out keeps ONE parser. It also keeps the twin's
GNU-only dependency, which is worth stating out loud rather than discovering on
macOS: `date -u -d` is not BSD date, and this gate has always been that way.

THE FRESHNESS RULE IS STILL `scripts/lib/release-age.ts`. The bash `release-age.sh`
is a SHIM, not an implementation -- the rule collapsed into the TypeScript on
2026-09-06 -- so the faithful port of a shim is another shim, not a third copy of
the rule. The three-rung runner ladder is carried with it, including the measured
timings that decided the order (`node --experimental-strip-types` 0.11 s,
`node_modules/.bin/tsx` 0.55 s, `npx tsx` 0.98 s, warm, 2026-09-06) and the
PROOF before adoption: the fast path is accepted only if a real query answers
with an integer, so a future Node that renames or drops the flag falls through to
tsx instead of poisoning every verdict. That matters because the fail-closed
policy turns an unreachable delegate into "deferred", and a freshness gate stuck
on "deferred" is a gate that has gone quiet.

THE 86400-SECOND FALLBACK IS THE CALLER'S POLICY AND STAYS ON THIS SIDE. The
TypeScript `getMinReleaseAgeMs()` returns 0 (deferral disabled) when `.npmrc`
carries no key; the bash shim has always fallen back to 24h. The divergence is
preserved here rather than silently resolved in either direction. Unreachable
today in any case: `check-npmrc.sh` gates the key's presence.

THE MEMO CACHES SURVIVE, and the reason the twin spells them as globals written
by `__..._ensure_*` helpers does not: a bash caller writing `x=$(f)` runs `f` in
a SUBSHELL, so every cache line `f` wrote is discarded when the subshell exits.
Written the obvious way, that file would have spawned the delegate on every call
and the memo would have been decorative. Python has no such trap, so the caches
here are plain dictionaries; the constraint is written down because its
disappearance is invisible in the result.

`emit_advisory` IS REPRODUCED, NOT IMPORTED. The twin's age check reaches
`emit-advisory.sh`, whose contract is eight optional associative arrays keyed by
advisory id plus the `::error::` / `::warning::` Actions form. This gate
populates NONE of those arrays, so the only shape it can produce is
`<id> (<name>)` on the error stream followed by `  Fix:` and `  Action:` on
stdout. That narrow shape is what is implemented here; a general port of
`emit_advisory` belongs with `audit.sh`, its other caller.

THE STREAM SPLIT IS THE TWIN'S AND IT IS ODD ON PURPOSE. `ci_error` writes the
header to STDERR (through common.sh's `log_error`) while the `  Fix:` and
`  Action:` continuation lines go to STDOUT via a bare `echo`. That is exactly
what `emit-advisory.sh` does, and the 2026-09-06 deference rule in that file
exists because an earlier version clobbered common.sh's TTY-gated logger and
flipped `log_info` / `log_warn` / `log_success` from stderr to stdout, leaking
colour escapes into anything that piped a gate's stdout for data. The split is
reproduced rather than tidied.

THE BASH `read` FIELD SPLIT IS REPRODUCED, WART AND ALL. The aggregation loop is
`IFS=' ' read -r path current latest kind`, so a sentinel line
`__PROBE_FAILED__ go-list exit=2 <stderr text>` lands as
path=`__PROBE_FAILED__`, current=`go-list`, latest=`exit=2` and kind=the whole
remaining text, which the report then prints as `  <name>: go-list exit=2 ...`.
That is not a data structure anyone designed; it is what the gate prints today,
so `_read_fields` below implements bash's rule (leading and trailing delimiter
runs stripped, the LAST variable takes the remainder verbatim) rather than
`str.split()`, which would re-join the remainder with single spaces.

EXIT CODES ARE UNCHANGED: 0 and 1 only. The twin has no setup-error code, and 77
is reserved by the W7 contract for cannot-run.
"""

import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls
from rediacc_ci.core import age as agecheck
from rediacc_ci.core import allowlist

# The list moved to `.ci/policy/` in W4 P2 (commit b80552370). It is spelled out
# here exactly as the twin spells it, and NOT reconstructed from a helper: the
# TypeScript seam `scripts/lib/policy-paths.ts` is deliberately a pure join with
# no filesystem access, and its rule 3 refuses a transition fallback, so there is
# one location at a time and hard-coding it here cannot half-land.
BLOCKLIST_REL = ".ci/policy/.go-deps-upgrade-blocklist"

# `age-check.sh`'s two knobs, with the same environment overrides and the same
# defaults. `readonly AGE_WARN_DAYS="${AGE_WARN_DAYS:-180}"`.
AGE_WARN_ENV = "AGE_WARN_DAYS"
AGE_FAIL_ENV = "AGE_FAIL_DAYS"
AGE_WARN_DAYS_DEFAULT = 180
AGE_FAIL_DAYS_DEFAULT = 365

# `release-age.sh`'s caller policy. See the PORT NOTES: the TypeScript returns 0
# for a missing key and this side has always used 24h.
RELEASE_AGE_DEFAULT_WINDOW_SECONDS = 86400
RELEASE_AGE_TS = "scripts/lib/release-age.ts"

# The wire format between the probe and the aggregation loop.
PROBE_SENTINEL = "__PROBE_FAILED__"

# `head -c 300` on the probe's stderr and `head -c 200` on jq's complaint. Both
# are TRUNCATIONS, not summaries: a 4 KB Go error shows its first 300 bytes on
# both sides, and dropping the truncation would make the port noisier than the
# twin on exactly the tree where the gate fires.
PROBE_STDERR_BYTES = 300
PARSE_ERROR_BYTES = 200

# U+2014 appears in three of the twin's messages. Written as an escape rather
# than as the character so this file stays ASCII: the repo's prose rules forbid
# the literal, and the byte still has to reach the output because the message
# text is what the differential compares.
_EM_DASH = "\u2014"


# ---------------------------------------------------------------------------
# emit-advisory.sh, in the one shape this gate can produce
# ---------------------------------------------------------------------------


def _in_ci() -> bool:
    """`[[ "${CI:-}" == "true" ]]`, the exact test, not a truthiness check."""
    return os.environ.get("CI", "") == "true"


def ci_error(message: str) -> None:
    """`::error::<m>` on stdout under CI, `log_error <m>` on stderr otherwise.

    THE PREFIX IS THE ENVIRONMENT'S DECISION, NOT THE GATE'S. One finding, two
    renderings; the shadow comparator strips both and keeps the severity, which
    is why a port may not quietly settle on one of them.
    """
    if _in_ci():
        print("::error::%s" % message)
    else:
        log.error(message)


def ci_warn(message: str) -> None:
    """The warn twin of `ci_error`."""
    if _in_ci():
        print("::warning::%s" % message)
    else:
        log.warn(message)


def emit_advisory(level: str, ident: str, name: str, fix_hint: str, action_hint: str = "") -> None:
    """`emit_advisory <level> <id> <name> <fix> [action]`, narrow form.

    None of the eight `ADV_*` arrays is populated by this gate, so severity,
    GHSA, title, url, range, patched version and description are all empty and
    every branch that reads them is skipped. The header is therefore exactly
    `<id> (<name>)`, and the two hint lines follow on STDOUT.
    """
    header = ident
    if name:
        header = "%s (%s)" % (ident, name)
    if level == "error":
        ci_error(header)
    else:
        ci_warn(header)
    if fix_hint:
        print("  Fix: %s" % fix_hint)
    if action_hint:
        print("  Action: %s" % action_hint)


def check_entry_age(
    file: str, entry: str, ident: str, name: str = "", root: pathlib.Path | None = None
) -> bool:
    """`check_entry_age`: emit the advisory, return True when it is an ERROR.

    THE EXIT CODE IS THE RETURN VALUE, and only `error` counts. A warn returns
    success exactly as the bash did, so a caller aggregating returns does not
    start failing on reminders.

    A VERDICT THE SHIM CANNOT READ IS NOT A PASS. The bash reads a TAB-separated
    line back from `rediacc_ci.core.age` and treats an unknown level as a
    failure, because anything other than the three known levels means the
    contract moved underneath it. Here the object is the contract, so the same
    refusal is expressed as an explicit else-branch rather than a parse.
    """
    display = name or ident
    warn_days = int(os.environ.get(AGE_WARN_ENV) or AGE_WARN_DAYS_DEFAULT)
    fail_days = int(os.environ.get(AGE_FAIL_ENV) or AGE_FAIL_DAYS_DEFAULT)
    days = agecheck.entry_age_days(file, entry, root=root)
    v = agecheck.verdict(days, warn_days, fail_days, _in_ci())
    if v.level in ("error", "warn"):
        emit_advisory(v.level, ident, display, v.message, v.remedy)
    elif v.level != "ok":
        print(
            "age-check: unreadable verdict '%s' for %s/%s" % (v.level, file, entry),
            file=sys.stderr,
        )
        return True
    return v.failed


# ---------------------------------------------------------------------------
# release-age.sh, as a shim over the same TypeScript
# ---------------------------------------------------------------------------


class ReleaseAge:
    """The freshness delegate, with the twin's two memo caches.

    ONE INSTANCE PER RUN, held by `main`, because the twin's caches are shell
    globals that live for the length of the process. A module-level singleton
    would outlive a `--selftest` case and let one control's answer leak into the
    next one's, which is the shape of a control that cannot fail.
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self._runner: list[str] | None = None
        self._window: int | None = None
        self._eligible: dict[tuple[int, int], int] = {}

    @property
    def _lib(self) -> str:
        return str(self.root / RELEASE_AGE_TS)

    def _resolve_runner(self) -> list[str]:
        """The three-rung ladder, resolved ONCE, with the fast path PROVEN.

        All three execute the SAME file, so they cannot answer differently; only
        the loader varies. The probe runs a real query and accepts the runner
        only if it answers with an integer.
        """
        if self._runner is not None:
            return self._runner
        probe = self._capture(["node", "--experimental-strip-types", self._lib], "--window-seconds")
        if probe is not None and re.fullmatch(r"[0-9]+", probe):
            self._runner = ["node", "--experimental-strip-types"]
            return self._runner
        local_tsx = self.root / "node_modules" / ".bin" / "tsx"
        if os.access(str(local_tsx), os.X_OK):
            self._runner = [str(local_tsx)]
            return self._runner
        self._runner = ["npx", "tsx"]
        return self._runner

    def _capture(self, argv: list[str], *args: str) -> str | None:
        """Run the delegate from the repository root; None when it could not."""
        try:
            proc = subprocess.run(
                [*argv, *args],
                cwd=str(self.root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    def _delegate(self, *args: str) -> str | None:
        runner = self._resolve_runner()
        return self._capture([*runner, self._lib], *args)

    def window_seconds(self) -> int:
        """The base freshness window. ALWAYS succeeds; see the fallback note."""
        if self._window is not None:
            return self._window
        answer = self._delegate("--window-seconds")
        if answer is None or not re.fullmatch(r"[0-9]+", answer) or int(answer) <= 0:
            self._window = RELEASE_AGE_DEFAULT_WINDOW_SECONDS
        else:
            self._window = int(answer)
        return self._window

    def eligible_epoch(self, publish_epoch: int, window: int) -> int | None:
        """The epoch at which the release becomes actionable, or None.

        THE DELEGATE COULD NOT ANSWER is said out loud on stderr rather than
        answered with an invented number: a silent fallback here would make every
        version look eligible (or every one deferred, depending on the sentinel
        chosen), and a freshness gate that quietly stops deferring is exactly the
        shape this repo keeps getting caught by.
        """
        key = (publish_epoch, window)
        if key in self._eligible:
            return self._eligible[key]
        answer = self._delegate("--eligible-epoch", str(publish_epoch), str(window))
        if answer is None or not re.fullmatch(r"-?[0-9]+", answer):
            print(
                "release-age: could not reach scripts/lib/release-age.ts (tsx missing "
                "or failing); treating '%s' as DEFERRED" % publish_epoch,
                file=sys.stderr,
            )
            return None
        self._eligible[key] = int(answer)
        return self._eligible[key]

    def is_deferred(self, publish_epoch: str, now: int | None = None) -> bool:
        """True when `now < eligibleAt`. FAIL-CLOSED on anything unusable.

        An empty or unparseable publish epoch is DEFERRED, because a lookup
        hiccup must never turn into a false "must upgrade" gate failure. The same
        rule covers a delegate that cannot run, which `eligible_epoch` has
        already reported loudly on stderr.
        """
        if not publish_epoch or not re.fullmatch(r"[0-9]+", publish_epoch):
            return True
        moment = int(time.time()) if now is None else now
        eligible = self.eligible_epoch(int(publish_epoch), self.window_seconds())
        if eligible is None:
            return True
        return moment < eligible


# ---------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------


def get_major(version: str) -> int:
    """`sed 's/^v//' | cut -d. -f1 | grep -o '^[0-9]*' || echo 0`.

    Handles `v1.2.3` and `v1+incompatible`. `sed 's/^v//'` strips ONE leading
    `v`; `cut -d. -f1` takes everything before the first dot, or the whole string
    when there is none.

    THE TWIN'S `|| echo "0"` IS DEAD CODE, measured rather than assumed. The
    pipeline ends in `grep -o '^[0-9]*'`, and `^[0-9]*` MATCHES a zero-length
    string at the start of any input, so GNU grep exits 0 while printing
    nothing:

        $ echo latest | grep -o '^[0-9]*' ; echo $?
        0

    The fallback therefore never runs, and `get_major vlatest` returns the EMPTY
    STRING rather than "0". The twin survives that because its only consumer is
    `[[ "$lat_major" -gt "$cur_major" ]]`, where bash arithmetic coerces an
    empty operand to 0. This function returns the integer 0 for the same inputs,
    which is the same comparison with the coercion made explicit. The dead
    fallback is reported as a finding against the twin, never fixed inside a
    port.
    """
    stripped = version.removeprefix("v")
    head = stripped.split(".")[0]
    digits = re.match(r"[0-9]*", head).group(0)
    return int(digits) if digits else 0


def _read_fields(line: str, count: int) -> list[str]:
    """`IFS=' ' read -r a b c d` on one line, as a list of `count` strings.

    Leading and trailing space runs are stripped, interior runs split, and the
    LAST variable takes the remainder VERBATIM (interior spacing preserved).
    Missing fields are the empty string, which is what `read` leaves them as.
    `str.split()` would collapse the remainder's spacing and `str.split(" ")`
    would produce empty fields for a run, so neither is the same rule.
    """
    rest = line.strip(" ")
    out: list[str] = []
    for _ in range(count - 1):
        if not rest:
            out.append("")
            continue
        head, sep, tail = rest.partition(" ")
        out.append(head)
        rest = tail.lstrip(" ") if sep else ""
    out.append(rest)
    return out


def slurp_json(raw: str) -> list[dict]:
    """`jq -s` over a stream of back-to-back JSON objects.

    `go list -json` emits objects one after another with no separator and no
    enclosing array, which is exactly what `-s` (slurp) is for. `raw_decode` in
    a loop is the same rule and nothing more general; anything it cannot read
    raises, and the caller turns that into the twin's parse-failure sentinel.
    """
    decoder = json.JSONDecoder()
    items: list[dict] = []
    index = 0
    length = len(raw)
    while index < length:
        while index < length and raw[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        value, index = decoder.raw_decode(raw, index)
        items.append(value)
    return items


def parse_date(value: str) -> str | None:
    """`date -u -d "<value>" +%s`, or None when GNU date refuses it.

    Shelled out on purpose; see the PORT NOTES. The value comes from `go list`,
    a tool this repo does not control, and two parsers would disagree about some
    future format on nobody's fixture.
    """
    try:
        proc = subprocess.run(
            ["date", "-u", "-d", value, "+%s"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def check_go_dir(
    directory: pathlib.Path, blocked: dict[str, str], freshness: ReleaseAge
) -> list[str]:
    """One Go module directory. Returns `MODULE CURRENT LATEST TYPE` lines.

    TYPE is `major`, `minor`, `blocked` or `toofresh`, or the whole line is a
    `__PROBE_FAILED__` sentinel. Warnings go to stderr, which does not disturb
    the machine-readable records this function returns.
    """
    try:
        proc = subprocess.run(
            ["go", "list", "-u", "-m", "-json", "all"],
            cwd=str(directory),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        # bash reports `command not found` as status 127 from the subshell.
        return ["%s go-list exit=127 go: command not found" % PROBE_SENTINEL]

    if proc.returncode != 0:
        detail = proc.stderr.replace("\n", " ")[:PROBE_STDERR_BYTES]
        return ["%s go-list exit=%d %s" % (PROBE_SENTINEL, proc.returncode, detail)]

    try:
        modules = slurp_json(proc.stdout)
    except ValueError as exc:
        detail = str(exc).replace("\n", " ")[:PARSE_ERROR_BYTES]
        return ["%s jq failed to parse go-list output: %s" % (PROBE_SENTINEL, detail)]

    if not modules:
        return ["%s go-list returned no modules at all" % PROBE_SENTINEL]

    records: list[str] = []
    for item in modules:
        if item.get("Indirect") is True:
            continue
        update = item.get("Update")
        if update is None:
            continue
        path = item.get("Path", "")
        current = item.get("Version", "")
        latest = update.get("Version", "")
        uptime = update.get("Time") or ""
        if not path:
            continue

        if path in blocked:
            records.append("%s %s %s blocked" % (path, current, latest))
            continue

        epoch = ""
        if uptime:
            parsed = parse_date(uptime)
            if parsed is None:
                log.warn(
                    "could not parse update timestamp '%s' for %s; freshness "
                    "deferral not applied" % (uptime, path)
                )
            else:
                epoch = parsed

        if epoch and freshness.is_deferred(epoch):
            records.append("%s %s %s toofresh" % (path, current, latest))
        elif get_major(latest) > get_major(current):
            records.append("%s %s %s major" % (path, current, latest))
        else:
            records.append("%s %s %s minor" % (path, current, latest))
    return records


def go_dirs(root: pathlib.Path) -> list[str]:
    """`for dir in "$REPO_ROOT/private"/*/` with a `go.mod` in it.

    The glob is SORTED by the shell, so the report's order is alphabetical, and
    a directory without `go.mod` is skipped rather than probed. A missing
    `private/` makes the glob match nothing at all, which is the vacuity hole
    named in the PORT NOTES.
    """
    private = root / "private"
    if not private.is_dir():
        return []
    found: list[str] = []
    for entry in sorted(os.listdir(str(private))):
        candidate = private / entry
        if candidate.is_dir() and (candidate / "go.mod").is_file():
            found.append(str(candidate))
    return found


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 when nothing minor is outdated, 1 otherwise."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    blocklist_file = root / BLOCKLIST_REL

    blocked: dict[str, str] = {}
    if blocklist_file.is_file():
        entries = allowlist.parse_file(blocklist_file, missing_ok=True)
        # `${!BLOCKED_MODULES[@]}` is a bash associative array, so a repeated
        # entry appears ONCE and the LAST reason wins. `pairs()` is that
        # projection; iterating `entries` would report a duplicate twice.
        blocked = allowlist.pairs(entries)

        failures = [
            message
            for entry, reason in blocked.items()
            for message in _verify_one(entry, reason, str(blocklist_file))
        ]
        if failures:
            for message in failures:
                head, _, tail = message.partition("\n")
                ci_error(head)
                if tail:
                    print(tail)
            log.error(
                "Go deps blocklist entries must include quality "
                "'# BLOCKER: <reason>' %s strict gate enforced" % _EM_DASH
            )
            return 1

        age_fail = False
        for module in blocked:
            if check_entry_age(
                str(blocklist_file), module, module, "go-deps-blocklist entry", root=root
            ):
                age_fail = True
        if age_fail:
            fail_days = int(os.environ.get(AGE_FAIL_ENV) or AGE_FAIL_DAYS_DEFAULT)
            log.error(
                "Go deps blocklist entries older than %d days must be re-reviewed" % fail_days
            )
            return 1

    dirs = go_dirs(root)
    if not dirs:
        # THE VACUITY HOLE, REPRODUCED. See the PORT NOTES: this is the twin's
        # verdict and changing it is the job of whoever retires the twin.
        log.info("No Go submodules found to check")
        return 0

    freshness = ReleaseAge(root)
    all_minor: list[str] = []
    all_major: list[str] = []
    all_blocked: list[str] = []
    all_toofresh: list[str] = []
    dirs_with_minor: list[str] = []
    probe_failures: list[str] = []

    for directory in dirs:
        name = os.path.basename(directory)
        log.step("Checking Go deps in %s..." % name)
        has_minor = False
        for line in check_go_dir(pathlib.Path(directory), blocked, freshness):
            path, current, latest, kind = _read_fields(line, 4)
            if not path:
                continue
            if path == PROBE_SENTINEL:
                probe_failures.append("  %s: %s %s %s" % (name, current, latest, kind))
                continue
            if kind == "minor":
                all_minor.append("  %s: %s %s -> %s" % (name, path, current, latest))
                has_minor = True
            elif kind == "major":
                all_major.append(
                    "  %s: %s %s -> %s (major - manual)" % (name, path, current, latest)
                )
            elif kind == "blocked":
                all_blocked.append("  %s: %s %s -> %s (blocked)" % (name, path, current, latest))
                # Surface the BLOCKER reason like the npm deps gate does.
                all_blocked.append("    Reason: %s" % blocked.get(path, ""))
            elif kind == "toofresh":
                all_toofresh.append("  %s: %s %s -> %s (too new)" % (name, path, current, latest))
        if has_minor:
            dirs_with_minor.append(directory)

    if all_minor:
        print()
        log.warn("Outdated Go direct dependencies (minor/patch - must upgrade):")
        for line in all_minor:
            print(line)
    if all_major:
        print()
        log.info("Major version updates available (manual upgrade required):")
        for line in all_major:
            print(line)
    if all_blocked:
        print()
        log.info("Blocked packages (see %s):" % BLOCKLIST_REL)
        for line in all_blocked:
            print(line)
    if all_toofresh:
        print()
        log.info("Too new %s within freshness window, deferred until next UTC day:" % _EM_DASH)
        for line in all_toofresh:
            print(line)

    # A PROBE THAT COULD NOT RUN IS A HARD FAILURE, checked BEFORE the all-good
    # path. Reporting "up-to-date" on the strength of a command that errored is
    # the exact defect this guard replaces.
    if probe_failures:
        print()
        log.error("Go dependency probe FAILED %s this is not the same as 'up-to-date':" % _EM_DASH)
        for line in probe_failures:
            print(line)
        log.error(
            "Fix the Go toolchain or module access and re-run; the gate cannot "
            "vouch for these modules."
        )
        return 1

    if not dirs_with_minor:
        if all_major:
            log.info(
                "Go deps check passed (%d major updates available - upgrade manually)"
                % len(all_major)
            )
        else:
            log.info("All Go direct dependencies are up-to-date")
        return 0

    return 1


def _verify_one(entry: str, reason: str, file: str) -> list[str]:
    """`verify_all_blockers`, for one entry. Zero or one message."""
    if not reason:
        return [allowlist.missing_reason(entry, file)]
    rejection = allowlist.validate_reason(entry, reason, file)
    return [] if rejection is None else [rejection.message]


# ---------------------------------------------------------------------------
# The selftest
# ---------------------------------------------------------------------------

_GOOD_REASON = "upstream pins a breaking major; the migration needs its own PR and a rebuild"

_STUB_GO = """\
#!/bin/sh
# A `go` that answers from a file instead of the network. Both implementations
# resolve `go` through PATH, so this exercises the same call the twin makes.
if [ -n "${PI_GO_FAIL:-}" ]; then
  echo "go: some toolchain problem" >&2
  exit "${PI_GO_FAIL}"
fi
cat "${PI_GO_JSON}"
"""


def _module_json(path: str, current: str, latest: str, when: str = "") -> str:
    record = {"Path": path, "Version": current, "Update": {"Version": latest}}
    if when:
        record["Update"]["Time"] = when
    return json.dumps(record)


def selftest() -> int:
    """Both directions on the arithmetic, the parsers and the gate itself."""
    ctl = Controls("go-deps", floor=28, verbose=True)

    # -- THE MAJOR/MINOR ARITHMETIC, both directions -----------------------------
    ctl.check("MAJOR: a plain semver reads its major", get_major("v1.2.3"), 1)
    ctl.check("MAJOR: `+incompatible` still reads its major", get_major("v2+incompatible"), 2)
    ctl.check("MAJOR: a non-numeric head falls back to 0", get_major("vlatest"), 0)
    ctl.check("MAJOR: an empty version falls back to 0", get_major(""), 0)
    ctl.truthy("MAJOR MIRROR: v2 is greater than v1", get_major("v2.0.0") > get_major("v1.9.9"))
    ctl.falsy(
        "MAJOR MIRROR: a minor bump is NOT a major bump",
        get_major("v1.9.9") > get_major("v1.2.3"),
    )

    # -- THE bash `read` FIELD SPLIT ---------------------------------------------
    ctl.check(
        "READ: four clean fields split four ways",
        _read_fields("a b c d", 4),
        ["a", "b", "c", "d"],
    )
    ctl.check(
        "READ: the last variable keeps the remainder VERBATIM",
        _read_fields("__PROBE_FAILED__ go-list exit=2 a  b   c", 4),
        ["__PROBE_FAILED__", "go-list", "exit=2", "a  b   c"],
    )
    ctl.check(
        "READ: a short line leaves the missing fields empty",
        _read_fields("a b", 4),
        ["a", "b", "", ""],
    )

    # -- THE JSON SLURP, both directions -----------------------------------------
    ctl.check(
        "SLURP: back-to-back objects are one list",
        [d["Path"] for d in slurp_json('{"Path":"a"}\n{"Path":"b"}\n')],
        ["a", "b"],
    )
    ctl.check("SLURP: an empty stream is an empty list", slurp_json("  \n "), [])
    ctl.raises(
        "SLURP: garbage RAISES rather than reading as empty", ValueError, slurp_json, "{oops"
    )

    # -- THE DATE PARSER, both directions ----------------------------------------
    ctl.check("DATE: an RFC3339 stamp converts", parse_date("1970-01-02T00:00:00Z"), "86400")
    ctl.check("DATE MIRROR: nonsense is refused, not guessed", parse_date("not-a-date"), None)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        # THE DELEGATE IS COPIED INTO EVERY FIXTURE THAT NEEDS THE RULE, and the
        # first cut of this selftest did not do it. `ReleaseAge` resolves
        # `scripts/lib/release-age.ts` under the ROOT it is given, so a fixture
        # without it fell through to the fail-closed branch and reported EVERY
        # update as deferred. The "a 2020 release still reds" control then
        # failed, which is the control doing its job: it named a fixture that
        # could not exercise the rule rather than a rule that was wrong.
        # `paths.CI_DIR.parent` and not `paths.repo_root()`: the latter reads
        # $REDIACC_CI_ROOT, which the cases below are busy overriding.
        real_root = paths.CI_DIR.parent

        def build(
            name: str,
            blocklist: str | None,
            modules: str,
            *,
            fail: str = "",
            delegate: bool = True,
        ) -> pathlib.Path:
            tree = base / name
            (tree / "private" / "renet").mkdir(parents=True, exist_ok=True)
            (tree / "private" / "renet" / "go.mod").write_text(
                "module github.com/rediacc/renet\n\ngo 1.25\n", encoding="utf-8"
            )
            if blocklist is not None:
                (tree / pathlib.Path(BLOCKLIST_REL).parent).mkdir(parents=True, exist_ok=True)
                (tree / BLOCKLIST_REL).write_text(blocklist, encoding="utf-8")
            (tree / "modules.json").write_text(modules, encoding="utf-8")
            binary = tree / "fxbin"
            binary.mkdir(parents=True, exist_ok=True)
            (binary / "go").write_text(_STUB_GO, encoding="utf-8")
            (binary / "go").chmod(0o755)
            (tree / "fail").write_text(fail, encoding="utf-8")
            if delegate:
                (tree / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
                (tree / RELEASE_AGE_TS).write_text(
                    (real_root / RELEASE_AGE_TS).read_text(encoding="utf-8"), encoding="utf-8"
                )
                (tree / ".npmrc").write_text(
                    (real_root / ".npmrc").read_text(encoding="utf-8"), encoding="utf-8"
                )
            return tree

        def run(tree: pathlib.Path, *, fail: str = "") -> int:
            saved = {
                key: os.environ.get(key)
                for key in (paths.ROOT_ENV, "PATH", "PI_GO_JSON", "PI_GO_FAIL")
            }
            os.environ[paths.ROOT_ENV] = str(tree)
            os.environ["PATH"] = "%s%s%s" % (tree / "fxbin", os.pathsep, saved["PATH"] or "")
            os.environ["PI_GO_JSON"] = str(tree / "modules.json")
            if fail:
                os.environ["PI_GO_FAIL"] = fail
            else:
                os.environ.pop("PI_GO_FAIL", None)
            try:
                return main([])
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        main_module = '{"Path":"github.com/rediacc/renet","Version":"v0.1.0","Main":true}\n'

        clean = build("clean", None, main_module)
        ctl.check("CONTROL: a module with no updates passes", run(clean), 0)

        outdated = build(
            "outdated",
            None,
            main_module + _module_json("github.com/sirupsen/logrus", "v1.10.0", "v1.10.1"),
        )
        ctl.check("PLANT: an outdated minor dep reds the gate", run(outdated), 1)

        major = build(
            "major",
            None,
            main_module + _module_json("github.com/x/y", "v1.0.0", "v2.0.0"),
        )
        ctl.check("PLANT MIRROR: a MAJOR update alone does not red the gate", run(major), 0)

        indirect = build(
            "indirect",
            None,
            main_module
            + json.dumps(
                {
                    "Path": "github.com/z/q",
                    "Version": "v1.0.0",
                    "Indirect": True,
                    "Update": {"Version": "v1.0.1"},
                }
            ),
        )
        ctl.check("PLANT MIRROR: an INDIRECT dep is not this gate's subject", run(indirect), 0)

        blocked_tree = build(
            "blocked",
            "# BLOCKER: %s\ngithub.com/sirupsen/logrus\n" % _GOOD_REASON,
            main_module + _module_json("github.com/sirupsen/logrus", "v1.10.0", "v1.10.1"),
        )
        ctl.check(
            "SUPPRESSION: a blocklisted module stops reddening the gate", run(blocked_tree), 0
        )

        bad_reason = build(
            "bad-reason",
            "# BLOCKER: tbd\ngithub.com/sirupsen/logrus\n",
            main_module,
        )
        ctl.check("PLANT: a low-effort BLOCKER is refused", run(bad_reason), 1)

        no_reason = build("no-reason", "github.com/sirupsen/logrus\n", main_module)
        ctl.check("PLANT: an entry with no BLOCKER at all is refused", run(no_reason), 1)

        # -- THE PROBE FAILURE, which must never read as up-to-date --------------
        probing = build(
            "probe-fail", None, main_module + _module_json("github.com/a/b", "v1.0.0", "v1.0.1")
        )
        ctl.check("PLANT: a go-list that exits non-zero is a FAILURE", run(probing, fail="1"), 1)

        empty_probe = build("empty-probe", None, "")
        ctl.check("VACUITY: zero modules from go list is a FAILURE", run(empty_probe), 1)

        garbage = build("garbage", None, "{not json")
        ctl.check("VACUITY: unparseable go-list output is a FAILURE", run(garbage), 1)

        # -- THE VACUITY HOLE THE TWIN CARRIES -----------------------------------
        # PINNED, NOT ENDORSED. `private/` with no Go module exits 0 having
        # probed nothing. This control exists so the day somebody closes the
        # hole, it fails and names the twin's line as the reason it was here.
        no_modules = base / "no-modules"
        (no_modules / "private").mkdir(parents=True, exist_ok=True)
        ctl.check(
            "TWIN DEFECT (pinned, not endorsed): zero Go submodules exits 0",
            run(no_modules),
            0,
        )

        # -- THE FRESHNESS DEFERRAL, END TO END THROUGH THE GATE -----------------
        # A JUST-PUBLISHED update must be DEFERRED rather than demanded, and the
        # mirror is the same module with an ancient publish date, which must
        # still red. Two fixtures differing in exactly one field, so the control
        # cannot pass because of something else.
        now_stamp = dt.datetime.fromtimestamp(time.time(), dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh = build(
            "fresh",
            None,
            main_module + _module_json("github.com/a/b", "v1.0.0", "v1.0.1", now_stamp),
        )
        ctl.check("FRESHNESS: a just-published update is deferred, not demanded", run(fresh), 0)
        stale = build(
            "stale",
            None,
            main_module
            + _module_json("github.com/a/b", "v1.0.0", "v1.0.1", "2020-01-02T03:04:05Z"),
        )
        ctl.check("FRESHNESS MIRROR: the same update from 2020 still reds", run(stale), 1)

        # AND THE FAIL-CLOSED DIRECTION, driven for real rather than reasoned
        # about: the SAME 2020 fixture with the delegate absent must report the
        # update as deferred, because an unreachable freshness rule must never
        # turn into a false "must upgrade".
        blind = build(
            "blind",
            None,
            main_module
            + _module_json("github.com/a/b", "v1.0.0", "v1.0.1", "2020-01-02T03:04:05Z"),
            delegate=False,
        )
        ctl.check("FRESHNESS: an unreachable delegate defers rather than demands", run(blind), 0)

        # -- THE FRESHNESS DEFERRAL, ON THE DELEGATE DIRECTLY --------------------
        freshness = ReleaseAge(paths.repo_root())
        ctl.truthy(
            "FRESHNESS: an empty publish epoch is DEFERRED (fail-closed)",
            freshness.is_deferred(""),
        )
        ctl.truthy(
            "FRESHNESS: a non-numeric publish epoch is DEFERRED (fail-closed)",
            freshness.is_deferred("yesterday"),
        )
        ctl.falsy(
            "FRESHNESS MIRROR: a release from 1970 is NOT deferred",
            freshness.is_deferred("86400", now=int(time.time())),
        )
        ctl.truthy(
            "FRESHNESS: a release published now IS deferred",
            freshness.is_deferred(str(int(time.time())), now=int(time.time())),
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
