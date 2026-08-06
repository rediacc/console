#!/usr/bin/env python3
"""No tracked source file may be invisible to every linter, and biome's
allowlist must actually be in force.

WHY THIS EXISTS. Two failures on 2026-08-06, and neither was a rule being wrong
about code -- both were code no rule ever looked at.

  1. SCOPE INVISIBILITY. `check:lint` ran eslint over `packages scripts
     private/account`, and four ignore entries removed most of what remained.
     93 files were linted by nothing: eslint-rules/ (42 -- the repo's own custom
     lint rules), .ci/ (21, including the live CI scope engine), and
     packages/*/scripts/ (18, which implement TEN check:ci-* gates), plus
     workers/ and .github/actions/ which were simply never passed as arguments.
     Every gate was green the whole time, because a file outside scope cannot
     produce a finding.

  2. A SILENTLY DISCARDED ALLOWLIST. A single `//` comment anywhere in
     biome.json's `files` object makes biome throw away the entire `includes`
     list -- no parse error, no warning. Measured: `biome lint private/account/`
     goes from 631 files to 1428 and reports 3657 errors. The failure LOOKS like
     a lint explosion in unrelated code, which is why it cost two attempts to
     attribute.

Both are the same shape as the dead i18n rules: the instrument reports success
because it never examined anything. check_lint_rule_liveness.py proves an
ENABLED RULE can fire; this proves the FILES reach a rule at all.

WHAT IT DOES NOT DO. It does not judge whether a file's rules are the right
rules -- only that some linter sees it. A file linted by a config that happens
to enable nothing would pass here and be caught by the liveness gate instead.
The two are complements and neither subsumes the other.
"""

import argparse
import json
import pathlib
import subprocess
import sys

# Extensions a linter is expected to cover, and the tool responsible.
JS_EXT = (".js", ".jsx", ".cjs", ".mjs", ".ts", ".tsx")

# Paths eslint legitimately does not lint, each with the reason it is exempt.
# An entry here is a claim that the file is not source, and it is reviewable.
ESLINT_EXEMPT = {
    "packages/cli/templates/": "shipped template files, embedded into the CLI binary rather than executed here",
    "packages/www/public/": "static site assets, including large generated search-index bundles",
    "packages/json/": "data templates for the JSON package, not program source",
    "private/": "submodules and sibling repos with their own CI",
    ".ci/cache/": "generated CI state, rewritten by CI on every run",
}

# Suffix-matched exemptions, same contract: each is a claim that the file is not
# executable source, and each is reviewable.
ESLINT_EXEMPT_SUFFIX = {
    ".d.ts": (
        "type declarations only -- no executable code for a rule to have an "
        "opinion about; tsc is the checker that matters for these"
    ),
}

# Whole-file exemptions, for files that ARE source but that a GLOBAL ignore
# pattern blocks. A `files:` block cannot override a global `ignores` entry in
# flat config, so bringing these in means editing the ignore itself.
ESLINT_EXEMPT_EXACT = {
    "eslint.config.js": (
        "blocked by the global '*.config.js' ignore, which also covers the vite, "
        "vitest and astro configs -- un-ignoring it is a scoped decision of its "
        "own. It additionally contains a no-restricted-syntax selector that "
        "matches ITSELF (the string literal that defines the ban), so linting it "
        "needs that one rule off for that one file"
    ),
}

# A path that MUST be outside biome's includes. If biome starts processing it,
# the allowlist has been discarded -- which is exactly what a stray comment in
# the `files` object does, silently.
BIOME_CANARY = "packages/www/src/i18n/translations/.translation-hashes.json"
# A path that MUST be inside it, so "everything is out of scope" cannot pass.
BIOME_ANCHOR = "packages/cli/src/index.ts"


def tracked(root, patterns):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", *patterns],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return None
    return out.stdout.split()


def exempt(path):
    if path in ESLINT_EXEMPT_EXACT:
        return ESLINT_EXEMPT_EXACT[path]
    for suffix, why in ESLINT_EXEMPT_SUFFIX.items():
        if path.endswith(suffix):
            return why
    return next((why for prefix, why in ESLINT_EXEMPT.items() if path.startswith(prefix)), None)


def eslint_ignored(root, paths):
    """The subset of `paths` eslint reports as ignored by configuration."""
    out = subprocess.run(
        ["npx", "eslint", "-f", "json", "--no-error-on-unmatched-pattern", *paths],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    try:
        report = json.loads(out.stdout)
    except ValueError:
        return None
    ignored = []
    for entry in report:
        rel = entry["filePath"].split("/console/")[-1]
        if any("File ignored" in (m.get("message") or "") for m in entry.get("messages", [])):
            ignored.append(rel)
    return ignored


def biome_processes(root, path):
    """True when biome's file selection actually admits `path`."""
    out = subprocess.run(
        ["npx", "biome", "format", path],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    blob = out.stdout + out.stderr
    return "No files were processed" not in blob


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    root = pathlib.Path(__file__).resolve().parents[3]

    files = tracked(root, ["*" + e for e in JS_EXT])
    if files is None:
        print("VACUOUS INPUT: not a git work tree, so nothing can be enumerated", file=sys.stderr)
        return 1
    if len(files) < 200:
        print(
            "VACUOUS INPUT: only %d js/ts file(s) tracked, expected 200+. A coverage\n"
            "check over an empty set exits 0 and reads exactly like full coverage." % len(files),
            file=sys.stderr,
        )
        return 1

    # ---- CONTROL: biome's allowlist must be demonstrably IN FORCE -----------
    # Both directions, because one alone is satisfiable by a broken config: an
    # allowlist that admits everything passes the anchor, and one that admits
    # nothing passes the canary.
    if not biome_processes(root, BIOME_ANCHOR):
        print(
            "CONTROL FAILED: biome does not process %s, which is squarely inside its\n"
            "includes. Its file selection is broken, so nothing below is meaningful."
            % BIOME_ANCHOR,
            file=sys.stderr,
        )
        return 1
    if biome_processes(root, BIOME_CANARY):
        print(
            "biome is processing %s, which is EXCLUDED by biome.json.\n"
            "  Its `includes` allowlist is not in force. The usual cause is a `//`\n"
            "  comment somewhere in the `files` object: biome then discards the whole\n"
            "  list with NO parse error and NO warning, and lint scope silently\n"
            "  widens (measured 2026-08-06: 631 files -> 1428, 3657 errors).\n"
            "  Move the comment outside `files`." % BIOME_CANARY,
            file=sys.stderr,
        )
        return 1

    # ---- the real scan ------------------------------------------------------
    candidates = [f for f in files if not exempt(f)]
    ignored = eslint_ignored(root, candidates)
    if ignored is None:
        print("could not read eslint's report; refusing a verdict", file=sys.stderr)
        return 1

    if ignored:
        print(
            "%d tracked file(s) are linted by NOTHING -- eslint ignores them and they\n"
            "carry no documented exemption:" % len(ignored),
            file=sys.stderr,
        )
        for path in sorted(ignored)[:40]:
            print("    %s" % path, file=sys.stderr)
        if len(ignored) > 40:
            print("    ... and %d more" % (len(ignored) - 40), file=sys.stderr)
        print(
            "\n  Either bring them into scope (that is what happened to eslint-rules/,\n"
            "  .ci/, workers/ and packages/*/scripts/ on 2026-08-06, and it surfaced a\n"
            "  build-breaking crash plus five dead rules), or add the prefix to\n"
            "  ESLINT_EXEMPT here WITH THE REASON it is not source.",
            file=sys.stderr,
        )
        return 1

    print(
        "%d tracked js/ts file(s) reach a linter (%d exempt by documented reason); "
        "biome's allowlist is in force" % (len(candidates), len(files) - len(candidates))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
