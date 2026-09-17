"""`.editorconfig` compliance across every tracked text file.

Ported from `.ci/scripts/quality/check-editorconfig.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHAT THE TWIN ENFORCES, carried over from its own header verbatim because the list IS the gate:

    Checks:
      1. All tracked text files end with a final newline
      2. No UTF-8 BOM in tracked text files
      3. No CRLF line endings in tracked text files
      4. No embedded NUL byte in a file whose extension says it must be text

    Respects .gitignore and only checks git-tracked files.
    Skips binary files. Includes submodule files.

THE TEXT-EXTENSION LIST AND WHY CHECK 4 CANNOT FALSE-POSITIVE, in the twin's own words: "Extensions that must always be text; a NUL byte inside one is corruption, not content -- e.g. a literal NUL typed in a shell/TS source file where a `\\0` escape sequence was meant (check-ci-parity.ts:163, found 2026-08-01). A real binary asset (png, woff, so, ...) never matches this list, which
is what makes check 4 unable to false-positive on legitimate binaries: only a file `file --mime-encoding` calls binary AND whose extension says it must be text gets flagged, and normal binary assets never have such extensions."

THE TWO CONTROLS THE TWIN RUNS BEFORE IT SCANS ANYTHING, both carried:

  1. "the NUL-byte check must be able to FIRE before its green means anything --
     a check that skips every binary-flagged file (as check 4's own branch does,
     on purpose, for real binary assets) is exactly the shape of gate that can
     silently stop firing if the corruption detection regresses."

  2. "the binary classifier must key on the ENCODING `file` reports, not on the
     path. The previous implementation ran `file --mime-encoding "$f" | grep -q
     binary` over the WHOLE line, so any path containing the substring "binary"
     was treated as a binary asset and silently exempted from the final-newline,
     BOM and CRLF checks. Five tracked text files matched, including
     .ci/scripts/test/gates/test-watchdog-binary-exec-guard.sh (us-ascii). A gate
     whose coverage depends on filenames is exactly the kind that goes quiet."

THE BATCHING, and why it is not an optimisation to be "cleaned up": "The previous shape was a while-read loop that spawned `file`, `tail`, `head|od|grep` and `grep -P` PER FILE. Measured on this repo: 6,595 tracked files at ~87ms of
process spawns each = ~573s, i.e. the gate looked hung and could not finish
inside a 10-minute local run. Nothing was wrong with the checks; the cost was fork/exec." And: "`file` is still the ONLY binary oracle, called with the same flags, so its heuristics cannot drift -- it is just invoked in batches via xargs instead of once per path."

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWIN'S SCANNING PASS IS ALREADY PYTHON, and that is the happiest part of this port: `check-editorconfig.sh:112-168` is a heredoc'd `python3 -` program. Its four rules, its symlink comment and its `.hash` skip are carried here as code rather than re-derived, so the byte-exact half of this gate is the same program with the heredoc removed.

THE `--recurse-submodules` DEFECT IS PORTED, NOT FIXED. The twin enumerates with `git ls-files -z --recurse-submodules` while its manifest lane checks out WITHOUT submodules, so in that lane the flag adds nothing and the gate silently narrows to the superproject. That mismatch is a KNOWN, REPORTED defect; a port that quietly dropped the flag or quietly added a submodule check would
change the corpus and therefore the verdict, and the differential would have nothing to compare. It is carried as-is and named here so nobody has to rediscover it.

`require_cmd python3` IS SATISFIED BY CONSTRUCTION and has no counterpart below.
The twin needs the probe because it shells out to a `python3` that may not exist;
this module IS that python3. There is no branch to port, and inventing one would be a check that cannot fail.

A MISSING `file` STILL FAILS THROUGH THE NUL CONTROL, deliberately with the twin's own message rather than a clearer one. `file --mime-encoding X 2>/dev/null`
with no `file` on PATH produces nothing, the `grep -q binary` fails, and the twin
reports "NUL-byte control did not fire ... The detection logic is broken; do not trust this gate." That message is wrong about the cause and right about the verdict, and the port emits the same bytes because a better message here is a finding the differential would score as a mismatch. Reported as a twin defect instead of repaired.

`file` PADS THE FILENAME COLUMN when it is given more than one path, so a batch prints `a.sh: us-ascii` while a single file prints `a.sh: binary`. The awk classifier strips `: [^:]*$` and is immune to the padding, which is why batching changes performance and not results. Reproduced rather than assumed: `tests/test_quality_editorconfig.py` compares the port's classifier against the
real awk on padded and unpadded input.

THE ARRAYS ARE REPORTED IN CORPUS ORDER, not sorted. `git ls-files` already emits sorted paths, so the four lists come out sorted anyway; the port does not add a sort, because a sort would hide a future change in enumeration order that the twin would show.
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

# The extensions that must always be text. Carried byte for byte from the twin's `TEXT_EXTENSIONS_RE`, including the anchor, because the twin's own comment says the bash ERE and Python's syntax agree for this pattern and it compiles the string as-is on both sides.
TEXT_EXTENSIONS_RE = (
    r"\.(sh|ts|tsx|js|jsx|cjs|mjs|json|jsonc|yml|yaml|md|mdx|go|py|css|html|toml|txt)$"
)

# The one extension exempted from the three byte-exact checks. Hash sidecars are generated, single-line and deliberately newline-free.
HASH_SUFFIX = ".hash"

# How many paths go into one `file` invocation. xargs sizes its batches by the kernel's argument limit; the exact number is invisible in the result because the awk classifier strips `file`'s padding, so a round number is honest here rather than a reverse-engineered ARG_MAX.
BATCH = 2000


def classify_binary(lines: list[str]) -> list[str]:
    """The paths `file` called binary, from its output. The twin's awk, exactly.

        awk -F': ' '$NF ~ /binary/ { sub(/: [^:]*$/, "", $0); print }'

    TWO SEPARATE OPERATIONS THAT LOOK LIKE ONE. The TEST is on the last ": " separated field, and the STRIP is a regex substitution on the whole line. Collapsing them into "split on the last colon" would classify a path containing ": " differently, and it is the asymmetry that makes the control in the twin's header meaningful: a path holding the word "binary" is not a binary file,
    because the word has to be in the ENCODING field.
    """
    out: list[str] = []
    for line in lines:
        if line == "":
            continue
        # `-F': '` splits on the two-character string, so $NF is everything after the LAST ": ". A line with no ": " at all has $NF equal to the whole line, which is awk's behaviour and not a special case here.
        last_field = line.split(": ")[-1]
        if "binary" in last_field:
            out.append(re.sub(r": [^:]*$", "", line, count=1))
    return out


def mime_encodings(root: pathlib.Path, rel_paths: list[str]) -> list[str]:
    """`file --mime-encoding -- <paths>`, in batches. Raw output lines.

    stderr is DISCARDED, matching the twin's `2>/dev/null`, and a non-zero exit is ignored, matching its `|| true`. `file` reports an unreadable path on stderr and carries on, so a broken symlink does not take the gate down.
    """
    if not rel_paths:
        return []
    if shutil.which("file") is None:
        # The NUL control has already refused in this case; reaching here means a caller drove this function directly. An empty list is the same shape `xargs -r` produces with nothing to run.
        return []
    out: list[str] = []
    for start in range(0, len(rel_paths), BATCH):
        chunk = rel_paths[start : start + BATCH]
        proc = subprocess.run(
            ["file", "--mime-encoding", "--", *chunk],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        text = proc.stdout.decode("utf-8", "surrogateescape")
        out.extend(line for line in text.split("\n") if line != "")
    return out


def tracked_files(root: pathlib.Path) -> list[str]:
    """`git ls-files -z --recurse-submodules`, as a list of repo-relative paths.

    THE SUBMODULE FLAG IS THE REPORTED DEFECT. See the port notes: the manifest lane checks out without submodules, so this flag buys nothing there. It is carried because removing it would change the corpus, and a port that changes the corpus is not a port.
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--recurse-submodules"],
        cwd=str(root),
        capture_output=True,
        check=False,
    )
    raw = proc.stdout.decode("utf-8", "surrogateescape")
    return [p for p in raw.split("\0") if p]


def scan(root: pathlib.Path, paths_list: list[str], binary: set[str]) -> list[tuple[str, str]]:
    """The byte-exact pass. Returns (kind, path) for every finding, in order.

    This is `check-editorconfig.sh:113-167` with the heredoc removed. Its comments are the twin's, not new ones, and they are kept at the lines they describe.
    """
    text_ext = re.compile(TEXT_EXTENSIONS_RE)
    findings: list[tuple[str, str]] = []

    for path in paths_list:
        full = root / path
        # Symlinks are SKIPPED, deliberately and unlike the old `[[ -f ]]` test which followed them: checking a symlink's dereferenced target for a final newline or CRLF reports on a file that is checked in its own right anyway, and a symlink pointing outside the repo is not ours to police.
        if not full.is_file() or full.is_symlink():
            continue

        if path in binary:
            # Only corruption matters here: a file `file` calls binary whose extension says it must be text.
            if text_ext.search(path):
                try:
                    with open(full, "rb") as handle:
                        if b"\0" in handle.read():
                            findings.append(("NUL", path))
                except OSError:
                    pass
            continue

        if path.endswith(HASH_SUFFIX):
            continue

        try:
            with open(full, "rb") as handle:
                data = handle.read()
        except OSError:
            continue

        if not data:
            continue

        if not data.endswith(b"\n"):
            findings.append(("NEWLINE", path))
        if data.startswith(b"\xef\xbb\xbf"):
            findings.append(("BOM", path))
        if b"\r\n" in data:
            findings.append(("CRLF", path))

    return findings


# The four report headers, in the twin's order. A tuple of (kind, header) rather than four if-blocks, because the four blocks are identical apart from these strings and a divergence between them would be invisible.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("NEWLINE", "Files missing final newline"),
    ("BOM", "Files with UTF-8 BOM"),
    ("CRLF", "Files with CRLF line endings"),
    ("NUL", "Text source files with an embedded NUL byte"),
)

# The extra line the NUL section prints after its list. Written with an explicit escape because the twin passes it through `echo -e`, which turns the source's `\\\\0` into a literal backslash-zero on the wire; a Python `"\0"` here would emit an actual NUL byte into the gate's own output.
NUL_ADVICE = (
    "  A NUL byte makes git treat the file as binary: diffs go unreviewable and it "
    "silently stops being 'text' to every downstream tool. Replace it with the "
    "\\0 escape sequence (or the intended literal character)."
)


def nul_control(tmpdir: pathlib.Path) -> bool:
    """Plant a NUL in a synthetic `.ts` and require it to read as binary+NUL.

    Both halves are required, matching the twin's `&&`: `file` must call it binary AND the bytes must contain a NUL. Either alone would pass while the other detector was broken.
    """
    target = tmpdir / "control.ts"
    target.write_bytes(b"const x = 1;\x00\nconst y = 2;\n")
    if shutil.which("file") is None:
        return False
    proc = subprocess.run(
        ["file", "--mime-encoding", str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    # `grep -q "binary"` over the WHOLE line, which is the shape the second control exists to forbid in the scanner. It is correct HERE because the path is a fresh mktemp name that cannot contain the word.
    said_binary = b"binary" in proc.stdout
    has_nul = b"\0" in target.read_bytes()
    return said_binary and has_nul


def classifier_control() -> str | None:
    """Prove the classifier keys on the encoding, not the path. None means OK.

    Returns the twin's message for whichever half failed, so the caller prints one string and the two failure modes stay distinguishable in the output.
    """
    if classify_binary(["some-binary-name.sh: us-ascii"]):
        return (
            "Binary-classifier control failed: a us-ascii file whose PATH contains "
            "'binary' was classified as binary. Checks 1-3 would silently skip it."
        )
    if not classify_binary(["assets/logo.png: binary"]):
        return (
            "Binary-classifier control failed: a genuinely binary file was NOT "
            "classified as binary. The NUL-corruption path would never run."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 on a control failure or any violation.

    `--selftest` is intercepted BEFORE any real scan. The twin documents itself as taking no arguments ("Usage: check-editorconfig.sh") and ignores any it is given, so nothing observable changes for a real caller.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="surrogateescape")

    root = paths.repo_root()

    with tempfile.TemporaryDirectory() as tmp:
        if not nul_control(pathlib.Path(tmp)):
            log.error(
                "NUL-byte control did not fire: a synthetic .ts file with a planted NUL "
                "byte was not detected as binary+NUL. The detection logic is broken; do "
                "not trust this gate."
            )
            return 1
    log.info("Control: planted NUL byte in a synthetic .ts file fires as binary+NUL -- OK")

    problem = classifier_control()
    if problem is not None:
        log.error(problem)
        return 1
    log.info("Control: classifier keys on encoding, not path -- OK")

    log.step("Checking editorconfig compliance across repository (including submodules)...")

    tracked = tracked_files(root)
    binary = set(classify_binary(mime_encodings(root, tracked)))
    findings = scan(root, tracked, binary)

    buckets: dict[str, list[str]] = {kind: [] for kind, _header in SECTIONS}
    for kind, path in findings:
        buckets[kind].append(path)

    errors = 0
    for kind, header in SECTIONS:
        hits = buckets[kind]
        if not hits:
            continue
        log.error("%s (%d):" % (header, len(hits)))
        for path in hits:
            # STDOUT, deliberately. The twin uses a bare `echo " $f"` for the list while the header goes through log_error to stderr, and `scripts/lib/shadow-gate.ts` attaches these indented lines to the header above them as individual findings. Un-indenting or moving them would turn N findings into one.
            print("  %s" % path)
        if kind == "NUL":
            log.error(NUL_ADVICE)
        errors += len(hits)

    if errors > 0:
        print()
        log.error("Found %d editorconfig violation(s)" % errors)
        log.info(
            "Ensure all text files: end with a newline, use UTF-8 without BOM, "
            "and use LF line endings"
        )
        return 1

    log.info("All tracked text files comply with .editorconfig rules")
    return 0


def selftest() -> int:
    """Plant each violation, prove it is found; plant its mirror, prove it is not.

    BOTH DIRECTIONS FOR EVERY CHECK. Three of the four rules are exemptions (binary, `.hash`, symlink), and an exemption that widened by one line would make the gate quiet while every control that only plants defects stayed green.
    """
    ctl = Controls("editorconfig", floor=22, verbose=True)

    # -- the two inline controls, driven directly -------------------------
    with tempfile.TemporaryDirectory() as tmp:
        ctl.check("CONTROL: the NUL control fires", nul_control(pathlib.Path(tmp)), True)
    ctl.check("CONTROL: the classifier control passes", classifier_control(), None)

    ctl.check(
        "CLASSIFIER: a path containing 'binary' with a text encoding is NOT binary",
        classify_binary(["some-binary-name.sh: us-ascii"]),
        [],
    )
    ctl.check(
        "CLASSIFIER: a genuinely binary file is binary",
        classify_binary(["assets/logo.png: binary"]),
        ["assets/logo.png"],
    )
    ctl.check(
        "CLASSIFIER: file's column padding is stripped with the encoding",
        classify_binary(["a.sh:       us-ascii", "b.png:      binary"]),
        ["b.png"],
    )
    ctl.check(
        "CLASSIFIER: a path holding ': ' keeps everything but the last field",
        classify_binary(["odd: name.png: binary"]),
        ["odd: name.png"],
    )

    # -- the scanner, plant and mirror for every rule ----------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        def write(name: str, data: bytes) -> str:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(data)
            return name

        clean = write("clean.ts", b"const x = 1;\n")
        no_newline = write("nonewline.ts", b"const x = 1;")
        bom = write("bom.ts", b"\xef\xbb\xbfconst x = 1;\n")
        crlf = write("crlf.ts", b"const x = 1;\r\n")
        empty = write("empty.ts", b"")
        hashfile = write("thing.hash", b"deadbeef")
        corrupt = write("corrupt.ts", b"const x = 1;\x00\n")
        asset = write("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00")

        every = [clean, no_newline, bom, crlf, empty, hashfile, corrupt, asset]
        binary = {corrupt, asset}
        found = scan(root, every, binary)

        ctl.check(
            "PLANT: a missing final newline is caught", ("NEWLINE", no_newline) in found, True
        )
        ctl.check("PLANT: a UTF-8 BOM is caught", ("BOM", bom) in found, True)
        ctl.check("PLANT: a CRLF line ending is caught", ("CRLF", crlf) in found, True)
        ctl.check("PLANT: a NUL in a .ts file is caught", ("NUL", corrupt) in found, True)

        ctl.check(
            "MIRROR: a compliant file is not reported",
            [f for f in found if f[1] == clean],
            [],
        )
        ctl.check(
            "MIRROR: an EMPTY file is not missing its newline",
            [f for f in found if f[1] == empty],
            [],
        )
        ctl.check(
            "MIRROR: a .hash file is exempt from all three byte checks",
            [f for f in found if f[1] == hashfile],
            [],
        )
        ctl.check(
            "MIRROR: a real binary asset is NOT reported for its NUL bytes",
            [f for f in found if f[1] == asset],
            [],
        )

        # A BINARY-FLAGGED FILE SKIPS CHECKS 1-3 ENTIRELY, which is the exemption the second inline control exists to keep honest. `corrupt.ts` ends without a newline problem but does carry a CRLF, and neither is reported: only the NUL is.
        crlf_binary = write("both.ts", b"a\r\n\x00")
        both = scan(root, [crlf_binary], {crlf_binary})
        ctl.check(
            "MIRROR: a binary-flagged text file reports ONLY the NUL, not its CRLF",
            both,
            [("NUL", crlf_binary)],
        )
        ctl.check(
            "PLANT: the same file NOT flagged binary reports its CRLF instead",
            scan(root, [crlf_binary], set()),
            [("NEWLINE", crlf_binary), ("CRLF", crlf_binary)],
        )

        # A binary file whose extension is NOT in the text list is invisible to check 4. This is the property that makes the check unable to false-positive on assets, and it is asserted rather than trusted.
        blob = write("data.bin", b"\x00\x01\x02")
        ctl.check(
            "MIRROR: a NUL in a non-text extension is not corruption",
            scan(root, [blob], {blob}),
            [],
        )

        # SYMLINKS ARE SKIPPED. Both halves: the link is not reported, and its target still is when the target is itself enumerated.
        link = "link.ts"
        (root / link).symlink_to(root / no_newline)
        ctl.check("MIRROR: a symlink is skipped", scan(root, [link], set()), [])
        ctl.check(
            "CONTROL: the symlink's target is still reported in its own right",
            scan(root, [no_newline], set()),
            [("NEWLINE", no_newline)],
        )

        # A path that does not exist at all is skipped rather than crashing: git can list a file a concurrent checkout has just removed.
        ctl.check(
            "MIRROR: a vanished path is skipped, not a crash", scan(root, ["gone.ts"], set()), []
        )

    # -- the whole gate, over a fixture repository -------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        def run(files: dict[str, bytes]) -> int:
            # EVERY CASE STARTS FROM AN EMPTY WORKING TREE. Without this the fixtures accumulate and a later case reds because of an earlier
            # case's plant, which reads as the port being wrong about the input
            # it was actually given. Found exactly that way.
            for stale in root.iterdir():
                if stale.name == ".git":
                    continue
                if stale.is_dir():
                    shutil.rmtree(stale)
                else:
                    stale.unlink()
            for name, data in files.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(data)
            for command in (
                ["git", "init", "-q", "-b", "main", "."],
                ["git", "add", "-A"],
            ):
                subprocess.run(
                    command,
                    cwd=str(root),
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        ctl.check("CONTROL: a compliant tracked tree passes", run({"ok.ts": b"const x = 1;\n"}), 0)
        ctl.check("PLANT: an offending tracked file reds", run({"bad.ts": b"const x = 1;"}), 1)
        # A TWIN BLIND SPOT, MEASURED HERE AND REPORTED RATHER THAN REPAIRED. `file --mime-encoding` calls a very short text file BINARY -- a
        # one-byte `x` comes back `binary` while `const x = 1;` comes back
        # `us-ascii` -- so a tiny tracked text file is silently exempted from checks 1 to 3 and can carry a missing newline, a BOM or a CRLF forever. The port reproduces it because it uses the same oracle with the same flags, and the control below pins the behaviour so a future reader meets it as a decision instead of as a surprise.
        ctl.check(
            "TWIN BLIND SPOT: a one-byte text file is classified binary and skips checks 1-3",
            run({"tiny.ts": b"x"}),
            0,
        )

        # ZERO TRACKED FILES. The twin exits 0 here, which is a REPORTED DEFECT rather than a design: a gate that enumerated nothing has verified nothing, and its green is indistinguishable from a clean tree. The port agrees with the twin on purpose, and the disagreement is recorded here so it is a decision rather than an oversight.
        bare = pathlib.Path(tmp) / "bare"
        bare.mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "main", "."],
            cwd=str(bare),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        saved = os.environ.get(paths.ROOT_ENV)
        os.environ[paths.ROOT_ENV] = str(bare)
        try:
            ctl.check("TWIN DEFECT: an EMPTY corpus still exits 0", main([]), 0)
        finally:
            if saved is None:
                del os.environ[paths.ROOT_ENV]
            else:
                os.environ[paths.ROOT_ENV] = saved

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
