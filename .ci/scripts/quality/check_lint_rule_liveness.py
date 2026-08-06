#!/usr/bin/env python3
"""An ENABLED lint rule must be able to fire. Prove it, per rule, by mutation.

WHY THIS EXISTS. On 2026-08-06 five of this repo's own i18n rules were found
reading `node.body?.members` on an @eslint/json Object node, which carries
`members` DIRECTLY. They walked an empty list and COULD NOT REPORT ANYTHING,
EVER -- while configured at severity 'error' the whole time. `sorted-keys` alone
had 2172 real findings waiting behind that one word, and the repo had been
reading its silence as compliance for as long as the rules had existed.

WHY "DOES IT HAVE FINDINGS" IS THE WRONG TEST, and this is the whole design.
A healthy rule on a clean tree reports zero, exactly like a broken one. Counting
findings cannot separate them. So this plants a violation the rule is SUPPOSED
to catch and asserts the rule catches it. A rule that cannot fire on its own
planted defect is broken, whatever the tree looks like.

That also makes this gate self-proving in the sense the repo cares about: it IS
a control, run per rule, every time.

ADDING A RULE MEANS ADDING A SPECIMEN. That is deliberate friction. A rule with
no specimen here is reported as unproven and fails the gate, because "we forgot
to write the test" and "the rule cannot fire" look identical from outside, and
this whole file exists because that ambiguity cost the repo five rules.
"""

import argparse
import json
import pathlib
import subprocess
import sys

# rule id -> (filename written into the fixture, content that MUST trip it)
#
# Content is chosen to violate exactly one rule so a specimen cannot pass by
# accidentally tripping a neighbour. Keep them minimal; a big specimen makes a
# failure hard to read.
SPECIMENS = {
    # Key SHAPE matters as much as content. seo-title-length only looks at paths
    # ending ".meta.title" (seo-title-length.js:53), seo-description-length at
    # ".meta.description" (:51), and seo-no-duplicate-h1-title compares a
    # sibling "hero.title" against "meta.title". A specimen with the right text
    # under the wrong key is silent, and reads exactly like a dead rule -- the
    # first draft of this file made that mistake and accused all three.
    "i18n/seo-title-length": (
        "tr.json",
        '{\n  "pages": {\n    "x": {\n      "meta": {\n        "title": "%s"\n'
        "      }\n    }\n  }\n}\n" % ("uzun baslik " * 12),
    ),
    "i18n/seo-description-length": (
        "tr.json",
        '{\n  "pages": {\n    "x": {\n      "meta": {\n        "description": "%s"\n'
        "      }\n    }\n  }\n}\n" % ("cok uzun aciklama " * 20),
    ),
    "i18n/seo-no-duplicate-h1-title": (
        "tr.json",
        '{\n  "pages": {\n    "x": {\n      "meta": {\n        "title": "Yedekleme Cozumu"\n'
        '      },\n      "hero": {\n        "title": "Yedekleme Cozumu"\n'
        "      }\n    }\n  }\n}\n",
    ),
    # The five that were inert. They are 'off' today by an explicit, documented
    # decision (see eslint.config.js), so this gate does not require them to
    # fire -- but the specimens stay, so the day someone turns one back on it is
    # proven live in the same commit rather than years later.
    "i18n/sorted-keys": ("tr.json", '{\n  "b": "1",\n  "a": "2"\n}\n'),
    "i18n/no-empty-translations": ("tr.json", '{\n  "a": ""\n}\n'),
}


def enabled_rules(root, probe):
    """{rule id: severity} for every i18n/* rule ESLint resolves for `probe`."""
    out = subprocess.run(
        ["npx", "eslint", "--print-config", probe],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    if out.returncode != 0:
        return None
    try:
        cfg = json.loads(out.stdout)
    except ValueError:
        return None
    rules = {}
    for key, value in (cfg.get("rules") or {}).items():
        if not key.startswith("i18n/"):
            continue
        rules[key] = value[0] if isinstance(value, list) else value
    return rules


# The specimen must sit FLAT in the translations directory, not in a temp
# subdirectory. eslint.config.js matches these rules with
# `packages/www/src/i18n/translations/*.json` -- a SINGLE star, which does not
# cross a directory boundary. The first version of this gate wrote its fixtures
# into a nested mkdtemp and every rule came back "dead"; measured, a nested path
# resolves 0 i18n rules and a flat one resolves 5. The gate was broken, not the
# rules, and it would have been a very convincing accusation.
SPECIMEN_DIR = "packages/www/src/i18n/translations"
SPECIMEN_STEM = "zz-rule-liveness-probe"


def fires(root, rule, filename, content):
    """True when `rule` reports on its own specimen."""
    suffix = pathlib.Path(filename).suffix or ".json"
    target = root / SPECIMEN_DIR / (SPECIMEN_STEM + suffix)
    try:
        target.write_text(content, encoding="utf-8")
        out = subprocess.run(
            ["npx", "eslint", str(target), "-f", "json", "--rule", json.dumps({rule: "error"})],
            capture_output=True,
            text=True,
            cwd=str(root),
            check=False,
        )
        try:
            report = json.loads(out.stdout)
        except ValueError:
            return False
        return any(
            msg.get("ruleId") == rule for entry in report for msg in entry.get("messages", [])
        )
    finally:
        # ALWAYS, including on an exception: a stray locale file left behind
        # would be picked up by the locale-set gates as a real one.
        target.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    root = pathlib.Path(__file__).resolve().parents[3]
    probe = "packages/www/src/i18n/translations/tr.json"
    if not (root / probe).is_file():
        print(
            "VACUOUS INPUT: %s is missing, so no rule set can be resolved" % probe, file=sys.stderr
        )
        return 1

    rules = enabled_rules(root, probe)
    if rules is None:
        print("cannot resolve the eslint config for %s" % probe, file=sys.stderr)
        return 1
    if len(rules) < 2:
        print(
            "VACUOUS INPUT: only %d i18n rule(s) resolved for %s. A gate that proves\n"
            "nothing exits 0 and reads exactly like a healthy rule set." % (len(rules), probe),
            file=sys.stderr,
        )
        return 1

    on = sorted(r for r, sev in rules.items() if sev)
    off = sorted(r for r, sev in rules.items() if not sev)

    # CONTROL: the harness must be able to say NO. A rule pointed at a specimen
    # that does not violate it has to come back dead, or every verdict below is
    # meaningless.
    if fires(root, "i18n/sorted-keys", "tr.json", '{\n  "a": "1",\n  "b": "2"\n}\n'):
        print(
            "CONTROL FAILED: sorted-keys 'fired' on ALREADY-SORTED input, so this\n"
            "harness cannot distinguish firing from not firing. Refusing a verdict.",
            file=sys.stderr,
        )
        return 1

    dead, unproven = [], []
    for rule in on:
        spec = SPECIMENS.get(rule)
        if spec is None:
            unproven.append(rule)
            continue
        if not fires(root, rule, *spec):
            dead.append(rule)

    if unproven:
        print(
            "%d enabled rule(s) have no specimen here, so nothing proves they can fire:"
            % len(unproven),
            file=sys.stderr,
        )
        for rule in unproven:
            print("    %s" % rule, file=sys.stderr)
        print("  Add one to SPECIMENS: input that MUST trip the rule.", file=sys.stderr)
    if dead:
        print(
            "%d ENABLED rule(s) did NOT fire on a violation they are supposed to catch:"
            % len(dead),
            file=sys.stderr,
        )
        for rule in dead:
            print("    %s" % rule, file=sys.stderr)
        print(
            "  That is the sorted-keys defect again: enabled, and structurally unable\n"
            "  to report. Fix the rule -- do not lower its severity to hide this.",
            file=sys.stderr,
        )
    if unproven or dead:
        return 1

    print(
        "%d enabled i18n rule(s) each fired on a planted violation; %d off by "
        "documented decision" % (len(on), len(off))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
