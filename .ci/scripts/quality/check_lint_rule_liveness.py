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

--------------------------------------------------------------------------
2026-08-15: THE GATE PROVED 3 RULES OUT OF 30 AND WAS SILENT ABOUT 27.

Everything above stayed true and was still nearly worthless in scope. The
implementation had three constants that fenced it in: one probe path
(packages/www/src/i18n/translations/tr.json), a namespace filter that only
looked at `i18n/`, and a hand-written specimen list of five. Repo-wide there
are 30 enabled rules across the `custom`, `i18n` and `i18n-source` plugins, so
a dead `custom/*` rule was invisible here AND to check_lint_scope_coverage.py,
which names this gate as its backstop. No RuleTester exists anywhere in the
repo, so nothing else covered them either.

The logic now lives in the sibling lint-rule-liveness.mjs, which derives its
universe from eslint.config.js instead of listing it -- a hand-written probe
list is precisely the artefact that misses a config block -- and asserts set
equality between the enabled rules and the matrix in BOTH directions. It also
runs on ESLint's JS API in one process rather than spawning `npx eslint` per
rule: 30 rules that way costs over 90 s, which is how a gate gets switched off.
Measured end to end: about 10 s.

THIS FILE STAYS THE ENTRY POINT and stays Python, because four places name this
path: package.json, scripts/ci-runner/manifest.ts, .github/workflows/ci-quality.yml,
and the anti-vacuity registry in .ci/scripts/test/gates/test-gate-anti-vacuity.sh.
Its remaining job is the two vacuity preconditions BELOW, which must be answered
before Node is spawned -- against the empty-tree fixture the anti-vacuity harness
uses, an unguarded `import('eslint')` dies with ERR_MODULE_NOT_FOUND, a non-zero
exit for an environment reason wearing a vacuity failure's exit code.

DO NOT ADD lint-rule-liveness.mjs TO THE manifest.ts `leaves` LIST. The plan
called for that, and it is wrong on two counts, both measured. `leaves` is a
DERIVED field: check-ci-parity.ts:488-495 resolves the package.json command's
own shell structure and fails when the declared list differs, so the extra
entry is reported as a hygiene finding ("declares leaves [...] but package.json
resolves to [...]"). And it buys nothing anyway -- scope-map.cjs:134 matches the
whole of `.ci/` with `full: 'harness'`, so ANY edit under this directory already
forces the full harness scope and reselects this gate.

Design: agent/PLAN-lint-rule-matrix-probe.md
"""

import argparse
import pathlib
import subprocess
import sys

DRIVER = "lint-rule-liveness.mjs"

# Checked BEFORE node starts. Without eslint.config.js there is no rule set to
# resolve, and without node_modules/eslint there is nothing to resolve it with;
# either way the gate would otherwise report that zero enabled rules are
# unhealthy, which is exactly what a healthy repo looks like.
REQUIRED = (
    ("eslint.config.js", "no rule set can be resolved"),
    ("node_modules/eslint", "there is no ESLint to resolve it with"),
)


def main(argv=None):
    # No --selftest flag: the controls are not a separate mode, they run inline
    # on EVERY invocation (see lint-rule-liveness.mjs). A mode nobody remembers
    # to run is how a control stops controlling anything.
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    root = pathlib.Path(__file__).resolve().parents[3]

    for relative, consequence in REQUIRED:
        if not (root / relative).exists():
            print(
                "VACUOUS INPUT: %s is missing, so %s" % (relative, consequence),
                file=sys.stderr,
            )
            return 1

    # cwd is the repo root on purpose: several rules resolve their paths against
    # process.cwd() rather than against the linted file, and a wrong cwd makes
    # some of them throw and others silently no-op -- i.e. look dead.
    return subprocess.run(
        ["node", str(pathlib.Path(__file__).resolve().parent / DRIVER)],
        cwd=str(root),
        check=False,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
