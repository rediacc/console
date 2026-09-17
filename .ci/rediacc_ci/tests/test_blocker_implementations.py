"""Every blocker-reason implementation in this tree, and what each one is allowed to be.

WHY THIS MODULE EXISTS, AND WHY `test_core_allowlist.py` CANNOT DO ITS JOB.
`test_core_allowlist` proves that `rediacc_ci.core.allowlist` reproduces the two
shared readers BYTE FOR BYTE over a frozen corpus. That is a strong claim and it
has a hole with a precise shape, recorded in `agent/PLAN-tooling-transformation.md`:

    nothing asserts a phrase present in the BASH or TS list but absent from the
    Python canonical, because test_core_allowlist.py:370 generates its corpus
    FROM the Python list, making that direction structurally invisible.

A CORPUS GENERATED FROM THE SUBJECT CANNOT SEE THE SUBJECT BEING SHORT. Drop a
phrase from `LOW_EFFORT_PHRASES` and the golden suite loses one test case; the
remaining cases all still agree, the counts all still match, and every test is
green. The missing phrase is now silently allowed by every gate in the tree.

So this module asserts the OTHER direction, once per implementation:

  1. THE INVENTORY. Scan the tracked tree for files carrying a table of these
     phrases and require the result to be exactly the known set. This is how the
     FIFTH implementation was found on 2026-09-09: `swallowed_failures.py` held a
     verbatim 150-line copy that the four-implementation docstring did not name.
  2. THE BASH MIRROR. `.ci/scripts/lib/blocker-validator.sh` still carries the two
     arrays as TEXT, because `test-breakpoint-portability.sh:361` parses them out
     of that file to prove the vendored copy is a subset. Nothing in the bash file
     READS them any more. A mirror nothing compares is just a second opinion, so
     this asserts set EQUALITY in both directions, plus the floor.
  3. THE TYPESCRIPT CLIENT, structurally: it must declare no table, no floor and
     no message text of its own. That is the strongest possible form of "nothing
     reachable from the TS side is missing from the canonical", because there is
     nothing reachable from the TS side.
  4. THE TYPESCRIPT CLIENT, behaviourally. The goldens compare Python against
     RECORDED TypeScript bytes, so live TS drift is invisible until somebody
     re-records. This drives the REAL `validateBlockerQuality` over every phrase
     the canonical bans, every substring, their normalisation variants and every
     distinct real reason in the frozen corpus, and compares the verdict AND the
     message digest.

WHAT IS DELIBERATELY NOT RE-ASSERTED HERE, because it already exists and a second
implementation of a check is the same defect this module is about:

  * `bp_phrases` is a subset of the canonical, and the vendored file's own
    innocence -- `.ci/scripts/test/gates/test-breakpoint-portability.sh:357-441`,
    with a planted-defect regression.
  * `bp_substrings == the empty set`, and the derivation of the corpus's five
    recorded divergences -- `check:ci-vendored-blocker-derivation`.
  * byte compatibility of the two readers with the canonical over the frozen
    corpus -- `test_core_allowlist.py`.

THE VENDORED FILE IS NEVER OPENED FOR WRITING HERE. It is read, and only to name
it in the inventory.
"""

import hashlib
import json
import os
import pathlib
import re
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.core import allowlist
from rediacc_ci.tests import differential as diff

ROOT = pathlib.Path(diff.repo())

CANONICAL = ".ci/rediacc_ci/core/allowlist.py"
BASH_MIRROR = ".ci/scripts/lib/blocker-validator.sh"
VENDORED = ".ci/breakpoint/lib/breakpoint-blocker.sh"
TS_CLIENT = "scripts/lib/blocker-validator.ts"

# Files that legitimately carry MANY of these phrases without being an implementation of the BLOCKER contract. Exempt BY NAME, with the reason, and kept visible in the inventory assertion's message rather than silently filtered: a quiet exemption is how a gate stops meaning what its name says.
#
# BLOCKER: `is_low_effort_reply` is a DIFFERENT rule with a deliberately different punctuation class (it strips only `.!?`, this one strips
# `.!?,;:`). The two lists were written separately, the difference is real, and
# unifying them would change one gate's verdicts to fix nothing. The bash validator's own header has cross-referenced this sibling since it was written.
SIBLING_LOW_EFFORT_REPLY_RULE: dict[str, str] = {
    ".ci/scripts/quality/check-review-comments.sh": "is_low_effort_reply, review replies",
    ".ci/scripts/quality/check-review-report-replies.sh": "is_low_effort_reply, report replies",
    ".ci/scripts/quality/check-submodule-branches.sh": "is_low_effort_reply, submodule replies",
    ".ci/rediacc_ci/quality/review_comments.py": "port of check-review-comments.sh",
    ".ci/rediacc_ci/quality/review_report_replies.py": "port of check-review-report-replies.sh",
    ".ci/rediacc_ci/quality/submodule_branches.py": "port of check-submodule-branches.sh",
}

# A file holding at least this many of the canonical phrases as QUOTED LITERALS is carrying a table, not mentioning the convention. Ten rather than forty: the vendored subset holds 44 and the sibling reply rule holds 13-14, so ten is below every real table AND below the siblings, which is what forces every sibling to be named above instead of cleared by a threshold nobody
# re-derives.
TABLE_THRESHOLD = 10

# Text extensions only. A binary read would raise, and catching the raise is how a scan silently stops scanning.
SKIP_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp4",
    ".mp3",
    ".wav",
    ".pdf",
    ".zip",
    ".gz",
)


# --------------------------------------------------------------------------- Extractors ---------------------------------------------------------------------------


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def bash_array(text: str, name: str) -> list[str]:
    """The elements of `readonly <name>=( ... )`, in order.

    The SAME shape `.ci/scripts/test/gates/test-breakpoint-portability.sh:504`
    parses, deliberately: if this extractor and that one ever disagree about what
    the file says, the subset proof over there is reading something this equality
    proof is not.
    """
    match = re.search(
        r"^readonly %s=\(\n(.*?)^\)$" % re.escape(name), text, re.MULTILINE | re.DOTALL
    )
    if match is None:
        return []
    return re.findall(r'"([^"]*)"', match.group(1))


def bash_int(text: str, name: str) -> int | None:
    match = re.search(r"^readonly %s=(\d+)$" % re.escape(name), text, re.MULTILINE)
    return int(match.group(1)) if match else None


def quoted_phrase_hits(text: str) -> int:
    """How many canonical phrases appear in `text` as a QUOTED literal.

    QUOTED, not substring. A substring test cannot express a phrase that is a
    PREFIX of another -- the table itself has real pairs shaped exactly like
    this, one entry a shorter prefix of a longer sibling -- illustrated here
    with words that are NOT table entries, so this docstring cannot trip its
    own detector: `"cat"` occurs inside `"category"`, and `"an"` inside almost
    anything. Requiring the surrounding quote characters makes each hit an
    element of a list rather than a coincidence of prose.
    """
    total = 0
    for phrase in allowlist.LOW_EFFORT_PHRASES:
        if any(q + phrase + q in text for q in ("'", '"', "`")):
            total += 1
    return total


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [f for f in out.split("\0") if f]


def files_carrying_a_table() -> dict[str, int]:
    found: dict[str, int] = {}
    scanned = 0
    for rel in tracked_files():
        if rel.endswith(SKIP_SUFFIXES):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        hits = quoted_phrase_hits(text)
        if hits >= TABLE_THRESHOLD:
            found[rel] = hits
    assert scanned > 500, (
        "the inventory scanned only %d file(s); it is not seeing the tree, and its "
        "green would mean nothing" % scanned
    )
    return found


# --------------------------------------------------------------------------- 1. The inventory ---------------------------------------------------------------------------


def test_the_set_of_files_carrying_a_phrase_table_is_the_known_set():
    """A SIXTH copy appearing anywhere in the tree fails here, by name.

    This is the test that would have caught `swallowed_failures.py`, which held a
    verbatim copy for three days while a docstring two directories away insisted
    there were four implementations and named a different four.
    """
    found = files_carrying_a_table()
    expected = {CANONICAL, BASH_MIRROR, VENDORED} | set(SIBLING_LOW_EFFORT_REPLY_RULE)
    unknown = {k: v for k, v in found.items() if k not in expected}
    gone = sorted(expected - set(found))
    shape = ", ".join("%s=%d" % (k, v) for k, v in sorted(found.items()))
    assert not unknown, (
        "a new copy of the BLOCKER phrase table appeared in %s. Collapse it onto "
        "%s; do not add it to the exempt map unless it is a genuinely different "
        "rule, and then say which. Full inventory: %s" % (sorted(unknown), CANONICAL, shape)
    )
    assert not gone, (
        "these files no longer carry a phrase table: %s. If one was collapsed, "
        "delete its row here; a stale expectation makes this test assert less "
        "than it says. Full inventory: %s" % (gone, shape)
    )
    assert len(found) == 9, "inventory shape changed: %s" % shape


def test_the_inventory_detector_would_find_a_planted_table():
    """THE CONTROL. A detector that cannot find a table proves nothing by not finding one."""
    plant = "\n".join("  '%s'," % p for p in allowlist.LOW_EFFORT_PHRASES[:TABLE_THRESHOLD])
    assert quoted_phrase_hits(plant) >= TABLE_THRESHOLD, (
        "the detector missed a table of exactly %d quoted phrases" % TABLE_THRESHOLD
    )
    # And the near-miss must NOT fire, or the threshold is decorative.
    near = "\n".join("  '%s'," % p for p in allowlist.LOW_EFFORT_PHRASES[: TABLE_THRESHOLD - 1])
    assert quoted_phrase_hits(near) < TABLE_THRESHOLD

    # BOTH DIRECTIONS ON THE QUOTING RULE. Prose that merely NAMES the phrases must not count, or every doc file in the tree becomes an implementation.
    prose = " ".join(allowlist.LOW_EFFORT_PHRASES)
    assert quoted_phrase_hits(prose) == 0, (
        "unquoted prose naming every phrase was counted as a table; the detector "
        "is matching substrings, not list elements"
    )


# --------------------------------------------------------------------------- 2. The bash mirror ---------------------------------------------------------------------------


def test_the_bash_mirror_is_exactly_the_canonical_tables():
    """SET EQUALITY, BOTH DIRECTIONS. This is the assertion the goldens cannot make.

    The goldens build their reason corpus from `LOW_EFFORT_PHRASES`, so a phrase
    that exists in the bash array and NOT in the canonical produces no test case
    at all and is invisible to every one of them. Here it is a named failure.
    """
    text = _text(BASH_MIRROR)
    phrases = bash_array(text, "LOW_EFFORT_BLOCKER_PATTERNS")
    substrings = bash_array(text, "LOW_EFFORT_BLOCKER_SUBSTRINGS")
    floor = bash_int(text, "BLOCKER_MIN_LENGTH")

    assert phrases, (
        "no LOW_EFFORT_BLOCKER_PATTERNS array parsed out of %s. An empty extraction "
        "makes every comparison below vacuous, so it is a failure rather than an "
        "agreement." % BASH_MIRROR
    )
    assert substrings, "no LOW_EFFORT_BLOCKER_SUBSTRINGS array parsed out of %s" % BASH_MIRROR

    bash_only = sorted(set(phrases) - set(allowlist.LOW_EFFORT_PHRASES))
    canonical_only = sorted(set(allowlist.LOW_EFFORT_PHRASES) - set(phrases))
    assert not bash_only, (
        "%s bans %s and the canonical does not. This is the direction the golden "
        "corpus cannot see: it generates its cases FROM the canonical list, so a "
        "phrase only the bash side knows about produces no case. Add it to "
        "LOW_EFFORT_PHRASES in %s, or delete it here." % (BASH_MIRROR, bash_only, CANONICAL)
    )
    assert not canonical_only, (
        "the canonical bans %s and the bash mirror does not. The mirror is what "
        "test-breakpoint-portability.sh:361 measures the vendored subset against, so "
        "a short mirror makes that subset proof weaker than it reads." % canonical_only
    )

    assert list(substrings) == list(allowlist.LOW_EFFORT_SUBSTRINGS), (
        "the substring tables differ: bash=%s canonical=%s"
        % (substrings, list(allowlist.LOW_EFFORT_SUBSTRINGS))
    )
    assert floor == allowlist.MIN_REASON_LENGTH, "BLOCKER_MIN_LENGTH is %r in %s and %r in %s" % (
        floor,
        BASH_MIRROR,
        allowlist.MIN_REASON_LENGTH,
        CANONICAL,
    )

    # ORDER IS LOAD-BEARING and set equality does not see it. The message quotes the FIRST pattern that matches, so a reordering changes printed bytes.
    assert phrases == list(allowlist.LOW_EFFORT_PHRASES), (
        "the two tables hold the same phrases in a DIFFERENT order. The rejection "
        "message names the first pattern that matches, so order changes output."
    )


def test_the_bash_extractor_reports_a_planted_divergence():
    """THE CONTROL for the equality above, on a COPY of the real file."""
    text = _text(BASH_MIRROR)
    planted = text.replace('"tbd" "wip"', '"tbd" "wip" "__planted_only_in_bash__"', 1)
    assert planted != text, (
        "the plant did not land: LOW_EFFORT_BLOCKER_PATTERNS no longer holds the "
        "line this control edits"
    )
    phrases = bash_array(planted, "LOW_EFFORT_BLOCKER_PATTERNS")
    assert "__planted_only_in_bash__" in phrases
    assert set(phrases) - set(allowlist.LOW_EFFORT_PHRASES) == {"__planted_only_in_bash__"}

    # And the other direction: a phrase REMOVED from the mirror is caught too.
    shortened = text.replace('"tbd" "wip"', '"wip"', 1)
    assert shortened != text
    assert "tbd" not in bash_array(shortened, "LOW_EFFORT_BLOCKER_PATTERNS")


def test_the_bash_mirror_is_not_read_by_the_bash_validator():
    """The mirror's whole justification is that it is DATA, not the rule.

    If a future edit wires `validate_blocker_quality` back onto the array, the
    file becomes a second implementation again and the equality test above turns
    from a guarantee into a hope somebody re-runs it.
    """
    text = _text(BASH_MIRROR)
    body = text[text.index("validate_blocker_quality() {") :]
    for name in (
        "LOW_EFFORT_BLOCKER_PATTERNS",
        "LOW_EFFORT_BLOCKER_SUBSTRINGS",
        "BLOCKER_MIN_LENGTH",
    ):
        assert name not in body, (
            "%s reads %s again. It is a mirror of the canonical, kept only so "
            "test-breakpoint-portability.sh can parse it; deciding anything from it "
            "re-creates the divergence this collapse removed." % (BASH_MIRROR, name)
        )
    assert "rediacc_ci.core.allowlist" in text, (
        "%s no longer names the canonical module; it has stopped delegating" % BASH_MIRROR
    )


# --------------------------------------------------------------------------- 3. The TypeScript client, structurally ---------------------------------------------------------------------------

# An array literal holding at least three quoted strings. The shape a phrase table has in TypeScript, and the shape this file must not contain.
_TS_ARRAY = re.compile(r"=\s*\[[^\]]*?((?:'[^']*'|\"[^\"]*\")\s*,\s*){3,}", re.DOTALL)
_TS_FLOOR = re.compile(r"\b[A-Za-z_]*(?:MIN_LENGTH|minLength)\s*[:=]\s*\d+")


def ts_own_tables(text: str) -> list[str]:
    """Every sign that the TypeScript file is carrying the rule rather than reading it."""
    findings: list[str] = []
    if _TS_ARRAY.search(text):
        findings.append("an array literal of three or more quoted strings")
    if _TS_FLOOR.search(text):
        findings.append("a numeric length floor")
    hits = quoted_phrase_hits(text)
    if hits:
        findings.append("%d canonical phrase(s) as quoted literals" % hits)
    return findings


def test_the_typescript_client_declares_no_rule_of_its_own():
    """THE STRONGEST FORM of "no TS-side phrase is missing from the canonical".

    Until 2026-09-09 this file held 54 phrases, 7 substrings, a 30-character floor
    and four message bodies, under a comment asking the next author to keep them in
    sync with bash by hand. Nothing asserted that the comment had been obeyed.
    """
    text = _text(TS_CLIENT)
    findings = ts_own_tables(text)
    assert not findings, (
        "%s carries %s. It is supposed to be a CLIENT of %s: the tables and the "
        "message text arrive from `contract`, and anything written here is a second "
        "copy nothing compares." % (TS_CLIENT, " and ".join(findings), CANONICAL)
    )
    assert "rediacc_ci.core.allowlist" in text, (
        "%s no longer names the canonical module; it has stopped delegating" % TS_CLIENT
    )


def test_the_typescript_table_detector_would_find_a_planted_table():
    """THE CONTROL, both directions.

    The failure this guards against is not the gate breaking, it is the detector
    quietly matching nothing: an `= [` pattern that no longer matches the shape a
    table has would let a re-introduced list through in silence.
    """
    text = _text(TS_CLIENT)
    planted = text.replace(
        "const SUPPORTED_CONTRACT_VERSION = 1;",
        "const PLANTED: readonly string[] = ['tbd', 'wip', 'todo', 'later'];\n"
        "const SUPPORTED_CONTRACT_VERSION = 1;",
        1,
    )
    assert planted != text, "the plant did not land: SUPPORTED_CONTRACT_VERSION moved"
    findings = ts_own_tables(planted)
    assert "an array literal of three or more quoted strings" in findings, findings
    assert any("canonical phrase" in f for f in findings), findings

    floor = text.replace(
        "const SUPPORTED_CONTRACT_VERSION = 1;",
        "const BLOCKER_MIN_LENGTH = 30;\nconst SUPPORTED_CONTRACT_VERSION = 1;",
        1,
    )
    assert "a numeric length floor" in ts_own_tables(floor)

    # The negative control: the real file, unmodified, must produce nothing. That is the same assertion as the test above, made here so this control proves the detector discriminates rather than merely fires.
    assert ts_own_tables(text) == []


def test_the_python_clients_declare_no_rule_of_their_own():
    """The two Python gates that used to hold copies, and the one that may.

    `plan_housekeeping.parse_allowlist` is NOT collapsed and is not expected to be:
    it enforces a 40-character floor, consumes one reason per entry, and does not
    reset on a blank line. Three deliberate differences, asserted as differences by
    `test_quality_plan_housekeeping.py:267` and `:277`. Averaging them away to fit a
    collapse would change that gate's verdicts.
    """
    for rel in (
        ".ci/rediacc_ci/quality/swallowed_failures.py",
        ".ci/scripts/quality/check_runner_advice.py",
        ".ci/scripts/quality/check_language_policy.py",
    ):
        text = _text(rel)
        hits = quoted_phrase_hits(text)
        # THE SAME THRESHOLD THE INVENTORY USES, not zero. Both files legitimately write one or two of these words for other reasons: `swallowed_failures` feeds the literal "todo" to a control probe, and emits a JSON object with an "ok" key. A floor of zero here and ten there would be two different answers to one question, and the stricter one would be the one nobody could satisfy.
        assert hits < TABLE_THRESHOLD, (
            "%s carries %d canonical phrase(s) as quoted literals, at or over the "
            "table threshold of %d; it is supposed to call rediacc_ci.core.allowlist"
            % (rel, hits, TABLE_THRESHOLD)
        )
        assert "rediacc_ci.core.allowlist" in text or "core import allowlist" in text, (
            "%s stopped naming the canonical module" % rel
        )

    # AND THE HOP THAT IS STILL THERE, recorded rather than asserted away. `check_language_policy.blocker_quality_problem` shells out to `.ci/scripts/lib/blocker-validator.sh` for the QUALITY rule, and that file now shells back to `rediacc_ci.core.allowlist`. Python -> bash -> Python for an answer the first Python could have computed. It is correct and it is wasteful, and the
    # reason it was not changed in the same pass is that the shell-out is what its gate test's "the validator cannot be consulted"
    # refusal exists to exercise; removing one without the other deletes a live
    # control. Pinned so the hop cannot be forgotten.
    policy = _text(".ci/scripts/quality/check_language_policy.py")
    assert "blocker-validator.sh" in policy, (
        "check_language_policy no longer shells out for the BLOCKER quality rule. If "
        "it now calls rediacc_ci.core.allowlist directly, good; delete this assertion "
        "AND the 'validator cannot be consulted' arm of test-language-policy.sh, which "
        "tests a failure mode that no longer exists."
    )

    housekeeping = _text(".ci/rediacc_ci/quality/plan_housekeeping.py")
    assert "MIN_REASON_LENGTH = 40" in housekeeping, (
        "plan_housekeeping's 40-character floor is gone. It is exempt from the "
        "collapse BECAUSE it is stricter on purpose; if the floor moved to 30 the "
        "exemption is what needs deleting, not this assertion."
    )


# --------------------------------------------------------------------------- 4. The TypeScript client, behaviourally, on the LIVE file ---------------------------------------------------------------------------


def _tsx_available() -> bool:
    return (ROOT / "node_modules" / "tsx").exists()


TS_DRIVER = """
import fs from 'node:fs';
import crypto from 'node:crypto';
import { validateBlockerQuality } from '%s/scripts/lib/blocker-validator.ts';
const tab = String.fromCharCode(9), nl = String.fromCharCode(10);
for (const line of fs.readFileSync(process.argv[2], 'utf-8').split(nl)) {
  if (!line) continue;
  const cut = line.indexOf(tab);
  const id = line.slice(0, cut), reason = line.slice(cut + 1);
  const r = validateBlockerQuality(id, reason, process.argv[3]);
  const digest = crypto.createHash('sha256').update(r ? r.message : '', 'utf8').digest('hex');
  process.stdout.write(id + tab + (r ? r.kind : 'ok') + tab + digest + nl);
}
"""

REASON_FILE = ".deps-upgrade-blocklist"


def _cases() -> list[tuple[str, str]]:
    """Every phrase, every substring, their normalisation variants, and real reasons.

    NOT generated from one side only. The phrase families come from the canonical
    (there is nowhere else to get them now), but the REAL family is read out of the
    frozen corpus, which is a byte copy of the tree's actual lists, and the
    normalisation family exists because deleting the trailing-punctuation strip
    left every other case green when it was measured.
    """
    cases: list[tuple[str, str]] = []
    for index, phrase in enumerate(allowlist.LOW_EFFORT_PHRASES):
        cases.append(("phrase-%03d" % index, phrase))
        cases.append(("norm-%03d" % index, "  %s.  " % phrase.upper()))
    for index, sub in enumerate(allowlist.LOW_EFFORT_SUBSTRINGS):
        cases.append(("sub-%03d" % index, "a long and otherwise fine reason that %s anyway" % sub))
    corpus = ROOT / ".ci" / "rediacc_ci" / "tests" / "goldens" / "allowlist" / "corpus"
    seen: list[str] = []
    for path in sorted(corpus.glob("*.list")):
        for entry in allowlist.parse_text(path.read_text(encoding="utf-8")):
            if entry.blocker and entry.blocker not in seen:
                seen.append(entry.blocker)
    for index, reason in enumerate(seen):
        cases.append(("real-%03d" % index, reason))
        cases.append(("short-%03d" % index, reason[:12]))
    assert len(seen) >= 20, (
        "only %d distinct real reason(s) came out of the frozen corpus; the "
        "accept-side of this differential would be nearly empty" % len(seen)
    )
    return cases


def test_the_live_typescript_client_agrees_with_the_canonical():
    """The REAL `validateBlockerQuality`, not a recorded copy of it.

    `test_core_allowlist` compares the canonical against TypeScript bytes RECORDED
    in a golden. That catches a regression in the canonical and cannot see drift in
    the TypeScript, because the golden does not change when the TypeScript does.
    Measured on 2026-09-09: a planted `+ 'PLANT'` inside the TS normaliser left all
    53 of those tests green.

    NOT A SKIP when tsx is missing. A skip is indistinguishable from a pass in the
    count `check_pytest.py` reconciles, so the absent branch ASSERTS the absence.
    """
    cases = _cases()
    for case_id, reason in cases:
        assert "\t" not in reason, case_id
        assert "\n" not in reason, case_id

    tsv = "".join("%s\t%s\n" % (case_id, reason) for case_id, reason in cases)
    entry = ROOT / ".ci" / "cache" / ("blocker-impl-%d.mts" % os.getpid())
    cases_file = ROOT / ".ci" / "cache" / ("blocker-impl-%d.tsv" % os.getpid())
    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(TS_DRIVER % str(ROOT), encoding="utf-8")
        cases_file.write_text(tsv, encoding="utf-8")
        result = subprocess.run(
            ["npx", "--no-install", "tsx", str(entry), str(cases_file), REASON_FILE],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(ROOT),
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        result = None
    finally:
        entry.unlink(missing_ok=True)
        cases_file.unlink(missing_ok=True)

    if result is None or result.returncode != 0:
        assert not _tsx_available(), (
            "tsx IS installed but %s could not be driven; the differential is broken "
            "rather than unavailable. stderr: %s"
            % (TS_CLIENT, "" if result is None else result.stderr[-2000:])
        )
        return

    got = [row for row in result.stdout.split("\n") if row]
    assert len(got) == len(cases), "the TypeScript driver returned %d verdict(s) for %d case(s)" % (
        len(got),
        len(cases),
    )

    mismatches: list[str] = []
    rejected = 0
    for (case_id, reason), row in zip(cases, got, strict=True):
        their_id, their_kind, their_digest = row.split("\t")
        assert their_id == case_id, "the driver reordered the cases at %s" % case_id
        rejection = allowlist.validate_reason(case_id, reason, REASON_FILE)
        mine_kind = rejection.kind if rejection else "ok"
        mine_digest = hashlib.sha256(
            (rejection.message if rejection else "").encode("utf-8")
        ).hexdigest()
        if mine_kind != their_kind or mine_digest != their_digest:
            mismatches.append(
                "%s (%r): canonical=%s/%s typescript=%s/%s"
                % (case_id, reason[:40], mine_kind, mine_digest[:12], their_kind, their_digest[:12])
            )
        if mine_kind != "ok":
            rejected += 1

    assert not mismatches, "the live TypeScript client diverged on %d case(s):\n  %s" % (
        len(mismatches),
        "\n  ".join(mismatches[:10]),
    )
    # ANTI-VACUITY, both sides. A comparison in which nothing was rejected, or nothing was accepted, agrees about nothing.
    accepted = len(cases) - rejected
    shape = "%d case(s), %d rejection(s), %d acceptance(s)" % (len(cases), rejected, accepted)
    assert rejected > 0, "no case was rejected, so the reject side proved nothing: " + shape
    assert accepted > 0, "no case was accepted, so the accept side proved nothing: " + shape


def test_the_contract_the_typescript_client_reads_is_complete():
    """Every field the client needs, and no template with an unresolvable field.

    A `contract` missing `templates` would make the client throw, which is loud. A
    contract whose template names a field no caller supplies throws only on the
    code path that renders it, which is the one a passing tree never takes.
    """
    payload = json.loads(
        subprocess.run(
            ["python3", "-m", "rediacc_ci.core.allowlist", "contract"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(paths.from_root(".ci"))},
        ).stdout
    )
    assert set(payload) == {
        "version",
        "minLength",
        "emdash",
        "phrases",
        "substrings",
        "templates",
    }, sorted(payload)
    assert payload["phrases"] == list(allowlist.LOW_EFFORT_PHRASES)
    assert payload["substrings"] == list(allowlist.LOW_EFFORT_SUBSTRINGS)
    assert payload["minLength"] == allowlist.MIN_REASON_LENGTH
    assert set(payload["templates"]) == {"low-effort", "deferral", "too-short", "missing"}

    supplied = {
        "low-effort": {"file", "entry", "reason", "normalized", "emdash"},
        "deferral": {"file", "entry", "reason", "pattern", "emdash"},
        "too-short": {"file", "entry", "reason", "length", "min", "emdash"},
        "missing": {"file", "entry", "emdash"},
    }
    for kind, lines in payload["templates"].items():
        wanted = set()
        for line in lines:
            wanted |= set(re.findall(r"\{([a-z]+)\}", line))
        assert wanted <= supplied[kind], (
            "template %r references %s, which no caller of `_render` supplies; the "
            "TypeScript client would throw on the path that renders it"
            % (kind, sorted(wanted - supplied[kind]))
        )


@pytest.mark.parametrize(
    "reason",
    [
        # Under the floor on purpose: the too-short arm quotes the reason back verbatim, which is where a rescanning renderer would corrupt it.
        "{entry} {file} {min}",
        # And the deferral arm, which is the only one that interpolates a SECOND
        # runtime value ({pattern}) into the same message as the reason.
        "{entry} {file} {pattern} {emdash} and not needed by this change either",
    ],
)
def test_a_reason_that_looks_like_a_template_is_not_substituted(reason):
    """THE INJECTION CASE. One pass over the TEMPLATE, values never rescanned.

    A `replace()` chain would splice the entry id into the middle of somebody's
    prose, and the two languages would then disagree about the bytes for a reason
    that is perfectly legal to write.
    """
    rejection = allowlist.validate_reason("ENTRY-42", reason, "FILE")
    assert rejection is not None
    assert "ENTRY-42" in rejection.message
    # The literal braces from the reason survive verbatim inside the quoted copy.
    assert '"%s"' % reason in rejection.message or '"%s"' % reason in rejection.message
