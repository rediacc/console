"""The generated CLI contract must not drift from the CLI it is generated from.

Ported from `.ci/scripts/quality/check-cli-contract.sh`, which is not deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHAT THE CONTRACT IS, from the twin's header. `packages/shared/src/cli-contract/data`
is derived from the live Commander tree, COMMAND_METADATA and the i18n
catalogues. It drives the web console, the `rdc --proxy` thin client and the
executor, so a stale contract means those consumers disagree with the CLI they
are driving.

Exit codes, unchanged: 0 contract is up-to-date, 1 stale contract detected.

HOW IT DECIDES. It REGENERATES the contract into a temporary directory and
diffs, rather than checking a hash or a timestamp. That is the expensive answer
and the only honest one: a hash pinned in a file is a claim about a generator
nobody re-ran, and a timestamp says which file is newer, not whether they agree.

THE VERSION IS EXCLUDED FROM THE DIFF, and the twin says why: "The version is
injected at build time, so ignore it when diffing (both the TS constant and the
JSON field). Mirrors check-renet-types.sh." This repository stores no version in
source at all -- every package.json carries the `0.0.0-dev` placeholder and the
real value arrives from a git tag at build time -- so a contract regenerated on
a developer's machine differs from the committed one in exactly those two lines
and in nothing else.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE GLOB HAS NO `nullglob`, AND THAT IS A DEFECT THE PORT REPRODUCES RATHER THAN
REPAIRS. `for generated in "$TEMP_DIR"/i18n/*.json` in bash, with no `shopt -s
nullglob`, iterates ONCE over the LITERAL PATTERN when nothing matches. The loop
body then computes `basename` as the string `*.json`, tests `-f
"$OUTPUT_DIR/i18n/*.json"` (false, because no file is named that), and appends
`i18n/*.json (missing)` to the stale list. So an EMPTY generated i18n directory
does not report "no locales were generated", it reports a missing locale whose
name is a glob. The second loop, over the committed directory, has the same
shape and produces `i18n/*.json (orphaned ...)`.

It is carried because a port that changes the verdict is not a port, and it is
reported as a finding instead of quietly fixed. The message it produces is
recognisable once you know it, which is the only reason it has never been
mistaken for a real locale.

THE SAME FILE CARRIES AN EM DASH IN USER-FACING OUTPUT: `i18n/$lang (orphaned <em dash>
no such locale)`. The house rule forbids em dashes in authored text, and the
differential requires the port to emit the same bytes. Both are satisfied by
writing the character as the escape `\\u2014`, so no em dash is typed into this
file while the emitted string stays byte-identical to the twin's. The finding
belongs to the twin and is reported rather than repaired here.

`npm` AND `npx` ARE RESOLVED THROUGH PATH, DELIBERATELY. The twin runs them as
bare words and so does this module, which is what lets a hermetic fixture put a
shim ahead of the real binaries and drive the whole gate without a build. A port
that hardcoded a path, or reached into `node_modules/.bin`, would be untestable
by exactly the harness that proves it equivalent.

BUILD FAILURE PROPAGATES THE BUILDER'S EXIT CODE, not 1. The twin runs under
`set -euo pipefail`, so a failing `npm run build:packages` aborts the script
with npm's own status and the gate never reaches its comparison. Collapsing that
to 1 would tell a reader "the contract is stale" when the truth is "the build
did not happen", which is the difference between a finding and a cannot-run.

STDOUT OF BOTH SUBPROCESSES IS DISCARDED AND STDERR IS NOT. `>/dev/null` in the
twin redirects stdout only. A build's progress chatter is noise; its errors are
the only thing that explains a non-zero status, and swallowing them is how a
gate failure becomes unreadable.

WHAT THIS GATE CANNOT SEE, unchanged: whether the generator itself is correct.
It proves the committed data equals what the generator produces TODAY, so a
generator that started emitting nonsense would make the tree stale, get
regenerated, and go green on the nonsense. That is the twin's blind spot and the
port inherits it rather than growing a second opinion.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# Where the committed contract lives, relative to the repository root.
OUTPUT_SUBDIR = "packages/shared/src/cli-contract/data"

# The generator, run through `npx tsx` from the repository root.
GENERATOR = "packages/cli/scripts/generate-cli-contract.ts"

# The two non-i18n artefacts, in the twin's order. Order is visible in the `Stale CLI contract: ...` line, which joins the list with spaces.
TOP_LEVEL_FILES = ("contract.generated.ts", "contract.json")

# The two substrings whose lines are dropped before diffing. Substrings, not
# patterns: `grep -v -e '_VERSION = ' -e '"version":'` is BRE and neither string
# contains a BRE metacharacter, so a literal `in` test is the same question.
VERSION_MARKERS = ("_VERSION = ", '"version":')

# The em dash the twin emits, written as an escape. See the port notes.
ORPHAN_SUFFIX = " (orphaned \u2014 no such locale)"


def strip_version_lines(path: pathlib.Path) -> str | None:
    """A file's content with every version-bearing line removed.

    Returns None when the file cannot be read, which is what `grep` on a missing
    file amounts to: an empty stream plus a complaint on stderr. The caller
    reproduces the complaint, because the twin's process substitutions inherit
    the script's stderr and the message reaches a reader today.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.split("\n")
    # `split` leaves a trailing empty element for a file that ends in a newline. grep would not emit a line there, so it is dropped before filtering rather than filtered and re-joined, which would add a spurious blank line to one side of the comparison.
    if lines and lines[-1] == "":
        lines.pop()
    kept = [line for line in lines if not any(marker in line for marker in VERSION_MARKERS)]
    # grep terminates every line it prints, including a final one the input did not terminate. Rebuilding with a trailing newline per line reproduces the bytes `diff` actually compares.
    return "".join(line + "\n" for line in kept)


def compare_ignoring_version(committed: pathlib.Path, generated: pathlib.Path) -> bool:
    """True when the two files agree once version lines are removed.

    `diff -q ... >/dev/null 2>&1` in the twin, so a diff of any size is one bit
    of information. The bit is what the stale list records.
    """
    left = strip_version_lines(committed)
    right = strip_version_lines(generated)
    for path, content in ((committed, left), (generated, right)):
        if content is None:
            print("grep: %s: No such file or directory" % path, file=sys.stderr)
    return left is not None and right is not None and left == right


def _glob_or_literal(directory: pathlib.Path) -> list[pathlib.Path]:
    """`<directory>/*.json` with BASH's no-nullglob behaviour.

    An empty match yields ONE entry: the unexpanded pattern itself. See the port
    notes for what the twin then does with it. Sorted for the same reason bash
    sorts a glob, and by bytes because LC_ALL=C is what CI runs under.
    """
    matches = sorted(directory.glob("*.json"), key=lambda p: str(p).encode())
    if matches:
        return matches
    return [directory / "*.json"]


def stale_entries(output_dir: pathlib.Path, temp_dir: pathlib.Path) -> list[str]:
    """Everything the twin would put in its STALE array, in the twin's order.

    Three passes, and the third is the one people forget: a locale bundle left
    behind after its locale was removed is drift in the other direction, and a
    gate that only compared generated-against-committed would never see it.
    """
    stale: list[str] = []

    for name in TOP_LEVEL_FILES:
        committed = output_dir / name
        if not committed.is_file():
            stale.append("%s (missing)" % name)
        elif not compare_ignoring_version(committed, temp_dir / name):
            stale.append(name)

    for generated in _glob_or_literal(temp_dir / "i18n"):
        lang = generated.name
        committed = output_dir / "i18n" / lang
        if not committed.is_file():
            stale.append("i18n/%s (missing)" % lang)
        elif not _files_equal(committed, generated):
            stale.append("i18n/%s" % lang)

    for committed in _glob_or_literal(output_dir / "i18n"):
        lang = committed.name
        if not (temp_dir / "i18n" / lang).is_file():
            stale.append("i18n/%s%s" % (lang, ORPHAN_SUFFIX))

    return stale


def _files_equal(left: pathlib.Path, right: pathlib.Path) -> bool:
    """Plain `diff -q`: no version filtering for the i18n bundles.

    The twin filters versions out of the two top-level artefacts and NOT out of
    the locale bundles, because no version is injected into them. Applying the
    filter uniformly would be tidier and would stop the gate seeing a locale
    whose text happens to contain `"version":`, which several of them do.
    """
    try:
        return left.read_bytes() == right.read_bytes()
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 up-to-date, 1 stale, or the builder's own code."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    output_dir = root / OUTPUT_SUBDIR

    # The generator imports the live CLI, which resolves @rediacc/shared and @rediacc/provisioning through their dist builds.
    log.step("Building packages the CLI imports...")
    build = subprocess.run(
        ["npm", "run", "build:packages"],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        check=False,
    )
    if build.returncode != 0:
        # `set -e`: the twin dies here with npm's status and never compares anything. See the port notes for why this is not collapsed to 1.
        return build.returncode

    log.step("Regenerating the CLI contract...")
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = pathlib.Path(tmp)
        generate = subprocess.run(
            ["npx", "tsx", GENERATOR, "--output", str(temp_dir)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            check=False,
        )
        if generate.returncode != 0:
            return generate.returncode

        stale = stale_entries(output_dir, temp_dir)

    if not stale:
        log.info("CLI contract is up-to-date")
        return 0

    # `${STALE[*]}` joins with the first character of IFS, which is a space.
    log.error("Stale CLI contract: %s" % " ".join(stale))
    log.error("The CLI changed but the generated contract did not. Run:")
    log.error("  npm run generate:cli-contract -w @rediacc/cli")
    log.error("then commit packages/shared/src/cli-contract/data.")
    return 1


# The shims the selftest puts ahead of the real binaries. `npm` does nothing and
# succeeds; `npx` copies a golden directory into `--output`. Both are FILES on
# PATH rather than Python mocks, because the subject resolves them through PATH and a mock inside this process would prove nothing about that.
_NPM_SHIM = "#!/bin/bash\nexit ${SHIM_NPM_EXIT:-0}\n"
_NPX_SHIM = """#!/bin/bash
# Reads the --output argument the way the real generator does, then copies the
# golden tree into it. Exits ${SHIM_NPX_EXIT:-0} so the failure branch is
# drivable too.
out=""
while [ $# -gt 0 ]; do
    if [ "$1" = "--output" ]; then out="$2"; shift; fi
    shift
done
[ -n "$out" ] || { echo "shim: no --output" >&2; exit 64; }
mkdir -p "$out"
cp -r "$SHIM_GOLDEN"/. "$out"/
exit ${SHIM_NPX_EXIT:-0}
"""


def _write_tree(base: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """Write `{relative path: content}` under `base` and return it."""
    for relative, content in files.items():
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return base


# The smallest tree that is a valid contract: two top-level artefacts and one locale. Every plant below is this dict with exactly one entry changed, which is what makes each control name a single cause.
_GOLDEN = {
    "contract.generated.ts": 'export const CLI_VERSION = "0.0.0-dev";\nexport const X = 1;\n',
    "contract.json": '{\n  "version": "0.0.0-dev",\n  "commands": ["repo"]\n}\n',
    "i18n/en.json": '{"repo": "Repository"}\n',
    "i18n/tr.json": '{"repo": "Depo"}\n',
}


def selftest() -> int:
    """Plant each kind of drift, prove it reds; remove it, prove it greens.

    THE SHIMS ARE THE POINT. Driving the real `npm run build:packages` here
    would make the selftest a build, which is slow enough that it would get
    switched off, and would prove nothing about the comparison logic that is
    the gate's actual subject.
    """
    ctl = Controls("cli-contract", floor=15, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        (bin_dir / "npm").write_text(_NPM_SHIM, encoding="utf-8")
        (bin_dir / "npx").write_text(_NPX_SHIM, encoding="utf-8")
        (bin_dir / "npm").chmod(0o755)
        (bin_dir / "npx").chmod(0o755)

        golden = _write_tree(base / "golden", _GOLDEN)

        def run(committed: dict[str, str], **shim_env: str) -> int:
            """Drive the gate over a fixture whose committed data is `committed`."""
            root = base / "root"
            if root.exists():
                shutil.rmtree(root)
            _write_tree(root / OUTPUT_SUBDIR, committed)
            saved = {
                key: os.environ.get(key)
                for key in ("PATH", paths.ROOT_ENV, "SHIM_GOLDEN", "SHIM_NPM_EXIT", "SHIM_NPX_EXIT")
            }
            os.environ["PATH"] = "%s:%s" % (bin_dir, saved["PATH"] or "")
            os.environ[paths.ROOT_ENV] = str(root)
            os.environ["SHIM_GOLDEN"] = str(golden)
            os.environ.pop("SHIM_NPM_EXIT", None)
            os.environ.pop("SHIM_NPX_EXIT", None)
            os.environ.update(shim_env)
            try:
                return main([])
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        # CONTROL FIRST: committed data identical to what the generator emits. Without this every plant below could be firing against a fixture that was already stale, and the suite would be green while testing nothing.
        ctl.check("CONTROL: an up-to-date contract passes", run(dict(_GOLDEN)), 0)

        # THE VERSION EXEMPTION, in both directions. A contract differing ONLY in the injected version is NOT stale...
        version_only = dict(_GOLDEN)
        version_only["contract.generated.ts"] = (
            'export const CLI_VERSION = "1.2.3";\nexport const X = 1;\n'
        )
        version_only["contract.json"] = '{\n  "version": "1.2.3",\n  "commands": ["repo"]\n}\n'
        ctl.check("MIRROR: a version-only difference is not stale", run(version_only), 0)

        # ...and a difference on any OTHER line still is, which is what stops the exemption from swallowing the whole file.
        real_drift = dict(_GOLDEN)
        real_drift["contract.generated.ts"] = (
            'export const CLI_VERSION = "1.2.3";\nexport const X = 2;\n'
        )
        ctl.check("PLANT: drift beside a version change is caught", run(real_drift), 1)

        # PLANT: each top-level artefact, missing and then merely different.
        for name in TOP_LEVEL_FILES:
            without = {k: v for k, v in _GOLDEN.items() if k != name}
            ctl.check("PLANT: a missing %s is caught" % name, run(without), 1)
            changed = dict(_GOLDEN)
            changed[name] = _GOLDEN[name] + "// drift\n"
            ctl.check("PLANT: a changed %s is caught" % name, run(changed), 1)

        # PLANT: a locale bundle that drifted, and one that was never committed.
        drifted = dict(_GOLDEN)
        drifted["i18n/tr.json"] = '{"repo": "Havuz"}\n'
        ctl.check("PLANT: a drifted locale bundle is caught", run(drifted), 1)
        missing_locale = {k: v for k, v in _GOLDEN.items() if k != "i18n/tr.json"}
        ctl.check("PLANT: an uncommitted locale is caught", run(missing_locale), 1)

        # PLANT: the ORPHAN direction, which a one-way comparison misses entirely. A committed bundle for a locale the generator no longer emits is drift, and the twin is one of the few gates that checks it.
        orphaned = dict(_GOLDEN)
        orphaned["i18n/zz.json"] = '{"repo": "Zed"}\n'
        ctl.check("PLANT: an orphaned locale bundle is caught", run(orphaned), 1)

        # THE NO-NULLGLOB DEFECT, pinned rather than fixed. An empty committed i18n directory makes the SECOND loop iterate over the literal pattern, and the entry it produces names a glob. Asserting the exact string here is what stops a future "cleanup" from silently changing the verdict, and what makes the finding visible to a reader of this file.
        empty_i18n = base / "empty-i18n"
        if empty_i18n.exists():
            shutil.rmtree(empty_i18n)
        _write_tree(empty_i18n, {k: v for k, v in _GOLDEN.items() if not k.startswith("i18n/")})
        (empty_i18n / "i18n").mkdir(parents=True, exist_ok=True)
        entries = stale_entries(empty_i18n, golden)
        ctl.truthy(
            "DEFECT PINNED: an empty committed i18n yields a glob-named orphan",
            any(entry.startswith("i18n/*.json") for entry in entries),
        )

        # THE GLOB'S NORMAL CASE, so the no-nullglob pin above is not passing because the helper always returns the literal. Both directions of the same function, which is the only way either assertion means anything.
        ctl.check(
            "GLOB MIRROR: a populated directory returns its real files",
            [p.name for p in _glob_or_literal(golden / "i18n")],
            ["en.json", "tr.json"],
        )

        # THE VERSION FILTER IS NOT APPLIED TO LOCALE BUNDLES, which is the asymmetry `_files_equal` exists for. A bundle whose only difference is a line containing `"version":` is STILL stale, and a port that had unified the two comparisons would report it clean.
        version_in_locale = dict(_GOLDEN)
        version_in_locale["i18n/en.json"] = '{"repo": "Repository", "version": "x"}\n'
        ctl.check(
            "ASYMMETRY: a version line inside a locale bundle is still drift",
            run(version_in_locale),
            1,
        )

        # SETUP ERRORS ARE NOT VERDICTS. A failing build must propagate the builder's code, not be reported as a stale contract.
        ctl.check(
            "SETUP: a failing build propagates its own exit code",
            run(dict(_GOLDEN), SHIM_NPM_EXIT="7"),
            7,
        )
        ctl.check(
            "SETUP: a failing generator propagates its own exit code",
            run(dict(_GOLDEN), SHIM_NPX_EXIT="9"),
            9,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
