r"""A capability probe must exercise the operations its CONSUMER depends on.

Ported from `.ci/scripts/quality/check-probe-parity.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live side by side until a
committed differential ledger says otherwise.

WHY THIS EXISTS, in the twin's own words, because the incident is the design:

    Parity gate: a capability probe must exercise the operations its CONSUMER
    depends on, not a convenient subset of them.

    On 2026-08-05 the transfer drill's keyring preflight ran `keyctl add`, saw
    it succeed, and reported "keyring usable". The drill then died anyway,
    because a GitHub runner permits `keyctl add` and DENIES the read
    (`keyctl pipe`), and the read is what `KeyctlStorage.get()` actually needs.
    The probe tested a permitted operation while the operation the code depends
    on was the denied one, so it produced a confident false negative.

    That was the SIXTH instance of this class in one night (probing `clang` when
    bpf2go also needs `llvm-strip`; `curl -f` on an endpoint documented to answer
    403; `keyctl show @u` in secure-storage.ts; a liveness probe that read
    `000000` as alive; a gate whose subject never loaded). It was authored hours
    after the TRAPS.md entry describing the class, by someone who had already
    been caught by it twice. Knowing about the pattern demonstrably does not
    prevent it, which is why it needs a gate rather than a note.

    WHAT THIS CHECKS, mechanically rather than semantically: the set of `keyctl`
    subcommands invoked by the PROBE must cover the set invoked by the CONSUMER,
    minus an explicit, justified exemption list. Adding a new keyctl call to
    KeyctlStorage without teaching the probe about it is then a red, with a
    message naming the operation that would go untested.

    CONTROL-FIRST. The gate fails itself when it cannot see its own inputs: if
    either extraction yields an empty verb set, the comparison would be a
    tautology over nothing, which is the exact vacuity this repo keeps paying
    for.

COMMENT LINES ARE STRIPPED FROM THE PROBE FIRST, and the twin records why that
is not a detail:

    The first version of this gate did not strip them, so it happily counted the
    `keyctl pipe` appearing inside the preflight's own explanatory comment and
    reported parity for a probe that had the read-back REMOVED. A gate that
    cannot tell "exercises an operation" from "mentions it in prose" is the very
    defect it audits, found by running the planted-defect proof, which is the
    only reason it is not still there.

THE ARCHAEOLOGY THAT GETS TIDIED OUT, AND MUST NOT BE. The twin was FIXED at
commit 96355d3b5 on 2026-09-06, and the fix is two `|| true` suffixes that look
like noise:

    `|| true` IS LOAD-BEARING on BOTH extractions. grep exits 1 on no match and
    pipefail promotes that to the pipeline, so `set -e` killed the script at the
    ASSIGNMENT -- taking out the two "CONTROL FAILED: ... empty set" branches
    below, which exist for precisely the extraction-broke case. Reproduced
    2026-09-06 against an empty consumer file: exit 1 with no control message.

That is the whole shape of the bug class this port must not lose: the handler
written for the empty-input case was UNREACHABLE, because the language killed
the program one line above it. The Python port cannot reproduce the defect (an
empty `re.findall` is an empty list, not a fatal status), which is exactly why
the note has to survive as prose: a reader who deletes it from the twin will
delete the reason the twin's own control can fire at all.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE EXEMPTION LIST IS PRINTED NOWHERE AND THAT IS CARRIED, NOT FIXED. The twin's
`EXEMPT_VERBS=("unlink" "purge" "revoke")` is silent: a consumer verb it forgives
never appears in any line of output, so a reader of a green run cannot see which
operations were excused. The port keeps that behaviour because the differential
compares finding sets and a new line would be a divergence; it is reported as a
finding against the twin rather than repaired here.

`sort -u` IS UNDER `LC_ALL=C`, which `scripts/lib/shadow-gate.ts` pins for both
sides (`buildEnv`). Python's `sorted()` on `str` is code-point order, which
agrees with C collation for the `[a-z]` alphabet these verbs are drawn from. The
regexes admit nothing else, so the two orders cannot diverge here.

THE `sed` COMMENT STRIP REPLACES ONLY THE FIRST MATCH PER LINE, which is what
`s///` without `g` means, and the leftmost match of `[[:space:]]*#.*$` starts at
the whitespace RUN preceding the first `#`. `re.sub(..., count=1)` is the same
rule. A `#` inside a quoted shell string is therefore treated as a comment by
both sides, identically; that is a known imprecision of the twin, not of the
port.

THE PROBE PATTERN HAS THE ALTERNATED-ANCHOR SHAPE (`(^|[^-[:alnum:]_])`) THAT THE
HOUSE RULES WARN CAN RETURN SILENT FALSE ZEROS UNDER `-E`. Probed 2026-09-06
against this exact pattern and a three-line specimen, using `/usr/bin/grep`, which
is GNU grep 3.12 and is what a SCRIPT resolves `grep` to on this host: it matched
`keyctl add` at line start and ` keyctl pipe` mid-line and rejected
`xkeyctl show`. So the twin is not affected. The port reproduces the
leading-character capture (the matched text includes the boundary character, which
`awk '{print $NF}'` then discards) so that a future divergence shows up as a
differing verb set rather than as a silently narrower scan.

MEASURE grep WITH `/usr/bin/grep`, NEVER AT AN INTERACTIVE PROMPT. A Claude Code
shell defines `grep` as a FUNCTION wrapping a bundled ugrep 7.8.4 with
`-G --ignore-files --hidden -I --exclude-dir=.git ...`; a script sees GNU grep
3.12. The two disagree on `\x27`, on binary-file reporting and on which files are
searched, and a probe run at the prompt is a statement about the wrapper rather
than about the gate. This cost two wrong port notes in this same wave.

THE EM DASHES IN THE TWIN'S MESSAGES ARE EMITTED AS `—` ESCAPES. The house
rule forbids an em dash in authored text; the twin's message bytes are not
authored here, they are REPRODUCED, and the differential compares finding text.
Writing the escape keeps this file free of the character while keeping the two
sides byte-identical.
"""

import pathlib
import re
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The two subjects, spelled exactly as the twin spells them, because the spelling lands in the finding text and in the log_step banner.
CONSUMER = "packages/cli/src/utils/secure-storage.ts"
PROBE = "scripts/drills/transfer.sh"

# Cleanup-only verbs, carried verbatim from the twin with its reasoning:
# "The consumer unlinks; the probe purges. Both remove the key and neither is on
# the success path the probe exists to predict, so they are interchangeable here. Anything else must be exercised."
EXEMPT_VERBS = ("unlink", "purge", "revoke")

# The em dash the twin's require_input lead carries. Named rather than embedded;
# see the port notes.
EM_DASH = "—"

# `grep -oE "execFileSync\('keyctl', \['[a-z]+"` then `grep -oE "'[a-z]+$"`. TWO STAGES, NOT ONE, because that is what the twin does and the intermediate string is what the second pattern anchors against. Collapsing them into one capture group would give the same answer today and a different one the moment the consumer's call shape grows a second quoted argument before the verb.
CONSUMER_CALL = re.compile(r"execFileSync\('keyctl', \['[a-z]+")
TRAILING_VERB = re.compile(r"'[a-z]+$")

# `grep -oE '(^|[^-[:alnum:]_])keyctl [a-z]+'`. The leading alternation is the word boundary: it rejects `xkeyctl show` and `re-keyctl add` while admitting a line that STARTS with the command. POSIX [[:alnum:]] is spelled out rather than abbreviated to `\w`, which in Python also admits `_` and every unicode letter.
PROBE_CALL = re.compile(r"(?:^|[^-a-zA-Z0-9_])keyctl [a-z]+")

# `sed 's/[[:space:]]*#.*$//'`, first match only, per line.
COMMENT_STRIP = re.compile(r"[ \t\v\f\r]*#.*$")


def consumer_verbs(text: str) -> list[str]:
    """Every `keyctl` verb the consumer invokes, sorted and deduplicated.

    Returns a LIST rather than a set so a caller can see the order the twin's
    `sort -u` produces, which is the order the banner line prints.
    """
    verbs: set[str] = set()
    for call in CONSUMER_CALL.findall(text):
        tail = TRAILING_VERB.search(call)
        if tail is not None:
            verbs.add(tail.group(0).replace("'", ""))
    return sorted(verbs)


def probe_verbs(text: str) -> list[str]:
    """Every `keyctl` verb the probe invokes, comments stripped first.

    The strip is the gate: see the module docstring for the version that counted
    a `keyctl pipe` living inside the preflight's own comment and certified a
    probe whose read-back had been deleted.
    """
    verbs: set[str] = set()
    for line in text.split("\n"):
        stripped = COMMENT_STRIP.sub("", line, count=1)
        for hit in PROBE_CALL.findall(stripped):
            # `awk '{print $NF}'`: the last whitespace-separated field. The match
            # may carry a leading boundary character, which this discards exactly as awk does.
            fields = hit.split()
            if fields:
                verbs.add(fields[-1])
    return sorted(verbs)


def missing_verbs(consumer: list[str], probe: list[str], exempt=EXEMPT_VERBS) -> list[str]:
    """Consumer verbs the probe never exercises, minus the exemptions.

    ORDER IS THE CONSUMER'S ORDER, not sorted separately, because the twin walks
    `$consumer_verbs` (already sorted) and appends, so the finding line reads in
    that order and the differential compares the whole line.
    """
    return [verb for verb in consumer if verb not in exempt and verb not in probe]


def _read(path: pathlib.Path) -> str:
    """File text, decoding replacement rather than raising.

    grep does not stop at a bad byte and neither does this; a source file with a
    stray latin-1 byte is a portability defect somewhere else, not a reason this
    gate cannot report.
    """
    return path.read_bytes().decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 on parity, 1 on a missing input, an empty extraction
    or a real gap.

    `--selftest` is intercepted BEFORE any real read, per the anti-vacuity rule:
    a control that runs after the scan cannot stop the scan's verdict being
    reported. The twin documents itself as taking no arguments ("Usage:
    check-probe-parity.sh") and ignores any it is given.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    consumer_path = root / CONSUMER
    probe_path = root / PROBE

    log.step("Checking capability-probe parity (%s vs %s)..." % (PROBE, CONSUMER))

    # `require_input -f`, with the twin's lead and its reason. The lead is the
    # CALLER'S because it is contract: common.sh:186 substitutes `{}` with the
    # offending path and adds no wording of its own.
    for path, shown in ((consumer_path, CONSUMER), (probe_path, PROBE)):
        if not path.is_file():
            log.error(
                "%s not found %s this gate has nothing to check, which is a failure,"
                % (shown, EM_DASH)
            )
            log.error("not a pass: parity cannot be asserted against a file that is gone.")
            return 1

    consumer = consumer_verbs(_read(consumer_path))
    probe = probe_verbs(_read(probe_path))

    # CONTROL: an empty side makes the comparison vacuous. This is the branch the
    # twin's missing `|| true` made unreachable until 96355d3b5; see the module
    # docstring.
    if not consumer:
        log.error("CONTROL FAILED: no keyctl verbs extracted from %s." % CONSUMER)
        log.error("Either the consumer stopped using keyctl (retire this gate) or the")
        log.error("extraction broke. Refusing to report parity against an empty set.")
        return 1
    if not probe:
        log.error("CONTROL FAILED: no keyctl verbs extracted from %s." % PROBE)
        log.error("The preflight appears to probe nothing, which is worse than the")
        log.error("partial probe this gate exists to catch.")
        return 1

    # `tr '\n' ' '` leaves a TRAILING SPACE on both banner lines. Reproduced, because the differential compares normalized text and a gate that quietly tidied its own output would be a difference nobody chose.
    log.info("consumer verbs: %s " % " ".join(consumer))
    log.info("probe verbs:    %s " % " ".join(probe))

    missing = missing_verbs(consumer, probe)
    if missing:
        log.error("The keyring preflight does NOT exercise: %s" % " ".join(missing))
        log.error("")
        log.error("%s calls those, so an environment that permits the probed" % CONSUMER)
        log.error("operations but denies one of these makes the preflight report")
        log.error("'usable' and the drill fail anyway %s the 2026-08-05 defect, where a" % EM_DASH)
        log.error("runner allowed 'keyctl add' and denied 'keyctl pipe'.")
        log.error("")
        log.error("Fix the PROBE to exercise the full round trip. Do not add the verb to")
        log.error("EXEMPT_VERBS unless it genuinely cannot affect whether the consumer")
        log.error("succeeds %s cleanup-only operations are the sole intended exemption." % EM_DASH)
        return 1

    log.info("Probe parity holds: every consumer keyctl operation is exercised by the preflight")
    return 0


def selftest() -> int:
    """Both directions for every rule, over synthetic text.

    A GATE WITH ONLY POSITIVE CONTROLS WILL HAPPILY FLAG THE WHOLE TREE, so each
    extractor is exercised on something it must catch AND on something it must
    ignore. The floor is not a hand-typed count of assertions: it is derived from
    the corpus below, so adding a case raises it automatically and deleting one
    that stopped running turns the suite red rather than quietly shortening it.
    """
    # The corpus, as (label, text, expected) triples. The FLOOR is len(corpus) plus the fixed structural checks, computed at the end.
    consumer_cases = [
        ("one call", "execFileSync('keyctl', ['add', k])", ["add"]),
        (
            "several calls, deduplicated and sorted",
            (
                "execFileSync('keyctl', ['pipe', a])\nexecFileSync('keyctl', ['add', b])\n"
                "execFileSync('keyctl', ['add', c])"
            ),
            ["add", "pipe"],
        ),
        # NEGATIVE: a different binary must not contribute a verb. Without this the extractor could be `\['[a-z]+` and still pass every positive case.
        ("a different command is ignored", "execFileSync('gpg', ['add', k])", []),
        ("prose mentioning keyctl add is ignored", "// we call keyctl add here", []),
        ("nothing at all", "", []),
    ]
    probe_cases = [
        ("bare invocation at line start", "keyctl add @u", ["add"]),
        ("indented invocation", "    keyctl pipe %s\n", ["pipe"]),
        (
            "several, deduplicated and sorted",
            "keyctl purge user\nkeyctl add @u\nkeyctl add @s\n",
            ["add", "purge"],
        ),
        # THE FOUNDING NEGATIVE. A verb named only in a comment must NOT count: this is the exact defect the twin's planted-defect proof found.
        ("a verb only in a comment does not count", "    # keyctl pipe reads it back", []),
        ("a trailing comment does not hide the code before it", "keyctl add  # then pipe", ["add"]),
        # NEGATIVE: the leading boundary class must reject a longer identifier.
        ("xkeyctl is not keyctl", "xkeyctl show @u", []),
        ("re-keyctl is not keyctl", "re-keyctl add @u", []),
        ("nothing at all", "", []),
    ]
    missing_cases = [
        ("a gap is reported", ["add", "pipe"], ["add"], ["pipe"]),
        ("full coverage reports nothing", ["add", "pipe"], ["add", "pipe"], []),
        # BOTH DIRECTIONS ON THE EXEMPTION: it must forgive its three verbs and must NOT forgive anything else.
        ("an exempt verb is forgiven", ["unlink", "purge", "revoke"], [], []),
        ("a non-exempt verb is not forgiven", ["search"], [], ["search"]),
        (
            "order follows the consumer list",
            ["add", "pipe", "search"],
            [],
            ["add", "pipe", "search"],
        ),
    ]

    floor = len(consumer_cases) + len(probe_cases) + len(missing_cases)
    ctl = Controls("probe-parity", floor=floor)

    for label, text, want in consumer_cases:
        ctl.check("consumer: %s" % label, consumer_verbs(text), want)
    for label, text, want in probe_cases:
        ctl.check("probe: %s" % label, probe_verbs(text), want)
    for label, consumer, probe, want in missing_cases:
        ctl.check("missing: %s" % label, missing_verbs(consumer, probe), want)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
