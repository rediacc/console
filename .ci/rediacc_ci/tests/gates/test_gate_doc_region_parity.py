"""Port of `.ci/scripts/test/gates/test-doc-region-parity.sh`.

`check:ci-doc-region-parity`, proved in both directions against a REAL fixture tree.

WHY A FIXTURE AND NOT THE LIVE TREE. `test-docs-gen.sh` case A runs the generator
against the checkout itself and requires a green. That couples a gate test to whether
some other session has regenerated the docs after adding a gate, and it was RED on
the branch where the twin was written: the manifest had grown and CLAUDE.md still
quoted the old totals. A control that cannot run until the tree is tidy is a control
that gets skipped. So every case here runs against a fixture built from the
repository's own files, where this test owns every byte and can perturb them without
touching anything a person is working in.

WHAT EACH CASE PROVES, in the twin's order and under the twin's letters:

  A. the fixture is REAL: every provider the code declares yields rows in it, and the
     fixture document carries one region per provider. The marker list is derived
     from `--list`, so ANOTHER provider is covered without editing this file. A count
     is deliberately not written here: it was "a seventh provider" while there were
     six, and there are twelve as of 2026-09-09.
  B. GREEN: the gate accepts a freshly generated tree, and prints a PASS line per
     region. Exit 0 with no PASS lines would be the vacuity this whole estate exists
     to refuse, so the PASS lines are counted rather than trusted.
  C. RED on one perturbed cell, naming the file, the region and the row.
  D. restored, and green again. Without D, C only proves the gate can fail, not that
     it can still pass, and a gate that always fails is removed rather than fixed.
  E. a REORDER is reported as a MOVE. Same rows, same count, same set.
  F. THE CASE THIS GATE EXISTS FOR. A document that loses its markers keeps its now
     hand-typed table, and the generator reports success over the documents that
     remain. BOTH halves are asserted: gen-docs stays green and this gate reds.
  G. a marker a human reads as a marker but the parser does not is named by line.
  H. a root with no markdown is a FAILURE. Zero inputs is never a pass.
  I. `--selftest` is green and still carries its planted controls BY NAME. Asserting
     the exit code alone keeps passing after someone deletes the controls.

A FLAT TWIN, so the parity floor is its runtime `PASS:` count. Measured 2026-09-07:
NINE, and the measurement needs one caveat that will otherwise waste somebody's
afternoon. `grep -c '^PASS:'` on that twin's output prints ZERO, because
`test-helpers.sh` writes the colour escape BEFORE the word, so no line literally
starts with `PASS:`. The parity driver strips ANSI first and then counts, which gives
nine. This module records one control per lettered case, nine in total.

THE FIXTURE'S CONTENTS ARE DERIVED, NOT TYPED, AND THAT IS THE POINT.

  This module used to carry an enumerated `TRACKED_PATHSPECS`, and enumeration LOST.
  `gen-docs` and its providers read the tree transitively, and nothing tells the author
  of a new provider that a list inside a test file exists. On 2026-09-09 alone the
  enumeration fell behind four separate times: `scripts/lib/policy-paths.ts`, then four
  W11 P5a seams (`run.sh`, `.ci/legacy/run-legacy.sh`, `.devcontainer/toolchain.env`,
  the two `sync-media-*.sh`), then `.ci/rediacc_ci/policy_paths.py`, then
  `.ci/scripts/quality/check_test_file_orphans.py`. Every miss surfaced as a node ENOENT
  stack trace or as the generator's own anti-vacuity refusal, which is to say as SEVEN
  RED CASES that said nothing at all about the gate. Not one of the four was a defect
  in the gate, or in the generator, or in a provider.

  So the pathspecs are derived FROM THE GENERATOR, in two steps:

    1. `import_closure()` walks the relative imports out of `scripts/gen-docs.ts`. A
       specifier that resolves to nothing is a LOUD failure naming it, never a silently
       short walk, because a walk that quietly returns one file would derive one file's
       literals and look like a much smaller repository.
    2. `derive_pathspecs()` keeps every quoted literal in those files that resolves to a
       TRACKED FILE or a TRACKED DIRECTORY. A provider has to NAME the seam it opens, so
       that literal is the one thing the author of a new provider cannot forget to write.

  The filter is "is this a real tracked path", which no regex can decide on its own and
  which cannot produce a false positive that hurts: a literal that happens to name a real
  path is a path this fixture can afford to carry. It OVER-copies on purpose. `.ci` and
  `.claude` arrive whole, because `ciTreeProvider` and the hook providers enumerate them
  whole; the derivation does not have to be minimal, only complete.

  DERIVATION IS NOT PROOF, so there is a second net behind it. If the generator still
  fails inside the fixture, `explain_fixture_gap()` reads the failure for paths that
  exist in the REPOSITORY and not in the FIXTURE, and names them. The next gap is then
  one sentence naming one file, rather than a stack trace from inside node.

WHERE THIS REIMPLEMENTS git, tar, grep, cut AND python, AND WHY THE ANSWERS AGREE.

  `git ls-files -z | tar -c --null --files-from=- | tar -x` copies exactly the TRACKED
  files under a set of pathspecs, preserving their relative layout. `copy_tracked`
  below drives the same `git ls-files -z` and copies each named path, creating parent
  directories. The tar pair is a transport, not a filter: everything it copies came
  out of `git ls-files`, so enumerating once and copying is the same set. The
  PATHSPECS are derived rather than typed (above); the COPY is still the twin's.
  Symlinks are the one place the two transports could differ, so `copy_tracked`
  refuses rather than guessing if it meets one.

  `cut -f1 list.txt` is the first TAB-separated field, which is `split("\\t")[0]` --
  `cut -f` defaults to TAB, not to whitespace, so `str.split()` would be wrong here
  and is not used.

  `grep -c '  PASS  '` counts LINES CONTAINING that fixed string, two spaces on each
  side. Not occurrences: a line carrying it twice counts once. The Python form counts
  lines the same way.

  `grep -q 'region \\`<id>\\` matches'` and the `-qF` needles in case I are fixed-string
  containment.

  The three inline `python3` perturbations (perturb a row, swap two rows, strip a
  marker pair, indent a marker) are lifted as functions, and each keeps its
  `raise SystemExit(...)` as a `log_fail`: a perturbation that could not find its
  anchor must be a red naming the anchor, never a silently skipped case.

`npx tsx`, `node` AND `git` ARE ALL REQUIRED, and each absence is a loud failure
carrying the fix. A case that could not run has not been checked.

NO `xdist_group`. The fixture, its git index and every perturbed copy live under
pytest's own `tmp_path`. The generator is run from the FIXTURE's copy of
`gen-docs.ts` so that `--write` can only ever reach the fixture: gen-docs roots itself
at its own parent directory, which is what makes the copy a containment boundary
rather than a convention.
"""

import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-doc-region-parity.sh"

ROOT = paths.repo_root()
GATE = ROOT / "scripts" / "gates" / "check-doc-region-parity.ts"
GEN = ROOT / "scripts" / "gen-docs.ts"

# The generator, repo-relative. Everything the fixture needs is reachable from here.
GEN_ENTRY = "scripts/gen-docs.ts"

# A RELATIVE import out of one of the generator's own modules. `node:` builtins and bare
# package specifiers are excluded by the required leading dot, which is exactly right: only
# this repository's own modules have to be copied into the fixture.
IMPORT_RE = re.compile(r"""(?:from|import)\s*\(?\s*['"](\.[^'"\n]+)['"]""")

# A quoted literal that COULD be a repository-relative path. Deliberately permissive; the
# filter that matters is applied afterwards and is "does git track this file or directory", which no regex can answer.
PATHISH_RE = re.compile(r"""['"`]([A-Za-z0-9_.][A-Za-z0-9_./-]*)['"`]""")

# Path characters, for pulling a filename back out of a node stack trace or an error line.
PATHCHARS_RE = "([A-Za-z0-9_./-]+)"

# The named controls case I requires by name. A COUNT would survive somebody deleting one control and adding another.
SELFTEST_CONTROLS = (
    "REORDERED rows are reported as a MOVE",
    "the counts a naive check would compare are EQUAL across that move",
    "planted: an INDENTED marker is a near miss",
    "planted: a provider DECLARED but never registered",
    "planted: a truncated source reads as fewer ids",
    "CONTROL: a marker QUOTED inside a table cell is neither",
    "the rendered body has the exact shape gen-docs writes",
)

OPEN_MARKER = "<!-- >>> gen-docs:"
CLOSE_MARKER = "<!-- <<< gen-docs"


def tool(name: str, fix: str) -> str:
    return harness.require_tool(name, fix)


def npx(gate) -> str:  # noqa: ARG001 - `gate` keeps every caller uniform
    return tool(
        "npx",
        "install Node 22 (the version .devcontainer/toolchain.env pins), or run this "
        "under the devbox where it is already on PATH",
    )


def git(gate) -> str:  # noqa: ARG001 - `gate` keeps every caller uniform
    return tool("git", "install git")


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def resolve_import(importer: pathlib.Path, spec: str) -> pathlib.Path | None:
    """`./lib/doc-providers.js` -> `scripts/lib/doc-providers.ts`, on disk or nothing.

    NodeNext spells a TypeScript import with the `.js` extension it will have after a
    build, so the literal in the source names a file that does not exist. Every shape
    this repository actually writes is tried, and a specifier that answers to none of
    them is reported by the caller rather than dropped.
    """
    base = importer.parent / spec
    candidates = [base]
    if base.suffix in (".js", ".jsx", ".mjs", ".cjs"):
        candidates += [base.with_suffix(".ts"), base.with_suffix(".tsx")]
    else:
        candidates += [base.with_name(base.name + ext) for ext in (".ts", ".tsx", ".js")]
    candidates += [base / "index.ts", base / "index.js"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def import_closure(gate) -> list[pathlib.Path]:
    """Every module the generator pulls in, transitively, as absolute paths.

    THE SHORT-WALK FAILURE IS THE ONE TO GUARD. If `IMPORT_RE` stopped matching, this
    would return the entry alone, `derive_pathspecs` would see one file's literals, the
    fixture would be built from a fraction of what the providers read, and the whole
    file would red with a node stack trace pointing at the generator. So an unresolvable
    specifier is a named failure, and a closure of one is refused outright: the generator
    has imported its providers from a sibling module since the day it was written.
    """
    entry = ROOT / GEN_ENTRY
    if not entry.is_file():
        gate.log_fail("%s is missing; there is nothing to derive a fixture from" % GEN_ENTRY)
    seen: dict[pathlib.Path, str] = {}
    queue = [entry.resolve()]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        text = read_text(current)
        seen[current] = text
        for match in IMPORT_RE.finditer(text):
            spec = match.group(1)
            target = resolve_import(current, spec)
            if target is None:
                gate.log_fail(
                    "%s imports %r and no file on disk answers it, so this fixture cannot "
                    "know which module to copy. Either the specifier is broken or "
                    "resolve_import has not met this shape before."
                    % (current.relative_to(ROOT), spec)
                )
            queue.append(target)
    if len(seen) < 2:
        gate.log_fail(
            "the import walk found NO local import from %s, so the closure is the entry "
            "alone. gen-docs has imported its providers from ./lib since it was written, "
            "so this means IMPORT_RE stopped matching, not that the generator became "
            "self-contained. A fixture built from this would be silently tiny." % GEN_ENTRY
        )
    return sorted(seen)


def tracked_index(gate) -> tuple[set[str], set[str]]:
    """(every tracked file, every directory that contains one), repo-relative."""
    listing = harness.run([git(gate), "-C", str(ROOT), "ls-files", "-z"], timeout=600)
    if listing.rc != 0:
        gate.log_fail("git ls-files failed, so nothing can be derived: %s" % listing.err)
    files = {name for name in listing.out.split("\0") if name}
    if not files:
        gate.log_fail("git ls-files named no tracked file at all in %s" % ROOT)
    dirs: set[str] = set()
    for name in files:
        head = name
        while "/" in head:
            head = head.rsplit("/", 1)[0]
            dirs.add(head)
    return files, dirs


def derive_pathspecs(gate) -> tuple[list[pathlib.Path], list[str]]:
    """(the generator's import closure, the pathspecs its literals resolve to).

    A provider cannot read a seam without naming it, so the literal IS the declaration.
    Anything that resolves to a tracked file or a tracked directory is copied; everything
    else in the source is not a path and is dropped by that test alone, never by a
    hand-kept list.
    """
    closure = import_closure(gate)
    files, dirs = tracked_index(gate)
    specs = {str(path.relative_to(ROOT)) for path in closure}
    for path in closure:
        for match in PATHISH_RE.finditer(read_text(path)):
            literal = match.group(1)
            # `.` is `lsFiles(root, '.')`, the whole tree. It is a real directory and it is not a pathspec this fixture can honour: the tracked tree is 2.0 GB, most of it submodule binaries no provider reads.
            if literal in (".", ".."):
                continue
            if literal in files or literal in dirs:
                specs.add(literal)
    if not specs:
        gate.log_fail(
            "no literal in %s resolved to a tracked path, so the fixture would hold only "
            "the generator itself and every case below would be vacuous"
            % ", ".join(str(p.relative_to(ROOT)) for p in closure)
        )
    return closure, sorted(specs)


def explain_fixture_gap(gate, fixture: pathlib.Path, result: harness.RunResult) -> None:
    """Name the inputs the fixture LACKS, when the generator failed inside it.

    A stale fixture and a broken gate look identical from the outside: both are a
    non-zero exit out of `run_fixgen`. They are not the same defect and they are not
    fixed by the same person, so this reads the failure text for paths that exist in the
    REPOSITORY and do not exist in the FIXTURE and prints them by name. Two shapes are
    recognised, which is every shape the generator produces today: node's own ENOENT,
    which names the path ABSOLUTE inside the fixture, and `readSeam`'s refusal in
    scripts/lib/doc-providers.ts, which names it REPO-RELATIVE.

    Silent when there is no gap, because then the failure really is about the gate.
    """
    text = result.combined
    gaps: list[str] = []
    seen: set[str] = set()

    def note(rel: str) -> None:
        # A stack trace puts the path in a sentence, so trailing punctuation rides along.
        rel = rel.rstrip(".:,;")
        if rel in ("", ".", "..") or rel in seen:
            return
        seen.add(rel)
        if (fixture / rel).exists() or not (ROOT / rel).exists():
            return
        gaps.append(rel)

    for match in re.finditer(re.escape(str(fixture)) + "/" + PATHCHARS_RE, text):
        note(match.group(1))
    for match in re.finditer(PATHCHARS_RE + r" is missing, so this provider", text):
        note(match.group(1))
    if not gaps:
        return
    gate.log_error(
        "FIXTURE GAP: %d path(s) exist in this repository and NOT in the fixture, so the "
        "generator could not run. That is a stale fixture, not a broken gate." % len(gaps)
    )
    for rel in sorted(gaps):
        gate.log_error("  missing from the fixture: %s" % rel)
    gate.log_error(
        "  Each is read by a provider, but no quoted literal in the generator's import "
        "closure resolved to it. Name it as a string literal in the provider that reads "
        "it, or teach derive_pathspecs the shape it is written in."
    )


def copy_tracked(gate, fixture: pathlib.Path, pathspecs: list[str]) -> int:
    """The twin's `git ls-files -z | tar | tar`, as an enumerate-and-copy.

    Built from the repository's own TRACKED files, because the providers read real
    shapes: a gates lock they refuse when it is malformed, the hook wiring in
    `.claude/settings.json`, files carrying `BLOCKER:`, and a `.ci` subtree.
    Hand-rolled stand-ins would drift from those shapes and the test would then be
    proving something about the stand-ins.
    """
    listing = harness.run(
        [git(gate), "-C", str(ROOT), "ls-files", "-z", "--", *pathspecs],
        timeout=600,
    )
    if listing.rc != 0:
        gate.log_fail("git ls-files failed, so the fixture has no contents: %s" % listing.err)
    names = sorted({name for name in listing.out.split("\0") if name})
    # DROP THIS REPOSITORY'S OWN GENERATED DOCUMENTS, here and not at pathspec level: a spec can be a DIRECTORY, and `git ls-files -- scripts/data` expands it to include `scripts/data/doc-registry.md`. Filtering the spec list therefore misses exactly the
    # case that matters, which is how the first attempt at this failed.
    #
    # THE FIXTURE MUST CARRY EXACTLY ONE DOCUMENT, the REGISTRY.md it writes itself with one region per provider. Every case works by perturbing that document -- case F strips the first region and requires the gate to report the provider "used by NO region". A second document holding a region for the same provider keeps it used, the gate stays green, and the control stops firing in
    # silence. Measured 2026-09-09: a new provider naming the literal `scripts/data` pulled in the real registry and case F
    # went quiet within the hour. The module docstring warned about this coupling; this
    # makes the warning enforceable.
    carriers = [n for n in names if n.endswith(".md") and OPEN_MARKER in read_text(ROOT / n)]
    if carriers:
        gate.log_info(
            "fixture excludes %d region-carrying document(s): %s"
            % (len(carriers), ", ".join(carriers))
        )
        names = [n for n in names if n not in set(carriers)]
    copied = 0
    if not names:
        gate.log_fail(
            "git ls-files named no tracked file under %s, so the fixture would be empty "
            "and every case below vacuous" % ", ".join(pathspecs)
        )
    for name in names:
        source = ROOT / name
        if source.is_symlink():
            gate.log_fail(
                "%s is a symlink; the tar pair the twin uses would copy it as a link and "
                "this copier would follow it, so the two fixtures would differ. Refusing "
                "rather than guessing." % name
            )
        # A submodule is ONE `git ls-files` entry whose mode is 160000 and whose path is a directory on disk. There are four (`private/*`), and no provider reads inside them, so they are skipped rather than recursed into: recursing would pull ~2 GB of vendored binaries into every one of this file's seven fixtures.
        if not source.is_file():
            continue
        target = fixture / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    if copied == 0:
        gate.log_fail(
            "%d tracked path(s) matched but NONE was a regular file, so the fixture is "
            "empty and every case below would be vacuous" % len(names)
        )
    return copied


def run_gate(gate, *argv: str) -> harness.RunResult:
    """The gate, always from the REPO root, exactly as the twin runs it."""
    return harness.run([npx(gate), "tsx", str(GATE), *argv], cwd=ROOT, timeout=600)


def run_fixgen(gate, fixture: pathlib.Path, *argv: str) -> harness.RunResult:
    """The FIXTURE's COPY of the generator, so `--write` can only reach the fixture.

    gen-docs roots itself at its own parent directory (scripts/gen-docs.ts:74), which
    is what makes running the copy a containment boundary and not a convention.
    """
    return harness.run(
        [npx(gate), "tsx", str(fixture / "scripts" / "gen-docs.ts"), *argv],
        cwd=ROOT,
        timeout=600,
    )


def build_fixture(gate, tmp_path: pathlib.Path):
    """(fixture root, document path, provider ids, pristine document bytes, shape).

    Cases A through I in the twin share ONE fixture and restore the document between
    perturbations. They are separate pytest functions here, so each rebuilds -- which
    costs a few seconds and buys the property the twin's `cp "$WORK/doc.orig"` lines
    are working to fake: no case can inherit another's damage.

    `shape` is the derivation's own numbers, printed by case A so a reader can see the
    fixture was non-trivial. A collapse from four figures to two is the failure this
    whole file has spent a day on, and "OK" would not show it.
    """
    fixture = tmp_path / "fixture"
    fixture.mkdir(parents=True, exist_ok=True)
    closure, pathspecs = derive_pathspecs(gate)
    copied = copy_tracked(gate, fixture, pathspecs)
    shape = "%d closure module(s) -> %d derived pathspec(s) -> %d tracked file(s) copied" % (
        len(closure),
        len(pathspecs),
        copied,
    )

    binary = git(gate)
    # The index first: every provider enumerates with `git ls-files`, so a fixture that is not yet a repository makes them THROW rather than report, which reads as a broken gate instead of a broken fixture.
    #
    # `--initial-branch=main`: a bare-or-not fixture whose HEAD points at a branch the
    # runner's init.defaultBranch does not create is the trap test-fetch-depth-safety.sh exists for.
    harness.run([binary, "-C", str(fixture), "init", "-q", "--initial-branch=main", "."])
    staged = harness.run([binary, "-C", str(fixture), "add", "-A", "--", "."], timeout=600)
    if staged.rc != 0:
        gate.log_fail("A. could not stage the fixture: %s" % staged.err)

    # EVERY PROVIDER ENUMERATES THE INDEX, not the disk, so a file that was copied and then not staged is invisible to all of them while sitting right there in the tree. The derivation copies the repository's own `.gitignore` files along with everything
    # else, and a tracked-but-ignored file (git allows one, via `add -f`) would be
    # dropped here in silence. Compare the two counts rather than assuming they agree.
    indexed = harness.run([binary, "-C", str(fixture), "ls-files", "-z"], timeout=600)
    staged_names = {name for name in indexed.out.split("\0") if name}
    if len(staged_names) != copied:
        gate.log_fail(
            "A. copied %d file(s) into the fixture but its index holds %d. A copied file "
            "that is not staged is invisible to every provider. First few unstaged: %s"
            % (
                copied,
                len(staged_names),
                ", ".join(
                    sorted(
                        str(p.relative_to(fixture))
                        for p in fixture.rglob("*")
                        if p.is_file()
                        and ".git/" not in str(p.relative_to(fixture))
                        and str(p.relative_to(fixture)) not in staged_names
                    )[:5]
                )
                or "(nothing on disk is unstaged, so the two counts disagree for another reason)",
            )
        )

    listed = run_fixgen(gate, fixture, "--list")
    if listed.rc != 0:
        explain_fixture_gap(gate, fixture, listed)
        gate.log_error(listed.err)
        gate.log_error(listed.out)
        gate.log_fail(
            "A. a provider scanned the fixture and found nothing, so nothing below "
            "would mean anything"
        )
    # `cut -f1` is TAB-separated, not whitespace-separated.
    providers = [line.split("\t")[0] for line in listed.out.splitlines() if line.strip()]
    if not providers:
        gate.log_fail("A. --list named no provider at all")

    document = fixture / "REGISTRY.md"
    body = ["# fixture registry", ""]
    for provider in providers:
        body += [
            "%s %s -->" % (OPEN_MARKER, provider),
            "<!-- prose the generator must preserve -->",
            "%s -->" % CLOSE_MARKER,
            "",
        ]
    body.append("hand-written tail")
    document.write_text("\n".join(body) + "\n", encoding="utf-8")

    stagedoc = harness.run([binary, "-C", str(fixture), "add", "--", "REGISTRY.md"])
    if stagedoc.rc != 0:
        gate.log_fail("A. could not stage the fixture document: %s" % stagedoc.err)
    written = run_fixgen(gate, fixture, "--write")
    if written.rc != 0:
        explain_fixture_gap(gate, fixture, written)
        gate.log_error(written.err)
        gate.log_fail("A. the generator could not write the fixture's regions")

    return fixture, document, providers, document.read_text(encoding="utf-8"), shape


def first_data_row(gate, document: pathlib.Path) -> tuple[list[str], int]:
    """(lines, index of the first DATA row of the first generated table).

    Found BY SHAPE rather than by content so this survives every rewording of every
    provider: the line after a `|---|` separator.
    """
    lines = document.read_text(encoding="utf-8").split("\n")
    for index, line in enumerate(lines):
        if line.startswith("|---") and index + 1 < len(lines) and lines[index + 1].startswith("| "):
            return lines, index + 1
    gate.log_fail("no generated table row found to perturb")
    raise AssertionError  # unreachable; log_fail raises


def count_lines_containing(text: str, needle: str) -> int:
    return len([line for line in text.splitlines() if needle in line])


def test_a_the_fixture_is_real_every_declared_provider_yields_rows(gate, tmp_path):
    if not GATE.is_file():
        gate.log_fail("scripts/gates/check-doc-region-parity.ts is missing; the gate is gone")
    if not GEN.is_file():
        gate.log_fail("scripts/gen-docs.ts is missing; there is nothing to keep faithful")
    _fixture, document, providers, _pristine, shape = build_fixture(gate, tmp_path)
    body = document.read_text(encoding="utf-8")
    for provider in providers:
        if "%s %s -->" % (OPEN_MARKER, provider) not in body:
            gate.log_fail("A. the fixture document lost the region for provider %s" % provider)
    gate.log_pass(
        "A. fixture carries %d region(s), one per provider, all non-empty (%s)"
        % (len(providers), shape)
    )


def test_b_the_gate_accepts_a_freshly_generated_tree(gate, tmp_path):
    fixture, _document, providers, _pristine, _shape = build_fixture(gate, tmp_path)
    result = run_gate(gate, "--root", str(fixture))
    if result.rc != 0:
        gate.log_error(result.err)
        gate.log_fail("B. the gate red on a tree the generator had just written")
    passes = count_lines_containing(result.out, "  PASS  ")
    if passes <= 0:
        gate.log_fail("B. the gate exited 0 with ZERO pass lines, which is vacuous")
    if "region(s) in" not in result.out:
        gate.log_fail("B. the green never printed its shape")
    for provider in providers:
        if "region `%s` matches" % provider not in result.out:
            gate.log_fail("B. the green never mentions the region for provider %s" % provider)
    gate.log_pass(
        "B. green with %d pass line(s), one per region plus the structural checks" % passes
    )


def test_c_one_perturbed_cell_turns_it_red_and_is_named(gate, tmp_path):
    fixture, document, _providers, _pristine, _shape = build_fixture(gate, tmp_path)
    lines, index = first_data_row(gate, document)
    original_row = lines[index]
    lines[index] = lines[index].replace("| ", "| PERTURBED ", 1)
    document.write_text("\n".join(lines), encoding="utf-8")

    result = run_gate(gate, "--root", str(fixture))
    if result.rc == 0:
        gate.log_fail("C. CONTROL DID NOT FIRE: the gate passed over a perturbed generated row")
    gate.assert_contains(result.err, "REGISTRY.md", "C. the finding never named the file")
    gate.assert_contains(
        result.err,
        "does not match what gen-docs would emit",
        "C. the finding never said what was wrong",
    )
    gate.assert_contains(
        result.err, original_row, "C. the finding never printed the row the tree actually supports"
    )
    gate.log_pass("C. a single perturbed cell is named, with the row it should have been")


def test_d_restoring_the_document_restores_the_green(gate, tmp_path):
    fixture, document, _providers, pristine, _shape = build_fixture(gate, tmp_path)
    lines, index = first_data_row(gate, document)
    lines[index] = lines[index].replace("| ", "| PERTURBED ", 1)
    document.write_text("\n".join(lines), encoding="utf-8")
    if run_gate(gate, "--root", str(fixture)).rc == 0:
        gate.log_fail("D. the perturbation this case restores from did not turn the gate red")

    document.write_text(pristine, encoding="utf-8")
    if document.read_text(encoding="utf-8") != pristine:
        gate.log_fail("D. restore failed; the fixture is not what it was")
    result = run_gate(gate, "--root", str(fixture))
    if result.rc != 0:
        gate.log_fail("D. still red after restoring: %s" % result.err)
    gate.log_pass("D. restored, and the gate is green again")


def test_e_the_same_rows_in_a_different_order_are_reported_as_a_move(gate, tmp_path):
    fixture, document, _providers, _pristine, _shape = build_fixture(gate, tmp_path)
    lines = document.read_text(encoding="utf-8").split("\n")
    swapped = False
    for index, line in enumerate(lines):
        if line.startswith("|---") and index + 2 < len(lines) and lines[index + 2].startswith("| "):
            lines[index + 1], lines[index + 2] = lines[index + 2], lines[index + 1]
            swapped = True
            break
    if not swapped:
        gate.log_fail("E. no table with two data rows found")
    document.write_text("\n".join(lines), encoding="utf-8")

    result = run_gate(gate, "--root", str(fixture))
    if result.rc == 0:
        gate.log_fail("E. CONTROL DID NOT FIRE: a reordered table passed")
    gate.assert_contains(result.err, "MOVED", "E. a reorder was not reported as a move")
    gate.assert_not_contains(
        result.err,
        "the tree has, the doc lacks",
        "E. a reorder was reported as an add plus a remove, which names the wrong defect",
    )
    gate.log_pass("E. a reorder is reported as a move and never as an add plus a remove")


def test_f_a_document_that_loses_its_markers(gate, tmp_path):
    # THE GAP THIS GATE EXISTS TO CLOSE. Only the two marker lines go. Every generated row stays exactly where it was, so a reader sees no difference at all: the table is simply hand-typed from now on.
    fixture, document, _providers, _pristine, _shape = build_fixture(gate, tmp_path)
    lines = document.read_text(encoding="utf-8").split("\n")
    opens = [i for i, line in enumerate(lines) if line.startswith(OPEN_MARKER)]
    closes = [i for i, line in enumerate(lines) if line.startswith(CLOSE_MARKER)]
    if not opens or not closes:
        gate.log_fail("F. the fixture carries no region to strip")
    open_at = opens[0]
    close_at = min(i for i in closes if i > open_at)
    del lines[close_at]
    del lines[open_at]
    document.write_text("\n".join(lines), encoding="utf-8")

    generated = run_fixgen(gate, fixture)
    if generated.rc != 0:
        explain_fixture_gap(gate, fixture, generated)
        gate.log_error(generated.err)
        gate.log_fail(
            "F. gen-docs went red on the stripped document. If it grew this check, this "
            "gate is now a strict subset and should be re-argued rather than kept"
        )
    if not any(line.startswith("ok ") for line in generated.out.splitlines()):
        gate.log_fail("F. gen-docs exited 0 without naming a target, which is a different defect")

    result = run_gate(gate, "--root", str(fixture))
    if result.rc == 0:
        gate.log_fail("F. CONTROL DID NOT FIRE: the gate passed over a provider no region uses")
    gate.assert_contains(
        result.err,
        "used by NO region",
        "F. the finding never said the provider had lost its region",
    )
    gate.log_pass("F. the generator is green over a hand-typed table; this gate names the provider")


def test_g_a_marker_a_human_reads_but_the_parser_refuses(gate, tmp_path):
    fixture, document, _providers, pristine, _shape = build_fixture(gate, tmp_path)
    lines = document.read_text(encoding="utf-8").split("\n")
    indented = False
    for index, line in enumerate(lines):
        if line.startswith(OPEN_MARKER):
            lines[index] = "  " + line
            indented = True
            break
    if not indented:
        gate.log_fail("G. no marker to indent")
    document.write_text("\n".join(lines), encoding="utf-8")

    result = run_gate(gate, "--root", str(fixture))
    if result.rc == 0:
        gate.log_fail("G. CONTROL DID NOT FIRE: an indented marker passed as if it were a region")
    gate.assert_contains(
        result.err, "does not parse as one", "G. the near-miss marker was not reported"
    )

    document.write_text(pristine, encoding="utf-8")
    if run_gate(gate, "--root", str(fixture)).rc != 0:
        gate.log_fail("G. the fixture did not come back to green")
    gate.log_pass("G. an indented marker is reported as a region the generator cannot see")


def test_h_a_root_with_no_markdown_is_a_failure(gate, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir(parents=True, exist_ok=True)
    binary = git(gate)
    harness.run([binary, "-C", str(empty), "init", "-q", "--initial-branch=main", "."])
    (empty / "readme.txt").write_text("not markdown\n", encoding="utf-8")
    harness.run([binary, "-C", str(empty), "add", "--", "readme.txt"])

    result = run_gate(gate, "--root", str(empty))
    if result.rc == 0:
        gate.log_fail(
            "H. CONTROL DID NOT FIRE: the gate was green over a tree with nothing to check"
        )
    gate.assert_contains(result.err, "VACUOUS", "H. the refusal never said why")
    gate.log_pass("H. an empty subject is refused rather than counted as a pass")


def test_i_the_selftest_is_green_and_still_plants_its_defects(gate):
    result = run_gate(gate, "--selftest")
    if result.rc != 0:
        gate.log_error(result.out)
        gate.log_fail("I. the gate's own selftest failed")
    if count_lines_containing(result.out, "  FAIL  ") > 0:
        gate.log_fail("I. --selftest exited 0 with FAIL lines in its output")
    for wanted in SELFTEST_CONTROLS:
        if wanted not in result.out:
            gate.log_fail("I. the selftest no longer runs the control: %s" % wanted)
    gate.log_pass(
        "I. --selftest is green with %d control(s) present"
        % count_lines_containing(result.out, "  PASS  ")
    )
