#!/usr/bin/env python3
"""Every locale value must have the same TYPE as its English counterpart.

WHY THIS EXISTS. On 2026-08-06 eight locales were found carrying
`"ref": "[1]"` where en.json holds `"ref": 1` -- a citation INDEX that had been
replaced by its own rendered marker, 18 keys per locale, 144 values. Where the
index was 0 it had become `""`, because 0 is falsy and something in the pipeline
did `value || ''`.

It was live in production. packages/www/src/components/solution-pages/
SPProblem.astro guards with `callout.ref && callout.ref > 0`; for a string
`'[1]' > 0` is false, so the citation superscript and its source link rendered
for NOBODY in those eight languages across six solution pages, while English
rendered them normally.

NOTHING CAUGHT IT, and that is the point of this file. The placeholder,
cross-locale and locale-source gates all passed, because each compares TEXT.
i18n/no-empty-translations would have caught exactly one of the 144 -- and it
could not, because it was one of five rules reading `node.body?.members` on an
AST that puts `members` on the Object node, so it iterated an empty list and
could never report at all.

A type check is cheap, has no false-positive surface worth speaking of (a value
is a string or it is not), and catches the whole class rather than the instance.

Run modes:
    check_i18n_value_types.py            the gate
    check_i18n_value_types.py --selftest controls only
"""

import argparse
import json
import pathlib
import sys

# (english file, [sibling locale files]) pairs are discovered, not listed, so a
# new locale is covered the day it is added rather than the day someone
# remembers this file. The locale SET is deliberately not hard-coded here --
# @rediacc/locales is the single source for that, and a hand-rolled list in a
# gate is how a 379-key blind spot happened once before.
WWW = "packages/www/src/i18n/translations"
CLI = "packages/cli/src/i18n/locales"


def flatten(node, path, out):
    """{dotted.path: leaf value} for one document."""
    if isinstance(node, dict):
        for key, value in node.items():
            flatten(value, [*path, key], out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            flatten(value, [*path, str(index)], out)
    else:
        out[".".join(path)] = node


def compare(en_doc, loc_doc):
    """[(key, english value, locale value)] where the TYPES disagree.

    Keys absent from the locale are NOT a finding here: missing translations are
    a different defect with its own gate, and folding them in would make this
    check fire on every partially-translated file and get switched off.
    """
    en_flat, loc_flat = {}, {}
    flatten(en_doc, [], en_flat)
    flatten(loc_doc, [], loc_flat)
    bad = []
    for key, en_value in en_flat.items():
        if key not in loc_flat:
            continue
        loc_value = loc_flat[key]
        # bool is a subclass of int in Python; treat them as distinct so a
        # `true` swapped for `1` is still caught.
        if type(en_value) is not type(loc_value):
            bad.append((key, en_value, loc_value))
    return bad


def locale_pairs(root):
    """[(label, en path, locale path)] across both layouts in this repo."""
    pairs = []
    www = root / WWW
    if (www / "en.json").is_file():
        for path in sorted(www.glob("*.json")):
            if path.name.startswith(".") or path.name == "en.json":
                continue
            pairs.append(("www/" + path.stem, www / "en.json", path))
    cli = root / CLI
    if (cli / "en").is_dir():
        for en_file in sorted((cli / "en").glob("*.json")):
            for locale_dir in sorted(p for p in cli.iterdir() if p.is_dir()):
                if locale_dir.name == "en":
                    continue
                sibling = locale_dir / en_file.name
                if sibling.is_file():
                    pairs.append(("cli/%s/%s" % (locale_dir.name, en_file.stem), en_file, sibling))
    return pairs


# ---- controls ----------------------------------------------------------------
# A gate that cannot fire reports a clean tree forever, and this one would be
# especially easy to break silently: a flatten() that returns {} makes every
# comparison vacuous while still exiting 0.
_MUST_FLAG = [
    ("a number replaced by its rendered marker", {"a": {"ref": 1}}, {"a": {"ref": "[1]"}}),
    ("a falsy 0 eaten by `value || ''`", {"a": {"ref": 0}}, {"a": {"ref": ""}}),
    ("a bool swapped for a number", {"a": True}, {"a": 1}),
    ("a value inside a list", {"a": [{"n": 2}]}, {"a": [{"n": "2"}]}),
]
_MUST_CLEAR = [
    ("an ordinary translated string", {"a": "Hello"}, {"a": "Merhaba"}),
    ("a key the locale has not translated yet", {"a": "Hello", "b": 1}, {"a": "Merhaba"}),
    ("matching numbers", {"a": {"ref": 3}}, {"a": {"ref": 3}}),
    ("an empty string BOTH sides hold on purpose", {"a": ""}, {"a": ""}),
]


def selftest():
    bad = 0
    for name, en_doc, loc_doc in _MUST_FLAG:
        if not compare(en_doc, loc_doc):
            print("CONTROL FAILED (should flag): %s" % name, file=sys.stderr)
            bad += 1
    for name, en_doc, loc_doc in _MUST_CLEAR:
        found = compare(en_doc, loc_doc)
        if found:
            print("CONTROL FAILED (should clear): %s -> %r" % (name, found), file=sys.stderr)
            bad += 1
    return bad


MIN_PAIRS = 8  # www alone has 12 non-English locales; a collapsed glob is a bug


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if selftest():
        print("refusing a verdict: this gate's own controls do not hold", file=sys.stderr)
        return 1
    if args.selftest:
        print("controls hold: %d flag-cases, %d clear-cases" % (len(_MUST_FLAG), len(_MUST_CLEAR)))
        return 0

    root = pathlib.Path(__file__).resolve().parents[3]
    pairs = locale_pairs(root)
    if len(pairs) < MIN_PAIRS:
        print(
            "VACUOUS INPUT: found %d locale pair(s), expected at least %d. A gate that\n"
            "compares nothing exits 0 and reads exactly like a clean tree."
            % (len(pairs), MIN_PAIRS),
            file=sys.stderr,
        )
        return 1

    findings, compared = 0, 0
    for label, en_path, loc_path in pairs:
        try:
            en_doc = json.loads(en_path.read_text(encoding="utf-8"))
            loc_doc = json.loads(loc_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("cannot read %s: %s" % (loc_path, exc), file=sys.stderr)
            return 1
        flat = {}
        flatten(en_doc, [], flat)
        compared += len(flat)
        for key, en_value, loc_value in compare(en_doc, loc_doc):
            print(
                "%s: %s\n    en=%r (%s)  locale=%r (%s)"
                % (
                    label,
                    key,
                    en_value,
                    type(en_value).__name__,
                    loc_value,
                    type(loc_value).__name__,
                ),
                file=sys.stderr,
            )
            findings += 1

    if findings:
        print(file=sys.stderr)
        print(
            "%d locale value(s) differ in TYPE from English. A translated value must keep\n"
            "its type: a number that becomes a string stops satisfying numeric guards, and\n"
            "the consumer renders nothing rather than failing loudly." % findings,
            file=sys.stderr,
        )
        return 1
    print(
        "%d locale pair(s), %d English key(s): every shared value matches its English type"
        % (len(pairs), compared)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
