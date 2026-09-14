"""`rediacc_ci.core.allowlist` against the two readers it consolidates.

WHAT THE PROOF IS. `core/allowlist.py` is a third implementation of a convention
that already has two shared ones plus two hand-rolled copies. "The port looks
right" is not evidence, so this suite runs the REAL bash function and the REAL
TypeScript function over real input and compares BYTES.

THE GOLDEN MECHANISM, and why it is shaped this way.

  1. `goldens/allowlist/corpus/<slug>.list` is a FROZEN BYTE COPY of a real
     allow/block list from this tree. Frozen rather than read live, for two
     reasons. The lists change (`.dead-bash-allowlist` was edited today), and a
     golden recorded against a moving file is a test that reds on somebody
     else's commit. And W4 P2 is scheduled to MOVE these files into
     `.ci/policy/`; a frozen copy keeps this proof valid across that move.

  2. `goldens/allowlist/bash-pairs/<slug>.golden` and
     `goldens/allowlist/ts-records/<slug>.golden` hold the stdout the two
     readers produced over that frozen corpus, byte for byte, under a header
     naming WHICH reader, WHICH command, WHICH source file, and the corpus
     sha256 they were recorded against. The header is metadata; everything
     after the `# ---` line is raw reader output and is what gets compared.

  3. The suite ALSO runs both readers over the LIVE lists and requires
     three-way agreement there. The goldens catch a regression in the port; the
     live differential catches DRIFT in the readers, which a frozen golden
     cannot see. The bash half always runs. The TypeScript half needs `tsx`, and
     the lane that runs this suite (`quality-static`) is `node: false` -- so it
     follows the pattern `test_workflows.py:326` already established: when tsx
     cannot be run, ASSERT ITS ABSENCE rather than skipping, because a skip
     reads exactly like a pass in the count `check_pytest.py` parses.

THE ANTI-VACUITY CONTRACT, because a golden suite is the easiest thing in this
repository to write in a form that cannot fail:

  * BOTH-EMPTY IS A MISMATCH. `_agree()` refuses a comparison in which both
    sides are empty, and `test_both_empty_is_refused_as_a_comparison` proves
    the refusal fires. Seven of the seventeen corpus files legitimately hold
    zero entries; they are still checked, but by a DIFFERENT control
    (`test_every_corpus_entry_line_becomes_exactly_one_entry`) that derives the
    expected count from the corpus text, so a zero there is a proved zero and
    not an assumed one.
  * EVERY COMPARISON IS PERTURBED. For each golden with rows,
    `test_perturbing_*` mutates the frozen corpus in a tempdir and requires the
    comparison to FAIL -- and requires the real bash reader to follow the
    mutation to the same new bytes, so the perturbation is proved to be visible
    to both sides rather than merely to have broken the port.
  * NO HAND-TYPED FLOORS. Every count in here is derived from the corpus or
    from the readers' own tables.

THE DEFECT THIS SUITE FOUND ON THE WAY, AND ITS FIX. `validate_blocker_quality`
in the bash reader used to normalize with `echo "$reason"`, and bash's `echo`
builtin eats a word that is exactly `-n`, `-e` or `-E`. A BLOCKER reason of `-n`
was therefore measured as ZERO characters by bash and TWO by TypeScript. Both
still rejected it, so no gate was wrong, and this suite recorded the divergence
and said the fix belonged in the bash file. It landed on 2026-09-09 with the
collapse: neither shared reader normalizes anything any more, both ask this
module, and `test_the_bash_echo_builtin_defect_is_gone_and_stays_gone` now
asserts the agreement plus a reproduction of the old normalization proving the
control still has something to detect.

WHAT THIS SUITE NO LONGER HAS TO CARRY. It says below that the readers are
separate implementations; since 2026-09-09 they are CLIENTS, which is why every
comparison here still passes and why none of them would notice a phrase present
in a reader's own table and absent from this module's. That direction is
`.ci/rediacc_ci/tests/test_blocker_implementations.py`'s, and it exists because
this file's reason corpus is generated FROM `LOW_EFFORT_PHRASES` at :370 and is
structurally blind to the list being short.

REGENERATING THE GOLDENS: `PYTHONPATH=.ci python3 .ci/rediacc_ci/tests/
test_core_allowlist.py --record` from the repo root, with node_modules present.
It re-freezes the corpus from the live sources and re-runs both readers.
"""

import hashlib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import allowlist
from rediacc_ci.tests import differential as diff

GOLDEN_ROOT = paths.from_root(".ci", "rediacc_ci", "tests", "goldens", "allowlist")
CORPUS_DIR = GOLDEN_ROOT / "corpus"
BASH_PAIRS_DIR = GOLDEN_ROOT / "bash-pairs"
TS_RECORDS_DIR = GOLDEN_ROOT / "ts-records"
REASONS_DIR = GOLDEN_ROOT / "reasons"

HEADER_END = "# ---"

BASH_READER = "bash:.ci/scripts/lib/blocker-validator.sh::parse_blockered_list"
TS_READER = "ts:scripts/lib/blocker-validator.ts::parseBlockeredList"
BASH_REASON_READER = "bash:.ci/scripts/lib/blocker-validator.sh::validate_blocker_quality"
TS_REASON_READER = "ts:scripts/lib/blocker-validator.ts::validateBlockerQuality"

# The file name the reason cases are validated "in". A constant rather than a
# real path because it is only ever interpolated into the message, and pinning
# it keeps the recorded messages independent of where the corpus lives.
REASON_FILE = ".deps-upgrade-blocklist"

# The real lists frozen into the corpus. Every root-level suppression list plus
# the two under .ci/config, which are the ones that go through the shared
# parsers with a `#` comment character. Selection, not invention: the CONTENT of
# each is whatever the tree holds.
SOURCES: tuple[str, ...] = (
    ".actions-upgrade-blocklist",
    ".audit-allowlist",
    ".audit-prod-allowlist",
    ".ci-parity-exempt",
    ".cli-i18n-orphan-allowlist",
    ".dead-bash-allowlist",
    ".deps-upgrade-blocklist",
    ".devcontainer-upgrade-blocklist",
    ".e2e-coverage-allowlist",
    ".embed-assets-upgrade-blocklist",
    ".go-deps-upgrade-blocklist",
    ".plan-housekeeping-allowlist",
    ".profiler-coverage-allowlist",
    ".runner-advice-allowlist",
    ".unverified-download-allowlist",
    ".ci/config/content-quality-allowlist.txt",
    ".ci/config/directive-quotes-allowlist.txt",
)


def _slug(source: str) -> str:
    stem = source.lstrip(".").replace("/", "-")
    return stem.removesuffix(".txt")


SLUGS: list[str] = [_slug(s) for s in SOURCES]


# ---------------------------------------------------------------------------
# The drivers. One process per reader for the WHOLE corpus, not one per file:
# `npx tsx` costs ~0.4s of startup and seventeen of them is a slow suite for no
# extra coverage.
# ---------------------------------------------------------------------------

# The multi-document envelope both drivers emit. Asserted absent from every
# payload by `test_driver_envelope_cannot_collide_with_payload`, so the split is
# not merely assumed to be unambiguous.
DOC_BEGIN = "<<<DOC "
DOC_END = "<<<END"

BASH_PAIRS_DRIVER = r"""
set -uo pipefail
source .ci/scripts/lib/blocker-validator.sh
for f in "$@"; do
    unset _entries _reasons
    declare -A _entries _reasons
    parse_blockered_list "$f" _entries _reasons "#"
    printf '<<<DOC %s\n' "$f"
    for k in "${!_reasons[@]}"; do printf '%s\t%s\n' "$k" "${_reasons[$k]}"; done | LC_ALL=C sort
    printf '<<<END\n'
done
"""

TS_RECORDS_DRIVER = """
import { parseBlockeredList } from '%s/scripts/lib/blocker-validator.ts';
for (const f of process.argv.slice(2)) {
  process.stdout.write('<<<DOC ' + f + String.fromCharCode(10));
  for (const r of parseBlockeredList(f, '#'))
    process.stdout.write(r.line + String.fromCharCode(9) + r.entry
      + String.fromCharCode(9) + r.blocker + String.fromCharCode(10));
  process.stdout.write('<<<END' + String.fromCharCode(10));
}
"""

# Reads TAB-separated `<case-id>\t<reason>` lines and prints
# `<case-id>\t<ok|reject>\t<sha256 of the message>`. The `::error::` prefix that
# `ci_error` adds under CI=true is stripped from line 1 so the digest is over the
# same bytes the TypeScript reader returns.
BASH_REASONS_DRIVER = r"""
set -uo pipefail
source .ci/scripts/lib/blocker-validator.sh
while IFS=$'\t' read -r id reason; do
    if out=$(validate_blocker_quality "$id" "$reason" "$2" 2>&1); then
        verdict=ok
        out=""
    else
        verdict=reject
    fi
    digest=$(printf '%s' "$out" | sed '1s/^::error:://' | sha256sum | cut -d' ' -f1)
    printf '%s\t%s\t%s\n' "$id" "$verdict" "$digest"
done < "$1"
"""

TS_REASONS_DRIVER = """
import fs from 'node:fs';
import crypto from 'node:crypto';
import { validateBlockerQuality } from '%s/scripts/lib/blocker-validator.ts';
const tab = String.fromCharCode(9), nl = String.fromCharCode(10);
for (const line of fs.readFileSync(process.argv[2], 'utf-8').split(nl)) {
  if (!line) continue;
  const cut = line.indexOf(tab);
  const id = line.slice(0, cut), reason = line.slice(cut + 1);
  const r = validateBlockerQuality(id, reason, process.argv[3]);
  const msg = r ? r.message : '';
  const digest = crypto.createHash('sha256').update(msg, 'utf8').digest('hex');
  process.stdout.write(id + tab + (r ? 'reject' : 'ok') + tab + digest + nl);
}
"""


TS_MESSAGES_DRIVER = """
import fs from 'node:fs';
import { validateBlockerQuality } from '%s/scripts/lib/blocker-validator.ts';
const tab = String.fromCharCode(9), nl = String.fromCharCode(10);
const out = {};
for (const line of fs.readFileSync(process.argv[2], 'utf-8').split(nl)) {
  if (!line) continue;
  const cut = line.indexOf(tab);
  const id = line.slice(0, cut), reason = line.slice(cut + 1);
  const r = validateBlockerQuality(id, reason, process.argv[3]);
  if (r && !(r.kind in out))
    out[r.kind] = { entry: id, reason, file: process.argv[3], message: r.message };
}
const sorted = {};
for (const k of Object.keys(out).sort()) sorted[k] = out[k];
process.stdout.write(JSON.stringify(sorted, null, 2) + nl);
"""


def _split_documents(stdout: str) -> dict[str, str]:
    """`<<<DOC <name>` ... `<<<END` blocks -> {name: payload}."""
    docs: dict[str, str] = {}
    name: str | None = None
    body: list[str] = []
    for line in stdout.split("\n"):
        if line.startswith(DOC_BEGIN):
            name, body = line[len(DOC_BEGIN) :], []
        elif line == DOC_END and name is not None:
            docs[name] = "".join(row + "\n" for row in body)
            name = None
        elif name is not None:
            body.append(line)
    return docs


def _tsx_available() -> bool:
    return (pathlib.Path(diff.repo()) / "node_modules" / "tsx").exists()


def _run_tsx(script: str, args: list[str]) -> str | None:
    """`npx --no-install tsx` over a temporary entry point. None when unavailable.

    PID-KEYED entry point, for the reason `test_workflows.py:283` gives: `.ci/
    cache/` is shared by every session in this tree and a fixed name lets two
    concurrent suites truncate each other's script mid-run.
    """
    entry = pathlib.Path(diff.repo()) / ".ci" / "cache" / ("allowlist-diff-%d.mts" % os.getpid())
    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(script % diff.repo(), encoding="utf-8")
        result = subprocess.run(
            ["npx", "--no-install", "tsx", str(entry), *args],
            capture_output=True,
            text=True,
            check=False,
            cwd=diff.repo(),
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        entry.unlink(missing_ok=True)
    return result.stdout if result.returncode == 0 else None


def _run_bash(script: str, args: list[str], *, cwd: str | None = None) -> tuple[int, str, str]:
    """The bash reader, with stdout and stderr kept APART.

    Never merged, for the reason `differential.py` states at length: the shape of
    defect these differentials exist to catch is a stream swap, and `2>&1` hides
    it completely. Every caller below asserts on stderr separately.

    Arguments arrive as POSITIONAL PARAMETERS via a `set --` prelude rather than
    being interpolated into the script text. `differential.bash_streams` runs
    `bash -c <script>` with nothing after it, so there is no other way to give
    the driver a `$1`, and string-substituting a path into a shell script is how
    a directory with a quote in it becomes a syntax error.
    """
    prelude = "set -- %s\n" % " ".join(shlex.quote(a) for a in args)
    return diff.bash_streams(prelude + script, env=diff.env_for(CI="true"), cwd=cwd)


def _bash_pairs(files: list[str], *, cwd: str | None = None) -> tuple[dict[str, str], str]:
    code, out, err = _run_bash(BASH_PAIRS_DRIVER, files, cwd=cwd)
    assert code == 0, "bash pairs driver failed (%d): %s" % (code, err)
    return _split_documents(out), err


def _ts_records(files: list[str]) -> dict[str, str] | None:
    out = _run_tsx(TS_RECORDS_DRIVER, files)
    return None if out is None else _split_documents(out)


# ---------------------------------------------------------------------------
# Golden files: a provenance header, then raw reader bytes.
# ---------------------------------------------------------------------------


def _read_golden(path: pathlib.Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    head, sep, payload = text.partition("\n%s\n" % HEADER_END)
    assert sep, "%s has no '%s' separator; it is not a golden" % (path, HEADER_END)
    meta: dict[str, str] = {}
    for line in head.split("\n"):
        if line.startswith("# ") and ": " in line:
            key, _, value = line[2:].partition(": ")
            meta[key] = value
    return meta, payload


def _write_golden(path: pathlib.Path, meta: dict[str, str], payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# rediacc_ci allowlist golden"]
    lines += ["# %s: %s" % (k, v) for k, v in meta.items()]
    lines += [HEADER_END]
    path.write_text("\n".join(lines) + "\n" + payload, encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _corpus_text(slug: str) -> str:
    return (CORPUS_DIR / ("%s.list" % slug)).read_text(encoding="utf-8")


def _agree(label: str, left: str, right: str) -> None:
    """Byte equality, with BOTH-EMPTY treated as a MISMATCH.

    If both sides are empty the comparison established nothing: an
    implementation that returned "" unconditionally would satisfy it, which is
    exactly the vacuous green this repository hunts. Cases that legitimately
    have no rows are covered by a different control; see the module docstring.
    """
    assert left or right, (
        "%s: both sides are empty, so this comparison proves nothing. An "
        "implementation that returned nothing at all would pass it." % label
    )
    assert left == right, "%s: byte mismatch" % label


# ---------------------------------------------------------------------------
# Reason cases -- derived from the corpus and from the readers' own tables
# ---------------------------------------------------------------------------


def _reason_cases() -> list[tuple[str, str]]:
    """(case-id, reason) for every case the reason goldens cover.

    Three families, none of them invented:
      real-<n>   every distinct reason present in the frozen corpus
      short-<n>  the same reason truncated, which is the too-short arm
      defer-<n>  the same reason with a real LOW_EFFORT_SUBSTRINGS phrase
      phrase-<n> every entry of LOW_EFFORT_PHRASES, which is the readers' own
                 banned list rather than a guess at what it contains
    """
    seen: list[str] = []
    for slug in SLUGS:
        for entry in allowlist.parse_text(_corpus_text(slug)):
            if entry.blocker and entry.blocker not in seen:
                seen.append(entry.blocker)
    cases: list[tuple[str, str]] = []
    for index, reason in enumerate(seen):
        cases.append(("real-%03d" % index, reason))
        cases.append(("short-%03d" % index, reason[:12]))
        cases.append(("defer-%03d" % index, "%s not needed by this change" % reason[:20]))
    for index, phrase in enumerate(allowlist.LOW_EFFORT_PHRASES):
        cases.append(("phrase-%03d" % index, phrase))
        # THE NORMALIZATION ITSELF, which nothing else here exercises. Measured:
        # deleting the trailing-punctuation strip from `normalize_reason` left
        # all 53 cases green, because every real reason is far above the length
        # floor and the step is invisible on a reason that passes. Wrapping each
        # banned phrase in whitespace, upper-casing it and adding a full stop
        # makes all three steps load-bearing: drop any one and the phrase stops
        # matching the table, so the verdict's KIND changes and the digest moves.
        cases.append(("norm-%03d" % index, "  %s.  " % phrase.upper()))
    return cases


def _python_reason_rows(cases: list[tuple[str, str]]) -> str:
    rows = []
    for case_id, reason in cases:
        rejection = allowlist.validate_reason(case_id, reason, REASON_FILE)
        verdict = "reject" if rejection else "ok"
        digest = _sha256(rejection.message if rejection else "")
        rows.append("%s\t%s\t%s\n" % (case_id, verdict, digest))
    return "".join(rows)


def _cases_tsv(cases: list[tuple[str, str]]) -> str:
    """TAB-separated, so the transport is only safe while no reason holds a TAB.

    Asserted rather than hoped: a reason carrying a TAB or a newline would be
    silently split by both drivers and the two halves compared against each
    other's neighbours, which would look like agreement.
    """
    for case_id, reason in cases:
        assert "\t" not in reason, case_id
        assert "\n" not in reason, case_id
    return "".join("%s\t%s\n" % (case_id, reason) for case_id, reason in cases)


# ---------------------------------------------------------------------------
# 1. The frozen goldens. These need neither bash nor node and always run.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", SLUGS)
def test_bash_pairs_golden_matches_the_python_pairs_projection(slug):
    """The bash reader's recorded bytes, reproduced by `render_pairs`."""
    meta, payload = _read_golden(BASH_PAIRS_DIR / ("%s.golden" % slug))
    corpus = _corpus_text(slug)
    assert meta["corpus-sha256"] == _sha256(corpus), (
        "%s: the frozen corpus changed without the golden being re-recorded" % slug
    )
    mine = allowlist.render_pairs(allowlist.parse_text(corpus))
    if not payload and not mine:
        # A legitimately entry-free list. Proved zero, not assumed zero: the
        # entry-line control below derives the count from the corpus text.
        return
    _agree("bash-pairs/%s" % slug, payload, mine)


@pytest.mark.parametrize("slug", SLUGS)
def test_ts_records_golden_matches_the_python_records_projection(slug):
    """The TypeScript reader's recorded bytes, reproduced by `render_records`."""
    meta, payload = _read_golden(TS_RECORDS_DIR / ("%s.golden" % slug))
    corpus = _corpus_text(slug)
    assert meta["corpus-sha256"] == _sha256(corpus), (
        "%s: the frozen corpus changed without the golden being re-recorded" % slug
    )
    mine = allowlist.render_records(allowlist.parse_text(corpus))
    if not payload and not mine:
        return
    _agree("ts-records/%s" % slug, payload, mine)


def test_every_golden_names_its_reader_its_command_and_its_input():
    """Provenance is part of the artifact, not something the reader must recall."""
    for slug in SLUGS:
        for directory, reader in (
            (BASH_PAIRS_DIR, BASH_READER),
            (TS_RECORDS_DIR, TS_READER),
        ):
            meta, _ = _read_golden(directory / ("%s.golden" % slug))
            assert meta["reader"] == reader
            assert meta["source"] in SOURCES
            assert meta["corpus"] == "corpus/%s.list" % slug
            assert meta["comment-char"] == "#"
            assert meta["command"]
            assert len(meta["corpus-sha256"]) == 64


def test_the_goldens_taken_together_are_not_empty():
    """The whole point of `_agree`'s both-empty rule, applied to the CORPUS.

    Seven of the seventeen lists hold no entries, which is fine individually and
    fatal collectively: if every golden were empty the suite above would return
    early seventeen times and report green. The floor is the number of entries
    the frozen corpus actually contains, so it is derived rather than typed.
    """
    total = sum(len(allowlist.parse_text(_corpus_text(slug))) for slug in SLUGS)
    assert total > 0, "the frozen corpus contains no entries at all"
    with_rows = [slug for slug in SLUGS if allowlist.parse_text(_corpus_text(slug))]
    assert len(with_rows) * 2 > len(SLUGS), (
        "most of the corpus is entry-free (%d of %d); the goldens are proving "
        "very little" % (len(with_rows), len(SLUGS))
    )
    payload_rows = sum(
        len(_read_golden(BASH_PAIRS_DIR / ("%s.golden" % slug))[1].splitlines()) for slug in SLUGS
    )
    assert payload_rows == sum(
        len(allowlist.pairs(allowlist.parse_text(_corpus_text(slug)))) for slug in SLUGS
    )
    assert payload_rows > 0


def test_every_corpus_entry_line_becomes_exactly_one_entry():
    """The count is DERIVED from the corpus, so a zero here is a proved zero.

    This is the control that keeps the entry-free files honest. An entry line is
    a line that is neither blank nor a comment, which is the grammar both readers
    implement; if the parser dropped or invented rows, this diverges even for a
    file whose golden payload is empty.
    """
    for slug in SLUGS:
        corpus = _corpus_text(slug)
        expected = [
            line
            for line in (raw.strip() for raw in corpus.split("\n"))
            if line and not line.startswith("#")
        ]
        got = allowlist.parse_text(corpus)
        assert len(got) == len(expected), slug
        for entry, line in zip(got, expected, strict=True):
            assert line.startswith(entry.entry), (slug, line, entry.entry)


def test_driver_envelope_cannot_collide_with_payload():
    """The multi-document split is unambiguous, not assumed to be."""
    for slug in SLUGS:
        for directory in (BASH_PAIRS_DIR, TS_RECORDS_DIR):
            _, payload = _read_golden(directory / ("%s.golden" % slug))
            assert DOC_BEGIN not in payload
            assert DOC_END not in payload
        corpus = _corpus_text(slug)
        assert DOC_BEGIN not in corpus
        assert DOC_END not in corpus


# ---------------------------------------------------------------------------
# 2. The perturbation controls. Every comparison above must FAIL when the
#    input moves, and the real bash reader must follow the mutation.
# ---------------------------------------------------------------------------


def _slugs_with_rows() -> list[str]:
    return [slug for slug in SLUGS if allowlist.parse_text(_corpus_text(slug))]


def test_perturbing_one_entry_breaks_the_bash_pairs_golden_and_bash_follows(tmp_path):
    """Both directions, on every non-empty corpus file.

    The mutation is applied to a COPY. Renaming one entry token must (a) change
    what this module renders, so the golden no longer matches, and (b) change
    what the bash reader renders in the same way -- otherwise the "failure" would
    only prove the port is fragile, not that the comparison is watching anything.
    """
    slugs = _slugs_with_rows()
    assert slugs, "nothing to perturb; the corpus has no entries"
    scratch = tmp_path / "corpus"
    scratch.mkdir()
    mutated_paths = []
    for slug in slugs:
        corpus = _corpus_text(slug)
        original = allowlist.parse_text(corpus)[0]
        lines = corpus.split("\n")
        index = original.line - 1
        lines[index] = lines[index].replace(original.entry, "PERTURBED-" + original.entry, 1)
        target = scratch / ("%s.list" % slug)
        target.write_text("\n".join(lines), encoding="utf-8")
        mutated_paths.append(str(target))

        mine = allowlist.render_pairs(allowlist.parse_file(target))
        _, golden = _read_golden(BASH_PAIRS_DIR / ("%s.golden" % slug))
        assert mine != golden, (
            "%s: renaming an entry did not change the pairs projection, so the "
            "golden comparison is not watching the entries" % slug
        )

    docs, stderr = _bash_pairs(mutated_paths)
    assert stderr == "", "the bash driver wrote to stderr: %r" % stderr
    for slug, path in zip(slugs, mutated_paths, strict=True):
        mine = allowlist.render_pairs(allowlist.parse_file(path))
        _agree("perturbed bash-pairs/%s" % slug, docs[path], mine)
        _, golden = _read_golden(BASH_PAIRS_DIR / ("%s.golden" % slug))
        assert docs[path] != golden, (
            "%s: the bash reader produced the recorded bytes from MUTATED input" % slug
        )


def test_perturbing_one_reason_breaks_the_ts_records_golden(tmp_path):
    """The reason column is compared too, not just the entry column."""
    slugs = [
        slug
        for slug in _slugs_with_rows()
        if any(e.blocker for e in allowlist.parse_text(_corpus_text(slug)))
    ]
    assert slugs, "no corpus file carries a reason; the reason column is untested"
    for slug in slugs:
        corpus = _corpus_text(slug)
        lines = corpus.split("\n")
        # THE REASON THAT IS ACTUALLY IN FORCE, not the first "BLOCKER:" string
        # in the file. `.audit-prod-allowlist` opens with prose that mentions the
        # convention above a blank line, so mutating the first match changed
        # nothing and the control passed while proving nothing -- caught by the
        # control itself on its first run. Scan UP from the first reasoned entry.
        first = next(e for e in allowlist.parse_text(corpus) if e.blocker)
        index = next(i for i in range(first.line - 1, -1, -1) if "BLOCKER:" in lines[i])
        lines[index] = lines[index].replace("BLOCKER:", "BLOCKER: PERTURBED", 1)
        target = tmp_path / ("%s.list" % slug)
        target.write_text("\n".join(lines), encoding="utf-8")
        mine = allowlist.render_records(allowlist.parse_file(target))
        _, golden = _read_golden(TS_RECORDS_DIR / ("%s.golden" % slug))
        assert mine != golden, (
            "%s: editing a BLOCKER reason did not change the records projection" % slug
        )


def test_both_empty_is_refused_as_a_comparison():
    """`_agree` must not accept two empty strings as agreement."""
    with pytest.raises(AssertionError, match="proves nothing"):
        _agree("control", "", "")
    _agree("control", "x\n", "x\n")


# ---------------------------------------------------------------------------
# 3. The live differential -- drift in the readers, which a golden cannot see.
# ---------------------------------------------------------------------------


def _live_source(source: str) -> pathlib.Path | None:
    """Where git tracks the corpus source TODAY, found by basename.

    Not a hardcoded second path. W4 P2 relocates these lists into `.ci/policy/`,
    and a differential that stopped comparing after the move would go quietly
    vacuous rather than red. Resolving through `git ls-files` follows the file
    wherever it is tracked; a file that is genuinely gone returns None and the
    caller counts it.
    """
    base = os.path.basename(source)
    result = subprocess.run(
        ["git", "ls-files", "--", "*%s" % base, base],
        capture_output=True,
        text=True,
        check=False,
        cwd=diff.repo(),
    )
    matches = [line for line in result.stdout.split("\n") if os.path.basename(line) == base]
    if len(matches) != 1:
        return None
    return pathlib.Path(diff.repo()) / matches[0]


def test_bash_reader_and_python_agree_on_the_live_lists():
    """The real `parse_blockered_list`, over the real files, right now."""
    live = {s: _live_source(s) for s in SOURCES}
    present = [s for s, p in live.items() if p is not None]
    assert present, (
        "not one corpus source is tracked any more; this differential has "
        "stopped comparing anything. Re-record the goldens against the new paths."
    )
    docs, stderr = _bash_pairs([str(live[s]) for s in present])
    assert stderr == "", "the bash driver wrote to stderr: %r" % stderr
    compared = 0
    for source in present:
        path = live[source]
        mine = allowlist.render_pairs(allowlist.parse_file(path))
        theirs = docs[str(path)]
        assert theirs == mine, "live bash differential diverged on %s" % source
        if mine:
            compared += 1
    assert compared > 0, "every live list is empty; the differential proved nothing"


def test_typescript_reader_and_python_agree_on_the_live_lists():
    """The real `parseBlockeredList`, or a proved absence of tsx.

    NOT A SKIP. A skipped test is indistinguishable from a passing one in the
    count `check_pytest.py` reconciles, and the lane that runs this suite is
    `node: false`, so the absent branch would be the only one CI ever took. If
    tsx IS installed and the driver still failed, that is a real failure.
    """
    live = {s: _live_source(s) for s in SOURCES}
    present = [s for s, p in live.items() if p is not None]
    assert present
    docs = _ts_records([str(live[s]) for s in present])
    if docs is None:
        assert not _tsx_available(), (
            "tsx IS installed but scripts/lib/blocker-validator.ts could not be "
            "run; the differential is broken rather than unavailable"
        )
        return
    compared = 0
    for source in present:
        path = live[source]
        mine = allowlist.render_records(allowlist.parse_file(path))
        assert docs[str(path)] == mine, "live TypeScript differential diverged on %s" % source
        if mine:
            compared += 1
    assert compared > 0, "every live list is empty; the differential proved nothing"


# ---------------------------------------------------------------------------
# 4. The BLOCKER reason contract, three ways.
# ---------------------------------------------------------------------------


def test_reason_verdicts_golden_matches_python():
    """The recorded TypeScript verdicts and message digests, reproduced here."""
    cases = _reason_cases()
    assert cases
    meta, payload = _read_golden(REASONS_DIR / "verdicts.golden")
    assert meta["reader"] == TS_REASON_READER
    assert meta["file"] == REASON_FILE
    _agree("reasons/verdicts", payload, _python_reason_rows(cases))
    kinds = {row.split("\t")[1] for row in payload.splitlines()}
    assert kinds == {"ok", "reject"}, (
        "the reason corpus does not exercise both verdicts: %s" % sorted(kinds)
    )


def test_reason_messages_golden_matches_python_byte_for_byte():
    """The full text of one message per rejection kind, not just its digest."""
    _, payload = _read_golden(REASONS_DIR / "messages.golden")
    recorded = json.loads(payload)
    assert set(recorded) == {"low-effort", "deferral", "too-short"}, sorted(recorded)
    for kind, case in recorded.items():
        rejection = allowlist.validate_reason(case["entry"], case["reason"], case["file"])
        assert rejection is not None, kind
        assert rejection.kind == kind
        _agree("reasons/messages/%s" % kind, case["message"], rejection.message)


def test_bash_reason_validator_agrees_with_python_on_every_case(tmp_path):
    """The real `validate_blocker_quality`, driven over the same corpus.

    Compared by sha256 of the message with `ci_error`'s `::error::` prefix
    stripped, so a difference in a single character of any of the four output
    lines is a failure -- not merely a difference in the accept/reject verdict.
    """
    cases = [case for case in _reason_cases() if case[1] != "-n"]
    assert cases
    # tmp_path, not `.ci/cache/`: a run killed mid-test leaves nothing behind in
    # the working tree. Observed once this session, when a 120s harness timeout
    # killed the suite and the PID-keyed TSV survived in the repository.
    tsv = tmp_path / "reasons.tsv"
    tsv.write_text(_cases_tsv(cases), encoding="utf-8")
    code, out, err = _run_bash(BASH_REASONS_DRIVER, [str(tsv), REASON_FILE])
    assert code == 0, "bash reasons driver failed: %s" % err
    assert err == "", "the bash reasons driver wrote to stderr: %r" % err
    _agree("bash reason verdicts", out, _python_reason_rows(cases))


def test_the_bash_echo_builtin_defect_is_gone_and_stays_gone(tmp_path):
    """THE DEFECT, AND THE COLLAPSE THAT REMOVED IT.

    `echo "-n"` in bash prints NOTHING, so `validate_blocker_quality` used to
    normalize a two-character reason to zero characters and print a different
    message from the other two readers. This suite recorded that divergence
    rather than working around it, and said in as many words that the fix
    belonged in the bash file and that this control should be retired when it
    landed. It landed on 2026-09-09: the bash reader no longer normalizes
    anything, it asks `rediacc_ci.core.allowlist`, so `echo` is not on the path.

    THE CONTROL IS RETIRED BY INVERSION, NOT BY DELETION. What was "the two
    disagree, and here is the digest that proves it" is now "the two agree, and
    here is the same digest on both sides", plus a reproduction of the old
    normalization showing the driver WOULD still see the divergence if it came
    back. Deleting it would have removed the only test in this repository that
    exercises a reason bash's `echo` can eat.
    """
    tsv = tmp_path / "dashn.tsv"
    tsv.write_text("dashn\t-n\n", encoding="utf-8")
    code, out, err = _run_bash(BASH_REASONS_DRIVER, [str(tsv), REASON_FILE])
    assert code == 0, err
    verdict, digest = out.strip().split("\t")[1:]
    assert verdict == "reject"

    mine = allowlist.validate_reason("dashn", "-n", REASON_FILE)
    assert mine is not None
    assert mine.kind == "too-short"
    assert "(2 chars, minimum 30)" in mine.message
    assert _sha256(mine.message) == digest, (
        "bash and the canonical disagree on a bare '-n' reason again. The reader "
        "used to normalize with the `echo` builtin, which eats `-n`, `-e` and `-E`; "
        "if that shape has returned to .ci/scripts/lib/blocker-validator.sh it is "
        "the same defect, not a new one."
    )

    # The message the bash reader actually prints, end to end, through ci_error.
    printed = _run_bash(
        "source .ci/scripts/lib/blocker-validator.sh\n"
        'validate_blocker_quality dashn "-n" "%s" || true\n' % REASON_FILE,
        [],
    )[1]
    assert "(2 chars, minimum 30)" in printed, printed
    assert "(0 chars, minimum 30)" not in printed, printed

    # THE CONTROL, so this is not a test that would pass with the differential
    # broken: reproduce the OLD normalization and show it still yields zero, i.e.
    # the divergence is genuinely absent rather than merely unmeasured.
    old_normalization = _run_bash(
        'n=$(echo "-n" | tr "[:upper:]" "[:lower:]" | '
        "sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/[.!?,;:]*$//')\n"
        'printf "%s\\n" "${#n}"\n',
        [],
    )[1].strip()
    assert old_normalization == "0", (
        "the `echo` builtin no longer eats `-n` on this bash, so this control is "
        "measuring nothing; got %r" % old_normalization
    )


def test_entries_with_no_reason_are_reported_not_silently_accepted():
    """The reportable population, taken from a real list that HAS one.

    `.ci/config/content-quality-allowlist.txt` carries entries under plain
    comments rather than BLOCKER lines, so it is the tree's own example of the
    case the module must not swallow. The expected count is derived from the
    file, never typed.
    """
    entries = allowlist.parse_text(_corpus_text("ci-config-content-quality-allowlist"))
    unreasoned = allowlist.unreasoned(entries)
    assert unreasoned, "the frozen corpus no longer contains an unreasoned entry"
    assert len(unreasoned) == len([e for e in entries if not e.blocker])
    failures = allowlist.verify(entries, "content-quality-allowlist.txt")
    assert len(failures) == len(entries)
    for entry in unreasoned:
        assert any("entry %s is missing" % entry.entry in f for f in failures)


def test_real_reasons_from_the_corpus_pass_and_truncations_do_not():
    """Both directions on the quality rules, over corpus data only."""
    real = [c for c in _reason_cases() if c[0].startswith("real-")]
    short = [c for c in _reason_cases() if c[0].startswith("short-")]
    defer = [c for c in _reason_cases() if c[0].startswith("defer-")]
    assert real
    assert short
    assert defer
    assert all(allowlist.validate_reason(i, r, REASON_FILE) is None for i, r in real), (
        "a reason that is live in the tree today is rejected by this validator"
    )
    assert all(allowlist.validate_reason(i, r, REASON_FILE) is not None for i, r in short)
    kinds = {allowlist.validate_reason(i, r, REASON_FILE).kind for i, r in defer}
    assert kinds == {"deferral"}, sorted(kinds)


def test_every_banned_phrase_is_actually_banned():
    """Set-based, over the readers' own table rather than a sample of it."""
    rejected = {
        phrase
        for phrase in allowlist.LOW_EFFORT_PHRASES
        if allowlist.validate_reason("x", phrase, REASON_FILE) is not None
    }
    assert rejected == set(allowlist.LOW_EFFORT_PHRASES)
    kinds = {
        allowlist.validate_reason("x", phrase, REASON_FILE).kind
        for phrase in allowlist.LOW_EFFORT_PHRASES
    }
    assert kinds == {"low-effort"}, (
        "some banned phrases are only caught by the length floor, so removing "
        "them from the table would not be noticed: %s" % sorted(kinds)
    )


# ---------------------------------------------------------------------------
# 5. Absence, and cwd. The two traps the readers walk into.
# ---------------------------------------------------------------------------


def test_a_missing_list_is_an_error_here_and_silence_in_both_readers(tmp_path):
    """The whole reason this module exists rather than a fourth thin wrapper."""
    absent = tmp_path / "no-such-allowlist"
    with pytest.raises(allowlist.ListNotFoundError):
        allowlist.parse_file(absent)
    assert allowlist.parse_file(absent, missing_ok=True) == []

    docs, _ = _bash_pairs([str(absent)])
    assert docs[str(absent)] == "", (
        "the bash reader no longer returns silently for a missing file; this "
        "control describes a divergence that has been fixed"
    )
    ts = _ts_records([str(absent)])
    if ts is not None:
        assert ts[str(absent)] == ""
    else:
        assert not _tsx_available()


def test_the_module_entry_point_separates_absent_from_dirty(tmp_path):
    """`python3 -m rediacc_ci.core.allowlist` exit codes, run for real.

    2 for "you pointed me at nothing" and 1 for "the list is dirty". Collapsing
    them is precisely how an absent list becomes a clean bill of health.
    """
    dirty = tmp_path / "dirty.list"
    dirty.write_text("# not a blocker comment\nsome-entry\n", encoding="utf-8")

    absent = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.allowlist", "verify", str(tmp_path / "nope")],
        capture_output=True,
        text=True,
        check=False,
        cwd=diff.repo(),
        env={**os.environ, "PYTHONPATH": str(paths.ci_dir())},
    )
    assert absent.returncode == 2
    assert absent.stdout == ""
    assert "missing_ok" in absent.stderr

    found = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.allowlist", "verify", str(dirty)],
        capture_output=True,
        text=True,
        check=False,
        cwd=diff.repo(),
        env={**os.environ, "PYTHONPATH": str(paths.ci_dir())},
    )
    assert found.returncode == 1
    assert "is missing a '# BLOCKER: <reason>' comment" in found.stdout
    assert found.stderr == ""


def test_load_resolves_from_the_repo_root_while_the_bash_reader_needs_cwd(tmp_path):
    """`audit.sh:327` passes a bare relative name; from anywhere else it finds nothing."""
    source = _live_source(".deps-upgrade-blocklist")
    assert source is not None
    name = str(source.relative_to(paths.repo_root()))

    from_root = allowlist.load(name)
    assert from_root, "the live list is empty; this control proves nothing"

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert allowlist.load(name) == from_root
        with pytest.raises(allowlist.ListNotFoundError):
            allowlist.parse_file(name)
    finally:
        os.chdir(cwd)

    docs, _ = _bash_pairs([name], cwd=str(tmp_path))
    assert docs[name] == "", (
        "the bash reader found the list from an unrelated cwd; the relative-path "
        "trap this control describes no longer exists"
    )
    docs, _ = _bash_pairs([name])
    assert docs[name] == allowlist.render_pairs(from_root)


# ---------------------------------------------------------------------------
# The recorder. Not part of the suite; see the module docstring.
# ---------------------------------------------------------------------------


def _record() -> int:
    root = pathlib.Path(diff.repo())
    for directory in (CORPUS_DIR, BASH_PAIRS_DIR, TS_RECORDS_DIR, REASONS_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    # THROUGH `_live_source`, NOT `root / source`, and this is a FIX rather than a
    # tidy-up. `SOURCES` names each list at its historical repo-root path, and
    # `dee3ade8b` moved all fifteen into `.ci/policy/`. The live differential above
    # already resolves by basename through `git ls-files` and kept working; only
    # this recorder was left on the hardcoded path, so `--record` died on its first
    # file with `FileNotFoundError` on `.ci/policy/.actions-upgrade-blocklist`, and every golden
    # became unrefreshable. That is not a cosmetic outage: eight corpora were
    # legitimately refreshed afterwards and their `corpus-sha256` headers could not
    # follow, which is what `test_ts_records_golden_matches_the_python_records_projection`
    # was reporting.
    #
    # `SOURCES` is deliberately NOT path-qualified to fix this. `_slug` derives every
    # golden's FILENAME from the source string, so adding `.ci/policy/` would rename
    # all seventeen goldens -- a re-baseline of the whole suite wearing the costume
    # of a one-line fix.
    frozen: list[str] = []
    missing: list[str] = []
    for source in SOURCES:
        live = _live_source(source)
        if live is None:
            missing.append(source)
            continue
        target = CORPUS_DIR / ("%s.list" % _slug(source))
        shutil.copyfile(live, target)
        frozen.append(str(target))
    if missing:
        # LOUD, AND WITHOUT WRITING ANYTHING. A partial re-record would leave the
        # corpus half old and half new with no marker saying which, and `None` handed
        # to `copyfile` raises a TypeError that names neither the list nor the move.
        print(
            "cannot record: %d corpus source(s) are not tracked anywhere under any\n"
            "  basename, so `git ls-files` cannot find where they moved to:\n    %s\n"
            "  Point SOURCES at a list that still exists, or drop the entry. Do NOT\n"
            "  path-qualify SOURCES to make this pass: _slug would rename the goldens."
            % (len(missing), "\n    ".join(missing)),
            file=sys.stderr,
        )
        return 1

    bash_docs, _ = _bash_pairs(frozen)
    ts_docs = _ts_records(frozen)
    if ts_docs is None:
        print("cannot record: npx tsx is not runnable here", file=sys.stderr)
        return 1

    for source in SOURCES:
        slug = _slug(source)
        path = str(CORPUS_DIR / ("%s.list" % slug))
        digest = _sha256(_corpus_text(slug))
        _write_golden(
            BASH_PAIRS_DIR / ("%s.golden" % slug),
            {
                "reader": BASH_READER,
                "command": "parse_blockered_list <corpus> A B '#'; "
                "for k in ${!B[@]}; printf '%s\\t%s\\n'; LC_ALL=C sort",
                "projection": "pairs",
                "source": source,
                "corpus": "corpus/%s.list" % slug,
                "comment-char": "#",
                "corpus-sha256": digest,
            },
            bash_docs[path],
        )
        _write_golden(
            TS_RECORDS_DIR / ("%s.golden" % slug),
            {
                "reader": TS_READER,
                "command": "parseBlockeredList(<corpus>, '#'); "
                "printf '%s\\t%s\\t%s\\n' line entry blocker",
                "projection": "records",
                "source": source,
                "corpus": "corpus/%s.list" % slug,
                "comment-char": "#",
                "corpus-sha256": digest,
            },
            ts_docs[path],
        )

    cases = _reason_cases()
    tsv = root / ".ci" / "cache" / ("allowlist-record-%d.tsv" % os.getpid())
    tsv.parent.mkdir(parents=True, exist_ok=True)
    tsv.write_text(_cases_tsv(cases), encoding="utf-8")
    try:
        verdicts = _run_tsx(TS_REASONS_DRIVER, [str(tsv), REASON_FILE])
    finally:
        tsv.unlink(missing_ok=True)
    if verdicts is None:
        print("cannot record reason verdicts: npx tsx failed", file=sys.stderr)
        return 1
    _write_golden(
        REASONS_DIR / "verdicts.golden",
        {
            "reader": TS_REASON_READER,
            "command": "validateBlockerQuality(id, reason, file); "
            "printf '%s\\t%s\\t%s\\n' id verdict sha256(message)",
            "projection": "verdicts",
            "source": "every distinct reason in corpus/, its truncation, a "
            "deferral phrase appended, and LOW_EFFORT_PHRASES",
            "file": REASON_FILE,
            "cases": str(len(cases)),
        },
        verdicts,
    )

    # RECORDED FROM THE TYPESCRIPT READER, not from `allowlist.validate_reason`.
    # A golden written by the implementation under test proves that the
    # implementation agrees with itself, which is the shape of vacuity this
    # whole suite exists to avoid.
    tsv.write_text(_cases_tsv(cases), encoding="utf-8")
    try:
        messages = _run_tsx(TS_MESSAGES_DRIVER, [str(tsv), REASON_FILE])
    finally:
        tsv.unlink(missing_ok=True)
    if messages is None:
        print("cannot record reason messages: npx tsx failed", file=sys.stderr)
        return 1
    _write_golden(
        REASONS_DIR / "messages.golden",
        {
            "reader": TS_REASON_READER,
            "command": "validateBlockerQuality(id, reason, file).message, verbatim",
            "projection": "messages",
            "source": "the first case of each rejection kind in verdicts.golden's corpus",
            "file": REASON_FILE,
        },
        messages,
    )

    print("recorded %d corpus files and %d reason cases" % (len(SOURCES), len(cases)))
    return 0


if __name__ == "__main__":
    sys.exit(_record() if "--record" in sys.argv[1:] else 2)
