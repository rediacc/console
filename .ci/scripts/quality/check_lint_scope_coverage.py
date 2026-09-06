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

  3. A SCOPE THAT CAN SILENTLY SHRINK. Fixed on 2026-09-06, when the roots were
     widened to the seven below. Failures 1 and 2 were both cured by PASSING
     MORE ROOTS, and nothing then held that widening in place: the roots are
     positional arguments in package.json, so deleting one is a one-word edit
     that removes files from every linter's view and leaves every gate green,
     including this one. The original scan could not see it, because it feeds
     eslint FILE PATHS directly and so only ever measured config-level
     `ignores` -- the root list was the one part of lint scope it did not read.

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

# The npm scripts that carry eslint's ROOT LIST. All three must agree: widening
# check:lint while `lint` and `fix:lint` keep the old list gives a developer a
# clean local run over a narrower tree than CI enforces, which is the same
# invisible-scope failure one script down.
LINT_ROOT_SCRIPTS = ("check:lint", "fix:lint", "lint")

# The wrapper the roots are positional arguments to. Its first argument is a heap
# size in MB, so the roots begin two tokens later.
ESLINT_RUNNER = "eslint-heap.sh"

# Roots whose load-bearingness this gate CANNOT measure, each with the reason.
# Same contract as ESLINT_EXEMPT: an entry is a reviewable claim, not a waiver.
ROOT_UNMEASURABLE = {
    "private/account": (
        "a git submodule (gitlink, mode 160000), so `git ls-files` returns the "
        "pointer and none of the files under it. Dropping this root therefore "
        "uncovers nothing HERE while still narrowing the real lint run, so the "
        "mutant below cannot speak for it. It is separately linted by the second "
        "half of the same npm script, `biome lint private/account/`"
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


def lint_roots(root):
    """The positional roots each lint script hands to eslint, parsed from package.json.

    PARSED, NOT DUPLICATED. A hard-coded copy of the root list here would be a
    second source of truth that drifts from the scripts it claims to describe,
    and a gate comparing its own constant against itself proves nothing about
    what eslint actually runs over.

    Returns {script name: [roots]}, or None when package.json cannot be read at
    all -- which is refused rather than treated as "no roots", because an empty
    list would make every file look uncovered and blame the wrong thing.
    """
    try:
        scripts = json.loads((root / "package.json").read_text())["scripts"]
    except (OSError, ValueError, KeyError):
        return None
    found = {}
    for name in LINT_ROOT_SCRIPTS:
        body = scripts.get(name)
        if body is None:
            continue
        # The eslint call is one `&&`-joined segment; the rest of the script is
        # biome, whose scope is biome.json's allowlist and not these arguments.
        segment = next((seg for seg in body.split("&&") if ESLINT_RUNNER in seg), None)
        if segment is None:
            continue
        tokens = segment.split()
        start = next(i for i, t in enumerate(tokens) if ESLINT_RUNNER in t) + 2
        roots = []
        for token in tokens[start:]:
            if token.startswith("-"):
                break
            roots.append(token)
        found[name] = roots
    return found


def uncovered_by(paths, roots):
    """The files no lint root reaches.

    The gate's real question when handed the WHOLE root list, and the mutant's
    when handed the list minus one. One function for both so the mutant exercises
    the same code the verdict comes from, rather than a lookalike of it.
    """
    return [p for p in paths if not any(p == r or p.startswith(r + "/") for r in roots)]


class BiomeUnreadableError(Exception):
    """biome did not answer the question at all."""


def biome_processes(root, path):
    """True when biome's file selection admits `path`, False when it excludes it.

    RAISES rather than guessing when biome did not run. The first version
    returned `"No files were processed" not in output`, which quietly turned
    "biome is missing" into "biome processed the file" -- and that is exactly
    how it failed: green locally, and on CI it accused biome.json of a discarded
    allowlist when the real story was that biome never executed. A probe that
    cannot distinguish absence from a negative answer is not a probe.
    """
    try:
        out = subprocess.run(
            ["npx", "--no-install", "biome", "format", path],
            capture_output=True,
            text=True,
            cwd=str(root),
            check=False,
        )
    except OSError as exc:
        raise BiomeUnreadableError("could not launch biome: %s" % exc) from exc
    blob = out.stdout + out.stderr
    if "No files were processed" in blob:
        return False
    if "Checked " in blob:
        return True
    raise BiomeUnreadableError(
        "biome produced neither 'Checked' nor 'No files were processed' for %s\n"
        "  exit=%s\n  output:\n%s" % (path, out.returncode, blob[:800] or "  (empty)")
    )


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
    try:
        anchor_in = biome_processes(root, BIOME_ANCHOR)
        canary_in = biome_processes(root, BIOME_CANARY)
    except BiomeUnreadableError as exc:
        print(
            "CANNOT PROBE BIOME, so no verdict about its scope is possible:\n  %s\n"
            "  This is an ENVIRONMENT failure, not a config failure. Do not go\n"
            "  editing biome.json on the strength of it." % exc,
            file=sys.stderr,
        )
        return 1
    if not anchor_in:
        print(
            "CONTROL FAILED: biome does not process %s, which is squarely inside its\n"
            "includes. Its file selection is broken, so nothing below is meaningful."
            % BIOME_ANCHOR,
            file=sys.stderr,
        )
        return 1
    if canary_in:
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

    # ---- LINT ROOTS: they must cover everything, and must not silently shrink -
    # The scan below hands eslint FILE PATHS, so it measures config `ignores` and
    # is blind to the root list. This section is the other half: what package.json
    # actually points eslint at.
    candidates = [f for f in files if not exempt(f)]
    by_script = lint_roots(root)
    if by_script is None:
        print(
            "could not read package.json's scripts, so the lint ROOT LIST cannot be\n"
            "  checked. This is an ENVIRONMENT failure, not a scope failure.",
            file=sys.stderr,
        )
        return 1
    missing = [n for n in LINT_ROOT_SCRIPTS if n not in by_script]
    if missing:
        print(
            "no eslint root list found in package.json script(s): %s\n"
            "  Either the script was renamed or it stopped invoking %s. Until this\n"
            "  parses, nothing below can speak for eslint's scope."
            % (", ".join(missing), ESLINT_RUNNER),
            file=sys.stderr,
        )
        return 1

    # All three must agree, or a developer's `npm run lint` covers a narrower tree
    # than CI's `check:lint` enforces and passes locally on code CI will reject.
    distinct = {tuple(r) for r in by_script.values()}
    if len(distinct) != 1:
        print("the lint scripts disagree about eslint's roots:", file=sys.stderr)
        for name in LINT_ROOT_SCRIPTS:
            print("    %-12s %s" % (name, " ".join(by_script[name])), file=sys.stderr)
        print(
            "\n  All of %s must pass the SAME roots. Widening one alone gives a clean\n"
            "  local run over a tree CI lints more of." % ", ".join(LINT_ROOT_SCRIPTS),
            file=sys.stderr,
        )
        return 1
    roots = list(distinct.pop())

    # VACUITY: no roots at all would make every file "uncovered" and report a
    # scope catastrophe when the truth is that the parse failed.
    if not roots:
        print(
            "VACUOUS: parsed an EMPTY root list out of the lint scripts. eslint would\n"
            "  be given no paths at all, so the coverage numbers below are meaningless.",
            file=sys.stderr,
        )
        return 1

    outside = uncovered_by(candidates, roots)
    if outside:
        print(
            "%d tracked file(s) are outside every eslint ROOT, so no amount of config\n"
            "correctness can reach them (roots: %s):" % (len(outside), " ".join(roots)),
            file=sys.stderr,
        )
        for path in sorted(outside)[:40]:
            print("    %s" % path, file=sys.stderr)
        if len(outside) > 40:
            print("    ... and %d more" % (len(outside) - 40), file=sys.stderr)
        print(
            "\n  Add the root to all of %s, or exempt the prefix in ESLINT_EXEMPT here\n"
            "  WITH THE REASON it is not source." % ", ".join(LINT_ROOT_SCRIPTS),
            file=sys.stderr,
        )
        return 1

    # ---- CONTROL: the assertion above must have TEETH ------------------------
    # "Everything is covered" is satisfied just as well by a root list that is too
    # WIDE, and a passing coverage check says nothing about whether removing a
    # root would be noticed. So mutate: drop each root in turn and require the
    # very same uncovered_by() call to come back non-empty. A root whose removal
    # changes nothing is a root this gate would let someone delete in silence.
    for dropped in roots:
        if uncovered_by(candidates, [r for r in roots if r != dropped]):
            continue
        why = ROOT_UNMEASURABLE.get(dropped)
        if why is not None:
            continue
        print(
            "CONTROL FAILED: dropping the root '%s' leaves every tracked file still\n"
            "  covered, so this gate would stay GREEN if someone deleted it from\n"
            "  package.json. The scope check above is not holding that root in place.\n"
            "\n  Either the root is redundant (another root already contains it, and it\n"
            "  should be removed deliberately rather than left as decoration), or its\n"
            "  files are untracked/exempt here -- in which case add it to\n"
            "  ROOT_UNMEASURABLE with the reason, the way private/account is." % dropped,
            file=sys.stderr,
        )
        return 1

    proven = [r for r in roots if r not in ROOT_UNMEASURABLE]
    print(
        "%d eslint root(s) cover every tracked file; %d proven load-bearing by the\n"
        "  drop-one mutant (%s)" % (len(roots), len(proven), " ".join(proven))
    )

    # ---- the real scan ------------------------------------------------------
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
