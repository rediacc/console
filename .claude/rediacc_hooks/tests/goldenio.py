"""Shared golden-file I/O for the three hook differentials (PLAN-retire-bash-oracles A1/A2).

WHY ONE MODULE FOR THREE DIFFERENTIALS. `test_guards_differential.py`, `test_post_bash_differential.py` and `test_shellscan_differential.py` each freeze a different shape of record (rc/out/err for a guard; rc/out/err/body/ calls for a post-bash hook; ~28 named fields for shellscan), but all three need the SAME three things: a stable case key, a way to make a bash message byte-safe inside JSON, and a way to strip the one thing that is guaranteed to differ between the recording session and every later comparison -- the ephemeral `tmp_path_factory` root. Three copies of that machinery is three chances for the copies to drift, which is exactly the failure class this whole plan exists to retire.

THE KEY IS CONTENT-DERIVED, NOT POSITIONAL. `test_guards_differential.build_cases`'s foreign-payload sample is a HASH-based 40-of-378 subset in
the default run and the FULL 378 under `REDIACC_GUARD_DIFF_FULL=1`; the two
runs assign the SAME payload different "cross-NNN" INDEXES because the list they enumerate is a different length. A key built from the label alone would therefore look up the wrong record (or none) depending on which mode recorded it and which mode is reading it. Hashing the payload/env/stub CONTENT into the key sidesteps the index entirely: the same case, however it was labelled or numbered when it was produced, hashes to the same key. The label is kept as a prefix purely so a mismatch reads as "guard/default|edge-plain-shape#a1b2c3d4e5f6a7b8" instead of a bare hash.

WHY BASE64 EVER, given the harness's own "BYTES, NOT TEXT" rule. A guard's stderr is built from Python strings today, so in practice it is always clean UTF-8 -- but a byte string decoded elsewhere with `surrogateescape` (as `hookio._jq_raw` and this suite's own `_git_read` both do) can carry a lone surrogate that is not valid UTF-8 and that `str.encode("utf-8")` refuses to write to a JSONL file. Encoding is content-addressed per field: plain text stays plain text (readable, diffable), and only a field that actually fails the UTF-8 round trip pays the base64 tax.
"""

from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import subprocess

GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "goldens"

_B64_MARKER = "\x00b64:"


# The checkout the harness runs from, found by the same predicate `hookio.repo_root` uses (a directory holding both `.claude` and `.ci`), not by counting `parents[N]`.
REPO_ROOT = next(
    p
    for p in pathlib.Path(__file__).resolve().parents
    if (p / ".claude").is_dir() and (p / ".ci").is_dir()
)


def normalize(text, work):
    """Replace the ephemeral per-session tmp root, and then the checkout's own root, with stable tokens.

    `work` is `tmp_path_factory`'s mint for this pytest session -- a fresh path under `/tmp/pytest-of-<user>/pytest-<n>/...` every single run. Anything built under it (a git fixture clone, a stub directory) can leak into a guard's own message, and a frozen golden that kept that path literally would fail its own recording session's comparison the very next time pytest ran, for a reason that has nothing to do with the guard. `test_post_bash_differential.py` already carries exactly this substitution for its own recordings (`out.replace(str(work).encode(), b"<work>")`); this generalises it rather than inventing a second scheme, named `<WORK>` to stay visually distinct from that file's `<work>`.

    THE CHECKOUT ROOT IS THE SECOND THING, found 2026-09-25 (#328aca77): a guard that names a repo path (`block_agent_browser_repo_output`'s refusal, `block_unlinked_commit_author`'s `Allowed (from <root>/.ci/config/commit-identity.json)`) froze `/home/developer/console` into its golden, so the same port run from a second checkout failed on the path alone. `<WORK>` goes first because a tmp root may sit INSIDE a checkout, and the longer prefix has to win.
    """
    if work is None or text is None:
        return text
    return text.replace(str(work), "<WORK>").replace(str(REPO_ROOT), "<REPO>")


def encode_field(value):
    """A JSON-safe string for one bash/python field, base64 only when needed."""
    raw = value.encode("utf-8", "surrogateescape")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return _B64_MARKER + base64.b64encode(raw).decode("ascii")


def decode_field(value):
    if value.startswith(_B64_MARKER):
        return base64.b64decode(value[len(_B64_MARKER) :]).decode("utf-8", "surrogateescape")
    return value


def content_hash(*parts):
    """A short stable digest of whatever decides one case's answer.

    `\\x1f`-joined the same way the corpus files frame their own records (`test_guards_differential.US`), so two parts can never collide by concatenation the way `"ab" + "c"` and `"a" + "bc"` would.
    """
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def case_key(label, *content_parts):
    """`"<label>#<hash>"`: readable on sight, exact on lookup.

    Two cases sharing a label but not their content hash to different keys (a stale label never masks a real divergence); two cases that hash the same ARE the same case, whatever they were labelled when they were produced -- which is the property `test_guards_differential`'s full-vs-default cross sample needs, see the module docstring.
    """
    return "%s#%s" % (label, content_hash(*content_parts))


def bash_version_line():
    proc = subprocess.run(["bash", "--version"], capture_output=True, check=True, text=True)
    return proc.stdout.splitlines()[0]


def golden_path(stem):
    return GOLDEN_DIR / ("%s.jsonl" % stem)


def write_golden(path, header, silent_keys, records):
    """One JSONL file: a header line, a silent-key-list line, then records.

    Sorted by key throughout, so a diff of two recordings is a diff of real content and never of dict, set or filesystem-listing order.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"_header": header}, sort_keys=True)]
    lines.append(json.dumps({"_silent": sorted(silent_keys)}, sort_keys=True))
    for key in sorted(records):
        row = dict(records[key])
        row["_key"] = key
        lines.append(json.dumps(row, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_golden_lines(lines):
    """`(header, silent_set, {key: record})` from an already-split JSONL body.

    Split out of `read_golden` so a second reader -- the golden-drift control, comparing the file on disk against `git show HEAD:<path>` -- parses the identical format from text that never touched a filesystem path, rather than growing its own second copy of this framing.
    """
    if not lines:
        return None, set(), {}
    header = json.loads(lines[0])["_header"]
    silent = set(json.loads(lines[1]).get("_silent", []))
    records = {}
    for line in lines[2:]:
        if not line:
            continue
        row = json.loads(line)
        key = row.pop("_key")
        records[key] = row
    return header, silent, records


def read_golden(path):
    """`(header, silent_set, {key: record})`. An absent file reads as empty.

    Absent-reads-empty rather than raising: `regolden.py`'s diff-against-the-old-file has to work the very first time a stem is recorded, when there is by definition no old file, and "nothing existed before" must mean "nothing changed" rather than a crash.
    """
    if not path.is_file():
        return None, set(), {}
    return parse_golden_lines(path.read_text(encoding="utf-8").splitlines())


def is_silent(rc, out, err):
    return rc == "0" and out == "" and err == ""


def lookup(silent, records, key):
    """The recorded answer for `key`, or `None` if this golden never saw it.

    A silent key stores no record at all (see the header comment on `is_silent`), so the caller gets back the canonical empty triple instead of a dict when the key is only in the silent set.
    """
    if key in silent:
        return {"rc": "0", "out": "", "err": ""}
    return records.get(key)


def diff_and_mark(answers, old_silent, old_records, reason):
    """Partition a fresh recording into `(silent_keys, records, changed_keys)`, marking every record whose value actually moved `intentional: reason`.

    `answers` is `{key: (rc, out, err)}`, already normalized. `reason` is REQUIRED regardless of whether anything changed -- regolden.py's whole point is that a silent re-recording still names why it ran -- but it is only written onto a record whose value differs from what the existing golden already said, per PLAN-retire-bash-oracles A2: "writes `intentional: <reason>` on each CHANGED record". A key absent from the old golden is new, not changed, and gets no marker; re-recording an untouched case reproduces the byte-identical row, which is what makes an idempotent regolden a no-op diff. Only the guard differential (uniformly rc/out/err) uses this; shellscan and post-bash carry wider records and compare them directly in `regolden.py`, so this stays the small shape it actually has a caller for.
    """
    if not reason:
        msg = "regolden refuses to write a golden without --reason"
        raise ValueError(msg)
    silent: set[str] = set()
    records: dict[str, dict[str, str]] = {}
    changed: list[str] = []
    for key, value in answers.items():
        rc, out, err = value
        if key in old_silent:
            old = ("0", "", "")
        elif key in old_records:
            old_row = old_records[key]
            old = (
                old_row["rc"],
                decode_field(old_row.get("out", "")),
                decode_field(old_row.get("err", "")),
            )
        else:
            old = None
        is_changed = old is not None and old != value
        if is_silent(rc, out, err) and not is_changed:
            silent.add(key)
            continue
        row = {"rc": rc, "out": encode_field(out), "err": encode_field(err)}
        if is_changed:
            row["intentional"] = reason
            changed.append(key)
        records[key] = row
    return silent, records, changed
