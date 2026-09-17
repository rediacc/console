"""The release signing key must reach nfpm as CANONICAL armor.

Ported from `.ci/scripts/quality/check-release-key-canonical.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live until a
differential ledger row exists over K distinct trees. Its gate header registers
it as step "Release key canonical", needs none, lane quality-security.

WHY THIS EXISTS, carried whole from the twin, dated incident included:

    On 2026-09-05 a release build failed at `Stage Artifacts / Build Linux
    packages` with

        signing error: armored detach sign: decoding armored PGP keyring:
        openpgp: invalid data: armor invalid

    one line AFTER "Signing key matches the published public key". gpg had read
    the very bytes nfpm then rejected. The cause: the key is stored as two
    Bitwarden items whose halves were joined without a newline, welding two
    base64 lines into one over-long line. gpg tolerates that; Go's armor decoder
    does not.

WHAT THIS GATE CAN AND CANNOT DO, said plainly so its green is not read as more
than it is. It CANNOT check the real RELEASE_GPG_PRIVATE_KEY: that value is a
secret, quality jobs do not have it and must not, and a gate that needs a
credential to run is a gate that gets skipped. So it checks the thing that IS
checkable offline -- that the canonicaliser the build depends on still repairs the
defect shape -- using a key generated here and thrown away. If the stored value is
welded again tomorrow, the BUILD repairs it and this gate proves the repair still
works.

THE PROXY FOR "Go would reject it", and why it is honest. This runs without Go, so
it cannot invoke openpgp.ReadArmoredKeyRing. It asserts the structural signature
instead: RFC 4880 armor wraps base64 at 64 columns, the weld produces one line far
longer, and that over-long line is precisely what differs between the block gpg
accepts and the block Go rejects. The causal link was measured
against x/crypto v0.56.0 on 2026-09-05 -- welded REJECT, newline-joined ACCEPT.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TALLY IS TRANSLITERATED, NOT REPLACED BY `rediacc_ci.controls.Controls`. The
twin sources `.ci/scripts/lib/gate-controls.sh`, whose header records why that
file exists: "Extracted 2026-09-06 after check:ci-shape-duplication caught the
same ~5 lines at three copies (check-release-key-canonical,
check-release-signing-coverage, check-staging-tag-guard) and was right to". The
twin's own line for it is "One copy of the tally, shared. check:ci-shape-duplication
caught this body at three copies and the extraction converted only ONE of them,
which took the count to two and made the gate quiet at its own threshold of three.
Doing a third of the work is how a gate gets silenced instead of satisfied."

`Controls` prints `FAIL  <label>: got <got!r>, wanted <want!r>`; gate-controls.sh
prints `  FAIL  <label> (got '<got>' want '<want>')`. Both are findings to
`scripts/lib/shadow-gate.ts` and their TEXT differs, so a port using `Controls`
for the gate's own output would disagree with the twin on every failing control
and the differential would read MISMATCH_FINDINGS for a port behaving correctly.
`Controls` is used only for `--selftest`, where nothing compares text. This is the
SECOND port to make that call (`rediacc_ci.quality.staging_tag_guard` was the
first) and the duplication is real: the right home is a shared
`rediacc_ci.gate_controls` byte-compatible with the bash file. It is not created
here because this change owns three files per subject and none of them is a new
shared module, and because `.ci/rediacc_ci/core/` is off limits to this writer.

THE FLOOR MESSAGE IS A REFUSAL TO THE COMPARATOR, and that shapes what a
differential can be recorded over. `gate_finish`'s short-battery line contains
"the battery is not being executed as written", which `scripts/lib/shadow-gate.ts`
matches as a REFUSAL and which suspends the comparison entirely. So do the three
early exits: "nothing here was verified" (no gpg) and "so NOTHING was verified"
(key generation failed). Those states are real and are ported faithfully, but no
ledger row can be recorded over them -- a refusal is not a verdict, and pretending
otherwise is exactly the vacuity the comparator refuses.

gpg IS DRIVEN, NEVER REIMPLEMENTED. Every control here is a claim about what gpg
and the canonicaliser do to real bytes; a Python OpenPGP library would answer a
different question and would make the gate certify itself. `python-gnupg` is not
imported and no key parsing happens in this module.

THE `awk` WELDER IS TRANSLITERATED WITH ITS `getline`, and the `NR>3` is the part
worth stating: `gpg --armor --export-secret-keys` emits the BEGIN line, a blank
line, then base64, so the first weldable pair is lines 4 and 5. A rewrite that
welded "the first two body lines" would produce a different fixture and a
different control. The `/^-----/` rule fires only on a line the main loop reads,
NOT on a line pulled in by `getline`, which is why the footer can in principle be
welded onto the last body line and why `done` is set on the first weld.

TWO `grep -c` CONTROLS COUNT LINES IN build-linux-pkg.sh, and the twin's comment
on the first is the reason it is a pipeline rather than one grep: "Count CODE, not
prose: the same idiom appears in the comment that explains it, and a naive grep -c
reads 2 and fails on a correct file."

THE TWO ARE ASYMMETRIC WHEN THE FILE IS ABSENT, and reproducing that asymmetry is
the reason they are two functions rather than one. Measured on this host (ugrep
7.8.4, 2026-09-06):

    grep -v '^\\s*#' missing.sh 2>/dev/null | grep -c '...'   ->  prints "0"
    grep -c '...' missing.sh                                  ->  prints NOTHING

The pipeline's second grep reads an EMPTY STDIN and dutifully counts zero; the
direct grep never opens a stream and writes only a warning to stderr, so the
twin's `$(...)` captures the empty string. The gate therefore reports
`(got '0' want '1')` for the guard control and `(got '' want '1')` for the call
control over the SAME missing file, and both of those strings are compared
findings. A port that returned 0 for both would disagree on one line of a real
recorded row. `guard_count_field` returns a number always; `call_count_field`
returns "" for an absent file.

ONE RESIDUAL DIVERGENCE, named rather than hidden: grep's own
`ugrep: warning: <path>: No such file or directory` lands on the twin's stderr and
this port writes nothing there. `scripts/lib/shadow-gate.ts` classifies that line
as CHATTER (it carries no severity marker and its `.sh:` is not followed by a line
number), and chatter is recorded but never compared, so it cannot change a
verdict. It is still a difference in the bytes a human diffs.

`grep -c '|| canon_rc=\\$?'` IS A BRE WITH AN ESCAPED DOLLAR, i.e. the literal
text `|| canon_rc=$?`. Matched with `in` rather than a compiled pattern, because
turning a fixed string into a regex is how `$?` would quietly become an anchor
plus a quantifier the day someone reformatted the line.

`grep -v '^\\s*#'` DROPS COMMENT LINES ONLY. A trailing comment on a line of code
is not removed, so `foo || canon_rc=$?  # note` still counts. That is the twin's
behaviour and the control's value depends on it staying that way.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci.controls import Controls

# The two files under test, relative to ROOT.
CANON_REL = (".ci", "scripts", "build", "canonicalise-gpg-key.sh")
BUILD_PKG_REL = (".ci", "scripts", "build", "build-linux-pkg.sh")

# The twin's own seam, kept by name so one harness drives either implementation.
ROOT_ENV = "RELEASE_KEY_ROOT"

# The throwaway key. Its passphrase is a literal in the twin and is a literal here: it protects nothing, and a generated one would make the "wrong passphrase" control depend on a value the reader cannot see. THE SUPPRESSION ON THE NEXT LINE IS NOT A SILENCING. bandit is right that this
# is a hardcoded credential; it protects a key generated and thrown away inside a
# temp GNUPGHOME for the length of one process, and it is the twin's literal. Replacing it with a random value would cost the "wrong passphrase" control its readability and would change nothing about what is protected.
PASSPHRASE = "gate-throwaway-passphrase"  # noqa: S105
KEY_UID = "Release Key Gate <gate@example.invalid>"

# RFC 4880 wraps armor base64 at 64 columns. The weld produces one line far longer, and that over-long line is the structural signature Go rejects.
ARMOR_COLUMNS = 64

# `gate_finish 8` in the twin. A battery that did not run is not a green one.
MIN_CONTROLS = 8

# `grep -c '|| canon_rc=\$?'` -- a BRE whose `\$` is a literal dollar, so this is
# a FIXED string. See the port notes.
GUARD_LITERAL = "|| canon_rc=$?"

# `grep -c 'canonicalise-gpg-key.sh'` -- likewise fixed.
CANON_LITERAL = "canonicalise-gpg-key.sh"

# `grep -v '^\s*#'`, with the POSIX class written out. Python's `\s` would also match U+00A0, which would drop a line grep keeps.
COMMENT_LINE_RE = re.compile(r"^[ \t\v\f\r]*#")

# `grep -c 'BEGIN PGP PRIVATE KEY BLOCK'`.
PROTECTED_LITERAL = "BEGIN PGP PRIVATE KEY BLOCK"


class _GateTally:
    """`.ci/scripts/lib/gate-controls.sh`, transliterated byte for byte.

    Not `rediacc_ci.controls.Controls`: see the port notes. These strings are the
    gate's OUTPUT CONTRACT and the shadow differential compares them.
    """

    def __init__(self) -> None:
        self.fails = 0
        self.count = 0

    def check(self, label: str, got: str, want: str) -> None:
        """`gate_check`: stdout on pass, stderr on failure, both indented two."""
        self.count += 1
        if got == want:
            print("  ok    %s" % label)
        else:
            self.fails += 1
            print("  FAIL  %s (got '%s' want '%s')" % (label, got, want), file=sys.stderr)

    def finish(self, minimum: int, subject: str) -> bool:
        """`gate_finish`: the floor, then the verdict. True when green."""
        if self.count < minimum:
            print(
                "FAIL  only %d control(s) ran; the battery is not being executed as written"
                % self.count,
                file=sys.stderr,
            )
            self.fails += 1
        if self.fails:
            print(
                "✗ %s: %d of %d control(s) failed" % (subject, self.fails, self.count),
                file=sys.stderr,
            )
            return False
        print("✓ %s: %d control(s) passed" % (subject, self.count))
        return True


def default_root() -> str:
    """`${RELEASE_KEY_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}`.

    Reproduced rather than delegated to `rediacc_ci.paths.repo_root()`, which
    answers with the package's own location outside a work tree where this
    answers with the current directory. The two disagree exactly where a harness
    would notice, so the twin's rung order is kept.
    """
    override = os.environ.get(ROOT_ENV)
    if override:
        return override
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    out = (completed.stdout or "").strip()
    return out if completed.returncode == 0 and out else "."


def longest_body_line(text: str) -> int:
    """`grep -v -- '-----' | awk '{ ... } END { print m+0 }'`.

    The longest line of the armor BODY, header and footer excluded. `grep -v`
    drops every line CONTAINING five dashes anywhere, not only the delimiters,
    and an empty result is 0 rather than blank, which is what `m+0` is for.
    """
    lengths = [len(line) for line in text.split("\n") if "-----" not in line]
    return max(lengths) if lengths else 0


def weld(text: str) -> str:
    """The twin's awk welder: join the first weldable body pair, losing one break.

    THE DEFECT SHAPE, exactly as `part1 + part2` produces it when part1 carries no
    trailing newline. Content identical, one line break gone. `NR>3` and the
    `getline` are transliterated; see the port notes for why the line number
    matters.
    """
    lines = text.split("\n")
    # awk sees no final empty record for a trailing newline; `split` invents one.
    if lines and lines[-1] == "":
        lines = lines[:-1]
    out: list[str] = []
    done = False
    index = 0
    while index < len(lines):
        line = lines[index]
        number = index + 1  # awk's NR
        if line.startswith("-----"):
            out.append(line)
            index += 1
            continue
        if not done and number > 3:
            if index + 1 < len(lines):
                out.append(line + lines[index + 1])
                done = True
                index += 2
                continue
            out.append(line)
            index += 1
            continue
        out.append(line)
        index += 1
    return "".join(part + "\n" for part in out)


def literal_count(text: str, needle: str) -> int:
    """`grep -c '<needle>'` -- MATCHING LINES, not occurrences.

    Two hits on one line count once. That is grep's contract and the difference
    is invisible until a line grows a second mention.
    """
    return sum(1 for line in text.split("\n") if needle in line)


def guard_count(text: str) -> int:
    """`grep -v '^\\s*#' | grep -c '|| canon_rc=$?'` -- COUNT CODE, NOT PROSE.

    The twin's comment: "the same idiom appears in the comment that explains it,
    and a naive grep -c reads 2 and fails on a correct file."
    """
    return sum(
        1 for line in text.split("\n") if not COMMENT_LINE_RE.match(line) and GUARD_LITERAL in line
    )


def guard_count_field(path: pathlib.Path) -> str:
    """The guard control's `got`, as the twin's PIPELINE produces it.

    ALWAYS A NUMBER, missing file included: the second grep reads an empty stdin
    and counts zero. See the port notes for the measurement.
    """
    return str(guard_count(_read(path)))


def call_count_field(path: pathlib.Path) -> str:
    """The call control's `got`, as the twin's DIRECT grep produces it.

    EMPTY for a missing file, because grep never opens a stream and writes only a
    warning to stderr. This is the half of the asymmetry a port loses by being
    tidy; see the port notes.
    """
    if not path.is_file():
        return ""
    return str(literal_count(_read(path), CANON_LITERAL))


def _read(path: pathlib.Path) -> str:
    """File text, or "" when it is not there. See the port notes for the divergence."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _gpg(args: list[str], home: str, *, capture: bool = True) -> subprocess.CompletedProcess:
    """One gpg invocation with GNUPGHOME pinned, stderr discarded as the twin does."""
    env = dict(os.environ)
    env["GNUPGHOME"] = home
    return subprocess.run(
        ["gpg", *args],
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        env=env,
        check=False,
    )


def _first_fpr(colons: str) -> str:
    """`awk -F: '$1=="fpr"{print $10; exit}'` -- the first fingerprint, or ""."""
    for line in colons.split("\n"):
        fields = line.split(":")
        if fields and fields[0] == "fpr" and len(fields) >= 10:
            return fields[9]
    return ""


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when every control holds, 1 otherwise.

    `--selftest` is intercepted BEFORE any real scan, which is the addition the
    twin does not have. The twin takes no arguments, so no caller passes it.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = pathlib.Path(default_root())
    canon = root.joinpath(*CANON_REL)
    build_pkg = root.joinpath(*BUILD_PKG_REL)

    if not (canon.is_file() and os.access(canon, os.X_OK)):
        print(
            "✗ %s is missing or not executable -- the build depends on it" % canon, file=sys.stderr
        )
        return 1
    if shutil.which("gpg") is None:
        # A MISSING TOOL IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE, and this wording is also the comparator's refusal vocabulary: "nothing here was verified" suspends a differential rather than scoring it.
        print(
            "✗ gpg is not installed, so nothing here was verified (CI installs it; locally: "
            "sudo apt-get install -y gnupg)",
            file=sys.stderr,
        )
        return 1

    tally = _GateTally()

    with tempfile.TemporaryDirectory() as tmpname:
        tmp = pathlib.Path(tmpname)
        home = tmp / "gnupg"
        home.mkdir()
        home.chmod(0o700)
        gnupghome = str(home)

        _gpg(
            [
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                PASSPHRASE,
                "--quick-generate-key",
                KEY_UID,
                "rsa2048",
                "sign",
                "never",
            ],
            gnupghome,
            capture=False,
        )
        fpr = _first_fpr(_gpg(["--list-secret-keys", "--with-colons"], gnupghome).stdout or "")
        if not fpr:
            print("✗ could not generate a throwaway key, so NOTHING was verified", file=sys.stderr)
            return 1

        good = tmp / "good.asc"
        good.write_text(
            _gpg(
                [
                    "--batch",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase",
                    PASSPHRASE,
                    "--armor",
                    "--export-secret-keys",
                    fpr,
                ],
                gnupghome,
            ).stdout
            or "",
            encoding="utf-8",
        )

        tally.check(
            "a canonical key wraps at 64 columns",
            "1" if longest_body_line(_read(good)) <= ARMOR_COLUMNS else "0",
            "1",
        )

        welded = tmp / "welded.asc"
        welded.write_text(weld(_read(good)), encoding="utf-8")

        tally.check(
            "CONTROL: the welded key really is malformed (an over-long body line)",
            "1" if longest_body_line(_read(welded)) > ARMOR_COLUMNS else "0",
            "1",
        )
        # The precondition the whole repair rests on, and the reason the build's own fingerprint check could not catch this: gpg reads the welded block happily.
        welded_colons = _gpg(["--show-keys", "--with-colons", str(welded)], gnupghome).stdout or ""
        tally.check(
            "CONTROL: gpg still reads the welded key, which is why it slipped through",
            "1" if _first_fpr(welded_colons) else "",
            "1",
        )

        repaired = tmp / "repaired.asc"
        shutil.copyfile(welded, repaired)
        # 0 = was already canonical, 10 = REPAIRED. Both are success here; only 1
        # is failure. Treating any non-zero as failure is what this gate did before the repair signal existed, and it turned a working repair into "canonicaliser-failed".
        canon_rc = _run_canon(canon, repaired, PASSPHRASE)
        tally.check("a welded key reports REPAIRED, not 'already fine'", str(canon_rc), "10")

        # CONTROL: an already-canonical key must NOT claim a repair, or the signal is noise and the next person mutes it.
        good_probe = tmp / "good-probe.asc"
        shutil.copyfile(good, good_probe)
        good_rc = _run_canon(canon, good_probe, PASSPHRASE)
        tally.check("CONTROL: an already-canonical key reports 0, not 10", str(good_rc), "0")

        # The caller runs under `set -e`, so a BARE call to a script exiting 10 aborts the whole build -- which is exactly the production case the signal exists for.
        tally.check(
            "build-linux-pkg.sh guards that non-zero exit", guard_count_field(build_pkg), "1"
        )

        if canon_rc in (0, 10):
            tally.check(
                "the canonicaliser repairs a welded key",
                "1" if longest_body_line(_read(repaired)) <= ARMOR_COLUMNS else "0",
                "1",
            )
            repaired_colons = (
                _gpg(["--show-keys", "--with-colons", str(repaired)], gnupghome).stdout or ""
            )
            tally.check(
                "...and the repaired key is still the SAME key", _first_fpr(repaired_colons), fpr
            )
            # If the re-export dropped the passphrase, nfpm's NFPM_*_PASSPHRASE would be wrong and signing would fail with a confusing error somewhere else.
            tally.check(
                "...and it is still passphrase-protected",
                str(literal_count(_read(repaired), PROTECTED_LITERAL)),
                "1",
            )
            # IMPORT IS NOT THE TEST. gpg imports a protected secret key without the passphrase -- it stores it still encrypted -- so an import that succeeds proves nothing about protection. Signing is what needs the passphrase, and it is what nfpm does, so that is what is asserted.
            tally.check(
                "...and it can still SIGN with the right passphrase",
                _sign_with(tmp, repaired, PASSPHRASE, "right"),
                "signed",
            )
            # CONTROL: without this, a re-export that stripped the passphrase would pass the assertion above while having silently removed the protection.
            tally.check(
                "CONTROL: and it REFUSES to sign with the wrong one",
                _sign_with(tmp, repaired, "wrong-pass", "wrong"),
                "refused",
            )
        else:
            tally.check("the canonicaliser repairs a welded key", "canonicaliser-failed", "1")

        # The build must actually CALL it, or this gate proves a function nothing uses.
        tally.check(
            "build-linux-pkg.sh calls the canonicaliser",
            call_count_field(build_pkg),
            "1",
        )

        if not tally.finish(MIN_CONTROLS, "release key canonicalisation"):
            return 1
        print("  (throwaway key; the real one is a secret and is deliberately out of scope)")
        return 0


def _run_canon(canon: pathlib.Path, target: pathlib.Path, passphrase: str) -> int:
    """`"$CANON" <file> <pass> >/dev/null 2>&1 || canon_rc=$?`. Returns the code."""
    completed = subprocess.run(
        [str(canon), str(target), passphrase],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode


def _sign_with(tmp: pathlib.Path, key: pathlib.Path, passphrase: str, tag: str) -> str:
    """`_sign_with` -- import into a fresh GNUPGHOME, then try to detach-sign.

    Returns "signed" or "refused", which is what the twin echoes.
    """
    home = tmp / ("sign-%s" % tag)
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)
    gnupghome = str(home)
    _gpg(
        [
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            passphrase,
            "--import",
            str(key),
        ],
        gnupghome,
        capture=False,
    )
    msg = home / "msg"
    msg.write_text("hi\n", encoding="utf-8")
    signed = _gpg(
        [
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            passphrase,
            "--armor",
            "--detach-sign",
            "--output",
            str(home / "sig"),
            str(msg),
        ],
        gnupghome,
        capture=False,
    )
    return "signed" if signed.returncode == 0 else "refused"


# A four-line armor block in the shape gpg emits: BEGIN, blank, body, body, END. The base every plant below mutates, and asserted CANONICAL first: without that, each plant would "fire" against a fixture that was already malformed.
_ARMOR = (
    "-----BEGIN PGP PRIVATE KEY BLOCK-----\n"
    "\n"
    "AAAA\n"
    "BBBB\n"
    "CCCC\n"
    "-----END PGP PRIVATE KEY BLOCK-----\n"
)


def selftest() -> int:
    """Plant each violation, prove it fires; remove it, prove it does not.

    THE PURE HALVES ONLY. Generating a throwaway key here would re-run the gate
    and prove that gpg agrees with itself; what is worth pinning is the welder,
    the line-length measure and the two counters, each in BOTH directions.
    """
    ctl = Controls("release-key-canonical", floor=18, verbose=True)

    # -- longest_body_line ---------------------------------------------------
    ctl.check("CONTROL: a short body measures its longest line", longest_body_line(_ARMOR), 4)
    ctl.check(
        "CONTROL: the delimiters are EXCLUDED, long as they are",
        longest_body_line("-----BEGIN A VERY LONG DELIMITER LINE INDEED-----\nAB\n"),
        2,
    )
    ctl.check("VACUITY: a body of nothing measures 0, not blank", longest_body_line(""), 0)
    ctl.check(
        "VACUITY: delimiters only also measure 0",
        longest_body_line("-----BEGIN X-----\n-----END X-----\n"),
        0,
    )
    ctl.check(
        "PLANT: a 65-column line is over the RFC 4880 wrap",
        longest_body_line("x" * 65 + "\n") > ARMOR_COLUMNS,
        True,
    )
    ctl.check(
        "MIRROR: exactly 64 is NOT over",
        longest_body_line("x" * 64 + "\n") > ARMOR_COLUMNS,
        False,
    )

    # -- weld ----------------------------------------------------------------
    welded = weld(_ARMOR)
    ctl.check(
        "CONTROL: the welder joins the first weldable pair (NR>3)",
        welded,
        "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nAAAA\nBBBBCCCC\n"
        "-----END PGP PRIVATE KEY BLOCK-----\n",
    )
    ctl.check("...so the body grows an over-long line", longest_body_line(welded), 8)
    ctl.check(
        "...and the delimiters survive untouched",
        welded.splitlines()[0],
        "-----BEGIN PGP PRIVATE KEY BLOCK-----",
    )
    ctl.check(
        "...and the CONTENT is identical, one line break gone",
        welded.replace("\n", ""),
        _ARMOR.replace("\n", ""),
    )
    ctl.check("VACUITY: welding nothing yields nothing", weld(""), "")
    # ONLY THE FIRST PAIR. `done=1` is what stops it, and a welder that joined
    # every pair would produce a fixture the canonicaliser might repair differently.
    ctl.check(
        "MIRROR: only ONE weld happens, however many body lines there are",
        weld("-----B-----\n\nA\nB\nC\nD\nE\n-----E-----\n"),
        "-----B-----\n\nA\nBC\nD\nE\n-----E-----\n",
    )

    # -- guard_count: COUNT CODE, NOT PROSE ----------------------------------
    ctl.check(
        "CONTROL: one real guard counts once",
        guard_count('canon.sh "$K" || canon_rc=$?\n'),
        1,
    )
    ctl.check(
        "PLANT: the same idiom in a COMMENT is not counted",
        guard_count("# `|| canon_rc=$?` rather than a bare call\ncanon.sh || canon_rc=$?\n"),
        1,
    )
    ctl.check(
        "MIRROR: an INDENTED comment is a comment too",
        guard_count("    # || canon_rc=$?\n"),
        0,
    )
    ctl.check(
        "MIRROR: a TRAILING comment is not a comment line, so its code still counts",
        guard_count("canon.sh || canon_rc=$?  # note\n"),
        1,
    )
    ctl.check("VACUITY: an absent build script counts 0, not blank", guard_count(""), 0)

    # -- literal_count: MATCHING LINES, not occurrences -----------------------
    ctl.check(
        "CONTROL: one mention on one line",
        literal_count("a canonicalise-gpg-key.sh b\n", CANON_LITERAL),
        1,
    )
    ctl.check(
        "MIRROR: TWO mentions on ONE line still count one, as grep -c does",
        literal_count("canonicalise-gpg-key.sh canonicalise-gpg-key.sh\n", CANON_LITERAL),
        1,
    )
    ctl.check(
        "CONTROL: two mentions on two lines count two",
        literal_count("canonicalise-gpg-key.sh\ncanonicalise-gpg-key.sh\n", CANON_LITERAL),
        2,
    )
    ctl.check("VACUITY: no mention counts 0", literal_count("nothing here\n", CANON_LITERAL), 0)

    # -- THE ASYMMETRY OVER A MISSING FILE, both halves ----------------------
    absent = pathlib.Path("/nonexistent/definitely-not-here-build-linux-pkg.sh")
    ctl.check("ABSENT: the PIPELINE control still reports a number", guard_count_field(absent), "0")
    ctl.check("ABSENT: the DIRECT control reports the empty string", call_count_field(absent), "")

    # -- the colon parser ----------------------------------------------------
    ctl.check(
        "CONTROL: the FIRST fpr record wins",
        _first_fpr("sec:u:2048:1:X::::::::::\nfpr:::::::::AAAA1111:\nfpr:::::::::BBBB2222:\n"),
        "AAAA1111",
    )
    ctl.check("VACUITY: no fpr record yields the empty string", _first_fpr("sec:u:2048::\n"), "")
    ctl.check("VACUITY: empty colon output yields the empty string", _first_fpr(""), "")

    # -- the tally's own contract -------------------------------------------- THE TWO LINES THIS BLOCK PRINTS ARE THE SUBJECT, NOT A FAILURE. The tally is what is under test here, so its own ` FAIL ...` and `✗ selftest: ...`
    # land on stderr on purpose; a reader scanning for red would otherwise take
    # them for the selftest failing.
    tally = _GateTally()
    tally.check("EXPECTED-OK: the tally under test, passing", "1", "1")
    tally.check("EXPECTED-FAIL: the tally under test, failing", "0", "1")
    ctl.check("the tally counts both", (tally.count, tally.fails), (2, 1))
    ctl.check("...and a short battery is not green", tally.finish(MIN_CONTROLS, "selftest"), False)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
