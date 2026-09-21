"""W4 P3d -- the vendored BLOCKER validator's divergence is DERIVED, not pinned.

WHAT WAS ALREADY TRUE BEFORE THIS FILE, so a reader can see what is new.

`.ci/breakpoint/lib/breakpoint-blocker.sh` is a deliberately reduced copy of the one BLOCKER convention, vendored into a directory invariant 8 says nobody writes to. Two instruments already watch it:

  * `.ci/rediacc_ci/tests/gates/test_gate_breakpoint_portability.py` `check_subset`
    asserts `BREAKPOINT_LOW_EFFORT_BLOCKERS` is contained in the bash canonical's
    `LOW_EFFORT_BLOCKER_PATTERNS`, with a planted-defect control and a
    second-read guard against a truncated extractor. Containment of the PHRASE
    list is therefore settled, and this gate does not re-assert it.
  * `.ci/scripts/test/gates/test-blocker-golden-corpus.sh` runs all three live
    implementations over a 20-case corpus and pins the vendored copy as
    differing on exactly FIVE of them.

THE GAP IS THE WORD "EXACTLY FIVE". It is a magic number. Nothing says WHICH five, nothing says why, and nothing notices when the number stays five while the membership changes -- the composition trap, one row in and one row out. Worse, two of the five are a different KIND of difference from the other three and the corpus cannot tell them apart: three are two implementations
rejecting the same reason for different stated reasons, and two are the vendored copy ACCEPTING a reason the canonical one REFUSES. Only the second kind is a hole in a suppression gate.

SO THE CLAIM HERE IS ABOUT THE LISTS, AND THE CORPUS IS ITS CONSEQUENCE:

  1. `bp_substrings == the empty set`. The canonical validator has a SECOND,
     substring-matched list; the vendored copy has no such list and no
     substring-matching operator at all. This is not asserted anywhere else.
  2. `bp_min_length == canonical_min_length`.
  3. Every recorded divergence is ATTRIBUTABLE to (1) or to a phrase the
     canonical list carries and the vendored one drops. An unattributable
     divergence means the model in this file no longer describes either
     implementation, which is a louder and more useful failure than a count
     moving from five to six.
  4. The two attributions have the DIRECTIONS stated above, and both buckets are
     non-empty. A derivation that explains nothing because one class is empty is
     not a derivation.

AND THE GATE'S OWN INNOCENCE, because invariant 8 is the reason this is a separate instrument rather than an addition to a test that already sources the vendored file. `.ci/breakpoint/` is read and hashed here, never written: sha256 is taken BEFORE and AFTER the body, and both are compared to the row in `.ci/breakpoint/MANIFEST.sha256`. Three separate claims, deliberately:

  before == manifest   the copy this gate reasoned about is the vendored one, so
                       its verdict is about the artifact and not about somebody's
                       edit-in-progress. A mismatch is a REFUSAL, not a finding:
                       drift is `check-breakpoint-drift.sh`'s subject and this
                       gate has nothing useful to say about a file that already
                       diverged.
  after == before      this gate did not write. A gate that policed a read-only
                       tree by mutating it would be the defect it exists for.
  after == manifest    stated separately rather than inferred, because inferring
                       it costs a line and assumes the manifest did not change
                       under us.

Nothing here mutates anything. The perturbation controls in `selftest()` build their own temporary copies and never name the real directory as a write target.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.core import allowlist

VENDORED_REL = ".ci/breakpoint/lib/breakpoint-blocker.sh"
MANIFEST_REL = ".ci/breakpoint/MANIFEST.sha256"
MANIFEST_ROW = "lib/breakpoint-blocker.sh"
CORPUS_REL = ".ci/scripts/test/gates/test-blocker-golden-corpus.sh"

# The tree under judgement, resolved at CALL time. Without this seam every refusal in `run()` is unreachable from a PROCESS -- the module's own controls could reach them by argument, and the gate test could only ever watch the gate succeed. A gate nobody has seen fail through its real entry point is the exact shape this estate keeps getting caught by.
ROOT_ENV = "VENDORED_BLOCKER_ROOT"

PHRASE_ARRAY = "BREAKPOINT_LOW_EFFORT_BLOCKERS"
MIN_LENGTH_NAME = "BREAKPOINT_BLOCKER_MIN_LENGTH"

# The extractor-truncation floor `check_subset` in test_gate_breakpoint_portability.py carries, for the reason it records: on 2026-07-31 a short read under the parallel runner returned a canonical list missing one phrase and the subset check blamed the vendored copy. A parse below this is an extractor failure and says so, rather than being reported as a list that changed.
MIN_PARSED_PHRASES = 30

# `[[ "$x" == *"$p"* ]]`, the only way bash does the substring match the canonical
# validator's second list needs. Written as its own constant so the refusal can quote what it looked for.
SUBSTRING_MATCH_RE = re.compile(r'==\s*\*"\$')


class RefusalError(Exception):
    """The gate cannot see its subject, so a green here would mean nothing."""


# --------------------------------------------------------------------------- reading the vendored copy, without writing to it ---------------------------------------------------------------------------


def sha256_of(path: pathlib.Path) -> str:
    """The file's digest, in the spelling `MANIFEST.sha256` uses."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_digest(manifest: pathlib.Path, row: str) -> str:
    """The pinned digest for one row, or a refusal naming what was missing.

    A MISSING MANIFEST IS THE CHEAPEST FREE PASS AVAILABLE, which is why it is a refusal rather than a skip: `test_gate_breakpoint_portability.py` already records that deleting `MANIFEST.sha256` is the least-effort way to make a diverged copy look clean, and a gate that shrugged at an absent pin would hand that back.
    """
    if not manifest.is_file():
        raise RefusalError(
            "%s does not exist, so there is no pinned digest to compare the vendored "
            "validator against. Deleting the manifest must never be the way past a gate."
            % MANIFEST_REL
        )
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1] == row:
            return parts[0]
    raise RefusalError(
        "%s carries no row for %r, so the vendored validator is unpinned and this gate "
        "cannot say which bytes it read" % (MANIFEST_REL, row)
    )


def parse_array(source: str, name: str) -> list[str]:
    """Every double-quoted member of `readonly <name>=( ... )`, in order.

    Comments are stripped FIRST. The vendored file's array is preceded and interleaved with prose that quotes phrases (`the npm-audit specific ones ("no upstream fix", "dev dep") are dropped`), and a naive quote scan would read those back as members and report the list as a SUPERSET of itself.
    """
    match = re.search(
        r"^readonly\s+%s=\(\s*(.*?)^\)" % re.escape(name), source, re.DOTALL | re.MULTILINE
    )
    if match is None:
        return []
    body = re.sub(r"#[^\n]*", "", match.group(1))
    return re.findall(r'"([^"]*)"', body)


def parse_min_length(source: str, name: str) -> int | None:
    match = re.search(r"^readonly\s+%s=(\d+)\s*$" % re.escape(name), source, re.MULTILINE)
    return int(match.group(1)) if match else None


def array_names(source: str) -> list[str]:
    """Every `readonly NAME=(` array in the file. The census the substring claim needs.

    Stated as "which arrays exist" rather than "is there an array called SUBSTRINGS", because the claim being defended is that the vendored copy has ONE list. A second list under any name is the thing that would make the derivation below wrong, whatever it is called.
    """
    return re.findall(r"^readonly\s+(\w+)=\(", source, re.MULTILINE)


# --------------------------------------------------------------------------- the corpus, read as data ---------------------------------------------------------------------------


class Case:
    """One golden-corpus row: the reason and the three recorded verdicts."""

    __slots__ = ("bp", "case_id", "reason", "sh", "ts")

    def __init__(self, case_id: str, reason: str, ts: str, sh: str, bp: str) -> None:
        self.case_id = case_id
        self.reason = reason
        self.ts = ts
        self.sh = sh
        self.bp = bp

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return "Case(%r, sh=%r, bp=%r)" % (self.case_id, self.sh, self.bp)


def parse_corpus(source: str) -> list[Case]:
    """The `<id>|<reason>|<ts>|<sh>|<bp>` heredoc, as rows.

    THE HEREDOC IS THE RECORD AND THE PARSE MUST NOT BE CLEVER. The corpus gate states in its own header that no field may contain a `|`, so a five-way split is exact; a row that does not split into five is returned to the caller as a refusal rather than skipped, because a silently dropped row is a case this gate would then claim to have derived.
    """
    # ANCHORED ON THE VARIABLE NAME AND TOLERANT OF WHAT FOLLOWS THE REDIRECT. The first draft matched `<<'EOF'\n` and found nothing, because the real line is `read -r -d '' CORPUS <<'EOF' || true` -- the `|| true` sits between the redirect and the newline. That parsed to zero rows, which the refusal caught and a laxer gate would have reported as a clean run over an empty corpus.
    match = re.search(r"CORPUS\s*<<'EOF'[^\n]*\n(.*?)\nEOF\n", source, re.DOTALL)
    if match is None:
        return []
    rows: list[Case] = []
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 5:
            raise RefusalError(
                "corpus row %r does not split into five fields; the record this gate "
                "derives from is not the shape %s documents" % (line, CORPUS_REL)
            )
        rows.append(Case(*fields))
    return rows


# --------------------------------------------------------------------------- the two models ---------------------------------------------------------------------------


def canonical_verdict(reason: str) -> str:
    """What the ONE validator says, from the canonical implementation itself.

    This calls `rediacc_ci.core.allowlist`, it does not re-implement it. The corpus's `sh` column was recorded by driving the live bash reader, so comparing the two is a real cross-check between the canonical module and the behaviour the corpus froze, not a tautology.
    """
    rejection = allowlist.validate_reason("entry", reason, "corpus")
    return "accept" if rejection is None else "reject:%s" % rejection.kind


def vendored_verdict(reason: str, phrases: frozenset[str], min_length: int) -> str:
    """What the vendored copy says, modelled from the two rules it has.

    THE MODEL IS FOUR LINES BECAUSE THE VENDORED FILE IS FOUR LINES OF LOGIC:
    normalize, exact-match the one phrase list, then the length floor. It is a MODEL and not an import (the original is bash and invariant 8 forbids sourcing it from here), so its fidelity is not assumed: `run()` asserts it reproduces the recorded `bp` column for every corpus row, and a model that stopped describing the file fails there before any derivation is reported.
    """
    normalized = allowlist.normalize_reason(reason)
    if normalized in phrases:
        return "reject:low-effort"
    if len(normalized) < min_length:
        return "reject:too-short"
    return "accept"


# --------------------------------------------------------------------------- the scan ---------------------------------------------------------------------------


class Shape:
    """What one run measured. Printed on success so a collapse is visible."""

    def __init__(self) -> None:
        self.canonical_phrases = 0
        self.canonical_substrings = 0
        self.vendored_phrases = 0
        self.dropped_phrases = 0
        self.vendored_arrays: list[str] = []
        self.min_length = 0
        self.cases = 0
        self.divergences = 0
        self.by_phrase: list[str] = []
        self.by_substring: list[str] = []
        self.digest = ""


def run(root: pathlib.Path | None = None) -> tuple[list[str], Shape]:
    """Every claim, against one root. Raises `RefusalError` when it cannot see them."""
    override = os.environ.get(ROOT_ENV)
    base = root or (pathlib.Path(override) if override else paths.repo_root())
    vendored = base / VENDORED_REL
    corpus_file = base / CORPUS_REL
    shape = Shape()

    if not vendored.is_file():
        raise RefusalError(
            "%s does not exist; there is no vendored copy to reason about" % VENDORED_REL
        )
    if not corpus_file.is_file():
        raise RefusalError(
            "%s does not exist, so the recorded divergence this gate derives is not in the tree"
            % CORPUS_REL
        )

    pinned = manifest_digest(base / MANIFEST_REL, MANIFEST_ROW)
    before = sha256_of(vendored)
    if before != pinned:
        raise RefusalError(
            "%s hashes %s but %s pins %s. The vendored copy has already drifted, which is "
            "check-breakpoint-drift.sh's subject; nothing this gate could say about a "
            "diverged file would be about the artifact it names."
            % (VENDORED_REL, before[:12], MANIFEST_REL, pinned[:12])
        )
    shape.digest = before

    source = vendored.read_text(encoding="utf-8")
    phrases = parse_array(source, PHRASE_ARRAY)
    min_length = parse_min_length(source, MIN_LENGTH_NAME)
    shape.vendored_arrays = array_names(source)

    if len(phrases) < MIN_PARSED_PHRASES:
        raise RefusalError(
            "only %d phrase(s) parsed out of %s in %s; that is an extractor or a short "
            "read, not a list that shrank, and blaming the list would be a false accusation"
            % (len(phrases), PHRASE_ARRAY, VENDORED_REL)
        )
    if min_length is None:
        raise RefusalError(
            "%s is not readable out of %s, so the length half of the model is unknown -- "
            "and unknown is a failure here, not a pass" % (MIN_LENGTH_NAME, VENDORED_REL)
        )

    canonical_phrases = frozenset(allowlist.LOW_EFFORT_PHRASES)
    canonical_substrings = tuple(allowlist.LOW_EFFORT_SUBSTRINGS)
    if len(canonical_phrases) < MIN_PARSED_PHRASES:
        raise RefusalError(
            "the canonical list in rediacc_ci.core.allowlist holds only %d phrase(s); the "
            "oracle is broken, so every comparison below would be against nothing"
            % len(canonical_phrases)
        )
    if not canonical_substrings:
        raise RefusalError(
            "the canonical substring list is EMPTY, so the whole substring half of this "
            "derivation would be vacuously satisfied by any vendored copy"
        )

    vendored_set = frozenset(phrases)
    shape.canonical_phrases = len(canonical_phrases)
    shape.canonical_substrings = len(canonical_substrings)
    shape.vendored_phrases = len(vendored_set)
    shape.dropped_phrases = len(canonical_phrases - vendored_set)
    shape.min_length = min_length

    findings: list[str] = []

    # -- claim 1: the vendored copy has no substring list, by two independent reads.
    extra_arrays = [n for n in shape.vendored_arrays if n != PHRASE_ARRAY]
    if extra_arrays:
        findings.append(
            "%s now declares %d array(s) besides %s (%s). The derivation below assumes ONE "
            "list; a second one changes what the vendored copy rejects and has to be modelled "
            "before this gate can speak."
            % (VENDORED_REL, len(extra_arrays), PHRASE_ARRAY, ", ".join(extra_arrays))
        )
    substring_sites = [
        i + 1 for i, line in enumerate(source.splitlines()) if SUBSTRING_MATCH_RE.search(line)
    ]
    if substring_sites:
        findings.append(
            "%s now substring-matches at line(s) %s. `bp_substrings == the empty set` is the "
            "claim two of the recorded corpus divergences are derived from; it no longer holds, "
            "so re-derive them instead of repinning the count."
            % (VENDORED_REL, ", ".join(str(n) for n in substring_sites))
        )

    # -- claim 2: the floors agree.
    if min_length != allowlist.MIN_REASON_LENGTH:
        findings.append(
            "%s is %d in %s and %d in the canonical list. The length floor is the vendored "
            "copy's ONLY other rule, so a difference here changes verdicts the corpus does "
            "not cover." % (MIN_LENGTH_NAME, min_length, VENDORED_REL, allowlist.MIN_REASON_LENGTH)
        )

    # -- claim 3: both models still describe the recorded corpus.
    cases = parse_corpus(corpus_file.read_text(encoding="utf-8"))
    if not cases:
        raise RefusalError(
            "no corpus row parsed out of %s; the record this gate derives from is absent "
            "and a green would mean nothing" % CORPUS_REL
        )
    shape.cases = len(cases)

    for case in cases:
        predicted = canonical_verdict(case.reason)
        if predicted != case.sh:
            findings.append(
                "corpus case %s: the canonical validator says %s, %s records %s for the live "
                "bash reader. The canonical module and the recorded behaviour have parted, so "
                "neither can stand in for the other."
                % (case.case_id, predicted, CORPUS_REL, case.sh)
            )
        predicted_bp = vendored_verdict(case.reason, vendored_set, min_length)
        if predicted_bp != case.bp:
            findings.append(
                "corpus case %s: this gate's model of %s says %s, the corpus records %s. The "
                "model no longer describes the vendored file, so every attribution below is "
                "guesswork." % (case.case_id, VENDORED_REL, predicted_bp, case.bp)
            )

    # -- claim 4: every divergence is attributable, and to the right direction.
    dropped = canonical_phrases - vendored_set
    for case in cases:
        if case.sh == case.bp:
            continue
        shape.divergences += 1
        normalized = allowlist.normalize_reason(case.reason)
        if normalized in dropped:
            if case.bp == "accept":
                findings.append(
                    "corpus case %s diverges on a DROPPED PHRASE and the vendored copy ACCEPTS "
                    "it. A phrase difference alone cannot do that, because both rules still "
                    "reject a short reason; something else changed." % case.case_id
                )
            shape.by_phrase.append(case.case_id)
        elif any(sub in normalized for sub in canonical_substrings):
            if case.bp != "accept":
                findings.append(
                    "corpus case %s diverges on a canonical SUBSTRING but the vendored copy "
                    "still rejects it. The empty-substring-list derivation predicts an accept "
                    "here." % case.case_id
                )
            shape.by_substring.append(case.case_id)
        else:
            findings.append(
                "corpus case %s diverges (%s vs %s) and is attributable to NEITHER a dropped "
                "phrase nor the empty substring list. The recorded divergence is no longer "
                "explained by the list difference, which is what this gate exists to keep true."
                % (case.case_id, case.sh, case.bp)
            )

    # A derivation that explains one class and not the other is half a derivation, and the half that is missing is invisible in a count.
    if not shape.by_phrase:
        findings.append(
            "ZERO divergences attributed to a dropped phrase. Either the corpus stopped "
            "covering that class or the attribution is broken; both make the phrase half of "
            "this gate vacuous."
        )
    if not shape.by_substring:
        findings.append(
            "ZERO divergences attributed to the empty substring list. That is the class where "
            "the vendored copy ACCEPTS what the canonical one refuses, so losing coverage of it "
            "loses the only divergence that is a hole rather than a wording difference."
        )

    # -- the gate's own innocence, invariant 8.
    after = sha256_of(vendored)
    if after != before:
        findings.append(
            "THIS GATE WROTE TO %s: %s before its body, %s after. `.ci/breakpoint/` is "
            "read-only for everything, and an instrument that mutates the artifact it polices "
            "is the defect, not the finding." % (VENDORED_REL, before[:12], after[:12])
        )
    if after != pinned:
        findings.append(
            "%s no longer matches %s after this run (%s vs pinned %s). Something changed the "
            "vendored copy while the gate was reading it."
            % (VENDORED_REL, MANIFEST_REL, after[:12], pinned[:12])
        )

    return findings, shape


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("vendored blocker derivation", selftest)
    if rc:
        return rc
    try:
        findings, shape = run()
    except RefusalError as exc:
        log.error("vendored blocker derivation: %s" % exc)
        log.error("  A green here would mean nothing, so this is a failure and not a note.")
        return 1
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s). Do NOT repin the divergence count in %s: re-derive it. The "
            "vendored copy is drift-locked, so the change that caused this is in the canonical "
            "list or in the corpus." % (len(findings), CORPUS_REL)
        )
        return 1
    log.success(
        "vendored blocker derivation: %d canonical phrase(s) + %d canonical substring(s) vs %d "
        "vendored phrase(s) in %d array, %d phrase(s) dropped, 0 vendored substrings, floor %d "
        "both sides; %d corpus case(s), %d divergence(s) all attributed -- %d to a dropped "
        "phrase (%s, both sides still reject) and %d to the empty substring list (%s, the "
        "vendored copy ACCEPTS). %s read twice at %s, unchanged and equal to %s."
        % (
            shape.canonical_phrases,
            shape.canonical_substrings,
            shape.vendored_phrases,
            len(shape.vendored_arrays),
            shape.dropped_phrases,
            shape.min_length,
            shape.cases,
            shape.divergences,
            len(shape.by_phrase),
            ", ".join(shape.by_phrase),
            len(shape.by_substring),
            ", ".join(shape.by_substring),
            VENDORED_REL,
            shape.digest[:12],
            MANIFEST_REL,
        )
    )
    return 0


# --------------------------------------------------------------------------- controls
#
# EVERY FIXTURE IS A COPY. The real `.ci/breakpoint/` is never a write target here, which is invariant 8 and also the thing claim 5 asserts at run time; a control that perturbed the original to prove the gate notices perturbation would be the one write nobody could defend. ---------------------------------------------------------------------------


def _fixture(tmp, *, vendored: str, corpus: str, manifest: str | None = None) -> pathlib.Path:
    """A minimal tree: the vendored copy, its manifest row, and a corpus."""
    root = pathlib.Path(tmp)
    (root / ".ci" / "breakpoint" / "lib").mkdir(parents=True)
    (root / ".ci" / "scripts" / "test" / "gates").mkdir(parents=True)
    target = root / VENDORED_REL
    target.write_text(vendored, encoding="utf-8")
    (root / CORPUS_REL).write_text(corpus, encoding="utf-8")
    if manifest is None:
        manifest = "# generated: fixture\n%s  %s\n" % (sha256_of(target), MANIFEST_ROW)
    (root / MANIFEST_REL).write_text(manifest, encoding="utf-8")
    return root


def _run_at(root: pathlib.Path):
    try:
        return run(root)
    except RefusalError as exc:
        return "REFUSED: %s" % exc, None


def _real(rel: str) -> str:
    return (paths.repo_root() / rel).read_text(encoding="utf-8")


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    import tempfile  # noqa: PLC0415

    check = Checker()

    # The REAL files are the fixture. An invented vendored copy and an invented corpus would prove the parsers agree with each other and nothing about the artifacts in this tree; the two defects a synthetic fixture cannot see are a comment shape the extractor mis-reads and a heredoc that moved.
    real_vendored = _real(VENDORED_REL)
    real_corpus = _real(CORPUS_REL)

    parsed = parse_array(real_vendored, PHRASE_ARRAY)
    check("the real vendored array parses to a non-trivial list", len(parsed) >= MIN_PARSED_PHRASES)
    check(
        "ANTI-SILENCER: the prose above the array is NOT read back as members",
        "no upstream fix" not in parsed and "dev dep" not in parsed,
    )
    check(
        "the real corpus parses to its documented five-field rows",
        len(parse_corpus(real_corpus)) >= 20,
    )
    check(
        "an array under any other name is counted, so a second list cannot hide",
        array_names('readonly A=(\n"x"\n)\nreadonly B=(\n"y"\n)\n') == ["A", "B"],
    )
    check(
        "the substring-match operator is recognised in the shape bash writes it",
        bool(SUBSTRING_MATCH_RE.search('    if [[ "$normalized" == *"$pattern"* ]]; then')),
    )
    check(
        "ANTI-SILENCER: an exact-match comparison is NOT read as a substring match",
        not SUBSTRING_MATCH_RE.search('    if [[ "$normalized" == "$pattern" ]]; then'),
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, vendored=real_vendored, corpus=real_corpus)
        findings, shape = _run_at(root)
        check("CONTROL: the tree as it stands is clean", findings == [])
        check(
            "CONTROL: and the run was not trivially empty",
            shape is not None and shape.cases >= 20 and shape.divergences > 0,
        )
        check(
            "both attribution buckets are populated, so neither half is vacuous",
            shape is not None and shape.by_phrase and shape.by_substring,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # A SECOND LIST APPEARS. The likeliest real drift: somebody upstreams the canonical substring rule into the vendored copy and the corpus's five stops meaning what it means.
        mutant = plant(
            real_vendored,
            "readonly BREAKPOINT_BLOCKER_MIN_LENGTH=30",
            'readonly BREAKPOINT_LOW_EFFORT_SUBSTRINGS=(\n"not needed by this change"\n)\n'
            "readonly BREAKPOINT_BLOCKER_MIN_LENGTH=30",
        )
        root = _fixture(tmp, vendored=mutant, corpus=real_corpus)
        findings, _ = _run_at(root)
        check(
            "a SECOND array in the vendored copy is a finding",
            isinstance(findings, list) and any("besides" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        mutant = plant(
            real_vendored,
            'if [[ "$normalized" == "$pattern" ]]; then',
            'if [[ "$normalized" == *"$pattern"* ]]; then',
        )
        root = _fixture(tmp, vendored=mutant, corpus=real_corpus)
        findings, _ = _run_at(root)
        check(
            "a substring-match operator appearing in the vendored copy is a finding",
            isinstance(findings, list) and any("substring-match" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        mutant = plant(
            real_vendored,
            "readonly BREAKPOINT_BLOCKER_MIN_LENGTH=30",
            "readonly BREAKPOINT_BLOCKER_MIN_LENGTH=25",
        )
        root = _fixture(tmp, vendored=mutant, corpus=real_corpus)
        findings, _ = _run_at(root)
        check(
            "a floor that no longer matches the canonical one is a finding",
            isinstance(findings, list) and any(MIN_LENGTH_NAME in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        # THE COMPOSITION TRAP, in its exact shape: the divergence COUNT is unchanged and the membership is not. Adding `no fix` back to the vendored list turns banned-no-fix into agreement; the corpus still records a divergence there, so the model stops describing the file.
        mutant = plant(real_vendored, '    "none" "n/a"', '    "no fix" "none" "n/a"')
        root = _fixture(tmp, vendored=mutant, corpus=real_corpus)
        findings, _ = _run_at(root)
        check(
            "a phrase ADDED back to the vendored list breaks the model, not just the count",
            isinstance(findings, list) and any("banned-no-fix" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        # An UNATTRIBUTABLE divergence: a corpus row the two lists cannot explain.
        mutant = plant(
            real_corpus,
            "len-30|abcdefghij abcdefghij abcdefg1|accept|accept|accept",
            "len-30|abcdefghij abcdefghij abcdefg1|accept|accept|reject:too-short",
        )
        root = _fixture(tmp, vendored=real_vendored, corpus=mutant)
        findings, _ = _run_at(root)
        check(
            "a divergence attributable to neither list is a finding",
            isinstance(findings, list) and any("NEITHER" in f for f in findings),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, vendored=real_vendored, corpus=real_corpus, manifest="# no rows\n")
        result, _ = _run_at(root)
        check(
            "a manifest with no row for the vendored copy is REFUSED",
            isinstance(result, str) and "carries no row" in result,
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, vendored=real_vendored, corpus=real_corpus)
        (root / MANIFEST_REL).unlink()
        result, _ = _run_at(root)
        check(
            "a DELETED manifest is refused, never treated as nothing to check",
            isinstance(result, str) and "does not exist" in result,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # The pin and the bytes disagree: drift, which belongs to another gate.
        root = _fixture(
            tmp,
            vendored=real_vendored,
            corpus=real_corpus,
            manifest="%s  %s\n" % ("0" * 64, MANIFEST_ROW),
        )
        result, _ = _run_at(root)
        check(
            "a vendored copy that already drifted is REFUSED, not judged",
            isinstance(result, str) and "already drifted" in result,
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, vendored="# nothing here\n", corpus=real_corpus)
        result, _ = _run_at(root)
        check(
            "a vendored copy the extractor cannot read is an extractor refusal, not a shrunk list",
            isinstance(result, str) and "extractor or a short read" in result,
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, vendored=real_vendored, corpus="# no heredoc at all\n")
        result, _ = _run_at(root)
        check(
            "a corpus that parses to zero rows is REFUSED",
            isinstance(result, str) and "no corpus row parsed" in result,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # INNOCENCE, asserted rather than assumed: the fixture's own bytes are unchanged after a full run, which is the same claim `run()` makes about the real file at the end of every invocation.
        root = _fixture(tmp, vendored=real_vendored, corpus=real_corpus)
        digest_before = sha256_of(root / VENDORED_REL)
        _run_at(root)
        check(
            "a full run leaves the vendored copy byte-identical",
            sha256_of(root / VENDORED_REL) == digest_before,
        )

    return not check.ok


if __name__ == "__main__":  # pragma: no cover - the entry point is the wrapper
    raise SystemExit(main(sys.argv[1:]))
